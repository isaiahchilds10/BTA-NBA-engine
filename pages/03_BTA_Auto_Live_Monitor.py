"""BTA live monitor v0.6. Streams attributed *observations*, not bets.
Run alongside v0.4/v0.5 Streamlit pages. Requires streamlit>=1.43.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from bta_v06.live import nba_monitor, nba_boxscore, espn_schedule, gate_freshness

st.set_page_config(page_title='BTA | Auto Live Monitor', page_icon='📡', layout='wide')
st.markdown('''<style>
.stApp {background: #0d121c; color: #e8eef8;}
div[data-testid="stMetric"] {background:#182235; border:1px solid #2d3d55; padding:12px; border-radius:10px;}
</style>''', unsafe_allow_html=True)
st.title('BTA • Automatic Live Monitor')
st.caption('Source-attributed schedules, statuses and NBA box scores. No odds feed, automatic bet placement or BTA grades.')

@st.cache_data(ttl=120, show_spinner=False)
def get_nba():
    return nba_monitor()

@st.cache_data(ttl=120, show_spinner=False)
def get_espn(league, day):
    return espn_schedule(league, day)

@st.cache_data(ttl=90, show_spinner=False)
def get_box(game_id):
    return nba_boxscore(game_id)


def show_games(data, league):
    if data.get('status')!='OK':
        st.warning(f'{league}: UNVERIFIED — provider could not be read.')
        return
    st.caption(f'Source: {data["source"]} · retrieved {data["retrieved_at_utc"]}')
    if not data['games']:
        st.info('No games reported by this source for the selected day. This is not a claim that no games exist anywhere.')
    else:
        display=[]
        for g in data['games']:
            display.append({'UTC date':g.get('date_utc'),'Game':f'{g.get("away")} @ {g.get("home")}',
                            'State':g.get('state'),'Away score':g.get('away_score'),'Home score':g.get('home_score')})
        st.dataframe(display,hide_index=True,use_container_width=True)

@st.fragment(run_every='120s')
def auto_monitor():
    asof=datetime.now(timezone.utc)
    st.caption(f'Automatic refresh while this dashboard is open · checked {asof.strftime("%Y-%m-%d %H:%M UTC")}.')
    today=asof.strftime('%Y%m%d')
    tabs=st.tabs(['NBA · official live','NFL · scoreboard','College football · scoreboard'])
    with tabs[0]:
        try:
            result=get_nba()
            st.write(f'**NBA date:** {result["date"]} · {result.get("provider_quality","")}')
            st.caption(f'Retrieved {result["retrieved_at_utc"]} · freshness: {gate_freshness(result["retrieved_at_utc"],asof,5)}')
            show_games(result,'NBA')
            if result['date']!=asof.date().isoformat():
                st.warning('NBA source date differs from UTC today; do not treat these as today’s fixtures without confirming time zone.')
            games=result['games']
            if games and result.get('provider_quality') == 'NBA OFFICIAL LIVE CDN':
                chosen=st.selectbox('Optional NBA game for official live player box score', games,
                    format_func=lambda g:f'{g["away"]} @ {g["home"]} • {g["state"]}',key='v06_game')
                try:
                    box=get_box(chosen['id'])
                    st.caption('Official box score: '+box['source']+' · fetched '+box['retrieved_at_utc'])
                    st.dataframe(box['players'], hide_index=True,use_container_width=True)
                    st.warning('NBA box scores contain in-game information. Do not leak these results into a pregame model.')
                except Exception as ex:
                    st.warning(f'Official NBA player box score unavailable: {type(ex).__name__}. No substitute player stats used.')
            elif games:
                st.warning('NBA official source unavailable. ESPN fallback shows games only; official player boxes not fetched.')
        except Exception as ex:
            st.error(f'NBA official live data UNVERIFIED: {type(ex).__name__}: {str(ex)[:160]}')
    with tabs[1]:
        try:show_games(get_espn('NFL',today),'NFL')
        except Exception as ex:st.error(f'NFL feed UNVERIFIED: {type(ex).__name__}: {str(ex)[:160]}')
    with tabs[2]:
        try:show_games(get_espn('College football',today),'College football')
        except Exception as ex:st.error(f'College feed UNVERIFIED: {type(ex).__name__}: {str(ex)[:160]}')

st.info('Historical NBA player logs and NFL weekly injuries/snaps already auto-fetch in v0.5. '
        'This page covers current scores and NBA live box scores; it does not replace official injury/inactive or role checks.')
auto_monitor()

st.subheader('Unattended background status')
snapshot=Path('bta_snapshots/current.json')
if snapshot.exists():
    try:
        payload=json.loads(snapshot.read_text(encoding='utf-8'))
        if payload.get('schema_version')!=1 or not isinstance(payload.get('sources'),dict):
            raise ValueError('Invalid snapshot schema')
        stamp=payload.get('captured_at_utc')
        st.caption(f'Last GitHub scheduled snapshot: {stamp}. Hourly is best effort, not continuous live tracking.')
        for name,record in payload['sources'].items():
            flag=gate_freshness(stamp,datetime.now(timezone.utc),180)
            st.write(f'{name}: **{record.get("status","UNVERIFIED")}** · {flag}')
    except (ValueError,UnicodeError) as err:
        st.warning(f'Background snapshot cannot be verified: {err}')
else:
    st.caption('No unattended snapshot yet; first GitHub workflow run must complete after deployment.')
st.warning('Not a calibrated prediction or betting recommendation. A live box score is never evidence for a supposedly pregame forecast.')
