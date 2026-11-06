"""Evidence-backed miss attribution and reverse-case audit.
Unexplained misses must not be waved away as injuries.
"""
from __future__ import annotations

INCIDENT_TYPES={
 'early_injury':'CONTEXTUAL', 'verified_midgame_qb_injury':'CONTEXTUAL',
 'verified_snap_restriction':'CONTEXTUAL','verified_extreme_weather':'CONTEXTUAL',
 'role_reduction_multiple_games':'STRUCTURAL','lost_starting_job':'STRUCTURAL',
 'new_qb_role_shift':'STRUCTURAL','offensive_scheme_change':'STRUCTURAL',
 'normal_volume_variation':'NORMAL','normal_efficiency_variation':'NORMAL',
 'low_possession_volume':'NORMAL'
}


def classify_miss(*, outcome:str, incident:dict|None=None) -> dict:
    if outcome!='LOSS':return {'category':'NOT A MISS','reason':'Market outcome was not a loss'}
    if not incident or not incident.get('source_url') or not incident.get('verified_at'):
        return {'category':'UNEXPLAINED','reason':'No dated evidence supports a specific cause; ordinary miss cannot be discounted.'}
    kind=incident.get('incident_type')
    if kind not in INCIDENT_TYPES:
        return {'category':'UNEXPLAINED','reason':'Unknown/unverified mechanism'}
    if kind=='role_reduction_multiple_games' and incident.get('observed_games',0)<3:
        return {'category':'UNEXPLAINED','reason':'Cannot declare a persistent role change from fewer than 3 observations'}
    return {'category':INCIDENT_TYPES[kind], 'incident_type':kind,
            'source_url':incident['source_url'],'verified_at':incident['verified_at'],
            'reason':'Attributed to a supported event; check whether the event is relevant to the upcoming matchup.'}


def reverse_failure_audit(*, losses:list[dict], scenario_findings:list[dict]|None=None,
                          available_role_evidence:bool=False) -> dict:
    """Do not invent failure probabilities. Prioritize observed normal losses."""
    findings=[]
    for r in losses:
        category=r.get('miss_category') or 'UNEXPLAINED'
        findings.append({'game_id':r.get('game_id'),'date':r.get('date'),
                         'actual':r.get('value'),'margin':r.get('clearance_margin'),
                         'mechanism':category,'explanation':r.get('attribution_reason') or 'Cause not verified'})
    for s in scenario_findings or []:
        if s.get('verdict') in {'WORSE','UNKNOWN'}:
            findings.append({'scenario':s.get('scenario'),'mechanism':s.get('verdict'),
                             'explanation':s.get('mechanism') or 'Causal mechanism not verified'})
    return {'status':'REVIEW REQUIRED','ordinary_failures':sum(x['mechanism']=='NORMAL' for x in findings),
            'unresolved_failures':sum(x['mechanism'] in {'UNEXPLAINED','UNKNOWN'} for x in findings),
            'findings':findings,
            'base_case_verified':bool(available_role_evidence),
            'caution':'Most plausible opposing case must be supported by actual observations; no hypothetical probability is generated.'}
