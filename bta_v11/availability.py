"""Strict game-day availability evaluation.

NBA official *injury report* is NOT a confirmed active roster.
NFL final inactives list is NOT a confirmed starting lineup. College rosters are
NOT official participation lists. Provenance must come from an authenticated
fetch, not from a typed checkbox. Incomplete feeds fail closed.
"""
from __future__ import annotations
from urllib.parse import urlparse
from .common import asof_gate
from .provider import read_json

ALLOWED_SOURCE_HOSTS={'nba.com','official.nba.com','nfl.com','www.nfl.com','api.collegefootballdata.com'}
NEGATIVE={'OUT','INACTIVE','DOUBTFUL','SUSPENDED','IR','PUP','NOT_AVAILABLE'}
UNCERTAIN={'QUESTIONABLE','GTD','GAME_TIME_DECISION','LIMITED','UNKNOWN','NOT_REPORTED'}


def fetch_availability(*,url:str,token:str,allowed_hosts:set[str],event_id:str,fetcher=read_json):
    """Use a licensed/current endpoint returning a complete *event-scoped* object.

    The endpoint contract is documented in PROVIDER_CONTRACT.md; no guesses
    about ESPN/NBA undocumented JSON fields are made.
    """
    if not token or not url or not allowed_hosts:return {'status':'PROVIDER_NOT_CONFIGURED','records':[]}
    try:
        obj=fetcher(url,token=token,allowed_hosts=allowed_hosts,params={'event_id':event_id})
    except (ValueError,OSError,TypeError,KeyError) as exc:
        return {'status':'PROVIDER_ERROR','error_type':type(exc).__name__,'records':[]}
    if not isinstance(obj,dict) or obj.get('event_id')!=event_id or not isinstance(obj.get('records'),list):
        return {'status':'IDENTITY_OR_SCHEMA_ERROR','records':[]}
    return {'status':'FETCHED_PROVIDER_RESPONSE','event_id':event_id,'records':obj['records'],
            'asof_utc':obj.get('asof_utc'),'retrieved_utc':obj.get('retrieved_utc'),
            'source_url':url,'coverage':obj.get('coverage'),
            'note':'Provider response needs game-by-game source/participation validation.'}


def evaluate(*,league:str,event_id:str,player_id:str,event_start_utc:str,
             response:dict,now_utc:str,max_age_hours:float=8,needs_starter:bool=False)->dict:
    base={'eligible':False,'status':'PENDING','player_id':player_id,'reasons':[]}
    if league not in ('NBA','NFL','College football') or not event_id or not player_id:
        return {**base,'reasons':['Invalid sport/event/player identity']}
    if not isinstance(response,dict) or response.get('status')!='FETCHED_PROVIDER_RESPONSE' or response.get('event_id')!=event_id:
        return {**base,'reasons':['No event-matched authenticated provider response']}
    origin=urlparse(str(response.get('source_url') or ''))
    if origin.scheme!='https' or not origin.hostname:
        return {**base,'reasons':['Missing HTTPS source provenance']}
    freshness=asof_gate(asof=response.get('asof_utc'),retrieved=response.get('retrieved_utc'),
                        event_start=event_start_utc,max_age_hours=max_age_hours,now=now_utc)
    if not freshness['ok']:return {**base,'reasons':[freshness['reason']]}
    found=[r for r in response.get('records',[]) if isinstance(r,dict) and str(r.get('player_id'))==str(player_id)
           and r.get('event_id')==event_id]
    if len(found)!=1:return {**base,'reasons':['No unique event-specific player record']}
    r=found[0];status=str(r.get('status') or '').upper(); kind=str(r.get('report_type') or '').upper()
    if status in NEGATIVE:return {**base,'status':'BLOCKED','reasons':['Player unavailable: '+status]}
    if status in UNCERTAIN:return {**base,'reasons':['Player status unresolved: '+status]}
    if status not in ('ACTIVE','AVAILABLE','CONFIRMED_STARTER'):
        return {**base,'reasons':['No affirmative participation status']}
    if kind in ('SEASON_ROSTER','DEPTH_CHART','PRACTICE_REPORT','INJURY_REPORT'):
        return {**base,'reasons':['Source type does not prove game-day participation']}
    if kind not in ('OFFICIAL_ACTIVE_LIST','CONFIRMED_LINEUP','FINAL_INACTIVES_PLUS_ACTIVE_ROSTER'):
        return {**base,'reasons':['Unrecognized source participation type']}
    if needs_starter and (kind!='CONFIRMED_LINEUP' or r.get('confirmed_starter') is not True):
        return {**base,'reasons':['Starting status not explicitly verified']}
    # An authenticated provider can report eligibility; even this cannot prove unrestricted minutes/snaps.
    if r.get('unrestricted_workload') is not True:
        return {**base,'status':'ELIGIBLE_WORKLOAD_UNKNOWN',
                'reasons':['Game-day participation supported; unrestricted workload not verified']}
    return {**base,'eligible':True,'status':'PROVIDER_SUPPORTED_ACTIVE',
            'reasons':[],'source_url':response['source_url'],'asof_utc':response['asof_utc'],
            'note':'No prediction of actual playing time or performance.'}
