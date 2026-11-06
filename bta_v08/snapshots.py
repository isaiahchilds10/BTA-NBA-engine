"""Immutable, timestamped *research snapshots* for audit / later validation.

Snapshots deliberately DO NOT contain predictive probabilities until a separate
validated model supplies them. They cannot be backfilled as pregame forecasts.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from hashlib import sha256
from .schedule import parse_instant


def make_snapshot(event:dict,selected:list[dict],*,observed_at_utc:str) -> dict:
    observed=parse_instant(observed_at_utc)
    scheduled=parse_instant(event.get('start_utc'))
    if not observed or not scheduled:
        raise ValueError('Timestamp required')
    if observed>=scheduled:
        raise ValueError('Research snapshot must be recorded BEFORE scheduled kickoff/tipoff')
    if event.get('status')!='UPCOMING':
        raise ValueError('Event not confirmed upcoming')
    markets=[]
    for item in selected:
        offer=item.get('offer') or {}
        if offer.get('american_odds') is None:
            raise ValueError('Timestamped actual offer required')
        markets.append({'market':offer.get('market'),'player':offer.get('player'),
                        'selection':offer.get('selection'),'line':offer.get('line'),
                        'american_odds':offer['american_odds'],
                        'book_updated_utc':offer.get('book_updated_utc'),
                        'bookmaker':offer.get('bookmaker'),
                        'research_grade':'PENDING EVIDENCE','calibrated_p':None,
                        'sample_n':(item.get('screen') or {}).get('n'),
                        'observed_hit_rate':(item.get('screen') or {}).get('hit_rate_observed')})
    blob={'schema_version':'v08_research_snapshot','event_key':event['event_key'],
          'event_start_utc':scheduled.isoformat(),'recorded_at_utc':observed.isoformat(),
          'event_status':'UPCOMING','not_a_forecast':True,'markets':markets}
    encoded=json.dumps(blob,sort_keys=True,separators=(',',':')).encode()
    blob['sha256']=sha256(encoded).hexdigest()
    return blob


def serialize_snapshot(snapshot:dict) -> bytes:
    if snapshot.get('schema_version')!='v08_research_snapshot':
        raise ValueError('Unexpected snapshot schema')
    return (json.dumps(snapshot,sort_keys=True,indent=2)+'\n').encode('utf-8')
