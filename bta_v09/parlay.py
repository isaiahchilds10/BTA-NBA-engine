"""Joint-outcome risk with exact probability bounds and verified paired history.

For arbitrary dependent legs, marginal probabilities do not specify a joint
probability. Fréchet/union bounds ALWAYS hold. No fake correlation coefficients.
"""
from __future__ import annotations
from math import prod,sqrt,isfinite


def _leg_id(x:dict) -> tuple:
    return (x.get('event'),str(x.get('player') or '').casefold(),x.get('market'),
            x.get('selection'),x.get('line'))


def overlap_warnings(legs:list[dict]) -> list[str]:
    issues=[]
    identities={};events={};players={}
    for i,leg in enumerate(legs,1):
        identities.setdefault(_leg_id(leg),[]).append(i)
        events.setdefault(leg.get('event'),[]).append(i)
        player=str(leg.get('player') or '').casefold()
        if player:players.setdefault(player,[]).append(i)
    for ids in identities.values():
        if len(ids)>1:issues.append(f'Identical/nested candidate entries at legs {ids[:8]}: cannot count separately')
    for name,ids in events.items():
        if name and len(ids)>1:issues.append(f'Shared game {name}: legs {ids[:8]} may move together')
    for player,ids in players.items():
        if len(ids)>1:issues.append(f'Shared player {player}: legs {ids[:8]} have overlapping injury and role risk')
    return issues[:35]


def uncertainty_bounds(legs:list[dict]) -> dict:
    if not legs:return {'status':'EMPTY','n':0}
    if len(legs)>200:raise ValueError('Maximum 200 candidate legs')
    values=[]
    for i,x in enumerate(legs,1):
        p=x.get('probability')
        if isinstance(p,bool) or not isinstance(p,(float,int)) or not isfinite(p) or not 0<=p<=1:
            return {'status':'NO JOINT ESTIMATE','n':len(legs),
                    'reason':f'Leg {i} has no defensible numeric marginal probability',
                    'overlaps':overlap_warnings(legs)}
        if x.get('calibrated') is not True or x.get('verified_market') is not True:
            return {'status':'NO JOINT ESTIMATE','n':len(legs),
                    'reason':f'Leg {i} is not both calibrated and linked to an exact verified market',
                    'overlaps':overlap_warnings(legs)}
        values.append(float(p))
    # Conjunction inequalities; apply even under arbitrarily strong dependence.
    lower=max(0.0, sum(values)-(len(values)-1))
    upper=min(values)
    # Independence estimate shown ONLY as a mathematical diagnostic assumption.
    independent=prod(values)
    return {'status':'BOUNDS ONLY','n':len(legs),
            'valid_joint_lower':round(lower,8),'valid_joint_upper':round(upper,8),
            'independence_hypothesis_only':round(independent,8),
            'overlaps':overlap_warnings(legs),
            'reason':'Marginal probabilities alone cannot determine correlated parlay success. ' 
                     'The bounds are mathematically valid, but may be extremely wide.'}


def wilson_interval(wins:int,n:int,z:float=1.96)->tuple[float,float]:
    if not 0<=wins<=n or n==0:raise ValueError('Invalid wins/sample')
    p=wins/n;z2=z*z;d=1+z2/n
    center=(p+z2/(2*n))/d
    spread=z*sqrt(p*(1-p)/n+z2/(4*n*n))/d
    return max(0,center-spread),min(1,center+spread)


def historical_joint(paired: list[dict], *,minimum:int=60) -> dict:
    """Paired complete outcomes must be from same comparable historical slates.

    Observed co-hits are NOT a guaranteed future joint probability.
    Cluster dependence across dates is NOT fully resolved by Wilson CI.
    """
    rows=[];dates=set()
    for record in paired:
        if record.get('verified_settlement') is not True or record.get('comparable') is not True:
            continue
        outcomes=record.get('outcomes')
        d=record.get('date')
        if not d or not isinstance(outcomes,list) or not outcomes or any(type(x) is not bool for x in outcomes):
            continue
        dates.add(d);rows.append(all(outcomes))
    if len(rows)<minimum or len(dates)<20:
        return {'status':'INSUFFICIENT PAIRED HISTORY','n':len(rows),'days':len(dates)}
    lo,hi=wilson_interval(sum(rows),len(rows))
    return {'status':'HISTORICAL JOINT ONLY','observed':sum(rows),'n':len(rows),
            'rate':round(sum(rows)/len(rows),5),
            'naive_wilson_95pct_interval':[round(lo,5),round(hi,5)],
            'caution':'Assumes observations are independent; cluster dependence can widen uncertainty. '
                      'Selection rules must match the proposed joint ticket prospectively.'}
