"""Opponent-adjusted historical environment, with strict pregame filtering.

Never treat adjustment factors as validated probabilities. Without pace and
opponent-strength denominators these are descriptive scouting estimates only.
"""
from __future__ import annotations
from statistics import mean
from datetime import date
from math import isfinite


def _f(v):
    try:
        f=float(v)
        return f if isfinite(f) else None
    except (ValueError,TypeError):return None


def opponent_rate_context(allowed_rows:list[dict], *, opponent:str, stat_key:str,
                          cutoff:date, date_key:str='date', opponent_key:str='defense_team',
                          min_opponent:int=5,min_league:int=40) -> dict:
    """Rows are *previous opponent possessions/games*, each carrying exposure.

    Required fields: defense_team, date, stat_key and `opportunities` denominator.
    E.g. receiving yards allowed per pass attempt, not totals per game.
    All entries MUST precede kickoff. Opponent strength of faced offenses not
    adjusted here; do not call this a fully opponent-adjusted forecast.
    """
    league=[]; target=[]
    for r in allowed_rows:
        try:d=date.fromisoformat(str(r.get(date_key,''))[:10])
        except ValueError:continue
        if d>=cutoff:continue
        value=_f(r.get(stat_key));exposure=_f(r.get('opportunities'))
        if value is None or exposure is None or exposure<=0:continue
        record=(value,exposure)
        league.append(record)
        if str(r.get(opponent_key,'')).upper()==opponent.upper():target.append(record)
    if len(target)<min_opponent or len(league)<min_league:
        return {'status':'INSUFFICIENT','target_n':len(target),'league_n':len(league),
                'reason':'No reliable past exposure-adjusted sample'}
    lg=sum(v for v,e in league)/sum(e for v,e in league)
    df=sum(v for v,e in target)/sum(e for v,e in target)
    if lg<=0:
        return {'status':'INSUFFICIENT','reason':'Zero league exposure rate'}
    # Shrink toward league rate. These values are research heuristics, not fitted.
    weight=len(target)/(len(target)+15)
    adj=1 + weight*(df/lg-1)
    return {'status':'DESCRIPTIVE ONLY','target_n':len(target),'league_n':len(league),
            'league_per_opportunity':round(lg,4),'opponent_per_opportunity':round(df,4),
            'shrunken_context_factor':round(max(.75,min(1.25,adj)),3),
            'reason':'Does not adjust for offenses faced, scheme, personnel, pace, or future role. Not a forecast.'}


def reverse_matchup_context(player_games:list[dict], *, opponent_quality:dict[str,float],
                            next_opponent:str, cutoff:date, field:str) -> dict:
    """Compare *previous defense ranks/ratings* to upcoming defense; return
    matchup strength signals, not automatic BTA approval.
    Quality scales must be supplied consistently (higher=better defense).
    """
    if next_opponent not in opponent_quality:
        return {'status':'UNVERIFIED','reason':'Upcoming defense not rated in common source/model'}
    past=[]
    for g in player_games:
        try:d=date.fromisoformat(str(g.get('date',''))[:10])
        except ValueError:continue
        if d>=cutoff:continue
        opp=g.get('opponent');v=_f(g.get(field))
        if opp in opponent_quality and v is not None:
            past.append((v,opponent_quality[opp]))
    if len(past)<5:return {'status':'INSUFFICIENT','n':len(past)}
    return {'status':'DESCRIPTIVE ONLY','n':len(past),
            'sample_mean_defense_quality':round(mean(q for _,q in past),3),
            'upcoming_defense_quality':round(opponent_quality[next_opponent],3),
            'potentially_tougher_than_history':opponent_quality[next_opponent]>mean(q for _,q in past),
            'reason':'The defense-quality scale must be validated and measured pregame; opponent adjustment is not causal.'}
