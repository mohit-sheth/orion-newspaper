# Orion Newspaper

Streamlit web UI that wraps the [orion](https://github.com/cloud-bulldozer/orion) CLI for OCP performance regression detection.

## Architecture

```
app.py                  → Page router (st.navigation), logging setup
orion_runner.py         → Backend: build_command(), run_orion(), execute_config(), config parsing, rate limiting
shared_rendering.py     → Shared CSS, CATEGORIES, INDEX_PRESETS, status helpers, render_results(), render_header()
pages/
  executive_summary.py  → Aggregated regression view across all configs (default landing page)
  newspaper.py          → Auto-refresh grid of categorized configs (2-hour interval)
  trends.py             → Long-term metric trends with weekly granularity (1–4 months)
  metrics.py            → Cross-config metric correlation matrix
  manual.py             → Single-config execute with custom YAML editor (streamlit-ace)
  about.py              → Environment info, page descriptions, repo links, security notes
tests/
  test_orion_runner.py  → 35 tests, 92% coverage
  conftest.py           → Shared fixtures (SIMPLE_YAML, SECOND_YAML, AGG_YAML, tmp dirs)
kustomize/base/         → OpenShift deployment manifests (namespace: orion-newspaper)
Makefile                → make run, test, lint, build, push, clean
```

## Key conventions

- **ES_SERVER is a secret.** Never display its value in the UI. Only check truthiness (`if es_server:`) or show "set"/"not set". Read it from `os.environ` in `build_command()`, never pass through user params. Scrub it from all output with `_scrub()` in `render_results()` and at exception capture points (including `execute_config()` success path).
- **HTML escaping.** All user-influenced values rendered via `unsafe_allow_html=True` must use `from html import escape as _esc`. This includes config names, test names, version strings, lookback input, status text, filenames, metric names.
- **CATEGORIES** is defined in `shared_rendering.py` with subcategory support. Category names: OpenShift Core, OpenShift Virtualization, OpenShift Telco, Hosted Control Planes. Use `filtered_categories()` to get a filtered copy and `_all_configs_for_category()` to flatten. Pages must not mutate it.
- **INDEX_PRESETS** in `shared_rendering.py` defines ES index preset pairs (Default, OSPST). Use `render_index_selector()` for pages with their own Advanced Options, or import `INDEX_PRESETS` directly when embedding in a custom expander.
- **Status mapping** — orion return codes: 0=Pass, 2=Regression, 3=No Data, other=Error. Use `_status_info(return_code)` from `shared_rendering.py` which returns `{"pill", "badge", "card", "label"}`.
- **Shared helpers** — `execute_config()`, `NoOpTracker`, `extract_metrics_json()`, `generate_date_windows()`, `aggregate_weekly_trends()` in `orion_runner.py`. `display_name()`, `format_duration()`, `is_container()`, `render_loading_subtitle()`, `render_index_selector()` in `shared_rendering.py`.
- **Metric naming** — `_full_metric_name()` builds orion output names: standard metrics use `{name}_{metric_of_interest}` (e.g., `podReadyLatency_P99`), aggregated metrics use `{name}_{agg_type}` (e.g., `ovnMem-ovncontroller_avg`).
- **Logger name** is `orion_newspaper` (set in `app.py`, used in `orion_runner.py`). JSON-formatted to stdout.
- **Rate limiting** uses `fcntl.flock` on `/tmp/orion_run.lock` — per-pod, not distributed.
- **JSON output** — orion runs with text format + `PROW_JOB_ID` env var to get both readable stdout and JSON output files. `extract_regressions_json()` parses for changepoints, `extract_metrics_json()` parses for raw metric values (used by Trends page).
- **Session state prefixes** — newspaper: `np_`, metrics: `mc_`, trends: `tr_`. Manual page uses unprefixed keys (legacy).
- **Path traversal protection** — `get_config_path()` validates resolved path stays within `ORION_EXAMPLES_DIR`.

## Common commands

```bash
make run          # local dev server (clones orion repo if needed)
make test         # pytest with coverage (threshold: 80%, currently 92%)
make lint         # ruff check + format
make build        # podman build
make push TAG=v1  # build + push to quay.io/msheth/orion-newspaper
make clean        # remove container + temp files
```

Container runs as non-root (UID 1001). App lives at `/app/newspaper/` inside the image.

## Security constraints

- Never expose ES_SERVER value in UI, logs, or error messages
- Scrub ES_SERVER from subprocess output at capture point in `execute_config()`, not just at display
- Escape all user input and filenames before HTML rendering
- ES index presets in `INDEX_PRESETS` — no free-form index input on batch pages
- Subprocess gets minimal env (PATH, HOME, PYTHONUNBUFFERED, PROW_JOB_ID, ES_SERVER, index vars)
- 600s timeout on orion runs (configurable via ORION_RUN_TIMEOUT env var)
- Path traversal protection in `get_config_path()`
- Container: non-root, `allowPrivilegeEscalation: false`, `capabilities.drop: ALL`
