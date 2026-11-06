"""Exact-contract settlement reconciliation and diagnosis with evidence gates."""
from __future__ import annotations
from .common import utc,market_identity,finite_number


def reconcile_settlement(event:dict,offer:dict,record:dict)->dict:
    identity=market_identity(event,offer)
    if not identity:return {'status':'UNKNOWN','verified':False,'reason':'Incomplete event/market identity'}
    if record.get('market_identity')!=identity or record.get('event_key')!=event.get('event_key'):
        return {'status':'IDENTITY_MISMATCH','verified':False}
    if record.get('platform')!=offer.get('bookmaker'):
        return {'status':'PLATFORM_MISMATCH','verified':False}
    recorded=utc(record.get('settled_at_utc'));start=utc(event.get('start_utc'))
    if not recorded or not start or recorded<=start:
        return {'status':'INVALID_TIMING','verified':False}
    final=record.get('outcome')
    if final not in ('WIN','LOSS','PUSH','VOID'):
        return {'status':'UNRESOLVED','verified':False}
    if not record.get('source_url','').startswith('https://') or record.get('source_confirmed') is not True:
        return {'status':'OBSERVED_NOT_VERIFIED','verified':False,'reported_outcome':final}
    return {'status':'VERIFIED_EXTERNAL_RESOLUTION_RECORD','verified':True,'outcome':final,
            'source_url':record['source_url'],
            'caution':'Platform-specific rules require independently authenticated records. A Boolean in a fixture is not authentication.'}


def diagnose_miss(*, outcome:str, evidence:list[dict])->dict:
    if outcome!='LOSS':return {'status':'NOT_A_LOSS','category':None}
    verified=[e for e in evidence if e.get('verified') is True and str(e.get('source_url','')).startswith('https://')]
    if not verified:return {'status':'CAUSE_UNKNOWN','category':None,'reason':'No externally corroborated explanation'}
    categories={'ordinary_variance','contextual','structural','model_error','shared_script','unusual_event'}
    marked={e.get('category') for e in verified if e.get('category') in categories}
    if len(marked)!=1:return {'status':'CAUSE_AMBIGUOUS','category':None,'candidate_categories':sorted(marked)}
    return {'status':'DOCUMENTED_CAUSE','category':next(iter(marked)),
            'sources':[e['source_url'] for e in verified],
            'note':'A documented correlation is not automatically proof of exclusive causal responsibility.'}
