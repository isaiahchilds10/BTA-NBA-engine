"""Rules-based independent veto path, distinct from any positive forecast model."""
from __future__ import annotations

REQUIRED=(
 'exact_market','event_identity','source_freshness','injury_and_active_status',
 'verified_role','opponent_context','historical_failure_paths',
 'mechanism_backed_scripts','model_holdout_validated','second_pass_verified',
)


def challenge(*, evidence:dict, scripts:list[dict]|None=None,
              ordinary_failures:list[dict]|None=None, source_conflicts:list[str]|None=None,
              material_news:bool=False, family:str='NFL_PROP')->dict:
    failures=ordinary_failures or []
    conflicts=source_conflicts or []
    blockers=[k for k in REQUIRED if evidence.get(k) is not True]
    if conflicts:blockers.append('Conflicting source records: '+', '.join(sorted(conflicts)))
    if material_news:blockers.append('Material news requires fresh research')
    scripts=scripts or []
    is_prop=family in ('NFL_PROP','NBA_PROP')
    accepted=('BETTER','SAME','MIXED','WORSE') if is_prop else ('RESILIENT','VULNERABLE','MIXED','UNKNOWN')
    worse=sum(1 for row in scripts if row.get('verdict')=='WORSE') if is_prop else 0
    unknown=sum(1 for row in scripts if row.get('verdict') not in accepted or row.get('verdict')=='UNKNOWN')
    ids=[row.get('scenario') for row in scripts]
    if len(scripts)!=5 or unknown or len(set(ids))!=5 or any(not x for x in ids):
        blockers.append('Five distinct evidence-backed scripts are incomplete')
    if any(not row.get('mechanism') or not row.get('evidence_urls') or
           not isinstance(row.get('evidence_urls'),list) or
           not all(isinstance(url,str) and url.startswith('https://') for url in row.get('evidence_urls',[])) for row in scripts):
        blockers.append('Script results lack causal explanation or evidence')
    if is_prop and worse>=2:return {'status':'CUT','eligible':False,'worse_count':worse,
                        'blockers':sorted(set(blockers+['Two or more material WORSE scripts'])),
                        'strongest_failure':_strongest(failures)}
    if any(x.get('severity')=='CRITICAL' and x.get('verified') is True for x in failures):
        blockers.append('Verified critical ordinary failure mechanism')
    return {'status':'PENDING' if blockers else 'RED_TEAM_REVIEW_ONLY',
            'eligible':False,'worse_count':worse,'blockers':sorted(set(blockers)),
            'strongest_failure':_strongest(failures),
            'note':'Passing a rule checklist does NOT independently certify TAIG/BTA+.'}


def _strongest(items:list[dict]):
    ranked={'CRITICAL':4,'HIGH':3,'MODERATE':2,'LOW':1}
    if not items:return None
    m=max(items,key=lambda x:ranked.get(x.get('severity'),0))
    return {'mechanism':m.get('mechanism'),'severity':m.get('severity'),
            'evidence':m.get('evidence_url'), 'verified':m.get('verified') is True}
