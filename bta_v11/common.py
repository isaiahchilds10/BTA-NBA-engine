"""As-of semantics; no naive or post-event dates are accepted."""
from __future__ import annotations
from datetime import datetime, timezone
from math import isfinite
from hashlib import sha256
from json import dumps


def parse_time(x):
    if isinstance(x, datetime):
        t=x
    elif isinstance(x,str):
        try:t=datetime.fromisoformat(x.replace('Z','+00:00'))
        except ValueError:return None
    else:return None
    return t.astimezone(timezone.utc) if t.tzinfo else None


def timestamp_now():return datetime.now(timezone.utc).isoformat()


def number(x):
    if isinstance(x,bool):return None
    try:v=float(x)
    except (TypeError,ValueError,OverflowError):return None
    return v if isfinite(v) else None


def fingerprint(obj):return sha256(dumps(obj,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()[:24]


def asof_gate(*, asof, retrieved, event_start, max_age_hours, now=None):
    """Metadata only; accepted timestamps do NOT authenticate the source."""
    a=parse_time(asof);r=parse_time(retrieved);e=parse_time(event_start)
    n=parse_time(now) if now is not None else datetime.now(timezone.utc)
    if not a or not r or not e or not n or max_age_hours<=0:
        return {'ok':False,'reason':'Timestamp missing, unzoned, or invalid'}
    if a>r or r>n or a>=e or n>=e:
        return {'ok':False,'reason':'Data or evaluation postdates retrieval/event start'}
    age=(n-a).total_seconds()/3600
    return {'ok':0<=age<=max_age_hours,'age_hours':round(age,2),
            'reason':'FRESH_AS_OF_ONLY' if age<=max_age_hours else 'STALE_SOURCE_AS_OF'}
