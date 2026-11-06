"""Best-effort provider-refresh status job. Does not archive licensed odds.

Run with python -m bta_v10.refresh_job; GitHub Actions upload is an artifact,
not a persistent database and is not automatically exposed to Streamlit.
"""
from __future__ import annotations
from pathlib import Path
from json import dumps
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from bta_v08.schedule import collect,next_days
from bta_v10.common import digest


def run(*,collector=collect,now:datetime|None=None)->dict:
    ref=now or datetime.now(timezone.utc)
    if ref.tzinfo is None:raise ValueError('Time must be timezone-aware')
    day=ref.astimezone(ZoneInfo('America/New_York')).date()
    result={'version':'v1.0-review','built_at_utc':ref.astimezone(timezone.utc).isoformat(),
            'quality':'PUBLIC SAFE, SCHEDULES ONLY; NO BETTING RECOMMENDATIONS','leagues':{}}
    for league in ('NBA','NFL','College football'):
        try:
            records=collector(league,next_days(day,horizon=3))
            events=[{'event_key':r['event_key'],'start_utc':r['start_utc'],
                     'status':r['status'],'home':r['home']['name'],'away':r['away']['name'],
                     'source_retrieved_at_utc':r.get('retrieved_at_utc')} for r in records['games']]
            result['leagues'][league]={'games':events,'errors':records.get('errors',[]),
                                      'source_ok':records.get('complete',False),
                                      'fingerprint':digest(events)}
        except Exception as exc:
            result['leagues'][league]={'games':[], 'source_ok':False,'errors':[{'error_class':type(exc).__name__}]}
    return result


def main():
    report=run()
    out=Path('bta_snapshots/v10/public_status.json');out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(dumps(report,sort_keys=True,indent=2),encoding='utf-8')
    print('Snapshot:',out,'games=',sum(len(x['games']) for x in report['leagues'].values()))
    if not any(v['source_ok'] for v in report['leagues'].values()):
        raise SystemExit('No successfully verified schedule responses.')

if __name__=='__main__':main()
