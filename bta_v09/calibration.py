"""Read-only holdout audit of REAL prospectively logged forecasts + settlements.

No missing settlements are invented or treated as losses, and records of unknown
provenance do not count toward a verified calibration dataset.
"""
from __future__ import annotations
from collections import defaultdict
from bta_v07.calibration import calibrated_holdout


def validate_archive(forecasts:list[dict], settlements:list[dict]) -> dict:
    settled={}
    for s in settlements:
        if s.get('verified_settlement') is not True or s.get('outcome') not in (0,1) or isinstance(s.get('outcome'),bool):
            continue
        if not str(s.get('settlement_source','')).startswith('https://'):
            continue
        key=s.get('forecast_id')
        if key in settled:  # conflicting or duplicate audit → exclude all duplicate claims
            settled[key]=None
        else:
            settled[key]=s
    grouped=defaultdict(list)
    rejected=0
    for f in forecasts:
        s=settled.get(f.get('forecast_id'))
        if s is None:
            rejected+=1;continue
        if f.get('model_id')!='historical-beta(2,2)-v09-NOT-CALIBRATED':
            rejected+=1;continue
        if not f.get('features_asof_utc') or not f.get('prediction_at_utc'):
            rejected+=1;continue
        if s.get('event_id')!=f.get('event_id') or s.get('market_id')!=f.get('market_id'):
            rejected+=1;continue
        if s.get('event_start_utc')!=f.get('event_start_utc'):
            rejected+=1;continue
        bucket=(f.get('league'),f.get('market'))
        grouped[bucket].append({'event_id':f['event_id'],'market_id':f['market_id'],
                                'probability':f['experimental_probability'],
                                'outcome':s['outcome'], 'event_start_utc':f['event_start_utc'],
                                'prediction_at_utc':f['prediction_at_utc'],
                                'features_asof_utc':f['features_asof_utc']})
    reports={}
    for (league,market),rows in grouped.items():
        reports[f'{league}:{market}']=calibrated_holdout(rows)
    return {'status':'AUDIT COMPLETE','verified_matched':sum(len(v) for v in grouped.values()),
            'unmatched_or_invalid':rejected,'groups':reports,
            'note':'Forecast records are eligible for evaluation only when a separate '
                   'timestamped market-specific settlement has been verified. '
                   'Holdout checks passing is not a guarantee of future profitability.'}
