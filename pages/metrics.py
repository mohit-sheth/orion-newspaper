import os
from html import escape as _esc

import streamlit as st

from orion_runner import (
    discover_configs,
    execute_config,
    get_metrics_for_configs,
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
render_header("Metric Correlation", "Check if a metric regresses consistently across configs and versions")

categories = filtered_categories(set(discover_configs()))

# --- Session state ---
if "mc_results" not in st.session_state:
    st.session_state["mc_results"] = {}
# Reset stale flag — if we're here, no run is active (page just loaded)
st.session_state["mc_is_running"] = False
if "mc_selected_cell" not in st.session_state:
    st.session_state["mc_selected_cell"] = None

# --- Sidebar ---
with st.sidebar:
    st.header("Metric Correlation")

    cat_names = [c["name"] for c in categories]
    selected_cat_name = st.selectbox("Category", cat_names, key="mc_category")
    selected_cat = next(c for c in categories if c["name"] == selected_cat_name)

    # Build metric reverse index for this category
    metrics_index = get_metrics_for_configs(_all_configs_for_category(selected_cat))
    metric_names = sorted(metrics_index.keys())

    if not metric_names:
        st.warning("No metrics found in this category's configs.")
        st.stop()

    selected_metric = st.selectbox("Metric", metric_names, key="mc_metric")

    appearances = metrics_index.get(selected_metric, [])
    config_count = len(set(cfg for cfg, _ in appearances))
    st.caption(f"Found in {config_count} config(s), {len(appearances)} test(s)")

    st.divider()
    versions = st.multiselect(
        "OCP Versions",
        OCP_VERSIONS,
        default=[OCP_VERSIONS[OCP_VERSION_DEFAULT_INDEX]],
        key="mc_versions",
    )
    lookback = render_lookback(default_index=0, key_prefix="mc")
    benchmark_index, metadata_index = render_index_selector("mc")

    render_es_status()

    st.divider()
    es_server = os.environ.get("ES_SERVER", "")
    if not es_server:
        st.error("ES_SERVER is not set. Analyze is disabled.")
    analyze_clicked = st.button(
        "Analyze",
        type="primary",
        use_container_width=True,
        disabled=st.session_state["mc_is_running"] or not es_server or not versions,
    )


# --- Run logic ---
def _run_correlation(appearances, versions, lookback, benchmark_index, metadata_index):
    """Run orion for each (config, version) pair that contains the selected metric."""
    st.session_state["mc_is_running"] = True
    results = st.session_state["mc_results"]

    # Deduplicate configs (a config may appear multiple times if multiple tests have the metric)
    unique_configs = list(dict.fromkeys(cfg for cfg, _ in appearances))
    total_runs = len(unique_configs) * len(versions)

    loading_placeholder = st.empty()
    with loading_placeholder.container():
        overall = st.progress(0, text="Starting analysis...")
        render_loading_subtitle(len(unique_configs), total_runs, item_label="runs")
    completed = 0

    for config_name in unique_configs:
        for version in versions:
            key = (config_name, version)
            display = display_name(config_name)
            pos = f"({completed + 1}/{total_runs})"
            overall.progress(completed / max(total_runs, 1), text=f"{pos} {display} v{version}")

            prev_dir = results.get(key, {}).get("temp_dir")
            results[key] = execute_config(
                config_name,
                version,
                lookback,
                benchmark_index=benchmark_index,
                metadata_index=metadata_index,
                prev_temp_dir=prev_dir,
            )
            completed += 1

    overall.progress(1.0, text="Analysis complete")
    loading_placeholder.empty()
    st.session_state["mc_is_running"] = False


# --- Trigger ---
if analyze_clicked and appearances and versions:
    st.session_state["mc_results"] = {}
    st.session_state["mc_selected_cell"] = None
    _run_correlation(appearances, versions, lookback, benchmark_index, metadata_index)
    st.rerun()


# --- Drill-down view ---
selected_cell = st.session_state["mc_selected_cell"]
if selected_cell and selected_cell in st.session_state["mc_results"]:
    config_name, version = selected_cell

    if st.button("← Back to matrix"):
        st.session_state["mc_selected_cell"] = None
        st.rerun()

    display = display_name(config_name)
    st.subheader(f"{display} — v{version}")

    result = st.session_state["mc_results"][selected_cell]
    render_results(
        return_code=result["return_code"],
        full_output=result["full_output"],
        temp_dir=result["temp_dir"],
        n_metrics=result["n_metrics"],
        run_duration=result["duration"],
        run_finished=result["last_run"],
        cmd_display=result.get("cmd_display", ""),
        expand_key="mc_expand_all",
    )

# --- Matrix view ---
elif st.session_state["mc_results"]:
    results = st.session_state["mc_results"]
    unique_configs = list(dict.fromkeys(cfg for cfg, _ in appearances))

    # Header row
    header_cols = st.columns([2] + [1] * len(versions))
    with header_cols[0]:
        st.markdown('<div class="mc-header">Config</div>', unsafe_allow_html=True)
    for i, ver in enumerate(versions):
        with header_cols[i + 1]:
            st.markdown(f'<div class="mc-header">v{_esc(ver)}</div>', unsafe_allow_html=True)

    # Data rows
    for config_name in unique_configs:
        display = display_name(config_name)
        tests_with_metric = [t for c, t in appearances if c == config_name]

        st.markdown('<div class="mc-row">', unsafe_allow_html=True)
        row_cols = st.columns([2] + [1] * len(versions))
        with row_cols[0]:
            st.markdown(
                f'<div class="mc-cell">'
                f'<div class="mc-config-name">{_esc(display)}</div>'
                f'<div class="mc-test-name">{_esc(", ".join(tests_with_metric))}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )

        for i, ver in enumerate(versions):
            key = (config_name, ver)
            result = results.get(key)

            with row_cols[i + 1]:
                rc = result["return_code"] if result else None
                info = _status_info(rc)
                status_cls, status_text = info["pill"], info["label"]

                dur_text = ""
                if result and result.get("duration"):
                    dur_text = format_duration(result["duration"])

                st.markdown(
                    f'<div class="mc-cell">'
                    f'<div class="np-status {status_cls}">{_esc(status_text)}</div>'
                    f'<div class="mc-test-name" style="margin-top:0.3rem">{_esc(dur_text)}</div>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if result is not None:
                    if st.button("Details", key=f"mc_detail_{config_name}_{ver}", use_container_width=True):
                        st.session_state["mc_selected_cell"] = key
                        st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # --- Summary ---
    st.divider()
    total_cells = len(unique_configs) * len(versions)
    regression_count = sum(
        1 for cfg in unique_configs for ver in versions if results.get((cfg, ver), {}).get("return_code") == 2
    )
    ok_count = sum(
        1 for cfg in unique_configs for ver in versions if results.get((cfg, ver), {}).get("return_code") == 0
    )
    nodata_count = sum(
        1 for cfg in unique_configs for ver in versions if results.get((cfg, ver), {}).get("return_code") == 3
    )
    error_count = total_cells - regression_count - ok_count - nodata_count

    if regression_count > total_cells / 2:
        confidence_cls = "mc-confidence-high"
        confidence_text = "High"
    elif regression_count >= 2:
        confidence_cls = "mc-confidence-medium"
        confidence_text = "Medium"
    else:
        confidence_cls = "mc-confidence-low"
        confidence_text = "Low"

    st.markdown(
        f'<div class="mc-summary">'
        f'<div class="mc-confidence {confidence_cls}">{confidence_text} confidence</div>'
        f'<div style="color:#b0b0c0; font-size:0.85rem;">'
        f"{regression_count} regression(s), {ok_count} OK, {error_count} error(s) "
        f"across {len(unique_configs)} config(s) and {len(versions)} version(s) "
        f"for metric <code>{_esc(selected_metric)}</code>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

# --- Welcome state ---
else:
    st.markdown(
        '<div class="welcome-card">'
        "<h2>Metric Correlation</h2>"
        '<p>Select a <span class="accent">metric</span> to check if it regresses consistently '
        "across multiple configs and versions.</p>"
        '<hr class="divider">'
        "<p>Consistent regressions across configs increase confidence that a real issue exists. "
        "If only one config shows a regression, it may be noise.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
