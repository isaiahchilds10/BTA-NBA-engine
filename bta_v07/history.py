"""Market-exact historical audits. Observed frequencies are never future probabilities."""
from __future__ import annotations
from collections import defaultdict
from datetime import date, datetime, timezone
from math import isfinite
from statistics import median, mean


def _num(v):
    try:
        x=float(v)
        return x if isfinite(x) else None
    except (TypeError,ValueError):
        return None


def _date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def market_result(value: float, line: float, side: str, *, market_kind: str = 'OVER_UNDER') -> str:
    """OVER/UNDER comparisons; inclusive YES/NO are different contract types.

    sportsbook OVER 20.5 requires >20.5; sportsbook UNDER 20.5 requires <20.5;
    integer threshold ties PUSH unless market rules override. 'YES_AT_LEAST'
    uses an inclusive threshold; 'NO_AT_LEAST' means strictly below threshold.
    """
    if not all(isfinite(float(v)) for v in (value,line)):
        raise ValueError('Nonfinite line or statistic')
    if market_kind == 'OVER_UNDER':
        if side not in {'OVER','UNDER'}:
            raise ValueError('Specify OVER/UNDER')
        if value == line: return 'PUSH'
        return 'WIN' if (value > line if side=='OVER' else value < line) else 'LOSS'
    if market_kind == 'YES_NO_THRESHOLD':
        if side not in {'YES','NO'}:
            raise ValueError('Specify YES or NO')
        return 'WIN' if (value>=line if side=='YES' else value<line) else 'LOSS'
    raise ValueError('Unverified market settlement type')


def historical_audit(games: list[dict], *, field: str, line: float, side: str,
                     before: date, market_kind: str = 'OVER_UNDER',
                     sample_season: str | None = None, min_comparable_games: int = 3) -> dict:
    """A game row must contain `date`, `game_id`, `field`, optional `eligible`.

    If eligible is False/None, exclude from hit denominator and disclose count.
    If an eligible row lacks the stat, count it as missing rather than a miss.
    Reject duplicate game IDs and no-lookahead violations.
    """
    if min_comparable_games<1:raise ValueError('min_comparable_games must be positive')
    accepted=[];skipped=[];seen=set()
    for row in games:
        try: dt=_date(row.get('date'))
        except (ValueError,TypeError):
            skipped.append({'game_id':row.get('game_id'),'reason':'invalid date'});continue
        if dt>=before: continue
        if sample_season is not None and str(row.get('season'))!=str(sample_season):continue
        ident=str(row.get('game_id') or '').strip()
        if not ident:
            skipped.append({'date':str(dt),'reason':'missing game id'});continue
        if ident in seen:raise ValueError(f'Duplicate game {ident} in candidate sample')
        seen.add(ident)
        if row.get('eligible') is not True:
            skipped.append({'game_id':ident,'reason':'participation or role comparability unverified'});continue
        value=_num(row.get(field))
        if value is None:
            skipped.append({'game_id':ident,'reason':f'{field} missing'});continue
        outcome=market_result(value,line,side,market_kind=market_kind)
        # Positive margin means selection cleared its exact requirement.
        margin=(value-line) if side in ('OVER','YES') else (line-value)
        accepted.append({'game_id':ident,'date':dt.isoformat(),'value':value,
                         'result':outcome,'clearance_margin':round(margin,3),
                         'opponent':row.get('opponent'), 'minutes':row.get('minutes'),
                         'snap_pct':row.get('snap_pct')})
    accepted.sort(key=lambda r:(r['date'],r['game_id']))
    if not accepted:
        return {'status':'INSUFFICIENT','reason':'No valid pregame eligible statistical games','skipped':skipped}
    vals=[r['value'] for r in accepted]
    wins=[r for r in accepted if r['result']=='WIN']; losses=[r for r in accepted if r['result']=='LOSS']
    pushes=[r for r in accepted if r['result']=='PUSH']
    decided=len(wins)+len(losses)
    n=len(accepted)
    first_three=accepted[:3]
    recent_three=accepted[-3:]
    last_ten=accepted[-10:]
    margins=sorted([r['clearance_margin'] for r in accepted])
    def wins_of(sample):return sum(r['result']=='WIN' for r in sample)
    def pct(sample):
        d=sum(r['result']!='PUSH' for r in sample)
        return round(wins_of(sample)/d,4) if d else None
    q10=vals and sorted(vals)[int((len(vals)-1)*.10)]
    return {'status':'RESEARCH ONLY' if n>=min_comparable_games else 'INSUFFICIENT',
            'market_kind':market_kind,'side':side,'line':float(line),
            'n_games':n,'n_decided':decided,'wins':len(wins),'losses':len(losses),'pushes':len(pushes),
            'historical_hit_rate':round(len(wins)/decided,4) if decided else None,
            'sample_first_three':first_three,'first_three_three_for_three':len(first_three)==3 and wins_of(first_three)==3,
            'recent_three':recent_three,'recent_three_hits':wins_of(recent_three),
            'last_ten':last_ten,'last_ten_hits':wins_of(last_ten),'last_ten_win_rate':pct(last_ten),
            'median':round(median(vals),3),'mean':round(mean(vals),3),'historical_min':min(vals),
            'historical_tenth_percentile':q10,'median_clearance_margin':round(median(margins),3),
            'losses_for_review':losses, 'skipped':skipped,
            'caution':'Historical hit rates and observed lower tail are not a future probability, guaranteed floor, or proof of an edge.'}


def nba_logs_for_player(rows: list[dict], player_name: str, *, stat: str, before:date) -> list[dict]:
    """Convert NBA community file schema to stable per-game historical rows.
    NBA IDs in community data are treated as player IDs; game IDs must be built
    from date+team+opponent and may collide on unusual doubleheaders (reject).
    """
    if stat not in {'Points','Rebounds','Assists'}:
        raise ValueError('Unsupported NBA stat')
    output=[]
    for r in rows:
        if str(r.get('Player','')).casefold().strip()!=player_name.casefold().strip():continue
        try: dt=_date(r.get('Date'))
        except (ValueError,TypeError):continue
        if dt>=before:continue
        minutes=_num(r.get('Minutes'));value=_num(r.get(stat))
        team=str(r.get('Team','')).strip().upper();opp=str(r.get('Opp','')).strip().upper()
        if not team or not opp: continue
        # Synthetic ID is NOT an official NBA Game ID; only use for local deduplication.
        ident=f'{dt.isoformat()}:{team}:{opp}:{r.get("ID")}'
        output.append({'date':dt.isoformat(),'game_id':ident,'season':r.get('Season'),
                       'opponent':opp,stat:value,'minutes':minutes,
                       'eligible':minutes is not None and minutes>0})
    return output
