"""NBA player-prop probability baseline; standard library only.

This is a historical, recency-weighted empirical estimator, NOT a validated
predictive edge. It never grades a selection TAIG/BTA+, bets, or invents data.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, date
from math import sqrt, isfinite

METRICS = {'Points': 'points', 'Rebounds': 'rebounds', 'Assists': 'assists'}
MIN_HISTORY = 12
WINDOW = 30
HALF_LIFE_GAMES = 9


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    for fmt in ('%Y-%m-%d', '%b %d, %Y', '%b %d, %Y %I:%M:%S %p', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(raw[:len(datetime.now().strftime(fmt))] if fmt == '%Y-%m-%dT%H:%M:%S' else raw, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw.replace('Z', '+00:00')).date()
    except ValueError as e:
        raise ValueError(f'Unrecognized game date: {raw}') from e


def normalize_logs(records):
    """Read NBA PlayerGameLogs CSV/DataFrame records or normalized input.

    Strictly rejects missing core fields rather than silently making up values.
    Data must be game-level box scores, one player + one game per row.
    """
    output = {}
    for idx, row in enumerate(records):
        if idx >= 100000:
            raise ValueError('CSV exceeds 100,000 rows. Upload a smaller file.')
        def get(*names):
            for name in names:
                v = row.get(name)
                if v is not None and str(v).strip() != '' and str(v).lower() != 'nan':
                    return v
            return None
        try:
            pid = str(get('PLAYER_ID', 'player_id') or '').strip()
            pname = str(get('PLAYER_NAME', 'player_name') or '').strip()
            gid = str(get('GAME_ID', 'game_id') or '').strip()
            d_raw = get('GAME_DATE','game_date')
            if not pid or not pname or not gid or d_raw is None:
                raise ValueError('missing player_id, name, game_id or date')
            d = _date(d_raw)
            raw_min = get('MIN','minutes','min')
            if isinstance(raw_min, str) and ':' in raw_min:
                mm, ss = raw_min.split(':', 1)
                m = float(mm) + float(ss)/60
            else:
                m = float(raw_min)
            p = float(get('PTS','points'))
            r = float(get('REB','rebounds'))
            a = float(get('AST','assists'))
            if any(not isfinite(x) or x < 0 for x in (m,p,r,a)) or m > 60:
                raise ValueError('invalid numerical values')
            if m <= 0:
                continue  # A DNP is not a statistical performance.
            matchup = str(get('MATCHUP','matchup') or '')
        except (TypeError, ValueError) as e:
            raise ValueError(f'Row {idx + 2}: {e}') from e
        key = (pid, gid)
        output[key] = {'player_id':pid, 'player_name':pname, 'game_id':gid,
                       'game_date':d, 'minutes':m, 'points':p, 'rebounds':r,
                       'assists':a, 'matchup':matchup}
    return sorted(output.values(), key=lambda x: (x['game_date'], x['game_id'], x['player_id']))


def group_players(logs):
    grouped = defaultdict(list)
    names = {}
    for row in logs:
        pid = row['player_id']; grouped[pid].append(row); names[pid] = row['player_name']
    return dict(grouped), names


def estimate(history, stat: str, line: float, min_games=MIN_HISTORY):
    """Estimate P(over/under/push) from past outcomes only.

    Weights decay by game; counts are shrunk toward neutral with 1 pseudo-
    observation each for over/under. Approximate uncertainty uses effective n.
    Not an opponent-adjusted, line-specific calibrated market model.
    """
    if stat not in ('points','rebounds','assists'):
        raise ValueError('Unknown NBA stat.')
    if not isfinite(float(line)) or line < 0 or line > 200:
        raise ValueError('Line must be between 0 and 200.')
    games = sorted(history, key=lambda x: (x['game_date'],x['game_id']))[-WINDOW:]
    if len(games) < min_games:
        return {'status':'INSUFFICIENT HISTORY','games':len(games),'min_required':min_games}
    weights = [2 ** (-(len(games) - 1 - i) / HALF_LIFE_GAMES) for i in range(len(games))]
    total = sum(weights)
    raw = [float(g[stat]) for g in games]
    wins = sum(w for w, v in zip(weights, raw) if v > line)
    losses = sum(w for w, v in zip(weights, raw) if v < line)
    pushes = max(0.0,total-wins-losses)
    # 1 pseudo hit and 1 pseudo miss to prevent 0%-100% overconfidence.
    denom = total + 2.0
    p_over, p_under, p_push = (wins+1)/denom, (losses+1)/denom, pushes/denom
    eff_n = total*total / sum(w*w for w in weights)
    se = sqrt(max(p_over*(1-p_over),0) / (eff_n+2))
    projected = sum(w*v for w,v in zip(weights,raw))/total
    mins = sum(w*g['minutes'] for w,g in zip(weights,games))/total
    rec5 = raw[-5:]
    return {'status':'BASELINE ONLY', 'games':len(games),
            'last_game':games[-1]['game_date'].isoformat(),
            'projection':projected, 'recent_5_avg':sum(rec5)/len(rec5),
            'projected_minutes_baseline':mins, 'p_over':p_over,
            'p_under':p_under, 'p_push':p_push,
            'over_90pct_approx_range':(max(0.0,p_over-1.645*se),min(1.0,p_over+1.645*se)),
            'effective_games':eff_n, 'sample_raw_over':wins/total}


def expected_roi(p_win, p_push, american):
    from engine import decimal_odds
    if not 0 <= p_win <= 1 or not 0 <= p_push <= 1 or p_win+p_push > 1.00000001:
        raise ValueError('Invalid probability inputs.')
    return p_win*(decimal_odds(american)-1) - (1-p_win-p_push)


def historical_brier(history, stat: str, line: float, min_games=MIN_HISTORY):
    """Chronological, no-lookahead check at a FIXED threshold (not historic odds).
    Pushes excluded from Brier; each outcome only uses earlier games.
    """
    rows = sorted(history,key=lambda x:(x['game_date'],x['game_id']))
    results = []
    for i in range(min_games,len(rows)):
        past = [r for r in rows[:i] if r['game_date'] < rows[i]['game_date']]
        model=estimate(past,stat,line,min_games)
        if model['status'] != 'BASELINE ONLY':
            continue
        if rows[i][stat] == line:
            continue
        truth = float(rows[i][stat] > line)
        # Conditioning on non-push decisions.
        q = model['p_over']/(model['p_over']+model['p_under'])
        results.append((q,truth))
    if not results:
        return {'count':0,'status':'NOT ENOUGH HISTORY'}
    brier = sum((p-y)**2 for p,y in results)/len(results)
    return {'count':len(results),'brier':brier,
            'avg_predicted_over':sum(p for p,_ in results)/len(results),
            'actual_over_rate':sum(y for _,y in results)/len(results),
            'status':'FIXED-LINE BACKTEST ONLY'}


def automatic_baselines(logs, max_players=120):
    """Unpriced scouting: derive example thresholds from each player's history.
    Does not imply a sportsbook offers these lines or any edge exists.
    """
    by_id, names = group_players(logs)
    out = []
    for pid,history in by_id.items():
        if len(history)<MIN_HISTORY:
            continue
        history = sorted(history,key=lambda x:(x['game_date'],x['game_id']))
        # limit to most recently active players only (historical team players filtered by date)
        last = history[-1]['game_date']
        for display, stat in METRICS.items():
            m0 = estimate(history,stat,0.5)
            if m0['status'] != 'BASELINE ONLY':continue
            line = int(m0['projection']) + 0.5
            m = estimate(history,stat,line)
            out.append({'player':names[pid], 'player_id':pid,'stat':display,
                        'example_line':line,'proj':round(m['projection'],2),
                        'over_pct':round(100*m['p_over'],1),
                        'under_pct':round(100*m['p_under'],1),
                        'games':m['games'],'last_game':last.isoformat(),
                        'status':'UNPRICED BASELINE • NOT A PICK'})
    out.sort(key=lambda r:(r['last_game'],r['games']),reverse=True)
    return out[:max_players*3]
