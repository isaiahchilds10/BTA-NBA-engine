"""Optional live moneyline quotes from the-odds-api.com; user supplies own free key."""
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SPORTS = {
    'NBA': 'basketball_nba',
    'NFL': 'americanfootball_nfl',
    'MLB': 'baseball_mlb',
    'NHL': 'icehockey_nhl',
    'College football': 'americanfootball_ncaaf',
    'College basketball': 'basketball_ncaab',
    'English Premier League': 'soccer_epl',
    'MLS': 'soccer_usa_mls',
}


def get_moneylines(api_key: str, sport_key: str):
    if not api_key.strip():
        raise ValueError('Enter an API key to fetch odds.')
    if sport_key not in SPORTS.values():
        raise ValueError('Unknown sport key.')
    url = 'https://api.the-odds-api.com/v4/sports/' + sport_key + '/odds/?' + urlencode({
        'apiKey': api_key.strip(), 'regions': 'us', 'markets': 'h2h', 'oddsFormat': 'american'
    })
    try:
        with urlopen(Request(url, headers={'User-Agent': 'BTA-Paper-Research/0.1'}), timeout=15) as response:
            payload = json.load(response)
            remaining = response.headers.get('x-requests-remaining', 'unknown')
    except HTTPError as exc:
        message = exc.read(400).decode('utf-8', errors='replace')
        raise ValueError(f'Odds provider error {exc.code}: {message}') from exc
    except (URLError, TimeoutError) as exc:
        raise ValueError(f'Network request failed: {exc}') from exc
    if not isinstance(payload, list):
        raise ValueError('Unexpected odds provider response format.')
    captured_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for event in payload:
        event_id = str(event.get('id', ''))
        game = f"{event.get('away_team', '?')} at {event.get('home_team', '?')}"
        for book in event.get('bookmakers', []):
            for market in book.get('markets', []):
                if market.get('key') != 'h2h':
                    continue
                for outcome in market.get('outcomes', []):
                    price = outcome.get('price')
                    if not isinstance(price, int) or -100 < price < 100:
                        continue
                    rows.append({
                        'event_id': event_id,
                        'game': game,
                        'start_utc': str(event.get('commence_time', '')),
                        'sport_key': sport_key,
                        'selection': str(outcome.get('name', '')),
                        'american_odds': price,
                        'bookmaker': str(book.get('title', '?')),
                        'bookmaker_update_utc': str(market.get('last_update') or book.get('last_update') or ''),
                        'captured_at_utc': captured_at,
                    })
    return rows, remaining
