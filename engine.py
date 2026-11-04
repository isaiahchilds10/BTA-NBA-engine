"""BTA paper-betting research core. No real wager placement or model predictions."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

ALLOWED_GRADES = ('TAIG', 'BTA+', 'BTA', 'Conditional', 'Eliminate')


def decimal_odds(american: int) -> float:
    """Convert valid American betting odds to decimal odds."""
    if isinstance(american, bool) or not isinstance(american, int):
        raise ValueError('American odds must be an integer.')
    if -100 < american < 100:
        raise ValueError('American odds must be +100 or higher, or -100 or lower.')
    return 1 + (american / 100 if american > 0 else 100 / abs(american))


def implied_probability(american: int) -> float:
    return 1.0 / decimal_odds(american)


def expected_return(probability: float, american: int) -> float:
    """Expected profit per dollar staked (not a forecast)."""
    if not 0 < probability < 1:
        raise ValueError('Probability must be between zero and one.')
    d = decimal_odds(american)
    return probability * (d - 1) - (1 - probability)


@dataclass(frozen=True)
class Assessment:
    status: str
    reason: str
    stake: float
    edge: float
    ev: float


def assess(*, probability: float, american: int, grade: str,
           bankroll: float, open_exposure: float,
           evidence_reviewed: bool, blockers: bool,
           same_event_already_open: bool = False) -> Assessment:
    """Conservative, illustrative paper-trading rules, NOT the user's full BTA rubric."""
    if not 0 < probability < 1:
        raise ValueError('Estimated probability must be between zero and one.')
    if not 0 < bankroll <= 1e9:
        raise ValueError('Simulated bankroll must be positive.')
    if not 0 <= open_exposure <= bankroll:
        raise ValueError('Open exposure must be between zero and bankroll.')
    if grade not in ALLOWED_GRADES:
        raise ValueError('Unknown BTA grade.')
    imp = implied_probability(american)
    edge = probability - imp
    ev = expected_return(probability, american)
    def reject(reason: str) -> Assessment:
        return Assessment('WATCH ONLY', reason, 0.0, edge, ev)
    if grade not in ('TAIG', 'BTA+'):
        return reject('Only provisional TAIG/BTA+ grades reach paper-stake eligibility.')
    if not evidence_reviewed:
        return reject('Review and document input evidence before assigning a paper stake.')
    if blockers:
        return reject('An unresolved injury, lineup, data-quality, or other blocker exists.')
    if same_event_already_open:
        return reject('One open simulated position per game; correlated exposure blocked.')
    if edge < 0.03 or ev <= 0:
        return reject('Estimated edge is below the illustrative 3 percentage-point buffer.')
    remaining = max(0, round(bankroll * 0.05 - open_exposure, 2))
    stake = min(round(bankroll * 0.005, 2), remaining)
    if stake <= 0:
        return reject('Portfolio paper-exposure cap is reached.')
    return Assessment('PAPER ELIGIBLE', 'Illustrative rule passed; the probability estimate is unvalidated.', stake, edge, ev)


def profit_for_result(stake: float, american: int, result: str) -> Optional[float]:
    if result == 'WIN':
        return round(stake * (decimal_odds(american) - 1), 2)
    if result == 'LOSS':
        return -round(stake, 2)
    if result == 'PUSH':
        return 0.0
    if result in ('OPEN', 'WATCH ONLY'):
        return None
    raise ValueError('Invalid result.')
