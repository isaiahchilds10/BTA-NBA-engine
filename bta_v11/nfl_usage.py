"""Separates actual charted NFL routes from snaps and a route proxy.

nflverse snap-count releases can lag game completion and are not live snap counts.
Free nflverse participation charting is not a complete in-season routes source.
"""
from __future__ import annotations
from statistics import median
from .common import number


def historical_usage(*,player_id:str,team:str,season:int,week:int,
                     snap_rows:list[dict],route_rows:list[dict]|None=None,
                     min_snap_games:int=3,min_route_games:int=3)->dict:
    if not player_id or not team or not (2000<=season<=2100 and 1<=week<=25):
        return {'status':'INVALID_IDENTITY'}
    snap_games={};used_names=set()
    for r in snap_rows:
        if str(r.get('season'))!=str(season) or str(r.get('team')).upper()!=team.upper():continue
        try:w=int(r.get('week'))
        except (ValueError,TypeError):continue
        if w>=week or w<1:continue
        # Must use a stable source player identifier, not same-looking names.
        rid=str(r.get('player_id') or r.get('gsis_id') or '')
        if rid!=player_id:continue
        pct=number(r.get('offense_pct'));snaps=number(r.get('offense_snaps'))
        if pct is None or snaps is None or not 0<=pct<=1 or snaps<0:continue
        if w in snap_games:continue
        snap_games[w]={'pct':pct,'snaps':snaps}
    route_games={}
    for r in route_rows or []:
        if str(r.get('season'))!=str(season) or str(r.get('team')).upper()!=team.upper():continue
        if str(r.get('player_id'))!=player_id or r.get('method')!='CHARTED_ROUTES':continue
        try:w=int(r.get('week'))
        except (ValueError,TypeError):continue
        if w>=week or w<1:continue
        routes=number(r.get('routes_run'));team_dropbacks=number(r.get('team_dropbacks'))
        if routes is None or team_dropbacks is None or team_dropbacks<=0 or not 0<=routes<=team_dropbacks:
            continue
        if w in route_games:continue
        route_games[w]={'routes':routes,'team_dropbacks':team_dropbacks}
    last=sorted(snap_games)[-4:];route_last=sorted(route_games)[-4:]
    snap_ready=len(snap_games)>=min_snap_games
    routes_ready=len(route_games)>=min_route_games
    return {'status':'USAGE_DATA_PRESENT' if snap_ready else 'INSUFFICIENT_SNAP_GAMES',
            'player_id':player_id,'team':team,'season':season,'pregame_week':week,
            'snap_games':len(snap_games),'charted_route_games':len(route_games),
            'last_four_median_snap_pct':round(median(snap_games[i]['pct'] for i in last),4) if last else None,
            'last_four_route_participation':round(sum(route_games[i]['routes'] for i in route_last)/sum(route_games[i]['team_dropbacks'] for i in route_last),4) if route_last else None,
            'snaps_supported':snap_ready,'routes_supported':routes_ready,
            'route_status':'CHARTED_HISTORY_AVAILABLE' if routes_ready else 'UNVERIFIED_ROUTES',
            'note':'Charted routes never inferred from dropbacks-on-field; no upcoming snap guarantee.'}


def fetch_snap_counts(season:int,*,loader=None)->dict:
    """Uses already-existing v0.5 nflverse adapter; player IDs may be absent."""
    try:
        if loader is None:
            from bta_v05.sources import nfl_snap_counts
            rows,meta=nfl_snap_counts(season)
        else:rows,meta=loader(season)
    except (ImportError,ValueError,OSError) as exc:
        return {'status':'SOURCE_ERROR','rows':[],'error_type':type(exc).__name__}
    if not isinstance(rows,list):return {'status':'SCHEMA_ERROR','rows':[]}
    return {'status':'SOURCE_ROWS_NEED_PLAYER_ID_LINKAGE','rows':rows,'source':meta,
            'note':'Some nflverse snap rows lack stable IDs; resolve IDs before using in a prop model.'}


def link_pfr_snap_ids(snap_rows:list[dict], player_records:list[dict])->dict:
    """Match PFR snap IDs to nflverse GSIS IDs; collisions fail closed.

    Public snap CSV uses `pfr_player_id`, not `player_id`. Matching by names
    alone is unsafe (identical names and roster transactions).
    """
    ids={};ambiguous=set()
    for row in player_records:
        pfr=str(row.get('pfr_id') or '').strip()
        gsis=str(row.get('gsis_id') or '').strip()
        if not pfr or not gsis:continue
        if pfr in ids and ids[pfr]!=gsis:ambiguous.add(pfr)
        ids[pfr]=gsis
    for key in ambiguous:ids.pop(key,None)
    mapped=[];missing=0
    for item in snap_rows:
        pfr=str(item.get('pfr_player_id') or '').strip()
        gsis=ids.get(pfr)
        if not gsis:
            missing+=1;continue
        mapped.append({**item,'player_id':gsis})
    return {'status':'JOINED_PFR_TO_GSIS','rows':mapped,'mapped':len(mapped),
            'unmatched':missing,'ambiguous_player_ids':len(ambiguous),
            'note':'GSIS player identity mapped from unique PFR ID; no name matching.'}


def fetch_player_directory(*,loader=None)->dict:
    if loader is not None:
        try:records,meta=loader()
        except (OSError,ValueError,TypeError) as exc:
            return {'status':'SOURCE_ERROR','error_type':type(exc).__name__,'rows':[]}
    else:
        try:
            from bta_v05.sources import _download,_csv
            uri='https://github.com/nflverse/nflverse-data/releases/download/players/players.csv'
            records=_csv(_download(uri,25_000_000),{'gsis_id','pfr_id'},max_rows=70_000)
            meta={'source':uri}
        except (OSError,ValueError,ImportError) as exc:
            return {'status':'SOURCE_ERROR','error_type':type(exc).__name__,'rows':[]}
    if not isinstance(records,list):return {'status':'SCHEMA_ERROR','rows':[]}
    return {'status':'IDENTITY_DIRECTORY','rows':records,'meta':meta}


def fetch_charted_routes(*,season:int,token:str,url:str,allowed_hosts:set[str],fetcher=None):
    """Configured licensed route-charting API. No guessed public route source.

    Schema: {season: int, observations: [{season,week,team,player_id,
    method:'CHARTED_ROUTES',routes_run,team_dropbacks}]}
    """
    if not token or not url or not allowed_hosts:
        return {'status':'ROUTE_PROVIDER_NOT_CONFIGURED','rows':[]}
    from .provider import read_json
    f=fetcher or read_json
    try:obj=f(url,token=token,allowed_hosts=allowed_hosts,params={'season':season})
    except (ValueError,OSError,TypeError,KeyError) as exc:
        return {'status':'ROUTE_PROVIDER_ERROR','rows':[],'error_type':type(exc).__name__}
    if not isinstance(obj,dict) or obj.get('season')!=season or not isinstance(obj.get('observations'),list):
        return {'status':'SCHEMA_OR_SEASON_MISMATCH','rows':[]}
    vetted=[]
    for row in obj['observations']:
        if (isinstance(row,dict) and row.get('method')=='CHARTED_ROUTES'
            and row.get('player_id') and row.get('week') is not None):
            vetted.append(row)
    return {'status':'CHARTED_ROUTE_SOURCE_ROWS' if vetted else 'NO_MEASURED_ROUTE_ROWS',
            'rows':vetted,'source':url,
            'note':'Provider claims charted routes; compare documentation, IDs, freshness and coverage before certification.'}
