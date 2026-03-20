import json
from unittest.mock import MagicMock, patch

from orion_runner import (
    NoOpTracker,
    _acquire_run_lock,
    _parse_log_message,
    _release_run_lock,
    aggregate_weekly_trends,
    build_command,
    discover_configs,
    execute_config,
    extract_metrics_json,
    extract_regressions_json,
    find_viz_html,
    generate_date_windows,
    get_config_metadata,
    get_config_metrics,
    get_metrics_for_configs,
    humanize_command,
    parse_csv_data,
    run_orion,
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
    assert env["PROW_JOB_ID"] == "orion-newspaper"


def test_build_command_env_no_es_server(tmp_path, monkeypatch):
    monkeypatch.delenv("ES_SERVER", raising=False)
    params = _base_params(tmp_path)
    _, env, _ = build_command(params)

    assert "ES_SERVER" not in env


# --- test_humanize_command ---


def test_humanize_command(tmp_path):
    cmd = [
        "/app/orion-venv/bin/orion",
        "--config",
        "/orion/examples/test.yaml",
        "--hunter-analyze",
        "--lookback",
        "15d",
        "--save-output-path",
        str(tmp_path / "output.txt"),
        "--save-data-path",
        str(tmp_path / "data.csv"),
        "--viz",
        "--input-vars",
        '{"version": "4.18"}',
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


# --- test_extract_regressions_json ---


def test_extract_regressions_json_empty():
    assert extract_regressions_json(None) == []
    assert extract_regressions_json("/nonexistent") == []


def test_extract_regressions_json(tmp_path):
    data = [
        {
            "ocpVersion": "4.17",
            "is_changepoint": False,
            "metrics": {"podReadyLatency": {"value": 80.0, "percentage_change": 0}},
        },
        {
            "ocpVersion": "4.18",
            "is_changepoint": True,
            "metrics": {"podReadyLatency": {"value": 105.0, "percentage_change": 31.25}},
        },
        {
            "ocpVersion": "4.19",
            "is_changepoint": False,
            "metrics": {"podReadyLatency": {"value": 106.0, "percentage_change": 0}},
        },
    ]
    (tmp_path / "output_my-test.json").write_text(json.dumps(data))

    result = extract_regressions_json(str(tmp_path))
    assert len(result) == 1
    assert result[0]["test_name"] == "my-test"
    assert result[0]["metric"] == "podReadyLatency"
    assert result[0]["percentage_change"] == 31.25
    assert result[0]["prev_value"] == 80.0
    assert result[0]["bad_value"] == 105.0
    assert result[0]["prev_ver"] == "4.17"
    assert result[0]["bad_ver"] == "4.18"


def test_extract_regressions_json_multiple_metrics(tmp_path):
    data = [
        {
            "ocpVersion": "4.20",
            "is_changepoint": False,
            "metrics": {
                "cpu": {"value": 10, "percentage_change": 0},
                "memory": {"value": 200, "percentage_change": 0},
            },
        },
        {
            "ocpVersion": "4.21",
            "is_changepoint": True,
            "metrics": {
                "cpu": {"value": 15, "percentage_change": 50.0},
                "memory": {"value": 210, "percentage_change": 5.0},
            },
        },
    ]
    (tmp_path / "output_perf-test.json").write_text(json.dumps(data))

    result = extract_regressions_json(str(tmp_path))
    assert len(result) == 2
    # Sorted by absolute percentage change descending
    assert result[0]["metric"] == "cpu"
    assert result[0]["percentage_change"] == 50.0
    assert result[1]["metric"] == "memory"
    assert result[1]["percentage_change"] == 5.0


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
    with (
        patch("orion_runner.subprocess.Popen", return_value=mock_process),
        patch("orion_runner.ORION_LOCK_FILE", lock_file),
    ):
        rc, output, log_messages = run_orion(
            ["orion", "--config", "test.yaml"],
            {},
            "/tmp",
            status,
            progress,
            metric_total=2,
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
    with (
        patch("orion_runner.subprocess.Popen", return_value=mock_process),
        patch("orion_runner.ORION_LOCK_FILE", lock_file),
    ):
        rc, output, log_messages = run_orion(
            ["orion", "--config", "test.yaml"],
            {},
            "/tmp",
            status,
            progress,
            metric_total=0,
            timeout=5,
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
            {},
            "/tmp",
            status,
            progress,
            metric_total=0,
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


def test_get_config_metrics_aggregated(tmp_path, monkeypatch):
    """Test that aggregated metrics use agg_type suffix, standard use metric_of_interest."""
    from tests.conftest import AGG_YAML

    (tmp_path / "agg.yaml").write_text(AGG_YAML)
    monkeypatch.setattr("orion_runner.ORION_EXAMPLES_DIR", str(tmp_path))
    get_config_metrics.clear()
    result = get_config_metrics("agg.yaml")
    assert result["test-agg"] == ["podReadyLatency_P99", "ovnMem_avg"]


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


# --- test_execute_config ---


def test_execute_config_success(tmp_examples_dir, tmp_path):
    """Test execute_config returns correct result dict on success."""
    mock_process = MagicMock()
    lines = [
        "2024-01-01 00:00:00,000 - orion - INFO - file: x.py - line: 1 - Collecting cpu\n",
        "",
    ]
    mock_process.stdout.readline.side_effect = lines
    mock_process.wait.return_value = None
    mock_process.returncode = 0

    lock_file = str(tmp_path / "test_exec.lock")
    with (
        patch("orion_runner.subprocess.Popen", return_value=mock_process),
        patch("orion_runner.ORION_LOCK_FILE", lock_file),
    ):
        result = execute_config("simple.yaml", "4.22", "7d")

    assert result["return_code"] == 0
    assert result["n_metrics"] == 1
    assert result["duration"] > 0
    assert result["temp_dir"] is not None
    assert result["cmd_display"] != ""
    assert "last_run" in result


def test_execute_config_exception_scrubs_es(tmp_examples_dir, tmp_path):
    """Test execute_config scrubs ES_SERVER from exception messages."""
    lock_file = str(tmp_path / "test_exec_err.lock")
    with (
        patch(
            "orion_runner.subprocess.Popen",
            side_effect=RuntimeError("Connection to https://secret-es:9200 failed"),
        ),
        patch("orion_runner.ORION_LOCK_FILE", lock_file),
        patch.dict("os.environ", {"ES_SERVER": "https://secret-es:9200"}),
    ):
        result = execute_config("simple.yaml", "4.22", "7d")

    assert result["return_code"] == -1
    assert "secret-es" not in result["full_output"]
    assert "***" in result["full_output"]
    assert result["temp_dir"] is None


def test_execute_config_cleans_prev_temp_dir(tmp_examples_dir, tmp_path):
    """Test execute_config removes prev_temp_dir."""
    prev_dir = tmp_path / "prev_run"
    prev_dir.mkdir()
    (prev_dir / "data.csv").write_text("x")

    mock_process = MagicMock()
    mock_process.stdout.readline.side_effect = [""]
    mock_process.wait.return_value = None
    mock_process.returncode = 0

    lock_file = str(tmp_path / "test_exec_clean.lock")
    with (
        patch("orion_runner.subprocess.Popen", return_value=mock_process),
        patch("orion_runner.ORION_LOCK_FILE", lock_file),
    ):
        execute_config("simple.yaml", "4.22", "7d", prev_temp_dir=str(prev_dir))

    assert not prev_dir.exists()


def test_noop_tracker():
    """Test NoOpTracker methods don't raise."""
    tracker = NoOpTracker()
    tracker.progress(0.5, text="test")
    tracker.text("test")


# --- test_build_command_since ---


def test_build_command_since_flag(tmp_path):
    params = _base_params(tmp_path, since="2026-01-15")
    cmd, _env, _cwd = build_command(params)
    assert "--since" in cmd
    idx = cmd.index("--since")
    assert cmd[idx + 1] == "2026-01-15"


def test_build_command_since_empty(tmp_path):
    params = _base_params(tmp_path, since="")
    cmd, _env, _cwd = build_command(params)
    assert "--since" not in cmd


# --- test_execute_config_with_filter ---


def test_execute_config_with_filter_algorithm(tmp_examples_dir, tmp_path):
    """Test execute_config passes algorithm parameter through."""
    mock_process = MagicMock()
    mock_process.stdout.readline.side_effect = [""]
    mock_process.wait.return_value = None
    mock_process.returncode = 0

    lock_file = str(tmp_path / "test_filter.lock")
    with (
        patch("orion_runner.subprocess.Popen", return_value=mock_process) as mock_popen,
        patch("orion_runner.ORION_LOCK_FILE", lock_file),
    ):
        execute_config("simple.yaml", "4.22", "7d", algorithm="filter")

    # Check that --filter flag was in the command
    cmd = mock_popen.call_args[0][0]
    assert "--filter" in cmd
    assert "--hunter-analyze" not in cmd


# --- test_generate_date_windows ---


def test_generate_date_windows():
    windows = generate_date_windows(6)
    assert len(windows) == 6
    # All windows have 30d lookback
    assert all(lb == "30d" for _, lb in windows)
    # All since dates are valid YYYY-MM-DD
    for since, _ in windows:
        assert len(since) == 10
        assert since[4] == "-" and since[7] == "-"
    # Ordered oldest to newest
    assert windows[0][0] < windows[-1][0]


def test_generate_date_windows_3months():
    assert len(generate_date_windows(3)) == 3


def test_generate_date_windows_12months():
    assert len(generate_date_windows(12)) == 12


# --- test_aggregate_weekly_trends ---


def _make_trend_runs(timestamps, metric_values):
    """Helper to create a list of dicts resembling extract_metrics_json output."""
    return [
        {"uuid": f"uuid-{i}", "timestamp": ts, "cpu_avg": val}
        for i, (ts, val) in enumerate(zip(timestamps, metric_values))
    ]


def test_aggregate_weekly_trends_median():
    # Two weeks of data, 2 runs per week
    runs = _make_trend_runs(
        ["2026-01-05T10:00:00", "2026-01-07T10:00:00", "2026-01-12T10:00:00", "2026-01-14T10:00:00"],
        [10.0, 20.0, 30.0, 40.0],
    )
    result = aggregate_weekly_trends([("2026-01-15", runs)], ["cpu_avg"], "median")
    assert len(result) == 2
    assert "week_start" in result.columns
    assert "n_runs" in result.columns
    assert "cpu_avg" in result.columns
    # Week 1 median of [10, 20] = 15, Week 2 median of [30, 40] = 35
    values = result["cpu_avg"].tolist()
    assert values[0] == 15.0
    assert values[1] == 35.0


def test_aggregate_weekly_trends_mean():
    runs = _make_trend_runs(
        ["2026-01-05T10:00:00", "2026-01-07T10:00:00", "2026-01-12T10:00:00"],
        [10.0, 20.0, 30.0],
    )
    result = aggregate_weekly_trends([("2026-01-15", runs)], ["cpu_avg"], "mean")
    assert len(result) == 2
    # Week 1 mean of [10, 20] = 15, Week 2 mean of [30] = 30
    values = result["cpu_avg"].tolist()
    assert values[0] == 15.0
    assert values[1] == 30.0


def test_aggregate_weekly_trends_empty():
    result = aggregate_weekly_trends([], ["cpu_avg"], "median")
    assert result.empty
    assert "week_start" in result.columns
    assert "cpu_avg" in result.columns


def test_aggregate_weekly_trends_deduplicates_uuids():
    """Overlapping monthly windows should not double-count runs."""
    runs1 = _make_trend_runs(["2026-01-05T10:00:00"], [10.0])
    runs2 = _make_trend_runs(["2026-01-05T10:00:00"], [10.0])  # same uuid-0
    result = aggregate_weekly_trends(
        [("2026-01-15", runs1), ("2026-02-15", runs2)],
        ["cpu_avg"],
        "median",
    )
    assert result["n_runs"].sum() == 1


# --- test_extract_metrics_json ---


def test_extract_metrics_json(tmp_path):
    data = [
        {
            "uuid": "abc-123",
            "timestamp": "2026-01-05T10:00:00",
            "is_changepoint": False,
            "metrics": {
                "cpu_avg": {"value": 42.5, "percentage_change": 0},
                "mem_avg": {"value": 1024.0, "percentage_change": 0},
            },
        },
        {
            "uuid": "def-456",
            "timestamp": "2026-01-06T10:00:00",
            "is_changepoint": True,
            "metrics": {
                "cpu_avg": {"value": 50.0, "percentage_change": 17.6},
                "mem_avg": {"value": 1100.0, "percentage_change": 7.4},
            },
        },
    ]
    (tmp_path / "output_test-one.json").write_text(json.dumps(data))

    result = extract_metrics_json(str(tmp_path))
    assert len(result) == 2
    assert result[0]["uuid"] == "abc-123"
    assert result[0]["cpu_avg"] == 42.5
    assert result[0]["mem_avg"] == 1024.0
    assert result[1]["cpu_avg"] == 50.0


def test_extract_metrics_json_empty():
    assert extract_metrics_json("") == []
    assert extract_metrics_json(None) == []
