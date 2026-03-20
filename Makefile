.PHONY: run test lint build push clean stop

IMAGE ?= quay.io/msheth/orion-newspaper
TAG ?= latest

run:
	# TODO: Switch back to cloud-bulldozer/orion once add-configs-med-large is merged
	# Original: git clone https://github.com/cloud-bulldozer/orion.git /tmp/orion
	@rm -rf /tmp/orion
	@echo "Cloning orion repo..."
	@git clone -b add-configs-med-large https://github.com/mohit-sheth/orion.git /tmp/orion
	@echo "Starting locally..."
	ORION_DIR=$$(pwd)/venv ORION_EXAMPLES_DIR=/tmp/orion/examples \
		./venv/bin/streamlit run app.py --server.headless true --server.port 8501 --server.address 127.0.0.1

test:
	./venv/bin/python -m pytest tests/ -v

lint:
	./venv/bin/python -m ruff check .
	./venv/bin/python -m ruff format --check .

build:
	podman build -t orion-newspaper .

push: build
	podman tag orion-newspaper $(IMAGE):$(TAG)
	podman push $(IMAGE):$(TAG)

stop:
	@lsof -ti :8501 | xargs -r kill 2>/dev/null && echo "Stopped" || echo "Not running"

clean: stop
	podman rm -f orion-newspaper 2>/dev/null || true
	rm -rf .coverage .pytest_cache __pycache__ tests/__pycache__
