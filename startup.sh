#!/bin/bash

STREAMLIT_PID=

cleanup() {
    if [ -n "$STREAMLIT_PID" ]; then
        kill -TERM "$STREAMLIT_PID" 2>/dev/null
        wait "$STREAMLIT_PID" 2>/dev/null
    fi
    exit 0
}

trap cleanup SIGTERM SIGINT SIGQUIT

streamlit run /app/newspaper/app.py \
    --server.headless true \
    --server.port "${PORT:-8501}" \
    --server.address 0.0.0.0 &

STREAMLIT_PID=$!
wait "$STREAMLIT_PID"
