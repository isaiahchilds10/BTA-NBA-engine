"""Experimental exact-threshold historical forecasts. NOT calibrated BTA chances.

All observations are restricted to games/weeks preceding the offered event.
The simple Beta shrinkage baseline is for testing a complete prospective pipeline;
it is not justified as an independently established probability model.
"""
from __future__ import annotations
from datetime import datetime
from math import isfinite
from statistics import median
from zoneinfo import ZoneInfo
from bta_v08.markets import NBA_STATS, NFL_STATS, _name, _number
from bta_v08.schedule import parse_instant


def _has_played_minutes(raw):
    """Accept numeric minutes and conventional MM:SS NBA time strings."""
    num=_number(raw)
    if num is not None:return num>0
    if isinstance(raw,str) and ':' in raw:
        parts=raw.split(':')
        if len(parts)==2 and all(x.isdigit() for x in parts):
            mm,ss=map(int,parts)
            return mm>0 or (mm==0 and 0<ss<60)
    return False


def historical_values(event: dict, offer: dict, rows: list[dict]) -> dict:
    sport=event.get('league')
    label=offer.get('market')
    stat={'NBA': NBA_STATS, 'NFL': NFL_STATS}.get(sport,{}).get(label)
    if not stat or not offer.get('player') or offer.get('line') is None:
        return {'status':'UNSUPPORTED', 'reason':'Market not supported by exact-stat history engine'}
    start=parse_instant(event.get('start_utc'))
    if not start:
        return {'status':'UNVERIFIED','reason':'Missing event start'}
    cutoff=start.astimezone(ZoneInfo('America/New_York')).date()
    teams={event.get('home',{}).get('abbr',''),event.get('away',{}).get('abbr','')}
    matches=[]
    for r in rows:
        if sport=='NBA':
            if _name(r.get('Player')) != _name(offer['player']): continue
            team=str(r.get('Team') or '').upper()
            if team not in teams:continue
            rawdate=str(r.get('Date') or '')[:10]
            if not rawdate:continue
            try: game_date=datetime.strptime(rawdate,'%Y-%m-%d').date()
            except ValueError:continue
            if game_date>=cutoff:continue
            if not _has_played_minutes(r.get('Minutes')):continue
            ident=str(r.get('game_id') or r.get('GAME_ID') or '')
            if not ident:ident=f'{game_date}:{team}:{r.get("Opp", "")}'
            order=(game_date.toordinal(),0)
        else:
            if _name(r.get('player_display_name') or r.get('player_name')) != _name(offer['player']):continue
            team=str(r.get('recent_team') or '').upper()
            if team not in teams:continue
            try: yr=int(r.get('season'));week=int(r.get('week'))
            except (ValueError,TypeError):continue
            if str(r.get('season_type') or 'REG').upper() not in {'REG','REGULAR'}:continue
            event_year=int(event.get('season_year') or (cutoff.year if cutoff.month>=4 else cutoff.year-1))
            event_week=event.get('week')
            if event_week is None:continue  # Never use same season without verified week cutoff
            try: event_week=int(event_week)
            except (ValueError,TypeError):continue
            if yr>event_year or (yr==event_year and week>=event_week):continue
            if yr<event_year-1:continue
            ident=f'{yr}:{week}:{team}:{_name(offer["player"])}'
            rawdate=f'NFL {yr} W{week}'
            order=(yr,week)
        val=_number(r.get(stat))
        if val is None or val < 0:continue
        matches.append({'id':ident,'order':order,'game_date':rawdate,'value':val,
                        'team':team, 'opponent':r.get('Opp') if sport=='NBA' else r.get('opponent_team')})
    unique={m['id']:m for m in matches}
    ordered=sorted(unique.values(), key=lambda x:(x['order'],x['id']))
    return {'status':'OK' if len(ordered)>=3 else 'INSUFFICIENT',
            'n':len(ordered),'games':ordered[-40:],
            'reason':'Descriptive historical records. NFL dates are week labels, not verified kickoff dates.'}


def exact_line_baseline(event: dict, offer: dict, rows: list[dict]) -> dict:
    past=historical_values(event,offer,rows)
    if past['status']!='OK':return {'status':past['status'],'reason':past.get('reason'),'n':past.get('n',0)}
    side=str(offer.get('selection','')).upper()
    if side not in {'OVER','UNDER'}:
        return {'status':'UNSUPPORTED','reason':'Only exact OVER/UNDER player props with supported stat columns'}
    line=_number(offer.get('line'))
    if line is None:return {'status':'UNSUPPORTED','reason':'Missing threshold'}
    games=past['games']
    values=[g['value'] for g in games]
    # Whole history latest 40, use last 20. Never skip normal misses.
    recent=values[-20:]
    wins=sum(v>line if side=='OVER' else v<line for v in recent)
    losses=sum(v<line if side=='OVER' else v>line for v in recent)
    pushes=len(recent)-wins-losses
    decided=wins+losses
    three=values[-3:]
    # Index 0 is older and 2 is newest; clearly label the period.
    margins=[(v-line if side=='OVER' else line-v) for v in recent]
    # Research-only prior = Beta(2,2), NOT an out-of-sample-calibrated posterior.
    p=(wins+2)/(decided+4) if decided else None
    return {'status':'EXPERIMENTAL_UNCALIBRATED' if decided>=6 else 'INSUFFICIENT',
            'market':offer.get('market'), 'line':line, 'side':side,
            'n':len(recent),'wins':wins,'losses':losses,'pushes':pushes,
            'sample_win_fraction':round(wins/decided,4) if decided else None,
            'recent_three':three,'recent_three_wins':sum(v>line if side=='OVER' else v<line for v in three),
            'median_value':median(recent), 'median_clearance':median(margins),
            'min_observed':min(recent),'max_observed':max(recent),
            'experimental_probability':round(p,6) if p is not None and isfinite(p) else None,
            'sample_games':games[-20:],
            'model_version':'historical-beta(2,2)-v09-NOT-CALIBRATED',
            'caution':'Shrinkage demonstration only. No opponent/role/injury adjustment; not a bet recommendation.'}
