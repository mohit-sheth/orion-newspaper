import os
import shutil
from html import escape as _esc

import altair as alt
import streamlit as st

from orion_runner import (
    aggregate_weekly_trends,
    discover_configs,
    execute_config,
    extract_metrics_json,
    generate_date_windows,
    get_config_metrics,
)
from shared_rendering import (
    OCP_VERSION_DEFAULT_INDEX,
    OCP_VERSIONS,
    TREND_TIMERANGES,
    display_name,
    render_css,
    render_es_status,
    render_header,
    render_index_selector,
    render_loading_subtitle,
)

render_css()
render_header("Trends", "Long-term metric trends with weekly granularity")

# --- Session state ---
if "tr_trend_data" not in st.session_state:
    st.session_state["tr_trend_data"] = None
# Reset stale flag — if we're here, no run is active (page just loaded)
st.session_state["tr_is_running"] = False
if "tr_run_meta" not in st.session_state:
    st.session_state["tr_run_meta"] = {}

# --- Sidebar ---
with st.sidebar:
    st.header("Trends")

    configs = discover_configs()
    default_config_idx = next(
        (i for i, c in enumerate(configs) if c == "trt-external-payload-udn-l2.yaml"),
        0,
    )
    config_name = st.selectbox("Config", configs, index=default_config_idx, key="tr_config")

    version = st.selectbox("OCP Version", OCP_VERSIONS, index=OCP_VERSION_DEFAULT_INDEX, key="tr_version")

    time_range = st.selectbox("Time Range", TREND_TIMERANGES, index=1, key="tr_range")
    months_map = {"1 month": 1, "2 months": 2, "3 months": 3, "4 months": 4}
    months_back = months_map.get(time_range, 2)

    # Metric selection from config YAML
    all_metrics = get_config_metrics(config_name) if config_name else {}
    flat_metrics = sorted(set(m for mlist in all_metrics.values() for m in mlist))
    # Default to ovnMem-ovnk-controller metric if available, else first 3
    preferred = [m for m in flat_metrics if m.startswith("ovnMem-ovncontroller")]
    default_metrics = preferred if preferred else (flat_metrics[:3] if len(flat_metrics) >= 3 else flat_metrics)
    selected_metrics = st.multiselect("Metrics", flat_metrics, default=default_metrics)

    agg_func = st.radio("Aggregation", ["Median", "Mean"], index=0, key="tr_agg")
    benchmark_index, metadata_index = render_index_selector("tr")

    render_es_status()

    st.divider()
    es_server = os.environ.get("ES_SERVER", "")
    if not es_server:
        st.error("ES_SERVER is not set. Analyze is disabled.", icon=":material/error:")
    analyze_clicked = st.button(
        "Analyze",
        type="primary",
        use_container_width=True,
        disabled=(st.session_state["tr_is_running"] or not es_server or not selected_metrics or not config_name),
    )


# --- Run logic ---
def _run_trends(config_name, version, months_back, selected_metrics, agg_func, benchmark_index, metadata_index):
    st.session_state["tr_is_running"] = True
    windows = generate_date_windows(months_back)

    loading_placeholder = st.empty()
    with loading_placeholder.container():
        overall = st.progress(0, text="Starting trend analysis...")
        render_loading_subtitle(1, len(windows), item_label="time windows")

    monthly_json_data = []
    total_runs = 0

    for i, (since_date, lookback) in enumerate(windows):
        overall.progress(
            i / len(windows),
            text=f"({i + 1}/{len(windows)}) Fetching {since_date}...",
        )

        result = execute_config(
            config_name,
            version,
            lookback,
            since=since_date,
            algorithm="hunter-analyze",
            benchmark_index=benchmark_index,
            metadata_index=metadata_index,
        )

        json_data = extract_metrics_json(result["temp_dir"]) if result["temp_dir"] else []
        monthly_json_data.append((since_date, json_data))
        total_runs += len(json_data)

        # Clean up temp dir immediately — we've extracted the JSON data
        if result["temp_dir"] and os.path.exists(result["temp_dir"]):
            shutil.rmtree(result["temp_dir"], ignore_errors=True)

    overall.progress(0.95, text="Aggregating weekly trends...")
    trend_df = aggregate_weekly_trends(monthly_json_data, selected_metrics, agg_func.lower())

    overall.progress(1.0, text="Complete")
    loading_placeholder.empty()

    st.session_state["tr_trend_data"] = trend_df
    st.session_state["tr_run_meta"] = {
        "config": config_name,
        "version": version,
        "months": months_back,
        "total_runs": total_runs,
        "weeks_with_data": len(trend_df),
        "metrics": selected_metrics,
        "agg_func": agg_func,
    }
    st.session_state["tr_is_running"] = False


# --- Trigger ---
if analyze_clicked:
    _run_trends(config_name, version, months_back, selected_metrics, agg_func, benchmark_index, metadata_index)
    st.rerun()


# --- Display ---
trend_df = st.session_state["tr_trend_data"]
meta = st.session_state["tr_run_meta"]

if trend_df is not None and not trend_df.empty:
    # Title
    st.subheader(f"{display_name(meta['config'])} — v{meta['version']} — {meta['months']}mo trend")

    # Summary cards
    st.markdown(
        f'<div class="summary-row">'
        f'<div class="summary-card">'
        f'<div class="num">{_esc(str(meta["weeks_with_data"]))}/{_esc(str(meta["months"] * 4))}</div>'
        f'<div class="lbl">Weeks with data</div></div>'
        f'<div class="summary-card">'
        f'<div class="num">{_esc(str(meta["total_runs"]))}</div>'
        f'<div class="lbl">Total runs</div></div>'
        f'<div class="summary-card">'
        f'<div class="num">{_esc(str(meta["months"]))}mo</div>'
        f'<div class="lbl">Queried</div></div>'
        f"</div>",
        unsafe_allow_html=True,
    )

    # Compute % diff for each metric and sort ascending
    metric_pcts = []
    for metric in meta["metrics"]:
        if metric not in trend_df.columns:
            continue
        cd = trend_df[["week_start", metric]].dropna(subset=[metric])
        if cd.empty:
            metric_pcts.append((metric, None))
        else:
            fv, lv = cd[metric].iloc[0], cd[metric].iloc[-1]
            pct = ((lv - fv) / fv) * 100 if fv else 0
            metric_pcts.append((metric, pct))
    metric_pcts.sort(key=lambda x: (x[1] is None, -(x[1] if x[1] is not None else 0)))

    # Trend cards — one per metric, chart inside expander
    for metric, pct_diff in metric_pcts:
        chart_data = trend_df[["week_start", metric]].dropna(subset=[metric])

        if chart_data.empty or pct_diff is None:
            st.markdown(
                f'<div class="trend-card trend-card-neutral">'
                f'<div class="trend-chart-label">{_esc(metric)}</div>'
                f'<div class="trend-meta">No data available</div></div>',
                unsafe_allow_html=True,
            )
            continue

        pct_str = f"+{pct_diff:.1f}%" if pct_diff > 0 else f"{pct_diff:.1f}%"
        pct_color = "#f87171" if pct_diff > 5 else ("#4ade80" if pct_diff < -5 else "#6c6c80")
        card_cls = "trend-card-up" if pct_diff > 5 else ("trend-card-down" if pct_diff < -5 else "trend-card-neutral")

        if pct_diff > 5:
            expander_label = f":red[{metric}  —  {pct_str}]"
        elif pct_diff < -5:
            expander_label = f":green[{metric}  —  {pct_str}]"
        else:
            expander_label = f":gray[{metric}  —  {pct_str}]"
        with st.expander(expander_label, expanded=abs(pct_diff) > 5):
            st.markdown(
                f'<div class="trend-card {card_cls}">'
                f'<div class="trend-meta">'
                f"{_esc(display_name(meta['config']))} &middot; "
                f"v{_esc(meta['version'])} &middot; "
                f"{_esc(meta['agg_func'])} per week"
                f"</div></div>",
                unsafe_allow_html=True,
            )
            chart = (
                alt.Chart(chart_data)
                .mark_line(point=True)
                .encode(
                    x=alt.X(
                        "week_start:N",
                        title="Week",
                        axis=alt.Axis(labelAngle=0),
                    ),
                    y=alt.Y(f"{metric}:Q", title=metric, scale=alt.Scale(zero=False)),
                    tooltip=["week_start", f"{metric}:Q"],
                )
                .properties(height=350)
            )
            st.altair_chart(chart, use_container_width=True)

    st.divider()

    # Run density
    if "n_runs" in trend_df.columns:
        with st.expander("Run density per week", icon=":material/bar_chart:"):
            density_df = trend_df[["week_start", "n_runs"]].set_index("week_start")
            st.bar_chart(density_df["n_runs"])

    # Data table
    with st.expander("Weekly data", icon=":material/table_chart:"):
        st.dataframe(trend_df, use_container_width=True)

elif trend_df is not None and trend_df.empty:
    st.warning("No data found for the selected config, version, and time range.", icon=":material/warning:")

else:
    n_configs = len(configs)
    st.markdown(
        '<div class="welcome-card">'
        "<h2>Trends</h2>"
        "<p>View long-term metric trends with "
        '<span class="accent">weekly granularity</span>.</p>'
        '<hr class="divider">'
        f'<p><span class="accent">{n_configs}</span> configs available. '
        "Select a config, metrics, and time range in the sidebar, "
        'then hit <span class="accent">Analyze</span>.</p>'
        '<hr class="divider">'
        "<p>Data is fetched in monthly chunks and aggregated into weekly data points, "
        "keeping Elasticsearch queries fast and lightweight.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
