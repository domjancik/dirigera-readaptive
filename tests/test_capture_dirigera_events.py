import importlib.util
import os
from pathlib import Path


def _capture_module():
    script_path = Path(__file__).parents[1] / "scripts" / "capture_dirigera_events.py"
    spec = importlib.util.spec_from_file_location("capture_dirigera_events", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rotating_writer_removes_oldest_capture_when_budget_is_exceeded(tmp_path):
    module = _capture_module()
    oldest = tmp_path / "old-events.jsonl"
    newest = tmp_path / "new-events.jsonl"
    oldest.write_bytes(b"123456")
    newest.write_bytes(b"abcdef")
    os.utime(oldest, (1, 1))
    os.utime(newest, (2, 2))

    with module.RotatingJsonlWriter(
        label="capture",
        rotate_bytes=0,
        max_total_bytes=10,
        captures_dir=tmp_path,
    ):
        pass

    assert not oldest.exists()
    assert newest.exists()
