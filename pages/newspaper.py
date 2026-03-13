import os
import shutil
import time
from datetime import datetime
from html import escape as _esc

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from orion_runner import (
    build_command, run_orion, create_temp_dir, humanize_command,
    discover_configs, get_config_path, get_config_metadata,
)
from shared_rendering import (
    render_css, render_header, render_es_status, render_results, render_lookback,
    OCP_VERSIONS, OCP_VERSION_DEFAULT_INDEX,
    DEFAULT_BENCHMARK_INDEX, DEFAULT_METADATA_INDEX,
    CATEGORIES,
)

render_css()
render_header()

available_configs = set(discover_configs())

# Build a working copy of categories filtered to available configs (don't mutate the shared constant)
categories = [
    {"name": cat["name"], "configs": [c for c in cat["configs"] if c in available_configs]}
    for cat in CATEGORIES
]

# Deduplicated list of all configs across categories
all_monitored = list(dict.fromkeys(c for cat in categories for c in cat["configs"]))

# --- Session state ---
if "np_results" not in st.session_state:
    st.session_state["np_results"] = {}
if "np_selected_config" not in st.session_state:
    st.session_state["np_selected_config"] = None
if "np_is_running" not in st.session_state:
    st.session_state["np_is_running"] = False
else:
    # Reset stale flag — if we're here, no run is active (page just loaded)
    st.session_state["np_is_running"] = False
if "np_last_poll_time" not in st.session_state:
    st.session_state["np_last_poll_time"] = 0

# --- Auto-refresh (15 min) ---
refresh_count = st_autorefresh(interval=900_000, limit=None, key="np_autorefresh")

# --- Sidebar ---
with st.sidebar:
    st.header("Newspaper")

    version = st.selectbox("OCP Version", OCP_VERSIONS, index=OCP_VERSION_DEFAULT_INDEX, key="np_version")
    lookback = render_lookback(default_index=0, key_prefix="np")

    render_es_status()

    st.divider()
    es_server = os.environ.get("ES_SERVER", "")
    if not es_server:
        st.error("ES_SERVER is not set. Refresh is disabled.")
    refresh_clicked = st.button("Refresh Now", type="primary", use_container_width=True,
                                disabled=st.session_state["np_is_running"] or not es_server)

    last_poll = st.session_state["np_last_poll_time"]
    if last_poll > 0:
        ago = int(time.time() - last_poll)
        mins, secs = divmod(ago, 60)
        st.caption(f"Last refresh: {mins}m {secs}s ago")


# --- Run all monitored configs ---
def _run_all(monitored_configs, version, lookback):
    if not os.environ.get("ES_SERVER"):
        st.error("ES_SERVER env var not set")
        return

    st.session_state["np_is_running"] = True
    results = st.session_state["np_results"]

    # Count total metrics across all configs for overall progress
    total_metrics = 0
    config_metric_counts = {}
    for cfg in monitored_configs:
        meta = get_config_metadata(cfg)
        config_metric_counts[cfg] = meta["metric_count"]
        total_metrics += meta["metric_count"]

    overall = st.progress(0, text="Starting refresh...")
    metrics_done = 0

    class _ProgressTracker:
        """Updates the single overall bar with config + metric name."""
        def __init__(self, bar, display, position, total_m, done):
            self._bar = bar
            self._display = display
            self._pos = position
            self._total = total_m
            self._done = done
        def progress(self, pct, text=""):
            if "Collecting " in text:
                self._update(text.split("Collecting ")[-1].split(" (")[0])
        def text(self, t):
            if "Collecting " in t:
                self._update(t.replace("Collecting ", "").rstrip("..."))
        def _update(self, metric):
            self._done += 1
            pct_overall = min(self._done / max(self._total, 1), 0.99)
            self._bar.progress(pct_overall, text=f"{self._pos} {self._display} · {metric}")

    for i, config_name in enumerate(monitored_configs):
        display = config_name.replace(".yaml", "")
        pos = f"({i+1}/{len(monitored_configs)})"
        overall.progress(metrics_done / max(total_metrics, 1),
                         text=f"{pos} {display}")

        # Clean up previous temp dir for this config
        prev = results.get(config_name, {})
        prev_dir = prev.get("temp_dir")
        if prev_dir and os.path.exists(prev_dir):
            shutil.rmtree(prev_dir, ignore_errors=True)

        temp_dir = create_temp_dir()
        params = {
            "config_path": get_config_path(config_name),
            "algorithm": "hunter-analyze",
            "lookback": lookback,
            "version": version,
            "benchmark_index": os.environ.get("es_benchmark_index", DEFAULT_BENCHMARK_INDEX),
            "metadata_index": os.environ.get("es_metadata_index", DEFAULT_METADATA_INDEX),
            "node_count": False,
            "debug": False,
            "sippy_pr_search": False,
            "temp_dir": temp_dir,
        }

        cmd, env, cwd = build_command(params)
        cmd_display = humanize_command(cmd)
        tracker = _ProgressTracker(overall, display, pos, total_metrics, metrics_done)

        try:
            t0 = time.monotonic()
            return_code, full_output, log_messages = run_orion(cmd, env, cwd, tracker, tracker, 0)
            elapsed = time.monotonic() - t0
            n_metrics = sum(1 for _, msg in log_messages if "Collecting " in msg)

            results[config_name] = {
                "return_code": return_code,
                "full_output": full_output,
                "n_metrics": n_metrics,
                "temp_dir": temp_dir,
                "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "duration": elapsed,
                "cmd_display": cmd_display,
            }
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            results[config_name] = {
                "return_code": -1,
                "full_output": str(e),
                "n_metrics": 0,
                "temp_dir": None,
                "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "duration": 0,
            }

        metrics_done += config_metric_counts.get(config_name, 0)

    overall.progress(1.0, text="Refresh complete")
    st.session_state["np_last_poll_time"] = time.time()
    st.session_state["np_is_running"] = False


# --- Trigger refresh ---
# Auto-refresh: only after first manual run, and if enough time has passed
auto_trigger = False
if st.session_state["np_last_poll_time"] > 0 and all_monitored:
    elapsed = time.time() - st.session_state["np_last_poll_time"]
    if elapsed >= 870:  # ~14.5 min, slightly under the 15 min interval
        auto_trigger = True

if (refresh_clicked or auto_trigger) and all_monitored and not st.session_state["np_is_running"]:
    _run_all(all_monitored, version, lookback)
    st.rerun()


# --- Helper: find category for a config ---
def _find_category(config_name):
    for cat in categories:
        if config_name in cat["configs"]:
            return cat["name"]
    return None


# --- Helper: render a card ---
def _status_for_return_code(return_code):
    """Map orion return code to (css_class, label)."""
    if return_code is None:
        return "np-status-gray", "Pending"
    if return_code == 0:
        return "np-status-green", "OK"
    if return_code == 2:
        return "np-status-yellow", "Regression"
    return "np-status-red", f"Error ({return_code})"


def _render_card(config_name, result, key_suffix=""):
    display_name = config_name.replace(".yaml", "")

    rc = result["return_code"] if result else None
    status_cls, status_text = _status_for_return_code(rc)
    time_text = result["last_run"] if result else "--"

    summary = ""
    if result and result["return_code"] is not None:
        mins, secs = divmod(int(result.get("duration", 0)), 60)
        dur = f"{mins}m {secs}s" if mins else f"{secs}s"
        summary = f'<div class="np-card-summary">{result.get("n_metrics", 0)} metrics &middot; {dur}</div>'

    st.markdown(
        f'<div class="np-card-name">{_esc(display_name)}</div>'
        f'<div class="np-card-time">{_esc(time_text)}</div>'
        f'<div class="np-status {status_cls}">{_esc(status_text)}</div>'
        f'{summary}',
        unsafe_allow_html=True,
    )

    if st.button("Details", key=f"np_detail_{key_suffix}_{config_name}", use_container_width=True,
                 disabled=result is None):
        st.session_state["np_selected_config"] = config_name
        st.rerun()


# --- Drill-down view ---
selected = st.session_state["np_selected_config"]
if selected and selected in st.session_state["np_results"]:
    cat_name = _find_category(selected)
    breadcrumb = f"{cat_name} / " if cat_name else ""

    if st.button(f"← Back to grid"):
        st.session_state["np_selected_config"] = None
        st.rerun()

    display_name = selected.replace(".yaml", "")
    st.subheader(f"{breadcrumb}{display_name}")

    result = st.session_state["np_results"][selected]
    render_results(
        return_code=result["return_code"],
        full_output=result["full_output"],
        temp_dir=result["temp_dir"],
        n_metrics=result["n_metrics"],
        run_duration=result["duration"],
        run_finished=result["last_run"],
        cmd_display=result.get("cmd_display", ""),
        expand_key="np_expand_all",
    )

# --- Grid view ---
else:
    if not all_monitored:
        st.info("No configs available.")
    elif not st.session_state["np_results"]:
        cat_sections = ""
        for cat in categories:
            if not cat["configs"]:
                continue
            config_badges = "".join(
                f'<span class="badge">{_esc(c.replace(".yaml", ""))}</span>'
                for c in cat["configs"]
            )
            cat_sections += (
                f'<div style="margin-bottom: 0.6rem;">'
                f'<span class="accent" style="font-size: 0.85rem;">{_esc(cat["name"])}</span>'
                f'<div style="margin-top: 0.3rem;">{config_badges}</div>'
                f'</div>'
            )
        st.markdown(
            '<div class="welcome-card">'
            '<h2>Newspaper</h2>'
            f'<p>Monitoring <span class="accent">{len(all_monitored)}</span> configs across '
            f'{sum(1 for c in categories if c["configs"])} categories.</p>'
            '<hr class="divider">'
            f'{cat_sections}'
            '<hr class="divider">'
            '<p>Click <span class="accent">Refresh Now</span> to run all configs. '
            'After the first run, auto-refresh kicks in every 15 minutes.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        results = st.session_state["np_results"]
        cols_per_row = 3

        for cat in categories:
            if not cat["configs"]:
                continue
            with st.expander(cat["name"], expanded=True):
                for row_start in range(0, len(cat["configs"]), cols_per_row):
                    row_configs = cat["configs"][row_start:row_start + cols_per_row]
                    cols = st.columns(cols_per_row)
                    for col, cfg in zip(cols, row_configs):
                        with col:
                            _render_card(cfg, results.get(cfg), key_suffix=cat["name"])
