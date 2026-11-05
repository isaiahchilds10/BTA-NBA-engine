"""NBA game-log ingestion for the BTA NBA Engine.

Accepts official NBA PlayerGameLogs CSV exports and the community game-log
CSV from xtheredshirtx/fanduel-player-data (2026-11-03 snapshot).

The community file does not provide an official NBA GAME_ID. A deterministic
matchup/date key is derived ONLY for identifying and deduplicating rows within
this application. It is not an official NBA identifier. The community data
may contain postseason games; game phase cannot be verified from this file.
"""

import csv
import io
from datetime import date

from nba_model import normalize_logs


_FANDUEL_REQUIRED = {
    "Date", "Player", "ID", "Team", "Opp", "Season",
    "Minutes", "Points", "Rebounds", "Assists",
}

_OFFICIAL_REQUIRED = {
    "PLAYER_ID", "PLAYER_NAME", "GAME_ID", "GAME_DATE",
    "MIN", "PTS", "REB", "AST",
}

_NORMALIZED_REQUIRED = {
    "player_id", "player_name", "game_id", "game_date",
    "minutes", "points", "rebounds", "assists",
}


def fetch_nba_logs(seasons=("2025-26", "2026-27")):
    """Fetch official logs using nba_api, with clear errors on failure."""
    try:
        from nba_api.stats.endpoints import playergamelogs
    except ImportError as exc:
        raise RuntimeError(
            "Install nba_api using requirements.txt or upload a game-log CSV."
        ) from exc

    allrows = []
    for season in seasons:
        try:
            response = playergamelogs.PlayerGameLogs(
                season_nullable=season,
                season_type_nullable="Regular Season",
                timeout=20,
            )
            dataframes = response.get_data_frames()
            if not dataframes or dataframes[0].empty:
                raise RuntimeError("empty response")
            allrows.extend(dataframes[0].to_dict(orient="records"))
        except Exception as exc:
            raise RuntimeError(
                f"NBA stats unavailable for {season}. Upload a genuine "
                f"PlayerGameLogs CSV. Source error: {type(exc).__name__}"
            ) from exc

    return normalize_logs(allrows)


def _adapt_community_rows(records):
    """Convert community player logs to the model's expected column names.

    The internal surrogate key is shared across a matchup on a given date.
    Same-date rematches cannot be distinguished from the source columns alone.
    """
    for line_number, row in enumerate(records, start=2):
        team = str(row.get("Team") or "").strip().upper()
        opponent = str(row.get("Opp") or "").strip().upper()
        season = str(row.get("Season") or "").strip()
        day = str(row.get("Date") or "").strip()

        if not team or not opponent or team == opponent or not season:
            raise ValueError(
                f"Row {line_number}: invalid team, opponent, or season."
            )
        if not (
            team.isalnum()
            and opponent.isalnum()
            and len(team) <= 5
            and len(opponent) <= 5
        ):
            raise ValueError(f"Row {line_number}: invalid team abbreviations.")
        try:
            date.fromisoformat(day)
        except ValueError as exc:
            raise ValueError(f"Row {line_number}: invalid game date.") from exc

        matchup = "-".join(sorted((team, opponent)))
        yield {
            "PLAYER_ID": row.get("ID"),
            "PLAYER_NAME": row.get("Player"),
            # Local, derived key, not an official NBA GAME_ID.
            "GAME_ID": f"derived:{season}:{day}:{matchup}",
            "GAME_DATE": day,
            "MIN": row.get("Minutes"),
            "PTS": row.get("Points"),
            "REB": row.get("Rebounds"),
            "AST": row.get("Assists"),
            "MATCHUP": f"{team} vs {opponent}",
        }


def parse_uploaded_csv(uploaded_file):
    """Parse either official or supported community NBA player-game logs."""
    raw = uploaded_file.getvalue()
    if len(raw) > 12_000_000:
        raise ValueError("CSV exceeds 12MB limit.")

    try:
        content = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("CSV must be UTF-8.") from exc

    records = csv.DictReader(io.StringIO(content))
    fields = set(records.fieldnames or [])
    if not fields:
        raise ValueError("CSV has no column headers.")

    if _FANDUEL_REQUIRED.issubset(fields):
        return normalize_logs(_adapt_community_rows(records))
    if _OFFICIAL_REQUIRED.issubset(fields):
        return normalize_logs(records)
    if _NORMALIZED_REQUIRED.issubset(fields):
        return normalize_logs(records)

    raise ValueError(
        "Unsupported CSV columns. Expected official NBA PlayerGameLogs or "
        "Date,Player,ID,Team,Opp,Season,Minutes,Points,Rebounds,Assists format."
    )
