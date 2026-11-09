import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(*args):
    return subprocess.run([sys.executable, "-m", "trialgraph", *args], cwd=ROOT,
                          capture_output=True, text=True)


def test_publish_republish_check_round_trip(tmp_path):
    db = str(tmp_path / "graph.db")
    assert run("publish", "--interp", "interpretations/v1.csv", "--db", db).returncode == 0
    assert run("check", "--interp", "interpretations/v1.csv", "--db", db).returncode == 0
    # the v1 graph is not the v2 graph
    stale = run("check", "--interp", "interpretations/v2.csv", "--db", db)
    assert stale.returncode == 1 and "DIFFERENT" in stale.stdout
    assert run("republish", "--interp", "interpretations/v2.csv", "--db", db).returncode == 0
    done = run("check", "--interp", "interpretations/v2.csv", "--db", db)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "same graph" in done.stdout


def test_quality_report_lists_the_codes_found_in_the_snapshot():
    out = run("quality")
    assert out.returncode == 0
    assert "W001" in out.stdout and "W002" in out.stdout and "W003" in out.stdout
