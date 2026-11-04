"""Streamlit front end. The prototype never places real wagers."""
import csv
import io
from datetime import datetime, timezone
from uuid import uuid4
from datetime import date
import unicodedata
from nba_model import METRICS, group_players, estimate, historical_brier, automatic_baselines, expected_roi
from nba_data import fetch_nba_logs, parse_uploaded_csv
from nba_prop_odds import get_events, get_event_props, MARKETS

import streamlit as st
from engine import ALLOWED_GRADES, assess, implied_probability, profit_for_result
from odds_provider import SPORTS, get_moneylines

st.set_page_config(page_title='BTA Free Engine · Paper Only', page_icon='📊', layout='wide')
st.title('BTA Research Engine · NBA Probabilities v0.2')
st.caption('Research prototype • NBA probability baseline + optional prop lookup + paper ledger • NO real-money bets')
st.warning('The NBA tab estimates probabilities itself from player game logs, but the model is UNVALIDATED and does NOT research injuries, expected lineups, opponents, or five-game scripts. No automatically assigned BTA grades or real-money bets.', icon='⚠️')

for name, default in [('quotes', []), ('ledger', []), ('bankroll', 1000.0), ('nba_logs', []), ('nba_events', []), ('nba_props', [])]:
    if name not in st.session_state:
        st.session_state[name] = default

with st.sidebar:
    st.header('Paper risk controls')
    bankroll = st.number_input('Simulated starting bankroll ($)', min_value=10.0, max_value=1_000_000.0, value=float(st.session_state.bankroll), step=50.0)
    st.session_state.bankroll = bankroll
    st.caption('Per-event paper stake: 0.5% of starting bankroll. All-open exposure cap: 5%. One open position per event. Rules are adjustable later after validation.')
    st.divider()
    st.header('Optional free live odds')
    sport = st.selectbox('Sport', list(SPORTS.keys()))
    api_key = st.text_input('The Odds API key', type='password', help='Use the provider at the-odds-api.com (with hyphens). Never upload keys to a public repository.')
    if st.button('Fetch current moneylines', type='primary', use_container_width=True):
        try:
            with st.spinner('Reading odds provider...'):
                quotes, remaining = get_moneylines(api_key, SPORTS[sport])
            st.session_state.quotes = quotes
            st.success(f'{len(quotes)} quotes received. Free credits remaining: {remaining}.')
        except Exception as e:
            st.error(str(e))
    st.caption('Provider access consumes credits. Quotes can be delayed; refresh before evaluating. The API connection uses moneylines only in this starter.')

nba_tab, research, ledger_tab, roadmap = st.tabs(['NBA probability engine', 'Manual research', 'Paper ledger', 'Roadmap'])

with research:
    rows = st.session_state.quotes
    if rows:
        st.subheader('Available fetched quotes')
        st.dataframe(rows[:300], use_container_width=True, hide_index=True)
        options = ['Manual entry'] + [f"{i+1}. {r['game']} | {r['selection']} {r['american_odds']:+d} | {r['bookmaker']}" for i,r in enumerate(rows)]
        pick = st.selectbox('Copy a quote into the review form', options)
        chosen = None if pick == 'Manual entry' else rows[options.index(pick)-1]
    else:
        chosen = None
        st.info('No live quotes loaded. Enter a hypothetical or manually observed quote below, or fetch moneylines using a free API key.')
    st.subheader('BTA research review')
    st.caption('Grades are manual placeholders until we encode and test your exact BTA criteria.')
    with st.form('review_form'):
        c1, c2 = st.columns(2)
        with c1:
            game = st.text_input('Game / matchup', value=chosen['game'] if chosen else '')
            event_id = st.text_input('Event identifier', value=chosen['event_id'] if chosen else '', help='For manual entries, use the same identifier for selections in the same game.')
            selection = st.text_input('Selection', value=chosen['selection'] if chosen else '')
            odds = st.number_input('American odds', min_value=-10000, max_value=10000, value=chosen['american_odds'] if chosen else -110, step=1)
            book = st.text_input('Sportsbook/source', value=chosen['bookmaker'] if chosen else 'Manual')
        with c2:
            grade = st.selectbox('Provisional BTA grade', ALLOWED_GRADES, index=2)
            probability = st.number_input('Your estimated win probability (%)', min_value=0.1, max_value=99.9, value=50.0, step=0.5, help='Never treat the sportsbook implied probability as an independent model estimate.')
            evidence_reviewed = st.checkbox('I reviewed relevant evidence and recorded key supporting factors')
            blockers = st.checkbox('Unresolved material blocker (injury, lineup, uncertainty, etc.)')
            notes = st.text_area('Research notes / failure scripts', placeholder='Data source, injury updates, matchup factors, alternative scripts, reasons this could fail...')
        submitted = st.form_submit_button('Evaluate and record paper candidate', type='primary')
    if submitted:
        if not game.strip() or not selection.strip():
            st.error('Game and selection are required.')
        elif -100 < int(odds) < 100:
            st.error('Odds must be at least +100 or at most -100.')
        else:
            open_rows = [r for r in st.session_state.ledger if r.get('result') == 'OPEN']
            exposure = sum(float(r['stake']) for r in open_rows)
            eid = event_id.strip() or game.strip().lower()
            same_event = any(r.get('event_id') == eid for r in open_rows)
            a = assess(probability=probability/100, american=int(odds), grade=grade,
                       bankroll=bankroll, open_exposure=exposure,
                       evidence_reviewed=evidence_reviewed, blockers=blockers,
                       same_event_already_open=same_event)
            quote_date = chosen.get('bookmaker_update_utc','') if chosen else ''
            new = dict(id=str(uuid4())[:8], logged_utc=datetime.now(timezone.utc).isoformat(),
                       event_id=eid, game=game.strip(), selection=selection.strip(), bookmaker=book.strip(),
                       odds=int(odds), grade=grade, estimated_probability=probability,
                       implied_probability=round(implied_probability(int(odds))*100,3),
                       estimated_edge_pp=round(a.edge*100,3), expected_roi_pct=round(a.ev*100,3),
                       status=a.status, reason=a.reason, stake=a.stake, result='OPEN' if a.stake else 'WATCH ONLY',
                       source_update_utc=quote_date, notes=notes)
            st.session_state.ledger.append(new)
            if a.stake:
                st.success(f'PAPER ELIGIBLE • simulated stake ${a.stake:.2f}; theoretical EV {a.ev*100:.2f}% (conditional on your unvalidated probability estimate).')
            else:
                st.warning(f'WATCH ONLY • no simulated stake. {a.reason}')
            st.caption('The system recorded a paper candidate only. No real money was wagered.')

with ledger_tab:
    records = st.session_state.ledger
    open_bets = [r for r in records if r.get('result') == 'OPEN']
    settled = [r for r in records if r.get('result') in ('WIN', 'LOSS', 'PUSH')]
    net = sum(profit_for_result(float(r['stake']), int(r['odds']), r['result']) or 0 for r in settled)
    outlay = sum(float(r['stake']) for r in settled)
    a,b,c,d = st.columns(4)
    a.metric('Candidates logged', len(records))
    b.metric('Open paper exposure', f"${sum(float(r['stake']) for r in open_bets):.2f}")
    c.metric('Settled paper P/L', f'${net:.2f}')
    d.metric('Settled paper ROI', f'{100*net/outlay:.2f}%' if outlay else 'N/A')
    if records:
        st.dataframe(records, use_container_width=True, hide_index=True)
        open_options = {f"{r['id']} • {r['game']} — {r['selection']}": r for r in open_bets}
        if open_options:
            with st.form('settle'):
                name = st.selectbox('Settle a simulated position', list(open_options))
                result = st.selectbox('Outcome', ['WIN', 'LOSS', 'PUSH'])
                if st.form_submit_button('Record outcome'):
                    chosen_id = open_options[name]['id']
                    for r in records:
                        if r['id'] == chosen_id:
                            r['result'] = result
                            break
                    st.success('Paper result recorded.')
                    st.rerun()
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
        st.download_button('Download ledger CSV (important backup)', buf.getvalue(), file_name='bta_paper_ledger.csv', mime='text/csv')
    else:
        st.info('No candidates yet. Add one on the Research tab.')
    st.divider()
    st.subheader('Restore from an earlier CSV backup')
    upload = st.file_uploader('Choose exported ledger CSV', type=['csv'])
    if upload is not None and st.button('Restore CSV (replaces this session)'):
        if upload.size > 2_000_000:
            st.error('CSV exceeds 2 MB safety limit.')
        else:
            try:
                parsed = list(csv.DictReader(io.StringIO(upload.getvalue().decode('utf-8-sig'))))
                required = {'id','game','event_id','selection','odds','stake','result','status'}
                if len(parsed) > 10000 or not parsed or not required.issubset(set(parsed[0])):
                    raise ValueError('Not a valid exported paper ledger CSV.')
                for r in parsed:
                    int(r['odds']); float(r['stake'])
                    if r['result'] not in ('WIN','LOSS','PUSH','OPEN','WATCH ONLY'):
                        raise ValueError('Invalid paper outcome in CSV.')
                st.session_state.ledger = parsed
                st.success(f'Restored {len(parsed)} records.')
                st.rerun()
            except (ValueError, UnicodeError) as e:
                st.error(f'Cannot restore CSV: {e}')
    st.caption('Community Cloud app sessions and local files can reset. Keep CSV exports. Do not store financial credentials or sensitive personal data in this prototype.')

with roadmap:
    st.markdown('''
**Version 0.1 — built:** Live moneyline ingestion, manual BTA checks, paper stakes, CSV ledger.

**Version 0.2 — built:** Automatic NBA points/rebounds/assists estimates from game logs; chronological fixed-line Brier checks; free NBA data fetch with CSV fallback; optional per-event player-prop odds lookup (uses API credits). The model is a recency-weighted historical baseline, not an injury-/opponent-adjusted predictive advantage. It assigns **no** BTA/TAIG grades itself.

**Version 0.3 — to build:** Injury/rotation/defense/rest context, five game-script risk review, calibrated probabilities evaluated against time-stamped market prices, comparable held-out tests.

**Version 0.4 — to build:** Scheduled scans, lineup blockers, audited multi-agent reviews, robust persistent ledger and no-lookahead paper portfolios.

**Parlays — later:** Must establish per-leg value and joint probabilities from correlations; multiplying probabilities without independence would be invalid. Never force a parlay.

**Restrictions:** No live wagers are placed. The public NBA stats endpoint sometimes blocks cloud servers. The Odds API free quota is limited; prop coverage and access vary. No historical bookmaker prop lines are provided for free backtests.
''')


def _match_key(value):
    text=unicodedata.normalize('NFKD',str(value))
    text=''.join(c for c in text if not unicodedata.combining(c)).casefold()
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in text).split())

def _make_csv(rows):
    import csv as _csv
    import io as _io
    if not rows:return ''
    buffer=_io.StringIO()
    writer=_csv.DictWriter(buffer,fieldnames=list(rows[0]))
    writer.writeheader();writer.writerows(rows)
    return buffer.getvalue()

with nba_tab:
    st.subheader('1 · NBA game logs — real data required')
    st.caption('Click fetch to request current + previous regular-season player logs from NBA.com via nba_api. If blocked, upload a genuine exported NBA PlayerGameLogs CSV. The app never substitutes fabricated statistics.')
    col_a,col_b=st.columns(2)
    with col_a:
        fetch_clicked=st.button('Fetch 2025–26 + 2026–27 NBA logs', use_container_width=True, type='primary')
    with col_b:
        nba_csv=st.file_uploader('Or upload PlayerGameLogs CSV',type=['csv'],key='nba_gamelogs_upload')
    if fetch_clicked:
        try:
            with st.spinner('Fetching regular-season NBA player game logs...'):
                st.session_state.nba_logs=fetch_nba_logs()
            st.success(f"Imported {len(st.session_state.nba_logs):,} game logs.")
        except Exception as e:
            st.error(str(e))
    if nba_csv is not None and st.button('Import uploaded game logs'):
        try:
            st.session_state.nba_logs=parse_uploaded_csv(nba_csv)
            st.success(f"Imported {len(st.session_state.nba_logs):,} verified-format game logs.")
        except Exception as e:
            st.error(f'Import failed: {e}')
    nba_logs=st.session_state.nba_logs
    if not nba_logs:
        st.info('No NBA records loaded. Fetch real NBA game logs above or upload a real CSV to unlock independent predictions.')
    else:
        grouped,names=group_players(nba_logs)
        most_recent=max(r['game_date'] for r in nba_logs)
        st.success(f"Loaded {len(nba_logs):,} game logs for {len(grouped):,} players. Latest box-score date: {most_recent.isoformat()}.")
        if (date.today()-most_recent).days>7:
            st.warning('Game logs are more than seven days old. The predictions are not suitable for evaluating current player props.')
        st.subheader('2 · Autonomous baseline scouting — no manual probability input')
        st.caption('For each player and stat, this scanner chooses an EXAMPLE half-point threshold near the recent historical projection. These are NOT verified sportsbook offerings or BTA recommendations.')
        auto=automatic_baselines(nba_logs, max_players=120)
        st.dataframe(auto,hide_index=True,use_container_width=True)
        if auto:
            st.download_button('Download baseline research CSV',
                data=_make_csv(auto), file_name='nba_baselines_unpriced.csv',mime='text/csv')
        st.subheader('3 · Probability estimate for any points, rebounds, or assists line')
        player_ids=sorted(grouped, key=lambda pid:names[pid].casefold())
        chosen_id=st.selectbox('NBA player',player_ids,format_func=lambda pid:names[pid])
        stat_name=st.selectbox('Prop statistic',list(METRICS),key='nba_selected_stat')
        stat_col=METRICS[stat_name]
        default_line=20.5 if stat_col=='points' else (6.5 if stat_col=='rebounds' else 4.5)
        line=st.number_input('Line (points/rebounds/assists)',min_value=0.5,max_value=199.5,step=1.0,value=default_line)
        american=st.number_input('Example/current American odds for side comparison',min_value=-5000,max_value=5000,value=-110,step=5)
        if -100<american<100:
            st.error('American odds must be at least +100 or at most -100.')
        else:
            model=estimate(grouped[chosen_id],stat_col,float(line))
            if model['status']!='BASELINE ONLY':
                st.warning(f"Not enough past games for this player: {model['games']} available, {model['min_required']} required.")
            else:
                a,b,c=st.columns(3)
                a.metric('History-weighted projection',f"{model['projection']:.1f} {stat_col}")
                b.metric(f'P(Over {line:g})',f"{100*model['p_over']:.1f}%")
                c.metric(f'P(Under {line:g})',f"{100*model['p_under']:.1f}%")
                side=st.radio('Evaluate side', ['Over','Under'], horizontal=True)
                pw=model['p_over'] if side=='Over' else model['p_under']
                roi=expected_roi(pw,model['p_push'],int(american))
                st.write(f"**Illustrative expected ROI at {american:+d}: {roi*100:+.1f}%**, *only if this unvalidated probability estimate is correct*. Based on {model['games']} games through {model['last_game']}; last-five-game average: {model['recent_5_avg']:.1f}.")
                st.caption('Model has no injury/lineup/role or defense adjustments. The approximate uncertainty interval does not account for model bias. Its estimate is NOT a BTA grade or an actionable pick.')
                check=historical_brier(grouped[chosen_id],stat_col,float(line))
                if check['count']:
                    st.write(f"**Chronological fixed-line test:** {check['count']} earlier outcomes; Brier score {check['brier']:.3f} (lower is better). Average predicted over: {100*check['avg_predicted_over']:.1f}%, observed over: {100*check['actual_over_rate']:.1f}%.")
                    st.caption('Historical test uses this same chosen line in past games; it does NOT represent historic sportsbook prop lines, ROI, or validated profitability.')
                else:
                    st.info('Not enough games for the chronological fixed-line check.')
        st.divider()
        st.subheader('4 · Optional scan of current bookmaker player props')
        st.caption('Uses your the-odds-api.com key, requested on demand; fetching three markets for one game may consume substantial free credits. Never automatic refresh. Only estimates for exact name matches and sufficient history.')
        odds_key=st.text_input('The Odds API key for NBA props',type='password',key='nba_prop_key')
        if st.button('Find upcoming NBA games (API call)',key='get_nba_event_btn'):
            try:
                st.session_state.nba_events,usage=get_events(odds_key)
                st.info(f"{len(st.session_state.nba_events)} upcoming NBA events returned. Credits remaining: {usage['remaining']}.")
            except Exception as e:st.error(str(e))
        if st.session_state.nba_events:
            evs=st.session_state.nba_events
            options={f"{e['game']} | {e['start_utc']}":e['id'] for e in evs}
            event_label=st.selectbox('One upcoming game',list(options))
            market_choices=st.multiselect('Markets to request (affects credits)',list(MARKETS),default=['player_points'])
            if st.button('Fetch these player props (spends API credits)',key='get_nba_prop_btn'):
                try:
                    st.session_state.nba_props,usage=get_event_props(odds_key,options[event_label],tuple(market_choices))
                    st.info(f"Fetched {len(st.session_state.nba_props)} unique current prop prices. Last API charge: {usage['last']} credits; remaining: {usage['remaining']}.")
                except Exception as e:st.error(str(e))
        if st.session_state.nba_props:
            key_lookup={_match_key(n):pid for pid,n in names.items()}
            scanned=[];unmatched=0
            now=datetime.now(timezone.utc)
            for quote in st.session_state.nba_props:
                try:
                    kickoff=datetime.fromisoformat(quote['start_utc'].replace('Z','+00:00'))
                    if kickoff<=now:continue
                except (ValueError,AttributeError):continue
                pid=key_lookup.get(_match_key(quote['player']))
                if not pid:
                    unmatched+=1
                    continue
                res=estimate(grouped[pid],quote['stat'],quote['line'])
                if res['status']!='BASELINE ONLY':continue
                p=res['p_over'] if quote['side']=='over' else res['p_under']
                ev=expected_roi(p,res['p_push'],quote['odds'])
                scanned.append({'player':quote['player'],'stat':quote['stat'],'side':quote['side'],
                    'line':quote['line'],'odds':quote['odds'],'book':quote['book'],
                    'estimated_probability_pct':round(p*100,1),'baseline_projection':round(res['projection'],1),
                    'model_expected_roi_pct':round(ev*100,1),'games':res['games'],
                    'latest_boxscore':res['last_game'],'start_utc':quote['start_utc'],
                    'status':'UNVALIDATED • NO BTA GRADE'})
            scanned.sort(key=lambda x:x['model_expected_roi_pct'],reverse=True)
            st.write(f'{len(scanned)} history-matched unvalidated estimates; {unmatched} unmatched prop names (skipped; no guessing).')
            st.dataframe(scanned[:300],hide_index=True,use_container_width=True)
            if scanned:
                st.download_button('Download assessed props CSV',_make_csv(scanned),
                    file_name='nba_prop_baseline_research.csv',mime='text/csv')
            st.warning('Do not treat high expected ROI in this scan as evidence of a real edge. The historical baseline is not calibrated against bookmaker markets or injury/lineup changes. Paper research only.')
