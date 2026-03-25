import os
from html import escape as _esc

import streamlit as st
import streamlit.components.v1 as components

from orion_runner import extract_regressions_json, find_viz_html, parse_csv_data

APP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Lora:wght@700&display=swap');

.stMarkdown, .stText, p, span:not([data-testid="stIconMaterial"]), label, h1, h2, h3, h4, h5, h6,
div, button, input, select, textarea, .stSelectbox, .stTextInput, .stButton {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
code, pre, .stCode, .stCodeBlock {
    font-family: 'JetBrains Mono', 'SFMono-Regular', 'Fira Code', 'Consolas', monospace;
}

/* Sidebar branding */
section[data-testid="stSidebar"] > div:first-child::before {
    content: "📰 Orion Newspaper";
    display: block;
    font-family: 'Lora', 'Georgia', serif;
    font-size: 1.7rem;
    font-weight: 700;
    color: #f0f0f5;
    letter-spacing: -0.02em;
    padding: 1.2rem 1rem 0.8rem 1rem;
    border-bottom: 1px solid #2a2a3a;
    margin-bottom: 0.5rem;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: #141420;
    border-right: 1px solid #2a2a3a;
    font-size: 1.5rem !important;
    min-width: 420px !important;
    width: 420px !important;
}
section[data-testid="stSidebar"] h2 {
    font-size: 2.1rem !important;
    font-weight: 700 !important;
}
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span {
    font-size: 1.4rem !important;
}
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stTextInput label,
section[data-testid="stSidebar"] .stCheckbox label {
    color: #b0b0c0; font-weight: 500; letter-spacing: 0.01em;
}
section[data-testid="stSidebar"] div[data-baseweb="select"] {
    font-size: 1.1rem !important;
}
section[data-testid="stSidebar"] input {
    font-size: 1.1rem !important;
}
section[data-testid="stSidebar"] button {
    font-size: 1.5rem !important;
}
section[data-testid="stSidebar"] small {
    font-size: 1.1rem !important;
}

/* Use full width of main area */
.stMainBlockContainer { max-width: 100%; padding-left: 2rem; padding-right: 2rem; }

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
    padding: 0.8rem 0 0.6rem 0;
    border-bottom: 1px solid #2a2a3a;
    margin-bottom: 1.2rem;
}
.newspaper-header h1 {
    color: #f0f0f5;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 1.5rem;
    font-weight: 800;
    margin: 0;
    letter-spacing: -0.03em;
}
.newspaper-header p {
    color: #8080a0;
    font-size: 1.1rem;
    font-weight: 400;
    margin: 0.3rem 0 0 0;
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
.status-nodata { background: linear-gradient(135deg, #0a1a2a, #102030); color: #60a5fa; border-color: #1a3050; }
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

.regression-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
}
.regression-table tr {
    background-color: #16161f;
}
.regression-table tr:hover {
    background-color: #1a1a28;
}
.regression-table th {
    color: #6c6c80;
    font-size: 0.65rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 0.5rem 0.8rem;
    text-align: left;
    border-bottom: 1px solid #2a2a3a;
}
.regression-table td {
    color: #e0e0ed;
    font-family: 'JetBrains Mono', 'SFMono-Regular', 'Consolas', monospace;
    font-size: 0.8rem;
    font-weight: 500;
    padding: 0.6rem 0.8rem;
    border-bottom: 1px solid #1e1e2a;
    white-space: nowrap;
}
.regression-table td:first-child {
    border-left: 3px solid #fbbf24;
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
    font-size: 1rem;
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
/* Card containers — heat signature tint */
.np-card {
    border: 1px solid #2a2a3a;
    border-radius: 10px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.4rem;
}
.np-card-pass { background-color: rgba(74, 222, 128, 0.04); border-color: rgba(74, 222, 128, 0.12); }
.np-card-regression { background-color: rgba(251, 191, 36, 0.06); border-color: rgba(251, 191, 36, 0.15); }
.np-card-error { background-color: rgba(248, 113, 113, 0.06); border-color: rgba(248, 113, 113, 0.15); }
.np-card-nodata { background-color: rgba(96, 165, 250, 0.04); border-color: rgba(96, 165, 250, 0.12); }
.np-card-pending { background-color: #16161f; border-color: #2a2a3a; }

.np-card-name {
    color: #e0e0ed;
    font-size: 0.88rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
    word-break: break-word;
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
.np-status-blue { background-color: #0a1a2a; color: #60a5fa; border-color: #1a3050; }
.np-status-gray { background-color: #1a1a24; color: #6c6c80; border-color: #2a2a3a; }
.np-card-summary {
    color: #8c8ca0;
    font-size: 0.8rem;
    margin-top: 0.5rem;
}
.np-card-regressions {
    display: inline-block;
}
.np-card-regressions summary { list-style: none; }
.np-card-regressions summary::-webkit-details-marker { display: none; }
.np-card-regressions[open] > summary { margin-bottom: 0.3rem; }
.np-card-regressions[open] .np-card-reg-item:first-child {
    padding-top: 0.2rem;
    border-top: 1px solid #2a2200;
}
.np-card-reg-item {
    font-family: 'JetBrains Mono', 'SFMono-Regular', 'Consolas', monospace;
    font-size: 0.78rem;
    font-weight: 500;
    padding: 0.05rem 0;
    display: flex;
    justify-content: space-between;
    gap: 0.5rem;
}
.np-card-reg-item .metric-name {
    color: #b0b0c0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

/* Loading subtitle */
.np-loading-subtitle {
    color: #6c6c80;
    font-size: 0.8rem;
    font-weight: 500;
    margin-top: -0.5rem;
    letter-spacing: 0.01em;
}

/* Progress bar */
.stProgress div[role="progressbar"],
.stProgress div[data-testid="stProgressBar"] > div {
    height: 16px !important;
    border-radius: 8px !important;
}
.stProgress p {
    color: #f0f0f5 !important;
    font-size: 1.3rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.01em !important;
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

/* Trend charts */
.trend-card {
    background: #13131d;
    border: 1px solid #2a2a3a;
    border-left: 3px solid #6c6c80;
    border-radius: 8px;
    padding: 0.7rem 1rem;
    margin-bottom: 1rem;
}
.trend-card-up { border-left-color: #f87171; background: #1a1318; }
.trend-card-down { border-left-color: #4ade80; background: #131a18; }
.trend-card-neutral { border-left-color: #6c6c80; }
.trend-chart-label {
    color: #e0e0ed;
    font-size: 0.95rem;
    font-weight: 600;
    display: inline;
}
.trend-pct {
    font-size: 0.85rem;
    margin-left: 0.8rem;
    font-weight: 600;
}
.trend-meta {
    color: #6c6c80;
    font-size: 0.75rem;
    margin-top: 0.2rem;
}
</style>
"""

OCP_VERSIONS = ["4.18", "4.19", "4.20", "4.21", "4.22", "4.23", "5.0"]
OCP_VERSION_DEFAULT_INDEX = 4
LOOKBACK_OPTIONS = ["7d", "15d", "30d", "60d", "Custom"]
TREND_TIMERANGES = ["1 month", "2 months", "3 months", "4 months"]

INDEX_PRESETS = {
    "Default": ("ripsaw-kube-burner-*", "perf_scale_ci*"),
    "OSPST": ("ospst-ripsaw-kube-burner-*", "ospst-perf-scale-ci-*"),
}

CATEGORIES = [
    {
        "name": "OpenShift Core",
        "subcategories": [
            {
                "name": "6 Nodes — TRT Payload",
                "prefix": "trt-external-payload-",
                "configs": [
                    "trt-external-payload-cluster-density.yaml",
                    "trt-external-payload-node-density.yaml",
                    "trt-external-payload-node-density-cni.yaml",
                    "trt-external-payload-udn-l2.yaml",
                ],
            },
            {
                "name": "24 Nodes — Small Scale",
                "prefix": "small-scale-",
                "configs": [
                    "small-scale-cluster-density.yaml",
                    "small-scale-node-density.yaml",
                    "small-scale-node-density-cni.yaml",
                    "small-scale-udn-l2.yaml",
                    "small-scale-udn-l3.yaml",
                ],
            },
            {
                "name": "120 Nodes — Med Scale",
                "prefix": "med-scale-",
                "configs": [
                    "med-scale-cluster-density.yaml",
                    "med-scale-node-density.yaml",
                    "med-scale-node-density-cni.yaml",
                    "med-scale-udn-l2.yaml",
                ],
            },
            {
                "name": "252 Nodes — Large Scale",
                "prefix": "large-scale-",
                "configs": [
                    "large-scale-cluster-density.yaml",
                    "large-scale-node-density.yaml",
                    "large-scale-node-density-cni.yaml",
                    "large-scale-udn-l2.yaml",
                ],
            },
        ],
    },
    {
        "name": "OpenShift Virtualization",
        "configs": [
            "metal-perfscale-cpt-virt-density.yaml",
            "trt-external-payload-node-density.yaml",
            "trt-external-payload-cluster-density.yaml",
        ],
    },
    {
        "name": "OpenShift Telco",
        "configs": [
            "trt-external-payload-node-density.yaml",
            "trt-external-payload-node-density-cni.yaml",
            "trt-external-payload-udn-l2.yaml",
        ],
    },
    {
        "name": "Hosted Control Planes",
        "configs": [
            "trt-external-payload-node-density.yaml",
            "trt-external-payload-cluster-density.yaml",
            "trt-external-payload-udn-l2.yaml",
        ],
    },
]


def _all_configs_for_category(cat: dict) -> list[str]:
    """Return flat list of all configs in a category (handles subcategories)."""
    if "subcategories" in cat:
        return [c for sub in cat["subcategories"] for c in sub["configs"]]
    return cat.get("configs", [])


def filtered_categories(available_configs: set) -> list[dict]:
    """Return CATEGORIES filtered to only include available configs, excluding empties."""
    result = []
    for cat in CATEGORIES:
        if "subcategories" in cat:
            subs = []
            for sub in cat["subcategories"]:
                filtered = [c for c in sub["configs"] if c in available_configs]
                if filtered:
                    entry = {"name": sub["name"], "configs": filtered}
                    if "prefix" in sub:
                        entry["prefix"] = sub["prefix"]
                    subs.append(entry)
            if subs:
                result.append({"name": cat["name"], "subcategories": subs})
        else:
            filtered = [c for c in cat["configs"] if c in available_configs]
            if filtered:
                result.append({"name": cat["name"], "configs": filtered})
    return result


def display_name(config_name: str, strip_prefix: str = "") -> str:
    """Strip .yaml extension and optional prefix for display."""
    name = config_name.replace(".yaml", "")
    if strip_prefix and name.startswith(strip_prefix):
        name = name[len(strip_prefix) :]
    return name


def format_duration(seconds: float) -> str:
    """Format seconds as 'Xm Ys' or 'Ys'."""
    mins, secs = divmod(int(seconds), 60)
    return f"{mins}m {secs}s" if mins else f"{secs}s"


def is_container() -> bool:
    """Detect if running inside a container."""
    return os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")


STATUS_MAP = {
    None: {
        "pill": "np-status-gray",
        "badge": "status-error",
        "card": "np-card-pending",
        "label": "Pending",
    },
    0: {
        "pill": "np-status-green",
        "badge": "status-success",
        "card": "np-card-pass",
        "label": "Pass",
    },
    2: {
        "pill": "np-status-yellow",
        "badge": "status-regression",
        "card": "np-card-regression",
        "label": "Regression",
    },
    3: {
        "pill": "np-status-blue",
        "badge": "status-nodata",
        "card": "np-card-nodata",
        "label": "No Data",
    },
}
_ERROR_STATUS = {"pill": "np-status-red", "badge": "status-error", "card": "np-card-error"}


def _status_info(return_code):
    """Return full status dict for a return code."""
    info = STATUS_MAP.get(return_code)
    if info:
        return info
    return {**_ERROR_STATUS, "label": f"Error ({return_code})"}


def _format_value(v):
    """Format a metric value for display."""
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v) if v != "" else "?"


def render_regression_table(regressions, show_config=False):
    """Render regressions as an aligned table. Set show_config=True for executive summary."""
    if not regressions:
        return
    config_th = "<th>Config</th>" if show_config else ""
    rows = ""
    for reg in regressions:
        pct = reg.get("percentage_change", 0)
        pct_str = f"+{pct:.1f}%" if pct > 0 else f"{pct:.1f}%"
        pct_cls = "color: #f87171" if abs(pct) >= 25 else "color: #fbbf24"
        prev_val = _format_value(reg.get("prev_value", ""))
        bad_val = _format_value(reg.get("bad_value", ""))
        tooltip = f"{prev_val} → {bad_val}"
        config_td = f"<td>{_esc(reg.get('config', ''))}</td>" if show_config else ""
        rows += (
            f"<tr>"
            f"{config_td}"
            f"<td>{_esc(reg.get('metric', ''))}</td>"
            f'<td style="{pct_cls}; cursor: help;" title="{_esc(tooltip)}">{_esc(pct_str)}</td>'
            f"<td>{_esc(reg.get('prev_ver', ''))}</td>"
            f'<td style="color: #fbbf24;">&rarr;</td>'
            f"<td>{_esc(reg.get('bad_ver', ''))}</td>"
            f"</tr>"
        )
    st.markdown(
        f'<table class="regression-table">'
        f"<thead><tr>{config_th}<th>Metric</th><th>Change</th>"
        f"<th>Previous</th><th></th><th>Bad</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>",
        unsafe_allow_html=True,
    )


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


def render_header(title="Orion Newspaper", subtitle=""):
    sub_html = f"<p>{_esc(subtitle)}</p>" if subtitle else ""
    st.markdown(
        f'<div class="newspaper-header"><h1>{_esc(title)}</h1>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def render_loading_subtitle(n_configs, n_items, item_label="metrics"):
    """Render a muted subtitle below the progress bar during batch runs."""
    st.markdown(
        f'<div class="np-loading-subtitle">'
        f"Refreshing {_esc(str(n_configs))} configs &middot; "
        f"{_esc(str(n_items))} {_esc(item_label)} &middot; this will take a moment"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_index_selector(key_prefix: str) -> tuple[str, str]:
    """Render an ES index preset selector under an Advanced Options expander.

    Returns (benchmark_index, metadata_index) based on selection.
    """
    with st.expander("Advanced Options"):
        preset_names = list(INDEX_PRESETS.keys())
        selected = st.selectbox(
            "ES Index Preset",
            preset_names,
            index=0,
            key=f"{key_prefix}_index_preset",
        )
        bm, md = INDEX_PRESETS[selected]
        return bm, md


def render_es_status():
    es_server = os.environ.get("ES_SERVER", "")
    if es_server:
        _mode_label = "Container" if is_container() else "Local-Dev"
        st.markdown(
            f'<div class="es-connected"><span class="es-dot"></span> ES connected</div>'
            f'<div class="es-connected">Mode: {_mode_label}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.warning("ES_SERVER env var not set")


def render_results(
    return_code, full_output, temp_dir, n_metrics, run_duration, run_finished, cmd_display="", expand_key="expand_all"
):
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
            info = _status_info(return_code)
            st.markdown(
                f'<div class="status-badge {info["badge"]}">{_esc(info["label"])}</div>',
                unsafe_allow_html=True,
            )
        with col_toggle:
            label = "Collapse All" if st.session_state[expand_key] else "Expand All"
            if st.button(label, use_container_width=True, key=f"toggle_{expand_key}"):
                st.session_state[expand_key] = not st.session_state[expand_key]
                st.rerun()

        if run_duration is not None:
            st.markdown(
                f'<div class="run-meta">Completed at '
                f'<span class="val">{_esc(str(run_finished))}</span> in '
                f'<span class="val">{_esc(format_duration(run_duration))}</span></div>',
                unsafe_allow_html=True,
            )

        regressions = extract_regressions_json(temp_dir) if return_code == 2 else []
        csv_results = parse_csv_data(temp_dir) if temp_dir else []
        total_runs = sum(len(df) for _, df in csv_results)
        reg_cls = " summary-card-alert" if regressions else ""

        st.markdown(
            f'<div class="summary-row">'
            f'<div class="summary-card"><div class="num">{total_runs}</div><div class="lbl">Runs analyzed</div></div>'
            f'<div class="summary-card"><div class="num">{n_metrics}</div><div class="lbl">Metrics</div></div>'
            f'<div class="summary-card{reg_cls}">'
            f'<div class="num">{len(regressions)}</div>'
            f'<div class="lbl">Regressions</div></div>'
            f"</div>",
            unsafe_allow_html=True,
        )

        if regressions:
            with st.expander("Regressions", expanded=expand):
                render_regression_table(regressions)

        viz_files = find_viz_html(temp_dir) if temp_dir else []
        if viz_files:
            with st.expander("Visualizations", expanded=expand):
                for viz_file in viz_files:
                    viz_name = os.path.basename(viz_file).replace("_viz.html", "")
                    st.markdown(f"**{_esc(viz_name)}**")
                    with open(viz_file, "r") as f:
                        html_content = _scrub(f.read())
                    n_plots = html_content.count('"yaxis')
                    height = max(600, min(n_plots * 350, 3000))
                    components.html(html_content, height=height, scrolling=True)

        if csv_results:
            with st.expander("Data", expanded=expand):
                for name, df in csv_results:
                    st.markdown(f"**{_esc(name)}**")
                    st.dataframe(df, use_container_width=True, height=400)

        if not csv_results and not viz_files:
            st.info("No data files or visualizations were generated. Check the Logs tab for details.")

    with tab_logs:
        if full_output:
            st.code(_scrub(full_output), language=None)
