"""Shared BTA (Belt to Ass) visual theme. No research calculations or API access."""
from __future__ import annotations
from html import escape
from pathlib import Path
import streamlit as st

LOGO_PATH = Path(__file__).parent / "assets" / "leather_belt.svg"

THEME_CSS = r"""
<style>
/* BTA — Belt to Ass. Full responsive UI for both classic pages and new pages. */
:root {
  --bta-black: #08090d;
  --bta-panel: #14171d;
  --bta-panel-2: #1b1f27;
  --bta-red: #e22332;
  --bta-red-hover: #ff4050;
  --bta-white: #f6f7f9;
  --bta-muted: #aab1bf;
  --bta-edge: rgba(255,255,255,.115);
}
html, body, [data-testid="stApp"], .stApp,
[data-testid="stAppViewContainer"], [data-testid="stMain"] {
  color: var(--bta-white) !important;
  background: radial-gradient(ellipse 60% 34% at 80% -10%, rgba(210,23,42,.17), transparent 80%),
              linear-gradient(180deg, #11141b 0%, #08090d 60%, #0b0d12 100%) !important;
}
[data-testid="stHeader"] { background: rgba(8,9,13,.92) !important; }
[data-testid="stDecoration"] { background: linear-gradient(90deg,#c40d23,#f03945,#671018) !important; }
[data-testid="stSidebar"] {
  background: linear-gradient(178deg,#191c23 0%,#0f1116 45%,#090a0d 100%) !important;
  border-right: 1px solid rgba(226,35,50,.27) !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarNav"]::before {
  content: "BTA  /  BELT TO ASS";
  display: block;
  color: #fff;
  font-size: .92rem;
  font-weight: 900;
  letter-spacing: .17em;
  padding: .9rem 1rem;
  margin: .3rem .5rem .9rem;
  border-bottom: 2px solid #e22332;
}
[data-testid="stSidebarNav"] a {border-radius: 10px !important; color:#d8dce5 !important;}
[data-testid="stSidebarNav"] a[aria-current="page"],
[data-testid="stSidebarNav"] a[aria-selected="true"] {
  background: linear-gradient(90deg,rgba(226,35,50,.27),rgba(226,35,50,.04)) !important;
  color:#fff !important;
  border-left:3px solid #ee3040 !important;
}
[data-testid="stSidebarNav"] a:hover {background:rgba(226,35,50,.13) !important;}
[data-testid="stSidebarNav"] span {font-size:.92rem;}
.block-container {max-width: 1560px; padding-top: 1.5rem; padding-bottom: 4.5rem;}
h1, h2, h3, h4, h5, h6 { color: #f7f7fa !important; letter-spacing:-.025em; }
h1 {font-weight:850 !important;}
p, li { color: #dde1ea; }
small, .stCaption, [data-testid="stCaptionContainer"] {color:var(--bta-muted) !important;}
[data-testid="stMetric"], div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]),
[data-testid="stForm"], [data-testid="stExpander"],
[data-testid="stDataFrame"], div[data-testid="stTable"] {
  background: linear-gradient(155deg,rgba(31,35,44,.94),rgba(16,19,25,.96)) !important;
  border:1px solid var(--bta-edge) !important;
  border-radius: 16px !important;
  box-shadow: 0 10px 28px rgba(0,0,0,.12);
}
[data-testid="stMetric"] {padding: 1rem 1.15rem !important;}
[data-testid="stMetricLabel"] {color:var(--bta-muted) !important;}
[data-testid="stMetricValue"] {color:#fff !important; font-weight:800 !important;}
[data-testid="stTabs"] [role="tablist"] { gap: .3rem; border-bottom:1px solid #343841; }
[data-testid="stTabs"] [role="tab"] {border-radius:9px 9px 0 0; color:#c7cbd3;}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {color:#fff !important; background:rgba(226,35,50,.12) !important;}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {background-color:#e22332 !important;}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
  background: linear-gradient(135deg,#c71528,#f12d3c) !important;
  border:1px solid #ee4350 !important;
  color:#fff !important;
  font-weight:700 !important;
  border-radius:11px !important;
  box-shadow:0 8px 20px rgba(182,12,37,.18);
}
.stButton > button, .stDownloadButton > button {
  border-radius: 11px !important;
  transition: background .15s ease, border-color .15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {border-color:#f2404e !important;}
[data-testid="stWidgetLabel"] p {font-weight:650; color:#e8eaf0 !important;}
[data-baseweb="input"] > div, [data-baseweb="select"] > div,
[data-baseweb="textarea"] > div {border-radius:11px !important; background:#1b1f26 !important; border-color:#454952 !important;}
[data-testid="stAlert"] {border-radius:12px !important;}
[data-testid="stMarkdownContainer"] a {color:#ff6a73;}
[data-testid="stMarkdownContainer"] a:hover {color:#ff8c94;}
hr {border-color:#3a3e47 !important;}
.bta-header {padding:1.05rem 1.2rem; border:1px solid rgba(255,255,255,.11); border-radius:18px;
  background:linear-gradient(115deg,#181b21,#111318 65%,#221015); margin-bottom:1rem;}
.bta-eyebrow {color:#ff6674;font-size:.72rem;font-weight:850;letter-spacing:.22em;text-transform:uppercase;margin:0 0 .4rem;}
.bta-title {font-size:clamp(2rem,4.3vw,3.65rem);font-weight:900;letter-spacing:-.045em;line-height:1.05;color:white;}
.bta-subtitle {color:#b7bfcc;margin:.55rem 0 .1rem;font-size:.98rem;}
.bta-brand {display:flex;gap:1rem;align-items:center;margin-bottom:.9rem;}
.bta-brand svg {width:min(205px,40vw);height:auto;flex-shrink:0;}
.bta-brand-title {font-size:clamp(1.55rem,3.4vw,2.6rem);font-weight:950;color:white;letter-spacing:.045em;font-style:italic;line-height:1;}
.bta-brand-tag {color:#cbd1d9;letter-spacing:.12em;font-size:.76rem;font-weight:750;margin-top:.24rem;}
.bta-rule {height:3px;border:0;background:linear-gradient(90deg,#e22332,#680d17,transparent);margin:0 0 1rem;}
.bta-chip {display:inline-block;background:rgba(226,35,50,.1);border:1px solid rgba(242,55,75,.35);
  border-radius:999px;color:#ffc3c8;font-size:.72rem;padding:.28rem .65rem;font-weight:750;margin:.22rem .27rem .15rem 0;}
.bta-small {color:#aeb6c3;font-size:.86rem;line-height:1.5;}
.bta-section {font-size:1.04rem;letter-spacing:.045em;font-weight:850;color:white;margin:1.3rem 0 .6rem;}
.bta-divider {border:0;border-top:1px solid #343843;margin:1.15rem 0;}
@media (max-width:760px){
  .block-container {padding: .7rem .75rem 5rem !important;}
  [data-testid="stSidebar"] {min-width:250px !important;}
  .bta-header {padding:.9rem; border-radius:13px;}
  .bta-title {font-size:2rem;}
  .bta-brand {gap:.6rem;}
  .bta-brand svg {max-width:115px;}
  .bta-brand-title {font-size:1.75rem;}
  .bta-brand-tag {font-size:.61rem;letter-spacing:.07em;}
  [data-testid="stHorizontalBlock"] {gap:.55rem !important;}
}
</style>
"""


def apply_theme() -> None:
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def brand_header(*, title: str, kicker: str, description: str) -> None:
    logo = LOGO_PATH.read_text(encoding="utf-8")
    st.markdown(
        '<div class="bta-header">'
        f'<div class="bta-brand">{logo}'
        '<div><div class="bta-brand-title">BTA</div>'
        '<div class="bta-brand-tag">BELT TO ASS</div></div></div>'
        '<div class="bta-rule"></div>'
        f'<div class="bta-eyebrow">{escape(kicker)}</div>'
        f'<div class="bta-title">{escape(title)}</div>'
        f'<div class="bta-subtitle">{escape(description)}</div></div>',
        unsafe_allow_html=True,
    )


def section(label: str) -> None:
    st.markdown(f'<div class="bta-section">{escape(label)}</div>',unsafe_allow_html=True)
