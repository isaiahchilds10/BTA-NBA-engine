"""Conservative BTA candidate adjudication: evidence gates before qualitative tiers.

This module cannot certify proprietary professional judgment or a real-world
betting advantage. It explicitly refuses to turn historical counts into TAIG.
"""
from __future__ import annotations
from bta_v08.markets import book_quote_status
from bta_v07.scenarios import validate_scenarios
from .evidence import valid_pregame

REQUIRED = (
    'exact_offered_market_and_settlement','event_and_participant_identity',
    'fresh_injury_and_inactive_status','expected_role_minutes_or_snap_share',
    'teammate_and_coaching_changes','opponent_adjusted_matchup',
    'five_evidence_linked_scripts','ordinary_failure_audit',
    'calibrated_out_of_sample_forecast','independent_second_pass',
)


def audit_candidate(event:dict,offer:dict,forecast:dict,*, now, verified_facets:dict|None=None,
                    scripts:list[dict]|None=None, calibration:dict|None=None) -> dict:
    verified_facets=verified_facets or {}
    missing=[facet for facet in REQUIRED if verified_facets.get(facet) is not True]
    ok,reason=valid_pregame(event,event.get('retrieved_at_utc'),now=now)
    if not ok: missing.append(reason)
    quote=book_quote_status(offer,now=now,max_age_minutes=15)
    if quote!='RECENT QUOTE':missing.append(f'Offer age/status: {quote}')
    if forecast.get('status')!='EXPERIMENTAL_UNCALIBRATED':
        missing.append('Supported recent historical model observations')
    if calibration is None or calibration.get('status')!='FORECAST_CHECKS_PASS':
        missing.append('Validated calibration from prior real-world forecast/settlement archive')
    family={'NBA':'NBA_PROP','NFL':'NFL_PROP'}.get(event.get('league')) if offer.get('player') else 'CFB_MONEYLINE'
    if family=='CFB_MONEYLINE' and event.get('league')!='College football':
        family=None
    if scripts is None:
        missing.append('Five separate mechanism-backed scripts')
        script_review=None
    elif family:
        try:
            script_review=validate_scenarios(family,scripts)
            if script_review.get('status')=='CUT':
                return {'grade':'CUT', 'strict_ticket_eligible':False,'reason':script_review.get('reason'),
                        'worse_count':script_review.get('worse_count'), 'missing':missing}
            if script_review.get('status')!='REVIEW':missing.append('Script validity or evidence not established')
        except (ValueError,TypeError,KeyError) as exc:
            script_review=None
            missing.append('Script assessment malformed')
    else:
        script_review=None
        missing.append('Unsupported sport/market family for script verification')
    if missing:
        return {'grade':'PENDING EVIDENCE','strict_ticket_eligible':False,
                'missing':sorted(set(missing)),'quoted_market':quote,
                'preliminary_probability':forecast.get('experimental_probability'),
                'probability_status':'UNCALIBRATED / NOT BTA-QUALIFIED',
                'script_review':script_review}
    # Critical safety: verified facets are asserted upstream, but cannot be authenticated
    # by local code; the additional adversarial substantive review is intentionally required.
    return {'grade':'AUDIT READY — NOT CERTIFIED','strict_ticket_eligible':False,
            'missing':['Final independent source authentication and actual game-specific adversarial assessment'],
            'probability_status':'Holdout checks passed for historical model family; live selection unverified',
            'script_review':script_review}
