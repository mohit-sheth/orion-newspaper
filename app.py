import logging
import sys

import streamlit as st

# Configure structured logging to stdout
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(
    logging.Formatter('{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}')
)
_root_logger = logging.getLogger("orion_newspaper")
if not _root_logger.handlers:
    _root_logger.addHandler(_handler)
    _root_logger.setLevel(logging.INFO)

st.set_page_config(
    page_title="Orion Newspaper",
    page_icon=":material/newspaper:",
    layout="wide",
    initial_sidebar_state="expanded",
)

pg = st.navigation(
    [
        st.Page("pages/newspaper.py", title="Newspaper", icon=":material/newspaper:", default=True),
        st.Page("pages/executive_summary.py", title="Executive Summary", icon=":material/summarize:"),
        st.Page("pages/trends.py", title="Trends", icon=":material/trending_up:"),
        st.Page("pages/metrics.py", title="Metric Correlation", icon=":material/analytics:"),
        st.Page("pages/manual.py", title="Manual Execute", icon=":material/play_circle:"),
        st.Page("pages/about.py", title="About", icon=":material/info:"),
    ]
)
pg.run()
