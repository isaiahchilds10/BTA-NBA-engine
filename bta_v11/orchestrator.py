"""Automated v1.1 evidence collection for registered providers.

No manual player statistic entry. Missing APIs produce blocked statuses.
This collector avoids inventing official game-day status, player routes,
or historical sportsbook settlement coverage.
"""
from __future__ import annotations
import os
from datetime import datetime,timezone
from .provider import cfbd_roster
from .availability import fetch_availability,evaluate as availability_gate
from .nfl_usage import fetch_snap_counts,historical_usage,fetch_player_directory,link_pfr_snap_ids,fetch_charted_routes


def gather(*,league:str,event:dict,player_id:str='',team:str='',now=None,
           availability_fetcher=None,roster_fetcher=None,snap_loader=None):
    now=now or datetime.now(timezone.utc).isoformat()
    start=event.get('start_utc','');eid=event.get('event_id') or event.get('event_key')
    result={'event_id':eid,'league':league,'at_utc':now,'sources':{},'blockers':[],
            'certified':False,'grade':'PENDING'}
    if not eid or not start:
        result['blockers'].append('Missing event ID / kickoff timestamp');return result
    if league=='College football':
        year=event.get('season_year')
        roster_key=os.getenv('CFBD_API_KEY','')
        if not roster_key:
            result['blockers'].append('CFBD_API_KEY missing: current roster cannot be fetched')
        else:
            try:
                ro= (roster_fetcher(year,team,roster_key) if roster_fetcher else
                     cfbd_roster(year=int(year),team=team,api_key=roster_key))
            except (ValueError,TypeError) as exc:
                ro={'status':'CONFIGURATION_ERROR','error_type':type(exc).__name__}
            result['sources']['college_roster']={'status':ro.get('status'),'count':len(ro.get('players',[]))}
            if ro.get('status')!='ROSTER_LIST_ONLY':result['blockers'].append('Current CFBD roster unavailable')
        result['blockers'].append('College roster does not establish starter or game-day availability')
    if league=='NFL':
        season=event.get('season_year')
        if season:
            snap=fetch_snap_counts(int(season),loader=snap_loader)
            result['sources']['nfl_snaps']={'status':snap.get('status'),'count':len(snap.get('rows',[]))}
            if snap.get('status')!='SOURCE_ROWS_NEED_PLAYER_ID_LINKAGE':
                result['blockers'].append('NFL snap data unavailable')
            elif player_id and event.get('week'):
                directory=fetch_player_directory()
                if directory['status']=='IDENTITY_DIRECTORY':
                    joined=link_pfr_snap_ids(snap['rows'],directory['rows'])
                    result['sources']['identity_matching']={'mapped':joined['mapped'],'unmatched':joined['unmatched']}
                    token=os.getenv('BTA_NFL_ROUTES_TOKEN','')
                    url=os.getenv('BTA_NFL_ROUTES_URL','')
                    hosts=set(filter(None,(x.strip() for x in os.getenv('BTA_NFL_ROUTES_HOSTS','').split(','))))
                    chart=fetch_charted_routes(season=int(season),token=token,url=url,allowed_hosts=hosts)
                    result['sources']['charted_routes']={'status':chart['status'],'rows':len(chart['rows'])}
                    usage=historical_usage(player_id=player_id,team=team,season=int(season),week=int(event['week']),
                                           snap_rows=joined['rows'],route_rows=chart['rows'])
                    result['sources']['prior_player_usage']={k:v for k,v in usage.items() if k!='note'}
                    if not usage.get('snaps_supported'):result['blockers'].append('Not enough correctly matched prior snap-count games')
                    if not usage.get('routes_supported'):result['blockers'].append('Measured routes unavailable or insufficient')
                else:result['blockers'].append('Could not automatically match nflverse PFR and GSIS player identifiers')
            else:result['blockers'].append('Player ID and exact NFL week required for individual participation research')
        else:result['blockers'].append('NFL season missing')
    if player_id:
        url=os.getenv('BTA_AVAILABILITY_URL','');token=os.getenv('BTA_AVAILABILITY_TOKEN','')
        hosts=set(filter(None,(s.strip() for s in os.getenv('BTA_AVAILABILITY_HOSTS','').split(','))))
        response=(availability_fetcher(eid) if availability_fetcher else
                  fetch_availability(url=url,token=token,allowed_hosts=hosts,event_id=eid))
        match=availability_gate(league=league,event_id=eid,player_id=player_id,
                                event_start_utc=start,response=response,now_utc=now)
        result['sources']['availability']={'status':match['status']}
        if not match['eligible']:result['blockers'].extend(match['reasons'])
    else:result['blockers'].append('Player selection/ID absent; game-market research only')
    result['blockers'].append('Prospective authenticated market settlement and holdout model validation required')
    result['blockers'].append('Five-script independent Red Team review required')
    return result
