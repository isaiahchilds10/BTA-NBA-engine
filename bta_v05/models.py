"""Deterministic BTA research models and safety gates (zero invented inputs).

Outputs describe research, not a bookmaker edge or BTA+ approval. Historical
frequency and Elo pseudo-probabilities require out-of-sample validation.
"""
from __future__ import annotations

import math
import re
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

NBA_STATUS = ('OUT', 'DOUBTFUL', 'QUESTIONABLE', 'PROBABLE', 'AVAILABLE')


def _key(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', (name or '').casefold())


def _number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None


def nba_injury_lookup(pdf_text: str, player_name: str, meta: dict, *, now: datetime | None = None) -> dict:
    """Player listed means verified listing; not-listed is ALWAYS unknown.

    Does NOT infer that report fully covers a game or that a player is active.
    """
    try:
        published = datetime.fromisoformat(str(meta.get('report_published_et_naive','')))
        published = published.replace(tzinfo=ZoneInfo('America/New_York'))
        checked_at = now or datetime.now(timezone.utc)
        if checked_at.tzinfo is None:
            raise ValueError('now must have timezone')
        age = (checked_at-published).total_seconds()/3600
        if age < -2 or age > 36:
            return {'gate':'UNVERIFIED','reason':f'Official injury report outside freshness window ({age:.1f} hours old)',
                    'source':meta.get('source')}
    except ValueError:
        return {'gate':'UNVERIFIED','reason':'Report publication date not verified','source':meta.get('source')}
    tokens = player_name.strip().split()
    if len(tokens) < 2:
        return {'gate': 'UNVERIFIED', 'reason': 'Full player name required'}
    first, last = tokens[0], ' '.join(tokens[1:])
    # Reports display "Surname, Given"; allow middle suffix tokens in between.
    # Status must appear directly after the exact surname/given name, possibly
    # separated by table whitespace or one line break. Never borrow the status
    # from a DIFFERENT player appearing later in the PDF.
    pattern = re.compile(r'(?<!\w)'+re.escape(last)+r',\s*'+re.escape(first)+
                         r'\b\s{1,70}(Out|Doubtful|Questionable|Probable|Available)\b', re.I)
    found = {m.group(1).upper() for m in pattern.finditer(pdf_text)}
    if not found:
        return {'gate': 'UNVERIFIED', 'reason': 'Not present in parsed report; this DOES NOT establish availability.',
                'source': meta.get('source'), 'published': meta.get('report_published_et_naive')}
    if len(found) != 1:
        return {'gate': 'UNVERIFIED', 'reason': 'Conflicting statuses in report', 'source':meta.get('source')}
    status = next(iter(found))
    return {'gate': 'BLOCKED' if status in ('OUT','DOUBTFUL') else 'REVIEW REQUIRED',
            'status': status, 'source': meta.get('source'), 'published':meta.get('report_published_et_naive'),
            'reason': 'This is a dated report, not a game-time active list. Recheck shortly before tipoff.'}


def nfl_injury_lookup(rows: list[dict], player: str, week: int, team: str = '') -> dict:
    if not isinstance(week, int) or week < 1 or week > 22:
        raise ValueError('Set a valid exact NFL week')
    matches = [r for r in rows if str(r.get('week','')) == str(week)
               and _key(r.get('full_name','')) == _key(player)
               and (not team or str(r.get('team','')).upper() == team.upper())]
    if not matches:
        return {'gate':'UNVERIFIED','reason':'No matching injury-list entry for chosen player/week. Not listed != active.'}
    teams = {r.get('team') for r in matches}
    if len(teams) > 1:
        return {'gate':'UNVERIFIED','reason':'Player matching multiple teams; disambiguate roster'}
    def stamp(r):
        raw = str(r.get('date_modified') or '')
        try:
            return datetime.fromisoformat(raw.replace('Z','+00:00')).timestamp()
        except ValueError:
            return 0
    best = max(matches, key=stamp)
    status = (best.get('report_status') or '').strip().upper()
    if status in ('OUT', 'DOUBTFUL'):
        gate = 'BLOCKED'
    elif status in ('QUESTIONABLE', 'PROBABLE'):
        gate = 'REVIEW REQUIRED'
    else:
        gate = 'UNVERIFIED'
    return {'gate':gate,'status':status or 'NOT DESIGNATED',
            'reported_week':week,'player':best.get('full_name'), 'team':best.get('team'),
            'primary_injury':best.get('report_primary_injury') or '',
            'practice_status':best.get('practice_status') or '',
            'date_modified':best.get('date_modified') or '',
            'reason':'Weekly injury report is not a verified game-day active roster; absence/blank status is inconclusive.'}


def nfl_snaps_lookup(rows: list[dict], player: str, *, before_week: int, team: str = '') -> dict:
    matched = []
    for r in rows:
        n = _number(r.get('week'))
        if n is None or not (0 < n < before_week):
            continue
        if _key(r.get('player','')) != _key(player) or (team and r.get('team','').upper()!=team.upper()):
            continue
        pct = _number(r.get('offense_pct'))
        snaps = _number(r.get('offense_snaps'))
        if pct is None or snaps is None: continue
        # nflverse uses 0–1 fractions; some imports can be scaled 0–100.
        frac = pct/100 if pct > 1 else pct
        if not 0 <= frac <= 1: continue
        matched.append({'week':int(n),'team':r.get('team'),'opponent':r.get('opponent'),
                        'offensive_snaps':snaps,'offensive_snap_share_pct':round(frac*100,1)})
    matched.sort(key=lambda r:r['week'])
    if len(matched) < 3:
        return {'gate':'UNVERIFIED','reason':'Fewer than 3 pregame snap records; role stability cannot be verified',
                'sample':matched}
    last3 = matched[-3:]
    baseline = matched[-6:-3] or matched[-6:]
    avg3 = statistics.mean(x['offensive_snap_share_pct'] for x in last3)
    prior = statistics.mean(x['offensive_snap_share_pct'] for x in baseline)
    concern = len(matched) >= 6 and (avg3 - prior < -15)
    return {'gate':'REVIEW REQUIRED' if concern else 'HISTORICAL CONTEXT ONLY',
            'last_three_avg_share_pct':round(avg3,1),'prior_avg_share_pct':round(prior,1),
            'change_pp':round(avg3-prior,1), 'sample':matched[-10:],
            'reason':'Snap share only; routes, starting status, injury limitations and upcoming role NOT verified.'}


def nba_matchup_context(raw_player_rows: list[dict], player: str, upcoming_opponent: str,
                        *, before: date, stat: str = 'Points') -> dict:
    """Opponent-adjusted scouting from prior NBA community box scores.

    Estimates opponent's *team scoring allowed* vs league sample, not player
    matchup defense or a calibrated prop probability. No future games used.
    """
    if stat not in ('Points', 'Rebounds', 'Assists'):
        raise ValueError('Unsupported NBA statistic')
    games = defaultdict(dict)  # (date, team, opponent) -> player_id -> (points, stat)
    relevant = []
    for row in raw_player_rows:
        try:
            game_date = date.fromisoformat(str(row.get('Date',''))[:10])
        except ValueError:
            continue
        if game_date >= before:
            continue
        team, opp = str(row.get('Team','')).upper(),str(row.get('Opp','')).upper()
        points = _number(row.get('Points'))
        value = _number(row.get(stat))
        if not team or not opp or points is None or value is None:
            continue
        player_id = str(row.get('ID') or row.get('Player') or '').strip()
        if not player_id: continue
        games[(game_date, team, opp)][player_id] = points
        if _key(row.get('Player','')) == _key(player):
            relevant.append({'date':game_date,'opponent':opp,'value':value,
                             'minutes':_number(row.get('Minutes'))})
    opponent_allowed = []
    league_games = []
    valid_games = {}
    for k, players in games.items():
        if len(players) < 5:
            continue
        total = sum(players.values())
        if 65 <= total <= 200:
            valid_games[k] = total
            league_games.append(total)
            if k[2] == upcoming_opponent.upper():
                opponent_allowed.append(total)
    if len(opponent_allowed) < 5 or len(league_games) < 30:
        return {'gate':'UNVERIFIED','reason':'Not enough complete opponent/league box scores for scoring-adjustment context.',
                'opponent_games':len(opponent_allowed),'league_games':len(league_games)}
    lg = statistics.mean(league_games)
    opp = statistics.mean(opponent_allowed[-20:])
    # Regularize to neutral to avoid extremes in small samples. Research-only heuristic.
    weight = min(0.75,len(opponent_allowed)/(len(opponent_allowed)+12))
    ratio = max(0.85,min(1.15,1 + weight*(opp/lg - 1)))
    player_games = [r for r in relevant if r['minutes'] is not None and r['minutes']>0]
    last = sorted(player_games, key=lambda x:x['date'])[-10:]
    vs_opp = [r['value'] for r in last if r['opponent']==upcoming_opponent.upper()]
    return {'gate':'RESEARCH ONLY','opponent_games':len(opponent_allowed),
            'league_games':len(league_games),'league_team_pts_avg':round(lg,2),
            'opponent_pts_allowed_avg':round(opp,2),
            'contextual_scoring_ratio':round(ratio,3),'player_last10_stat': [r['value'] for r in last],
            'player_last10_vs_opponent':vs_opp,
            'reason':'Box-score scoring environment proxy, not positional defense or player usage model. '
                     'Never multiply a calibrated probability by this ratio.'}


def cfb_elo_progress(games: list[dict], *, cutoff: datetime | None = None,
                     home_advantage: float = 55.0, k_factor: float = 24.0):
    """Sequential pregame Elo from final completed games (research baseline).

    Inputs CFBD game records; scores affect ratings only after that game's
    *pregame* forecast is saved. Defaults are fixed heuristics, NOT fit to data.
    """
    rows = []
    for g in games:
        home,away = g.get('homeTeam'),g.get('awayTeam')
        hp,ap = _number(g.get('homePoints')),_number(g.get('awayPoints'))
        raw_time = str(g.get('startDate') or '')
        try:
            dt = datetime.fromisoformat(raw_time.replace('Z','+00:00'))
            if dt.tzinfo is None:dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(timezone.utc)
        except ValueError:continue
        if not home or not away or home==away or hp is None or ap is None:
            continue
        if cutoff is not None and dt >= cutoff.astimezone(timezone.utc):
            continue
        if not bool(g.get('completed',False)):
            continue
        rows.append((dt,str(g.get('id') or ''),home,away,hp,ap))
    rows.sort(key=lambda x:(x[0],x[1]))
    ratings = defaultdict(lambda:1500.0)
    predictions = []
    for dt,game_id,home,away,hp,ap in rows:
        diff = ratings[home] + home_advantage - ratings[away]
        p = 1/(1+10**(-diff/400))
        if hp == ap:
            # no binary win outcome in tie; keep rating update half and skip validation
            actual = .5
        else:
            actual = float(hp>ap)
            predictions.append({'date':dt.isoformat(), 'event_id':game_id, 'home':home,'away':away,
                                'p_home_raw':p,'home_won':int(actual),
                                'home_pts':hp,'away_pts':ap})
        delta = k_factor*(actual-p)
        ratings[home] += delta
        ratings[away] -= delta
    return dict(ratings),predictions


def cfb_unvalidated_upcoming(home: str, away: str, ratings: dict[str,float],
                             home_advantage=55.0) -> dict:
    if home not in ratings or away not in ratings:
        return {'gate':'UNVERIFIED','reason':'At least one team has no observed Elo history'}
    diff = ratings[home] + home_advantage-ratings[away]
    return {'gate':'EXPERIMENTAL ONLY','home_elo':round(ratings[home],1),
            'away_elo':round(ratings[away],1),'raw_home_elo_probability':round(1/(1+10**(-diff/400)),4),
            'reason':'Simple fixed-parameter Elo; NOT calibrated, not opponent-adjusted for roster, QB, injuries, or odds.'}


def bta_stress_gate(sport_market: str, decisions: list[str], *, blockers: list[str],
                    sources_verified: bool, independent_audit: bool) -> dict:
    """Prevents invalid approval. Never automatically returns TAIG/BTA+ or BTA."""
    allowed = {'BETTER','SAME','MIXED','WORSE','NOT ASSESSED'}
    if len(decisions)!=5 or any(s not in allowed for s in decisions):
        raise ValueError('Exactly five valid stress verdicts required')
    worse=sum(v=='WORSE' for v in decisions)
    if worse>=2 and 'player props' in sport_market.casefold():
        return {'status':'CUT','worse_count':worse,'reason':'Two or more meaningful WORSE game scripts for player props'}
    if worse>=2:
        return {'status':'PENDING / UPSET RISK','worse_count':worse,
                'reason':'College moneyline has multiple failed adversity tests; strongest plausible upset case requires expert review'}
    if blockers:
        return {'status':'PENDING','worse_count':worse, 'reason':'Unresolved blockers: '+', '.join(blockers[:5])}
    if not sources_verified or 'NOT ASSESSED' in decisions or not independent_audit:
        return {'status':'PENDING','worse_count':worse,
                'reason':'Sources, all scripts and independent audit required for any high-confidence grade'}
    if worse==1:
        return {'status':'CONDITIONAL','worse_count':1,'reason':'One adverse script needs deeper review; no automatic approval'}
    return {'status':'MANUAL AUDIT REQUIRED','worse_count':0,
            'reason':'Zero WORSE is not proof of a BTA grade or positive expected value'}


def nfl_defense_context(player_week_rows: list[dict], snap_rows: list[dict],
                        *, opponent: str, metric: str, before_week: int) -> dict:
    """Opponent's prior team-week total allowed vs league's prior team-week total.

    Use opponent from independently reported snap counts; no inference from
    alphabetical game IDs. No future weeks. This does NOT account for personnel.
    """
    stat_map={'Passing yards':'passing_yards','Rushing yards':'rushing_yards',
              'Receiving yards':'receiving_yards','Receptions':'receptions',
              'Passing touchdowns':'passing_tds','Rushing attempts':'carries',
              'Targets':'targets'}
    if metric not in stat_map:
        return {'gate':'UNVERIFIED','reason':'Metric has no validated team-week defense proxy'}
    field=stat_map[metric]
    team_opp={}
    ambiguity=set()
    for r in snap_rows:
        wk=_number(r.get('week'))
        team=str(r.get('team') or '').upper()
        opp=str(r.get('opponent') or '').upper()
        if wk is not None and 0 < wk < before_week and team and opp and team != opp:
            key=(int(wk),team)
            if key in team_opp and team_opp[key]!=opp:
                ambiguity.add(key)
            else:
                team_opp[key]=opp
    for key in ambiguity:
        team_opp.pop(key,None)
    totals=defaultdict(float)
    counts=defaultdict(int)
    for r in player_week_rows:
        wk=_number(r.get('week'))
        team=str(r.get('team') or r.get('recent_team') or '').upper()
        value=_number(r.get(field))
        if wk is None or not (0 < wk < before_week) or not team or value is None or value<0:
            continue
        key=(int(wk),team)
        totals[key]+=value
        counts[key]+=1
    observations=[]
    for (week,team),v in totals.items():
        opp=team_opp.get((week,team))
        if opp and counts[(week,team)]>=2:
            observations.append((week,opp, v))
    target=[v for week,opp,v in observations if opp==opponent.upper()]
    if len(target)<3 or len(observations)<35:
        return {'gate':'UNVERIFIED','reason':'Insufficient mapped opponent games or source coverage',
                'opponent_games':len(target),'league_team_weeks':len(observations)}
    avg=statistics.mean(v for _,_,v in observations)
    oppavg=statistics.mean(target)
    if avg<=0:
        return {'gate':'UNVERIFIED','reason':'Invalid league-average denominator'}
    weight=len(target)/(len(target)+10)
    factor=max(0.75,min(1.25,1+weight*(oppavg/avg-1)))
    return {'gate':'RESEARCH ONLY','metric':metric,'opponent_games':len(target),
            'league_team_weeks':len(observations),'league_team_week_avg':round(avg,2),
            'opponent_allowed_team_week_avg':round(oppavg,2),
            'contextual_factor':round(factor,3),
            'reason':'Unadjusted team-week totals allowed, not opponent quality or positional matchup; '
                     'pacing and game-script confounders remain. No numeric player success probability.'}


def historical_threshold(games: list[dict], *, field: str, line:float,
                         minutes_field: str | None = None) -> dict:
    """Exact displayed sample frequencies, not forward-looking probabilities."""
    if not math.isfinite(line):
        raise ValueError('Invalid threshold')
    selected=[]
    for r in games:
        v=_number(r.get(field))
        if v is None:continue
        if minutes_field is not None:
            mn=_number(r.get(minutes_field))
            if mn is None or mn <= 0:continue
        selected.append(v)
    if not selected:
        return {'gate':'UNVERIFIED','reason':'No numeric game observations'}
    last3=selected[-3:]
    last10=selected[-10:]
    # half lines count strictly >; ties can push on integer lines and are omitted from hits
    return {'gate':'DESCRIPTIVE ONLY','count':len(selected),'median':statistics.median(selected),
            'historical_min':min(selected),'last3':[{'value':v,'cleared':v>line,'margin':round(v-line,2)} for v in last3],
            'three_for_three':len(last3)==3 and all(v>line for v in last3),
            'last10_hits':sum(v>line for v in last10),'last10_games':len(last10),
            'all_hits':sum(v>line for v in selected),
            'reason':'Observed clearance history; a sample hit rate is NOT a projected probability.'}


def nba_walk_forward_research(raw_rows: list[dict], *, stat: str='points', max_players: int=90,
                             min_history: int=12, window: int=30) -> list[dict]:
    """NBA historical pregame-only forecasts with synthetic prior-determined lines.

    NOT retrospective sportsbook offered lines. Must not be used for betting ROI.
    Group by source player ID and require strictly earlier calendar dates.
    """
    from nba_model import estimate, normalize_logs
    from nba_data import _adapt_community_rows
    if stat not in ('points','rebounds','assists'):
        raise ValueError('Unsupported stat')
    logs = normalize_logs(_adapt_community_rows(raw_rows))
    grouped=defaultdict(list)
    for row in logs: grouped[row['player_id']].append(row)
    pids=sorted(grouped,key=lambda p:len(grouped[p]),reverse=True)[:max_players]
    out=[]
    for pid in pids:
        history=sorted(grouped[pid],key=lambda r:(r['game_date'],r['game_id']))
        for i in range(min_history,len(history)):
            target=history[i]
            prior=[h for h in history[max(0,i-window-4):i]
                   if h['game_date']<target['game_date']][-window:]
            if len(prior)<min_history:
                continue
            values=[_number(h.get(stat)) for h in prior]
            values=[v for v in values if v is not None]
            if len(values)<min_history:continue
            line=max(0.5,math.floor(statistics.median(values))+0.5)
            try:
                e=estimate(prior, stat, line)
                if e.get('status')!='BASELINE ONLY':continue
                over=_number(e.get('p_over'));under=_number(e.get('p_under'))
                if over is None or under is None or over+under<=0:continue
                targetval=_number(target.get(stat))
                if targetval is None:continue
                out.append({'id':f'{pid}|{target["game_id"]}|{stat}',
                            'date':target['game_date'].isoformat(),
                            'probability':over/(over+under),
                            'outcome':int(targetval>line),
                            'example_line':line,'player':target['player_name'],
                            'metric':stat})
            except (ValueError, TypeError,KeyError,ZeroDivisionError):
                continue
    return out


def nfl_game_elo_progress(rows: list[dict], *, cutoff: date | None = None,
                          start_season: int = 2022):
    """NFL game-winner exploratory Elo, reset halfway to 1500 each new season.

    Returns prior-only game forecasts and contemporary ratings. Does NOT model
    spread, totals, QB/OL injuries, coaching or sports-book market prices.
    """
    schedule=[]
    for r in rows:
        try:
            season=int(r.get('season',''))
            day=date.fromisoformat(str(r.get('gameday') or '')[:10])
        except (ValueError,TypeError):continue
        if season < start_season or (cutoff is not None and day>=cutoff):continue
        hp=_number(r.get('home_score'));ap=_number(r.get('away_score'))
        home,away=str(r.get('home_team') or ''),str(r.get('away_team') or '')
        if hp is None or ap is None or not home or not away or home==away:continue
        schedule.append((season,day,str(r.get('game_id') or ''),home,away,hp,ap))
    schedule.sort(key=lambda g:(g[1],g[2]))
    ratings=defaultdict(lambda:1500.0);predictions=[];oldseason=None
    for season,day,gid,home,away,hp,ap in schedule:
        if oldseason is not None and season!=oldseason:
            for name,elo in list(ratings.items()):
                ratings[name]=1500+0.5*(elo-1500)
        oldseason=season
        p=1/(1+10**(-(ratings[home]+45-ratings[away])/400))
        y=0.5 if hp==ap else float(hp>ap)
        if hp!=ap:
            predictions.append({'date':day.isoformat(),'event_id':gid,'home':home,'away':away,
                                'p_home_raw':p,'home_won':int(y),'season':season,
                                'home_pts':hp,'away_pts':ap})
        update=20*(y-p)
        ratings[home]+=update;ratings[away]-=update
    return dict(ratings),predictions
