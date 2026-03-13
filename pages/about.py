import os

import streamlit as st

from orion_runner import ORION_DIR, ORION_BIN, ORION_EXAMPLES_DIR, discover_configs
from shared_rendering import render_css, render_header, OCP_VERSIONS

render_css()
render_header()

st.subheader("About")

# --- Mode ---
_mode = "Container" if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv") else "Local-Dev"

# --- Orion version ---
orion_version = "installed" if os.path.isfile(ORION_BIN) else "not found"

# --- Config count ---
configs = discover_configs()

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

st.markdown("### Newspaper defaults")
st.markdown(
    "The Newspaper page monitors configs in 4 categories. "
    "Each category runs with **hunter-analyze** algorithm. "
    "Auto-refreshes every **15 minutes**."
)
st.markdown(
    "| Category | Description |\n"
    "|---|---|\n"
    "| Core | Cluster density, node density, CNI, UDN L2, virt density |\n"
    "| Virt | Virtualization workloads |\n"
    "| Telco | Telco-specific workloads |\n"
    "| HCP | Hosted Control Plane workloads |"
)

st.markdown("### Manual Execute")
st.markdown(
    "The Manual Execute page lets you run any available config with full control over:\n"
    "- Algorithm (hunter-analyze, anomaly-detection, cmr, filter)\n"
    "- Lookback period\n"
    "- OCP version\n"
    "- Base UUID / Baseline comparison\n"
    "- Sippy PR search\n"
    "- Debug logging"
)

st.markdown("### Security")
st.markdown(
    "- ES_SERVER is passed at runtime via environment variable — **never baked into the image**\n"
    "- ES_SERVER is scrubbed from all UI output (shown as `***`)\n"
    "- The subprocess receives a minimal environment (PATH, HOME, ES_SERVER, index vars)\n"
    "- Default run command binds host port to `127.0.0.1` — no external exposure"
)
