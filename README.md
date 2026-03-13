# Orion Newspaper

Web UI for [cloud-bulldozer/orion](https://github.com/cloud-bulldozer/orion) — performance regression detection for OCP from your browser.

## Features

**Newspaper** (default) — a morning dashboard for perfscale engineers.
- Auto-refreshing grid of monitored configs grouped by category (Core, Virt, Telco, HCP)
- Status at a glance: green (OK), yellow (regression), red (error) per config
- Drill into any config for full results, interactive Plotly visualizations, and logs
- Auto-refreshes every 15 minutes after the first manual run

**Manual Execute** — full control over a single analysis run.
- Pick any config, algorithm (hunter-analyze, anomaly-detection, CMR), lookback, and OCP version
- Compare specific UUIDs, adjust baselines, enable Sippy PR search
- Custom Config: paste your own YAML config with syntax-highlighted editor
- Real-time progress with metric-level updates

**Metric Correlation** — cross-config regression confidence.
- Select a metric (e.g. `ovsCPU-Workers`) and multiple OCP versions
- Runs all configs in the category that contain that metric
- Shows a correlation matrix: config × version → regression status
- Confidence indicator: if multiple configs regress on the same metric, it's likely real

**About** — environment info, repo links, category breakdown, security notes.

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
shared_rendering.py     # Shared CSS, constants, CATEGORIES, render_results()
orion_runner.py         # Backend — command building, subprocess execution, output parsing
pages/
  newspaper.py          # Auto-refreshing grid with categorized configs and drill-down
  manual.py             # Single-config manual execute with custom YAML editor
  metrics.py            # Metric correlation matrix across configs and versions
  about.py              # Environment info, repo links, security notes
tests/
  conftest.py           # Shared test fixtures
  test_orion_runner.py  # Unit + integration tests for orion_runner.py
kustomize/              # OpenShift deployment manifests
```

## Newspaper categories

| Category | Configs |
|----------|---------|
| Core | cluster-density, node-density, node-density-cni, udn-l2, virt-density |
| Virt | node-density (placeholder) |
| Telco | node-density (placeholder) |
| HCP | node-density (placeholder) |

Categories are defined in `shared_rendering.py` (`CATEGORIES` list).

## Development

```bash
make run          # start locally
make test         # run tests (16 tests, 93% coverage)
make lint         # ruff check + format
make build        # podman build
make push TAG=v2  # build + push to quay
make clean        # remove container + temp files
```

## Security

- ES_SERVER is passed at runtime via env var — **never baked into the image**
- ES_SERVER is scrubbed from all UI output (shown as `***`)
- The subprocess receives a minimal environment (PATH, HOME, ES_SERVER, index vars)
- All user-influenced values are HTML-escaped before rendering
- Index patterns validated against allowlist before use
- Non-root container (UID 1001)
- Default run command binds host port to `127.0.0.1` — no external exposure
- For OpenShift: injected via K8s Secret, ClusterIP only (no Route)
