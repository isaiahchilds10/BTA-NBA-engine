"""Conservative research gate, never an automatic BTA grade.

Written for the 40-section BTA specifications. These checks represent
provenance and human-reviewed scenario records, not automatic evidence discovery.
"""
from __future__ import annotations

SCRIPT_FAMILIES = {
    'CFB_MONEYLINE': ('normal', 'underdog_fast_start','favorite_minus_two_turnovers',
                      'primary_strength_neutralized','one_score_fourth'),
    'NFL_PROP': ('favorite_blowout','underdog_blowout','close','low_scoring','shootout'),
    'NBA_PROP': ('our_team_blowout','opponent_blowout','close','slow','fast'),
}
VERDICTS = {'BETTER','SAME','MIXED','WORSE'}


def evaluate_candidate(*, family: str, scripts: dict, source_attestations: dict,
                       evidence_reasons: dict, independent_review: bool,
                       settlement_verified: bool) -> dict:
    """Fail closed. A 'ready for manual grading' status is NOT a BTA selection.

    source_attestations keyed by matchup, participation, role, opponent,
    market_price, publication_time. Value must be explicitly verified as True.
    Caller must prove these attestations from source-linked records; UI
    checkboxes alone are not authoritative.
    """
    if family not in SCRIPT_FAMILIES:
        raise ValueError('Unknown market/sport script family')
    expected = set(SCRIPT_FAMILIES[family])
    if set(scripts) != expected:
        return {'gate':'PENDING','why':'Incomplete or incorrect scenario framework','worse_count':None}
    if any(v not in VERDICTS for v in scripts.values()):
        return {'gate':'PENDING','why':'Some game-script verdicts are unknown','worse_count':None}
    if any(not str(evidence_reasons.get(k,'')).strip() for k in expected):
        return {'gate':'PENDING','why':'Every script needs a documented causal mechanism','worse_count':None}
    worse=sum(v=='WORSE' for v in scripts.values())
    if family.endswith('PROP') and worse>=2:
        return {'gate':'CUT','why':'Two or more meaningfully WORSE player-prop scripts','worse_count':worse}
    required=('matchup','participation','role','opponent','market_price','publication_time')
    missing=[k for k in required if source_attestations.get(k) is not True]
    if missing:
        return {'gate':'PENDING','why':'Critical source checks unresolved: '+', '.join(missing), 'worse_count':worse}
    if not settlement_verified:
        return {'gate':'PENDING','why':'Market-specific settlement/void rules unknown','worse_count':worse}
    if not independent_review:
        return {'gate':'PENDING','why':'Independent failure-path audit not completed','worse_count':worse}
    if worse:
        return {'gate':'FURTHER REVIEW','why':'At least one WORSE game script; assess likelihood and severity', 'worse_count':worse}
    return {'gate':'READY FOR MANUAL GRADING',
            'why':'Research gates checked; no probability validation or BTA grade implied',
            'worse_count':0}
