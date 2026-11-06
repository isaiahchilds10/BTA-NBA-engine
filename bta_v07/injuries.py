"""Dated injury evidence from v0.5 sources; no 'not listed = healthy' shortcuts."""
from __future__ import annotations
from datetime import datetime, timezone


def _iso_dt(value):
    try:
        dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if dt.tzinfo is None:return None
        return dt.astimezone(timezone.utc)
    except (ValueError,TypeError):return None


def safety_verdict(record:dict, *, requested_game_utc:datetime|None=None,
                   checked_at:datetime|None=None, max_age_hours:float=24) -> dict:
    """Only decides blocked/review/unverified. Does not confirm an active lineup."""
    now=checked_at or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError('checked_at must have timezone')
    published=_iso_dt(record.get('published_at_utc'))
    if not published:return {'gate':'UNVERIFIED','reason':'Missing timezone-aware source publication timestamp'}
    age=(now-published).total_seconds()/3600
    if age < -1 or age>max_age_hours:
        return {'gate':'UNVERIFIED','reason':'Injury report is stale or future-dated','age_hours':round(age,2)}
    if requested_game_utc is not None:
        if requested_game_utc.tzinfo is None:raise ValueError('Game start requires timezone')
        if published>=requested_game_utc.astimezone(timezone.utc):
            return {'gate':'UNVERIFIED','reason':'Report published at/after event start, cannot use for pregame analysis'}
    status=str(record.get('status') or 'UNKNOWN').upper().strip()
    if status in {'OUT','DOUBTFUL','INACTIVE'}:
        return {'gate':'BLOCKED','status':status,'reason':'Source reports likely unavailable; require recheck if status changes'}
    if status in {'QUESTIONABLE','GTD','PROBABLE','AVAILABLE'}:
        return {'gate':'REVIEW REQUIRED','status':status,
                'reason':'A dated injury designation does not establish unrestricted playing time or official game-day activity.'}
    return {'gate':'UNVERIFIED','status':status,
            'reason':'Not listed/unmatched or unrecognized status does not confirm that player is active.'}


def nba_official(player:str):
    """Automatic download of official report, then conservative player lookup."""
    from bta_v05.sources import latest_nba_official_report
    from bta_v05.models import nba_injury_lookup
    text, meta=latest_nba_official_report()
    return nba_injury_lookup(text,player,meta),meta


def nfl_weekly_report(player:str, team:str, week:int,season:int):
    """Automatically reads nflverse weekly injury listing, NOT an official inactive roster."""
    from bta_v05.sources import nfl_injury_reports
    from bta_v05.models import nfl_injury_lookup
    rows,meta=nfl_injury_reports(season)
    result=nfl_injury_lookup(rows,player,week,team)
    return result,meta


def college_availability(team:str,player:str|None=None):
    return {'gate':'UNVERIFIED','team':team,'player':player,
            'reason':'No comprehensive, reliable official college participation source connected. '
                     'Team game-day release or verified personnel information required.'}
