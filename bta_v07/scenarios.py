"""Sport-specific scenario families; empirical analogs are NOT causal proof."""
from __future__ import annotations
from statistics import mean

SCRIPT_FAMILIES={
    'NFL_PROP':['favorite_blowout','underdog_blowout','close_game','low_scoring','shootout'],
    'NBA_PROP':['own_team_blowout','opponent_blowout','close_game','slow_game','fast_game'],
    'CFB_MONEYLINE':['normal','underdog_early_lead','favorite_minus_two_turnovers',
                     'primary_strength_neutralized','one_possession_fourth_quarter'],
}


def validate_scenarios(family:str,scenarios:list[dict]) -> dict:
    if family not in SCRIPT_FAMILIES:raise ValueError('Unsupported scenario family')
    expected=SCRIPT_FAMILIES[family]
    received={s.get('scenario'):s for s in scenarios}
    if set(received)!=set(expected) or len(received)!=len(expected):
        return {'status':'INCOMPLETE','missing':[x for x in expected if x not in received],
                'reason':'All five distinct scripts must be supported'}
    for key in expected:
        s=received[key];v=s.get('verdict')
        valid={'BETTER','SAME','MIXED','WORSE'} if family.endswith('PROP') else {'SURVIVES','AT_RISK','FAILS','UNKNOWN'}
        if v not in valid or not str(s.get('mechanism') or '').strip() or not str(s.get('evidence_source') or '').strip():
            return {'status':'INCOMPLETE','reason':f'{key} lacks supported scenario verdict/mechanism'}
    worse=sum(s['verdict']=='WORSE' for s in scenarios)
    if family.endswith('PROP') and worse>=2:
        return {'status':'CUT','worse_count':worse,'reason':'At least two meaningful WORSE scripts'}
    if family=='CFB_MONEYLINE' and any(s['verdict']=='UNKNOWN' for s in scenarios):
        return {'status':'REVIEW','reason':'Unverified adverse college moneyline scenario'}
    return {'status':'REVIEW','worse_count':worse,
            'reason':'Five scripts documented; empirical and causal validity require independent review'}


def scenario_analogs(games:list[dict],*,line:float,side:str, before=None,
                     min_games_per_script:int=5) -> dict:
    """Research-only description using fully observed historical games.

    Required game fields: points, game_margin, game_total, win_side_favorite;
    also can include low/high scoring threshold determined from historical data.
    Does not claim counterfactual scripts are equally probable.
    """
    from bta_v07.history import market_result
    result={}
    groups={'own_team_blowout':[],'opponent_blowout':[],'close_game':[],
            'slow_game':[],'fast_game':[]}
    from datetime import date
    if before is None:
        return {'status':'INSUFFICIENT','reason':'Pregame cutoff date required to prevent future leakage'}
    if isinstance(before,str):before=date.fromisoformat(before)
    valid=[]
    for r in games:
        try: d=date.fromisoformat(str(r.get('date'))[:10])
        except (TypeError,ValueError):continue
        if d>=before:continue
        if all(isinstance(r.get(k),(int,float)) for k in ('value','game_margin','game_total')):
            valid.append(r)
    if len(valid)<25:return {'status':'INSUFFICIENT','reason':'Need 25 prior fully-contextualized games'}
    totals=sorted(r['game_total'] for r in valid)
    low=totals[int(.25*(len(totals)-1))];high=totals[int(.75*(len(totals)-1))]
    for r in valid:
        margin=r['game_margin'];total=r['game_total']
        if margin>=15:groups['own_team_blowout'].append(r)
        if margin<=-15:groups['opponent_blowout'].append(r)
        if abs(margin)<=6:groups['close_game'].append(r)
        if total<=low:groups['slow_game'].append(r)
        if total>=high:groups['fast_game'].append(r)
    for label,sample in groups.items():
        wins=sum(market_result(r['value'],line,side)=='WIN' for r in sample)
        decided=sum(market_result(r['value'],line,side)!='PUSH' for r in sample)
        result[label]={'n':len(sample),'wins':wins,'rate':round(wins/decided,4) if decided else None,
                       'status':'DESCRIPTIVE' if len(sample)>=min_games_per_script else 'INSUFFICIENT',
                       'verdict':'UNKNOWN','mechanism':'Cannot infer game-script causal effect from game-level history alone'}
    return {'status':'SCENARIO ANALOGS ONLY','scenarios':result,
            'warning':'Game analogs may be selected on outcomes and confounded by opponents/personnel. No automatic BETTER/WORSE assigned.'}
