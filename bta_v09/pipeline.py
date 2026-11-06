"""Scheduled, read-only research collector. Real data fetch, no wagering.

By default outputs ONLY game/source status, safe for public repos. Licensed
bookmaker quotations and player-level model snapshots require explicit opt-in
and PRIVATE repository/storage; no provider credentials are ever recorded.
"""
from __future__ import annotations
import hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from bta_v08.schedule import collect,next_days,parse_instant,augment_nba_official_score
from bta_v08.markets import fetch_markets,match_offers,book_quote_status
from .evidence import coverage_report
from .health import source_age
from .forecast import exact_line_baseline
from .grade import audit_candidate
from .scripts import mechanisms,reverse_failure
from .college import research as college_research

LEAGUES=('NBA','NFL','College football')


def _histories(league: str, when:datetime, *, loader=None) -> tuple[list[dict],list[dict]]:
    if loader is not None:return loader(league,when)
    from bta_v05.sources import newest_nba_community_logs, nfl_weekly_player_stats
    rows=[];meta=[]
    if league=='NBA':
        current=when.year if when.month>=7 else when.year-1
        years=(current-1,current)
    elif league=='NFL':
        current=when.year if when.month>=4 else when.year-1
        years=(current-1,current)
    else:
        return rows,[{'status':'NO AUTOMATIC PLAYER PROPS','note':'CFB only game-level markets'}]
    for year in years:
        try:
            if league=='NBA':
                year_tag=f'{year}-{(year+1)%100:02d}'
                data,info=newest_nba_community_logs(year_tag)
            else:
                data,info=nfl_weekly_player_stats(year)
            rows.extend(data)
            # Retrieval date alone does not prove the underlying game logs updated.
            latest_observation=None
            try:
                if league=='NBA':
                    observed=[str(r.get('Date') or '')[:10] for r in data]
                    dates=[x for x in observed if len(x)==10 and x[:4].isdigit()]
                    latest_observation=max(dates) if dates else None
                else:
                    weeks=[int(r.get('week')) for r in data if str(r.get('season'))==str(year)
                           and str(r.get('week') or '').isdigit()]
                    latest_observation=f'{year} week {max(weeks)}' if weeks else None
            except (TypeError,ValueError):pass
            meta.append({**info,'status':'RETRIEVED','season':year,
                         'latest_observation':latest_observation,
                         'freshness_caution':'Latest observed game/week may trail the provider retrieval timestamp.'})
        except Exception as exc:
            meta.append({'season':year,'status':'SOURCE ERROR',
                         'error_class':type(exc).__name__,
                         'message':'Provider unavailable or schema changed; no synthetic rows substituted'})
    return rows,meta


def _key_for(event:dict,offer:dict)->str:
    identity=[event.get('event_key'),event.get('start_utc'),offer.get('bookmaker'),
              offer.get('market'),offer.get('player'),offer.get('selection'),offer.get('line')]
    return hashlib.sha256(json.dumps(identity,sort_keys=True,default=str).encode()).hexdigest()[:32]


def collect_research(*,now:datetime|None=None,horizon:int=3,
                     odds_key:str='', include_props:bool=False,
                     save_market_details:bool=False, schedule_fetcher=None,
                     odds_fetcher=None,history_loader=None,nba_official_fetcher=None,
                     injury_loader=None,cfbd_key:str="",college_loader=None) -> tuple[dict,list[dict]]:
    """Return full snapshot in memory; only persist licensed details if opted-in.

    Caller is responsible for confirming private storage rights and provider ToS.
    No 'auto TAIG' or final qualified ticket is emitted.
    """
    now=(now or datetime.now(timezone.utc))
    if now.tzinfo is None:raise ValueError('now must have a timezone')
    now=now.astimezone(timezone.utc)
    if not 1<=horizon<=7:raise ValueError('horizon must be 1..7')
    local=now.astimezone(ZoneInfo('America/New_York')).date()
    days=next_days(local,horizon=horizon)
    snapshot={'version':'v0.9-review','built_at_utc':now.isoformat(),
              'data_policy':'Fail closed: no guaranteed live source/graded BTA.',
              'market_details_persisted':bool(save_market_details),
              'leagues':{}, 'model_validation':'NOT VALIDATED','auto_ticket':[]}
    forecast_rows=[]
    college_games=[]
    college_sources=[]
    if cfbd_key:
        for season in (local.year-1,local.year):
            try:
                if college_loader is None:
                    from bta_v05.sources import cfbd_fbs_games
                    batch,info=cfbd_fbs_games(season,cfbd_key)
                else: batch,info=college_loader(season,cfbd_key)
                college_games.extend(batch)
                college_sources.append({'season':season,'status':'RETRIEVED',**info})
            except Exception as exc:
                college_sources.append({'season':season,'status':'UNAVAILABLE',
                                        'error_class':type(exc).__name__})
    for league in LEAGUES:
        collection=collect(league,days,**({'fetcher':schedule_fetcher} if schedule_fetcher else {}))
        games=collection['games']
        official_nba={'status':'NOT CHECKED'}
        if league=='NBA':
            try:
                if nba_official_fetcher is None:
                    from bta_v06.live import nba_today
                    official_nba=nba_today()
                else: official_nba=nba_official_fetcher()
                games,updated=augment_nba_official_score(games,official_nba,local_day=local)
                official_nba={'status':official_nba.get('status'),'games_matched':updated,
                             'retrieved_at_utc':official_nba.get('retrieved_at_utc')}
            except (ImportError,KeyError,ValueError,TypeError,OSError) as exc:
                official_nba={'status':'UNAVAILABLE','error_class':type(exc).__name__}
        record={'games':[],'source_errors':collection['errors'],
                'source_logs':collection['source_logs'],
                'complete':collection['complete'],
                'market_status':'NO PROVIDER KEY' if not odds_key else 'UNTESTED',
                'history_sources':college_sources if league=='College football' else [],'unmatched_quotes':0,'official_nba_scoreboard':official_nba}
        offers=[]
        if odds_key:
            try:
                f=odds_fetcher or fetch_markets
                ordinary,meta=f(league,odds_key,props=False,only_book='fanduel')
                offers.extend(ordinary)
                record['market_status']='RETRIEVED'
                record['market_meta']=[meta]
            except Exception as exc:
                record['market_status']='PROVIDER ERROR: '+type(exc).__name__
            if include_props and league!='College football':
                try:
                    f=odds_fetcher or fetch_markets
                    props,meta=f(league,odds_key,props=True,only_book='fanduel',bulk=True)
                    offers.extend(props)
                    record.setdefault('market_meta',[]).append(meta)
                except Exception as exc:
                    record['player_props_status']='PROVIDER ERROR: '+type(exc).__name__
        matched,unmatched=match_offers(games,offers) if offers else ({x['event_key']:[] for x in games},[])
        record['unmatched_quotes']=len(unmatched)
        # Refresh the supported NBA/NFL historical data on scheduled runs even
        # without a paid odds key; record source provenance, not entire datasets.
        if league in ('NBA','NFL'):
            hist,meta=_histories(league,now,loader=history_loader)
            record['history_sources']=meta
            record['historical_rows_loaded']=len(hist)
            record['history_publication_audit']=source_age(league,meta,hist,now=now)
        else:hist=[]
        # Injury evidence is fetched automatically, but a dated report is NOT
        # equivalent to an officially confirmed unrestricted game-day active.
        injury_source={'status':'NOT FETCHED'}
        injury_payload=None
        if league in ('NBA','NFL'):
            try:
                if injury_loader is not None:
                    injury_payload,injury_source=injury_loader(league,now)
                elif league=='NBA':
                    from bta_v05.sources import latest_nba_official_report
                    injury_payload,injury_source=latest_nba_official_report()
                else:
                    from bta_v05.sources import nfl_injury_reports
                    season=now.year if now.month>=4 else now.year-1
                    injury_payload,injury_source=nfl_injury_reports(season)
                injury_source={'status':'RETRIEVED', **injury_source}
            except Exception as exc:
                injury_source={'status':'UNAVAILABLE','error_class':type(exc).__name__}
        record['injury_source']={k:v for k,v in injury_source.items() if k not in ('raw','text')}
        for event in games:
            game={'event_key':event['event_key'],'start_utc':event['start_utc'],
                  'status':event['status'],'away':event['away']['name'],'home':event['home']['name'],
                  'source':event['source'],'source_retrieved_at_utc':event['retrieved_at_utc'],
                  'candidate_count':0,'research_leads':[],'grade':'NO CERTIFIED BTA PICK'}
            if league=='College football' and college_games:
                game['team_strength_research']=college_research(event,college_games)
            if save_market_details and event.get('status')=='UPCOMING':
                for offer in matched.get(event['event_key'],[]):
                    if not offer.get('player'):
                        game['research_leads'].append({'market':offer['market'],
                             'selection':offer['selection'],'line':offer['line'],
                             'american_odds':offer['american_odds'],
                             'status':'MARKET OFFER ONLY - UNGRADED',
                             'provider_time':offer['book_updated_utc']})
                        continue
                    baseline=exact_line_baseline(event,offer,hist)
                    gate=audit_candidate(event,offer,baseline,now=now)
                    availability={'gate':'UNVERIFIED','reason':'No matching dated report; not-listed is not confirmed active'}
                    try:
                        if league=='NBA' and isinstance(injury_payload,str):
                            from bta_v05.models import nba_injury_lookup
                            availability=nba_injury_lookup(injury_payload,offer['player'],injury_source,now=now)
                        elif league=='NFL' and isinstance(injury_payload,list) and event.get('week') is not None:
                            from bta_v05.models import nfl_injury_lookup
                            team_guess='' # Unknown player team from matched bookmaker offer. Never guess.
                            availability=nfl_injury_lookup(injury_payload,offer['player'],int(event['week']),team_guess)
                    except Exception:
                        availability={'gate':'UNVERIFIED','reason':'Injury lookup failed or player identity ambiguous'}
                    script_report=mechanisms(league,offer['market'],offer['selection'],offer['player'])
                    reverse=reverse_failure(baseline)
                    detail={'player':offer['player'],'market':offer['market'],
                            'selection':offer['selection'],'line':offer.get('line'),
                            'american_odds':offer.get('american_odds'),
                            'provider_time':offer.get('book_updated_utc'),
                            'bookmaker':offer.get('bookmaker'),'experimental_model':baseline,
                            'grade':gate['grade'],'missing':gate.get('missing',[]),
                            'strict_ticket_eligible':False,
                            'availability':availability, 'scenario_prompts':script_report,
                            'reverse_failure_observations':reverse}
                    game['research_leads'].append(detail)
                    if (baseline.get('status')=='EXPERIMENTAL_UNCALIBRATED'
                            and book_quote_status(offer,now=now,max_age_minutes=15)=='RECENT QUOTE'
                            and parse_instant(event['start_utc'])>now):
                        fid=_key_for(event,offer)
                        forecast_rows.append({
                            'forecast_id':fid,'event_id':event['event_key'],'event_start_utc':event['start_utc'],
                            'market_id':fid,'league':league,'market':offer['market'],
                            'player':offer['player'],'side':offer['selection'],
                            'line':offer['line'],'bookmaker':offer.get('bookmaker'),
                            'american_odds_snapshot':offer['american_odds'],
                            'book_quote_at_utc':offer['book_updated_utc'],
                            'model_id':baseline['model_version'],
                            'experimental_probability':baseline['experimental_probability'],
                            'prediction_at_utc':now.isoformat(),
                            'features_asof_utc':now.isoformat(),
                            'history_sample_n':baseline['n'],
                            'history_publication_status':record.get('history_publication_audit',{}).get('status'),
                            'calibration_status':'NOT VALIDATED',
                            'qualified_bta':False,
                            'not_betting_advice':True})
            game['candidate_count']=len(game['research_leads'])
            record['games'].append(game)
        snapshot['leagues'][league]=record
    snapshot['forecast_attempt_count']=len(forecast_rows)
    if not save_market_details:
        snapshot['forecast_attempt_count']=0
        # no paid market data or lines stored in public snapshots
        forecast_rows=[]
    return snapshot,forecast_rows


def _atomic_json(path:Path,payload:dict)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+'\n',encoding='utf-8')
    os.replace(temp,path)


def append_forecasts(path:Path,rows:list[dict])->int:
    """Idempotent prospective append; never overwrite a historical earlier forecast."""
    path.parent.mkdir(parents=True,exist_ok=True)
    old=[]
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():old.append(json.loads(line))
    seen={r['forecast_id'] for r in old}
    additions=[]
    for r in rows:
        key=r.get('forecast_id')
        if not key or key in seen:continue
        made=parse_instant(r.get('prediction_at_utc'))
        start=parse_instant(r.get('event_start_utc'))
        if not made or not start or made>=start:continue
        additions.append(r)
        seen.add(key)
    if additions:
        text=''.join(json.dumps(row,sort_keys=True)+'\n' for row in old+additions)
        temp=path.with_suffix('.tmp')
        temp.write_text(text,encoding='utf-8')
        os.replace(temp,path)
    return len(additions)


def write_snapshot(snapshot:dict,path:Path)->None:
    _atomic_json(path,snapshot)
