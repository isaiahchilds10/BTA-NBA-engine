# BTA NBA Probability Engine v0.2 — free research prototype

**What is new:** An independently calculating NBA points/rebounds/assists historical-probability baseline, a no-lookahead fixed-line historical check, bulk **unpriced** player scouting, and an optional event-level bookmaker prop lookup. This extends v0.1's manual research/paper bankroll/ledger. No real-money wagers.

## Critical distinction

The engine calculates over/under probabilities without anyone manually typing in percentages. **That is not the same as a trustworthy BTA+ prediction.** Today it uses recent game-level box scores with time-decaying weights and modest smoothing. It does **not** yet check injuries, minutes restrictions, likely starters, opponent matchup strength, rest, rotation shifts, or your full five-script BTA procedure. It cannot automatically label anything TAIG or BTA+. A theoretical ROI based on an unvalidated probability estimate is **not evidence of an edge**. Don't use the output to risk money.

This is an **implementation**, not a validated sports-betting model. We have no verified out-of-sample NBA performance results. The tests use **synthetic** data solely to check code behavior.

## Run locally (free)

You need Python 3.10+.

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

`http://localhost:8501` opens the dashboard. This is a complete v0.2 replacement for the v0.1 starter; it includes all existing files plus `nba_model.py`, `nba_data.py`, and `nba_prop_odds.py`.

### Deploy to your iPhone via a browser (free tier)

1. Create a GitHub repo and upload the **contents of this folder** at the repository root (`app.py`, `nba_model.py`, etc.; not the ZIP file itself).
2. At [Streamlit Community Cloud](https://share.streamlit.io/) create an app from the repository and set the main file to `app.py`. Hosting availability, repository privacy, uptime, and resource limits may change; refer to Streamlit's current terms. Do not upload credentials or sensitive data to public GitHub.
3. Open the deployed link on your phone. Select the **NBA probability engine** tab.
4. Click **Fetch 2025–26 + 2026–27 NBA logs**. It queries NBA.com via `nba_api`. If the NBA blocks your hosting environment or times out, upload a **genuine** NBA PlayerGameLogs CSV instead. No fake stats are substituted.
5. With valid logs loaded, see automatically calculated illustrative points/rebounds/assists baselines and choose an actual player/prop line for an estimated probability plus chronological backtest.
6. **Optional**: supply a key from [The Odds API](https://the-odds-api.com/) (**with hyphens**) and click the explicit buttons to list upcoming NBA games and request one game's player props. It automatically joins available prop odds to independently estimated probabilities by player names. If no match or insufficient history, that prop is skipped. Every API call can spend credits.

CSV import must contain at least these columns with real values: `PLAYER_ID`, `PLAYER_NAME`, `GAME_ID`, `GAME_DATE`, `MIN`, `PTS`, `REB`, `AST`. These are part of the NBA `PlayerGameLogs` dataset. Use regular-season rows. A current and previous season will give more sample history; game dates are required for chronological testing. CSV must be UTF-8 and <=12 MB. The engine does not generate any example player records for production use.

### Obtain genuine CSV if needed

`nba_api` exposes NBA.com `PlayerGameLogs`; details and documented fields: https://github.com/swar/nba_api/blob/master/docs/nba_api/stats/endpoints/playergamelogs.md

If you have Python running on a network that can reach NBA.com:

```python
from nba_api.stats.endpoints import playergamelogs
import pandas as pd
all_games = []
for season in ['2025-26', '2026-27']:
    frame = playergamelogs.PlayerGameLogs(
        season_nullable=season, season_type_nullable='Regular Season', timeout=20
    ).get_data_frames()[0]
    all_games.append(frame)
pd.concat(all_games, ignore_index=True).to_csv('nba_player_logs.csv', index=False)
```

NBA.com is not a guaranteed-access or uptime-backed data feed. If it fails, do **not** fabricate or silently assume recent statistics.

## How the baseline works

For each player and statistic:

- Exclude DNPs and require at least **12 recorded games** (a development threshold, not proof of sufficiency).
- Use the most recent **30** games, weighting recent games more heavily (a nine-game weight half-life).
- Produce a weighted projection and smoothed frequency estimates of `P(over)`, `P(under)`, and `P(push)` for a supplied line. Odds are not used to generate the estimate.
- The fixed-line chronological test predicts each later game using only previous games and reports a Brier score. It does **not** know historical market lines, so its performance must **not** be interpreted as a sports-betting ROI or actual odds-based profitability.
- Auto-scouting chooses **fictional example thresholds**, not sportsbook lines. It assigns no BTA grade and never outputs an official pick.
- Optional live prop odds come from The Odds API event-odds endpoint, which returns bookmaker-specific lines and prices. Results are labeled **unvalidated**. Current quotes are not a substitute for historical closing odds or verified market snapshots.

Current Odds API docs: https://the-odds-api.com/sports/nba-odds.html and https://the-odds-api.com/liveapi/guides/v4/. Free account quotas can be exhausted quickly. Avoid repeat clicking or trying to scan every game on the free quota. Historical prop odds generally need a paid feed.

**Do not conflate these providers:** `the-odds-api.com` (hyphens) and `theoddsapi.com` (no hyphens) are different services and have different pricing/API contracts. This project uses the former.

## Risk/safety boundaries

- Simulation and research only. Does not place real bets. Real sportsbook rules may prohibit automated wagers.
- Do not automatically create parlays yet. Combining bets requires **joint** probabilities and correlation analysis; multiplying marginal probabilities requires independence and is often invalid.
- No guarantee of gains. Small samples and changing player roles can make historical probabilities inaccurate; displayed theoretical ROI can be misleading.
- Session data may disappear when Streamlit restarts. Download research and paper ledger CSVs for backup. No secrets in the repository; paste API keys into the app's password input.
- Only trust verified current records. The developer environment could not connect to NBA.com, so live ingestion and end-to-end hosted deployment have not been verified here.

## Tests

```bash
python -m pytest -q
```

If `pytest` is not installed, `python -m pip install pytest`. Tests include previous v0.1 checks plus NBA calculation, backtest no-lookahead, DNP handling, value calculation, and importer validation. **Synthetic fixtures are test-only**.

## Next real milestone (v0.3)

Independent injury/rotation reports, opponent/pace/role adjustments, a strict five-game-script review, player prop time-stamped odds history, and genuine held-out calibration checks. Only after those are validated should we discuss parlay assembly or BTA-classified opportunities.
