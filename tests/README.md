# Tests

Unit and integration tests for `orion_runner.py`. No external services (ES, cluster) needed.

## Run

```bash
pip install pytest
python -m pytest tests/ -v
```

## Test summary

| Test | What it covers |
|------|---------------|
| `test_build_command_flags` | All CLI flags (algorithm, lookback, node_count, debug, sippy, uuid, baseline, version via --input-vars) end up in the command correctly |
| `test_build_command_env` | ES_SERVER, benchmark_index, metadata_index are set in the subprocess environment |
| `test_humanize_command` | Command is displayed cleanly: binary path shortened, save paths stripped, config path shortened |
| `test_parse_log_message` | Orion log lines are parsed into (level, message) tuples; non-log lines return None |
| `test_extract_regressions` | Regression blocks are parsed from orion output; handles zero, single, and multiple regressions |
| `test_discover_and_metadata` | YAML config discovery and metadata extraction (test count, metric count, test names) |
| `test_parse_csv_and_viz` | CSV data files are read into DataFrames; viz HTML files are found; missing dirs return empty |
| `test_run_orion_subprocess` | Full subprocess pipeline with mocked Popen: stdout streaming, log parsing, progress bar updates, return code |

## Fixtures (conftest.py)

- `tmp_examples_dir` -- temp directory with a sample YAML config, patches `ORION_EXAMPLES_DIR`
- `tmp_data_dir` -- temp directory with sample CSV and viz HTML files
