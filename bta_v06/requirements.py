"""Forty-section BTA compliance crosswalk to *prepared* v0.4/v0.5/v0.6 code.

'Partial' and 'Manual' never mean the research can be performed autonomously.
These represent source-code review, not a deployed-app acceptance test.
"""
from __future__ import annotations

# section, concise name, current status, prepared implementation, blocker
REQUIREMENTS = [
 (1,'Analyst objective & expected value','Partial','Qualitative research screens and probability comparisons','No proven automated end-to-end selection research'),
 (2,'Official grade hierarchy','Partial','v0.4 labels and v0.5 no-auto-grade gate','Full source-driven grade assignment and independent audit'),
 (3,'Current verified data','Partial','NBA game logs; NFL weekly stats; v0.6 current live score monitors','Official rosters, live inactives, book quotes, consistent source matching'),
 (4,'Full statistical and situational audit','Partial','NBA box logs, NFL weekly volume, experimental Elo','Coaching, OL/DL, possessions, turnovers and strength-adjusted features'),
 (5,'Five script test','Manual','v0.4 prompt matrix and v0.5 validation gate','Real scenario opportunity modeling and quantified failure tests'),
 (6,'College football moneyline analysis','Partial','CFBD optional FBS results, experimental Elo','Verified QB, line-of-scrimmage, FBS filter, matchups and live moneylines'),
 (7,'NFL player prop evaluation','Partial','Weekly stats, snaps and role-trend screens','Routes, targets, lineup verification and per-market probabilities'),
 (8,'Ordinary failure audit','Manual','BTA stress notes, adverse/reverse questions','Automated grounded failure-path detection'),
 (9,'Odds and true probability separation','Partial','Odds math and calibration diagnostics','Real offered pregame lines/odds, adequately calibrated probabilities'),
 (10,'Parlay construction','Partial','Manual research slip, independent bounds and same-game warning','Validated dependencies, settlement, qualified-board link'),
 (11,'Live game analysis','Partial','v0.6 live NBA boxes plus NFL/CFB status','Full live player context, timestamps, availability, actionable line data'),
 (12,'Final report format','Partial','Research views and manual script audit','Automatic sourced audit and ranked true-qualified board'),
 (13,'Batch management','Pending','None persistent in prepared versions','Unique-slate ledger, resumption, dedupe and tally reconciliation'),
 (14,'General quality control','Partial','Fail-closed model sources and offline tests','Comprehensive independent source verification and held-out success'),
 (15,'Ten-question decision hierarchy','Manual','Research form and conservative gates','Automated reliable evidence and reasoned cross-sport conclusions'),
 (16,'Nonnegotiable behavior','Partial','Source-gated research labels, no automatic wagers','Broader provenance enforcement in all feature paths'),
 (17,'When a slate is submitted','Manual','Manual research selection interfaces','Bulk autonomous retrieval, grading and qualified-board construction'),
 (18,'Ultimate BTA philosophy','Manual','Loss-path emphasis and conservatism in screens','Tested operational consistency in automatic research'),
 (19,'Separate five-script families','Partial','Distinct NFL prop, CFB moneyline and NBA prop framework constants','Automated evidence-linked scenario assessment'),
 (20,'BETTER/SAME/MIXED/WORSE & 2-WORSE cut','Partial','v0.5 and v0.6 code enforces script count for props','Automatic causal verdict generation and review'),
 (21,'3-for-3 and 2-for-3 exception','Partial','Observed NBA/NFL samples and threshold comparisons','Verified injury/context for misses and role comparability'),
 (22,'Floor/cushion and explosive removal','Partial','Recent medians and clearance margins','True play-level long-gain removal and adverse projected floor'),
 (23,'Normal/contextual/structural misses','Manual','Audit checklist supports categorization','Verified event-level automatic miss attribution'),
 (24,'Opponent-adjusted history & reverse matchup','Partial','NBA scoring environment, NFL team-week allowed proxies','Quality-adjusted defensive features, scheme and role context'),
 (25,'Base/adverse/reverse analysis','Manual','Audit text fields','Automated empirical downside and reverse evidence'),
 (26,'15 supplemental adversity tests','Manual','v0.4 checkbox list','Automatically select applicable tests and assess scenarios'),
 (27,'Grade subtiers; no TAIG+','Partial','Documented approved grade vocabulary, no auto-awards','Complete ranked board, graded via actual evidence'),
 (28,'Polymarket YES/NO settlement','Pending','No exact live contract retrieval','Contract identifiers, resolution, price and void terms'),
 (29,'Advanced anytime-TD analysis','Pending','No verified inside-five / goal-line feeds','Play-by-play scoring opportunity model'),
 (30,'Quarter-specific prop analysis','Pending','No quarter-level model','Quarter play-by-play and exact contract meaning'),
 (31,'Nested alt lines and correlation','Partial','Same-event risk flag; independence bounds','Nested threshold detector, joint conditional probability model'),
 (32,'Qualified board vs final ticket','Partial','Research slip separate from strict board concept','Real source-gated approved-board workflow'),
 (33,'Provider / platform market restrictions','Pending','Manual market text only','FanDuel and Polymarket verified offerings and settlements'),
 (34,'Independent second-pass audit','Manual','Independent audit text field and v0.6 gate','Separate automated challenge with dated evidence'),
 (35,'Exact denominators','Partial','Recorded sample counts and last-ten hits','Every market threshold, eligibility and context matched'),
 (36,'CFB original order & FBS slate ledger','Pending','No reliable persistent review ledger','FBS-only verified queue, uniqueness and counts'),
 (37,'Prioritize decisive information & fail closed','Partial','v0.5/0.6 blockers and unverified statuses','Prove sources actually address each high-impact question'),
 (38,'Required report enhancements','Partial','Stats, scripts, failure and evidence screens','Sourced final audit, independently graded shortlist and ticket'),
 (39,'Hardest ordinary failure-path test','Manual','Explicit reverse argument requirement','Empirically tested, comparable scenario failure model'),
 (40,'Integrate both instruction sets','Partial','Rules crosswalk and manual gates in v0.4–v0.6','True end-to-end automation, external acceptance and validation'),
]
assert len(REQUIREMENTS) == 40
assert [row[0] for row in REQUIREMENTS] == list(range(1,41))
