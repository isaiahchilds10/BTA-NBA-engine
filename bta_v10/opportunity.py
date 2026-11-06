"""Sport-aware opportunity estimates; descriptive and explicit assumptions.

Separate projected opportunity from efficiency; no certified win probabilities.
Only past data is accepted by functions using an event cutoff.
"""
from __future__ import annotations
from statistics import median
from .common import finite_number, utc


def _before(rows:list[dict], start_utc:str, min_n:int=3)->list[dict]:
    start=utc(start_utc)
    if not start:return []
    out=[]
    for row in rows:
        played=utc(row.get('played_at_utc'))
        if played and played<start:out.append(row)
    return sorted(out,key=lambda r:r['played_at_utc'])


def nba_rotation(rows:list[dict], *, event_start_utc:str, expected_pace:float|None=None,
                 opponent_pace:float|None=None)->dict:
    """Requires dated actual minutes + opportunities and active role verification elsewhere."""
    past=_before(rows,event_start_utc)
    usable=[]
    for row in past:
        mins=finite_number(row.get('minutes'))
        pts=finite_number(row.get('points'))
        usage=finite_number(row.get('usage_rate'))
        if mins is not None and mins>0 and pts is not None and pts>=0:
            usable.append({'minutes':mins,'points':pts,'usage':usage,'start':row.get('started')})
    if len(usable)<5:return {'status':'INSUFFICIENT','n':len(usable),'reason':'At least five dated played games required'}
    last=usable[-10:];mins=[r['minutes'] for r in last]
    rates=[r['points']/r['minutes'] for r in last]
    pace_adjust=1.0
    if expected_pace is not None and opponent_pace is not None:
        a=finite_number(expected_pace);b=finite_number(opponent_pace)
        if not a or not b or a<=0 or b<=0:raise ValueError('Pace inputs must be positive')
        pace_adjust=max(.85,min(1.15,b/a))
    projected_minutes=median(mins)
    projected_points=projected_minutes*median(rates)*pace_adjust
    prev=usable[-10:-3]
    drift=(median(mins[-3:])-median([x['minutes'] for x in prev])) if len(prev)>=3 else None
    return {'status':'RESEARCH_ONLY','n':len(last),'median_minutes':round(projected_minutes,2),
            'recent_three_minutes':mins[-3:],'minutes_trend_difference':round(drift,2) if drift is not None else None,
            'observed_points_per_minute_median':round(median(rates),4),
            'pace_multiplier_scenario':round(pace_adjust,4),
            'illustrative_points_projection':round(projected_points,2),
            'note':'No verified current lineup, minutes cap, usage adjustment, defense, or calibrated forecast. Not BTA-qualified.'}


def nfl_role(rows:list[dict], *, event_start_utc:str, role:str)->dict:
    if role not in ('receiver','rusher','quarterback'):raise ValueError('Unsupported role')
    fields={'receiver':('routes','targets','receptions'),'rusher':('carries','rush_yards','snaps'),
            'quarterback':('pass_attempts','completions','snaps')}[role]
    candidates=_before(rows,event_start_utc)
    usable=[]
    for r in candidates:
        base=finite_number(r.get(fields[0]))
        snaps=finite_number(r.get('snaps'))
        if base is not None and base>=0 and (snaps is None or snaps>=0):usable.append(r)
    if len(usable)<5:return {'status':'INSUFFICIENT','n':len(usable),'missing_primary_field':fields[0]}
    recent=usable[-10:]
    vals=[finite_number(r[fields[0]]) for r in recent]
    earlier=vals[:-3]
    trend=median(vals[-3:])-median(earlier) if len(earlier)>=3 else None
    out={'status':'RESEARCH_ONLY','role':role,'n':len(recent),'opportunity_field':fields[0],
         'median_opportunities':round(median(vals),2),'last_three':vals[-3:],
         'opportunity_trend_difference':round(trend,2) if trend is not None else None,
         'role_change_flag':(abs(trend)>=max(3,0.2*max(median(earlier),1))) if trend is not None else None,
         'note':'Role change is an alert, not proof of cause. QB/coaches/competition/inactive status require separate verification.'}
    if role=='receiver':
        targets=[finite_number(x.get('targets')) for x in recent]
        if all(x is not None for x in targets):
            out['total_targets_per_route']=round(sum(targets)/sum(vals),4) if sum(vals)>0 else None
    return out


def college_continuity(prior:dict,current:dict)->dict:
    """Only explicit verified QB/coach/returning-starter data; don't guess transfers."""
    required=('starting_qb_id','head_coach_id','returning_offensive_starters','returning_defensive_starters')
    missing=[x for x in required if x not in prior or x not in current or current[x] is None or prior[x] is None]
    if missing:return {'status':'PENDING','missing':missing,'reason':'Roster continuity facts missing'}
    for fld in required[2:]:
        x=finite_number(current[fld]);y=finite_number(prior[fld])
        if x is None or y is None or not 0<=x<=11 or not 0<=y<=11:
            return {'status':'INVALID','reason':'Returning-starter count must be 0..11'}
    return {'status':'RESEARCH_ONLY',
            'qb_changed':prior['starting_qb_id']!=current['starting_qb_id'],
            'head_coach_changed':prior['head_coach_id']!=current['head_coach_id'],
            'returning_offensive_starters':current['returning_offensive_starters'],
            'returning_defensive_starters':current['returning_defensive_starters'],
            'note':'Continuity checklist, not automatic win probability or accurate strength rating.'}


def opponent_adjusted(value:float, opponent_strength:float, *, baseline_strength:float,
                      sample_size:int, shrinkage_games:int=12)->dict:
    """Explicit experimental shrinkage calculation; no universal interpretation."""
    nums=[finite_number(x) for x in (value,opponent_strength,baseline_strength)]
    if any(x is None for x in nums) or sample_size<1 or shrinkage_games<1:
        return {'status':'INSUFFICIENT'}
    raw=nums[0]+(nums[1]-nums[2]);weight=sample_size/(sample_size+shrinkage_games)
    adj=nums[0]+weight*(nums[1]-nums[2])
    return {'status':'EXPERIMENTAL','raw':nums[0],'adjusted':round(adj,4),'sample_weight':round(weight,4),
            'note':'Strength orientation and metric units must be consistent; this is not a validated opponent-adjustment algorithm.'}
