"""Collect a small, attributed schedule-status snapshot for background display.

Usage: python -m bta_v06.refresh
The collector NEVER assigns betting grades, probabilities, or wagers.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from .live import nba_monitor, espn_schedule, utc_now

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / 'bta_snapshots' / 'current.json'


def capture(now: datetime | None = None, *, nba_fetch=nba_monitor, espn_fetch=espn_schedule) -> dict:
    now = now or datetime.now(timezone.utc)
    stamp = now.astimezone(timezone.utc).strftime('%Y%m%d')
    out = {'schema_version': 1, 'captured_at_utc': utc_now(), 'date_utc': stamp,
           'sources': {}, 'note': 'Monitoring only; no lines, live odds, lineup verification, or BTA picks.'}
    for name, producer in [
        ('NBA official scoreboard', nba_fetch),
        ('NFL schedule / score', lambda: espn_fetch('NFL', stamp)),
        ('College football schedule / score', lambda: espn_fetch('College football', stamp)),
    ]:
        try:
            data = producer()
            if not isinstance(data, dict) or data.get('status') != 'OK':
                raise ValueError('Provider did not confirm a usable response')
            out['sources'][name] = data
        except Exception as exc:
            out['sources'][name] = {'status': 'UNVERIFIED', 'retrieved_at_utc': utc_now(),
                                    'error_type': type(exc).__name__,
                                    'message': str(exc)[:180], 'games': []}
    return out


def write_atomic(payload: dict, output: Path = DEFAULT_OUTPUT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + '.tmp')
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    os.replace(temp, output)


def main() -> None:
    payload = capture()
    write_atomic(payload)
    statuses = {k: v.get('status') for k, v in payload['sources'].items()}
    print('BTA source monitoring (not prediction):', json.dumps(statuses, sort_keys=True))
    # Return success even if a provider is down: the file explicitly records UNVERIFIED.


if __name__ == '__main__':
    main()
