"""Evidence provenance, conflict detection and strict age gates.

Provider retrieval time is not publication or data-effective time. Two mirrors
repeating one feed do not constitute independent corroboration.
"""
from __future__ import annotations
from datetime import datetime, timezone
from urllib.parse import urlparse
from .common import utc, finite_number


def reconcile(facts:list[dict], *, now:datetime|None=None, max_age_minutes:int=60,
              numeric_tolerance:float=0.0)->dict:
    clock=utc(now or datetime.now(timezone.utc))
    if not clock or max_age_minutes<0 or numeric_tolerance<0:
        raise ValueError('Invalid timezone or tolerance')
    if not facts:return {'status':'MISSING','verified':False,'reason':'No sourced facts'}
    keys={(f.get('event_key'),f.get('entity_id'),f.get('field')) for f in facts}
    if len(keys)!=1 or any(not all(k) for k in keys):
        return {'status':'IDENTITY_CONFLICT','verified':False,'reason':'Facts do not describe exactly one event/entity/field'}
    valid=[];invalid=[]
    for f in facts:
        stamp=utc(f.get('source_asof_utc'));seen=utc(f.get('retrieved_at_utc'))
        url=f.get('source_url') or ''
        root=(f.get('origin_id') or urlparse(url).netloc.lower().removeprefix('www.')).strip()
        if not stamp or not seen or stamp>seen or seen>clock or (clock-stamp).total_seconds() < -300 or not root or not url.startswith('https://'):
            invalid.append('Untrusted or missing original source time / URL / origin')
            continue
        age=(clock-stamp).total_seconds()/60
        if age>max_age_minutes:
            invalid.append(f'Stale source data: {age:.0f} min old')
            continue
        value=f.get('value')
        if value is None or isinstance(value,(dict,list)):
            invalid.append('Absent or non-scalar fact value')
            continue
        valid.append({**f,'origin':root,'age_minutes':round(age,2)})
    if not valid:
        return {'status':'STALE_OR_INVALID','verified':False,'reason':'No usable current sourced observations',
                'rejected':invalid}
    # Multiple rows from the same upstream origin: only the most recent is material.
    by_origin={}
    for f in sorted(valid,key=lambda x:x['source_asof_utc']):
        by_origin[f['origin']]=f
    observations=list(by_origin.values())
    values=[x['value'] for x in observations]
    nums=[finite_number(x) for x in values]
    if all(x is not None for x in nums):
        agree=max(nums)-min(nums)<=numeric_tolerance
    else:
        agree=len({str(x).casefold().strip() for x in values})==1
    if not agree:
        return {'status':'CONFLICT','verified':False,'reason':'Current independent sources disagree',
                'sources':[{k:r[k] for k in ('source_url','source_asof_utc','origin','value','age_minutes')} for r in observations],
                'rejected':invalid}
    official=any(r.get('source_class')=='official' for r in observations)
    status='CORROBORATED' if len(observations)>=2 else 'CURRENT_SINGLE_SOURCE'
    return {'status':status,'verified':len(observations)>=2,'value':values[0],
            'has_official_source':official,'independent_origin_count':len(observations),
            'reason':('Corroborated original published fact' if len(observations)>=2 else 'One current original source; independent corroboration absent'),
            'sources':[{k:r[k] for k in ('source_url','source_asof_utc','origin','value','age_minutes')} for r in observations],
            'rejected':invalid,
            'important':'Even corroborated injury designation is not confirmed full-game participation.'}


def evidence_gate(facts:dict[str,list[dict]], required:list[str], *, now:datetime,
                  ages:dict[str,int]|None=None)->dict:
    audits={name:reconcile(facts.get(name,[]),now=now,max_age_minutes=(ages or {}).get(name,240)) for name in required}
    missing=[name for name,result in audits.items() if result['status'] not in ('CORROBORATED','CURRENT_SINGLE_SOURCE')]
    conflicts=[name for name,result in audits.items() if result['status']=='CONFLICT']
    return {'status':'BLOCKED' if missing else 'SOURCE_OBSERVED_ONLY', 'missing':missing,
            'conflicts':conflicts,'audit':audits,'note':'Original sources observed; status does not certify player availability or model validity.'}
