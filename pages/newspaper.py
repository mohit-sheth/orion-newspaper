import os
import time
from datetime import datetime
from html import escape as _esc

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from orion_runner import (
    discover_configs,
    execute_config,
    extract_regressions_json,
    get_config_metadata,
    parse_csv_data,
)
from shared_rendering import (
    OCP_VERSION_DEFAULT_INDEX,
    OCP_VERSIONS,
    _all_configs_for_category,
    _status_info,
    display_name,
    filtered_categories,
    format_duration,
    render_css,
    render_es_status,
    render_header,
    render_index_selector,
    render_loading_subtitle,
    render_lookback,
    render_results,
)

render_css()
render_header("Newspaper", "Auto-refresh grid of all monitored configs with regression detection")

categories = filtered_categories(set(discover_configs()))

# Deduplicated list of all configs across categories
all_monitored = list(dict.fromkeys(c for cat in categories for c in _all_configs_for_category(cat)))

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

# --- Auto-refresh (2 hours) ---
st_autorefresh(interval=7_200_000, limit=None, key="np_autorefresh")

# --- Sidebar ---
with st.sidebar:
    st.header("Newspaper")

    version = st.selectbox("OCP Version", OCP_VERSIONS, index=OCP_VERSION_DEFAULT_INDEX, key="np_version")
    lookback = render_lookback(default_index=0, key_prefix="np")
    benchmark_index, metadata_index = render_index_selector("np")

    render_es_status()

    st.divider()
    es_server = os.environ.get("ES_SERVER", "")
    if not es_server:
        st.error("ES_SERVER is not set. Refresh is disabled.")
    refresh_clicked = st.button(
        "Refresh Now",
        type="primary",
        use_container_width=True,
        disabled=st.session_state["np_is_running"] or not es_server,
    )

    last_poll = st.session_state["np_last_poll_time"]
    if last_poll > 0:
        st.caption(f"Last refresh: {datetime.fromtimestamp(last_poll).strftime('%H:%M:%S')}")


# --- Run all monitored configs ---
def _run_all(monitored_configs, version, lookback, benchmark_index, metadata_index):
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

    loading_placeholder = st.empty()
    with loading_placeholder.container():
        overall = st.progress(0, text="Starting refresh...")
        render_loading_subtitle(len(monitored_configs), total_metrics)
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
        display = display_name(config_name)
        pos = f"({i + 1}/{len(monitored_configs)})"
        overall.progress(metrics_done / max(total_metrics, 1), text=f"{pos} {display}")

        prev_dir = results.get(config_name, {}).get("temp_dir")
        tracker = _ProgressTracker(overall, display, pos, total_metrics, metrics_done)
        result = execute_config(
            config_name,
            version,
            lookback,
            benchmark_index=benchmark_index,
            metadata_index=metadata_index,
            status_tracker=tracker,
            progress_tracker=tracker,
            prev_temp_dir=prev_dir,
        )

        # Augment with newspaper-specific fields
        if result["return_code"] == 2:
            result["regressions"] = extract_regressions_json(result["temp_dir"])
        else:
            result["regressions"] = []
        csv_data = parse_csv_data(result["temp_dir"]) if result["temp_dir"] else []
        result["n_runs"] = sum(len(df) for _, df in csv_data)
        result["n_metrics"] = config_metric_counts.get(config_name, result["n_metrics"])
        results[config_name] = result

        metrics_done += config_metric_counts.get(config_name, 0)

    overall.progress(1.0, text="Refresh complete")
    loading_placeholder.empty()
    st.session_state["np_last_poll_time"] = time.time()
    st.session_state["np_is_running"] = False


# --- Trigger refresh ---
# Auto-refresh: only after first manual run, and if enough time has passed
auto_trigger = False
if st.session_state["np_last_poll_time"] > 0 and all_monitored:
    elapsed = time.time() - st.session_state["np_last_poll_time"]
    if elapsed >= 7_100:  # ~1h58m, slightly under the 2 hour interval
        auto_trigger = True

if (refresh_clicked or auto_trigger) and all_monitored and not st.session_state["np_is_running"]:
    _run_all(all_monitored, version, lookback, benchmark_index, metadata_index)
    st.rerun()


# --- Helper: find category for a config ---
def _find_category(config_name):
    for cat in categories:
        if config_name in _all_configs_for_category(cat):
            return cat["name"]
    return None


# --- Helper: render a card ---
def _render_card(config_name, result, key_suffix="", strip_prefix=""):
    dn = display_name(config_name, strip_prefix)

    rc = result["return_code"] if result else None
    info = _status_info(rc)
    status_cls = info["pill"]
    status_text = info["label"]
    card_cls = info["card"]

    summary = ""
    items = ""
    if result and result["return_code"] is not None:
        dur = format_duration(result.get("duration", 0))
        n_metrics = result.get("n_metrics", 0)
        n_runs = result.get("n_runs", 0)
        parts = []
        if n_runs:
            parts.append(f"{n_runs} runs")
        parts.append(f"{n_metrics} metrics")
        parts.append(dur)
        summary = f'<div class="np-card-summary">{" &middot; ".join(parts)}</div>'

        for reg in result.get("regressions", []):
            pct = reg.get("percentage_change", 0)
            pct_str = f"+{pct:.1f}%" if pct > 0 else f"{pct:.1f}%"
            pct_color = "#f87171" if abs(pct) >= 25 else "#fbbf24"
            items += (
                f'<div class="np-card-reg-item">'
                f'<span class="metric-name">{_esc(reg.get("metric", ""))}</span>'
                f'<span style="color: {pct_color};">{_esc(pct_str)}</span>'
                f"</div>"
            )

    # For regression cards, the status badge itself is the dropdown trigger
    if items:
        status_html = (
            f'<details class="np-card-regressions">'
            f'<summary class="np-status {status_cls}" style="cursor:pointer;">{_esc(status_text)}</summary>'
            f"{items}"
            f"</details>"
        )
    else:
        status_html = f'<div class="np-status {status_cls}">{_esc(status_text)}</div>'

    st.markdown(
        f'<div class="np-card {card_cls}"><div class="np-card-name">{_esc(dn)}</div>{status_html}{summary}</div>',
        unsafe_allow_html=True,
    )

    if st.button(
        "Details", key=f"np_detail_{key_suffix}_{config_name}", use_container_width=True, disabled=result is None
    ):
        st.session_state["np_selected_config"] = config_name
        st.rerun()


# --- Drill-down view ---
selected = st.session_state["np_selected_config"]
if selected and selected in st.session_state["np_results"]:
    cat_name = _find_category(selected)
    breadcrumb = f"{cat_name} / " if cat_name else ""

    if st.button("← Back to grid"):
        st.session_state["np_selected_config"] = None
        st.rerun()

    st.subheader(f"{breadcrumb}{display_name(selected)}")

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
            cat_configs = _all_configs_for_category(cat)
            if not cat_configs:
                continue
            config_badges = "".join(f'<span class="badge">{_esc(display_name(c))}</span>' for c in cat_configs)
            cat_sections += (
                f'<div style="margin-bottom: 0.6rem;">'
                f'<span class="accent" style="font-size: 0.85rem;">{_esc(cat["name"])}</span>'
                f'<div style="margin-top: 0.3rem;">{config_badges}</div>'
                f"</div>"
            )
        non_empty = sum(1 for c in categories if _all_configs_for_category(c))
        st.markdown(
            '<div class="welcome-card">'
            "<h2>Newspaper</h2>"
            f'<p>Monitoring <span class="accent">{len(all_monitored)}</span> configs across '
            f"{non_empty} categories.</p>"
            '<hr class="divider">'
            f"{cat_sections}"
            '<hr class="divider">'
            '<p>Click <span class="accent">Refresh Now</span> to run all configs. '
            "After the first run, auto-refresh kicks in every 2 hours.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        results = st.session_state["np_results"]
        cols_per_row = 4

        for cat in categories:
            cat_configs = _all_configs_for_category(cat)
            if not cat_configs:
                continue

            with st.expander(cat["name"], expanded=True):
                if "subcategories" in cat:
                    for sub in cat["subcategories"]:
                        if not sub["configs"]:
                            continue
                        prefix = sub.get("prefix", "")
                        has_issues = any(results.get(cfg, {}).get("return_code") in (2, -1) for cfg in sub["configs"])
                        with st.expander(f":orange[{sub['name']}]", expanded=has_issues):
                            for row_start in range(0, len(sub["configs"]), cols_per_row):
                                row_configs = sub["configs"][row_start : row_start + cols_per_row]
                                cols = st.columns(cols_per_row)
                                for col, cfg in zip(cols, row_configs):
                                    with col:
                                        key = f"{cat['name']}_{sub['name']}"
                                        _render_card(
                                            cfg,
                                            results.get(cfg),
                                            key_suffix=key,
                                            strip_prefix=prefix,
                                        )
                else:
                    for row_start in range(0, len(cat["configs"]), cols_per_row):
                        row_configs = cat["configs"][row_start : row_start + cols_per_row]
                        cols = st.columns(cols_per_row)
                        for col, cfg in zip(cols, row_configs):
                            with col:
                                _render_card(cfg, results.get(cfg), key_suffix=cat["name"])
