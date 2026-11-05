"""BTA multi-sport research command center — an optional Streamlit page.

Install in `pages/01_BTA_Command_Center.py` beside your existing app.py.
This page does not place wagers, assign automatic BTA grades, or claim to
have live injury/lineup data. NBA probabilities are a historical baseline.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import streamlit as st

from nba_data import parse_uploaded_csv
from nba_model import MIN_HISTORY, WINDOW, METRICS, estimate, group_players


OWNER = "xtheredshirtx"
REPOSITORY = "fanduel-player-data"
SOURCE_DIRECTORY = "NBA/csv"
API_URL = (
    f"https://api.github.com/repos/{OWNER}/{REPOSITORY}/contents/{SOURCE_DIRECTORY}"
)
SEASONS = ("2025-26", "2026-27")
MAX_CSV_BYTES = 12_000_000
MAX_LOG_ROWS = 100_000

EVIDENCE_CHECKS = (
    "Matchup, date, venue, and expected starters verified",
    "Availability, injuries, restrictions, and inactives verified",
    "Role / minutes / snaps / routes / touches verified",
    "Teammate availability and changed usage verified",
    "Opposing defense, personnel, and comparable opponents checked",
    "Pace, coaching, rest, travel, and weather (if relevant) checked",
    "Historical floor, clearance cushion, 3-for-3 and last-10 reviewed",
    "Explosive-play dependence and ordinary failure paths reviewed",
    "Bookmaker line, price, and observation timestamp verified",
    "Same-game correlations and shared failure modes reviewed",
)

SCRIPTS = {
    "NBA": (
        "Our player's team wins in a blowout (reduced fourth-quarter minutes)",
        "Our player's team loses in a blowout",
        "Close, competitive game with normal rotation",
        "Slow pace / low-scoring defensive game",
        "Fast pace / high-scoring game",
    ),
    "NFL": (
        "Our player's team wins in a blowout",
        "Our player's team is trailing / opponent dominates",
        "Close, competitive game",
        "Low-scoring defensive game",
        "High-scoring shootout",
    ),
    "College football — moneyline": (
        "Expected, normal game script",
        "Underdog jumps out to an early lead",
        "Favorite commits two turnovers",
        "Favorite's main advantage gets neutralized",
        "One-possession game in the fourth quarter",
    ),
    "College football — player prop": (
        "Our player's team wins in a blowout",
        "Our player's team trails / opponent controls game",
        "Close, competitive game",
        "Low-scoring, slow-tempo game",
        "High-scoring, high-tempo game",
    ),
}

NFL_MARKETS = (
    "Passing yards", "Passing attempts", "Passing touchdowns",
    "Rushing yards", "Rushing attempts", "Receptions", "Targets",
    "Receiving yards", "Receiving touchdowns", "Anytime touchdown",
    "Sacks", "Moneyline", "Spread", "Total",
)
CFB_MARKETS = (
    "Moneyline", "Spread", "Total", "Passing yards", "Rushing yards",
    "Receiving yards", "Receptions", "Touchdowns",
)


def _get(url: str, *, limit: int) -> bytes:
    """Read only bounded HTTPS responses; no secrets or external user URLs."""
    req = Request(
        url,
        headers={
            "User-Agent": "BTA-Research-Engine/0.3 (public-game-logs)",
            "Accept": "application/vnd.github+json" if url.startswith("https://api.github.com/") else "text/csv",
        },
    )
    with urlopen(req, timeout=25) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Source file exceeds the supported download size.")
    return raw


def select_latest_snapshot(entries: list, season: str) -> tuple[str, str]:
    """Select latest dated CSV filename for one season from a GitHub directory.

    Selecting by a dated filename is intentional: a previously downloaded CSV
    never magically changes on a user's device. Future provider snapshots do.
    """
    if season not in SEASONS:
        raise ValueError("Unsupported NBA season.")
    pattern = re.compile(
        rf"^NBA_players_game_log_{re.escape(season)}_as_of_(\d{{4}}-\d{{2}}-\d{{2}})\.csv$"
    )
    options = []
    for item in entries:
        if not isinstance(item, dict) or item.get("type") != "file":
            continue
        filename = item.get("name", "")
        match = pattern.fullmatch(filename)
        if match:
            try:
                date.fromisoformat(match.group(1))
            except ValueError:
                continue
            options.append((match.group(1), filename))
    if not options:
        raise ValueError(f"No dated {season} game-log CSV found at the source.")
    snapshot, filename = max(options)
    return snapshot, filename


def fetch_nba_snapshots(seasons: tuple[str, ...]) -> tuple[list[dict], list[dict]]:
    """Find latest dated files in public GitHub, fetch and normalize their rows."""
    directory_bytes = _get(API_URL, limit=1_000_000)
    contents = json.loads(directory_bytes.decode("utf-8"))
    if not isinstance(contents, list):
        raise RuntimeError("GitHub returned an unexpected directory response (possibly rate-limited).")
    all_logs = []
    source_details = []
    for season in seasons:
        snapshot, filename = select_latest_snapshot(contents, season)
        raw_url = (
            f"https://raw.githubusercontent.com/{OWNER}/{REPOSITORY}/main/"
            f"{SOURCE_DIRECTORY}/{quote(filename)}"
        )
        raw = _get(raw_url, limit=MAX_CSV_BYTES)
        parsed = parse_uploaded_csv(io.BytesIO(raw))
        if not parsed:
            raise ValueError(f"The {season} snapshot contains no playable game logs.")
        all_logs.extend(parsed)
        source_details.append({
            "season": season,
            "snapshot": snapshot,
            "filename": filename,
            "rows": len(parsed),
            "latest_game": max(r["game_date"] for r in parsed).isoformat(),
            "source": raw_url,
        })
    if len(all_logs) > MAX_LOG_ROWS:
        raise ValueError("Combined dataset exceeds the supported row limit.")
    # Key by (player, source's per-game identifier); this also deduplicates
    # accidental repeated snapshots of exactly the same season/game.
    unique = {(r["player_id"], r["game_id"]): r for r in all_logs}
    combined = sorted(
        unique.values(),
        key=lambda r: (r["game_date"], r["game_id"], r["player_id"]),
    )
    return combined, source_details


def select_example_line(history: list[dict], stat: str) -> float | None:
    """Construct a research threshold using only data known before the game."""
    if len(history) < MIN_HISTORY:
        return None
    # Line is fixed BEFORE seeing the test game's box score; it is NOT a
    # historical sportsbook prop or a recommendation.
    initial = estimate(history, stat, 0.5)
    if initial.get("status") != "BASELINE ONLY":
        return None
    line = max(0.5, min(199.5, math.floor(initial["projection"]) + 0.5))
    return float(line)


def rolling_predictions(
    logs: list[dict], *, max_players: int = 100, seasons: tuple[str, ...] | None = None
) -> list[dict]:
    """Strictly chronological research-only backtest with prior-only baselines.

    For each prediction, earlier GAMES ONLY determine the sample line and both
    forecasts. No later box score or historic odds are read into the forecasts.
    The comparison is an equal-weight rolling hit-rate baseline, not a market.
    """
    if seasons is not None:
        # A season label is not retained by the normalized source, so this
        # option is intentionally unsupported instead of silently guessing.
        raise ValueError("A labeled season filter is not available for these normalized logs.")
    grouped, _names = group_players(logs)
    player_ids = sorted(
        grouped,
        key=lambda p: (
            grouped[p][-1]["game_date"] if grouped[p] else date.min,
            len(grouped[p]),
        ),
        reverse=True,
    )[:max_players]
    output = []
    for player_id in player_ids:
        rows = sorted(grouped[player_id], key=lambda r: (r["game_date"], r["game_id"]))
        if len(rows) < MIN_HISTORY + 1:
            continue
        for i in range(MIN_HISTORY, len(rows)):
            target = rows[i]
            # Explicit strict date comparison avoids simultaneous same-day data.
            prior = [r for r in rows[max(0, i - WINDOW - 5):i]
                     if r["game_date"] < target["game_date"]][-WINDOW:]
            if len(prior) < MIN_HISTORY:
                continue
            for display, stat in METRICS.items():
                example_line = select_example_line(prior, stat)
                if example_line is None:
                    continue
                forecast = estimate(prior, stat, example_line)
                if forecast.get("status") != "BASELINE ONLY":
                    continue
                # Same past sample and same line: simple rolling empirical rate.
                hits = sum(float(r[stat]) > example_line for r in prior)
                basic_p = (hits + 1.0) / (len(prior) + 2.0)
                model_p = forecast["p_over"] / (forecast["p_over"] + forecast["p_under"])
                outcome = int(float(target[stat]) > example_line)
                output.append({
                    "player_id": player_id,
                    "player": target["player_name"],
                    "date": target["game_date"].isoformat(),
                    "metric": display,
                    "example_line": example_line,
                    "model_probability": model_p,
                    "simple_probability": basic_p,
                    "outcome": outcome,
                    "model_brier": (model_p - outcome) ** 2,
                    "simple_brier": (basic_p - outcome) ** 2,
                    "neutral_brier": (0.5 - outcome) ** 2,
                })
    return output


def score_backtest(records: list[dict]) -> list[dict]:
    """Per-stat and overall Brier with calibration gap. No profitability claim."""
    if not records:
        return []
    results = []
    for label in ("Points", "Rebounds", "Assists", "All"):
        sample = [r for r in records if label == "All" or r["metric"] == label]
        if not sample:
            continue
        count = len(sample)
        results.append({
            "Stat": label,
            "Forecasts": count,
            "Model Brier": round(sum(r["model_brier"] for r in sample) / count, 4),
            "Simple Brier": round(sum(r["simple_brier"] for r in sample) / count, 4),
            "50% Brier": 0.25,
            "Mean predicted over %": round(100 * sum(r["model_probability"] for r in sample) / count, 1),
            "Observed over %": round(100 * sum(r["outcome"] for r in sample) / count, 1),
        })
    return results


def calibration_buckets(records: list[dict]) -> list[dict]:
    """Observed vs predicted by forecast probability bin; exploratory only."""
    bins = []
    for lo in (0, 20, 40, 60, 80):
        sample = [r for r in records if lo <= 100 * r["model_probability"] < lo + 20
                  or (lo == 80 and r["model_probability"] == 1.0)]
        if not sample:
            continue
        bins.append({
            "Probability bin": f"{lo}–{lo+20}%",
            "Forecasts": len(sample),
            "Predicted over %": round(100 * sum(r["model_probability"] for r in sample) / len(sample), 1),
            "Observed over %": round(100 * sum(r["outcome"] for r in sample) / len(sample), 1),
        })
    return bins


def stress_screen(evidence: dict[str, str], scripts: list[str]) -> tuple[str, str]:
    """Conservative *screen*, never an automated TAIG/BTA+/BTA grade."""
    if len(scripts) != 5:
        raise ValueError("Exactly five scenario judgments are required.")
    worse = sum(s == "Worse" for s in scripts)
    if worse >= 2:
        return "ELIMINATE", "Two or more adverse scenarios were marked Worse."
    if any(v == "Concern / blocker" for v in evidence.values()):
        return "BLOCKED / CONDITIONAL", "A material evidence concern needs resolution first."
    if any(v != "Verified" for v in evidence.values()) or any(s == "Not assessed" for s in scripts):
        return "INCOMPLETE", "Missing evidence or untested game scripts; no BTA grade can be assigned."
    if worse == 1:
        return "CONDITIONAL", "One normal failure scenario needs investigation; exclude from strict tickets."
    if "Mixed" in scripts:
        return "REVIEW REQUIRED", "Mixed scenarios remain; this is not an automatic strong grade."
    return "REVIEW REQUIRED", "Five scenarios survived, but validated probabilities, price, and source evidence still need expert review."


# -------- Streamlit UI (existing app.py is intentionally untouched) --------
st.set_page_config(page_title="BTA Command Center", page_icon="🏟️", layout="wide")
st.markdown("""
<style>
.block-container {max-width: 1100px; padding-top: 1.25rem; padding-bottom: 2rem;}
@media (max-width: 700px) {
 .block-container {padding-left: .8rem; padding-right: .8rem;}
 div[data-testid="stMetric"] {padding: .35rem 0;}
}
</style>
""", unsafe_allow_html=True)
st.title("BTA • Multi-Sport Command Center")
st.caption("NBA · NFL · College football | Research-only prototype | Not a live sportsbook")
st.info(
    "A historical hit rate is not a calibrated probability. No automatic TAIG, BTA+, "
    "or BTA grades until injury, role, opponent, game-script and market checks are verified."
)

nba_tab, nfl_tab, cfb_tab, stress_tab = st.tabs(
    ["🏀 NBA", "🏈 NFL", "🎓 College football", "🛡️ BTA stress desk"]
)

with nba_tab:
    st.subheader("Automatic NBA game-log research")
    st.caption(
        "Fetches the newest dated source CSV for each chosen season when this page opens "
        "or its cache expires. The source must publish a new snapshot first. "
        "This is not live injury, odds, or lineup monitoring."
    )
    seasons = st.multiselect("NBA seasons", SEASONS, default=list(SEASONS))
    if not seasons:
        st.warning("Select at least one NBA season.")
    else:
        @st.cache_data(ttl=3 * 60 * 60, show_spinner=False)
        def cached_nba(selected):
            return fetch_nba_snapshots(tuple(selected))

        if st.button("Check latest NBA source now", type="primary"):
            cached_nba.clear()
        source_logs = []
        source_details = []
        try:
            with st.spinner("Reading the NBA source snapshots..."):
                source_logs, source_details = cached_nba(tuple(seasons))
            st.success(f"Latest source files loaded: {len(source_logs):,} player-games.")
            st.dataframe(source_details, hide_index=True, use_container_width=True)
            st.caption("Community snapshots can combine regular-season and playoff games without a separate phase field. Source dates are not game dates.")
        except (ValueError, UnicodeError, URLError, HTTPError, RuntimeError, OSError, json.JSONDecodeError) as exc:
            st.warning(f"Automatic NBA update unavailable: {exc}")
            st.caption("The provider, server, or network may be unavailable; this is not a successful refresh.")
        except Exception as exc:
            st.warning(f"Automatic NBA update failed: {type(exc).__name__}.")
        if source_logs:
            st.session_state["bta_auto_nba_logs"] = source_logs
            st.session_state["bta_nba_source_details"] = source_details

    st.divider()
    st.subheader("Chronological NBA backtesting")
    st.caption(
        "For each later player-game, the model sees only earlier games and chooses "
        "an example line from those earlier games. We compare the model to an "
        "equal-weight historical hit-rate baseline and a 50% reference. "
        "These are NOT historical sportsbook lines or odds."
    )
    source_choice = st.radio(
        "Game logs to test",
        ["Automatic source", "Earlier uploaded NBA logs"], horizontal=True,
    )
    if source_choice == "Automatic source":
        test_logs = st.session_state.get("bta_auto_nba_logs", [])
    else:
        test_logs = st.session_state.get("nba_logs", [])
    if not test_logs:
        st.info("No logs in the selected source. Return to the NBA tab or upload logs in the existing app.")
    else:
        most_recent = max(row["game_date"] for row in test_logs)
        st.write(f"**{len(test_logs):,} player-games** available; latest game {most_recent.isoformat()}.")
        if (date.today() - most_recent).days > 7:
            st.warning("Game logs are stale for current markets. Historical backtests remain usable.")
        n_players = st.slider("Number of players to backtest", min_value=20, max_value=300, value=100, step=20)
        if st.button("Run no-lookahead historical test"):
            with st.spinner("Comparing model against prior-only baselines..."):
                records = rolling_predictions(test_logs, max_players=n_players)
            st.session_state["bta_eval_rows"] = records
            st.session_state["bta_eval_meta"] = (source_choice, len(test_logs), n_players)
        past = st.session_state.get("bta_eval_rows", [])
        meta = st.session_state.get("bta_eval_meta")
        if past:
            if meta != (source_choice, len(test_logs), n_players):
                st.warning("These results use prior settings. Run the test again for the current selection.")
            st.dataframe(score_backtest(past), hide_index=True, use_container_width=True)
            st.caption("Lower Brier score is better. Same player appears in many forecasts, so rows are NOT independent samples.")
            st.dataframe(calibration_buckets(past), hide_index=True, use_container_width=True)
            with st.expander("Inspect and export the individual predictions"):
                st.dataframe(past[:250], hide_index=True, use_container_width=True)
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=list(past[0]))
                writer.writeheader()
                writer.writerows(past)
                st.download_button(
                    "Download historical test details CSV", output.getvalue(),
                    "bta_nba_walk_forward_research.csv", "text/csv",
                )
        else:
            st.caption("No backtest run in this session yet.")

# --- Player-prop calculator: reuses the existing NBA baseline model ---
    st.divider()
    st.subheader("NBA player prop calculator")
    st.caption(
        "Choose a real game-log dataset, player, stat, and line. These are "
        "historical baseline estimates, not verified BTA grades or betting advice."
    )
    from nba_model import historical_brier, expected_roi

    calc_source = st.radio(
        "Calculator game logs",
        ["Automatic source", "Upload NBA CSV"],
        horizontal=True, key="bta_calc_source",
    )
    if calc_source == "Upload NBA CSV":
        calc_upload = st.file_uploader(
            "Upload genuine NBA PlayerGameLogs CSV",
            type=["csv"], key="bta_calc_upload",
        )
        if calc_upload is not None and st.button(
            "Import calculator CSV", key="bta_calc_import"
        ):
            try:
                parsed_logs = parse_uploaded_csv(calc_upload)
                if not parsed_logs:
                    raise ValueError("The file contains no recognized game logs.")
                st.session_state["bta_calc_uploaded_logs"] = parsed_logs
                st.success(f"Imported {len(parsed_logs):,} player-game records.")
            except (ValueError, UnicodeError, KeyError, TypeError) as exc:
                st.error(f"CSV could not be imported: {exc}")
        calc_logs = st.session_state.get("bta_calc_uploaded_logs", [])
    else:
        calc_logs = st.session_state.get("bta_auto_nba_logs", [])

    if not calc_logs:
        st.info("No calculator game logs loaded. Check the automatic NBA source above or import a CSV.")
    else:
        calc_grouped, calc_names = group_players(calc_logs)
        if not calc_grouped:
            st.warning("No recognizable players were found in this dataset.")
        else:
            newest_game = max(row["game_date"] for row in calc_logs)
            st.caption(
                f"{len(calc_logs):,} player-games loaded; newest recorded game: "
                f"{newest_game.isoformat()}."
            )
            if (date.today() - newest_game).days > 7:
                st.warning("The most recent game log is over seven days old. Do not treat this as current player information.")
            calc_ids = sorted(calc_grouped, key=lambda pid: calc_names[pid].casefold())
            calc_pid = st.selectbox(
                "NBA player", calc_ids,
                format_func=lambda pid: calc_names[pid],
                key="bta_calc_player",
            )
            calc_stat_name = st.selectbox(
                "Prop statistic", list(METRICS), key="bta_calc_stat",
            )
            calc_stat = METRICS[calc_stat_name]
            suggested_line = {"points": 20.5, "rebounds": 6.5, "assists": 4.5}.get(calc_stat, 20.5)
            calc_line = st.number_input(
                "Prop line", min_value=0.5, max_value=199.5,
                value=suggested_line, step=0.5,
                key="bta_calc_line",
            )
            calc_odds = st.number_input(
                "American odds (illustrative; verify your actual price)",
                min_value=-5000, max_value=5000, value=-110, step=5,
                key="bta_calc_odds",
            )
            if -100 < calc_odds < 100:
                st.error("American odds must be +100 or greater, or -100 or lower.")
            else:
                calc_result = estimate(calc_grouped[calc_pid], calc_stat, float(calc_line))
                if calc_result.get("status") != "BASELINE ONLY":
                    st.warning(
                        f"Not enough historical games: {calc_result.get('games', 0)} "
                        f"available; {calc_result.get('min_required', 'more')} required."
                    )
                else:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Historical projection", f"{calc_result['projection']:.1f}")
                    c2.metric(f"Over {calc_line:g}", f"{calc_result['p_over'] * 100:.1f}%")
                    c3.metric(f"Under {calc_line:g}", f"{calc_result['p_under'] * 100:.1f}%")
                    calc_side = st.radio(
                        "Evaluate side", ["Over", "Under"],
                        horizontal=True, key="bta_calc_side",
                    )
                    calc_p = calc_result["p_over"] if calc_side == "Over" else calc_result["p_under"]
                    calc_roi = expected_roi(calc_p, calc_result["p_push"], int(calc_odds))
                    st.write(
                        f"**Illustrative expected ROI at {calc_odds:+d}: {calc_roi * 100:+.1f}%** "
                        "— valid only if the unvalidated probability estimate is accurate."
                    )
                    st.caption(
                        f"Based on {calc_result['games']} games through "
                        f"{calc_result['last_game']}. Last-five average: "
                        f"{calc_result['recent_5_avg']:.1f}."
                    )
                    calc_check = historical_brier(
                        calc_grouped[calc_pid], calc_stat, float(calc_line)
                    )
                    if calc_check.get("count", 0):
                        st.caption(
                            f"Historical fixed-line test: {calc_check['count']} outcomes; "
                            f"Brier score {calc_check['brier']:.3f} (lower is better). "
                            "This does not use historical sportsbook prices."
                        )
                    st.warning(
                        "No injuries, lineups, minutes, opponent adjustments, or five-game-script "
                        "analysis are included. This is NOT a TAIG, BTA+, or BTA pick."
                    )
                    
with nfl_tab:
    st.subheader("NFL research engine")
    st.selectbox("NFL market families", NFL_MARKETS, key="bta_nfl_market")
    st.warning("NFL player statistics, snap counts, rosters, and injuries are not connected in this release.")
    st.write(
        "Planned: nflverse weekly player stats, PFR snap counts, role/route and "
        "offensive-line changes, opponent-adjusted defenses, injuries, and scenario risk. "
        "Player participation data may have a different refresh schedule than box scores."
    )
    st.markdown("Data source: [nflverse release schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html)")
    st.caption("Until inputs are verified, NFL analysis remains ungraded.")

with cfb_tab:
    st.subheader("College football research engine")
    st.selectbox("College football market families", CFB_MARKETS, key="bta_cfb_market")
    st.warning("College football team/player data and game-day injury checks are not connected in this release.")
    st.write(
        "The college model needs its own QB, offense/defense, turnover, "
        "opponent-strength, coaching, weather, and moneyline stress tests. "
        "It must not reuse NBA player-prop probability formulas."
    )
    st.markdown("Potential source: [CollegeFootballData API](https://api.collegefootballdata.com/) (key required).")
    st.caption("The key belongs in Streamlit secrets, never in a public GitHub repository.")

with stress_tab:
    st.subheader("Full BTA evidence + five-script review")
    st.caption(
        "This is a structured research checklist. You must actually verify the "
        "underlying evidence. Selecting 'Verified' does not automatically verify any source."
    )
    sport_key = st.selectbox("Sport and bet type", list(SCRIPTS), key="bta_stress_sport")
    st.text_input("Game / player / market", placeholder="Example: NFL · WR receiving yards · 45.5", key="bta_stress_target")
    evidence = {}
    with st.expander("Ten required evidence checks", expanded=True):
        for j, label in enumerate(EVIDENCE_CHECKS):
            evidence[label] = st.selectbox(
                label, ["Not reviewed", "Verified", "Concern / blocker"],
                key=f"evidence_{sport_key}_{j}",
            )
    st.markdown("**Five adverse game scripts**")
    script_decisions = []
    for j, label in enumerate(SCRIPTS[sport_key], 1):
        script_decisions.append(st.selectbox(
            f"{j}. {label}",
            ["Not assessed", "Better", "Same", "Mixed", "Worse"],
            key=f"scenario_{sport_key}_{j}",
        ))
    notes = st.text_area(
        "Dated sources, uncertainty, normal failure paths, and correlations",
        placeholder="Source URLs and dates; missing inputs; coach / injury / snap changes...",
        key="bta_evidence_notes",
    )
    screen, explanation = stress_screen(evidence, script_decisions)
    st.markdown(f"**Screen: {screen}**")
    st.write(explanation)
    if not notes.strip():
        st.caption("No source notes yet. Do not promote this screen to an approved pick.")
    st.caption(
        "TAIG is rare; BTA+/BTA require an independently supported matchup, role, "
        "injury, price, and calibration case. Conditional is excluded from strict "
        "tickets; Eliminate is rejected. No wager is placed."
    )
