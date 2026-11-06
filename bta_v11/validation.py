"""Prospective model validation from pre-event, exact-market archived forecasts.

All statistics here are model validation signals, not proof of profitable picks.
For unknown/void/push outcomes calibration is not computed for that market.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import datetime,timezone
from math import log
from .common import parse_time,number


def _brier(rows,key):return sum((r[key]-r['y'])**2 for r in rows)/len(rows)

def _logloss(rows,key):
    return sum(-r['y']*log(max(r[key],1e-12))-(1-r['y'])*log(max(1-r[key],1e-12)) for r in rows)/len(rows)


def validate(forecasts:list[dict],*,model_id:str,market_family:str,
             min_train=250,min_test=100,min_test_events=50,n_bins=5, evaluation_now=None)->dict:
    """Chronological split (entire event stays on one side), never retrain on test.

    Forecast input fields: event_id, market_id, league, market_family, model_id,
    event_start_utc, forecast_utc, features_asof_utc, settled_utc, outcome (0|1),
    probability, authenticated_settlement=True. Exact offered line is identified
    by market_id. Model version must be held constant.
    """
    at=parse_time(evaluation_now) if evaluation_now is not None else datetime.now(timezone.utc)
    if at is None:
        return {'status':'INVALID_EVALUATION_CLOCK'}
    if min_train<30 or min_test<30 or min_test_events<10 or not 2<=n_bins<=12:
        raise ValueError('Validation minima too small')
    count=Counter((r.get('event_id'),r.get('market_id')) for r in forecasts)
    rows=[];rejected=0
    for r in forecasts:
        key=(r.get('event_id'),r.get('market_id'))
        if count[key]!=1 or not all(key) or r.get('model_id')!=model_id or r.get('market_family')!=market_family:
            rejected+=1;continue
        event=parse_time(r.get('event_start_utc'));forecast=parse_time(r.get('forecast_utc'))
        asof=parse_time(r.get('features_asof_utc'));settled=parse_time(r.get('settled_utc'))
        p=number(r.get('probability'));out=r.get('outcome')
        if (not event or not forecast or not asof or not settled or
            not asof<=forecast<event<settled<=at or p is None or not 0<p<1 or
            type(out)!=int or out not in (0,1) or r.get('authenticated_settlement') is not True):
            rejected+=1;continue
        rows.append({'date':event.date(),'event_id':key[0],'market_id':key[1],
                     'p':p,'y':out,'settled':settled,'forecast':forecast})
    if len(rows)<min_train+min_test:
        return {'status':'INSUFFICIENT_PROSPECTIVE_DATA','accepted':len(rows),'rejected':rejected,
                'required_train':min_train,'required_test':min_test}
    by_date=defaultdict(list)
    for r in rows:by_date[r['date']].append(r)
    dates=sorted(by_date)
    train=[];cutoff=None
    for date in dates:
        train.extend(by_date[date])
        if len(train)>=max(min_train,int(.7*len(rows))):cutoff=date;break
    # Outcomes used in training must already be available before the first
    # held-out forecast. Skipping an intervening gap is safer than lookahead.
    trained_through=max(r['settled'] for r in train) if train else at
    test=[r for r in rows if r['date']>cutoff and r['forecast']>trained_through] if cutoff else []
    if len(train)<min_train or len(test)<min_test or len({r['event_id'] for r in test})<min_test_events:
        return {'status':'INSUFFICIENT_OUT_OF_TIME_HOLDOUT','train':len(train),'test':len(test),
                'test_events':len({r['event_id'] for r in test}),'rejected':rejected}
    baseline=sum(r['y'] for r in train)/len(train)
    groups=defaultdict(list)
    for r in train:groups[min(n_bins-1,int(r['p']*n_bins))].append(r['y'])
    mapping={i:(sum(groups[i])+15*baseline)/(len(groups[i])+15) for i in range(n_bins)}
    evaluated=[]
    for r in test:
        evaluated.append({**r,'cal':mapping[min(n_bins-1,int(r['p']*n_bins))], 'baseline':baseline})
    # ECE on held-out data; bin by calibrated probability.
    buckets=defaultdict(list)
    for r in evaluated:buckets[min(n_bins-1,int(r['cal']*n_bins))].append(r)
    ece=sum(len(rows_in_bin)/len(evaluated)*abs(
       sum(x['cal'] for x in rows_in_bin)/len(rows_in_bin)-
       sum(x['y'] for x in rows_in_bin)/len(rows_in_bin)) for rows_in_bin in buckets.values())
    metrics={'brier_calibrated':_brier(evaluated,'cal'),
             'brier_raw':_brier(evaluated,'p'),
             'brier_train_frequency_baseline':_brier(evaluated,'baseline'),
             'logloss_calibrated':_logloss(evaluated,'cal'),
             'calibration_ece':ece}
    pass_heuristic=(metrics['brier_calibrated'] < metrics['brier_train_frequency_baseline']
                    and metrics['calibration_ece']<=.08)
    return {'status':'OUT_OF_TIME_DIAGNOSTICS_PASS' if pass_heuristic else 'OUT_OF_TIME_DIAGNOSTICS_FAIL',
            'train':len(train),'test':len(test),'test_event_count':len({r['event_id'] for r in test}),
            'cutoff_date':str(cutoff),'rejected':rejected,
            'metrics':{k:round(v,6) for k,v in metrics.items()},
            'model_id':model_id,'market_family':market_family,
            'calibration_mapping':{str(i):round(x,6) for i,x in mapping.items()},
            'note':'Heuristic checks do not prove stability, independence, edge or certification. Results must be continuously monitored on future untouched data.'}
