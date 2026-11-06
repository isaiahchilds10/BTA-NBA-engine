"""League-specific ESPN scoreboard ingestion (undocumented endpoint).

All fetched events include provider ID, UTC time, teams, state and source metadata.
FBS-only `groups=80` is an ESPN convention rather than a stable public API.
Schedules are not evidence of player availability or bettable markets.
"""
from __future__ import annotations
import json
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LEAGUES = {
    'NBA': ('basketball', 'nba'),
    'NFL': ('football', 'nfl'),
    'College football': ('football', 'college-football'),
}


def utcstamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_instant(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except ValueError:
        return None


def _team(comp: dict) -> dict:
    team = comp.get('team') or {}
    return {
        'id': str(team.get('id') or ''),
        'name': str(team.get('displayName') or ''),
        'abbr': str(team.get('abbreviation') or '').upper(),
        'score': str(comp.get('score')) if comp.get('score') is not None else None,
    }


def parse_scoreboard(payload: dict, league: str, *, request_day: date, source: str, retrieved_at_utc: str) -> list[dict]:
    if league not in LEAGUES or not isinstance(payload, dict) or not isinstance(payload.get('events'), list):
        raise ValueError('Unsupported league or scoreboard schema changed')
    result = []
    for event in payload['events']:
        if not isinstance(event, dict):
            continue
        comps = event.get('competitions') or []
        if not comps or not isinstance(comps[0], dict):
            continue
        by_side = {}
        for member in comps[0].get('competitors') or []:
            if isinstance(member, dict) and member.get('homeAway') in ('home', 'away'):
                by_side[member['homeAway']] = member
        if 'home' not in by_side or 'away' not in by_side:
            continue
        event_id = str(event.get('id') or '')
        start = parse_instant(event.get('date'))
        if not event_id.isdigit() or start is None:
            continue
        home, away = _team(by_side['home']), _team(by_side['away'])
        if not home['name'] or not away['name'] or home['name'] == away['name']:
            continue
        status = event.get('status') or {}
        state = str((status.get('type') or {}).get('state') or '').lower()
        if state not in ('pre', 'in', 'post'):
            state = 'unknown'
        result.append({
            'event_key': f'espn:{league}:{event_id}', 'provider_event_id': event_id,
            'league': league, 'start_utc': start.isoformat(), 'day_requested': request_day.isoformat(),
            'status': {'pre': 'UPCOMING', 'in': 'LIVE', 'post': 'FINAL'}.get(state, 'UNKNOWN'),
            'detail': str((status.get('type') or {}).get('shortDetail') or (status.get('type') or {}).get('description') or ''),
            'home': home, 'away': away, 'source': source, 'retrieved_at_utc': retrieved_at_utc,
            'season_year': (event.get('season') or {}).get('year'),
            'week': (event.get('week') or {}).get('number') if isinstance(event.get('week'), dict) else
                    ((payload.get('week') or {}).get('number') if isinstance(payload.get('week'),dict) else None),
            'roster_verified': False, 'market_available': False,
        })
    return result


def fetch_day(league: str, day: date, *, timeout: int = 14) -> tuple[list[dict], dict]:
    if league not in LEAGUES or not isinstance(day, date):
        raise ValueError('Invalid league or date')
    family, tag = LEAGUES[league]
    params = {'dates': day.strftime('%Y%m%d'), 'limit': '500'}
    if league == 'College football':
        params['groups'] = '80'  # ESPN's current FBS grouping; unofficial.
    url = f'https://site.api.espn.com/apis/site/v2/sports/{family}/{tag}/scoreboard?{urlencode(params)}'
    request = Request(url, headers={'User-Agent': 'BTAResearchDashboard/0.8', 'Accept': 'application/json'})
    with urlopen(request, timeout=timeout) as response:
        if response.url.split('/')[2] != 'site.api.espn.com':
            raise ValueError('Unexpected ESPN redirect')
        raw = response.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError('Scoreboard response too large')
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise ValueError('Scoreboard response not JSON') from exc
    stamp = utcstamp()
    events = parse_scoreboard(payload, league, request_day=day, source=url, retrieved_at_utc=stamp)
    return events, {'source': url, 'retrieved_at_utc': stamp, 'count': len(events),
                    'caution': 'ESPN JSON schedule feed is undocumented; events may be missing or delayed.'}


def collect(league: str, days: list[date], fetcher=fetch_day) -> dict:
    events = {}
    failed = []
    sources = []
    for day in days:
        try:
            rows, meta = fetcher(league, day)
            sources.append(meta)
            for row in rows:
                key = row['event_key']
                if key in events and events[key]['start_utc'] != row['start_utc']:
                    failed.append({'date': day.isoformat(), 'error': f'Conflicting start for {key}'})
                else:
                    events[key] = row
        except (OSError, ValueError, KeyError, TypeError) as exc:
            failed.append({'date': day.isoformat(), 'error': type(exc).__name__})
    records = sorted(events.values(), key=lambda item: (item['start_utc'], item['event_key']))
    return {'league': league, 'games': records, 'source_logs': sources, 'errors': failed,
            'complete': len(failed) == 0, 'retrieved_at_utc': utcstamp()}


def game_counts(events: list[dict]) -> dict:
    return {s: sum(1 for r in events if r['status'] == s) for s in ('UPCOMING','LIVE','FINAL','UNKNOWN')}


def next_days(local_today: date, *, horizon: int = 3) -> list[date]:
    if not 1 <= horizon <= 14:
        raise ValueError('horizon 1-14 days')
    return [local_today + timedelta(days=i) for i in range(horizon)]


def augment_nba_official_score(events: list[dict], official: dict, *, local_day: date) -> tuple[list[dict], int]:
    """Prefer official NBA scoreboard for same-day scores/status where uniquely matched.

    Does not change ESPN event ID, start time, opponent names or pregame roster
    verification. If there is an ambiguous NBA match, retain ESPN data.
    """
    if official.get('status') != 'OK' or official.get('date') != local_day.isoformat():
        return events,0
    pairs={}
    for o in official.get('games',[]):
        if not isinstance(o,dict):continue
        key=(str(o.get('home','')).upper(),str(o.get('away','')).upper())
        if all(key):pairs.setdefault(key,[]).append(o)
    espn_pair_counts={}
    for item in events:
        if item.get('league')=='NBA':
            k=(item['home'].get('abbr'),item['away'].get('abbr'))
            espn_pair_counts[k]=espn_pair_counts.get(k,0)+1
    merged=[];updated=0
    for e in events:
        if e.get('league')!='NBA':merged.append(e);continue
        etime=parse_instant(e.get('start_utc'))
        if etime is None:merged.append(e);continue
        from zoneinfo import ZoneInfo
        if etime.astimezone(ZoneInfo('America/New_York')).date()!=local_day:
            merged.append(e);continue
        key=(e['home'].get('abbr'),e['away'].get('abbr'))
        options=pairs.get(key,[])
        if len(options)!=1 or espn_pair_counts.get(key)!=1:merged.append(e);continue
        o=options[0]
        code=o.get('status_code')
        if code not in (1,2,3):merged.append(e);continue
        clone={**e,'home':{**e['home']},'away':{**e['away']}}
        clone['status']={1:'UPCOMING',2:'LIVE',3:'FINAL'}[code]
        clone['detail']=o.get('state') or clone['detail']
        clone['home']['score']=str(o['home_score']) if o.get('home_score') is not None else None
        clone['away']['score']=str(o['away_score']) if o.get('away_score') is not None else None
        clone['score_authority']='NBA OFFICIAL LIVE CDN'
        clone['score_retrieved_at_utc']=official.get('retrieved_at_utc')
        merged.append(clone);updated+=1
    return merged,updated
