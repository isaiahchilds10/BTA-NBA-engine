"""Read the existing v0.9 automatic collector output and add v1.0 vetoes.

Does not copy API keys, proprietary odds, unsupported predictions or player
names to a public artifact. This is an audit overlay; no invented markets.
"""
from __future__ import annotations
from .common import utc


def audit_auto_snapshot(snapshot:dict)->dict:
    if not isinstance(snapshot,dict) or not isinstance(snapshot.get('leagues'),dict):
        return {'status':'BAD_SNAPSHOT','games':[]}
    results=[]
    for league,section in snapshot['leagues'].items():
        if not isinstance(section,dict):continue
        history=section.get('history_publication_audit') or {}
        injury=section.get('injury_source') or {}
        injuries_ok=False  # A report is NOT authenticated actual participation
        historical_ok=history.get('status') in ('RECENT PUBLICATION','WEEKLY HISTORY ONLY')
        if league=='College football':historical_ok=bool(section.get('history_sources'))
        for event in section.get('games',[]):
            blockers=[]
            if event.get('status')!='UPCOMING':blockers.append('Game is not an upcoming pregame market')
            if not utc(event.get('start_utc')):blockers.append('Game start missing timezone')
            if not section.get('complete'):blockers.append('Schedule source incomplete')
            if not historical_ok:blockers.append('Historical source coverage not confirmed')
            if not injuries_ok:blockers.append('Current participant availability is unverified')
            if event.get('candidate_count',0)==0:blockers.append('No exact matched available offered markets')
            blockers.extend(['Opponent-adjusted role/roster verification pending',
                             'Independent red-team review pending',
                             'Prospective calibrated holdout forecast missing',
                             'Correlation/settlement validation pending'])
            results.append({'league':league,'event_key':event.get('event_key'),
                            'start_utc':event.get('start_utc'),
                            'status':'RESEARCH_PENDING','bta_grade':'NO CERTIFIED GRADE',
                            'blockers':blockers,
                            'data_provenance':{'injury_status':injury.get('status','UNKNOWN'),
                                               'history_status':history.get('status','UNKNOWN')}})
    return {'status':'RESEARCH_AUDIT_ONLY','games':results,
            'source_snapshot_built_at':snapshot.get('built_at_utc'),
            'note':'No graded BTA picks are generated from stale, incomplete or unauthenticated research.'}


def changes_between(previous:dict|None,current:dict)->dict:
    def lookup(s):
        return {(lg,e.get('event_key')):e for lg,section in (s or {}).get('leagues',{}).items()
                for e in section.get('games',[]) if e.get('event_key')}
    earlier=lookup(previous);now=lookup(current)
    changed=[]
    for key,item in now.items():
        before=earlier.get(key)
        material=('start_utc','status','candidate_count','grade')
        if before is None or any(item.get(k)!=before.get(k) for k in material):
            changed.append({'league':key[0],'event_key':key[1],
                            'reason':'NEW EVENT' if before is None else 'MATERIAL SOURCE/STATE CHANGE',
                            'invalidate_old_grade':True})
    return {'status':'CHANGES_DETECTED' if changed else 'NO_TRACKED_CHANGES',
            'changed':changed,'removed_event_keys':[{'league':k[0],'event_key':k[1]} for k in earlier if k not in now],
            'note':'Disappeared games may indicate provider failure, postponement or schedule window roll-over.'}
