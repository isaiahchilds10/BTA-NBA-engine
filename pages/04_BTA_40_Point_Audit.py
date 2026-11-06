"""Version-controlled coverage report; no claims that manual BTA checks were automated."""
import streamlit as st
from bta_v06.requirements import REQUIREMENTS
st.set_page_config(page_title='BTA | 40-Point Audit',page_icon='🧪',layout='wide')
st.markdown('<style>.stApp{background:#0d121c;color:#e8eef8}</style>',unsafe_allow_html=True)
st.title('BTA • 40-Point Requirements Audit')
st.caption('Audit of prepared v0.4, v0.5 and v0.6 code. Verify live deployment independently.')
st.warning('A manual questionnaire, an API connection, or an Elo model is not equivalent to full automatic BTA research.')
counts={k:sum(row[2]==k for row in REQUIREMENTS) for k in ('Partial','Manual','Pending')}
a,b,c=st.columns(3)
a.metric('Partially coded',counts['Partial'])
b.metric('Manual-only',counts['Manual'])
c.metric('Not implemented',counts['Pending'])
choice=st.radio('Show', ['All','Partial','Manual','Pending'],horizontal=True)
shown=REQUIREMENTS if choice=='All' else [r for r in REQUIREMENTS if r[2]==choice]
for index,name,status,covered,missing in shown:
    with st.expander(f'{index:02d} · {name} — {status}'):
        st.write('**Prepared:** '+covered)
        st.write('**Still needed:** '+missing)
st.caption('Status counts refer to implementation readiness, not proved predictive performance or live-source uptime.')
