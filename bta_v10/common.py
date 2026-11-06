"""Common strict UTC + identity utilities; fail closed on ambiguous input."""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
from json import dumps
from math import isfinite


def utc(value: str | datetime | None) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        result=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:
        return None
    return result.astimezone(timezone.utc) if result.tzinfo else None


def finite_number(value) -> float | None:
    if isinstance(value, bool):return None
    try:
        x=float(value)
    except (TypeError,ValueError,OverflowError):return None
    return x if isfinite(x) else None


def digest(data) -> str:
    return sha256(dumps(data,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()


def market_identity(event:dict, offer:dict) -> str | None:
    """Exact sportsbook line + direction, not just team or player names."""
    keys=('event_key','start_utc')
    if any(not event.get(k) for k in keys):return None
    if not offer.get('market') or not offer.get('selection') or not offer.get('bookmaker'):
        return None
    if offer.get('line') is None and offer.get('market') not in ('h2h','moneyline'):
        return None
    item={k:event[k] for k in keys}
    item.update({k:offer.get(k) for k in ('bookmaker','market','player','selection','line','period','contract_id','rule_version')})
    return digest(item)[:32]


def before_event(*, event_start:str, created_at:str, data_asof:str)->bool:
    start=utc(event_start);made=utc(created_at);asof=utc(data_asof)
    return bool(start and made and asof and asof<=made<start)
