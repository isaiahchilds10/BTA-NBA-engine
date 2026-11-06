"""Strict cross-provider game identity mapping.

Never match a quote, injury report, or settlement to a different game based
on team nicknames alone. Only a unique exact home/away plus league/time match
can be mapped automatically; otherwise stop and require provider event IDs.
"""
from __future__ import annotations
from .common import parse_time


def _name(x):
    return ' '.join(str(x or '').casefold().replace('.', ' ').split())


def resolve(schedule_event:dict, candidates:list[dict], *,max_start_gap_minutes:int=30)->dict:
    if not 0<=max_start_gap_minutes<=45:return {'status':'INVALID_TOLERANCE'}
    start=parse_time(schedule_event.get('start_utc'))
    if not start:return {'status':'MISSING_SCHEDULE_START'}
    sport=schedule_event.get('league')
    h=schedule_event.get('home') or {}; a=schedule_event.get('away') or {}
    home=_name(h.get('name'));away=_name(a.get('name'))
    if not home or not away or home==away:return {'status':'INVALID_PARTICIPANTS'}
    matches=[]
    for row in candidates:
        if not isinstance(row,dict) or row.get('league')!=sport:continue
        t=parse_time(row.get('start_utc'))
        if not t or abs((t-start).total_seconds())>max_start_gap_minutes*60:continue
        if _name(row.get('home'))==home and _name(row.get('away'))==away and row.get('event_id'):
            matches.append(row)
    if len(matches)!=1:
        return {'status':'AMBIGUOUS_PROVIDER_EVENT' if len(matches)>1 else 'NO_EXACT_MATCH',
                'matches':len(matches),'note':'Never assign a similarly named or rematched game automatically.'}
    return {'status':'EXACT_CROSSWALK','schedule_event_id':schedule_event.get('event_key'),
            'provider_event_id':matches[0]['event_id'],'league':sport,
            'note':'Names, home/away and start match uniquely; provider identifiers should still be persisted and rechecked when schedules change.'}
