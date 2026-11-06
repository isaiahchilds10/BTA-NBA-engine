"""HTTPS-only configured provider gateway. No scrape-of-bookmaker/unguarded URLs.

A successful HTTP request is only proof of the provider response, NOT of an
official sportsbook, league, or cryptographic signature. User must supply
licensed/allowed data endpoint and verify their contractual usage rights.
"""
from __future__ import annotations
import json
from urllib.parse import urlparse,urlencode
from urllib.request import Request,urlopen


def read_json(url, *, token='', allowed_hosts, params=None, max_bytes=8_000_000, timeout=14):
    parts=urlparse(url)
    allow={str(host).lower() for host in allowed_hosts}
    if (parts.scheme!='https' or not parts.hostname or parts.hostname.lower() not in allow
        or parts.username or parts.password or parts.fragment or parts.port not in (None,443)):
        raise ValueError('Provider host is not on allowlist')
    if params:
        if any(k in ('apiKey','key','token') for k in params):
            raise ValueError('Never put credentials in query parameters')
        sep='&' if parts.query else '?'
        url+=sep+urlencode(params)
    headers={'Accept':'application/json','User-Agent':'BTA-Research/1.1'}
    if token:headers['Authorization']=f'Bearer {token}'
    req=Request(url,headers=headers)
    with urlopen(req,timeout=timeout) as resp:
        final=urlparse(resp.geturl())
        if final.scheme!='https' or final.hostname not in allow:
            raise ValueError('Provider redirected outside allowlist')
        raw=resp.read(max_bytes+1)
    if len(raw)>max_bytes:raise ValueError('Provider response too large')
    obj=json.loads(raw)
    if not isinstance(obj,(dict,list)):raise ValueError('Unexpected provider response type')
    return obj


def cfbd_roster(*,year:int,team:str,api_key:str,fetcher=read_json):
    """CFBD returns listed players for named season; NOT game-day availability."""
    if not 2004<=year<=2100 or not team.strip() or not api_key:
        return {'status':'CONFIGURATION_REQUIRED','players':[]}
    endpoint='https://api.collegefootballdata.com/roster'
    try:
        records=fetcher(endpoint,token=api_key,allowed_hosts={'api.collegefootballdata.com'},
                        params={'year':year,'team':team})
    except (OSError,ValueError,TypeError,KeyError) as exc:
        return {'status':'PROVIDER_ERROR','error_type':type(exc).__name__,'players':[]}
    if not isinstance(records,list):return {'status':'SCHEMA_ERROR','players':[]}
    players=[]
    for r in records:
        if not isinstance(r,dict):continue
        ident=r.get('id') or r.get('athleteId') or r.get('playerId')
        name=r.get('name') or (' '.join(str(r.get(k) or '') for k in ('firstName','lastName'))).strip()
        if ident is None or not name:continue
        players.append({'player_id':str(ident),'name':name,'position':r.get('position'),
                        'team':r.get('team') or team})
    return {'status':'ROSTER_LIST_ONLY' if players else 'NO_MATCHING_ROSTER',
            'players':players,'year':year,'team':team,'source':endpoint,
            'note':'Season roster has no confirmed lineup, game status or daily injury availability.'}
