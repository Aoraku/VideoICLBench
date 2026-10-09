import json
import subprocess
import sys
from pathlib import Path

from simulator.tabletop50.tools.record import source_hash
from simulator.tabletop50.tools.batch import valid_proof

ROOT = Path(__file__).resolve().parents[3]


def test_fresh_and_resumed_jobs_require_unambiguous_current_proof(tmp_path):
    assert not valid_proof({}, "A", False, tmp_path)
    proof = dict(score={"success": True}, error=None, source_unchanged=True,
                 source_sha256=source_hash(), cross_rule_predicates={"A": True, "B": True, "C": False})
    assert not valid_proof(proof, "A", False, tmp_path)
    proof["cross_rule_predicates"]["B"] = False
    assert valid_proof(proof, "A", False, tmp_path)
    assert not valid_proof(proof, "B", False, tmp_path)
    assert not valid_proof(proof, "A", True, tmp_path)


def test_resume_rejects_stale_proof_and_headless_proof_for_video_job(tmp_path):
    folder = tmp_path/"F01-A-0"; folder.mkdir()
    proof = dict(score={"success": True}, error=None, source_unchanged=True,
                 source_sha256="stale", cross_rule_predicates={"A": True, "B": False, "C": False},
                 video={"recorded": False, "final_success": True})
    path = folder/"result.private.json"
    cmd = [sys.executable, str(ROOT/"simulator/tabletop50/tools/batch.py"), "--tasks", "F01",
           "--variants", "A", "--output", str(tmp_path)]
    path.write_text(json.dumps(proof))
    assert subprocess.run(cmd, cwd=ROOT, capture_output=True).returncode == 1
    proof["source_sha256"] = source_hash(); path.write_text(json.dumps(proof))
    assert subprocess.run(cmd, cwd=ROOT, capture_output=True).returncode == 0
    assert subprocess.run(cmd+["--record"], cwd=ROOT, capture_output=True).returncode == 1


def test_relative_output_is_resolved_from_callers_directory(tmp_path):
    folder = tmp_path/"recordings"/"F01-A-0"; folder.mkdir(parents=True)
    proof = dict(score={"success": True}, error=None, source_unchanged=True,
                 source_sha256=source_hash(), cross_rule_predicates={"A": True, "B": False, "C": False})
    (folder/"result.private.json").write_text(json.dumps(proof))
    cmd = [sys.executable, str(ROOT/"simulator/tabletop50/tools/batch.py"), "--tasks", "F01",
           "--variants", "A", "--output", "recordings"]
    assert subprocess.run(cmd, cwd=tmp_path, capture_output=True).returncode == 0
    row = json.loads((tmp_path/"recordings"/"batch.private.json").read_text())["rows"][0]
    assert row["result"] == str(folder/"result.private.json")
