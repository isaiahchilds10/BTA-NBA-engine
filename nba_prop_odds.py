"""Optional event-specific NBA props via the-odds-api.com (hyphens).

API usage may burn free credits; requests are on explicit button press only.
Not affiliated with the-odds-api.com and does not place wagers.
"""
import json
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE='https://api.the-odds-api.com/v4/sports/basketball_nba'
MARKETS={'player_points':'points','player_rebounds':'rebounds','player_assists':'assists'}


def _get(url):
    try:
        with urlopen(Request(url,headers={'User-Agent':'BTA-Research-Only/0.2'}),timeout=15) as resp:
            data=json.load(resp)
            usage={'remaining':resp.headers.get('x-requests-remaining','?'),
                   'last':resp.headers.get('x-requests-last','?')}
        return data,usage
    except HTTPError as e:
        raise RuntimeError(f'Odds API returned HTTP {e.code}. Check your key, usage quota, and plan.') from e
    except (URLError,TimeoutError) as e:
        raise RuntimeError(f'Odds API network error: {e}') from e


def get_events(key):
    if not key.strip(): raise ValueError('Enter an Odds API key.')
    url=BASE+'/events?'+urlencode({'apiKey':key.strip()})
    events,usage=_get(url)
    if not isinstance(events,list):raise RuntimeError('Unexpected events response.')
    return [{'id':str(e.get('id','')),'game':f"{e.get('away_team','?')} at {e.get('home_team','?')}",
             'start_utc':str(e.get('commence_time',''))} for e in events],usage


def get_event_props(key, event_id, markets=tuple(MARKETS)):
    if not key.strip():raise ValueError('Enter an Odds API key.')
    if not event_id or not all(c.isalnum() or c in '-_' for c in event_id):
        raise ValueError('Invalid event ID.')
    if not markets or any(m not in MARKETS for m in markets):
        raise ValueError('Invalid requested markets.')
    url=BASE+'/events/'+quote(event_id,safe='')+'/odds?'+urlencode({
        'apiKey':key.strip(),'regions':'us',
        'markets':','.join(markets),'oddsFormat':'american'})
    event,usage=_get(url)
    if not isinstance(event,dict): raise RuntimeError('Unexpected event odds response.')
    best={}
    for book in event.get('bookmakers',[]):
        for market in book.get('markets',[]):
            stat=MARKETS.get(market.get('key'))
            if not stat:continue
            for outcome in market.get('outcomes',[]):
                side=str(outcome.get('name','')).lower()
                if side not in ('over','under'):continue
                player=str(outcome.get('description','')).strip()
                try:
                    line=float(outcome['point']); price=int(outcome['price'])
                except (KeyError,ValueError,TypeError):continue
                if not player or line < 0 or -100 < price < 100:continue
                k=(player.casefold(),stat,side,line)
                obj={'player':player,'stat':stat,'side':side,'line':line,'odds':price,
                     'book':book.get('title','?'),'event_id':event_id,
                     'game':f"{event.get('away_team','?')} at {event.get('home_team','?')}",
                     'start_utc':event.get('commence_time',''),
                     'market_updated_utc':market.get('last_update') or book.get('last_update','')}
                if k not in best or price>best[k]['odds']:
                    best[k]=obj
    return list(best.values()),usage
