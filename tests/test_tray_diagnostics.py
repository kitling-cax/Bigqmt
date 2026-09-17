from pathlib import Path

from kitling_bigqmt.tray_diagnostics import _diagnosis, _read_json_lines


def test_diagnosis_marks_missing_launch_record():
    code, _ = _diagnosis([], [], [], [])
    assert code == "NO_LAUNCH_ATTEMPT_RECORDED"


def test_diagnosis_marks_exited_launcher():
    code, _ = _diagnosis([], [{"event": "launcher_spawned"}], [], [])
    assert code == "TRAY_EXITED_AFTER_SPAWN"


def test_read_json_lines_ignores_bad_rows(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"event":"one"}\nbad json\n{"event":"two"}\n', encoding="utf-8")
    assert [row["event"] for row in _read_json_lines(path)] == ["one", "two"]
