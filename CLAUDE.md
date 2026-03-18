# Orion Newspaper

Streamlit web UI that wraps the [orion](https://github.com/cloud-bulldozer/orion) CLI for OCP performance regression detection.

## Architecture

```
app.py                  → Page router (st.navigation), logging setup
orion_runner.py         → Backend: build_command(), run_orion(), config parsing, rate limiting
shared_rendering.py     → Shared CSS, CATEGORIES, status helpers, render_results(), render_header()
pages/
  newspaper.py          → Auto-refresh grid of categorized configs (2-hour interval)
  executive_summary.py  → Aggregated regression view across all configs
  manual.py             → Single-config execute with custom YAML editor (streamlit-ace)
  metrics.py            → Cross-config metric correlation matrix
  about.py              → Environment info, repo links
tests/
  test_orion_runner.py  → 18 tests, 91% coverage
  conftest.py           → Shared fixtures (SIMPLE_YAML, SECOND_YAML, tmp dirs)
kustomize/base/         → OpenShift deployment manifests (namespace: orion-newspaper)
Makefile                → make run, test, lint, build, push, clean
```

## Key conventions

- **ES_SERVER is a secret.** Never display its value in the UI. Only check truthiness (`if es_server:`) or show "set"/"not set". Read it from `os.environ` in `build_command()`, never pass through user params. Scrub it from all output with `_scrub()` in `render_results()` and at exception capture points.
- **HTML escaping.** All user-influenced values rendered via `unsafe_allow_html=True` must use `from html import escape as _esc`. This includes config names, test names, version strings, lookback input, status text, filenames.
- **CATEGORIES** is defined in `shared_rendering.py` with subcategory support. Use `filtered_categories()` to get a filtered copy and `_all_configs_for_category()` to flatten. Pages must not mutate it.
- **Status mapping** — orion return codes: 0=Pass, 2=Regression, 3=No Data, other=Error. Use `_status_info(return_code)` from `shared_rendering.py` which returns `{"pill", "badge", "card", "label"}`.
- **Shared helpers** — `display_name()`, `format_duration()`, `is_container()` in `shared_rendering.py`. `DEFAULT_BENCHMARK_INDEX`, `DEFAULT_METADATA_INDEX` in `orion_runner.py`.
- **Logger name** is `orion_newspaper` (set in `app.py`, used in `orion_runner.py`). JSON-formatted to stdout.
- **Rate limiting** uses `fcntl.flock` on `/tmp/orion_run.lock` — per-pod, not distributed.
- **JSON regression extraction** — orion runs with text format + `PROW_JOB_ID` env var to get both readable stdout and JSON output files. `extract_regressions_json()` parses `output_*.json` for metric-level regression data.

## Common commands

```bash
make run          # local dev server (clones orion repo if needed)
make test         # pytest with coverage (threshold: 80%, currently 91%)
make lint         # ruff check + format
make build        # podman build
make push TAG=v2  # build + push to quay.io/msheth/orion-newspaper
make clean        # remove container + temp files
```

Container runs as non-root (UID 1001). App lives at `/app/newspaper/` inside the image.

## Security constraints

- Never expose ES_SERVER value in UI, logs, or error messages
- Scrub ES_SERVER from exception messages at capture point, not just at display
- Escape all user input and filenames before HTML rendering
- Validate index patterns with `[a-zA-Z0-9_.*-]+` regex
- Subprocess gets minimal env (PATH, HOME, PYTHONUNBUFFERED, PROW_JOB_ID, ES_SERVER, index vars)
- 600s timeout on orion runs (configurable via ORION_RUN_TIMEOUT env var)
