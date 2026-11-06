"""Verified-format NFL play-level auditing from nflverse (not an official inactive list).

Downloads only publicly published, bounded nflverse CSV.gz releases; never
claims that a player with zero recorded plays was absent, healthy, or active.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
from math import isfinite
import csv, gzip, io
from urllib.request import Request,urlopen


def _float(v):
    try:
        f=float(v)
        return f if isfinite(f) else None
    except (ValueError,TypeError):return None


def _flag(v):
    return str(v or '').strip().lower() in ('1','1.0','true','t','yes')


def fetch_nfl_pbp(season:int,*, max_compressed_bytes:int=25_000_000,
                  player_id:str|None=None) -> tuple[list[dict],dict]:
    """Select rows relevant to player; use season URL fixed to vetted provider.
    Parquet isn't needed: .csv.gz processed with stdlib and memory-bound rows.
    """
    if not (2000<=season<=2100):raise ValueError('Season out of bounds')
    url=f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv.gz'
    req=Request(url,headers={'User-Agent':'BTA Research v0.7','Accept':'application/octet-stream'})
    with urlopen(req,timeout=35) as response:
        payload=response.read(max_compressed_bytes+1)
    if len(payload)>max_compressed_bytes:raise ValueError('PBP exceeds compressed download limit')
    if payload[:2]!=b'\x1f\x8b':raise ValueError('Provider did not return gzip')
    try:
        handle=io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(payload)),encoding='utf-8-sig',newline='')
        reader=csv.DictReader(handle)
        necessary={'game_id','qtr','posteam','rusher_player_id','receiver_player_id',
                   'rush_attempt','pass_touchdown','rush_touchdown','yardline_100','rushing_yards','receiving_yards'}
        if not reader.fieldnames or not necessary.issubset(set(reader.fieldnames)):
            raise ValueError('nflverse play-by-play schema changed')
        relevant=[]
        for i,r in enumerate(reader):
            if i>120_000:raise ValueError('PBP row count safety limit exceeded')
            if player_id is None or player_id in (r.get('rusher_player_id'),r.get('receiver_player_id'),r.get('passer_player_id')):
                relevant.append({key:r.get(key) for key in
                    ('game_id','week','season','season_type','posteam','defteam','qtr','no_play','qb_kneel','qb_spike',
                     'yardline_100','rush_attempt','rusher_player_id','rushing_yards','receiver_player_id',
                     'receiving_yards','pass_touchdown','rush_touchdown','passer_player_id','pass_attempt')})
                if len(relevant)>120_000:raise ValueError('Relevant play limit exceeded')
    except (OSError,UnicodeDecodeError,csv.Error) as exc:
        raise ValueError('Could not parse verified-format nflverse PBP') from exc
    return relevant,{'source':url,'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),
                     'rows_selected':len(relevant),'player_id_filter':player_id}


def audit_nfl_player_plays(plays:list[dict],*,player_id:str,goal_line_yards:int=5,
                           quarter_stat:str='RUSH',quarter_threshold:float=5.0,
                           before_week:int|None=None) -> dict:
    """Descriptive opportunities and quarter thresholds, restricted to regulation.

    Only games where player appears in relevant play fields are counted. Compare
    against official participation/snap records before interpreting denominators.
    """
    if not player_id or not str(player_id).strip():raise ValueError('player_id required')
    if quarter_stat not in {'RUSH','RECEIVING'}:raise ValueError('Unknown stat')
    if goal_line_yards<1 or goal_line_yards>20:raise ValueError('Invalid goal line region')
    if before_week is not None and not (1<=before_week<=23):raise ValueError('Invalid NFL cutoff week')
    games=defaultdict(lambda:{'rush':0.,'receiving':0.,'rushes':0,'targets_or_receptions':0,
                              'inside_5_rushes':0,'red_zone_rushes':0,'inside_5_targets':0,
                              'rushing_tds':0,'receiving_tds':0,
                              'rush_plays':[],'rec_plays':[],'quarters':defaultdict(lambda:{'RUSH':0.,'RECEIVING':0.})})
    for row in plays:
        if before_week is not None:
            wk=_float(row.get('week'))
            if wk is None or wk>=before_week:continue  # strict pregame chronological filter
        if _flag(row.get('no_play')) or _flag(row.get('qb_kneel')) or _flag(row.get('qb_spike')):
            continue
        if str(row.get('season_type') or 'REG').upper() not in ('REG','REGULAR'):
            continue
        game=str(row.get('game_id') or '')
        if not game:continue
        q=_float(row.get('qtr'))
        if q is None or int(q)!=q or not 1<=q<=4:
            continue  # overtime excluded pending exact market rule
        q=int(q)
        yard=_float(row.get('yardline_100'))
        g=games[game]
        if row.get('rusher_player_id')==player_id and _flag(row.get('rush_attempt')):
            gain=_float(row.get('rushing_yards'))
            if gain is None:continue
            g['rush']+=gain;g['rushes']+=1;g['quarters'][q]['RUSH']+=gain;g['rush_plays'].append(gain)
            if yard is not None and 0<=yard<=20:g['red_zone_rushes']+=1
            if yard is not None and 0<=yard<=goal_line_yards:g['inside_5_rushes']+=1
            if _flag(row.get('rush_touchdown')):g['rushing_tds']+=1
        if row.get('receiver_player_id')==player_id:
            gain=_float(row.get('receiving_yards'))
            # Does not count routes; NFL PBP does not reliably identify every target.
            if gain is not None:
                g['receiving']+=gain;g['targets_or_receptions']+=1;g['quarters'][q]['RECEIVING']+=gain;g['rec_plays'].append(gain)
            if yard is not None and 0<=yard<=goal_line_yards:g['inside_5_targets']+=1
            if _flag(row.get('pass_touchdown')):g['receiving_tds']+=1
    results=[]
    for game,g in games.items():
        if not g['rushes'] and not g['targets_or_receptions']:
            continue
        q_values={q:dict(v) for q,v in g['quarters'].items()}
        quarter_success=any(stats[quarter_stat]>=quarter_threshold for stats in q_values.values())
        long_r=max(g['rush_plays']) if g['rush_plays'] else None
        long_c=max(g['rec_plays']) if g['rec_plays'] else None
        results.append({'game_id':game, 'rushing_yards':round(g['rush'],2),'receiving_yards':round(g['receiving'],2),
                        'rushing_attempts':g['rushes'],'recorded_receptions':g['targets_or_receptions'],
                        'inside_5_rushes':g['inside_5_rushes'],'red_zone_rushes':g['red_zone_rushes'],
                        'inside_5_recorded_receiving_plays':g['inside_5_targets'],
                        'rushing_tds':g['rushing_tds'],'receiving_tds':g['receiving_tds'],
                        'rush_without_longest':round(g['rush']-long_r,2) if long_r is not None else None,
                        'receiving_without_longest':round(g['receiving']-long_c,2) if long_c is not None else None,
                        'regulation_quarters':q_values,'met_any_regulation_quarter':quarter_success})
    results.sort(key=lambda r:r['game_id'])
    count=len(results)
    return {'status':'RESEARCH ONLY' if count>=3 else 'INSUFFICIENT','player_id':player_id,
            'games_with_recorded_relevant_plays':count,'games':results,
            'total_inside_5_rushes':sum(g['inside_5_rushes'] for g in results),
            'total_rushing_tds':sum(g['rushing_tds'] for g in results),
            'total_receiving_tds':sum(g['receiving_tds'] for g in results),
            'any_quarter_threshold':quarter_threshold,'quarter_stat':quarter_stat,
            'any_regulation_quarter_clears':sum(g['met_any_regulation_quarter'] for g in results),
            'pregame_cutoff_week':before_week,
            'warnings':['Participation denominators incomplete: games with no recorded player play are not counted.',
                        'No claims about routes, target counts, inactives, overtime contract rules, or push/void.',
                        'Goal-line opportunity share requires team-wide play records, not a player-filtered file.',
                        'Without an exact before_week, outputs must not be used as a pregame forecast.',
                        'Scoring and official result may differ after stat corrections.']}
