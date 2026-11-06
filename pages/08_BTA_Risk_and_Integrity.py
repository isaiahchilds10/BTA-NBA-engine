"""BTA v1.0 risk and data-integrity workbench.

This page is an *automatic slate + research status* interface, not a predictor.
It consumes current schedules from the existing v0.8 provider and optional
v0.9 snapshots. Risk calculations never promote a pick to TAIG/BTA+.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import streamlit as st
from bta_v08.schedule import collect,next_days
from bta_v10.portfolio import shared_risk,joint_bounds
from bta_v10.performance import grade_report
from bta_v10.regrade import freshness_veto
from bta_v10.pipeline import audit_auto_snapshot
from bta_v10.adapters import nba_team_observations,nfl_team_observations
from bta_v09.health import source_age

st.set_page_config(page_title='BTA | Risk & Integrity',page_icon='🛡️',layout='wide',initial_sidebar_state='collapsed')
st.markdown('''<style>
.stApp{background:#08111f;color:#e3ecfa}
[data-testid="stSidebar"]{background:#0d192a}
div[data-testid="stMetric"]{background:#142339;border:1px solid #28435f;border-radius:14px;padding:13px}
div[data-testid="stExpander"]{background:#101d30;border:1px solid #2b405a;border-radius:12px}
.stButton>button{border-radius:10px}
h1,h2,h3{color:#f4f9ff}
</style>''',unsafe_allow_html=True)
ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo('America/New_York')

@st.cache_data(ttl=180,show_spinner=False)
def _slate(league:str,days:int,start_day:str):
    from datetime import date
    return collect(league,next_days(date.fromisoformat(start_day),horizon=days))

@st.cache_data(ttl=180,show_spinner=False)
def _read_public_snapshot():
    path=ROOT/'bta_snapshots'/'v09'/'latest.json'
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return None

@st.cache_data(ttl=1800,show_spinner=False)
def _auto_history(league:str,asof_iso:str):
    # Reuses existing source adapters; no manual CSV entry. Bad provider data are
    # exposed as errors or missing observations, never replaced with examples.
    from bta_v09.pipeline import _histories
    return _histories(league,datetime.fromisoformat(asof_iso))

st.title('BTA · RISK & INTEGRITY')
st.caption('Source accountability · Research vetoes · Multi-sport opportunity checks · Parlay shared-risk analysis')
st.warning('This workbench cannot certify automatic TAIG/BTA+ picks or calibrated parlay chances. Missing evidence blocks approval. No automatic betting.')
now=datetime.now(timezone.utc)
with st.sidebar:
    st.header('Research controls')
    league=st.selectbox('Sport',['NBA','NFL','College football'])
    horizon=st.selectbox('Upcoming days',[1,3,5,7],index=1)
    today=now.astimezone(TZ).date()
    st.caption('Date updates automatically each day; timestamps are Eastern.')
    if st.button('Refresh provider now'):
        _slate.clear();_read_public_snapshot.clear();st.rerun()

try:
    slate=_slate(league,horizon,today.isoformat())
except Exception as exc:
    slate={'games':[],'errors':[{'error':type(exc).__name__}],'source_logs':[],'complete':False}

public=_read_public_snapshot()
tabs=st.tabs(['Automatic games','Source integrity','Opportunity research','Red Team & BTA gates','Parlay risk','Performance & settlement'])
with tabs[0]:
    events=slate.get('games',[])
    c1,c2,c3=st.columns(3)
    c1.metric('Events returned',len(events))
    c2.metric('Live',sum(g.get('status')=='LIVE' for g in events))
    c3.metric('Feed failures',len(slate.get('errors',[])))
    if not slate.get('complete'):
        st.error('Schedule feed is incomplete or unavailable. A missing game is NOT evidence it is not scheduled.')
    if not events:st.info('No records were returned from the feed for this date window.')
    for event in events:
        h=event.get('home',{});a=event.get('away',{})
        time_utc=event.get('start_utc')
        from bta_v10.common import utc
        kickoff=utc(time_utc)
        when=kickoff.astimezone(TZ).strftime('%a %b %d · %I:%M %p ET') if kickoff else 'TIME UNKNOWN'
        with st.expander(f"{a.get('name','Unknown')} @ {h.get('name','Unknown')}  ·  {event.get('status','?')}"):
            st.write(when)
            st.caption(f"Event: {event.get('event_key','unknown')} | Retrieved: {event.get('retrieved_at_utc','unknown')} | Provider: {event.get('source','unknown')}")
            if event.get('status')=='UPCOMING':
                st.info('Automatic BTA evidence check: PENDING. No live verified injury/role/market/calibration packet attached here.')
            else:st.caption('This game is no longer eligible for a newly constructed pregame prediction.')
            st.caption('Current and full historical statistics are researched in the v0.9 Autonomous Research tab. This is a separate adversarial quality-control screen.')
    if slate.get('errors'):st.json(slate['errors'])
with tabs[1]:
    st.subheader('Source status')
    st.caption('Publication time, observed time and retrieval time are different. A successful network request is not sufficient evidence.')
    for meta in slate.get('source_logs',[]):
        if isinstance(meta,dict):
            st.write(f"{meta.get('source','Unknown feed')} · retrieved: {meta.get('retrieved_at_utc','unknown')}")
    if public:
        st.success('A v0.9 snapshot file is available.')
        st.json({'built_at_utc':public.get('built_at_utc'),'model_validation':public.get('model_validation'),
                 'auto_ticket':public.get('auto_ticket'),'market_details_persisted':public.get('market_details_persisted')})
        for name,row in public.get('leagues',{}).items():
            if name==league and isinstance(row,dict):
                st.write('Historical publication audit')
                st.json(row.get('history_publication_audit',{}))
                st.write('Injury source status')
                st.json(row.get('injury_source',{}))
        audit=audit_auto_snapshot(public)
        rows=[r for r in audit.get('games',[]) if r['league']==league]
        st.write(f'Automatic per-game research audit: {len(rows)} events')
        for r in rows[:30]:
            with st.expander(f"{r['event_key']} — {r['status']}"):
                for reason in r['blockers']:st.caption('• '+reason)
    else:st.info('No v0.9 scheduled snapshot found. Open the v0.9 research page to fetch current sources; do not substitute manual fictional stats.')
    st.markdown('**Mandatory evidence reconciliation before a high grade:** event/identity, official injury and active status, role, current coaching, opposing personnel, market quote, and pregame feature timestamps.')
with tabs[2]:
    st.subheader('Opportunity-first research')
    explanations={
        'NBA':'Minutes trend, starting rotation, usage/shot opportunities, possessions, rest, foul and blowout exposure, teammate-on/off changes.',
        'NFL':'Snap/route/carry participation, target share, neutral-script tendencies, quarterback and offensive-line changes, red-zone opportunities.',
        'College football':'Verified starting QB, coach, transfers/returning starters, efficiency adjusted for comparable opponents, OL/DL and special teams.'}
    st.write(explanations[league])
    st.info('The new adapter automatically loads existing v0.9 statistics when available. A role summary is descriptive; current starting status and unavailable route/snap metrics remain unverified.')
    if events and league in ('NBA','NFL'):
        selection=st.selectbox('Select scheduled matchup for an automatic research audit',
            options=list(range(len(events))),format_func=lambda idx:f"{events[idx]['away']['name']} @ {events[idx]['home']['name']}")
        with st.spinner('Retrieving available dated player history from the existing data sources...'):
            try: history,meta=_auto_history(league,now.replace(minute=0,second=0,microsecond=0).isoformat())
            except Exception as exc:
                history=[];meta=[{'status':'SOURCE ERROR','error_class':type(exc).__name__}]
        st.caption(f'{len(history)} history records returned · Automatic retrieval · Source coverage may lag current games')
        if meta:
            with st.expander('Source publication audit'):
                st.json([{k:v for k,v in item.items() if k not in ('raw','token','authorization')} for item in meta])
        research=nba_team_observations(events[selection],history) if league=='NBA' else nfl_team_observations(events[selection],history)
        if research.get('players'):
            st.dataframe(research['players'][:24],use_container_width=True,hide_index=True)
        else:
            st.warning('No sufficiently comparable player history could be verified for this matchup; no synthetic data substituted.')
        st.caption(research.get('note','Role data requires stable event and player IDs.'))
    elif league=='College football':
        st.caption('College game strength from CFBD historical FBS results is available through v0.9 when a key is configured; this page does not invent roster/coach/transfer data.')
        if public:
            for g in (public.get('leagues',{}).get('College football',{}).get('games') or [])[:15]:
                if g.get('team_strength_research'):
                    with st.expander(str(g.get('event_key'))):st.json(g['team_strength_research'])

    st.code('from bta_v10.opportunity import nba_rotation, nfl_role, college_continuity, opponent_adjusted',language='python')
with tabs[3]:
    st.subheader('Independent disconfirmation and veto checks')
    for title,meaning in [
        ('Source conflict veto','Contradictory source observations cannot be averaged into certainty.'),
        ('Material news veto','Injury, quarterback, rotation, coach, kickoff or exact-line changes invalidate older grades.'),
        ('Five-script veto','Two meaningful WORSE scripts cut player props; unknown scripts block grading.'),
        ('Prospective forecast veto','Research after kickoff cannot backfill a pregame pick.'),
        ('Model quality veto','A high old hit rate is not calibrated probability evidence.'),
        ('Independent review','One positive model cannot certify its own independent second-pass review.')]:
        st.markdown(f'**{title}** — {meaning}')
    st.warning('CURRENT DEFAULT: NO CERTIFIED PICKS. The red-team engine produces pending or rejected states until an independently verifiable evidence packet exists.')
with tabs[4]:
    st.subheader('Parlay research slip — shared failure paths')
    try:
        session_slip=list(st.session_state.get('v08_slip',{}).values())
    except (KeyError,TypeError,AttributeError):session_slip=[]
    st.write(f'Existing v0.8 research-slip legs available in this session: {len(session_slip)}')
    if session_slip:
        legs=[]
        for o in session_slip:
            legs.append({'event_key':o.get('event'),'player_id':o.get('player'),'team_id':o.get('team_id'),
                         'market_id':str(o.get('event'))+':'+str(o.get('market'))+':'+str(o.get('player'))+':'+str(o.get('line'))})
        st.json(shared_risk(legs))
    else:st.info('Add candidates to the existing v0.8 research slip in this Streamlit session to see overlap flags.')
    st.caption('No numerical joint chance is shown without validated individual probabilities and credible dependence evidence. Same-game/same-player flags do not exhaust every common cause.')
with tabs[5]:
    st.subheader('Prospective grading / settlement archive')
    st.info('Only forecasts recorded before kickoff and matched to externally verified settlements should count toward real grade performance.')
    p=ROOT/'bta_snapshots'/'v09'/'forecast_journal.jsonl'
    if p.exists():
        count=0
        try:
            with p.open(encoding='utf-8') as f:
                for line in f:
                    if line.strip():count+=1
            st.metric('Archived forecast records (not necessarily settled)',count)
        except OSError:st.warning('Cannot read forecast archive')
    else:st.caption('No privately archived forecast journal is mounted here.')
    st.caption('Automatic settlement requires a licensed/authorized exact-platform resolution source, including injury void/push and participation rules.')
