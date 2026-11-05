"""NBA game-log ingestion.
Accepts official NBA PlayerGameLogs exports and the game-log CSV published by
xtheredshirtx/fanduel-player-data (as of 2026-11-03).
Important: the latter has NO official NBA GAME_ID. A local deterministic
matchup/date key is used solely to deduplicate player-game rows for the model;
it is NOT an NBA game ID. These community CSVs may include postseason games.
"""
import csv
import io
from datetime import date
from nba_model import normalize_logs

_FANDUEL_REQUIRED = {
'Date', 'Player', 'ID', 'Team', 'Opp', 'Season',
'Minutes', 'Points', 'Rebounds', 'Assists'
}

def fetch_nba_logs(seasons=('2025-26', '2026-27')):
try:
from nba_api.stats.endpoints import playergamelogs
except ImportError as e:
raise RuntimeError('Install nba_api using requirements.txt or upload a game-log CSV.') from e
allrows = []
for season in seasons:
try:
response = playergamelogs.PlayerGameLogs(
season_nullable=season, season_type_nullable='Regular Season', timeout=20
)
dataframes = response.get_data_frames()
if not dataframes or dataframes[0].empty:
raise RuntimeError('empty response')
allrows.extend(dataframes[0].to_dict(orient='records'))
except Exception as e:
raise RuntimeError(
f'NBA stats unavailable for {season}. Upload a genuine PlayerGameLogs CSV. '
f'Source error: {type(e).__name__}'
) from e
return normalize_logs(allrows)

def _adapt_community_rows(records):
"""Map a known community dataset to the NBA PlayerGameLogs interface.
Builds a surrogate key, NOT a real GAME_ID. Team pairs are sorted so rows
for the two opponents share the same matchup-day identifier. A rare
same-date doubleheader of the same matchup cannot be distinguished from
this CSV and would require a richer source.
"""
for line_number, row in enumerate(records, start=2):
team = str(row.get('Team') or '').strip().upper()
opponent = str(row.get('Opp') or '').strip().upper()
season = str(row.get('Season') or '').strip()
day = str(row.get('Date') or '').strip()
if not team or not opponent or team == opponent or not season:
raise ValueError(f'Row {line_number}: invalid team, opponent, or season.')
if not (team.isalnum() and opponent.isalnum() and len(team) <= 5 and len(opponent) <= 5):
raise ValueError(f'Row {line_number}: invalid team abbreviations.')
try:
date.fromisoformat(day)
except ValueError as e:
raise ValueError(f'Row {line_number}: invalid game date.') from e
matchup = '-'.join(sorted((team, opponent)))
yield {
'PLAYER_ID': row.get('ID'),
'PLAYER_NAME': row.get('Player'),
# Surrogate used only within this application for row uniqueness.
'GAME_ID': f'derived:{season}:{day}:{matchup}',
'GAME_DATE': day,
'MIN': row.get('Minutes'),
'PTS': row.get('Points'),
'REB': row.get('Rebounds'),
'AST': row.get('Assists'),
'MATCHUP': f'{team} vs {opponent}',
}

def parse_uploaded_csv(uploaded_file):
raw = uploaded_file.getvalue()
if len(raw) > 12_000_000:
raise ValueError('CSV exceeds 12MB limit.')
try:
content = raw.decode('utf-8-sig')
except UnicodeError as e:
raise ValueError('CSV must be UTF-8.') from e
records = csv.DictReader(io.StringIO(content))
fields = set(records.fieldnames or [])
if not fields:
raise ValueError('CSV has no column headers.')
if _FANDUEL_REQUIRED.issubset(fields):
return normalize_logs(_adapt_community_rows(records))
# Keep accepting official PlayerGameLogs CSV files unchanged.
if {'PLAYER_ID', 'PLAYER_NAME', 'GAME_ID', 'GAME_DATE', 'MIN', 'PTS', 'REB', 'AST'}.issubset(fields):
return normalize_logs(records)
if {'player_id', 'player_name', 'game_id', 'game_date', 'minutes', 'points', 'rebounds', 'assists'}.issubset(fields):
return normalize_logs(records)
raise ValueError(
'Unsupported CSV columns. Expected official NBA PlayerGameLogs or the '
'Date,Player,ID,Team,Opp,Season,Minutes,Points,Rebounds,Assists format.'
)
