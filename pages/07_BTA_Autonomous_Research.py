"""BTA v0.9 — automatically refreshed, research-only command dashboard.

Add after installing v0.4-v0.8. This is not an automatic wagering program.
"""
from __future__ import annotations
import json,os
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import streamlit as st
from bta_v09.pipeline import collect_research
from bta_v09.parlay import uncertainty_bounds
from bta_v09.calibration import validate_archive
from bta_v09.health import snapshot_age

st.set_page_config(page_title='BTA | Autonomous Research',page_icon='🔎',layout='wide',initial_sidebar_state='collapsed')
st.markdown('''<style>
.stApp {background:#080f1a;color:#e8f0fc}
[data-testid="stSidebar"] {background:#111c2c}
div[data-testid="stMetric"] {background:#112036; border:1px solid #274461; padding:14px; border-radius:13px}
div[data-testid="stExpander"] {background:#101c2c; border:1px solid #274461; border-radius:12px}
.stButton>button {border-radius:10px}
</style>''',unsafe_allow_html=True)
TZ=ZoneInfo('America/New_York')


def _secret(key):
    try:return str(st.secrets.get(key,'') or '').strip()
    except (KeyError,FileNotFoundError,OSError):return ''


def _load_json(path:Path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError,ValueError,OSError):return None


def _load_jsonl(path:Path):
    if not path.exists():return []
    try:return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]
    except (OSError,ValueError):return []


@st.cache_data(ttl=900,show_spinner=False,scope='session')
def _live_refresh(has_secret:bool,key:str):
    # In-memory only. No key or licensed market content written to GitHub.
    return collect_research(cfbd_key=_secret("CFBD_API_KEY"),
                            odds_key=key if has_secret else '',
                            include_props=_secret("BTA_ENABLE_PROPS")=="1",
                            save_market_details=has_secret)


st.title('BTA · AUTONOMOUS RESEARCH')
st.caption('Automatic game discovery · source freshness · preliminary exact-market research · zero fake BTA approvals')
now=datetime.now(timezone.utc).astimezone(TZ)
with st.sidebar:
    st.header('Data controls')
    source=st.radio('Data view',('Live refresh','Last scheduled snapshot'),index=0)
    league=st.selectbox('League',('All sports','NBA','NFL','College football'))
    show_all=st.checkbox('Include completed games',value=False)
    st.caption('Live refresh may consume odds-provider quota if an API key is connected.')
    if st.button('Refresh now'):
        _live_refresh.clear();st.rerun()
key=_secret('BTA_ODDS_API_KEY') if _secret('BTA_PRIVATE_DASHBOARD')=='1' else ''
if not key:
    st.info('Schedules and historical-source checks need no manual stats. Exact current offers and props require an authorized market API key, applicable provider tier, and access-controlled dashboard.')
    st.caption('Market feed is disabled on public dashboards. BTA_PRIVATE_DASHBOARD=1 is an operator flag, NOT an authentication mechanism; use access controls before enabling it.')
else:
    st.caption('A market API key is configured. Prices shown below are provider snapshots, not a confirmed executable sportsbook ticket.')

@st.fragment(run_every='7m')
def show_live():
    if source=='Live refresh':
        with st.spinner('Refreshing league feeds and historical source status…'):
            snap,_=_live_refresh(bool(key),key)
    else:
        snap=_load_json(Path('bta_snapshots/v09/latest.json'))
    if not snap:
        st.warning('No scheduled v0.9 snapshot found. Run the v0.9 scheduled workflow or switch to Live refresh.')
        return
    stamp=snap.get('built_at_utc')
    age=snapshot_age(stamp, now=datetime.now(timezone.utc))
    st.caption(f'Collected at: {stamp} UTC · Snapshot: {age["status"]} ({age.get("age_minutes")} min)')
    st.caption('Research-only snapshot. Different sources have different release times. Do not interpret absence of a report as confirmed health.')
    leagues=snap.get('leagues',{})
    for name,content in leagues.items():
        if league!='All sports' and name!=league:continue
        items=content.get('games',[])
        events=[g for g in items if show_all or g['status']!='FINAL']
        st.markdown(f'### {"🏀" if name=="NBA" else "🏈" if name=="NFL" else "🎓"} {name}')
        left,mid,right=st.columns(3)
        left.metric('Games',len(events))
        mid.metric('Provider errors',len(content.get('source_errors',[])))
        right.metric('Stat rows checked',content.get('historical_rows_loaded',0))
        st.caption('Bookmaker feed: '+content.get('market_status','NOT CONNECTED')+' · Dated stat sources: '
                   +str(len(content.get('history_sources',[]))))
        if content.get('source_errors'):
            st.warning('Incomplete game schedule. Provider failures are disclosed; missing games are not treated as no games.')
        if content.get('history_publication_audit'):
            st.caption('Stat publication check: '+str(content['history_publication_audit']))
        if content.get('history_sources'):
            with st.expander('Historical data sources and freshness'):
                st.dataframe(content['history_sources'],hide_index=True,use_container_width=True)
        if not events:st.write('No games returned for this window. This is not proof the league has no games.');continue
        for game in events:
            label=f"{game['away']} @ {game['home']} · {game['status']}"
            with st.expander(label,expanded=game['status']=='LIVE'):
                start=game['start_utc']
                try:when=datetime.fromisoformat(start.replace('Z','+00:00')).astimezone(TZ)
                except ValueError:when=None
                st.caption(f"{when.strftime('%a %b %d, %I:%M %p ET') if when else start} · Provider event {game['event_key']}")
                if game.get('source'):st.caption('Source: '+game['source'])
                if game.get("team_strength_research"):
                    st.caption("College model research: "+game["team_strength_research"].get("status","UNKNOWN"))
                    with st.expander("CFBD prior-game team-strength research"):
                        st.json(game["team_strength_research"])
                candidates=game.get('research_leads',[])
                if candidates:
                    # Prioritize records with historical context. Still PENDING, never BTA+.
                    shown=sorted(candidates,key=lambda x:bool(x.get('experimental_model',{}).get('status')=='EXPERIMENTAL_UNCALIBRATED'),reverse=True)[:3]
                    for item in shown:
                        title=(str(item.get('player') or item.get('market'))+' '+str(item.get('selection',''))+' '+str(item.get('line','')))
                        st.markdown('**'+title+'**')
                        st.caption(f"{item.get('grade','PENDING')} · {item.get('bookmaker','provider')} · quote {item.get('provider_time','time unavailable')}")
                        pilot=item.get('experimental_model',{})
                        if pilot.get('experimental_probability') is not None:
                            st.caption(f"Experimental uncalibrated baseline: {pilot['experimental_probability']:.1%} · sample {pilot['wins']}/{pilot['wins']+pilot['losses']} decided · NOT a verified chance")
                        with st.expander('Why this is not BTA+'):st.write(item.get('missing') or ['No independently verified game-specific BTA audit'])
                else:
                    st.caption('No qualified automatic selection. No market offers or required evidence may be available. No invented recommendations.')

show_live()
st.divider()
st.subheader('Parlay exposure audit')
st.caption('Reads the candidate slip from the v0.8 page in this session. Unverified legs cannot produce a credible combined win percentage.')
slip=list(st.session_state.get('v08_slip',{}).values())
if slip:
    st.dataframe(slip,hide_index=True,use_container_width=True)
    legs=[{**x,'event':x.get('event'),'probability':x.get('calibrated_win_probability'),
           'calibrated':False,'verified_market':False} for x in slip]
    st.json(uncertainty_bounds(legs))
else:st.info('No research legs saved in your v0.8 session.')
st.divider()
st.subheader('Prospective calibration audit')
forecasts=_load_jsonl(Path('bta_snapshots/v09/forecast_journal.jsonl'))
settlements=_load_jsonl(Path('bta_snapshots/v09/verified_settlements.jsonl'))
st.caption(f'{len(forecasts)} archived pregame model forecasts · {len(settlements)} independent verified settlements')
if forecasts and settlements:
    st.json(validate_archive(forecasts,settlements))
else:
    st.info('Calibration is not established. The system must first save many genuine pregame forecasts and match them to independently verified results and market settlements. Do not upload made-up outcomes.')
st.divider()
st.caption('This is an offline-tested research workflow. Data connectors, paid access, complete injuries, role tracking, causal scripts and real out-of-sample performance remain to be verified after deployment.')
