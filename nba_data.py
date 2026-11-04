"""Optional source fetch from official NBA statistics through third-party nba_api.

NBA.com can timeout/block hosted applications. CSV import is the supported fallback.
"""
import csv
import io
from nba_model import normalize_logs


def fetch_nba_logs(seasons=('2025-26','2026-27')):
    try:
        from nba_api.stats.endpoints import playergamelogs
    except ImportError as e:
        raise RuntimeError('Install nba_api using requirements.txt or upload a game-log CSV.') from e
    allrows = []
    for season in seasons:
        try:
            response = playergamelogs.PlayerGameLogs(
                season_nullable=season,season_type_nullable='Regular Season',timeout=20)
            dataframes = response.get_data_frames()
            if not dataframes or dataframes[0].empty:
                raise RuntimeError('empty response')
            allrows.extend(dataframes[0].to_dict(orient='records'))
        except Exception as e:
            raise RuntimeError(f'NBA stats unavailable for {season}. Upload a genuine PlayerGameLogs CSV. Source error: {type(e).__name__}') from e
    return normalize_logs(allrows)


def parse_uploaded_csv(uploaded_file):
    raw = uploaded_file.getvalue()
    if len(raw)>12_000_000:
        raise ValueError('CSV exceeds 12MB limit.')
    try:
        content=raw.decode('utf-8-sig')
    except UnicodeError as e:
        raise ValueError('CSV must be UTF-8.') from e
    records = csv.DictReader(io.StringIO(content))
    return normalize_logs(records)
