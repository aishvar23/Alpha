import json

from conftest import SAMPLE

from robotics101.cli import EXIT_INPUT, EXIT_INVALID, EXIT_OK, main


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


def test_render_requires_out(capsys):
    import pytest
    with pytest.raises(SystemExit):
        main(["render", str(SAMPLE)])


def test_render_invalid_spec_exits_before_any_output(tmp_path, spec):
    spec["scenes"][0]["template"] = "nope_template"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(spec))
    assert main(["render", str(path), "--out", str(tmp_path / "out"), "--tts", "fixture"]) == EXIT_INVALID
    assert not (tmp_path / "out" / "final.mp4").exists()


def test_qa_on_missing_dir(tmp_path):
    assert main(["qa", str(tmp_path / "nope")]) == EXIT_INPUT
