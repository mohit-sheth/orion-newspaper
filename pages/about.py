import os

import streamlit as st

from orion_runner import ORION_BIN, ORION_DIR, ORION_EXAMPLES_DIR, discover_configs
from shared_rendering import OCP_VERSIONS, is_container, render_css, render_header

render_css()
render_header("About", "Environment info and repo links")

# --- Mode ---
_mode = "Container" if is_container() else "Local-Dev"

# --- Orion version ---
orion_version = "installed" if os.path.isfile(ORION_BIN) else "not found"

# --- Config count ---
configs = discover_configs()

st.markdown("### Pages")
st.markdown(
    "| Page | Description |\n"
    "|---|---|\n"
    "| **Executive Summary** | Aggregated regression view — overall health badge, "
    "pass/regression/error counts, category breakdown, and regression table sorted by severity |\n"
    "| **Newspaper** | Auto-refreshing grid of all monitored configs grouped by category and node scale. "
    "Smart-collapse: subcategories collapse when all pass, expand on regression. "
    "Drill into any config for Plotly visualizations and logs. Auto-refreshes every 2 hours |\n"
    "| **Trends** | Long-term metric trends with weekly granularity. "
    "Fetches data in monthly chunks to keep ES queries light, aggregates into weekly data points "
    "with median or mean. Sorted by % change with color-coded cards |\n"
    "| **Metric Correlation** | Cross-config regression confidence. "
    "Select a metric and multiple OCP versions to see a correlation matrix. "
    "If multiple configs regress on the same metric, it is likely a real issue |\n"
    "| **Manual Execute** | Full control over a single analysis run — "
    "pick any config, algorithm, lookback, OCP version, UUID comparison, "
    "custom YAML config editor, real-time progress |"
)

st.markdown("### Environment")
st.markdown(
    f"| Setting | Value |\n"
    f"|---|---|\n"
    f"| Mode | **{_mode}** |\n"
    f"| ORION_DIR | `{ORION_DIR}` |\n"
    f"| ORION_BIN | `{ORION_BIN}` |\n"
    f"| ORION_EXAMPLES_DIR | `{ORION_EXAMPLES_DIR}` |\n"
    f"| Orion binary | {orion_version} |\n"
    f"| Available configs | {len(configs)} |\n"
    f"| OCP versions | {', '.join(OCP_VERSIONS)} |\n"
    f"| ES_SERVER | {'set' if os.environ.get('ES_SERVER') else '**not set**'} |"
)

st.markdown("### Repositories")
st.markdown(
    "| Repo | URL |\n"
    "|---|---|\n"
    "| Newspaper | [mohit-sheth/orion-newspaper](https://github.com/mohit-sheth/orion-newspaper) |\n"
    "| Orion | [cloud-bulldozer/orion](https://github.com/cloud-bulldozer/orion) |"
)

st.markdown("### Categories")
st.markdown(
    "| Category | Subcategory | Configs |\n"
    "|---|---|---|\n"
    "| OpenShift Core | TRT Payload (6 nodes) | cluster-density, node-density, node-density-cni, udn-l2 |\n"
    "| OpenShift Core | Small Scale (24 nodes) | cluster-density, node-density, node-density-cni, udn-l2, udn-l3 |\n"
    "| OpenShift Core | Med Scale (120 nodes) | cluster-density, node-density, node-density-cni, udn-l2 |\n"
    "| OpenShift Core | Large Scale (252 nodes) | cluster-density, node-density, node-density-cni, udn-l2 |\n"
    "| OpenShift Virtualization | — | metal-perfscale-cpt-virt-density |\n"
    "| OpenShift Telco | — | trt-external-payload-node-density |\n"
    "| Hosted Control Planes | — | trt-external-payload-node-density |"
)

st.markdown("### Security")
st.markdown(
    "- ES_SERVER is passed at runtime via environment variable — **never baked into the image**\n"
    "- ES_SERVER is scrubbed from all UI output and subprocess output at capture point\n"
    "- The subprocess receives a minimal environment (PATH, HOME, ES_SERVER, index vars)\n"
    "- All user-influenced values are HTML-escaped before rendering\n"
    "- Path traversal protection on config file resolution\n"
    "- ES index presets (no free-form index input on batch pages)\n"
    "- Non-root container (UID 1001), privilege escalation blocked, all capabilities dropped\n"
    "- Default run command binds host port to `127.0.0.1` — no external exposure\n"
    "- For OpenShift: injected via K8s Secret, ClusterIP only (no Route)"
)
