# Orion Newspaper

Web UI for [cloud-bulldozer/orion](https://github.com/cloud-bulldozer/orion) — performance regression detection for OCP from your browser.

## Features

**Executive Summary** (default) — aggregated regression view across all configs.
- Overall health badge, pass/regression/error counts
- Category breakdown with per-category status
- Regression table sorted by severity

**Newspaper** — auto-refreshing grid of monitored configs.
- Configs grouped by category (Core with subcategories by scale, Virt, Telco, HCP)
- Smart-collapse: subcategories collapsed when all pass, expanded on regression/error
- Status at a glance: green (OK), yellow (regression), red (error), blue (no data)
- Drill into any config for full results, interactive Plotly visualizations, and logs
- Auto-refreshes every 2 hours after the first manual run

**Trends** — long-term metric trends with weekly granularity.
- View metric trends over 3, 6, or 12 months
- Data fetched in monthly chunks to keep ES queries light and fast
- Weekly aggregation with median or mean, sorted by % change
- Altair charts with auto-scaled Y-axis and tooltips

**Metric Correlation** — cross-config regression confidence.
- Select a metric and multiple OCP versions
- Runs all configs in the category that contain that metric
- Correlation matrix: config × version → regression status
- Confidence indicator: multiple configs regressing = likely real

**Manual Execute** — full control over a single analysis run.
- Pick any config, algorithm (hunter-analyze, anomaly-detection, CMR, filter), lookback, and OCP version
- Compare specific UUIDs, adjust baselines, enable Sippy PR search
- Custom Config: paste your own YAML config with syntax-highlighted editor
- Real-time progress with metric-level updates

**About** — environment info, repo links, security notes.

## Getting started

See [DEPLOYMENT.md](DEPLOYMENT.md) for all deployment options (pre-built image, local dev, build from source, OpenShift).

Quickest way:

```bash
podman run -d --name orion-newspaper \
  -p 127.0.0.1:8501:8501 \
  -e "ES_SERVER=$ES_SERVER" \
  quay.io/msheth/orion-newspaper:v1
```

Open http://localhost:8501

## Project structure

```
app.py                  # Router — st.navigation between pages
shared_rendering.py     # Shared CSS, constants, CATEGORIES, render helpers
orion_runner.py         # Backend — command building, subprocess execution, output parsing
pages/
  executive_summary.py  # Aggregated regression view across all configs
  newspaper.py          # Auto-refreshing grid with categorized configs and drill-down
  trends.py             # Long-term metric trends with weekly granularity
  metrics.py            # Metric correlation matrix across configs and versions
  manual.py             # Single-config manual execute with custom YAML editor
  about.py              # Environment info, repo links, security notes
tests/
  conftest.py           # Shared test fixtures
  test_orion_runner.py  # Unit + integration tests for orion_runner.py
kustomize/              # OpenShift deployment manifests
```

## Newspaper categories

| Category | Subcategory | Configs |
|----------|-------------|---------|
| Core | 6 nodes (TRT payload) | cluster-density, node-density, node-density-cni, udn-l2 |
| Core | 24 nodes (small scale) | cluster-density, node-density, node-density-cni, udn-l2, udn-l3 |
| Core | 120 nodes (med scale) | cluster-density, node-density, node-density-cni, udn-l2 |
| Core | 252 nodes (large scale) | cluster-density, node-density, node-density-cni, udn-l2 |
| Virt | — | metal-perfscale-cpt-virt-density |
| Telco | — | trt-external-payload-node-density |
| HCP | — | trt-external-payload-node-density |

Categories are defined in `shared_rendering.py` (`CATEGORIES` list).

## Development

```bash
make run          # start locally (clones orion repo if needed)
make test         # run tests (35 tests, 92% coverage)
make lint         # ruff check + format
make build        # podman build
make push TAG=v1  # build + push to quay
make clean        # remove container + temp files
```

## Security

- ES_SERVER is passed at runtime via env var — **never baked into the image**
- ES_SERVER is scrubbed from all UI output and subprocess output at capture point
- The subprocess receives a minimal environment (PATH, HOME, ES_SERVER, index vars)
- All user-influenced values are HTML-escaped before rendering
- Path traversal protection on config file resolution
- ES index presets (no free-form index input on batch pages)
- Non-root container (UID 1001)
- Default run command binds host port to `127.0.0.1` — no external exposure
- For OpenShift: injected via K8s Secret, ClusterIP only (no Route)
