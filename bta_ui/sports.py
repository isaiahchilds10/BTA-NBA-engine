"""Shared styled sports hub with actual schedule data; research values are never invented."""
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st
from bta_ui.theme import apply_theme,brand_header,section

LEAGUE_INFO = {
    'NBA': ('NBA Intelligence', 'Pro basketball · slate and research', 'NBA games, opponent context, and verified participation when connected.'),
    'NFL': ('NFL Intelligence', 'Pro football · usage and game scripts', 'NFL schedules, player workload checks, defensive context, and five-script stress tests.'),
    'College football': ('College Football Intelligence', 'FBS football · rosters and moneylines', 'College schedules, roster continuity, matchup context, and five-script moneyline stress tests.'),
}

@st.cache_data(ttl=180,show_spinner=False)
def _slate(league: str, local_day: str):
    from datetime import date
    from bta_v08.schedule import collect,next_days
    return collect(league,next_days(date.fromisoformat(local_day),horizon=3))


def _display_event(event:dict)->None:
    home=event.get('home') or {}; away=event.get('away') or {}
    st.write(f"**{away.get('name') or 'Away team'}**  @  **{home.get('name') or 'Home team'}**")
    # Scores are displayed only if the provider actually supplies them.
    away_score=away.get('score'); home_score=home.get('score')
    if away_score is not None and home_score is not None:
        st.markdown(f"**Score: {away_score} – {home_score}**")
    status=event.get('status') or 'UNKNOWN'
    start=event.get('start_utc')
    time_label='Time not confirmed'
    if isinstance(start,str):
        try:
            instant=datetime.fromisoformat(start.replace('Z','+00:00'))
            time_label=instant.astimezone(ZoneInfo('America/New_York')).strftime('%a %b %d, %I:%M %p ET')
        except (ValueError,OverflowError): pass
    st.caption(f"{status} • {time_label} • ESPN schedule feed (unofficial)")


def render(league:str):
    if league not in LEAGUE_INFO:
        raise ValueError('Unknown sport')
    title,kicker,description=LEAGUE_INFO[league]
    st.set_page_config(page_title=f'BTA | {league}',page_icon='🥊',layout='wide',initial_sidebar_state='expanded')
    apply_theme()
    brand_header(title=title,kicker=kicker,description=description)
    st.markdown('<span class="bta-chip">Real schedule feed · subject to availability</span>'
                '<span class="bta-chip">Research grades require verified evidence</span>',unsafe_allow_html=True)
    section('SCHEDULE & MATCHUPS')
    local_day=datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    top_left,top_right=st.columns([3,1])
    with top_left: st.caption('3-day schedule window • times shown in Eastern Time • ESPN feed may be delayed or incomplete')
    with top_right:
        if st.button('Refresh schedule',icon=':material/refresh:',use_container_width=True):
            _slate.clear();st.rerun()
    try:
        slate=_slate(league,local_day)
    except Exception as e:
        slate={'games':[],'complete':False,'errors':[{'error':type(e).__name__}]}
    games=slate.get('games') or []
    if not slate.get('complete',False):
        st.warning('The schedule feed is incomplete or unavailable. Missing games are not assumed to be off the schedule.')
    if games:
        options=['All games','Upcoming','Live','Final']
        filter_status=st.segmented_control('Filter games',options,default='All games',label_visibility='collapsed')
        shown=games if filter_status=='All games' else [g for g in games if g.get('status','').upper()==filter_status.upper()]
        st.caption(f'{len(shown)} displayed of {len(games)} received')
        for ev in shown:
            with st.container(border=True):_display_event(ev)
        if not shown:st.info('No games match that filter in the retrieved schedule.')
    else:
        st.info('No games returned by the schedule provider in this 3-day window.')

    section('DEEP RESEARCH')
    a,b=st.columns(2)
    with a:
        with st.container(border=True):
            st.markdown('#### Evidence & model analysis')
            st.caption('Historical player/team statistics, source quality and matchup research.')
            st.page_link('pages/05_BTA_Advanced_Research.py',label='Open advanced research',icon=':material/arrow_forward:',use_container_width=True)
            st.page_link('pages/02_BTA_Evidence_and_Model_Lab.py',label='Open evidence lab',icon=':material/arrow_forward:',use_container_width=True)
    with b:
        with st.container(border=True):
            st.markdown('#### BTA+ verification')
            st.caption('Check data freshness, roster status, scripts, settlements and future-model validation.')
            st.page_link('pages/09_BTA_Certification_Lab.py',label='Open certification lab',icon=':material/verified_user:',use_container_width=True)
            st.page_link('pages/08_BTA_Risk_and_Integrity.py',label='Open risk & integrity',icon=':material/shield:',use_container_width=True)
    st.caption('A schedule listing does not verify starters, player availability, line prices, probability calibration or a qualified BTA+ pick.')
