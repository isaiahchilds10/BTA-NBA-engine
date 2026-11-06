"""Optional Betting Data API ingestion. No sportsbook login or automated betting.

Prices are bookmaker *offers*, not model probability or high-confidence picks.
Tier access: Free NBA/NFL h2h; wider markets Pro; player props Business,
per provider docs as of 2026-10-30 (terms can change).
"""
from __future__ import annotations
import json
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .schedule import parse_instant, utcstamp

SPORT_KEYS = {'NBA':'basketball_nba','NFL':'americanfootball_nfl','College football':'americanfootball_ncaaf'}
NBA_STATS = {'player_points':'Points', 'player_rebounds':'Rebounds', 'player_assists':'Assists'}
NFL_STATS = {'player_pass_yds':'passing_yards','player_rush_yds':'rushing_yards',
             'player_receptions':'receptions','player_reception_yds':'receiving_yards',
             'player_pass_attempts':'attempts', 'player_rush_attempts':'carries',
             'player_pass_tds':'passing_tds'}
SUPPORTED_PROP_STATS = {'NBA': NBA_STATS, 'NFL': NFL_STATS, 'College football': {}}


def _name(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', (name or '').casefold())


def _number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def fetch_markets(league: str, api_key: str, *, props=False, event_id: str | None=None,
                  only_book: str | None='fanduel', bulk: bool=False) -> tuple[list[dict], dict]:
    """A few API requests on demand; UI caches this to avoid burning quotas."""
    if league not in SPORT_KEYS or not api_key or not isinstance(api_key, str):
        raise ValueError('Supported league and a provider API key required')
    if props and league == 'College football':
        return [], {'status':'NOT REQUESTED','reason':'CFB is restricted to ML/spread/total in this BTA system'}
    if props and not event_id and not bulk:
        raise ValueError('Explicitly allow a bulk player-prop query (within provider live window)')
    if event_id is not None and not re.fullmatch(r'[\w-]{1,100}', event_id):
        raise ValueError('Invalid event id')
    if only_book is not None and only_book not in {'fanduel', 'draftkings', 'betmgm'}:
        raise ValueError('Unsupported preferred bookmaker')
    params = {'sport_key': SPORT_KEYS[league]}
    if event_id:
        params['event_id'] = event_id
    if not props:
        params['markets'] = 'h2h,spreads,totals'
    if only_book:
        params['bookmakers'] = only_book
    path = 'props' if props else 'odds'
    url = f'https://api.bettingdataapi.com/{path}/?{urlencode(params)}'
    req = Request(url, headers={'x-api-key':api_key, 'Accept':'application/json', 'User-Agent':'BTAResearch/0.8'})
    with urlopen(req, timeout=17) as res:
        if res.url.split('/')[2] != 'api.bettingdataapi.com':
            raise ValueError('Unexpected betting data redirect')
        raw = res.read(6_000_001)
    if len(raw) > 6_000_000:
        raise ValueError('Betting API response too large')
    try:
        doc=json.loads(raw)
    except ValueError as exc:
        raise ValueError('Betting API did not return JSON') from exc
    if not isinstance(doc, dict) or doc.get('success') is not True or not isinstance(doc.get('data'), list):
        raise ValueError('Provider error or unsupported subscription tier')
    records = parse_offers(doc['data'], league=league, only_book=only_book, props=props)
    return records, {'source':'https://api.bettingdataapi.com/'+path+'/', 'retrieved_at_utc':utcstamp(),
                     'market_count':len(records),'props':props,
                     'note':'Offers are provider snapshots; not verified current FanDuel screens or model predictions.'}


def parse_offers(events: list, *, league: str, only_book: str | None = 'fanduel', props=False) -> list[dict]:
    if league not in SPORT_KEYS:
        raise ValueError('Invalid league')
    offers=[]
    for event in events:
        if not isinstance(event,dict):
            continue
        provider_id=str(event.get('event_id') or '')
        start=parse_instant(event.get('start_time'))
        home=str(event.get('home_team') or '');away=str(event.get('away_team') or '')
        if not provider_id or not start or not home or not away:
            continue
        books = event.get('books') or []
        # For API versions nesting markets[].books, accept only documented-equivalent structures.
        if not books and isinstance(event.get('markets'),list):
            for m in event['markets']:
                if not isinstance(m,dict): continue
                for b in m.get('books') or []:
                    if isinstance(b,dict):books.append({**b,'market':m.get('market')})
        for book in books:
            if not isinstance(book,dict):continue
            bookmaker=str(book.get('book') or '').casefold()
            if only_book and bookmaker != only_book: continue
            market=str(book.get('market') or '')
            if props:
                if market not in SUPPORTED_PROP_STATS[league]: continue
            elif market not in {'h2h','spreads','totals'}:
                continue
            updated=str(book.get('updated_at') or '')
            for outcome in book.get('outcomes') or []:
                if not isinstance(outcome,dict):continue
                price=_number(outcome.get('price'))
                if price is None or not (abs(price)>=100 and abs(price)<=100000) or price==0:
                    continue
                player=str(outcome.get('description') or '') if props else ''
                side=str(outcome.get('name') or '').strip()
                line=_number(outcome.get('point'))
                if props and (not player or line is None or side.lower() not in ('over','under')):
                    continue
                if not props and market in {'spreads','totals'} and line is None:
                    continue
                offers.append({
                    'provider_event_id':provider_id,'league':league,'start_utc':start.isoformat(),
                    'home_name':home,'away_name':away,'bookmaker':bookmaker, 'market':market,
                    'player':player,'selection':side,'line':line,'american_odds':int(price),
                    'book_updated_utc':updated,'research_label':'MARKET OFFER ONLY',
                    'provider':'Betting Data API','player_props':props,
                })
    return offers


def match_offers(slate: list[dict], offers: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    """Match by exact normalized team names plus start window; fail closed on ambiguity."""
    matches={r['event_key']:[] for r in slate}
    unmatched=[]
    for offer in offers:
        st=parse_instant(offer.get('start_utc'))
        candidates=[]
        for game in slate:
            start=parse_instant(game.get('start_utc'))
            if game.get('league')!=offer.get('league') or st is None or start is None:
                continue
            if abs((start-st).total_seconds())>4*3600:continue
            if _name(game['home']['name'])==_name(offer['home_name']) and _name(game['away']['name'])==_name(offer['away_name']):
                candidates.append(game)
        if len(candidates)==1:
            matches[candidates[0]['event_key']].append({**offer, 'match_basis':'Exact normalized home/away name, start ±4h',
                                                        'provider_ids_not_equal':True})
        else:
            unmatched.append({'offer':offer,'reason':'No strict name/time match' if not candidates else 'Ambiguous multiple matches'})
    return matches,unmatched


def book_quote_status(offer: dict, *, now: datetime | None=None, max_age_minutes: int = 180) -> str:
    checked=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stamp=parse_instant(offer.get('book_updated_utc'))
    if stamp is None:return 'UNKNOWN QUOTE TIME'
    age=(checked-stamp).total_seconds()/60
    if age < -5:return 'INVALID FUTURE QUOTE'
    return 'RECENT QUOTE' if age<=max_age_minutes else 'STALE QUOTE'
