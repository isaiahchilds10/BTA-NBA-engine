"""Game-score outcome OBSERVATIONS, not independently verified wager settlements.

A sportsbook may void/cancel independently of a game's final score. These
observations are deliberately not permitted as calibration settlements.
"""
from __future__ import annotations
from bta_v08.markets import _name,_number


def observed_game_outcome(event:dict,offer:dict) -> dict:
    if event.get('status')!='FINAL':
        return {'status':'PENDING FINAL SCORE','verified_settlement':False}
    a=_number((event.get('away') or {}).get('score'))
    h=_number((event.get('home') or {}).get('score'))
    if a is None or h is None:
        return {'status':'UNKNOWN FINAL SCORE','verified_settlement':False}
    market=offer.get('market')
    selection=str(offer.get('selection') or '')
    line=_number(offer.get('line'))
    if market=='totals' and line is not None:
        side=selection.upper()
        if side not in ('OVER','UNDER'):return {'status':'BAD MARKET DIRECTION','verified_settlement':False}
        diff=a+h-line
        delta=diff if side=='OVER' else -diff
    elif market in ('h2h','spreads'):
        ishome=_name(selection)==_name(event['home'].get('name',''))
        isaway=_name(selection)==_name(event['away'].get('name',''))
        if ishome==isaway:return {'status':'AMBIGUOUS TEAM SELECTION','verified_settlement':False}
        base=h-a if ishome else a-h
        if market=='spreads':
            if line is None:return {'status':'MISSING SPREAD','verified_settlement':False}
            base+=line
        delta=base
    else:
        return {'status':'UNSUPPORTED GAME MARKET','verified_settlement':False}
    if delta>0:result='WIN'
    elif delta<0:result='LOSS'
    else:result='TIE / PUSH REQUIRES BOOK RULES'
    return {'status':'SCORE-DERIVED OBSERVATION ONLY','raw_result':result,
            'verified_settlement':False,
            'reason':'Official final score and exact sportsbook settlement/void rule not independently matched.'}
