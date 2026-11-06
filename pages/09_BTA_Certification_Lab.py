"""BTA 1.1 evidence lab, fail-closed by design. No live betting or guaranteed picks."""
from __future__ import annotations
import os
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import streamlit as st
from bta_v11.orchestrator import gather
from bta_v11.certification import REQUIRED_GATES

st.set_page_config(page_title='BTA | Certification Lab',page_icon='🔎',layout='wide',initial_sidebar_state='collapsed')
st.markdown('''<style>
.stApp{background:#080f1d;color:#e8f0fd}
[data-testid="stSidebar"]{background:#101c31}
div[data-testid="stMetric"]{background:#14233b;border:1px solid #263e5c;border-radius:13px;padding:12px}
.stButton button{border-radius:11px} h1,h2,h3{color:#f3f8ff}
</style>''',unsafe_allow_html=True)
st.title('BTA · CERTIFICATION LAB')
st.caption('Game-day participation · Verified routes/snaps · CFBD roster continuity · Authenticated settlements · Model calibration · Dependent parlays')
st.warning('This is the certification workbench, not proof that data providers have confirmed any lineup or that forecast models are calibrated. Incomplete evidence prevents an automatic grade.')
now=datetime.now(timezone.utc)
today=now.astimezone(ZoneInfo('America/New_York')).date()
with st.sidebar:
    st.header('Current automatic feeds')
    league=st.selectbox('League',['NBA','NFL','College football'])
    st.caption(f'Date: {today.isoformat()} (Eastern), automatic each day')
    st.caption('API credentials are read from environment variables and never displayed.')
    if st.button('Refresh schedules now'):
        st.cache_data.clear();st.rerun()

@st.cache_data(ttl=180,show_spinner=False)
def auto_games(sport,day):
    from bta_v08.schedule import collect,next_days
    return collect(sport,next_days(day,horizon=3))

try:
    slate=auto_games(league,today)
except Exception as exc:
    slate={'games':[],'complete':False,'errors':[{'error':type(exc).__name__}]}

col1,col2,col3=st.columns(3)
col1.metric('Games retrieved',len(slate['games']))
col2.metric('Schedule coverage','OK' if slate.get('complete') else 'CHECK FEED')
col3.metric('Auto-certified picks',0)
if not slate.get('complete'):st.error('Schedule provider incomplete; missing games are not assumed unscheduled.')

tabs=st.tabs(['Automatic game evidence','Six certification blockers','Quality requirements','Parlay validation'])
with tabs[0]:
    if slate['games']:
        options=list(range(len(slate['games'])))
        idx=st.selectbox('Upcoming / live / completed matchup', options,
            format_func=lambda i:f"{slate['games'][i]['away']['name']} @ {slate['games'][i]['home']['name']} — {slate['games'][i]['status']}")
        ev=slate['games'][idx]
        stamp=ev.get('start_utc',''); st.caption(f"Kickoff/tipoff UTC: {stamp} | Provider: {ev.get('source','?')}")
        st.write('**Research identity:**',ev['event_key'])
        if ev['status']!='UPCOMING':st.warning('Not eligible for a new pregame forecast.')
        player=st.text_input('Optional player ID for provider-matched availability',placeholder='Leave empty for game-market research')
        team=st.selectbox('Team for roster/role matching',[ev['home']['name'],ev['away']['name']])
        if st.button('Retrieve current event evidence',type='primary'):
            with st.spinner('Reading supported provider feeds...'):
                data=gather(league=league,event=ev,player_id=player,team=team,now=now.isoformat())
            st.subheader('Evidence result')
            st.json(data)
            if data.get('blockers'):st.error('Final BTA certification withheld: required evidence still missing.')
    else:st.info('Schedule source returned no games for the next three Eastern calendar days.')
with tabs[1]:
    st.subheader('The six remaining source / validation requirements')
    st.markdown('''
**1. Game-day starter/active verification:** licensed provider plus exact event/player identity. An injury report or roster entry is never an automatic ACTIVE designation.

**2. NFL snaps and charted routes:** snap-count data retrieved from nflverse; routes require licensed in-season charting and validated stable player IDs. Dropback participation is not a measured route.

**3. College roster continuity:** CFBD provides official API access to season rosters, not confirmed active day-of-game participants or confirmed quarterbacks.

**4. Exact sportsbook settlement:** match bookmaker, event ID, threshold, market period, rule version and settlement timestamp. Third-party graded results are not authenticated FanDuel settlements.

**5. Out-of-time probability testing:** preserve immutable pregame snapshots; hold out later dates and distinct events; reject future-data leakage and duplicate outcomes.

**6. Joint parlay forecasts:** require paired outcomes or a separately validated conditional dependence model. No default multiplication of leg probabilities.
''')
    st.caption('Each external provider depends on access rights, reliable coverage, historical data quality, and future live testing.')
with tabs[2]:
    st.subheader('Automatic BTA+ quality gates')
    for gate in REQUIRED_GATES:
        st.write('◻',gate.replace('_',' ').capitalize())
    st.info('The assessment function can output a qualified research grade only when all gates have real independently verified inputs. TAIG requires exceptional additional review.')
    st.code('from bta_v11.certification import assess\n# Pass real verified evidence, five scripts, availability and holdout diagnostics.',language='python')
with tabs[3]:
    st.subheader('Dependence-aware forecasts')
    st.markdown('Historical paired results are descriptive. For a new parlay, a future joint probability requires calibrated pregame scenario probabilities and externally tested joint-outcome dependence.')
    st.code('from bta_v11.parlay import joint_historical, conditional_scenarios',language='python')
    st.info('Until enough authenticated, comparable past parlays are observed, the output is insufficient history, not a made-up 99% success estimate.')

st.divider()
st.caption('No wager is placed. Do not publish private sportsbook feeds, API keys, or account settlement records in a public GitHub repository.')
