"""Home dashboard. Navigation only; never invent model accuracy or certified picks."""
from __future__ import annotations
import streamlit as st
from bta_ui.theme import apply_theme, brand_header, section

st.set_page_config(page_title="BTA | Belt to Ass", page_icon="🥊", layout="wide", initial_sidebar_state="expanded")
apply_theme()
brand_header(
    title="Command Center",
    kicker="Sports intelligence • NBA / NFL / College Football",
    description="Research, model evidence, risk checks and BTA+ certification — organized in one workspace.",
)
st.markdown(
    '<span class="bta-chip">7 engine generations · v0.5–v1.1</span>'
    '<span class="bta-chip">3 sports</span>'
    '<span class="bta-chip">BTA+ gate code installed · real verification pending</span>',
    unsafe_allow_html=True,
)

section("CHOOSE YOUR SPORT")
for col, title, subtitle, target in zip(
    st.columns(3),
    ("NBA", "NFL", "COLLEGE FOOTBALL"),
    ("Pro basketball", "Pro football", "FBS football"),
    ("bta_ui/pages/nba.py", "bta_ui/pages/nfl.py", "bta_ui/pages/college.py"),
):
    with col:
        with st.container(border=True):
            st.markdown(f"### {title}")
            st.caption(subtitle)
            st.page_link(target, label=f"Explore {title}", icon=":material/arrow_forward:", use_container_width=True)

section("RESEARCH & VERIFICATION")
left, center, right = st.columns(3)
with left:
    with st.container(border=True):
        st.markdown("#### Game intelligence")
        st.caption("Review today's slates, player evidence, and advanced research tools.")
        st.page_link("pages/07_BTA_Autonomous_Research.py", label="Open research", icon=":material/search:", use_container_width=True)
with center:
    with st.container(border=True):
        st.markdown("#### BTA+ certification")
        st.caption("Inspect lineup, usage, calibration, settlement and parlay evidence blockers.")
        st.page_link("pages/09_BTA_Certification_Lab.py", label="Open certification", icon=":material/verified_user:", use_container_width=True)
with right:
    with st.container(border=True):
        st.markdown("#### Risk & integrity")
        st.caption("Review the failure paths, uncertainty, and restrictions behind a potential play.")
        st.page_link("pages/08_BTA_Risk_and_Integrity.py", label="Open risk analysis", icon=":material/shield:", use_container_width=True)

section("ENGINE STATUS")
a,b,c=st.columns(3)
a.metric("Implemented analysis versions","7",help="Modules v0.5 through v1.1 are present in this test branch. Not all are live-certified.")
b.metric("Sport hubs","3",help="NBA, NFL and college football")
c.metric("BTA+ certification", "PENDING",help="Real provider coverage and prospective model validation must be completed before any real BTA+ certification.")
st.warning("BTA+ is not currently live-certified. Missing lineup, route, roster, bookmaker settlement and future-model validation evidence must not be replaced by fictional stats.")
st.caption("BTA means BELT TO ASS. This app is a research environment; it does not place wagers.")
