import pytest
import orion_runner


SIMPLE_YAML = """\
tests:
  - name: test-one
    metrics:
      - name: throughput
      - name: latency
  - name: test-two
    metrics:
      - name: cpu_usage
      - name: memory_usage
"""

SECOND_YAML = """\
tests:
  - name: test-alpha
    metrics:
      - name: throughput
      - name: disk_io
"""

SAMPLE_CSV = """\
timestamp,uuid,value,build
2024-01-01,abc-123,100.5,build-1
2024-01-02,def-456,98.3,build-2
2024-01-03,ghi-789,102.1,build-3
"""


@pytest.fixture
def tmp_examples_dir(tmp_path, monkeypatch):
    cfg = tmp_path / "simple.yaml"
    cfg.write_text(SIMPLE_YAML)
    monkeypatch.setattr(orion_runner, "ORION_EXAMPLES_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def tmp_multi_examples_dir(tmp_path, monkeypatch):
    (tmp_path / "simple.yaml").write_text(SIMPLE_YAML)
    (tmp_path / "second.yaml").write_text(SECOND_YAML)
    monkeypatch.setattr(orion_runner, "ORION_EXAMPLES_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def tmp_data_dir(tmp_path):
    (tmp_path / "data.csv").write_text(SAMPLE_CSV)
    (tmp_path / "example_viz.html").write_text("<html>plot</html>")
    return tmp_path
