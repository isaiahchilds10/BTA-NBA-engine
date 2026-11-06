"""BTA automatic *eligibility and provisional tiering*, with fail-closed gates.

This is a transparent rule prototype, NOT a validated fully autonomous sports
analyst. Any missing critical research => PENDING; scripts cannot self-certify.
A category emitted as 'provisional' MUST NOT be shown as a qualified final leg.
"""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
from math import isfinite
from bta_v07.calibration import parse_utc
from bta_v07.scenarios import validate_scenarios

REQUIRED_BASE={'matchup','market_exact','market_settlement','availability','injuries','opponent',
               'role','coaching','historical_sample','publication_time'}
REQUIRED_FOOTBALL={'quarterback','offensive_line','defensive_front','weather','turnovers'}
REQUIRED_NFL_PROP={'usage','snap_share','personnel','situational_gameflow'}
REQUIRED_NBA_PROP={'minutes','rotation','pace','teammate_status'}
REQUIRED_CFB={'schedule_strength','special_teams','team_rushing','team_passing'}


def _required(family):
    if family=='NFL_PROP':return REQUIRED_BASE|REQUIRED_FOOTBALL|REQUIRED_NFL_PROP
    if family=='NBA_PROP':return REQUIRED_BASE|REQUIRED_NBA_PROP
    if family=='CFB_MONEYLINE':return REQUIRED_BASE|REQUIRED_FOOTBALL|REQUIRED_CFB
    raise ValueError('Unknown family')


def _validated_record(e:dict,event_id:str,kickoff:datetime,facet:str)->bool:
    if not isinstance(e,dict) or e.get('status')!='VERIFIED':return False
    if str(e.get('event_id'))!=event_id:return False
    src=str(e.get('source_url') or '')
    if not src.startswith('https://'):return False
    asof=parse_utc(e.get('observed_at_utc'))
    if asof is None or asof>=kickoff:return False
    # Conservative currency limits. Historical facts can be older if stored
    # in a bona fide timestamped, prospective snapshot.
    if facet in {'availability','injuries','market_exact'}:
        if (kickoff-asof)>timedelta(hours=36 if facet!='market_exact' else 6):return False
    return True


def automatic_candidate_review(packet:dict) -> dict:
    """Returns a PROVISIONAL tier, never auto-inserts into final ticket.

    packet:
      family, event_id, event_start_utc, facets[facet]={status:'VERIFIED',...},
      scenarios[5] with distinct evidence_source/mechanism/verdict,
      history (from historical_audit), injury_gate, calibration_status,
      independent_audit {result, source_url, reviewer_id, original_reviewer_id},
      probability (from independent, chronologically calibrated model).

    The system has no ability to authenticate arbitrarily supplied URLs or
    model evaluations; therefore all tier recommendations remain provisional.
    """
    family=packet.get('family')
    req=_required(family)
    event_id=str(packet.get('event_id') or '')
    kickoff=parse_utc(packet.get('event_start_utc'))
    if not event_id or not kickoff:
        return {'grade':'PENDING','why':['Missing unambiguous event ID/start time'],'tier':'NONE','final_ticket_eligible':False}
    facets=packet.get('facets') or {}
    missing=sorted(k for k in req if not _validated_record(facets.get(k),event_id,kickoff,k))
    script=validate_scenarios(family,packet.get('scenarios') or [])
    if script['status']=='CUT':
        return {'grade':'CUT','tier':'RED','why':[script['reason']], 'final_ticket_eligible':False}
    if packet.get('injury_gate')=='BLOCKED':
        return {'grade':'CUT','tier':'RED','why':['Verified availability concern blocks selection'],
                'final_ticket_eligible':False}
    reasons=[]
    if missing: reasons.append('Missing/dated/undocumented facets: '+', '.join(missing))
    if script['status']!='REVIEW':reasons.append('Incomplete five-script evidence: '+script['reason'])
    if packet.get('injury_gate')!='VERIFIED_ACTIVE':
        reasons.append('No verified game-day participation and anticipated normal role')
    if packet.get('calibration_status')!='FORECAST_CHECKS_PASS':
        reasons.append('Calibrated forecast not supported by untouched chronological holdout')
    history=packet.get('history') or {}
    if history.get('status')!='RESEARCH ONLY' or (history.get('n_games') or 0)<10:
        reasons.append('Fewer than 10 verified comparable history observations')
    if not packet.get('exact_market_offer_verified'):
        reasons.append('No timestamped offer for this exact sportsbook market/line')
    audit=packet.get('independent_audit') or {}
    if audit.get('result')!='PASSED' or not str(audit.get('source_url','')).startswith('https://') or not audit.get('reviewer_id') or audit.get('reviewer_id')==audit.get('original_reviewer_id'):
        reasons.append('Independent second-pass audit not completed')
    p=packet.get('calibrated_probability')
    if not isinstance(p,(float,int)) or not isfinite(p) or p<=0 or p>=1:
        reasons.append('No usable calibrated event probability')
    if reasons:
        return {'grade':'PENDING','tier':'NONE','why':reasons,'missing_facets':missing,
                'scripts':script,'final_ticket_eligible':False}
    # Heuristic ranking thresholds, not statistically validated BTA thresholds.
    hit=history.get('historical_hit_rate') or 0
    last10=history.get('last_ten_win_rate') or 0
    cushion=history.get('median_clearance_margin') or 0
    normal_failures=packet.get('confirmed_ordinary_failure_count')
    if not isinstance(normal_failures,int) or normal_failures<0:
        return {'grade':'PENDING','tier':'NONE','why':['Ordinary failures have not been independently classified'],
                'final_ticket_eligible':False}
    worse=script.get('worse_count') or 0
    if family=='CFB_MONEYLINE':
        # No validated cross-sport numeric rating schema yet.
        return {'grade':'CONDITIONAL','tier':'UNRANKED CFB',
                'why':['CFB game-script survival is not a quantified team-win model; qualitative review required'],
                'final_ticket_eligible':False}
    if (history['n_games']>=20 and hit>=.92 and last10>=.90 and cushion>0
            and normal_failures==0 and worse==0 and p>=.80):
        tier='TAIG CANDIDATE'
    elif hit>=.85 and last10>=.8 and cushion>0 and normal_failures<=1 and worse==0 and p>=.75:
        tier='BTA+ CANDIDATE'
    elif hit>=.75 and last10>=.7 and cushion>0 and normal_failures<=2 and worse<=1 and p>=.65:
        tier='BTA CANDIDATE'
    else:
        tier='CONDITIONAL'
    return {'grade':'PROVISIONAL','tier':tier,
            'why':['Rule-based research tier; heuristic cutoffs have not been empirically validated as BTA grades.',
                   'A second independently sourced audit and settlement review are still required before final ticket inclusion.'],
            'final_ticket_eligible':False,'scripts':script,
            'caution':'No automated selection is authorized as TAIG/BTA+/BTA solely from this module.'}
