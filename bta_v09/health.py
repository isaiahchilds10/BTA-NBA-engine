"""Evidence age audit: downloaded now does not imply published now.

No player availability, freshness, or model confidence may be inferred from
an HTTP success alone. All functions are pure and fixture-testable.
"""
from __future__ import annotations
from datetime import date, datetime, timezone
from bta_v08.schedule import parse_instant


def source_age(league: str, metadata: list[dict], rows: list[dict], *, now: datetime) -> dict:
    if now.tzinfo is None:
        raise ValueError('Timestamp must be timezone-aware')
    local_date = now.astimezone(timezone.utc).date()
    if league == 'NBA':
        snapshots=[]
        for meta in metadata:
            if not isinstance(meta,dict) or meta.get('status')=='SOURCE ERROR':
                continue
            value=str(meta.get('snapshot') or '')
            try:
                stamp=date.fromisoformat(value)
            except ValueError:
                continue
            snapshots.append(stamp)
        if not snapshots:
            return {'status':'UNKNOWN PUBLICATION DATE','as_of':None,
                    'reason':'No parseable NBA game-log snapshot date; successful retrieval is not freshness proof.'}
        latest=max(snapshots)
        days=(local_date-latest).days
        if days < 0:
            status='INVALID FUTURE SNAPSHOT'
        elif days<=5:
            status='RECENT PUBLICATION'
        else:
            status='STALE PUBLICATION'
        return {'status':status,'as_of':latest.isoformat(),'age_days':days,
                'reason':'Five days is a review policy, not a provider release guarantee. Offseason files may be older.'}
    if league == 'NFL':
        weeks=set()
        for row in rows:
            try:
                season=int(row.get('season'));week=int(row.get('week'))
                if 1999<=season<=2100 and 1<=week<=25:
                    weeks.add((season,week))
            except (ValueError,TypeError,AttributeError):
                continue
        if not weeks:
            return {'status':'UNKNOWN PUBLICATION DATE','latest_season_week':None,
                    'reason':'No usable NFL season/week metadata; retrieval date is not publication date.'}
        year,week=max(weeks)
        return {'status':'WEEKLY HISTORY ONLY','latest_season_week':f'{year} W{week}',
                'reason':'Latest available game week; cannot certify current release timing, lineup, or injury status.'}
    return {'status':'UNSUPPORTED','reason':'No freshness method for this source family'}


def snapshot_age(built_at_utc: str | None, *, now:datetime) -> dict:
    stamp=parse_instant(built_at_utc)
    if stamp is None:
        return {'status':'UNKNOWN','age_minutes':None}
    delta=(now.astimezone(timezone.utc)-stamp).total_seconds()/60
    if delta < -5:
        status='INVALID FUTURE SNAPSHOT'
    elif delta <= 20:
        status='RECENT COLLECTION'
    elif delta <= 180:
        status='AGING COLLECTION'
    else:
        status='STALE COLLECTION'
    return {'status':status,'age_minutes':round(delta,1),
            'note':'Collection age is not the age of all underlying statistics.'}
