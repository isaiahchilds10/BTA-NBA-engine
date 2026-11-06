"""CFBD-derived, *uncalibrated* FBS moneyline research context.

Uses only completed historical matches strictly before each game.
Explicitly refuses ambiguous school-name alignment with ESPN events.
"""
from __future__ import annotations
from datetime import datetime
from bta_v05.models import cfb_elo_progress,cfb_unvalidated_upcoming
from bta_v08.markets import _name
from bta_v08.schedule import parse_instant


def _school(label:str, schools:set[str]) -> str|None:
    value=str(label or '').casefold().strip()
    # ESPN team displayName commonly has the school's mascot appended.
    # Only accept a unique longest exact word-boundary prefix.
    matched=[s for s in schools if value==s.casefold() or value.startswith(s.casefold()+' ')]
    if not matched:return None
    maximal=max(len(s) for s in matched)
    best=[s for s in matched if len(s)==maximal]
    return best[0] if len(best)==1 else None


def research(event:dict,historical_games:list[dict]) -> dict:
    cutoff=parse_instant(event.get('start_utc'))
    if event.get('league')!='College football' or cutoff is None:
        return {'status':'UNVERIFIED','reason':'Not a dated college-football event'}
    valid=[g for g in historical_games if isinstance(g,dict) and g.get('completed') is True]
    schools=set()
    for g in valid:
        if g.get('homeTeam'):schools.add(g['homeTeam'])
        if g.get('awayTeam'):schools.add(g['awayTeam'])
    home=_school(event.get('home',{}).get('name'),schools)
    away=_school(event.get('away',{}).get('name'),schools)
    if not home or not away or home==away:
        return {'status':'UNVERIFIED','reason':'Cannot uniquely align ESPN school names with CFBD FBS history'}
    ratings,prior_predictions=cfb_elo_progress(valid,cutoff=cutoff)
    comparison=cfb_unvalidated_upcoming(home,away,ratings)
    if comparison.get('gate')!='EXPERIMENTAL ONLY':
        return {'status':'UNVERIFIED','reason':comparison.get('reason','Elo missing')}
    return {'status':'EXPERIMENTAL ONLY','home_school':home,'away_school':away,
            'baseline':comparison,'prior_games_processed':len(prior_predictions),
            'model_id':'fixed-elo-v09-NOT-VALIDATED',
            'warning':'CFBD completed-game Elo is not adjusted for current QB, injury, coaching, lines, '
                      'turnovers, FCS eligibility or actual offered market. Do not label BTA+.'}
