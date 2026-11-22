import json

from conftest import SAMPLE

from robotics101.cli import EXIT_INPUT, EXIT_INVALID, EXIT_NOT_IMPLEMENTED, EXIT_OK, main


def test_validate_sample_exit_zero(capsys):
    assert main(["validate", str(SAMPLE)]) == EXIT_OK
    assert "VALID" in capsys.readouterr().out


def test_validate_invalid_spec_exit_nonzero(tmp_path, spec, capsys):
    spec["scenes"][0]["template"] = "nope_template"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(spec))
    assert main(["validate", str(path)]) == EXIT_INVALID
    captured = capsys.readouterr()
    assert "unknown template 'nope_template'" in captured.err
    assert "INVALID" in captured.out


def test_validate_strict_fails_on_warnings(tmp_path, spec):
    spec["durationTargetSeconds"] = 600
    path = tmp_path / "warn.json"
    path.write_text(json.dumps(spec))
    assert main(["validate", str(path)]) == EXIT_OK
    assert main(["validate", "--strict", str(path)]) == EXIT_INVALID


def test_validate_missing_file_and_bad_json(tmp_path):
    assert main(["validate", str(tmp_path / "missing.json")]) == EXIT_INPUT
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert main(["validate", str(bad)]) == EXIT_INPUT


def test_render_placeholder_not_implemented(capsys):
    assert main(["render", str(SAMPLE)]) == EXIT_NOT_IMPLEMENTED
    assert "not implemented yet (M01.5)" in capsys.readouterr().err
