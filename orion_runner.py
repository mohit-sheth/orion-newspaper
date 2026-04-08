import fcntl
import glob
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
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

DEFAULT_BENCHMARK_INDEX = "ripsaw-kube-burner-*"
DEFAULT_METADATA_INDEX = "perf_scale_ci*"

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
    resolved = os.path.realpath(os.path.join(ORION_EXAMPLES_DIR, config_name))
    if not resolved.startswith(os.path.realpath(ORION_EXAMPLES_DIR)):
        raise ValueError("Invalid config path")
    return resolved


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


def _full_metric_name(metric: dict) -> str:
    """Build the full metric name as orion outputs it.

    Standard metrics: {name}_{metric_of_interest} (e.g., podReadyLatency_P99)
    Aggregated metrics: {name}_{agg_type} (e.g., ovnMem-ovncontroller_avg)
    """
    name = metric.get("name", "unnamed")
    agg = metric.get("agg")
    if agg and "agg_type" in agg:
        return f"{name}_{agg['agg_type']}"
    moi = metric.get("metric_of_interest", "")
    return f"{name}_{moi}" if moi else name


@st.cache_data(ttl=300)
def get_config_metrics(config_name: str) -> dict[str, list[str]]:
    """Return {test_name: [metric_name, ...]} for a config.

    Metric names include the metric_of_interest suffix (e.g., podReadyLatency_P99)
    to match orion's JSON output column names.
    """
    tests = _load_config_yaml(config_name)
    if tests is None:
        return {}

    return {t.get("name", "unnamed"): [_full_metric_name(m) for m in t.get("metrics", [])] for t in tests}


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

    if params.get("since"):
        cmd.extend(["--since", params["since"]])

    if params.get("node_count"):
        cmd.extend(["--node-count", "true"])

    input_vars = {}
    if params.get("version"):
        input_vars["version"] = params["version"]
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
        "PROW_JOB_ID": "orion-newspaper",
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
        elif arg == "--config" and i + 1 < len(cmd):
            skip_next = True
            parts.append(f"--config {os.path.basename(cmd[i + 1])}")
        elif arg in ("--save-output-path", "--save-data-path"):
            skip_next = True
        elif arg == "--input-vars" and i + 1 < len(cmd):
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
            config_name,
            process.returncode,
            elapsed,
            metrics_collected,
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


def extract_regressions_json(temp_dir: str) -> list[dict[str, Any]]:
    """Parse saved JSON output files to extract rich regression data.

    Returns list of dicts with keys:
        test_name, metric, percentage_change, prev_value, bad_value, prev_ver, bad_ver
    """
    if not temp_dir:
        return []

    json_files = sorted(glob.glob(os.path.join(temp_dir, "output_*.json")))
    regressions: list[dict[str, Any]] = []

    for json_file in json_files:
        # Test name is encoded in the filename: output_<testname>.json
        basename = os.path.basename(json_file)
        test_name = re.sub(r"^output_", "", basename).replace(".json", "")

        try:
            with open(json_file) as f:
                data = json.load(f)
        except Exception:
            logger.warning("Failed to parse JSON %s", json_file, exc_info=True)
            continue

        if not isinstance(data, list):
            continue

        # Walk through data points looking for changepoints
        prev_entry = None
        for entry in data:
            if entry.get("is_changepoint"):
                metrics = entry.get("metrics", {})
                for metric_name, metric_data in metrics.items():
                    pct = metric_data.get("percentage_change", 0)
                    if pct == 0:
                        continue
                    bad_ver = entry.get("ocpVersion", entry.get("build", ""))
                    bad_value = metric_data.get("value", "")
                    prev_ver = ""
                    prev_value = ""
                    if prev_entry:
                        prev_ver = prev_entry.get("ocpVersion", prev_entry.get("build", ""))
                        prev_metric = prev_entry.get("metrics", {}).get(metric_name, {})
                        prev_value = prev_metric.get("value", "")
                    regressions.append(
                        {
                            "test_name": test_name,
                            "metric": metric_name,
                            "percentage_change": round(pct, 2),
                            "prev_value": prev_value,
                            "bad_value": bad_value,
                            "prev_ver": str(prev_ver),
                            "bad_ver": str(bad_ver),
                            "prs": entry.get("prs", []),
                        }
                    )
            prev_entry = entry

    # Sort by absolute percentage change descending (most severe first)
    regressions.sort(key=lambda r: abs(r["percentage_change"]), reverse=True)
    return regressions


def extract_metrics_json(temp_dir: str) -> list[dict[str, Any]]:
    """Parse saved JSON output files to extract per-run metric values.

    Returns list of dicts with keys: uuid, timestamp, and one key per metric name.
    Each dict represents one run/data point.
    """
    if not temp_dir:
        return []

    json_files = sorted(glob.glob(os.path.join(temp_dir, "output_*.json")))
    runs: list[dict[str, Any]] = []

    for json_file in json_files:
        try:
            with open(json_file) as f:
                data = json.load(f)
        except Exception:
            logger.warning("Failed to parse JSON %s", json_file, exc_info=True)
            continue

        if not isinstance(data, list):
            continue

        for entry in data:
            row: dict[str, Any] = {
                "uuid": entry.get("uuid", ""),
                "timestamp": entry.get("timestamp", ""),
            }
            for metric_name, metric_data in entry.get("metrics", {}).items():
                if isinstance(metric_data, dict):
                    row[metric_name] = metric_data.get("value")
                else:
                    row[metric_name] = metric_data
            runs.append(row)

    return runs


# --- Shared execution helpers ---


class NoOpTracker:
    """No-op progress/status tracker for batch runs that manage their own progress."""

    def progress(self, pct, text=""):
        pass

    def text(self, t):
        pass


def execute_config(
    config_name,
    version,
    lookback,
    since="",
    algorithm="hunter-analyze",
    benchmark_index="",
    metadata_index="",
    status_tracker=None,
    progress_tracker=None,
    metric_total=0,
    prev_temp_dir=None,
):
    """Run orion for a single config and return a standardized result dict.

    Defaults to hunter-analyze algorithm. Pass algorithm="filter" for faster runs
    that skip changepoint detection (useful for trend data collection).

    Handles temp dir lifecycle, command building, error handling with ES_SERVER scrubbing.
    Callers can augment the returned dict with extra fields (e.g. regressions, n_runs).
    """
    if prev_temp_dir and os.path.exists(prev_temp_dir):
        shutil.rmtree(prev_temp_dir, ignore_errors=True)

    temp_dir = create_temp_dir()
    params = {
        "config_path": get_config_path(config_name),
        "algorithm": algorithm,
        "lookback": lookback,
        "since": since,
        "version": version,
        "benchmark_index": benchmark_index or os.environ.get("es_benchmark_index", DEFAULT_BENCHMARK_INDEX),
        "metadata_index": metadata_index or os.environ.get("es_metadata_index", DEFAULT_METADATA_INDEX),
        "node_count": False,
        "debug": False,
        "sippy_pr_search": True,
        "temp_dir": temp_dir,
    }

    cmd, env, cwd = build_command(params)
    cmd_display = humanize_command(cmd)

    _tracker = NoOpTracker()
    if status_tracker is None:
        status_tracker = _tracker
    if progress_tracker is None:
        progress_tracker = _tracker

    try:
        t0 = time.monotonic()
        return_code, full_output, log_messages = run_orion(
            cmd,
            env,
            cwd,
            status_tracker,
            progress_tracker,
            metric_total,
        )
        elapsed = time.monotonic() - t0
        n_metrics = sum(1 for _, msg in log_messages if "Collecting " in msg)

        # Scrub ES_SERVER from subprocess output at capture point
        _es = os.environ.get("ES_SERVER", "")
        if _es and _es in full_output:
            full_output = full_output.replace(_es, "***")

        return {
            "return_code": return_code,
            "full_output": full_output,
            "n_metrics": n_metrics,
            "temp_dir": temp_dir,
            "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration": elapsed,
            "cmd_display": cmd_display,
        }
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        _es = os.environ.get("ES_SERVER", "")
        sanitized = str(e).replace(_es, "***") if _es else str(e)
        return {
            "return_code": -1,
            "full_output": sanitized,
            "n_metrics": 0,
            "temp_dir": None,
            "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration": 0,
            "cmd_display": "",
        }


# --- Trend analysis helpers ---


def generate_date_windows(months_back: int = 6) -> list[tuple[str, str]]:
    """Generate (since_date, lookback) pairs for monthly windows going back from today.

    Returns list of tuples like [("2026-03-18", "30d"), ("2026-02-16", "30d"), ...].
    Ordered from oldest to newest.
    """
    today = datetime.now()
    windows = []
    for i in range(months_back):
        since = today - timedelta(days=30 * i)
        windows.append((since.strftime("%Y-%m-%d"), "30d"))
    windows.reverse()
    return windows


def aggregate_weekly_trends(
    monthly_json_data: list[tuple[str, list[dict[str, Any]]]],
    metrics: list[str],
    agg_func: str = "median",
) -> "pd.DataFrame":
    """Aggregate monthly JSON data into weekly trend data points.

    Args:
        monthly_json_data: list of (since_date, extract_metrics_json result) pairs
        metrics: metric column names to aggregate
        agg_func: "median" or "mean"

    Returns:
        DataFrame with columns: week_start, n_runs, plus one column per metric.
        Sorted by week_start ascending.
    """
    all_rows = []
    for _since_date, runs in monthly_json_data:
        all_rows.extend(runs)

    if not all_rows:
        return pd.DataFrame(columns=["week_start", "n_runs"] + metrics)

    combined = pd.DataFrame(all_rows)
    if "timestamp" not in combined.columns:
        return pd.DataFrame(columns=["week_start", "n_runs"] + metrics)

    # Handle both unix timestamps (int/float) and ISO strings
    ts = combined["timestamp"]
    if ts.dtype in ("int64", "float64"):
        combined["timestamp"] = pd.to_datetime(ts, unit="s", errors="coerce")
    else:
        combined["timestamp"] = pd.to_datetime(ts, errors="coerce")
    combined = combined.dropna(subset=["timestamp"])

    if combined.empty:
        return pd.DataFrame(columns=["week_start", "n_runs"] + metrics)

    # Drop duplicate UUIDs (overlapping monthly windows may fetch same run)
    if "uuid" in combined.columns:
        combined = combined.drop_duplicates(subset=["uuid"])

    # Group by ISO year-week
    combined["_year"] = combined["timestamp"].dt.isocalendar().year
    combined["_week"] = combined["timestamp"].dt.isocalendar().week
    grouped = combined.groupby(["_year", "_week"])

    rows = []
    agg = "median" if agg_func == "median" else "mean"
    for (year, week), group in grouped:
        # Monday of that ISO week
        week_start = datetime.strptime(f"{year}-W{week:02d}-1", "%G-W%V-%u")
        row: dict[str, Any] = {
            "_sort_key": week_start.strftime("%Y-%m-%d"),
            "week_start": week_start.strftime("%b %d"),
            "n_runs": len(group),
        }
        for m in metrics:
            if m in group.columns:
                row[m] = getattr(group[m], agg)()
            else:
                row[m] = None
        rows.append(row)

    result = pd.DataFrame(rows)
    result = result.sort_values("_sort_key").reset_index(drop=True)
    return result.drop(columns=["_sort_key"])
