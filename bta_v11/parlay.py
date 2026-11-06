"""Dependence-aware parlay research.

Naive products of P(leg) are not used. If scenario probabilities are supplied,
a within-scenario independence assumption must be explicitly validated. Exact
historical joint results are descriptive. Future probability needs its own
prospective out-of-time validation; no arbitrary copula coefficients are set.
"""
from __future__ import annotations
from math import sqrt
from .common import number,parse_time


def joint_historical(observations:list[dict], leg_ids:list[str],*,minimum=150)->dict:
    if len(leg_ids)<2 or len(set(leg_ids))!=len(leg_ids) or minimum<30:
        return {'status':'INVALID_INPUT'}
    unique={};duplicate=set();invalid=0
    for obs in observations:
        # Independent units are explicitly identified comparable historical
        # slate configurations, never repeated copies of the same games.
        key=obs.get('independent_slate_id')
        pred=parse_time(obs.get('forecast_utc'))
        started=parse_time(obs.get('earliest_event_start_utc'))
        settled=parse_time(obs.get('settled_at_utc'))
        if (not key or not obs.get('source_verified') or not obs.get('pregame_archived')
            or not pred or not started or not settled or not pred<started<settled):
            invalid+=1;continue
        marks=obs.get('outcomes')
        if not isinstance(marks,dict) or any(type(marks.get(i))!=int or marks[i] not in (0,1) for i in leg_ids):
            invalid+=1;continue
        if key in unique:
            duplicate.add(key)
        else:unique[key]=marks
    for key in duplicate:unique.pop(key,None)
    n=len(unique)
    if n<minimum:
        return {'status':'INSUFFICIENT_COMPARABLE_JOINT_HISTORY',
                'n':n,'required':minimum,'duplicate_slate_ids':len(duplicate),'invalid':invalid}
    hits=sum(all(row[i]==1 for i in leg_ids) for row in unique.values())
    p=hits/n;z=1.96;d=1+z*z/n
    c=(p+z*z/(2*n))/d
    e=z*sqrt((p*(1-p)+z*z/(4*n))/n)/d
    return {'status':'OBSERVED_HISTORICAL_JOINT_RATE','n':n,'hits':hits,'rate':round(p,6),
            'wilson_95':[round(max(0,c-e),6),round(min(1,c+e),6)],
            'note':'Historical joint success is not a validated future parlay probability.'}


def conditional_scenarios(scenarios:list[dict],leg_ids:list[str],*,model_validation:dict|None=None)->dict:
    """Compute sum_s weight[s] * joint_p[s], where joint_p[s] is itself fitted
    and validated from paired within-scenario outcomes, not products of legs.
    No independent-marginal multiplication is used.
    """
    if len(leg_ids)<2 or len(set(leg_ids))!=len(leg_ids) or not scenarios:
        return {'status':'INVALID_INPUT'}
    weights=[];pieces=[]
    for row in scenarios:
        w=number(row.get('weight'));p=number(row.get('empirical_joint_p'))
        if w is None or p is None or w<0 or not 0<=p<=1 or not row.get('distinct_scenario'):
            return {'status':'MISSING_VALIDATED_SCENARIO_INPUT'}
        observed=parse_time(row.get('data_asof_utc'))
        start=parse_time(row.get('event_start_utc'))
        if row.get('leg_ids')!=leg_ids or not observed or not start or not observed<start:
            return {'status':'SCENARIO_IDENTITY_OR_TIMING_MISMATCH'}
        weights.append(w);pieces.append(p)
    if len({x['distinct_scenario'] for x in scenarios})!=len(scenarios) or abs(sum(weights)-1)>.000001:
        return {'status':'BAD_SCENARIO_WEIGHTS'}
    estimate=sum(w*p for w,p in zip(weights,pieces))
    valid=((model_validation or {}).get('status')=='OUT_OF_TIME_DIAGNOSTICS_PASS'
           and (model_validation or {}).get('market_family')=='JOINT_PARLAY'
           and (model_validation or {}).get('model_id')==scenarios[0].get('joint_model_id')
           and (model_validation or {}).get('test',0)>=100
           and (model_validation or {}).get('test_event_count',0)>=50
           and all(x.get('joint_model_id')==scenarios[0].get('joint_model_id')
                   and x.get('validated_joint_source') is True
                   and isinstance(x.get('training_pair_count'),int)
                   and x['training_pair_count']>=100 for x in scenarios))
    return {'status':'JOINT_MODEL_DIAGNOSTICS_PASS' if valid else 'JOINT_MODEL_UNVALIDATED',
            'probability_estimate':round(estimate,6) if valid else None,
            'hypothetical_estimate':round(estimate,6),
            'note':'Scenario joint probabilities must come from comparable PAIRWISE/JOINED outcomes, not multiplied marginals. Even a passing holdout is not a guarantee.'}
