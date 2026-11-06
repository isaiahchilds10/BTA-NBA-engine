"""Leakage-aware chronological evaluation and experimental probability calibration.

Supply predictions MADE PRIOR TO their events; do not supply hindsight fitted
probabilities, future injuries, or historical lines invented after results.
"""
from __future__ import annotations

import math
from datetime import datetime


def _brier(p, y): return (p-y)**2


def _logloss(p,y):
    p = max(1e-9,min(1-1e-9,p))
    return -y*math.log(p)-(1-y)*math.log(1-p)


def _summary(records: list[dict], kind='raw'):
    if not records:return {}
    n=len(records)
    return {'n':n,
            'brier':sum(_brier(r[kind],r['outcome']) for r in records)/n,
            'log_loss':sum(_logloss(r[kind],r['outcome']) for r in records)/n,
            'avg_pred':sum(r[kind] for r in records)/n,
            'hit_rate':sum(r['outcome'] for r in records)/n}


def fit_evaluate(records: list[dict], *, min_train=300, min_test=100) -> dict:
    """Use first 70% by event date for calibration; untouched last 30% evaluation.

    All events on the same date remain in one partition. Enforces uniqueness of
    market event IDs, if provided. Five regularized fixed probability bins.
    """
    rows=[];seen=set()
    for r in records:
        try:
            p=float(r['probability']); y=int(r['outcome'])
            dt=datetime.fromisoformat(str(r['date']).replace('Z','+00:00'))
        except (KeyError,ValueError,TypeError):
            raise ValueError('Record missing valid date, probability or binary outcome')
        if not math.isfinite(p) or not (0<=p<=1) or y not in (0,1):
            raise ValueError('Invalid probability or outcome')
        # A caller can provide a unique market-event ID; skip duplicate predictions,
        # not different legitimate markets played same day.
        ident=r.get('id')
        if ident is not None:
            if ident in seen: raise ValueError('Duplicate observation ID')
            seen.add(ident)
        rows.append({'date':dt,'raw':p,'outcome':y})
    rows.sort(key=lambda x:x['date'])
    if len(rows)<min_train+min_test:
        return {'status':'NOT VALIDATED','reason':'Not enough chronologically ordered predictions',
                'observations':len(rows),'minimum':min_train+min_test}
    desired=min(len(rows)-min_test,max(min_train,int(len(rows)*.7)))
    cutoff=rows[desired-1]['date']
    # Remove date-boundary leakage; no games on cutoff day enter the holdout.
    train=[r for r in rows if r['date']<=cutoff]
    test=[r for r in rows if r['date']>cutoff]
    if len(train)<min_train or len(test)<min_test:
        return {'status':'NOT VALIDATED','reason':'Insufficient distinct days after chronological split',
                'train':len(train),'test':len(test)}
    bins={i:[] for i in range(5)}
    for r in train:
        bins[min(int(r['raw']*5),4)].append(r)
    train_base=sum(r['outcome'] for r in train)/len(train)
    # Smoothed frequency per 20%-wide bin; regularize to training rate (not 50%).
    # This mapping is learned only on training observations.
    estimates={i:(sum(r['outcome'] for r in sample)+20*train_base)/(len(sample)+20)
               for i,sample in bins.items()}
    cal=[]
    for r in test:
        cal.append({**r,'calibrated':estimates[min(int(r['raw']*5),4)],'train_baseline':train_base})
    raw=_summary(cal,'raw'); post=_summary(cal,'calibrated'); base=_summary(cal,'train_baseline')
    n=len(cal)
    ece=0
    for idx in range(5):
        bucket=[r for r in cal if min(int(r['calibrated']*5),4)==idx]
        if bucket:ece+=len(bucket)/n*abs(sum(r['calibrated'] for r in bucket)/len(bucket)-sum(r['outcome'] for r in bucket)/len(bucket))
    return {'status':'TESTED / NOT PROVEN BETTING EDGE',
            'train':len(train),'test':len(test),'cutoff':cutoff.isoformat(),
            'raw':raw,'calibrated':post,'train_frequency_baseline':base,
            'test_expected_calibration_error':round(ece,4),
            'bins_train_counts':{i:len(bins[i]) for i in range(5)},
            'postprocess_improved_brier':post['brier']<raw['brier'],
            'beats_simple_baseline':post['brier']<base['brier'],
            'reason':'No sportsbook odds/actual offered lines were tested. Event selection, model updates, '
                     'correlated observations, live lineup knowledge, and transaction costs are NOT validated.'}


def cfb_records_from_elo(predictions: list[dict]) -> list[dict]:
    return [{'id':g['event_id'] or f"{g['date']}:{g['home']}:{g['away']}",
             'date':g['date'],'probability':g['p_home_raw'],'outcome':g['home_won']}
            for g in predictions]
