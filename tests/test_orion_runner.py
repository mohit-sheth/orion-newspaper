import json
import os
from unittest.mock import MagicMock, patch

import orion_runner
from orion_runner import (
    build_command,
    humanize_command,
    _parse_log_message,
    extract_regressions,
    discover_configs,
    get_config_metadata,
    get_config_metrics,
    get_metrics_for_configs,
    parse_csv_data,
    find_viz_html,
    run_orion,
    _acquire_run_lock,
    _release_run_lock,
)


def _base_params(tmp_path, **overrides):
    params = {
        "config_path": "/fake/examples/test.yaml",
        "algorithm": "hunter-analyze",
        "lookback": "",
        "node_count": False,
        "version": "",
        "benchmark_index": "",
        "metadata_index": "",
        "uuid": "",
        "baseline": "",
        "display": "",
        "debug": False,
        "sippy_pr_search": False,
        "temp_dir": str(tmp_path),
    }
    params.update(overrides)
    return params


# --- test_build_command_flags ---

def test_build_command_flags(tmp_path):
    params = _base_params(
        tmp_path,
        algorithm="anomaly-detection",
        lookback="30d",
        node_count=True,
        version="4.18",
        debug=True,
        sippy_pr_search=True,
        uuid="abc-123",
        baseline="def-456",
        display="buildUrl",
    )
    cmd, env, cwd = build_command(params)

    assert "--anomaly-detection" in cmd
    assert "--lookback" in cmd and cmd[cmd.index("--lookback") + 1] == "30d"
    assert "--node-count" in cmd
    assert "--debug" in cmd
    assert "--sippy-pr-search" in cmd
    assert "--uuid" in cmd and cmd[cmd.index("--uuid") + 1] == "abc-123"
    assert "--baseline" in cmd and cmd[cmd.index("--baseline") + 1] == "def-456"
    assert "--display" in cmd
    assert "--viz" in cmd

    # version goes into --input-vars as JSON
    iv_idx = cmd.index("--input-vars")
    iv_json = json.loads(cmd[iv_idx + 1])
    assert iv_json["version"] == "4.18"


# --- test_build_command_env ---

def test_build_command_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ES_SERVER", "https://es:9200")
    params = _base_params(
        tmp_path,
        benchmark_index="ripsaw-*",
        metadata_index="perf_ci*",
    )
    _, env, _ = build_command(params)

    assert env["ES_SERVER"] == "https://es:9200"
    assert env["es_benchmark_index"] == "ripsaw-*"
    assert env["es_metadata_index"] == "perf_ci*"
    assert env["PYTHONUNBUFFERED"] == "1"


def test_build_command_env_no_es_server(tmp_path, monkeypatch):
    monkeypatch.delenv("ES_SERVER", raising=False)
    params = _base_params(tmp_path)
    _, env, _ = build_command(params)

    assert "ES_SERVER" not in env


# --- test_humanize_command ---

def test_humanize_command(tmp_path):
    cmd = [
        "/app/orion-venv/bin/orion",
        "--config", "/orion/examples/test.yaml",
        "--hunter-analyze",
        "--lookback", "15d",
        "--save-output-path", str(tmp_path / "output.txt"),
        "--save-data-path", str(tmp_path / "data.csv"),
        "--viz",
        "--input-vars", '{"version": "4.18"}',
    ]
    result = humanize_command(cmd)

    assert result.startswith("orion")
    assert "--config test.yaml" in result
    assert "--save-output-path" not in result
    assert "--save-data-path" not in result
    assert "--viz" not in result
    assert "--input-vars" in result
    assert "4.18" in result


# --- test_parse_log_message ---

def test_parse_log_message():
    valid = "2024-03-01 12:00:00,123 - orion - INFO - file: foo.py - line: 42 - Starting Orion"
    assert _parse_log_message(valid) == ("INFO", "Starting Orion")

    warning = "2024-03-01 12:00:00,123 - orion - WARNING - file: foo.py - line: 10 - Something odd"
    assert _parse_log_message(warning) == ("WARNING", "Something odd")

    assert _parse_log_message("some random output") is None
    assert _parse_log_message("") is None


# --- test_extract_regressions ---

def test_extract_regressions():
    assert extract_regressions("All good\nNo issues") == []

    output = (
        "Some output\n"
        "Regression(s) found\n"
        "  Previous Version: 4.17.0\n"
        "  Bad Version: 4.18.0\n"
        "More output\n"
    )
    result = extract_regressions(output)
    assert len(result) == 1
    assert result[0] == {"prev_ver": "4.17.0", "bad_ver": "4.18.0"}

    multi = (
        "Regression(s) found\n"
        "  Previous Version: 4.16\n"
        "  Bad Version: 4.17\n"
        "  Previous Version: 4.17\n"
        "  Bad Version: 4.18\n"
    )
    assert len(extract_regressions(multi)) == 2


# --- test_discover_and_metadata ---

def test_discover_and_metadata(tmp_examples_dir):
    # Clear the cache before testing
    discover_configs.clear()
    configs = discover_configs()
    assert configs == ["simple.yaml"]

    meta = get_config_metadata("simple.yaml")
    assert meta["test_count"] == 2
    assert meta["metric_count"] == 4
    assert "test-one" in meta["test_names"]
    assert "test-two" in meta["test_names"]


# --- test_parse_csv_and_viz ---

def test_parse_csv_and_viz(tmp_data_dir):
    results = parse_csv_data(str(tmp_data_dir))
    assert len(results) == 1
    name, df = results[0]
    assert len(df) == 3
    assert "uuid" in df.columns

    viz = find_viz_html(str(tmp_data_dir))
    assert len(viz) == 1
    assert viz[0].endswith("example_viz.html")

    empty = parse_csv_data("/nonexistent")
    assert empty == []

    empty_viz = find_viz_html("/nonexistent")
    assert empty_viz == []


# --- test_run_orion_subprocess ---

class FakeProgressBar:
    def __init__(self):
        self.calls = []
    def progress(self, pct, text=""):
        self.calls.append((pct, text))


class FakeStatusContainer:
    def __init__(self):
        self.texts = []
    def text(self, t):
        self.texts.append(t)


def test_run_orion_subprocess(tmp_path):
    lines = [
        "2024-03-01 12:00:00,123 - orion - INFO - file: main.py - line: 1 - Starting Orion\n",
        "2024-03-01 12:00:01,456 - orion - INFO - file: run.py - line: 50 - Collecting throughput\n",
        "2024-03-01 12:00:02,789 - orion - INFO - file: run.py - line: 50 - Collecting latency\n",
        "plain output line\n",
    ]

    mock_process = MagicMock()
    mock_process.stdout.readline.side_effect = lines + [""]
    mock_process.wait.return_value = None
    mock_process.returncode = 0

    progress = FakeProgressBar()
    status = FakeStatusContainer()

    lock_file = str(tmp_path / "test_run.lock")
    with patch("orion_runner.subprocess.Popen", return_value=mock_process), \
         patch("orion_runner.ORION_LOCK_FILE", lock_file):
        rc, output, log_messages = run_orion(
            ["orion", "--config", "test.yaml"],
            {}, "/tmp", status, progress, metric_total=2,
        )

    assert rc == 0
    assert "Starting Orion" in output
    assert "plain output line" in output
    assert len(log_messages) == 3
    assert progress.calls[-1] == (1.0, "Complete")
    assert any(pct > 0 for pct, _ in progress.calls)


# --- test_run_orion_timeout ---

def test_run_orion_timeout(tmp_path):
    import subprocess as real_subprocess

    mock_process = MagicMock()
    mock_process.stdout.readline.side_effect = [""]
    # First wait() call raises TimeoutExpired; second (after kill) returns normally
    mock_process.wait.side_effect = [real_subprocess.TimeoutExpired(cmd="orion", timeout=5), None]
    mock_process.kill.return_value = None
    mock_process.returncode = -9

    progress = FakeProgressBar()
    status = FakeStatusContainer()

    lock_file = str(tmp_path / "test_timeout.lock")
    with patch("orion_runner.subprocess.Popen", return_value=mock_process), \
         patch("orion_runner.ORION_LOCK_FILE", lock_file):
        rc, output, log_messages = run_orion(
            ["orion", "--config", "test.yaml"],
            {}, "/tmp", status, progress, metric_total=0, timeout=5,
        )

    assert rc == -1
    assert "timed out" in output.lower()
    mock_process.kill.assert_called_once()


# --- test_rate_limiting ---

def test_acquire_and_release_lock(tmp_path):
    lock_file = str(tmp_path / "test.lock")
    with patch("orion_runner.ORION_LOCK_FILE", lock_file):
        fd = _acquire_run_lock()
        assert fd is not None

        # Second acquire should fail (non-blocking)
        fd2 = _acquire_run_lock()
        assert fd2 is None

        _release_run_lock(fd)

        # After release, should succeed again
        fd3 = _acquire_run_lock()
        assert fd3 is not None
        _release_run_lock(fd3)


def test_run_orion_blocked_by_lock(tmp_path):
    lock_file = str(tmp_path / "test_blocked.lock")
    with patch("orion_runner.ORION_LOCK_FILE", lock_file):
        # Hold the lock
        fd = _acquire_run_lock()
        assert fd is not None

        progress = FakeProgressBar()
        status = FakeStatusContainer()

        rc, output, log_messages = run_orion(
            ["orion", "--config", "test.yaml"],
            {}, "/tmp", status, progress, metric_total=0,
        )

        assert rc == -1
        assert "already in progress" in output.lower()

        _release_run_lock(fd)


# --- test_discover_configs_caching ---

def test_discover_configs_caching(tmp_examples_dir):
    discover_configs.clear()
    result1 = discover_configs()
    assert result1 == ["simple.yaml"]

    # Create another config file — cached result should still show only one
    import pathlib
    (pathlib.Path(str(tmp_examples_dir)) / "another.yaml").write_text("tests: []")
    result2 = discover_configs()
    assert result2 == ["simple.yaml"]  # still cached

    # After clearing, should pick up new file
    discover_configs.clear()
    result3 = discover_configs()
    assert "another.yaml" in result3


# --- test_get_config_metrics ---

def test_get_config_metrics(tmp_examples_dir):
    get_config_metrics.clear()
    result = get_config_metrics("simple.yaml")
    assert "test-one" in result
    assert "test-two" in result
    assert result["test-one"] == ["throughput", "latency"]
    assert result["test-two"] == ["cpu_usage", "memory_usage"]


def test_get_config_metrics_missing():
    get_config_metrics.clear()
    result = get_config_metrics("nonexistent.yaml")
    assert result == {}


# --- test_get_metrics_for_configs ---

def test_get_metrics_for_configs(tmp_multi_examples_dir):
    get_config_metrics.clear()
    index = get_metrics_for_configs(["simple.yaml", "second.yaml"])

    # throughput appears in both configs
    assert "throughput" in index
    assert len(index["throughput"]) == 2
    configs_with_throughput = [cfg for cfg, _ in index["throughput"]]
    assert "simple.yaml" in configs_with_throughput
    assert "second.yaml" in configs_with_throughput

    # disk_io only in second.yaml
    assert "disk_io" in index
    assert len(index["disk_io"]) == 1
    assert index["disk_io"][0] == ("second.yaml", "test-alpha")

    # latency only in simple.yaml
    assert "latency" in index
    assert len(index["latency"]) == 1
    assert index["latency"][0] == ("simple.yaml", "test-one")
