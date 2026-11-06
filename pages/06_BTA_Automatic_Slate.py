"""BTA v0.8 Automatic Slate & Research Leads — REVIEW BUILD.

Add as a new Streamlit page AFTER v0.4–v0.7. Do not change app.py.
This is automated slate discovery + exact offered market research, NOT
fully autonomous BTA+/TAIG selection or a real-money betting interface.
"""
from __future__ import annotations
import json
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from zoneinfo import ZoneInfo

import streamlit as st
from bta_v08.schedule import collect, game_counts, next_days, parse_instant, augment_nba_official_score
from bta_v08.markets import fetch_markets, match_offers, book_quote_status
from bta_v08.research import queue_for_event

st.set_page_config(page_title='BTA | Automatic Slate', page_icon='🏟️', layout='wide', initial_sidebar_state='collapsed')

st.markdown('''<style>
.stApp {background:#0a101a;color:#e4ebf5;}
[data-testid="stSidebar"] {background:#111b2b;}
h1,h2,h3 {color:#f5f8ff;}
div[data-testid="stMetric"] {background:#121e2f; border:1px solid #27405d; border-radius:12px; padding:12px;}
div[data-testid="stExpander"] {border:1px solid #25405c; border-radius:12px; background:#0d1827;}
.stButton>button[kind="primary"] {background:#177ca8;}
</style>''',unsafe_allow_html=True)

TZ=ZoneInfo('America/New_York')
LEAGUE_LABELS=('NBA','NFL','College football')


def _secret(name: str) -> str:
    try:
        return str(st.secrets.get(name,'') or '').strip()
    except (FileNotFoundError, KeyError, OSError):
        return ''


@st.cache_data(ttl=135,show_spinner=False)
def _slate(league: str, daystrings: tuple[str, ...]):
    return collect(league,[date.fromisoformat(day) for day in daystrings])


@st.cache_data(ttl=900,show_spinner=False)
def _odds(league: str, key: str, book: str | None, props: bool):
    # Full-league prop query on-demand and cached to respect paid API quotas.
    return fetch_markets(league,key,only_book=book,props=props,bulk=props)


@st.cache_data(ttl=90,show_spinner=False)
def _nba_official_cached():
    from bta_v06.live import nba_today
    return nba_today()


@st.cache_data(ttl=1800,show_spinner=False)
def _historical(league: str, year: int):
    from bta_v05.sources import newest_nba_community_logs,nfl_weekly_player_stats
    records=[];details=[]
    if league=='NBA':
        for start_year in (year-1,year):
            season=f'{start_year}-{(start_year+1)%100:02d}'
            try:
                rows,meta=newest_nba_community_logs(season)
                records.extend(rows);details.append(meta)
            except Exception as exc:
                details.append({'season':season,'status':type(exc).__name__})
    elif league=='NFL':
        for y in (year-1,year):
            try:
                rows,meta=nfl_weekly_player_stats(y)
                records.extend(rows);details.append(meta)
            except Exception as exc:
                details.append({'season':y,'status':type(exc).__name__})
    return records,details


def _display_time(game:dict)->str:
    start=parse_instant(game['start_utc'])
    if not start:return 'Time unavailable'
    dt=start.astimezone(TZ)
    return f"{dt.strftime('%a, %b')} {dt.day} · {dt.strftime('%I:%M %p').lstrip('0')} ET"


def _label_offer(o:dict)->str:
    stat=o['market'].replace('player_','').replace('_',' ').title()
    if o.get('player'):
        return f"{o['player']} · {stat} · {o['selection']} {o.get('line')}"
    if o['market']=='h2h':return f"Moneyline · {o['selection']}"
    if o['market']=='spreads':return f"Spread · {o['selection']} {o.get('line'):+g}"
    return f"Game Total · {o['selection']} {o.get('line')}"


def _display_league(league:str, games:list[dict], *, error_message:list[dict],
                    prices:list[dict], meta:list[dict], history:list[dict], histories_meta:list[dict]):
    by_game,unmatched=match_offers(games,prices) if prices else ({g['event_key']:[] for g in games},[])
    if error_message:
        st.warning(f'{len(error_message)} scoreboard day request(s) failed; this may be an incomplete slate.')
        with st.expander('Provider errors'):
            st.json(error_message)
    if not games:
        st.info('No games returned for the requested days. This does not establish that no games are scheduled.')
        return
    if unmatched:
        st.warning(f'{len(unmatched)} offer(s) could not be matched confidently to an ESPN game. They were excluded.')
    for event in games:
        a,b=event['away'],event['home']
        caption=f"{_display_time(event)} · {event['status']} · {event.get('detail') or 'No additional status'}"
        if event['status'] in ('LIVE','FINAL'):
            caption+=f" · {a.get('score') or '—'}–{b.get('score') or '—'}"
        with st.expander(f"{a['name']} @ {b['name']}  |  {event['status']}",expanded=event['status']=='LIVE'):
            st.caption(caption)
            st.caption(f"Event: {event['event_key']} · Schedule source: ESPN (unofficial feed) · Retrieved: {event['retrieved_at_utc']}")
            if league=='College football':
                st.caption('ESPN FBS schedule grouping; individual FBS/FCS eligibility and player availability not verified.')
            offers=by_game.get(event['event_key'],[])
            if event['status']!='UPCOMING' or (parse_instant(event['start_utc']) or datetime.min.replace(tzinfo=timezone.utc)) <= datetime.now(timezone.utc):
                st.info('Game has started or its scheduled kickoff/tipoff has passed. Scoreboard monitoring only; pregame research cannot be offered.')
                continue
            if not offers:
                st.info('No matched, confirmed market offers from the selected provider. Showing NO invented odds or BTA+ picks.')
                st.markdown('**Markets to investigate once a provider is connected:** Moneyline · Spread · Total' if league=='College football'
                            else '**Markets to investigate:** Moneyline · Spread · Total · Player props (when offered)')
                continue
            game_props=[o for o in offers if o.get('player_props')]
            game_lines=[o for o in offers if not o.get('player_props')]
            if game_lines:
                st.markdown('**Observed game markets — not recommendations**')
                shown=game_lines[:30]
                st.dataframe([{'Market':_label_offer(o),'Odds':f"{o['american_odds']:+d}",
                               'Book':o['bookmaker'],'Quote status':book_quote_status(o),
                               'Updated':o['book_updated_utc']} for o in shown],hide_index=True,use_container_width=True)
            if game_props:
                st.markdown('**Automatic player-prop research queue (up to 3)**')
                queue=queue_for_event(event,game_props,history,max_items=3)
                if not queue:
                    st.info('Offers exist but cannot be evaluated with the supported historical schema.')
                for index,row in enumerate(queue,1):
                    o=row['offer'];s=row['screen'];g=row['gate'];c1,c2=st.columns([4,1])
                    c1.markdown(f"**{index}. {_label_offer(o)}** · {o['american_odds']:+d} ({o['bookmaker']})")
                    c1.caption(f"Research priority index {row['priority']}/100 · Not a success probability · {book_quote_status(o)}")
                    c2.write('PENDING')
                    if s.get('status')=='HISTORICAL CONTEXT ONLY':
                        c1.caption(f"Past sample: {s['hits']}/{s['decided']} decided; median clearance {s['median_clearance']:+g}; "
                                   f"recent 3 wins {s['recent_3_hits']}; {s['sample_period']}.")
                    else:
                        c1.caption('Historical audit pending: '+s.get('reason','Unavailable'))
                    with st.popover('Why not automatically BTA+?',use_container_width=False):
                        st.write('This is a research lead, NOT a graded pick.')
                        st.write('\n'.join(f'• {reason}' for reason in g.get('reasons',[])))
                    if st.button(f'Add to research slip · #{index}',key=f"slip_{event['event_key']}_{index}"):
                        key=f"{event['event_key']}:{o['market']}:{o['player']}:{o['selection']}:{o['line']}:{o['bookmaker']}"
                        st.session_state.setdefault('v08_slip',{})[key]={'event':event['event_key'],'league':league,
                           'event_start_utc':event['start_utc'],'bookmaker':o['bookmaker'],'market':o['market'],
                           'player':o['player'],'selection':o['selection'],'line':o['line'],
                           'american_odds':o['american_odds'],'quote_updated':o['book_updated_utc'],
                           'bta_grade':'PENDING','calibrated_win_probability':None}
                        st.toast('Added as an unverified research lead, not a BTA pick')
                        st.rerun()
            elif game_lines:
                st.caption('No actual player-prop offers returned. No automatic player prop shortlist is possible from game odds alone.')


st.title('BTA · AUTOMATIC SLATE')
st.caption('Live schedules and optional sportsbook offers · Historical research only · No fabricated lines · No automatic BTA+ approvals')
now=datetime.now(timezone.utc).astimezone(TZ)
with st.sidebar:
    st.header('Slate controls')
    league=st.radio('League',LEAGUE_LABELS,horizontal=False,index=0)
    day_from=st.date_input('Start date (Eastern Time)',value=now.date())
    horizon=st.select_slider('Number of days',options=[1,2,3,5,7],value=3)
    book=st.selectbox('Bookmaker offers',('FanDuel only','DraftKings only','BetMGM only','All available books'))
    provider_name={'FanDuel only':'fanduel','DraftKings only':'draftkings',
                   'BetMGM only':'betmgm','All available books':None}[book]
    auto_props=st.checkbox('Look up player props when supported',value=True)
    st.caption('Player props require a provider subscription. API polling is cached to limit usage.')
    if st.button('Refresh schedules and markets now'):
        _slate.clear(); _odds.clear();st.rerun()

key=_secret('BTA_ODDS_API_KEY')
if not key:
    st.info('Game schedules work without a key. Exact bookmaker moneyline/spread/total/prop offers need a separate API key; none is configured. No lines will be invented.')
else:
    st.caption('A provider key is configured. The available markets depend on your paid/free tier and actual bookmaker coverage.')

st.markdown('### TODAY · LIVE · UPCOMING')

@st.fragment(run_every='2m')
def render_auto_slate():
    days=tuple(d.isoformat() for d in next_days(day_from,horizon=horizon))
    with st.spinner('Loading game schedules…'):
        slate=_slate(league,days)
    games=slate['games']
    official_updated=0
    current_local_day=datetime.now(timezone.utc).astimezone(TZ).date()
    if league=='NBA' and day_from <= current_local_day < day_from + timedelta(days=horizon):
        try:
            from bta_v06.live import nba_today
            official_record=_nba_official_cached()
            games,official_updated=augment_nba_official_score(games,official_record,local_day=current_local_day)
        except Exception:
            pass  # ESPN remains explicitly identified; do not fake an official feed.
    counts=game_counts(games)
    c1,c2,c3,c4=st.columns(4)
    c1.metric('Upcoming',counts['UPCOMING'])
    c2.metric('Live',counts['LIVE'])
    c3.metric('Final',counts['FINAL'])
    c4.metric('Schedule errors',len(slate['errors']))
    prices=[];metalogs=[];history=[];histmeta=[]
    if key:
        try:
            records,meta=_odds(league,key,provider_name,False)
            prices.extend(records);metalogs.append(meta)
        except Exception as exc:
            st.warning(f'Market feed unavailable ({type(exc).__name__}). Key tier, quota or provider may not support these markets.')
        if league!='College football' and auto_props:
            try:
                props,meta=_odds(league,key,provider_name,True)
                prices.extend(props);metalogs.append(meta)
                if props:
                    year=day_from.year if day_from.month>=3 else day_from.year-1
                    history,histmeta=_historical(league,year)
            except Exception as exc:
                st.warning(f'Player-prop feed unavailable ({type(exc).__name__}). Business-tier access may be required.')
    st.caption(f"Latest slate read: {slate['retrieved_at_utc']} UTC · ESPN schedule feed unofficial · NBA official live scores matched: {official_updated} game(s)")
    _display_league(league,games,error_message=slate['errors'],prices=prices,
                    meta=metalogs,history=history,histories_meta=histmeta)
    if metalogs:
        with st.expander('Offer source information'):
            st.json(metalogs)
    if histmeta:
        with st.expander('Historical source information'):
            st.json(histmeta)

render_auto_slate()

st.divider()
st.markdown('### YOUR RESEARCH SLIP')
st.caption('Stores potential legs in this browser session. It does not place bets, validate settlements, estimate parlay success or approve a BTA ticket.')
slip=st.session_state.setdefault('v08_slip',{})
if slip:
    st.dataframe(list(slip.values()),hide_index=True,use_container_width=True)
    st.download_button('Export research slip JSON',data=json.dumps(list(slip.values()),indent=2),
                       file_name='bta_v08_research_slip.json',mime='application/json')
    if st.button('Clear research slip'):
        st.session_state['v08_slip']={};st.rerun()
else:
    st.write('No candidate legs added yet.')

with st.expander('Why top-three BTA+ is not automatic yet'):
    st.write('The slate and market offers are automated when their providers work. But a high-confidence grade requires ' 
             'a matching pregame player, expected role, injuries/inactives, opponent-adjusted data, five distinct ' 
             'scenario mechanisms, calibration from past predictions, exact settlement rules and a second-pass audit. ' 
             'Those pieces are NOT verified merely because historical results look favorable.')
    st.write('Even if all three example picks appear strong, it is acceptable to show zero actual BTA+ selections.')
