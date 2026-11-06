"""Chronological validation of *timestamped pregame* probability snapshots.
A score obtained after an event or a future market line is never valid input.
"""
from __future__ import annotations
import math
from datetime import datetime, timezone


def parse_utc(s):
    try:
        d=datetime.fromisoformat(str(s).replace('Z','+00:00'))
    except (ValueError,TypeError):return None
    if d.tzinfo is None:return None
    return d.astimezone(timezone.utc)


def metrics(rows, column):
    n=len(rows)
    if not n:return None
    p=[r[column] for r in rows]; y=[r['outcome'] for r in rows]
    return {'n':n,'brier':round(sum((a-b)**2 for a,b in zip(p,y))/n,5),
            'hit_rate':round(sum(y)/n,5),'avg_forecast':round(sum(p)/n,5),
            'log_loss':round(sum(-b*math.log(max(1e-9,min(a,1-1e-9)))-(1-b)*math.log(max(1e-9,min(1-a,1-1e-9))) for a,b in zip(p,y))/n,5)}


def calibrated_holdout(records:list[dict],*,min_train:int=300,min_test:int=100,
                       min_distinct_test_dates:int=12, n_bins:int=5) -> dict:
    """Train on oldest events, test later events without same-date overlap.

    The input rows must include: event_id, market_id, probability, outcome (0/1),
    event_start_utc, prediction_at_utc, features_asof_utc. All pregame.
    Same event may have several distinct markets; confidence intervals derived
    from records may understate uncertainty due to correlation.
    """
    if min_train<10 or min_test<10:raise ValueError('Validation minima too small')
    if not 2<=n_bins<=20:raise ValueError('n_bins out of bounds')
    clean=[];seen=set();rejected=[]
    for idx,r in enumerate(records):
        ident=(r.get('event_id'),r.get('market_id'))
        dt=parse_utc(r.get('event_start_utc'));made=parse_utc(r.get('prediction_at_utc'))
        asof=parse_utc(r.get('features_asof_utc'))
        try:p=float(r.get('probability'));outcome=int(r.get('outcome'))
        except (ValueError,TypeError):p=float('nan');outcome=-1
        if not all(ident) or ident in seen or not dt or not made or not asof or not (asof<=made<dt) or not math.isfinite(p) or not 0<p<1 or outcome not in (0,1):
            rejected.append(idx);continue
        seen.add(ident)
        clean.append({'event_id':ident[0],'market_id':ident[1],'date':dt.date(),
                      'p':p,'outcome':outcome})
    clean.sort(key=lambda r:(r['date'],r['event_id'],r['market_id']))
    if len(clean)<min_train+min_test:
        return {'status':'INSUFFICIENT','usable':len(clean),'rejected_rows':len(rejected),
                'reason':'Not enough verifiable *pregame* forecasts for chronological calibration'}
    cutoff=clean[max(min_train,int(.7*len(clean)))-1]['date']
    train=[r for r in clean if r['date']<=cutoff];test=[r for r in clean if r['date']>cutoff]
    if len(train)<min_train or len(test)<min_test or len({r['date'] for r in test})<min_distinct_test_dates:
        return {'status':'INSUFFICIENT','train':len(train),'test':len(test),
                'reason':'Insufficient independent dates for strictly later testing'}
    baseline=sum(r['outcome'] for r in train)/len(train)
    buckets={i:[] for i in range(n_bins)}
    for r in train:buckets[min(n_bins-1,int(r['p']*n_bins))].append(r)
    table={i:(sum(r['outcome'] for r in bucket)+25*baseline)/(len(bucket)+25)
           for i,bucket in buckets.items()}
    evaluated=[]
    for r in test:
        evaluated.append({'p':r['p'],'cal':table[min(n_bins-1,int(r['p']*n_bins))],
                          'base':baseline,'outcome':r['outcome']})
    raw=metrics(evaluated,'p');cal=metrics(evaluated,'cal');base=metrics(evaluated,'base')
    ece=sum(len(sub)/len(evaluated)*abs(sum(z['cal'] for z in sub)/len(sub)-sum(z['outcome'] for z in sub)/len(sub))
            for i in range(n_bins) if (sub:=[r for r in evaluated if min(n_bins-1,int(r['cal']*n_bins))==i]))
    passed=cal['brier']<base['brier'] and ece<=0.08
    return {'status':'FORECAST_CHECKS_PASS' if passed else 'FORECAST_CHECKS_FAIL',
            'train':len(train),'test':len(test),'train_cutoff_date':str(cutoff),
            'test_distinct_dates':len({r['date'] for r in test}),
            'raw':raw,'calibrated':cal,'training_frequency_baseline':base,
            'expected_calibration_error':round(ece,5),
            'bins':{str(i):len(buckets[i]) for i in buckets},
            'rejected_rows':len(rejected),
            'warnings':['No proof of profitable betting without timestamped *actual market odds* and costs.',
                        'Multiple props within a game are correlated; effective sample size may be lower.',
                        'The 8-percentage-point ECE gate is a heuristic, not evidence of universal calibration.',
                        'Do not reuse holdout data to tune this model and then claim it remains untouched.']}
