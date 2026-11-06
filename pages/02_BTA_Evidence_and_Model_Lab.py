"""BTA v0.5 optional additive research lab. Place beside 01_BTA_Command_Center.py.

No real-money actions; no autonomous TAIG/BTA+ grades. Uses v0.5 modules.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import statistics
import streamlit as st

from bta_v05.sources import (nfl_injury_reports,nfl_snap_counts,nfl_weekly_player_stats,
                              latest_nba_official_report,newest_nba_community_logs,cfbd_fbs_games,espn_day_schedule,NBA_INJURY_INDEX,nfl_complete_schedules)
from bta_v05.models import (nba_injury_lookup,nfl_injury_lookup,nfl_snaps_lookup,
                             nba_matchup_context,nfl_defense_context,
                             cfb_elo_progress,cfb_unvalidated_upcoming,
                             bta_stress_gate,historical_threshold,nba_walk_forward_research,nfl_game_elo_progress)
from bta_v05.calibration import fit_evaluate,cfb_records_from_elo

st.set_page_config(page_title='BTA Evidence & Model Lab',page_icon='🛡️',layout='wide')
st.markdown('''<style>
.stApp{background:#080d17;color:#e9efff}
[data-testid="stMetric"]{background:#121d2e;padding:12px;border-radius:12px;border:1px solid #203650}
.stButton>button[kind="primary"]{background:#1679d3;border:none}
div[data-testid="stVerticalBlock"]{row-gap:.6rem}
</style>''',unsafe_allow_html=True)
st.title('BTA Evidence & Model Lab')
st.caption('v0.5 review build | automatic when this page loads or cache expires; no unattended betting, guaranteed injury clearance, or approved picks.')
st.info('RESEARCH ONLY: data source freshness, roster role and exact sportsbook market must be verified before any TAIG/BTA+/BTA assessment.')

@st.cache_data(ttl=45*60,show_spinner=False)
def cached_nfl_injuries(year):return nfl_injury_reports(year)
@st.cache_data(ttl=4*60*60,show_spinner=False)
def cached_nfl_snaps(year):return nfl_snap_counts(year)
@st.cache_data(ttl=4*60*60,show_spinner=False)
def cached_nfl_stats(year):return nfl_weekly_player_stats(year)
@st.cache_data(ttl=40*60,show_spinner=False)
def cached_nfl_games():return nfl_complete_schedules()
@st.cache_data(ttl=15*60,show_spinner=False)
def cached_nba_injury():return latest_nba_official_report()
@st.cache_data(ttl=20*60,show_spinner=False)
def cached_scoreboard(sport,league,day):return espn_day_schedule(sport,league,day)
@st.cache_data(ttl=4*60*60,show_spinner=False)
def cached_nba_logs(year):return newest_nba_community_logs(year)
@st.cache_data(ttl=4*60*60,show_spinner=False)
def cached_cfb_games(year,token):return cfbd_fbs_games(year,token)
@st.cache_data(ttl=4*60*60,show_spinner=False)
def cached_nba_backtest(rows,stat):return nba_walk_forward_research(list(rows),stat=stat)

def _none_or_unplayed(g):
    return g.get('home_score') in (None,'') or g.get('away_score') in (None,'')

nba_tab,nfl_tab,cfb_tab,validation_tab,stress_tab=st.tabs([
    '🏀 NBA','🏈 NFL','🎓 College football','📈 Validation','🛡️ BTA stress audit'])

with nba_tab:
    st.subheader('Official NBA injury report + automatic historical opponent context')
    season_year = date.today().year if date.today().month >= 7 else date.today().year-1
    season = st.selectbox('NBA game-log season',[f'{season_year}-{(season_year+1)%100:02d}',
                     f'{season_year-1}-{season_year%100:02d}'],key='v05_nba_season')
    if st.button('Recheck NBA sources',key='nba_v05_clear'):
        cached_nba_logs.clear();cached_nba_injury.clear();st.rerun()
    logs=[]
    try:
        logs,meta=cached_nba_logs(season)
        st.success(f'Automatic published NBA game logs: {len(logs):,} player-game rows; snapshot {meta["snapshot"]}.')
        st.caption('Source: '+meta['source']+'. Community-maintained box scores; date is snapshot date, not a medical update.')
    except Exception as e:
        st.warning(f'Automatic NBA box-score source unavailable ({type(e).__name__}: {str(e)[:180]}). No data substituted.')
    pdf_text,report_meta=None,None
    try:
        pdf_text,report_meta=cached_nba_injury()
        st.caption('NBA official injury PDF: '+report_meta['source']+' | Report publication: '+report_meta['report_published_et_naive']+
                   f' | Not-yet-submitted labels: {report_meta["not_submitted_sections"]}.')
    except Exception as e:
        st.warning(f'NBA injury PDF could not be parsed ({type(e).__name__}: {str(e)[:140]}). Availability UNVERIFIED.')
        st.markdown(f'[Official injury report page]({NBA_INJURY_INDEX})')
    if logs:
        people=sorted({r.get('Player','') for r in logs if r.get('Player')})
        player=st.selectbox('Player to investigate',people,key='v05_nba_player')
        asof=st.date_input('Matchup/game date — only prior games included',value=date.today(),key='v05_nba_asof')
        active_games=[]
        try:
            active_games,_=cached_scoreboard('basketball','nba',asof.strftime('%Y%m%d'))
        except Exception as e:
            st.caption(f'Automatic NBA opponent schedule unavailable ({type(e).__name__}); manual fallback permitted.')
        player_team_logs=[r for r in logs if r.get('Player')==player]
        latest_team=str(max(player_team_logs,key=lambda r:str(r.get('Date') or '')).get('Team') or '').upper() if player_team_logs else ''
        st.caption(f'Last observed team in historical logs: {latest_team or "unknown"}. Current roster affiliation is NOT verified.')
        default_opponent=''
        auto_games=[g for g in active_games if latest_team and latest_team in (g['home']['abbrev'],g['away']['abbrev'])]
        if len(auto_games)==1:
            g=auto_games[0]
            default_opponent=g['away']['abbrev'] if g['home']['abbrev']==latest_team else g['home']['abbrev']
            st.caption(f'Auto game match: {g["away"]["name"]} @ {g["home"]["name"]}. Recheck player roster.')
        opponent=st.text_input('Upcoming opponent code (auto from scheduled game when possible)',
                               value=default_opponent,placeholder='e.g. BOS',key='v05_nba_opp').strip().upper()
        stat=st.selectbox('Prop statistic',('Points','Rebounds','Assists'),key='v05_nba_stat')
        line=st.number_input('Research threshold (verify actual bookmaker line separately)',
                             min_value=0.5,max_value=250.5,value=20.5,step=0.5,key='v05_nba_line')
        player_data=sorted((r for r in logs if r.get('Player')==player and str(r.get('Date',''))[:10]<asof.isoformat()),
                           key=lambda r:r.get('Date',''))
        historic=historical_threshold(player_data,field=stat,line=line,minutes_field='Minutes')
        if historic['gate']=='DESCRIPTIVE ONLY':
            a,b,c=st.columns(3)
            a.metric('Observed sample',historic['count']);b.metric('Historical median',f'{historic["median"]:.1f}');c.metric('Last 10 clears',f'{historic["last10_hits"]}/{historic["last10_games"]}')
            st.caption(f'Last three observations: {historic["last3"]}. These are actual sample values, not next-game probabilities.')
        else:st.warning(historic['reason'])
        if pdf_text and report_meta and 0 <= (asof-date.today()).days <= 1:
            injury=nba_injury_lookup(pdf_text,player,report_meta)
            st.write('**Official report listing:**',injury['gate'],injury.get('status',''),injury.get('reason',''))
        else:st.warning('Official injury gate: UNVERIFIED (report not available or selected date is not today/tomorrow).')
        if opponent:
            context=nba_matchup_context(logs,player,opponent,before=asof,stat=stat)
            st.write('**Opponent research:**',context)
        else:st.info('Enter an actual opponent to calculate historical scoring-environment context.')
        st.warning('No automatic NBA BTA+ grade: coach, confirmed minutes, teammate restrictions, five scripts, and exact market odds still require evidence.')

with nfl_tab:
    st.subheader('NFL player injuries, snap-share trends, and opponent defense')
    year=date.today().year if date.today().month >= 8 else date.today().year-1
    year=int(st.selectbox('NFL season',[year,year-1],key='v05_nfl_year'))
    if st.button('Recheck NFL sources',key='v05_nfl_clear'):
        cached_nfl_injuries.clear();cached_nfl_snaps.clear();cached_nfl_stats.clear();cached_nfl_games.clear();st.rerun()
    injuries=[];snaps=[];stats=[]
    for label,fun in [('Injury reports',cached_nfl_injuries),('Snap counts',cached_nfl_snaps),('Weekly box scores',cached_nfl_stats)]:
        try:
            data,details=fun(year)
            if label=='Injury reports':injuries=data
            elif label=='Snap counts':snaps=data
            else:stats=data
            st.caption(f'{label}: {len(data):,} rows · {details["source"]} · fetched {details["retrieved_at_utc"]}.')
        except Exception as e:
            st.warning(f'{label} source unavailable ({type(e).__name__}: {str(e)[:150]}).')
    if injuries or snaps or stats:
        week=1
        people=sorted({r.get('full_name','') for r in injuries if r.get('full_name')}
                      | {r.get('player','') for r in snaps if r.get('player')})
        if people:
            player=st.selectbox('NFL player',people,key='v05_nfl_player')
            all_weeks=[int(r['week']) for r in injuries if str(r.get('week','')).isdigit()]
            wk=max(all_weeks) if all_weeks else 1
            week=int(st.number_input('Exact upcoming week (recheck NFL calendar)',min_value=1,max_value=22,value=min(22,wk),key='v05_nfl_week'))
            team=st.text_input('Player team code (optional)',key='v05_nfl_team').strip().upper()
            st.write('**Weekly injury report:**',nfl_injury_lookup(injuries,player,week,team) if injuries else {'gate':'UNVERIFIED'})
            st.write('**Prior snap shares:**',nfl_snaps_lookup(snaps,player,before_week=week,team=team) if snaps else {'gate':'UNVERIFIED'})
        metric=st.selectbox('Opposing defense context',('Receiving yards','Rushing yards','Passing yards','Receptions','Targets','Passing touchdowns'),key='v05_nfl_metric')
        opponent=st.text_input('Opponent abbreviation (check game schedule)',key='v05_nfl_opponent').strip().upper()
        if opponent and snaps and stats:
            st.write('**Team-week defensive environment:**',nfl_defense_context(stats,snaps,opponent=opponent,metric=metric,before_week=week))
    st.markdown('**NFL game-winner strength baseline**')
    try:
        schedule,gm=cached_nfl_games()
        st.caption(f'Automatic historical NFL results: {len(schedule):,} schedule records · {gm["source"]}.')
        future=[g for g in schedule if str(g.get('season'))==str(year) and _none_or_unplayed(g)]
        if future:
            g=st.selectbox('NFL upcoming matchup',future,
                format_func=lambda g:f'{g.get("gameday")} · {g.get("away_team")} @ {g.get("home_team")}',key='v05_nfl_game')
            cutoff=date.fromisoformat(str(g['gameday'])[:10])
            elos,old=nfl_game_elo_progress(schedule,cutoff=cutoff)
            home,away=str(g.get('home_team','')),str(g.get('away_team',''))
            if home in elos and away in elos:
                from math import pow
                p=1/(1+pow(10,-(elos[home]+45-elos[away])/400))
                st.caption(f'Experimental raw home-win Elo probability: {p:.1%}. No QB, coaching, injuries, spread, total or odds incorporated.')
            else:st.warning('Not enough game history for both teams.')
        else:st.info('No unplayed games in the returned NFL schedule for this season.')
    except Exception as e:
        st.warning(f'NFL games dataset unavailable ({type(e).__name__}: {str(e)[:150]}).')
    st.warning('NFL injuries are weekly reports—not confirmed inactives. Routes, OL/DL injuries, coaching, personnel and final lineup are not automatically verified. Missing entry NEVER means healthy.')

with cfb_tab:
    st.subheader('FBS college football — chronological Elo research, never automatic TAIG')
    st.caption('Only moneyline, spread, total. Spread and total models NOT implemented in this upgrade; no fabricated prices.')
    year=date.today().year if date.today().month >= 7 else date.today().year-1
    year=int(st.selectbox('FBS season',[year,year-1],key='v05_cfb_year'))
    key=None
    try:key=st.secrets.get('CFBD_API_KEY')
    except Exception:pass
    if not key:
        st.warning('CFBD_API_KEY not in Streamlit Secrets. This provider may require a qualifying API tier. FBS projections unavailable.')
        st.markdown('[Official CollegeFootballData access](https://api.collegefootballdata.com/usage-and-access)')
    else:
        if st.button('Recheck CFBD',key='cfb_v05_clear'):
            cached_cfb_games.clear();st.rerun()
        try:
            games,meta=cached_cfb_games(year,str(key))
            st.caption(f'{len(games):,} FBS game records · {meta["source"]}.')
            options=[g for g in games if g.get('homeTeam') and g.get('awayTeam') and g.get('startDate')]
            options.sort(key=lambda g:g.get('startDate',''))
            if options:
                selected=st.selectbox('Choose historical or upcoming FBS game',options,
                    format_func=lambda g:f'{str(g["startDate"])[:10]} · {g["awayTeam"]} @ {g["homeTeam"]}',key='v05_cfb_match')
                cutoff=datetime.fromisoformat(str(selected['startDate']).replace('Z','+00:00'))
                if cutoff.tzinfo is None:cutoff=cutoff.replace(tzinfo=timezone.utc)
                ratings,forecasts=cfb_elo_progress(games,cutoff=cutoff)
                result=cfb_unvalidated_upcoming(selected['homeTeam'],selected['awayTeam'],ratings)
                st.write('**Pregame-only team-strength research:**',result)
                st.caption(f'{len(forecasts)} earlier completed-game forecasts; target game score is not used in calculation.')
            st.warning('FBS injury/starting-QB status, coaching changes and weather cannot be verified through this feed. All are PENDING.')
        except Exception as e:
            st.warning(f'CFBD feed unavailable ({type(e).__name__}: {str(e)[:180]}).')

with validation_tab:
    st.subheader('Chronological probability reliability tests')
    st.caption('No line-shopping or hindsight: forecasts must precede games. Historical synthetic lines are NOT real sportsbook markets.')
    target=st.radio('Validation dataset',('NBA synthetic prior-derived prop lines','College football Elo game winners','NFL Elo game winners'),key='v05_validation_target')
    mintrain=st.number_input('Minimum training observations',min_value=100,max_value=3000,value=300,step=50,key='v05_validation_train')
    mintest=st.number_input('Minimum untouched evaluation observations',min_value=50,max_value=2000,value=100,step=50,key='v05_validation_test')
    if st.button('Run held-out evaluation',type='primary',key='v05_eval_run'):
        try:
            if target.startswith('NBA'):
                now=date.today();start=now.year if now.month>=7 else now.year-1
                season=f'{start-1}-{start%100:02d}'
                raw,meta=cached_nba_logs(season)
                stat=st.session_state.get('v05_nba_stat','Points').lower()
                records=nba_walk_forward_research(raw,stat=stat,max_players=90)
                label=f'NBA {stat}; {meta["source"]}; synthetic prior-derived lines'
            elif target.startswith('College'):
                if not key: raise ValueError('CFBD key unavailable')
                games,meta=cached_cfb_games(year,str(key))
                _ratings,preds=cfb_elo_progress(games)
                records=cfb_records_from_elo(preds)
                label=f'CFB {year}; {meta["source"]}'
            else:
                games,meta=cached_nfl_games()
                _ratings,preds=nfl_game_elo_progress(games)
                records=cfb_records_from_elo(preds)
                label=f'NFL win/loss research since 2022; {meta["source"]}' 
            report=fit_evaluate(records,min_train=int(mintrain),min_test=int(mintest))
            st.write('**Source and method:**',label)
            st.json(report)
            if report['status'].startswith('TESTED'):
                st.warning('Calibration sample only. Tests do NOT establish positive expected value at actual sportsbook odds. No live wagering.')
        except Exception as e:
            st.error(f'Validation could not complete: {type(e).__name__}: {str(e)[:220]}')

with stress_tab:
    st.subheader('BTA / BTA+ / TAIG five-script evidence gate')
    sport=st.selectbox('Scenario framework',('NFL player props','NBA player props','College football moneyline'),key='v05_stress_sport')
    scenarios={'NFL player props':('Favorite blowout','Underdog blowout/upset','Close game','Low-scoring defense','High-scoring shootout'),
               'NBA player props':('Player team wins blowout','Player team loses blowout','Close competitive','Slow defensive','Fast high scoring'),
               'College football moneyline':('Expected performance','Underdog early 10–0 / 14–0','Favorite minus-two turnovers','Favorite best strength neutralized','One-score fourth quarter')}
    st.caption('A grade requires independently checked evidence. Five scenario verdicts require a mechanism, not a checkbox.')
    verdicts=[];mechanisms=[]
    for i,script in enumerate(scenarios[sport]):
        l,r=st.columns((1,2))
        with l:v=st.selectbox(f'{i+1}. {script}',('NOT ASSESSED','BETTER','SAME','MIXED','WORSE'),key=f'v05_script_{sport}_{i}')
        with r:why=st.text_input('Evidence-based mechanism',key=f'v05_mechanism_{sport}_{i}',placeholder='What changes in usage, possessions, pressure, etc.?')
        verdicts.append(v);mechanisms.append(why)
    st.markdown('**Evidence blockers**')
    blocks=[]
    for label in ('Injury/active status','Expected snaps or minutes','Opposing personnel and strength','Coaching/rotation/starter changes',
                  'Exact offered line, price, push/void rules','Travel, weather, schedule when relevant','Base/adverse/reverse failure route','Independent opponent-adjusted checks'):
        if st.checkbox(f'Unresolved: {label}',value=True,key=f'v05_block_{sport}_{label}'):
            blocks.append(label)
    supplied=st.checkbox('All checked evidence has genuinely dated independent sources (not merely unchecked boxes)',key='v05_sources_checked')
    independent=st.checkbox('Independent second-pass review completed with dated source notes',key='v05_second_pass')
    st.text_area('Dated links, ordinary misses, structural risks, opponent comparison and independent audit notes',key='v05_audit_notes')
    if any(v!='NOT ASSESSED' and not mechanisms[i].strip() for i,v in enumerate(verdicts)):
        blocks.append('Unexplained game-script classifications')
    result=bta_stress_gate(sport,verdicts,blockers=blocks,
                           sources_verified=supplied,independent_audit=independent)
    st.markdown(f'### {result["status"]}')
    st.caption(result['reason'])
    st.info('This stress test never awards TAIG, BTA+ or BTA by itself. Full graded board and a recommended ticket are distinct. The 2+ WORSE rule eliminates player props from strict tickets.')

st.divider()
st.caption('Version 0.5 · Modular addon to v0.4. Automatic fetches occur when this page loads and while it is open, based on caching; this is NOT a background 24/7 job.')
