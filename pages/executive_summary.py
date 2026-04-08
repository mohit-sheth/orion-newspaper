from html import escape as _esc

import streamlit as st

from orion_runner import discover_configs
from shared_rendering import (
    _all_configs_for_category,
    _status_info,
    display_name,
    filtered_categories,
    render_css,
    render_header,
    render_regression_table,
)

render_css()
render_header("Executive Summary", "Aggregated regression view across all configs")

categories = filtered_categories(set(discover_configs()))

np_results = st.session_state.get("np_results", {})

if not np_results:
    st.markdown(
        '<div class="welcome-card">'
        "<h2>Executive Summary</h2>"
        '<p>No data yet. Run <span class="accent">Newspaper &rarr; Refresh Now</span> first, '
        "then come back here for an aggregated view.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()

# --- Aggregate data ---
total_configs = len(np_results)
ok_count = sum(1 for r in np_results.values() if r.get("return_code") == 0)
regression_count = sum(1 for r in np_results.values() if r.get("return_code") == 2)
nodata_count = sum(1 for r in np_results.values() if r.get("return_code") == 3)
error_count = total_configs - ok_count - regression_count - nodata_count

# Collect all regressions across all configs
all_regressions = []
for config_name, result in np_results.items():
    for reg in result.get("regressions", []):
        all_regressions.append({**reg, "config": display_name(config_name)})

# --- Overall Health ---
if regression_count == 0 and error_count == 0:
    health_rc = 0
elif error_count > 0:
    health_rc = -1
elif regression_count > 0:
    health_rc = 2
else:
    health_rc = 0
health_info = _status_info(health_rc)
health_labels = {0: "All Configs Pass", 2: "Regressions Detected", -1: "Errors Present"}
st.markdown(
    f'<div class="status-badge {health_info["badge"]}">{_esc(health_labels.get(health_rc, "Unknown"))}</div>',
    unsafe_allow_html=True,
)

reg_cls = " summary-card-alert" if regression_count > 0 else ""
err_cls = " summary-card-alert" if error_count > 0 else ""
st.markdown(
    f'<div class="summary-row">'
    f'<div class="summary-card"><div class="num">{ok_count}/{total_configs}</div><div class="lbl">Pass</div></div>'
    f'<div class="summary-card{reg_cls}">'
    f'<div class="num">{len(all_regressions)}</div>'
    f'<div class="lbl">Regressions ({regression_count} configs)</div></div>'
    f'<div class="summary-card{err_cls}"><div class="num">{error_count}</div><div class="lbl">Errors</div></div>'
    f"</div>",
    unsafe_allow_html=True,
)

# --- Category Breakdown ---
non_empty_cats = [c for c in categories if _all_configs_for_category(c)]
if non_empty_cats:
    st.subheader("Category Breakdown")
    cat_cols = st.columns(len(non_empty_cats))
    for col, cat in zip(cat_cols, non_empty_cats):
        with col:
            cat_cfgs = _all_configs_for_category(cat)
            cat_ok = sum(1 for c in cat_cfgs if np_results.get(c, {}).get("return_code") == 0)
            cat_reg = sum(1 for c in cat_cfgs if np_results.get(c, {}).get("return_code") == 2)
            cat_nodata = sum(1 for c in cat_cfgs if np_results.get(c, {}).get("return_code") == 3)
            cat_run = sum(1 for c in cat_cfgs if c in np_results)
            cat_err = cat_run - cat_ok - cat_reg - cat_nodata
            cat_total = len(cat_cfgs)

            cat_rc = -1 if cat_err > 0 else (2 if cat_reg > 0 else 0)
            cat_info = _status_info(cat_rc)

            st.markdown(
                f'<div class="mc-cell" style="padding: 1rem;">'
                f'<div class="mc-config-name">{_esc(cat["name"])}</div>'
                f'<div class="np-status {cat_info["pill"]}" style="margin-top: 0.5rem;">'
                f"{cat_ok}/{cat_total} Pass</div>"
                f'<div class="mc-test-name" style="margin-top: 0.4rem;">'
                f"{cat_reg} regression(s), {cat_err} error(s)</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

# --- Regressions by Severity ---
if all_regressions:
    st.subheader("Regressions by Severity")
    render_regression_table(all_regressions, show_config=True)
else:
    st.success("No regressions detected across any configs.", icon=":material/check_circle:")
