"""Parlay dependence analysis. Never multiply correlated marginals as a forecast."""
from __future__ import annotations
from math import sqrt
from .common import finite_number


def shared_risk(legs:list[dict])->dict:
    conflicts=[]
    for i,a in enumerate(legs):
        for j in range(i+1,len(legs)):
            b=legs[j];reasons=[]
            if a.get('event_key') and a.get('event_key')==b.get('event_key'):
                reasons.append('same_game')
            if a.get('player_id') and a.get('player_id')==b.get('player_id'):
                reasons.append('same_player')
            if a.get('team_id') and a.get('team_id')==b.get('team_id'):
                reasons.append('same_team_offensive_environment')
            if a.get('weather_group') and a.get('weather_group')==b.get('weather_group'):
                reasons.append('shared_weather')
            if a.get('injury_dependency') and a.get('injury_dependency')==b.get('injury_dependency'):
                reasons.append('shared_injury_dependency')
            if a.get('market_id') and a.get('market_id')==b.get('market_id'):
                reasons.append('duplicate_market')
            if reasons:conflicts.append({'a':i,'b':j,'reasons':reasons})
    return {'status':'RISK_FLAGS_ONLY','leg_count':len(legs),'pairs':conflicts,
            'note':'Absence of flagged metadata does not prove independence.'}


def joint_bounds(probabilities:list[float],*,calibrated:bool=False)->dict:
    vals=[finite_number(p) for p in probabilities]
    if not vals or any(p is None or not 0<=p<=1 for p in vals):
        return {'status':'INVALID_INPUT'}
    lower=max(0.0,sum(vals)-(len(vals)-1))
    upper=min(vals)
    return {'status':'MATHEMATICAL_BOUNDS' if calibrated else 'INPUT_NOT_CALIBRATED',
            'lower':round(lower,6),'upper':round(upper,6),
            'note':'Frechet bounds are valid for marginals; not a joint predicted chance.'}


def paired_history(observations:list[dict],leg_ids:list[str],*,minimum:int=100)->dict:
    """Describe matched prospective samples; do not extrapolate to future games.

    Each row must supply a pre-event timestamp, a unique observation ID,
    unique paired event IDs, a verified settlement, full binary outcome dict,
    stable source and exact shared exposure. Duplicated games are excluded.
    """
    if not leg_ids or len(set(leg_ids))!=len(leg_ids) or minimum<30:
        return {'status':'INVALID_INPUT'}
    from .common import utc
    eligible=[];rejected=0;seen=set();seen_event_sets=set()
    for row in observations:
        start=utc(row.get('event_start_utc'));logged=utc(row.get('forecast_at_utc'))
        outcomes=row.get('outcomes')
        ident=row.get('observation_id')
        component_events=row.get('paired_event_ids')
        unit=tuple(sorted(str(x) for x in component_events)) if isinstance(component_events,(list,tuple)) else None
        if not ident or ident in seen or not unit or len(unit)!=len(set(unit)) or unit in seen_event_sets:
            rejected+=1;continue
        if not (start and logged and logged<start and row.get('verified_settlement') is True
                and isinstance(outcomes,dict) and all(k in outcomes and type(outcomes[k]) is int and outcomes[k] in (0,1) for k in leg_ids)
                and str(row.get('settlement_source','')).startswith('https://')):
            rejected+=1;continue
        seen.add(ident);seen_event_sets.add(unit)
        eligible.append(int(all(outcomes[k]==1 for k in leg_ids)))
    n=len(eligible)
    if n<minimum:
        return {'status':'INSUFFICIENT_PAIRED_HISTORY','n':n,'required':minimum,'rejected':rejected,
                'note':'Not enough comparable paired pregame observations to characterize dependence'}
    hits=sum(eligible);p=hits/n;z=1.96;denom=1+z*z/n
    center=(p+z*z/(2*n))/denom
    half=z*sqrt(p*(1-p)/n+z*z/(4*n*n))/denom
    return {'status':'HISTORICAL_JOINT_FREQUENCY_ONLY','n':n,'wins':hits,
            'observed_joint_rate':round(p,5),'wilson_95_interval':[round(max(0,center-half),5),round(min(1,center+half),5)],
            'rejected':rejected,'note':'Not a calibrated future parlay probability. Historical pairings must be comparable and independently held out.'}
