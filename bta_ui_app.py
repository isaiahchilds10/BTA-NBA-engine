"""BTA — Belt to Ass branded Streamlit test entrypoint.

Runs the same existing pages and research engines, under one themed navigation.
Deploy as a SECOND Streamlit app on branch bta-v11-test; do not replace app.py.
"""
from __future__ import annotations

import streamlit as st

from bta_ui.theme import apply_theme


def make_navigation():
    """Existing page files are run in place; their research logic stays unchanged."""
    return st.navigation(
        {
            "BTA / BELT TO ASS": [
                st.Page("bta_ui/home.py", title="Command Center", icon=":material/home:", default=True),
                st.Page("bta_ui/pages/nba.py", title="NBA", icon=":material/sports_basketball:"),
                st.Page("bta_ui/pages/nfl.py", title="NFL", icon=":material/sports_football:"),
                st.Page("bta_ui/pages/college.py", title="College Football", icon=":material/school:"),
            ],
            "RESEARCH": [
                st.Page("pages/01_BTA_Command_Center.py", title="Research Command Center", icon=":material/monitoring:"),
                st.Page("pages/02_BTA_Evidence_and_Model_Lab.py", title="Evidence & Model Lab", icon=":material/science:"),
                st.Page("pages/03_BTA_Auto_Live_Monitor.py", title="Auto Live Monitor", icon=":material/radar:"),
                st.Page("pages/04_BTA_40_Point_Audit.py", title="40-Point Audit", icon=":material/fact_check:"),
                st.Page("pages/05_BTA_Advanced_Research.py", title="Advanced Research", icon=":material/query_stats:"),
                st.Page("pages/06_BTA_Automatic_Slate.py", title="Automatic Slate", icon=":material/calendar_month:"),
                st.Page("pages/07_BTA_Autonomous_Research.py", title="Autonomous Research", icon=":material/psychology:"),
                st.Page("pages/08_BTA_Risk_and_Integrity.py", title="Risk & Integrity", icon=":material/shield:"),
                st.Page("pages/09_BTA_Certification_Lab.py", title="BTA+ Certification Lab", icon=":material/verified_user:"),
            ],
        },
        position="sidebar",
        expanded=True,
    )


# No set_page_config here: the existing research pages already set their own
# configuration; avoiding a second call preserves compatibility across versions.
page = make_navigation()
apply_theme()  # Theme from the start of the run.
page.run()
apply_theme()  # Reapply after older page-specific CSS, so shared branding wins.
