"""Run hourly via GitHub Actions, or on demand by `python -m bta_v09.runner`.

Default is PUBLIC-SAFE schedule/source metadata only. To store bookmaker
markets you must explicitly confirm *private* storage + license permissions.
"""
from __future__ import annotations
import os
from pathlib import Path
from .pipeline import collect_research,write_snapshot,append_forecasts


def main():
    secret=os.environ.get('BTA_ODDS_API_KEY','').strip()
    private=os.environ.get('BTA_PRIVATE_STORAGE','')=='1'
    has_permission=os.environ.get('BTA_MARKET_STORAGE_PERMITTED','')=='1'
    full=private and has_permission
    if secret and not full:
        print('Odds key detected; no market details will be persisted. '
              'Enable only after checking repo privacy and provider data rights.')
    snapshot,forecasts=collect_research(
        cfbd_key=os.environ.get('CFBD_API_KEY','').strip(),
        odds_key=secret if full else '',include_props=os.environ.get('BTA_ENABLE_PROPS','0')=='1',
        save_market_details=full)
    base=Path('bta_snapshots/v09')
    write_snapshot(snapshot,base/'latest.json')
    if full:
        count=append_forecasts(base/'forecast_journal.jsonl',forecasts)
        print(f'Appended {count} prospective research model forecasts')
    errors=sum(len(v['source_errors']) for v in snapshot['leagues'].values())
    print(f'BTA v0.9 research snapshot: {sum(len(v["games"]) for v in snapshot["leagues"].values())} '
          f'scheduled events, {errors} scoreboard read errors, {len(forecasts)} model forecasts')
    if all(not v['complete'] for v in snapshot['leagues'].values()):
        raise SystemExit('All league scoreboards failed. Snapshot reports failure; do not assume no games.')

if __name__=='__main__':main()
