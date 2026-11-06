"""Audit source timestamps without pretending a successful download proves validity.

Source publication time and retrieval time are different. Missing publication
metadata is never interpreted as a contemporaneous official report.
"""
from __future__ import annotations
from datetime import datetime, timezone
from bta_v08.schedule import parse_instant

MAX_AGE = {'schedule': 30, 'odds': 15, 'injury': 24*60,
           'boxscore': 48*60, 'weekly': 7*24*60, 'historical': 30*24*60}


def freshness(*, timestamp: str | None, kind: str, now: datetime | None = None) -> dict:
    if kind not in MAX_AGE:
        raise ValueError(f'Unknown source family: {kind}')
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        raise ValueError('now must be timezone-aware')
    stamp = parse_instant(timestamp)
    if stamp is None:
        return {'status': 'UNVERIFIED', 'reason': 'Missing time-zoned source timestamp', 'age_minutes': None}
    delta = (ref.astimezone(timezone.utc)-stamp).total_seconds()/60
    if delta < -5:
        return {'status': 'INVALID', 'reason': 'Future-dated source', 'age_minutes': round(delta,2)}
    return {'status': 'CURRENT' if delta <= MAX_AGE[kind] else 'STALE',
            'reason': f'{kind} age {delta:.1f} min (policy <= {MAX_AGE[kind]} min)',
            'age_minutes': round(delta,2)}


def valid_pregame(event: dict, asof: str, now: datetime | None = None) -> tuple[bool, str]:
    when = parse_instant(event.get('start_utc'))
    data = parse_instant(asof)
    clock = now or datetime.now(timezone.utc)
    if not when or not data or clock.tzinfo is None:
        return False, 'Missing/invalid timezone-aware event or data timestamp'
    if data > clock.astimezone(timezone.utc):
        return False, 'Data appears to be from the future'
    if not (data < when and clock.astimezone(timezone.utc) < when and event.get('status') == 'UPCOMING'):
        return False, 'Game has begun, or research timestamp is not pregame'
    return True, 'Pregame cutoff passed'


def coverage_report(required: dict[str, bool], sources: list[dict]) -> dict:
    missing = sorted(k for k,v in required.items() if v is not True)
    return {'status': 'COMPLETE' if not missing else 'INCOMPLETE', 'missing': missing,
            'sources': [{k:v for k,v in row.items() if k not in ('raw','api_key','token','authorization')}
                        for row in sources],
            'note': 'Source retrieval proves data availability, NOT current player participation.'}
