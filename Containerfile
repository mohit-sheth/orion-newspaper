# ============================================================
# Stage 1: Build stage - compile and install dependencies
# ============================================================
FROM python:3.11.8-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Clone Orion repository (latest)
RUN git clone --depth 1 https://github.com/cloud-bulldozer/orion /app/orion-repo

# Create and populate Orion virtual environment
RUN python -m venv /app/orion-venv
RUN /app/orion-venv/bin/pip install --no-cache-dir --upgrade pip setuptools && \
    /app/orion-venv/bin/pip install --no-cache-dir -r /app/orion-repo/requirements.txt && \
    /app/orion-venv/bin/pip install --no-cache-dir /app/orion-repo && \
    /app/orion-venv/bin/pip install --no-cache-dir pandas plotly

# Copy examples
RUN mkdir -p /orion && cp -r /app/orion-repo/examples /orion/examples

# ============================================================
# Stage 2: Runtime stage - minimal final image
# ============================================================
FROM python:3.11.8-slim-bookworm

ENV PYTHONUNBUFFERED="1"

# Copy Orion venv and examples from builder
COPY --from=builder /app/orion-venv /app/orion-venv
COPY --from=builder /orion/examples /orion/examples

# Install newspaper dependencies
WORKDIR /app/newspaper
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy newspaper code
COPY app.py orion_runner.py shared_rendering.py ./
COPY pages/ pages/
COPY .streamlit .streamlit/
COPY startup.sh /app/startup.sh
RUN chmod +x /app/startup.sh

# Create non-root user
RUN useradd -u 1001 -m appuser && \
    chown -R appuser:appuser /app
USER 1001

EXPOSE 8501

ENTRYPOINT ["/app/startup.sh"]
