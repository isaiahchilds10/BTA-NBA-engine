"""Read-only automatic screening of *offered* markets against PRIOR historical records.

Research priority is NOT forecast win probability or a BTA grade. No player prop
is recommended or qualified; missing role, injury, opponent or script evidence
must remain visibly unresolved.
"""
from __future__ import annotations
from datetime import date, datetime, timezone
from math import isfinite
from statistics import median
from .markets import NBA_STATS, NFL_STATS, _name, _number
from .schedule import parse_instant


def _prior_game_day(event: dict) -> date | None:
    start = parse_instant(event.get('start_utc'))
    return start.date() if start else None


def _raw_hist(league: str, league_rows: list[dict], offer: dict, event: dict) -> list[dict]:
    if offer.get('market') not in {'NBA':NBA_STATS,'NFL':NFL_STATS}.get(league, {}):
        return []
    prop = offer['market']
    stat = NBA_STATS.get(prop) if league=='NBA' else NFL_STATS.get(prop)
    player = _name(offer.get('player',''))
    if not player:
        return []
    cutoff = _prior_game_day(event)
    if cutoff is None:
        return []
    teams = {event['home'].get('abbr',''),event['away'].get('abbr','')}
    accepted=[]
    for r in league_rows:
        if league=='NBA':
            name = r.get('Player')
            team = str(r.get('Team') or '').upper()
            when = str(r.get('Date') or '')[:10]
            minutes = _number(r.get('Minutes'))
            if minutes is not None and minutes <= 0:continue
            value = _number(r.get(stat))
            identifier = str(r.get('game_id') or '') or when+':'+str(r.get('Opp') or '')
        else:
            name = r.get('player_display_name') or r.get('player_name')
            team = str(r.get('recent_team') or '').upper()
            week = r.get('week')
            season = r.get('season')
            if str(r.get('season_type') or 'REG').upper() not in ('REG','REGULAR'):
                continue
            # nflverse weekly rows are tagged by season/week, not UTC kickoff.
            # Never include current/future week in a pregame screen. If week
            # isn't supplied by the schedule, only prior seasons are eligible.
            try:
                current_year=int(str(season))
                schedule_season=int(event.get('season_year') or (cutoff.year-1 if cutoff.month <= 3 else cutoff.year))
                current_week=int(week)
                event_week=int(event['week']) if event.get('week') is not None else None
            except (TypeError,ValueError):continue
            if current_year > schedule_season or (current_year == schedule_season and
                                                  (event_week is None or current_week >= event_week)):
                continue
            if current_year < schedule_season:
                # Ordering across older seasons; exact game date unknown.
                when=f'{current_year}-01-01'
            else:
                # Ordering by season-week, but don't pretend this is exact kickoff date.
                when=f'{current_year}-01-01'
            value=_number(r.get(stat))
            identifier=f'{season}-{current_week:02d}'
        if _name(str(name or '')) != player or team not in teams:
            continue
        try: game_day=date.fromisoformat(when)
        except ValueError:continue
        if game_day>=cutoff or value is None:continue
        accepted.append({'date':game_day.isoformat(),'value':value,'game_id':identifier,'team':team})
    dedup={r['game_id']:(r) for r in accepted if r['game_id']}
    return sorted(dedup.values(),key=lambda r:(r['date'],r['game_id']))


def _bin(value: float,line:float,side:str) -> str:
    if value==line:return 'PUSH'
    return 'WIN' if (value>line if side=='OVER' else value<line) else 'LOSS'


def _is_future_pregame(event: dict, now: datetime | None = None) -> bool:
    t=parse_instant(event.get('start_utc'))
    now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return event.get('status')=='UPCOMING' and t is not None and now<t


def descriptive_screen(league: str, league_rows: list[dict], offer: dict, event: dict, *, now: datetime | None = None) -> dict:
    """Strictly descriptive research, never calibrated probability or betting grade."""
    if not _is_future_pregame(event,now):
        return {'status':'BLOCKED','reason':'Only future, pregame events can enter pregame research.'}
    if not offer.get('player') or offer.get('market') not in {'NBA':NBA_STATS,'NFL':NFL_STATS}.get(league,{}):
        return {'status':'NO MODEL','reason':'No supported exact-player market model.'}
    line=_number(offer.get('line'))
    side=str(offer.get('selection') or '').upper()
    if line is None or side not in {'OVER','UNDER'}:
        return {'status':'NO MODEL','reason':'Exact market threshold or side is missing.'}
    hist=_raw_hist(league,league_rows,offer,event)
    sample=hist[-10:]
    if len(sample)<3:
        return {'status':'INSUFFICIENT','reason':'Fewer than 3 usable past appearances with safe date/team matching.',
                'n':len(sample),'source_warning':'NFL this version deliberately avoids same-season stats without a verified week mapping.'}
    values=[r['value'] for r in sample]
    outcomes=[_bin(v,line,side) for v in values]
    decided=[s for s in outcomes if s!='PUSH']
    hits=sum(s=='WIN' for s in outcomes)
    clearance=median((v-line if side=='OVER' else line-v) for v in values)
    recent=sample[-3:]
    first3=hist[:3]
    return {'status':'HISTORICAL CONTEXT ONLY','n':len(sample),
            'sample_period': f'{sample[0]["date"]} through {sample[-1]["date"]}',
            'hits':hits, 'decided':len(decided),
            'hit_rate_observed':round(hits/len(decided),3) if decided else None,
            'median_observed':round(median(values),2), 'median_clearance':round(clearance,2),
            'recent_3_hits':sum(_bin(g['value'],line,side)=='WIN' for g in recent),
            'first_3_all_hit':len(first3)==3 and all(_bin(g['value'],line,side)=='WIN' for g in first3),
            'last10_values':values,'n_available_total':len(hist),
            'source_warning':('Past appearances do not establish a future probability. '
                              'Current starter status, injuries, comparability, opponent quality, five scripts and odds settlement require verification.')}


def research_priority(offer: dict, screen: dict) -> tuple[int,str]:
    """Ordering heuristic only: empirical past exact-line performance with sample discount.

    Returns 0..100 'research queue priority', NEVER a selection rating/EV.
    Higher priorities have more historically favorable evidence and deserve audit first.
    """
    if screen.get('status') != 'HISTORICAL CONTEXT ONLY':
        return 0, 'Not enough verified historical data for a research screen'
    n=int(screen['n'])
    rate=screen.get('hit_rate_observed')
    cushion=screen.get('median_clearance')
    if rate is None or cushion is None:
        return 0,'Sample has no decided observations'
    line=_number(offer.get('line')) or 1.0
    # Shrink toward neutral as sample shrinks. Completely heuristic, not a p estimate.
    shrink=n/(n+10)
    adjusted=0.5+(rate-0.5)*shrink
    cushion_ratio=max(-1.,min(1.,cushion/max(1.,abs(line))))
    score=round(100*max(0.,min(1.,0.8*adjusted+0.2*(0.5+0.5*cushion_ratio))))
    return score, 'Research ordering index only; not a predicted chance of winning'


def pregame_gate(event:dict,offer:dict,screen:dict,*,now:datetime | None=None) -> dict:
    missing=['verified game-day participation/role','opponent-adjusted matchup',
             'empirically supported five-script effects','independent second-pass audit',
             'out-of-sample calibrated model probability']
    if screen.get('status')!='HISTORICAL CONTEXT ONLY':
        missing.append('adequate historical sample')
    if not _is_future_pregame(event,now):
        return {'grade':'NOT ACTIONABLE','strict_ticket_eligible':False,
                'reasons':['Market is live/final, or scheduled start has passed']}
    return {'grade':'PENDING EVIDENCE','strict_ticket_eligible':False,
            'reasons':missing,
            'comment':'No automatic TAIG/BTA+/BTA status. Historical hits are not calibrated true probability.'}


def queue_for_event(event:dict,offers:list[dict],history_rows:list[dict],*,max_items:int=3,now:datetime | None=None) -> list[dict]:
    scored=[]
    for o in offers:
        if o.get('player') and o.get('market') not in {'NBA':NBA_STATS,'NFL':NFL_STATS}.get(event['league'],{}):
            continue
        screen=descriptive_screen(event['league'],history_rows,o,event,now=now)
        score,note=research_priority(o,screen)
        scored.append({'offer':o, 'screen':screen, 'priority':score, 'priority_note':note,
                       'gate':pregame_gate(event,o,screen,now=now)})
    scored.sort(key=lambda x:(x['screen'].get('status')=='HISTORICAL CONTEXT ONLY',x['priority'],
                              x['offer'].get('market','')),reverse=True)
    # Separate multiple bookmakers/lines on same player-market; avoid deceptive duplicates.
    seen=set();out=[]
    for row in scored:
        o=row['offer']
        key=(o.get('player'),o.get('market'),o.get('selection'))
        if key in seen:continue
        seen.add(key)
        out.append(row)
        if len(out)>=max_items:break
    return out
