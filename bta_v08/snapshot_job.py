"""Optional scheduled *schedule* snapshot, no sportsbook data or fake forecast.
Run in GitHub Actions or locally. Uses no API keys. Output is publicly shareable.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from .schedule import collect, next_days, utcstamp


def build_snapshot(now: datetime | None = None, *, fetcher=None) -> dict:
    now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    local=now.astimezone(ZoneInfo('America/New_York')).date()
    days=next_days(local,horizon=3)
    result={'version':'v0.8','captured_at_utc':now.isoformat(),
            'includes_model_forecasts':False,'includes_verified_market_offers':False,
            'data_status':'SCHEDULE ONLY: NO BTA GRADES', 'leagues':{}}
    for league in ('NBA','NFL','College football'):
        kwargs={'fetcher':fetcher} if fetcher else {}
        slate=collect(league,days,**kwargs)
        # trim source display, not user secrets
        result['leagues'][league]={'games':slate['games'], 'errors':slate['errors'],
                                   'complete':slate['complete']}
    return result


def main() -> None:
    result=build_snapshot()
    path=Path('bta_snapshots/v08/latest_schedule.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    # On wholly broken feeds, preserve the errors in output; don't claim success.
    broken=all(not v['complete'] for v in result['leagues'].values())
    if broken:raise SystemExit('All providers failed; snapshot contains errors but pipeline cannot be called healthy')

if __name__=='__main__':main()
