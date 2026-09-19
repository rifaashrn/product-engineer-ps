from solution.agent.cli import main


def test_fake_multi_demo_runs_end_to_end(tmp_path, capsys):
    code = main(["--fake", "multi", "--runs-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "EVIDENCE" in out
    assert "CONCLUSION" in out
    assert len(list(tmp_path.glob("*.jsonl"))) == 1


def test_fake_limit_demo_reports_the_stop(tmp_path, capsys):
    code = main(["--fake", "limit", "--max-steps", "3", "--runs-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 1
    assert "max_steps_reached" in out