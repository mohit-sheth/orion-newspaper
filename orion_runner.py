import fcntl
import glob
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from typing import Any

import pandas as pd
import streamlit as st
import yaml

logger = logging.getLogger("orion_newspaper")

ORION_DIR = os.environ.get("ORION_DIR", "/app/orion-venv")
ORION_BIN = os.path.join(ORION_DIR, "bin", "orion")
ORION_EXAMPLES_DIR = os.environ.get("ORION_EXAMPLES_DIR", "/orion/examples")

ORION_RUN_TIMEOUT = int(os.environ.get("ORION_RUN_TIMEOUT", "600"))
# NOTE: File lock is per-pod. With multiple replicas, each pod enforces its own
# limit. For the current scale (~5 users) this is acceptable.
ORION_LOCK_FILE = os.environ.get("ORION_LOCK_FILE", "/tmp/orion_run.lock")

ALGORITHM_FLAGS: dict[str, str] = {
    "hunter-analyze": "--hunter-analyze",
    "anomaly-detection": "--anomaly-detection",
    "cmr": "--cmr",
    "filter": "--filter",
}

# --- Config discovery ---

@st.cache_data(ttl=300)
def discover_configs() -> list[str]:
    pattern = os.path.join(ORION_EXAMPLES_DIR, "*.yaml")
    return sorted(os.path.basename(f) for f in glob.glob(pattern))


def get_config_path(config_name: str) -> str:
    return os.path.join(ORION_EXAMPLES_DIR, config_name)


def _load_config_yaml(config_name: str) -> "list[dict] | None":
    """Load and parse a config YAML, handling Jinja templates. Returns tests list or None."""
    path = get_config_path(config_name)
    try:
        with open(path) as f:
            raw = f.read()
        cleaned = re.sub(r'"?\{\{.*?\}\}"?', "__tpl__", raw)
        data = yaml.safe_load(cleaned)
    except Exception:
        logger.warning("Failed to parse config %s", config_name, exc_info=True)
        return None

    if not data:
        return None
    return data.get("tests", [])


def get_config_metadata(config_name: str) -> dict[str, Any]:
    tests = _load_config_yaml(config_name)
    if tests is None:
        return {"test_count": 0, "test_names": [], "metric_count": 0}

    return {
        "test_count": len(tests),
        "test_names": [t.get("name", "unnamed") for t in tests],
        "metric_count": sum(len(t.get("metrics", [])) for t in tests),
    }


@st.cache_data(ttl=300)
def get_config_metrics(config_name: str) -> dict[str, list[str]]:
    """Return {test_name: [metric_name, ...]} for a config."""
    tests = _load_config_yaml(config_name)
    if tests is None:
        return {}

    return {
        t.get("name", "unnamed"): [m.get("name", "unnamed") for m in t.get("metrics", [])]
        for t in tests
    }


def get_metrics_for_configs(config_names: list[str]) -> dict[str, list[tuple[str, str]]]:
    """Return {metric_name: [(config_name, test_name), ...]} — reverse index."""
    index: dict[str, list[tuple[str, str]]] = {}
    for config_name in config_names:
        for test_name, metrics in get_config_metrics(config_name).items():
            for metric in metrics:
                index.setdefault(metric, []).append((config_name, test_name))
    return index


# --- Command building ---

def create_temp_dir() -> str:
    return tempfile.mkdtemp(prefix="orion_run_")


def build_command(params: dict[str, Any]) -> tuple[list[str], dict[str, str], str]:
    temp_dir = params["temp_dir"]

    cmd = [ORION_BIN, "--config", params["config_path"]]

    algo_flag = ALGORITHM_FLAGS.get(params.get("algorithm", ""))
    if algo_flag:
        cmd.append(algo_flag)

    if params.get("lookback"):
        cmd.extend(["--lookback", params["lookback"]])

    if params.get("node_count"):
        cmd.extend(["--node-count", "true"])

    input_vars = {}
    if params.get("version"):
        input_vars["version"] = params["version"]
    if params.get("extra_input_vars"):
        input_vars.update(params["extra_input_vars"])
    if input_vars:
        cmd.extend(["--input-vars", json.dumps(input_vars)])

    cmd.extend(["--save-output-path", os.path.join(temp_dir, "output.txt")])
    cmd.extend(["--save-data-path", os.path.join(temp_dir, "data.csv")])
    cmd.append("--viz")

    if params.get("uuid"):
        cmd.extend(["--uuid", params["uuid"]])
    if params.get("baseline"):
        cmd.extend(["--baseline", params["baseline"]])
    if params.get("display"):
        cmd.extend(["--display", params["display"]])
    if params.get("debug"):
        cmd.append("--debug")
    if params.get("sippy_pr_search"):
        cmd.append("--sippy-pr-search")

    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/root"),
        "PYTHONUNBUFFERED": "1",
    }
    # ES_SERVER is always read from the process environment, never from user params
    es_server = os.environ.get("ES_SERVER", "")
    if es_server:
        env["ES_SERVER"] = es_server
    if params.get("benchmark_index"):
        env["es_benchmark_index"] = params["benchmark_index"]
    if params.get("metadata_index"):
        env["es_metadata_index"] = params["metadata_index"]

    return cmd, env, ORION_DIR


def humanize_command(cmd: list[str]) -> str:
    parts = []
    skip_next = False
    for i, arg in enumerate(cmd):
        if skip_next:
            skip_next = False
            continue
        if arg == cmd[0]:
            parts.append("orion")
        elif arg == "--config":
            skip_next = True
            parts.append(f"--config {os.path.basename(cmd[i + 1])}")
        elif arg in ("--save-output-path", "--save-data-path"):
            skip_next = True
        elif arg == "--input-vars":
            skip_next = True
            parts.append(f"--input-vars '{cmd[i + 1]}'")
        elif arg == "--viz":
            pass
        else:
            parts.append(arg)
    return " \\\n  ".join(parts)

# --- Rate limiting ---

def _acquire_run_lock() -> "int | None":
    try:
        fd = os.open(ORION_LOCK_FILE, os.O_CREAT | os.O_WRONLY, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except (OSError, IOError):
        return None


def _release_run_lock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    except OSError:
        pass

# --- Subprocess execution ---

def _parse_log_message(line: str) -> "tuple[str, str] | None":
    m = re.match(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+ - \w+\s+- (\w+) - file: \S+ - line: \d+ - (.+)",
        line,
    )
    if m:
        return m.group(1), m.group(2).strip()
    return None


def run_orion(
    cmd: list[str],
    env: dict[str, str],
    cwd: str,
    status_container: Any,
    progress_bar: Any,
    metric_total: int,
    timeout: int = ORION_RUN_TIMEOUT,
) -> tuple[int, str, list[tuple[str, str]]]:
    config_name = "unknown"
    for i, arg in enumerate(cmd):
        if arg == "--config" and i + 1 < len(cmd):
            config_name = os.path.basename(cmd[i + 1])
            break

    lock_fd = _acquire_run_lock()
    if lock_fd is None:
        logger.warning("orion_run_blocked config=%s reason=concurrent_run", config_name)
        return -1, "Another orion run is already in progress. Please wait and try again.", []

    logger.info("orion_run_start config=%s timeout=%d", config_name, timeout)
    t0 = time.monotonic()

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=cwd,
            text=True,
            bufsize=1,
        )

        all_lines: list[str] = []
        log_messages: list[tuple[str, str]] = []
        metrics_collected = 0
        deadline = t0 + timeout

        for line in iter(process.stdout.readline, ""):
            if time.monotonic() > deadline:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)
            all_lines.append(line)

            parsed = _parse_log_message(line)
            if parsed:
                level, msg = parsed
                log_messages.append((level, msg))

                if "Collecting " in msg:
                    metrics_collected += 1
                    metric_name = msg.replace("Collecting ", "")
                    if metric_total > 0:
                        pct = min(metrics_collected / metric_total, 0.95)
                        label = f"Collecting {metric_name} ({metrics_collected}/{metric_total})"
                        progress_bar.progress(pct, text=label)
                    else:
                        status_container.text(f"Collecting {metric_name}...")
                elif "Starting Orion" in msg:
                    progress_bar.progress(0.02, text="Starting Orion...")
                elif "ACK" in msg and "loaded" in msg.lower():
                    progress_bar.progress(0.05, text="Config loaded")
                elif "test " in msg.lower() and "started" in msg.lower():
                    progress_bar.progress(0.08, text="Querying Elasticsearch...")
                elif "Regression" in line:
                    progress_bar.progress(0.98, text="Analyzing changepoints...")

        process.wait(timeout=max(0, deadline - time.monotonic()))
        elapsed = time.monotonic() - t0
        progress_bar.progress(1.0, text="Complete")
        logger.info(
            "orion_run_end config=%s return_code=%d duration=%.1fs metrics=%d",
            config_name, process.returncode, elapsed, metrics_collected,
        )
        return process.returncode, "".join(all_lines), log_messages

    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        elapsed = time.monotonic() - t0
        error_msg = f"Orion run timed out after {timeout}s"
        logger.error("orion_run_timeout config=%s timeout=%d duration=%.1fs", config_name, timeout, elapsed)
        progress_bar.progress(1.0, text="Timed out")
        return -1, error_msg, []

    finally:
        _release_run_lock(lock_fd)

# --- Output parsing ---

def parse_csv_data(temp_dir: str) -> list[tuple[str, "pd.DataFrame"]]:
    csv_files = sorted(glob.glob(os.path.join(temp_dir, "data*.csv")))
    results = []
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            if not df.empty:
                name = os.path.basename(csv_file)
                name = re.sub(r"^data[-_]?", "", name).replace(".csv", "")
                results.append((name, df))
        except Exception:
            logger.warning("Failed to parse CSV %s", csv_file, exc_info=True)
            continue
    return results


def find_viz_html(temp_dir: str) -> list[str]:
    return sorted(glob.glob(os.path.join(temp_dir, "*_viz.html")))


def extract_regressions(raw_output: str) -> list[dict[str, str]]:
    regressions = []
    lines = raw_output.split("\n")
    i = 0
    while i < len(lines):
        if "Regression(s) found" in lines[i]:
            prev_ver = None
            bad_ver = None
            for j in range(i + 1, min(i + 20, len(lines))):
                line = lines[j]
                match_prev = re.match(r"\s*Previous Version:\s*(.*)", line)
                match_bad = re.match(r"\s*Bad Version:\s*(.*)", line)
                if match_prev:
                    prev_ver = match_prev.group(1).strip()
                if match_bad:
                    bad_ver = match_bad.group(1).strip()
                if prev_ver and bad_ver:
                    regressions.append({"prev_ver": prev_ver, "bad_ver": bad_ver})
                    prev_ver = None
                    bad_ver = None
        i += 1
    return regressions
