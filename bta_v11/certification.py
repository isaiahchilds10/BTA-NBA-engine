"""Conservative BTA+ *eligibility* gate. Never claims a guaranteed winner.

Each gate requires externally checked evidence. Under user rules, 2+ WORSE
player-prop scripts always CUT. TAIG remains exceptional and requires a separate
audit; unsupported automated TAIG inflation is prohibited.
"""
from __future__ import annotations

REQUIRED_GATES=(
    'exact_market_and_rule_verified','schedule_and_event_verified',
    'provider_freshness_verified','source_conflicts_resolved',
    'current_availability_verified','role_and_workload_verified',
    'opponent_adjustment_supported','distribution_and_cushion_audited',
    'ordinary_misses_reviewed','reverse_failure_audited',
    'five_scripts_evidence_backed','independent_red_team_passed',
    'prospective_model_validation_passed','market_price_verified',
    'no_material_new_information','separate_holdout_used',
)


def assess(*,family:str,evidence:dict,scripts:list[dict],
           proposed_grade:str,ordinary_failure_severity:str,
           model_diagnostics:dict,availability:dict,
           nfl_route_evidence:dict|None=None,market_identity:str|None=None,
           forecast_model_id:str|None=None)->dict:
    family=str(family).upper()
    prop=family in ('NBA_PROP','NFL_PROP')
    if family not in ('NBA_PROP','NFL_PROP','CFB_MONEYLINE','GAME_MARKET'):
        return {'status':'INVALID_FAMILY','grade':'NONE','qualified':False}
    worse=sum(x.get('verdict')=='WORSE' for x in scripts) if prop else 0
    if prop and worse>=2:
        return {'status':'CUT_TWO_WORSE_SCRIPTS','grade':'CUT','qualified':False,
                'worse':worse,'blockers':['Two or more material WORSE game scripts']}
    blockers=[k for k in REQUIRED_GATES if evidence.get(k) is not True]
    if not prop and sum(s.get('verdict')=='VULNERABLE' for s in scripts)>=2:
        blockers.append('Two or more vulnerable outright-win stress scenarios; independent review required')
    if not market_identity:blockers.append('Canonical market identity missing')
    if (model_diagnostics or {}).get('status')!='OUT_OF_TIME_DIAGNOSTICS_PASS':
        blockers.append('Independent out-of-time calibration diagnostics missing')
    if not forecast_model_id or model_diagnostics.get('model_id')!=forecast_model_id or model_diagnostics.get('market_family')!=family:
        blockers.append('Forecast model/version/market family differs from validated holdout')
    if availability.get('eligible') is not True:
        blockers.append('Game-day availability not supported by required source')
    if family=='NFL_PROP' and (nfl_route_evidence or {}).get('routes_supported') is not True:
        blockers.append('Verified in-season route participation incomplete')
    expected={
        'NFL_PROP': {'FAVORITE_BLOWOUT','UNDERDOG_BLOWOUT','CLOSE','LOW_SCORING','SHOOTOUT'},
        'CFB_MONEYLINE': {'NORMAL_EXPECTED','UNDERDOG_FAST_START','NEGATIVE_TWO_TURNOVERS',
                          'PRIMARY_STRENGTH_NEUTRALIZED','ONE_SCORE_Q4'},
        'NBA_PROP': {'PLAYER_TEAM_BLOWOUT','OPPONENT_BLOWOUT','CLOSE','LOW_PACE','HIGH_PACE'},
        'GAME_MARKET': {'EXPECTED','FAST_START','TURNOVER_OR_POSSESSION_SHOCK','KEY_STRENGTH_LOST','CLOSE_FINISH'},
    }[family]
    if len(scripts)!=5 or {s.get('scenario') for s in scripts}!=expected:
        blockers.append('Sport-specific five scripts incomplete or wrongly named')
    valid_verdicts={'BETTER','SAME','MIXED','WORSE'} if prop else {'RESILIENT','MIXED','VULNERABLE'}
    if any(not isinstance(s.get('mechanism'),str) or len(s['mechanism'].strip())<12 or
           not isinstance(s.get('evidence_urls'),list) or
           not s['evidence_urls'] or
           not all(isinstance(url,str) and url.startswith('https://') for url in s['evidence_urls']) or
           s.get('verdict') not in valid_verdicts for s in scripts):
        blockers.append('Script lacks valid mechanism, verdict or source evidence')
    if ordinary_failure_severity not in ('LOW','MODERATE','HIGH','CRITICAL'):
        blockers.append('Ordinary failure severity unsupported')
    if ordinary_failure_severity in ('HIGH','CRITICAL'):
        blockers.append('Serious ordinary failure mechanism remains')
    if proposed_grade not in ('TAIG','ELITE/CORE BTA+','STRONG BTA+','BTA+','BTA'):
        blockers.append('No qualified predeclared grade')
    if blockers:
        return {'status':'PENDING_VERIFICATION','grade':'PENDING','qualified':False,
                'worse':worse,'blockers':sorted(set(blockers))}
    if proposed_grade=='TAIG':
        return {'status':'EXCEPTIONAL_AUDIT_REQUIRED','grade':'PENDING TAIG','qualified':False,
                'worse':worse,'blockers':['Independent exceptional TAIG audit required']}
    if worse==1 and proposed_grade!='BTA':
        return {'status':'ONE_WORSE_ADDITIONAL_REVIEW','grade':'PENDING','qualified':False,
                'worse':worse,'blockers':['One WORSE scenario requires further case-specific evidence']}
    # Eligibility still means evidence-backed quantitative evaluation, not outcome guarantee.
    return {'status':'RULE_QUALIFIED_RESEARCH','grade':proposed_grade,'qualified':True,
            'worse':worse,'blockers':[],
            'note':'Automatic rule qualification requires real authenticated inputs. It is not a guarantee of winning or proof of positive expected value.'}
