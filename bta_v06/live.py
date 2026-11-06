"""Bounded, attributed live sports endpoints, each with fail-closed schema checks.

Providers:
- Official NBA live CDN, current-day scores and per-game box scores.
- Unofficial ESPN scoreboard JSON for NFL / NCAA D-I football *schedule only*.
- Existing v0.5 adapters for season stats and injury reports, on demand.

No real-time betting odds, lineup verification, or probabilistic edges are claimed.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.request import Request, urlopen

NBA_SCOREBOARD_URL = 'https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json'
NBA_BOXSCORE_PREFIX = 'https://cdn.nba.com/static/json/liveData/boxscore/boxscore_'
ESPN_URLS = {
    'NBA': 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard',
    'NFL': 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard',
    'College football': 'https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard',
}
ALLOWED = {'cdn.nba.com', 'site.api.espn.com'}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch_json(url: str, *, max_bytes: int = 3_000_000, timeout: int = 15) -> dict:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ALLOWED:
        raise ValueError('Unexpected provider URL')
    if not (1_000 <= max_bytes <= 6_000_000):
        raise ValueError('Invalid response size limit')
    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; BTAResearchMonitor/0.6; research)',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    if parsed.hostname == 'cdn.nba.com':
        headers.update({'Referer': 'https://www.nba.com/', 'Origin': 'https://www.nba.com'})
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as result:
        if urlparse(result.url).hostname not in ALLOWED:
            raise ValueError('Provider redirected outside approved domains')
        payload = result.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError('Provider response is unexpectedly large')
    try:
        obj = json.loads(payload.decode('utf-8-sig'))
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Provider did not return valid JSON') from exc
    if not isinstance(obj, dict):
        raise ValueError('Unexpected JSON structure')
    return obj


def parse_nba_scoreboard(obj: dict) -> dict:
    board = obj.get('scoreboard')
    if not isinstance(board, dict) or not isinstance(board.get('games'), list):
        raise ValueError('NBA scoreboard format changed')
    day = str(board.get('gameDate', ''))[:10]
    if not re.fullmatch(r'\d{4}-\d\d-\d\d', day):
        raise ValueError('NBA scoreboard date missing')
    games = []
    for item in board['games']:
        home, away = item.get('homeTeam'), item.get('awayTeam')
        game_id = str(item.get('gameId', ''))
        if not isinstance(home, dict) or not isinstance(away, dict) or not re.fullmatch(r'\d{10}', game_id):
            continue
        games.append({
            'id': game_id,
            'date_utc': str(item.get('gameTimeUTC') or ''),
            'state': str(item.get('gameStatusText') or ''),
            'status_code': item.get('gameStatus'),
            'home': str(home.get('teamTricode') or ''),
            'away': str(away.get('teamTricode') or ''),
            'home_score': home.get('score'),
            'away_score': away.get('score'),
        })
    return {'date': day, 'games': games, 'games_count': len(games)}


def nba_today() -> dict:
    obj = fetch_json(NBA_SCOREBOARD_URL)
    result = parse_nba_scoreboard(obj)
    return {'status': 'OK', 'source': NBA_SCOREBOARD_URL, 'retrieved_at_utc': utc_now(), **result}


def parse_nba_boxscore(obj: dict, game_id: str) -> dict:
    if not re.fullmatch(r'\d{10}', game_id):
        raise ValueError('Invalid NBA game ID')
    game = obj.get('game')
    if not isinstance(game, dict) or str(game.get('gameId')) != game_id:
        raise ValueError('NBA box score missing or game ID mismatch')
    players = []
    for side in ('homeTeam', 'awayTeam'):
        team = game.get(side) or {}
        if not isinstance(team, dict):
            continue
        for player in team.get('players') or []:
            if not isinstance(player, dict):
                continue
            stats = player.get('statistics') or {}
            if not isinstance(stats, dict):
                stats = {}
            players.append({
                'person_id': str(player.get('personId') or ''),
                'name': str(player.get('name') or ''),
                'team': str(team.get('teamTricode') or ''),
                'played': player.get('played'),
                'starter': player.get('starter'),
                'minutes': str(stats.get('minutes') or stats.get('minutesCalculated') or ''),
                'points': stats.get('points'),
                'rebounds': stats.get('reboundsTotal'),
                'assists': stats.get('assists'),
            })
    return {'game_id': game_id, 'game_status': game.get('gameStatus'),
            'game_status_text': str(game.get('gameStatusText') or ''), 'players': players}


def nba_boxscore(game_id: str) -> dict:
    if not re.fullmatch(r'\d{10}', str(game_id)):
        raise ValueError('Invalid NBA game ID')
    url = f'{NBA_BOXSCORE_PREFIX}{game_id}.json'
    parsed = parse_nba_boxscore(fetch_json(url, max_bytes=5_000_000), str(game_id))
    return {'source': url, 'retrieved_at_utc': utc_now(), 'status': 'OK', **parsed}


def parse_espn_scoreboard(obj: dict) -> dict:
    events = obj.get('events')
    if not isinstance(events, list):
        raise ValueError('ESPN scoreboard format changed')
    games=[]
    for event in events:
        if not isinstance(event, dict):
            continue
        comp = (event.get('competitions') or [{}])[0]
        competitors = comp.get('competitors', []) if isinstance(comp, dict) else []
        by_side = {c.get('homeAway'): c for c in competitors if isinstance(c, dict)}
        home = by_side.get('home', {}); away = by_side.get('away', {})
        if not home or not away:
            continue
        games.append({
            'id': str(event.get('id') or ''), 'date_utc': str(event.get('date') or ''),
            'state': str(((event.get('status') or {}).get('type') or {}).get('description') or ''),
            'home': str((home.get('team') or {}).get('displayName') or ''),
            'away': str((away.get('team') or {}).get('displayName') or ''),
            'home_score': home.get('score'), 'away_score': away.get('score')
        })
    return {'games': games, 'games_count': len(games)}


def espn_schedule(league: str, day: str) -> dict:
    if league not in ESPN_URLS or not re.fullmatch(r'20\d{6}', day):
        raise ValueError('Unsupported league or date; YYYYMMDD required')
    url = f'{ESPN_URLS[league]}?dates={day}'
    data = parse_espn_scoreboard(fetch_json(url))
    return {'status': 'OK', 'source': url, 'retrieved_at_utc': utc_now(), 'date': day, **data,
            'provider_note': 'Unofficial ESPN JSON endpoint; not a verified lineup/injury provider'}



def nba_monitor(*, official_fetch=nba_today, espn_fetch=espn_schedule) -> dict:
    """Use official NBA score data when possible; visibly mark ESPN fallback.

    A fallback does not provide official NBA player box scores or lineup proof.
    """
    try:
        record = official_fetch()
        record['provider_quality'] = 'NBA OFFICIAL LIVE CDN'
        return record
    except Exception as exc:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d')
        fallback = espn_fetch('NBA', stamp)
        fallback['provider_quality'] = 'UNOFFICIAL ESPN FALLBACK'
        fallback['provider_note'] = 'Official NBA live CDN inaccessible; no official box score lookup from ESPN event ID'
        fallback['official_error_type'] = type(exc).__name__
        return fallback

def gate_freshness(retrieved_at: str, now: datetime, max_age_minutes: int) -> str:
    try:
        parsed = datetime.fromisoformat(retrieved_at.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return 'UNVERIFIED'
        age = (now.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()
        return 'CURRENT SNAPSHOT' if -90 <= age <= max_age_minutes*60 else 'STALE / UNVERIFIED'
    except (TypeError, ValueError):
        return 'UNVERIFIED'
