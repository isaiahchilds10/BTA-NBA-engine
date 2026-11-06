"""Integrate the 13 requested layers into the v0.9 fail-closed grading model."""
from __future__ import annotations
from .common import market_identity, before_event
from .redteam import challenge
from .regrade import compare
from .portfolio import shared_risk


def evaluate(*, event:dict,offer:dict, forecast:dict,
             evidences:dict, scripts:list[dict]|None=None, failure_paths:list[dict]|None=None,
             sources_conflict:list[str]|None=None, old_context:dict|None=None,
             new_context:dict|None=None, observed_at:str|None=None,
             calibrated:bool=False,verified_market:bool=False,identity_verified:bool=False)->dict:
    """Gates verified prospective candidates. No automatic final high BTA grades.

    Positive forecasting MUST come from v0.9 and a separately validated model;
    this independent path attempts to disprove rather than approve it.
    """
    identity=market_identity(event,offer)
    checklist=dict(evidences)
    checklist['exact_market']=bool(identity and verified_market)
    checklist['event_identity']=bool(identity and identity_verified)
    checklist['model_holdout_validated']=bool(calibrated)
    if not before_event(event_start=event.get('start_utc',''),
                        created_at=forecast.get('prediction_at_utc',''),
                        data_asof=forecast.get('features_asof_utc','')):
        checklist['model_holdout_validated']=False
    material=False;change=None
    if new_context is not None:
        if not observed_at:raise ValueError('New evidence context requires observed_at')
        change=compare(old_context,new_context,observed_at=observed_at)
        material=change['veto_existing_grade']
    family=('NFL_PROP' if event.get('league')=='NFL' else 'NBA_PROP') if offer.get('player') else ('CFB_MONEYLINE' if event.get('league')=='College football' else 'GAME_MARKET')
    independent=challenge(evidence=checklist,scripts=scripts,ordinary_failures=failure_paths,
                          source_conflicts=sources_conflict,material_news=material,family=family)
    return {'market_identity':identity,'status':independent['status'],
            'strict_eligible':False,'grade': 'CUT' if independent['status']=='CUT' else 'PENDING VERIFICATION',
            'red_team':independent,'regrade':change,
            'calibration_flag':calibrated,'model_status':forecast.get('status','UNKNOWN'),
            'next_action':'Resolve evidence blockers; confirm live source authentication, outside holdout results, and game-specific second pass',
            'note':'Rule-complete audit is not itself validation or BTA+ certification. No auto-picks or wagers are placed.'}


def evaluate_slip(legs:list[dict])->dict:
    risk=shared_risk(legs)
    blocked=[i for i,r in enumerate(legs) if r.get('strict_eligible') is not True]
    return {'status':'NOT_APPROVED' if blocked or risk['pairs'] else 'INDEPENDENT_REVIEW_REQUIRED',
            'unverified_leg_indexes':blocked, 'risk':risk,
            'note':'No joint parlay probability without validated marginals and historical dependence.'}
