"""Event-driven invalidation; no inference that a player is healthy."""
from __future__ import annotations
from .common import utc, digest

MATERIAL_FIELDS={
    'injury_status','inactive_status','starting_lineup','starting_qb','minutes_limit',
    'snap_restriction','coach','offensive_scheme','route_share','target_share',
    'snap_share','expected_minutes','opponent','event_start_utc','player_team',
    'sportsbook_line','sportsbook_price','market_status','teammate_status',
    'offensive_line_status','weather',
}
HARD_VETO={'inactive_status','injury_status','starting_lineup','starting_qb',
           'minutes_limit','snap_restriction','player_team','event_start_utc','market_status'}


def compare(old:dict|None,new:dict, *, observed_at:str)->dict:
    if not utc(observed_at):raise ValueError('Timestamp must be UTC-offset aware')
    if old is None:
        return {'status':'INITIAL','changed_fields':[],'requires_regrade':True,
                'veto_existing_grade':True,'reason':'No previous verified assessment'}
    changed=sorted(k for k in MATERIAL_FIELDS if old.get(k)!=new.get(k))
    hard=sorted(set(changed)&HARD_VETO)
    return {'status':'CHANGED' if changed else 'UNCHANGED','changed_fields':changed,
            'requires_regrade':bool(changed),'veto_existing_grade':bool(changed),
            'hard_veto_fields':hard,'observed_at_utc':observed_at,
            'previous_fingerprint':digest({k:old.get(k) for k in MATERIAL_FIELDS}),
            'current_fingerprint':digest({k:new.get(k) for k in MATERIAL_FIELDS}),
            'reason':'New materially relevant data invalidates earlier grade until reevaluated' if changed else 'No tracked material change'}


def freshness_veto(*, evidence_asof:str|None, now:str, maximum_minutes:int)->dict:
    seen=utc(evidence_asof);clock=utc(now)
    if not clock or maximum_minutes<0:raise ValueError('Invalid clock or policy')
    if not seen or seen>clock:
        return {'veto':True,'reason':'Missing or future evidence timestamp'}
    elapsed=(clock-seen).total_seconds()/60
    return {'veto':elapsed>maximum_minutes, 'age_minutes':round(elapsed,2),
            'reason':('Evidence is stale' if elapsed>maximum_minutes else 'Evidence within freshness policy')}
