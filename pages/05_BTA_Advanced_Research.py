"""Additive BTA v0.7 research dashboard. No real-money orders.
Requires v0.5 modules; does not replace v0.4, v0.5, v0.6 pages.
"""
from __future__ import annotations
from datetime import date,datetime,timezone
from pathlib import Path
import json
import streamlit as st

from bta_v05.sources import (newest_nba_community_logs, nfl_weekly_player_stats,
    nfl_injury_reports, nfl_snap_counts, nfl_complete_schedules, cfbd_fbs_games)
from bta_v05.models import (nba_matchup_context, nfl_injury_lookup, nfl_snaps_lookup,
                             nfl_defense_context, cfb_elo_progress)
from bta_v07.history import historical_audit,nba_logs_for_player
from bta_v07.injuries import nba_official,college_availability
from bta_v07.playbyplay import fetch_nfl_pbp,audit_nfl_player_plays
from bta_v07.failures import reverse_failure_audit
from bta_v07.calibration import calibrated_holdout
from bta_v07.grading import automatic_candidate_review

st.set_page_config(page_title='BTA | Advanced Research',page_icon='🧠',layout='wide')
st.markdown('''<style>
.stApp{background:#0b101a;color:#e6eef9}
[data-testid="stMetric"]{background:#151d2b;border:1px solid #29354a;border-radius:13px;padding:12px}
div.stButton>button[kind="primary"]{background-color:#1769b5}
</style>''',unsafe_allow_html=True)
st.title('BTA · Advanced Research Workbench')
st.caption('v0.7 research preview • automated historical retrieval when opened • not verified active lineups • no automatic real-money bets')
st.warning('No TAIG/BTA+/BTA picks are approved here. The decision gate withholds final grades until complete sourced evidence, real odds, and independent audit exist.')

@st.cache_data(ttl=21600,show_spinner=False)
def nba_logs(season):return newest_nba_community_logs(season)
@st.cache_data(ttl=21600,show_spinner=False)
def nfl_logs(season):return nfl_weekly_player_stats(season)
@st.cache_data(ttl=21600,show_spinner=False)
def nfl_inj(season):return nfl_injury_reports(season)
@st.cache_data(ttl=21600,show_spinner=False)
def nfl_snaps(season):return nfl_snap_counts(season)
@st.cache_data(ttl=21600,show_spinner=False)
def nfl_sched():return nfl_complete_schedules()
@st.cache_data(ttl=86400,show_spinner=False)
def college_games(year,key):return cfbd_fbs_games(year,key)
@st.cache_data(ttl=21600,show_spinner=False)
def pbp_game(season,player_id):return fetch_nfl_pbp(season,player_id=player_id)
@st.cache_data(ttl=3600,show_spinner=False)
def official_injury(player):return nba_official(player)

def meta(meta):
    st.caption(f'Source: {meta.get("source", "unknown")} · retrieved {meta.get("retrieved_at_utc","unknown")}; '
               'time of retrieval ≠ verified time of game-day availability')

def show_history(report):
    if report['status']=='INSUFFICIENT':
        st.warning(report.get('reason','Insufficient comparable history'));return
    a,b,c=st.columns(3)
    a.metric('Historical sample',str(report['n_games']))
    b.metric('Last 10 hits',f'{report["last_ten_hits"]}/{len(report["last_ten"])}')
    c.metric('Median cushion',str(report['median_clearance_margin']))
    st.caption(f'First three in selected chronological sample: {sum(x["result"]=="WIN" for x in report["sample_first_three"])}/{len(report["sample_first_three"])} '
               '· not a future success probability')
    st.write('Last three historical games')
    st.dataframe(report['recent_three'],hide_index=True,use_container_width=True)
    st.write('Misses to investigate (normal/contextual/structural cause NOT assumed)')
    if report['losses_for_review']:
        st.dataframe(report['losses_for_review'][-12:],hide_index=True,use_container_width=True)
    else:st.caption('No observed misses among eligible games in this sample. Does not imply safety.')
    if report['skipped']:
        st.caption(f'{len(report["skipped"])} historical rows skipped due to missing eligibility/data fields.')


def nfl_player_rows(stats,schedules,player,stat,season,asof):
    candidates=[r for r in stats if str(r.get('player_display_name') or r.get('player_name') or r.get('player') or '').casefold()==player.casefold()
                and str(r.get('season',''))==str(season)]
    by_team_week={}
    for s in schedules:
        if str(s.get('season',''))!=str(season):continue
        try:dt=date.fromisoformat(str(s.get('gameday'))[:10])
        except ValueError:continue
        if dt>=asof:continue
        for t,opp in ((s.get('home_team'),s.get('away_team')),(s.get('away_team'),s.get('home_team'))):
            by_team_week[(str(s.get('week')),t)]=(dt,s.get('game_id'),opp)
    output=[]
    for r in candidates:
        team=r.get('recent_team') or r.get('team');wk=str(r.get('week'))
        game=by_team_week.get((wk,team))
        if game is None:continue
        d,gid,opp=game
        try:value=float(r.get(stat))
        except (ValueError,TypeError):value=None
        output.append({'date':str(d),'game_id':str(gid),'season':season,'opponent':opp,
                       'value':value,'eligible':value is not None, 'team':team,'week':wk,
                       'player_id':r.get('player_id')})
    return output

t1,t2,t3,t4=st.tabs(['NBA · player research','NFL · player and play level','College · FBS','Forecast validation & BTA gates'])
with t1:
    current_year=date.today().year if date.today().month>=7 else date.today().year-1
    nba_season=st.selectbox('NBA season', [f'{current_year}-{str(current_year+1)[-2:]}',f'{current_year-1}-{str(current_year)[-2:]}'],key='v07_season')
    try:
        logs,details=nba_logs(nba_season);meta(details)
        players=sorted(set(r.get('Player') for r in logs if r.get('Player')))
        player=st.selectbox('Player',players,key='v07_nba_player')
        c1,c2,c3=st.columns(3)
        with c1:stat=st.selectbox('Stat', ['Points','Rebounds','Assists'],key='v07_nba_stat')
        with c2:side=st.selectbox('Direction',['OVER','UNDER'],key='v07_nba_side')
        with c3:line=st.number_input('Exact illustrative threshold',min_value=0.,value=20.5,step=.5,key='v07_nba_line')
        asof=st.date_input('Research cutoff (future games excluded)',date.today(),key='v07_nba_asof')
        observations=nba_logs_for_player(logs,player,stat=stat,before=asof)
        report=historical_audit(observations,field=stat,line=line,side=side,before=asof)
        show_history(report)
        if (asof-date.today()).days in (0,1):
            try:
                inj,injmeta=official_injury(player)
                st.write('**Official NBA injury-report lookup**:',inj)
                meta(injmeta)
            except Exception as ex:
                st.warning(f'NBA official report unavailable: {type(ex).__name__}. Player participation UNVERIFIED.')
        else:st.caption('Current injury report not applicable to selected historical date. Requires archived pregame injury snapshot.')
        opp=st.text_input('Optional opponent abbreviation for historical context',key='v07_nba_opp').strip().upper()
        if opp:
            st.write('**Opponent context (not a calibrated probability)**',nba_matchup_context(logs,player,opp,before=asof,stat=stat))
        st.write('**Reverse failure audit**')
        if report.get('losses_for_review'):
            st.write(reverse_failure_audit(losses=report['losses_for_review']))
        st.caption('Upcoming NBA team roster and minutes projections are not verified from this historical snapshot.')
    except Exception as ex:
        st.error(f'NBA source unavailable ({type(ex).__name__}: {str(ex)[:200]}). Cannot create a prediction from missing data.')

with t2:
    season=date.today().year if date.today().month>=8 else date.today().year-1
    season=st.selectbox('NFL season',[season,season-1],key='v07_nfl_year')
    try:
        stats,sm=nfl_logs(season);meta(sm)
        schedule,gm=nfl_sched();meta(gm)
        player_names=sorted({str(r.get('player_display_name') or r.get('player_name') or r.get('player') or '').strip() for r in stats})
        player_names=[p for p in player_names if p]
        player=st.selectbox('NFL player',player_names,key='v07_nfl_player')
        metric=st.selectbox('Stat', ['receiving_yards','rushing_yards','passing_yards','receptions','carries','targets','passing_tds','rushing_tds','receiving_tds'],key='v07_nfl_stat')
        c1,c2=st.columns(2)
        with c1:line=st.number_input('Exact research threshold',value=20.5,min_value=0.,step=.5,key='v07_nfl_line')
        with c2:side=st.selectbox('Side',['OVER','UNDER'],key='v07_nfl_side')
        asof=st.date_input('Pregame research date',date.today(),key='v07_nfl_asof')
        rows=nfl_player_rows(stats,schedule,player,metric,season,asof)
        if rows:
            audit=historical_audit(rows,field='value',line=line,side=side,before=asof)
            show_history(audit)
            player_id=next((r['player_id'] for r in reversed(rows) if r.get('player_id')),None)
            if player_id:st.caption('Observed nflverse player ID: '+str(player_id))
            else:st.warning('Player ID missing; cannot safely join detailed play-by-play')
        else:
            st.warning('No historical appearance rows matched this player/season/schedule. Do not infer zero production.')
            player_id=None
        latest_row=next((r for r in reversed(rows) if r.get('team')),None) if rows else None
        inferred_team=str(latest_row.get('team') if latest_row else '').upper()
        upcoming=[]
        for g in schedule:
            if str(g.get('season'))!=str(season) or inferred_team not in (g.get('home_team'),g.get('away_team')):continue
            try:gd=date.fromisoformat(str(g.get('gameday'))[:10])
            except ValueError:continue
            if gd>=date.today():upcoming.append((gd,int(g.get('week',1)),g))
        upcoming.sort(key=lambda x:x[0])
        inferred_week=upcoming[0][1] if upcoming else min(22,max([int(r['week']) for r in rows if r.get('week')]+[1])+1)
        if upcoming:
            st.caption('Automatically matched upcoming matchup: '+str(upcoming[0][2].get('away_team'))+' @ '+str(upcoming[0][2].get('home_team'))+
                       ' · scheduled '+str(upcoming[0][0])+' (verify game and current roster)')
        week=int(st.number_input('NFL game week (auto-suggested from player team schedule)',min_value=1,max_value=22,
                                 value=max(1,min(22,inferred_week)),key='v07_nfl_week'))
        team=st.text_input('Team code (auto-suggested from historical roster)',value=inferred_team,key='v07_nfl_team').strip().upper()
        try:
            inj,mi=nfl_inj(season);meta(mi)
            st.write('**Weekly injury report, NOT confirmed inactives**',nfl_injury_lookup(inj,player,week,team))
            snaps,ms=nfl_snaps(season);meta(ms)
            st.write('**Prior offensive snap percentages**',nfl_snaps_lookup(snaps,player,before_week=week,team=team))
            if upcoming and team:
                this_game=upcoming[0][2]
                defender=(this_game.get('away_team') if this_game.get('home_team')==team else this_game.get('home_team'))
                names={'receiving_yards':'Receiving yards','rushing_yards':'Rushing yards',
                       'passing_yards':'Passing yards','receptions':'Receptions','targets':'Targets',
                       'passing_tds':'Passing touchdowns','carries':'Rushing attempts'}
                if metric in names:
                    st.write('**Opposing team defense research proxy (not a calibrated matchup forecast)**',
                             nfl_defense_context(stats,snaps,opponent=str(defender),metric=names[metric],before_week=week))
        except Exception as ex:
            st.warning(f'NFL injury/snap source unavailable ({type(ex).__name__}). Participation remains UNVERIFIED.')
        qcol1,qcol2=st.columns(2)
        with qcol1:quarter_stat=st.selectbox('Quarter-specific stat',['RUSH','RECEIVING'],key='v07_quarter_stat')
        with qcol2:quarter_line=st.number_input('At least this many yards in any regulation quarter',value=5.0,min_value=0.0,step=1.0,key='v07_quarter_line')
        if player_id and st.button('Fetch NFL play-by-play (goal line, quarters, explosive plays)',key='v07_pbp'):
            try:
                plays,pp=pbp_game(season,str(player_id));meta(pp)
                profile=audit_nfl_player_plays(plays,player_id=str(player_id),quarter_stat=quarter_stat,quarter_threshold=quarter_line,before_week=week)
                st.session_state['v07_play_profile']=profile
            except Exception as ex:
                st.error(f'Play-by-play unavailable: {type(ex).__name__} — {str(ex)[:120]}.')
        if st.session_state.get('v07_play_profile'):
            p=st.session_state['v07_play_profile']
            if p.get('player_id')==player_id:
                st.write('**Player-level historical play audit**',p)
        st.warning('Play-level dataset may lag games. Receiving plays are not full route/target counts. No automatic touchdown probabilities.')
    except Exception as ex:
        st.error(f'NFL source unavailable ({type(ex).__name__}: {str(ex)[:170]}).')

with t3:
    season=date.today().year if date.today().month>=7 else date.today().year-1
    season=st.selectbox('FBS year',[season,season-1],key='v07_cfb_year')
    key=None
    try:key=st.secrets.get('CFBD_API_KEY')
    except Exception:pass
    if key:
        try:
            games,info=college_games(season,str(key));meta(info)
            before=datetime.now(timezone.utc)
            ratings,predictions=cfb_elo_progress(games,cutoff=before)
            st.write('**Historical chronological Elo forecasts (raw research model)**')
            st.dataframe(predictions[-30:],hide_index=True,use_container_width=True)
            st.caption(f'Team ratings calculated: {len(ratings)}. These exclude unplayed games, and do not establish a moneyline edge.')
        except Exception as ex:st.warning(f'CFBD FBS data unavailable ({type(ex).__name__}: {str(ex)[:160]}).')
    else:
        st.warning('Add CFBD_API_KEY to Streamlit Secrets once to enable automatic FBS history. Never put it into public GitHub code.')
        st.markdown('[CollegeFootballData key setup](https://api.collegefootballdata.com/authentication)')
    st.write('**College participation:**', college_availability('Any team'))
    st.caption('BTA college moneyline uses its separate five scripts: normal, underdog early lead, -2 turnover battle, strength neutralized, one-score fourth. Spread and total advanced models remain unvalidated.')

with t4:
    st.subheader('Prospective probability calibration')
    file=Path('bta_snapshots/pregame_forecasts.jsonl')
    if file.exists():
        try:
            with file.open(encoding='utf-8') as fh:
                records=[json.loads(x) for x in fh if x.strip()]
            result=calibrated_holdout(records)
            st.write(result)
        except Exception as ex:st.warning(f'Forecast snapshots invalid: {type(ex).__name__}; no calibration proven.')
    else:
        st.warning('No saved timestamped pregame forecast ledger exists. Historical final results cannot be retroactively labeled pregame predictions.')
        st.caption('v0.7 includes a validator and schema, but a future automatic pregame forecast scheduler and actual sportsbook historical line snapshots must still be connected.')
    st.subheader('Automatic candidate eligibility')
    st.caption('This displays conservative blockers for unverified data. It will not manufacture an automated BTA label.')
    selected_family=st.selectbox('Market family',['NBA_PROP','NFL_PROP','CFB_MONEYLINE'],key='v07_gate_family')
    grade=automatic_candidate_review({'family':selected_family,'event_id':'not-connected',
       'event_start_utc':'2030-01-01T00:00:00Z','scenarios':[]})
    st.write(grade)
    st.caption('The real automatic grader must be supplied with event-specific provenance, verified offer, game-day availability, source-linked script mechanisms and independently audited model evidence.')
