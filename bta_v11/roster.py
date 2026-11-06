"""Historical college roster continuity, no fabrication of active depth charts."""
from __future__ import annotations


def continuity(previous:dict,current:dict,*,key_positions=('QB','OL','DL')):
    if previous.get('status')!='ROSTER_LIST_ONLY' or current.get('status')!='ROSTER_LIST_ONLY' or previous.get('team')!=current.get('team'):
        return {'status':'INSUFFICIENT_COMPARABLE_ROSTERS'}
    old={r['player_id']:r for r in previous['players'] if r.get('player_id')}
    cur={r['player_id']:r for r in current['players'] if r.get('player_id')}
    if len(old)<10 or len(cur)<10:return {'status':'SMALL_ROSTER_SAMPLE','old_count':len(old),'new_count':len(cur)}
    keep=set(old)&set(cur)
    position_changes=[]
    for ident in keep:
        if old[ident].get('position')!=cur[ident].get('position'):
            position_changes.append(ident)
    return {'status':'DESCRIPTIVE_ROSTER_CONTINUITY','previous_n':len(old),'current_n':len(cur),
            'returning_n':len(keep),'returning_fraction_of_previous':round(len(keep)/len(old),4),
            'qbs_listed_current':[r['name'] for r in cur.values() if r.get('position')=='QB'],
            'position_changes_n':len(position_changes),
            'note':'Count is NOT returning production or a confirmed current starter, injury, or depth chart.'}
