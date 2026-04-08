import os
import shutil
import tempfile
import time
from datetime import datetime
from html import escape as _esc

import streamlit as st
from streamlit_ace import st_ace

from orion_runner import (
    build_command,
    create_temp_dir,
    discover_configs,
    get_config_metadata,
    get_config_path,
    humanize_command,
    run_orion,
)
from shared_rendering import (
    INDEX_PRESETS,
    OCP_VERSION_DEFAULT_INDEX,
    OCP_VERSIONS,
    render_css,
    render_es_status,
    render_header,
    render_lookback,
    render_results,
)

CUSTOM_CONFIG_LABEL = "Custom Config"

CUSTOM_CONFIG_PLACEHOLDER = """\
tests:
  - name: my-test
    metadata:
      platform: AWS
      ocpVersion: "{{ version }}"
      networkType: OVNKubernetes

    metrics:
    - name: podReadyLatency
      metricName.keyword: podLatencyQuantilesMeasurement
      quantileName: Ready
      metric_of_interest: P99
      direction: 1
"""

render_css()
render_header("Manual Execute", "Run a single config with custom parameters")

# --- Session state ---
for key, default in [
    ("running", False),
    ("full_output", ""),
    ("return_code", None),
    ("temp_dir", None),
    ("cmd_display", ""),
    ("n_metrics", 0),
    ("expand_all", True),
    ("run_duration", None),
    ("run_finished", None),
    ("custom_config_path", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# --- Sidebar ---
with st.sidebar:
    st.header("Parameters")

    configs = discover_configs()
    config_options = configs + [CUSTOM_CONFIG_LABEL]

    default_idx = next((i for i, c in enumerate(configs) if "trt-external-payload-udn-l2" in c), 0)
    config_name = st.selectbox("Config File", config_options, index=default_idx)

    is_custom = config_name == CUSTOM_CONFIG_LABEL

    metric_total = 0
    if not is_custom and config_name:
        meta = get_config_metadata(config_name)
        metric_total = meta["metric_count"]
        st.markdown(
            f'<div class="config-preview">'
            f'<div class="label">Tests</div>'
            f'<div class="value">{meta["test_count"]} test(s): {_esc(", ".join(meta["test_names"]))}</div>'
            f'<div class="label">Metrics</div>'
            f'<div class="value">{meta["metric_count"]} metric(s)</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

    st.divider()
    version = st.selectbox("OCP Version", OCP_VERSIONS, index=OCP_VERSION_DEFAULT_INDEX)

    lookback = render_lookback(default_index=1)

    node_count = st.checkbox("Match node count", value=False)

    render_es_status()

    st.divider()
    es_server = os.environ.get("ES_SERVER", "")
    if not es_server:
        st.error("ES_SERVER is not set. Execute is disabled.", icon=":material/error:")
    col_exec, col_clear = st.columns([2, 1])
    with col_exec:
        execute_clicked = st.button(
            "Execute", type="primary", use_container_width=True, disabled=st.session_state.running or not es_server
        )
    with col_clear:
        clear_clicked = st.button("Clear", use_container_width=True)

    with st.expander("Advanced Options", icon=":material/tune:"):
        algorithm = st.selectbox("Algorithm", ["hunter-analyze", "anomaly-detection", "cmr", "filter"], index=0)
        preset_names = list(INDEX_PRESETS.keys())
        selected_preset = st.selectbox("ES Index Preset", preset_names, index=0, key="manual_index_preset")
        benchmark_index, metadata_index = INDEX_PRESETS[selected_preset]
        uuid_input = st.text_input("Base UUID", value="")
        baseline_input = st.text_input("Baseline UUID(s)", value="")
        display_input = st.text_input("Display fields", value="buildUrl")
        debug = st.checkbox("Debug logging", value=False)
        sippy_pr_search = st.checkbox("Sippy PR search", value=True)

# --- Custom config editor ---
if is_custom:
    st.subheader("Custom Config")
    st.caption("Paste or edit your orion YAML config below. Supports `{{ version }}` template variables.")
    custom_yaml = st_ace(
        value=st.session_state.get("custom_yaml_content", CUSTOM_CONFIG_PLACEHOLDER),
        language="yaml",
        theme="monokai",
        min_lines=20,
        max_lines=40,
        font_size=13,
        key="custom_config_editor",
    )
    st.session_state["custom_yaml_content"] = custom_yaml

# --- Clear results ---
if clear_clicked:
    if st.session_state.temp_dir and os.path.exists(st.session_state.temp_dir):
        shutil.rmtree(st.session_state.temp_dir, ignore_errors=True)
    if st.session_state.custom_config_path and os.path.exists(st.session_state.custom_config_path):
        os.unlink(st.session_state.custom_config_path)
        st.session_state.custom_config_path = None
    st.session_state.return_code = None
    st.session_state.full_output = ""
    st.session_state.n_metrics = 0
    st.session_state.temp_dir = None
    st.session_state.cmd_display = ""
    st.rerun()

# --- Execute ---
if execute_clicked:
    if not config_name:
        st.error("Please select a config file.", icon=":material/error:")
        st.stop()
    if not es_server:
        st.error("ES Server is required. Set the ES_SERVER env var.", icon=":material/error:")
        st.stop()

    # Resolve config path
    if is_custom:
        custom_yaml = st.session_state.get("custom_yaml_content", "").strip()
        if not custom_yaml:
            st.error("Custom config is empty. Paste a valid YAML config.", icon=":material/error:")
            st.stop()
        # Clean up previous custom config file
        if st.session_state.custom_config_path and os.path.exists(st.session_state.custom_config_path):
            os.unlink(st.session_state.custom_config_path)
        fd, custom_path = tempfile.mkstemp(prefix="orion_custom_", suffix=".yaml")
        with os.fdopen(fd, "w") as f:
            f.write(custom_yaml)
        st.session_state.custom_config_path = custom_path
        config_path = custom_path
    else:
        config_path = get_config_path(config_name)

    if st.session_state.temp_dir and os.path.exists(st.session_state.temp_dir):
        shutil.rmtree(st.session_state.temp_dir, ignore_errors=True)

    temp_dir = create_temp_dir()
    st.session_state.temp_dir = temp_dir
    st.session_state.running = True
    st.session_state.return_code = None
    st.session_state.full_output = ""
    st.session_state.n_metrics = 0

    params = {
        "config_path": config_path,
        "algorithm": algorithm,
        "lookback": lookback,
        "node_count": node_count,
        "version": version,
        "benchmark_index": benchmark_index,
        "metadata_index": metadata_index,
        "uuid": uuid_input,
        "baseline": baseline_input,
        "display": display_input,
        "debug": debug,
        "sippy_pr_search": sippy_pr_search,
        "temp_dir": temp_dir,
    }

    cmd, env, cwd = build_command(params)
    st.session_state.cmd_display = humanize_command(cmd)

    progress_bar = st.progress(0, text="Starting...")
    status_container = st.empty()

    t0 = time.monotonic()
    return_code, full_output, log_messages = run_orion(cmd, env, cwd, status_container, progress_bar, metric_total)
    elapsed = time.monotonic() - t0

    st.session_state.return_code = return_code
    st.session_state.full_output = full_output
    st.session_state.n_metrics = sum(1 for _, msg in log_messages if "Collecting " in msg)
    st.session_state.run_duration = elapsed
    st.session_state.run_finished = datetime.now().strftime("%H:%M:%S")
    st.session_state.running = False
    st.rerun()

# --- Results ---
if st.session_state.return_code is not None:
    render_results(
        return_code=st.session_state.return_code,
        full_output=st.session_state.full_output,
        temp_dir=st.session_state.temp_dir,
        n_metrics=st.session_state.n_metrics,
        run_duration=st.session_state.run_duration,
        run_finished=st.session_state.run_finished,
        cmd_display=st.session_state.cmd_display,
        expand_key="expand_all",
    )
elif not is_custom:
    n_configs = len(configs)
    st.markdown(
        '<div class="welcome-card">'
        "<h2>Manual Execute</h2>"
        f'<p><span class="accent">{n_configs}</span> configs available. '
        f'Pick one in the sidebar and hit <span class="accent">Execute</span>.</p>'
        '<hr class="divider">'
        "<p>Orion queries Elasticsearch for historical runs, applies changepoint detection, "
        "and surfaces regressions with interactive Plotly visualizations.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
