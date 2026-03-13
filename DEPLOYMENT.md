# Deployment

## Pre-built image

```bash
podman run -d --name orion-newspaper \
  -p 127.0.0.1:8501:8501 \
  -e "ES_SERVER=$ES_SERVER" \
  quay.io/msheth/orion-newspaper:latest
```

Open http://localhost:8501

## Local dev

Prerequisites: Python 3.11+

```bash
git clone https://github.com/mohit-sheth/orion-newspaper.git && cd orion-newspaper
git clone https://github.com/cloud-bulldozer/orion.git /tmp/orion

python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt /tmp/orion plotly

export ES_SERVER="https://your-es-server:9200"
export ORION_DIR=$(pwd)/venv
export ORION_EXAMPLES_DIR=/tmp/orion/examples
streamlit run app.py
```

Open http://localhost:8501

## Build from source

```bash
podman build -t orion-newspaper .
podman run -d --name orion-newspaper \
  -p 127.0.0.1:8501:8501 \
  -e "ES_SERVER=$ES_SERVER" \
  orion-newspaper
```

Manage:

```bash
podman logs -f orion-newspaper       # view logs
podman stop orion-newspaper           # stop
podman rm -f orion-newspaper          # remove
```

## OpenShift (kustomize)

```bash
# Set ES_SERVER
echo "ES_SERVER=https://your-es-server:9200" > kustomize/base/.env

# Set quay pull secret (if private registry)
export QUAY_CRED=$(base64 -w0 < ~/.docker/config.json)
envsubst < kustomize/base/secret-quay.yaml | oc apply -f -

# Deploy
oc apply -k kustomize/base/

# Access
oc port-forward -n orion-newspaper svc/orion-newspaper 8501:8501
```

Creates: namespace, Deployment, ClusterIP Service (no Route), ImageStream, K8s Secret.

## Configuration

| Setting | Required | Description |
|---|---|---|
| `ES_SERVER` | Yes | Elasticsearch/OpenSearch endpoint URL |
| `ORION_DIR` | No | Path to orion venv (default: `/app/orion-venv`, override for local dev) |
| `ORION_EXAMPLES_DIR` | No | Path to orion examples (default: `/orion/examples`, override for local dev) |
| `PORT` | No | Streamlit port (default: `8501`) |

Benchmark and metadata indexes are configurable in the Manual Execute sidebar (defaults: `ripsaw-kube-burner-*`, `perf_scale_ci*`).
