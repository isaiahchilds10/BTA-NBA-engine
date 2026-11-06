"""Automatically convert existing v0.9 NBA/NFL history into traceable role summaries.

Uses only prior dated games/older NFL weeks. Explicitly avoids treating week
labels as precise NFL kickoff timestamps or NBA date-only logs as live stats.
No lineups, snap route data, FBS roster continuity, BTA probabilities inferred.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from statistics import median
from zoneinfo import ZoneInfo
from .common import utc,finite_number


def nba_team_observations(event:dict,rows:list[dict],*,min_games:int=3)->dict:
    start=utc(event.get('start_utc'))
    if event.get('league')!='NBA' or not start:return {'status':'INVALID_EVENT','players':[]}
    local_day=start.astimezone(ZoneInfo('America/New_York')).date()
    teams={str(x.get('abbr','')).upper() for x in (event.get('home',{}),event.get('away',{}))}
    grouped=defaultdict(list);dedup=set()
    for row in rows:
        team=str(row.get('Team') or '').upper();name=str(row.get('Player') or '').strip()
        try:day=datetime.strptime(str(row.get('Date') or '')[:10],'%Y-%m-%d').date()
        except ValueError:continue
        if not name or team not in teams or day>=local_day:continue
        key=(str(row.get('ID') or name),str(row.get('game_id') or day.isoformat()),team)
        if key in dedup:continue
        mins=finite_number(row.get('Minutes'))
        if mins is None and ':' in str(row.get('Minutes')):
            try:
                a,b=map(int,str(row['Minutes']).split(':'))
                mins=a+b/60 if 0<=b<60 else None
            except (TypeError,ValueError):pass
        points=finite_number(row.get('Points'));reb=finite_number(row.get('Rebounds'));ast=finite_number(row.get('Assists'))
        if mins is None or mins<=0 or points is None:continue
        dedup.add(key)
        grouped[(team,name)].append((day,mins,points,reb,ast))
    ranked=[]
    for (team,name),games in grouped.items():
        ordered=sorted(games,key=lambda x:x[0])[-10:]
        if len(ordered)<min_games:continue
        ranked.append({'team':team,'player':name,'n':len(ordered),
                       'last_game_date':ordered[-1][0].isoformat(),
                       'median_minutes':round(median(x[1] for x in ordered),2),
                       'median_points':round(median(x[2] for x in ordered),2),
                       'median_rebounds':round(median(x[3] for x in ordered if x[3] is not None),2) if all(x[3] is not None for x in ordered) else None,
                       'median_assists':round(median(x[4] for x in ordered if x[4] is not None),2) if all(x[4] is not None for x in ordered) else None,
                       'model':'DESCRIPTIVE_HISTORY_ONLY'})
    ranked.sort(key=lambda x:(x['median_minutes'],x['n']),reverse=True)
    return {'status':'HISTORICAL_ROLE_RESEARCH','players':ranked,
            'safe_cutoff_local_day':local_day.isoformat(),
            'note':'Source game dates are day-resolution; the event day is excluded to avoid same-day future leakage. Current availability NOT verified.'}


def nfl_team_observations(event:dict,rows:list[dict],*,min_weeks:int=3)->dict:
    if event.get('league')!='NFL' or not event.get('week') or not event.get('season_year'):
        return {'status':'NO_VERIFIED_WEEK_CUTOFF','players':[]}
    try:target=(int(event['season_year']),int(event['week']))
    except (TypeError,ValueError):return {'status':'BAD_WEEK','players':[]}
    if target[1]<1 or target[1]>25:return {'status':'BAD_WEEK','players':[]}
    teams={str(x.get('abbr','')).upper() for x in (event.get('home',{}),event.get('away',{}))}
    grouped=defaultdict(list);dedup=set()
    for row in rows:
        try:period=(int(row.get('season')),int(row.get('week')))
        except (TypeError,ValueError):continue
        team=str(row.get('recent_team') or '').upper()
        name=str(row.get('player_display_name') or row.get('player_name') or '').strip()
        if not name or team not in teams or period>=target or period[0]<target[0]-1:continue
        if str(row.get('season_type') or 'REG').upper() not in ('REG','REGULAR'):continue
        key=(period,team,name)
        if key in dedup:continue
        dedup.add(key)
        grouped[(team,name)].append((period,row))
    out=[]
    for (team,name),games in grouped.items():
        latest=sorted(games,key=lambda x:x[0])[-10:]
        if len(latest)<min_weeks:continue
        field_results={}
        for field in ('targets','carries','passing_yards','receiving_yards','rushing_yards','attempts'):
            values=[finite_number(r.get(field)) for _,r in latest]
            if all(v is not None and v>=0 for v in values):field_results['median_'+field]=round(median(values),2)
        if not field_results:continue
        out.append({'team':team,'player':name,'n':len(latest),'latest_week':f'{latest[-1][0][0]} W{latest[-1][0][1]}',
                    **field_results,'model':'WEEKLY_DESCRIPTIVE_HISTORY_ONLY'})
    out.sort(key=lambda x:(x['n'],x.get('median_targets',0),x.get('median_carries',0)),reverse=True)
    return {'status':'WEEKLY_ROLE_RESEARCH','players':out,
            'safe_cutoff':f'{target[0]} W{target[1]}',
            'note':'Week labels are not game times. Routes/snap share/current active status are NOT inferred; past performance cannot guarantee future usage.'}
