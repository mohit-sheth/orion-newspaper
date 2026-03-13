import os
from html import escape as _esc

import streamlit as st
import streamlit.components.v1 as components

from orion_runner import parse_csv_data, find_viz_html, extract_regressions

APP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

.stMarkdown, .stText, p, span:not([data-testid="stIconMaterial"]), label, h1, h2, h3, h4, h5, h6,
div, button, input, select, textarea, .stSelectbox, .stTextInput, .stButton {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
code, pre, .stCode, .stCodeBlock { font-family: 'JetBrains Mono', 'SFMono-Regular', 'Fira Code', 'Consolas', monospace; }

/* Use full width of main area */
.stMainBlockContainer { max-width: 100%; padding-left: 2rem; padding-right: 2rem; }

section[data-testid="stSidebar"] { background-color: #141420; border-right: 1px solid #2a2a3a; }
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stTextInput label,
section[data-testid="stSidebar"] .stCheckbox label {
    color: #b0b0c0; font-weight: 500; font-size: 0.85rem; letter-spacing: 0.01em;
}

/* Modern dropdowns */
div[data-baseweb="select"] > div {
    background-color: #1a1a28;
    border: 1px solid #2a2a3a;
    border-radius: 8px;
    cursor: pointer;
}
div[data-baseweb="select"] > div:focus-within {
    border-color: #6C63FF;
    box-shadow: 0 0 0 1px #6C63FF;
}
div[data-baseweb="popover"] ul {
    background-color: #1a1a28;
    border: 1px solid #2a2a3a;
    border-radius: 8px;
    padding: 4px;
    max-height: 300px;
}
div[data-baseweb="popover"] li {
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 0.85rem;
}
div[data-baseweb="popover"] li:hover {
    background-color: #2a2a3a;
}
div[data-baseweb="popover"] li[aria-selected="true"] {
    background-color: #6C63FF22;
    color: #a9a4ff;
}

.newspaper-header {
    padding: 1.2rem 0 0.8rem 0;
    border-bottom: 1px solid #2a2a3a;
    margin-bottom: 1.8rem;
}
.newspaper-header h1 {
    color: #f0f0f5;
    font-size: 1.6rem;
    font-weight: 700;
    margin: 0;
    letter-spacing: -0.02em;
}
.newspaper-header p {
    color: #6c6c80;
    font-size: 0.85rem;
    font-weight: 400;
    margin: 0.3rem 0 0 0;
    letter-spacing: 0.01em;
}

.status-badge {
    padding: 0.6rem 1.4rem;
    border-radius: 8px;
    font-weight: 600;
    display: inline-block;
    margin-bottom: 1rem;
    font-size: 0.9rem;
    border: 1px solid;
}
.status-success { background: linear-gradient(135deg, #0d2818, #132e1c); color: #4ade80; border-color: #1a4028; }
.status-regression { background: linear-gradient(135deg, #2a1a00, #332200); color: #fbbf24; border-color: #4a3000; }
.status-error { background: linear-gradient(135deg, #2a0a0a, #331010); color: #f87171; border-color: #4a1a1a; }

.config-preview {
    background-color: #16161f;
    border: 1px solid #2a2a3a;
    border-radius: 10px;
    padding: 0.8rem 1rem;
    margin-top: 0.6rem;
    font-size: 0.82rem;
}
.config-preview .label {
    color: #6c6c80;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.15rem;
}
.config-preview .value { color: #c0c0d0; margin-bottom: 0.4rem; }

.regression-card {
    background-color: #16161f;
    border-left: 3px solid #fbbf24;
    border-radius: 8px;
    padding: 0.7rem 1.2rem;
    margin-bottom: 0.6rem;
    display: flex;
    align-items: center;
    gap: 0.8rem;
}
.regression-card .ver {
    color: #e0e0ed;
    font-family: 'JetBrains Mono', 'SFMono-Regular', 'Consolas', monospace;
    font-size: 0.82rem;
    font-weight: 500;
}
.regression-card .arrow { color: #fbbf24; font-size: 1.2rem; }
.regression-card .label-text {
    color: #6c6c80;
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.summary-row { display: flex; gap: 1rem; margin-bottom: 1.4rem; flex-wrap: wrap; }
.summary-card {
    background-color: #16161f;
    border: 1px solid #2a2a3a;
    border-radius: 10px;
    padding: 1rem 1.4rem;
    min-width: 130px;
    flex: 1;
}
.summary-card .num {
    color: #f0f0f5;
    font-size: 1.6rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    line-height: 1.2;
}
.summary-card .lbl {
    color: #6c6c80;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 0.2rem;
}

@keyframes shimmer {
    0% { border-color: #2a2a3a; }
    50% { border-color: #6C63FF; }
    100% { border-color: #2a2a3a; }
}
.welcome-card {
    background: linear-gradient(160deg, #13131d, #1a1a2e 40%, #16162a);
    border: 1px solid #2a2a3a;
    border-top: 2px solid #6C63FF40;
    border-radius: 14px;
    padding: 2.5rem 3rem;
    text-align: left;
    margin: 2rem 0;
    animation: shimmer 4s ease-in-out infinite;
}

.welcome-card .badge {
    display: inline-block;
    background-color: #6C63FF18;
    color: #8b83ff;
    border: 1px solid #6C63FF30;
    border-radius: 20px;
    padding: 0.25rem 0.75rem;
    font-size: 0.78rem;
    font-weight: 500;
    margin: 0.2rem 0.3rem 0.2rem 0;
}

.welcome-card .divider {
    border: none;
    border-top: 1px solid #2a2a3a;
    margin: 1rem 0;
}

@keyframes pulse-dot {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}
.es-connected {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.78rem;
    color: #6c6c80;
    margin-top: 0.3rem;
}
.es-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background-color: #4ade80;
    display: inline-block;
    animation: pulse-dot 2s ease-in-out infinite;
}
.welcome-card h2 {
    color: #f0f0f5;
    font-size: 1.5rem;
    font-weight: 600;
    margin: 0 0 0.8rem 0;
    letter-spacing: -0.01em;
}
.welcome-card p { color: #b0b0c0; font-size: 1.05rem; margin: 0.4rem 0; line-height: 1.6; }
.welcome-card .accent { color: #8b83ff; font-weight: 600; }

.summary-card-alert { border-color: #fbbf24 !important; }
.summary-card-alert .num { color: #fbbf24 !important; }

.run-meta {
    color: #6c6c80;
    font-size: 0.75rem;
    margin-bottom: 0.8rem;
    letter-spacing: 0.01em;
}
.run-meta .val { color: #b0b0c0; }

/* Newspaper grid */
.np-card-name {
    color: #e0e0ed;
    font-size: 0.88rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
    word-break: break-word;
}
.np-card-time {
    color: #6c6c80;
    font-size: 0.72rem;
    margin-bottom: 0.4rem;
}
.np-status {
    display: inline-block;
    padding: 0.3rem 0.9rem;
    border-radius: 20px;
    font-size: 0.9rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    border: 1px solid;
}
.np-status-green { background-color: #0d2818; color: #4ade80; border-color: #1a4028; }
.np-status-yellow { background-color: #2a1a00; color: #fbbf24; border-color: #4a3000; }
.np-status-red { background-color: #2a0a0a; color: #f87171; border-color: #4a1a1a; }
.np-status-gray { background-color: #1a1a24; color: #6c6c80; border-color: #2a2a3a; }
.np-card-summary {
    color: #6c6c80;
    font-size: 0.7rem;
    margin-top: 0.5rem;
}

/* Metric correlation matrix */
.mc-row {
    padding-bottom: 0.8rem;
    margin-bottom: 0.8rem;
    border-bottom: 1px solid #1e1e2a;
}
.mc-row:last-child {
    border-bottom: none;
    margin-bottom: 0;
    padding-bottom: 0;
}
.mc-cell {
    background-color: #16161f;
    border: 1px solid #2a2a3a;
    border-radius: 8px;
    padding: 0.8rem 1rem;
    text-align: center;
    min-height: 70px;
}
.mc-header {
    color: #e0e0ed;
    font-size: 1rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    text-align: center;
    padding: 0.6rem 0.8rem;
    border-bottom: 2px solid #2a2a3a;
    margin-bottom: 0.6rem;
}
.mc-config-name {
    color: #e0e0ed;
    font-size: 1rem;
    font-weight: 600;
    word-break: break-word;
}
.mc-test-name {
    color: #6c6c80;
    font-size: 0.8rem;
}
.mc-summary {
    background-color: #16161f;
    border: 1px solid #2a2a3a;
    border-radius: 10px;
    padding: 1rem 1.4rem;
    margin-top: 1rem;
}
.mc-confidence {
    font-size: 1.1rem;
    font-weight: 600;
    margin-bottom: 0.3rem;
}
.mc-confidence-high { color: #f87171; }
.mc-confidence-medium { color: #fbbf24; }
.mc-confidence-low { color: #4ade80; }
</style>
"""

OCP_VERSIONS = ["4.18", "4.19", "4.20", "4.21", "4.22", "4.23", "5.0"]
OCP_VERSION_DEFAULT_INDEX = 4
LOOKBACK_OPTIONS = ["7d", "15d", "30d", "60d", "Custom"]
DEFAULT_BENCHMARK_INDEX = "ripsaw-kube-burner-*"
DEFAULT_METADATA_INDEX = "perf_scale_ci*"

CATEGORIES = [
    {
        "name": "Core",
        "configs": [
            "trt-external-payload-cluster-density.yaml",
            "trt-external-payload-node-density.yaml",
            "trt-external-payload-node-density-cni.yaml",
            "trt-external-payload-udn-l2.yaml",
            "metal-perfscale-cpt-virt-density.yaml",
        ],
    },
    {"name": "Virt", "configs": ["trt-external-payload-node-density.yaml"]},
    {"name": "Telco", "configs": ["trt-external-payload-node-density.yaml"]},
    {"name": "HCP", "configs": ["trt-external-payload-node-density.yaml"]},
]


def render_lookback(default_index=1, key_prefix=""):
    """Render lookback selectbox with optional custom input. Returns the lookback string."""
    lb_key = f"{key_prefix}_lookback" if key_prefix else "lookback"
    custom_key = f"{key_prefix}_lookback_custom" if key_prefix else "lookback_custom"
    option = st.selectbox("Lookback", LOOKBACK_OPTIONS, index=default_index, key=lb_key)
    if option == "Custom":
        return st.text_input("Custom lookback (e.g. 45d, 10d2h)", value="30d", key=custom_key)
    return option

def render_css():
    st.markdown(APP_CSS, unsafe_allow_html=True)


def render_header():
    st.markdown(
        '<div class="newspaper-header">'
        "<h1>Orion Newspaper</h1>"
        "<p>Performance regression detection</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_es_status():
    es_server = os.environ.get("ES_SERVER", "")
    _mode = "container" if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv") else "local"
    if es_server:
        _mode_label = "Local-Dev" if _mode == "local" else "Container"
        st.markdown(
            f'<div class="es-connected"><span class="es-dot"></span> ES connected</div>'
            f'<div class="es-connected">Mode: {_mode_label}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.warning("ES_SERVER env var not set")


def render_results(return_code, full_output, temp_dir, n_metrics, run_duration, run_finished,
                   cmd_display="", expand_key="expand_all"):
    if expand_key not in st.session_state:
        st.session_state[expand_key] = True

    _es_scrub = os.environ.get("ES_SERVER", "")
    def _scrub(text):
        return text.replace(_es_scrub, "***") if _es_scrub else text

    if cmd_display:
        with st.expander("Command", expanded=False):
            st.code(cmd_display, language="bash")

    tab_results, tab_logs = st.tabs(["Results", "Logs"])
    expand = st.session_state[expand_key]

    with tab_results:
        col_status, col_toggle = st.columns([4, 1])
        with col_status:
            if return_code == 0:
                st.markdown('<div class="status-badge status-success">No regressions detected</div>', unsafe_allow_html=True)
            elif return_code == 2:
                st.markdown('<div class="status-badge status-regression">Regression(s) detected</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="status-badge status-error">Error (exit code {int(return_code)})</div>', unsafe_allow_html=True)
        with col_toggle:
            label = "Collapse All" if st.session_state[expand_key] else "Expand All"
            if st.button(label, use_container_width=True, key=f"toggle_{expand_key}"):
                st.session_state[expand_key] = not st.session_state[expand_key]
                st.rerun()

        if run_duration is not None:
            mins, secs = divmod(int(run_duration), 60)
            dur_str = f"{mins}m {secs}s" if mins else f"{secs}s"
            st.markdown(
                f'<div class="run-meta">Completed at <span class="val">{_esc(str(run_finished))}</span> in <span class="val">{_esc(dur_str)}</span></div>',
                unsafe_allow_html=True,
            )

        regressions = extract_regressions(full_output) if return_code == 2 else []
        csv_results = parse_csv_data(temp_dir) if temp_dir else []
        total_runs = sum(len(df) for _, df in csv_results)
        n_changepoints = full_output.count("··························")
        reg_cls = " summary-card-alert" if regressions else ""

        st.markdown(
            f'<div class="summary-row">'
            f'<div class="summary-card"><div class="num">{total_runs}</div><div class="lbl">Runs analyzed</div></div>'
            f'<div class="summary-card"><div class="num">{n_metrics}</div><div class="lbl">Metrics</div></div>'
            f'<div class="summary-card"><div class="num">{n_changepoints}</div><div class="lbl">Changepoints</div></div>'
            f'<div class="summary-card{reg_cls}"><div class="num">{len(regressions)}</div><div class="lbl">Regressions</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        if regressions:
            with st.expander("Regressions", expanded=expand):
                for reg in regressions:
                    st.markdown(
                        f'<div class="regression-card">'
                        f'<div><div class="label-text">Previous</div><div class="ver">{_esc(reg["prev_ver"])}</div></div>'
                        f'<div class="arrow">&rarr;</div>'
                        f'<div><div class="label-text">Bad</div><div class="ver">{_esc(reg["bad_ver"])}</div></div>'
                        f"</div>",
                        unsafe_allow_html=True,
                    )

        viz_files = find_viz_html(temp_dir) if temp_dir else []
        if viz_files:
            with st.expander("Visualizations", expanded=expand):
                for viz_file in viz_files:
                    viz_name = os.path.basename(viz_file).replace("_viz.html", "")
                    st.markdown(f"**{viz_name}**")
                    with open(viz_file, "r") as f:
                        html_content = _scrub(f.read())
                    n_plots = html_content.count('"yaxis')
                    height = max(600, min(n_plots * 350, 3000))
                    components.html(html_content, height=height, scrolling=True)

        if csv_results:
            with st.expander("Data", expanded=expand):
                for name, df in csv_results:
                    st.markdown(f"**{name}**")
                    st.dataframe(df, use_container_width=True, height=400)

        if not csv_results and not viz_files:
            st.info("No data files or visualizations were generated. Check the Logs tab for details.")

    with tab_logs:
        output_file = os.path.join(temp_dir, "output.txt") if temp_dir else None
        if output_file and os.path.exists(output_file):
            with open(output_file) as f:
                formatted = f.read()
            st.code(_scrub(formatted), language=None)
        if full_output:
            with st.expander("Raw stdout", expanded=not (output_file and os.path.exists(output_file))):
                st.code(_scrub(full_output), language=None)
