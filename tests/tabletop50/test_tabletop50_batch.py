import json
import subprocess
import sys
from pathlib import Path

from scripts.tabletop50.record import source_hash

ROOT = Path(__file__).resolve().parents[2]


def test_resume_rejects_stale_proof_and_headless_proof_for_video_job(tmp_path):
    folder = tmp_path/"F01-A-0"; folder.mkdir()
    proof = dict(score={"success": True}, error=None, source_unchanged=True,
                 source_sha256="stale", cross_rule_predicates={"A": True, "B": False, "C": False},
                 video={"recorded": False, "final_success": True})
    path = folder/"result.private.json"
    cmd = [sys.executable, str(ROOT/"scripts/tabletop50/batch.py"), "--tasks", "F01",
           "--variants", "A", "--output", str(tmp_path)]
    path.write_text(json.dumps(proof))
    assert subprocess.run(cmd, cwd=ROOT, capture_output=True).returncode == 1
    proof["source_sha256"] = source_hash(); path.write_text(json.dumps(proof))
    assert subprocess.run(cmd, cwd=ROOT, capture_output=True).returncode == 0
    assert subprocess.run(cmd+["--record"], cwd=ROOT, capture_output=True).returncode == 1
