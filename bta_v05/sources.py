"""Bounded, non-secret source adapters for BTA v0.5.

Important: an available source is not the same as a verified active player.
Network errors raise explicit exceptions; we do not reuse synthetic data.
Do not import Streamlit in this module, so it can be tested offline.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone, date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urlencode
from urllib.request import Request, urlopen

_today = date.today()
_nba_start = _today.year if _today.month >= 7 else _today.year-1
NBA_INJURY_INDEX = f"https://official.nba.com/nba-injury-report-{_nba_start}-{(_nba_start+1)%100:02d}-season/"
NFL_RELEASE = "https://github.com/nflverse/nflverse-data/releases/download"
CFBD_GAMES = "https://api.collegefootballdata.com/games"
NBA_REPOSITORY_API = "https://api.github.com/repos/xtheredshirtx/fanduel-player-data/contents/NBA/csv"


def _download(url: str, max_bytes: int, *, accept: str = '*/*', headers: dict | None = None) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.hostname not in {
        'github.com', 'raw.githubusercontent.com', 'api.github.com',
        'official.nba.com', 'ak-static.cms.nba.com', 'api.collegefootballdata.com', 'site.api.espn.com'
    }:
        raise ValueError('Unexpected provider domain; refusing arbitrary URL fetch')
    req = Request(url, headers={'User-Agent': 'BTA-Research/0.5 (research only)',
                                'Accept': accept, **(headers or {})})
    with urlopen(req, timeout=20) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError('Provider response exceeds safe size')
    return data


def _csv(raw: bytes, required: set[str], *, max_rows: int = 150_000) -> list[dict]:
    doc = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if not doc.fieldnames or not required.issubset(set(doc.fieldnames)):
        raise ValueError(f'Source schema changed: missing required CSV fields: {required - set(doc.fieldnames or [])}')
    result = []
    for row in doc:
        if len(result) >= max_rows:
            raise ValueError('Too many source rows')
        if None in row:  # malformed extra fields
            raise ValueError('Malformed CSV: unexpected extra cells')
        result.append(row)
    if not result:
        raise ValueError('Empty provider CSV')
    return result


def nfl_injury_reports(season: int) -> tuple[list[dict], dict]:
    if not 2012 <= season <= 2100:
        raise ValueError('Invalid NFL season')
    url = f'{NFL_RELEASE}/injuries/injuries_{season}.csv'
    rows = _csv(_download(url, 18_000_000), {'season', 'week', 'team', 'full_name', 'report_status', 'date_modified'})
    # There may be several dated updates for the same player-week. Later module selects latest.
    return rows, {'source': url, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(), 'rows': len(rows)}


def nfl_snap_counts(season: int) -> tuple[list[dict], dict]:
    if not 2012 <= season <= 2100:
        raise ValueError('Invalid NFL season')
    url = f'{NFL_RELEASE}/snap_counts/snap_counts_{season}.csv'
    rows = _csv(_download(url, 22_000_000),
                {'season','week','player','team','opponent','offense_snaps','offense_pct'})
    return rows, {'source': url, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(), 'rows': len(rows)}


def cfbd_fbs_games(year: int, key: str) -> tuple[list[dict], dict]:
    if not 2000 <= year <= 2100:
        raise ValueError('Invalid college season')
    if not key or not key.strip():
        raise ValueError('CFBD_API_KEY missing')
    url = f'{CFBD_GAMES}?{urlencode({"year":year,"classification":"fbs","seasonType":"regular"})}'
    result = json.loads(_download(url, 12_000_000,
                                 accept='application/json',
                                 headers={'Authorization': f'Bearer {key.strip()}'}) .decode('utf-8'))
    if not isinstance(result, list):
        raise ValueError('CFBD changed response format')
    return result, {'source': url, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(), 'rows': len(result)}


class _InjuryLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        href = dict(attrs).get('href', '')
        absolute = urljoin(NBA_INJURY_INDEX, href)
        parsed = urlparse(absolute)
        if parsed.hostname == 'ak-static.cms.nba.com' and re.search(r'Injury-Report_\d{4}-\d\d-\d\d_\d\d_\d\d[AP]M\.pdf', parsed.path, re.I):
            self.urls.append(absolute)


def select_latest_official_nba_pdf(html: str) -> tuple[str, datetime]:
    """Choose link by parsed publication timestamp, never lexicographic time."""
    parser = _InjuryLinks()
    parser.feed(html)
    items = []
    for url in parser.urls:
        match = re.search(r'Injury-Report_(\d{4}-\d\d-\d\d)_(\d\d_\d\d[AP]M)\.pdf', url, re.I)
        if match:
            try:
                published = datetime.strptime(match.group(1)+' '+match.group(2), '%Y-%m-%d %I_%M%p')
                items.append((published, url))
            except ValueError:
                continue
    if not items:
        raise ValueError('NBA official report link not found: source format may have changed')
    return max(items, key=lambda x: x[0])[1], max(items, key=lambda x: x[0])[0]


def latest_nba_official_report() -> tuple[str, dict]:
    """Read current official NBA report PDF, without guessing unlisted player statuses.

    Reports can be incomplete because teams have NOT YET SUBMITTED. The returned
    text must NOT be interpreted as a roster or verified active-player list.
    """
    html = _download(NBA_INJURY_INDEX, 5_000_000, accept='text/html').decode('utf-8', errors='replace')
    pdf_url, publication = select_latest_official_nba_pdf(html)
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError('Install pypdf (see requirements addition)') from exc
    raw = _download(pdf_url, 12_000_000, accept='application/pdf')
    if not raw.startswith(b'%PDF'):
        raise ValueError('NBA source did not return PDF data')
    reader = PdfReader(io.BytesIO(raw), strict=False)
    if not 1 <= len(reader.pages) <= 40:
        raise ValueError('Unexpected NBA injury report length')
    text = '\n'.join((page.extract_text() or '') for page in reader.pages)
    if 'Injury Report' not in text or 'Current Status' not in text or len(text) < 70:
        raise ValueError('Could not reliably extract official NBA injury report')
    return text, {'source': pdf_url, 'report_published_et_naive': publication.isoformat(),
                  'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                  'not_submitted_sections': text.upper().count('NOT YET SUBMITTED')}


def newest_nba_community_logs(season: str) -> tuple[list[dict], dict]:
    """Obtain current published snapshot, not a stale local CSV.

    Community-maintained stats are not an official injury or lineup source.
    """
    if not re.fullmatch(r'20\d{2}-\d{2}', season):
        raise ValueError('Invalid NBA season')
    contents = json.loads(_download(NBA_REPOSITORY_API, 2_000_000, accept='application/json').decode('utf-8'))
    if not isinstance(contents, list):
        raise ValueError('GitHub contents API did not return file list')
    matches = []
    regex = re.compile(rf'NBA_players_game_log_{re.escape(season)}_as_of_(\d{{4}}-\d\d-\d\d)\.csv')
    for item in contents:
        if item.get('type') == 'file':
            m = regex.fullmatch(item.get('name',''))
            if m:
                try:
                    datetime.strptime(m.group(1), '%Y-%m-%d')
                    matches.append((m.group(1), item['name']))
                except (ValueError, KeyError):
                    pass
    if not matches:
        raise ValueError('No published NBA player game-log snapshot for this season')
    asof, name = max(matches)
    from urllib.parse import quote
    url = f'https://raw.githubusercontent.com/xtheredshirtx/fanduel-player-data/main/NBA/csv/{quote(name)}'
    rows = _csv(_download(url, 16_000_000), {'Date','Player','ID','Team','Opp','Minutes','Points','Rebounds','Assists'},max_rows=75_000)
    return rows, {'source': url, 'snapshot': asof, 'rows': len(rows),
                  'retrieved_at_utc': datetime.now(timezone.utc).isoformat()}


def nfl_weekly_player_stats(season: int) -> tuple[list[dict], dict]:
    """Active NFL stats_player weekly release, not legacy frozen player_stats."""
    if not 1999 <= season <= 2100:
        raise ValueError('Invalid season')
    url = f'{NFL_RELEASE}/stats_player/stats_player_week_{season}.csv'
    rows=_csv(_download(url, 44_000_000), {'week','passing_yards','rushing_yards','receiving_yards'}, max_rows=100_000)
    return rows, {'source':url,'rows':len(rows),'retrieved_at_utc':datetime.now(timezone.utc).isoformat()}


def espn_day_schedule(sport: str, league: str, day: str) -> tuple[list[dict], dict]:
    """Unofficial schedule feed. Teams are game participants, NOT confirmed starters."""
    if (sport,league) not in {('basketball','nba'),('football','nfl'),('football','college-football')}:
        raise ValueError('Unsupported schedule type')
    if not re.fullmatch(r'20\d{6}',day):
        raise ValueError('Provide YYYYMMDD')
    url=f'https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard?dates={day}'
    obj=json.loads(_download(url,3_000_000,accept='application/json').decode('utf-8'))
    if not isinstance(obj,dict) or not isinstance(obj.get('events'),list):
        raise ValueError('Scoreboard schema changed')
    events=[]
    for game in obj['events']:
        competitions=game.get('competitions') or []
        if not competitions:continue
        competitors=competitions[0].get('competitors') or []
        home=next((x for x in competitors if x.get('homeAway')=='home'),None)
        away=next((x for x in competitors if x.get('homeAway')=='away'),None)
        if not home or not away:continue
        def fmt(x):
            return {'name':str(x.get('team',{}).get('displayName') or ''),
                    'abbrev':str(x.get('team',{}).get('abbreviation') or '').upper()}
        events.append({'id':str(game.get('id') or ''),'start':str(game.get('date') or ''),
                       'status':str((game.get('status') or {}).get('type',{}).get('state') or ''),
                       'home':fmt(home),'away':fmt(away)})
    return events,{'source':url,'retrieved_at_utc':datetime.now(timezone.utc).isoformat()}


def nfl_complete_schedules() -> tuple[list[dict], dict]:
    """Published NFL schedule/results incl. historical games (not live active lists)."""
    url=f'{NFL_RELEASE}/schedules/games.csv'
    rows=_csv(_download(url,12_000_000),
              {'game_id','season','week','gameday','home_team','away_team','home_score','away_score'},
              max_rows=15_000)
    return rows, {'source':url,'rows':len(rows),'retrieved_at_utc':datetime.now(timezone.utc).isoformat()}
