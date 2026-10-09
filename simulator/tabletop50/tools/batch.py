#!/usr/bin/env python3
"""Bounded independent simulation processes, resumable without hiding failures."""
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from simulator.tabletop50.catalog import IMPLEMENTED
from simulator.tabletop50.families import REVISION
from simulator.tabletop50.tools.record import source_hash


def valid_proof(r, variant, record, folder):
    cross = r.get("cross_rule_predicates", {})
    video = r.get("video", {})
    return bool(r.get("score", {}).get("success") and not r.get("error")
        and r.get("source_unchanged") and r.get("source_sha256") == source_hash()
        and sum(cross.values()) == 1 and cross.get(variant)
        and (not record or video.get("recorded") and video.get("final_success")
             and (folder/"video.mp4").is_file()))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tasks", nargs="+", choices=IMPLEMENTED, default=IMPLEMENTED)
    p.add_argument("--variants", nargs="+", choices=list("ABC"), default=list("ABC"))
    p.add_argument("--seeds", nargs="+", type=int, default=[0])
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--record", action="store_true")
    a = p.parse_args()
    # Children execute from the frozen source root, which can differ from the
    # caller's cwd. Resolve once so logs and proofs use the same directory.
    a.output = a.output.resolve()
    a.output.mkdir(parents=True, exist_ok=True)
    cases = [(t, v, s) for t in a.tasks for v in a.variants for s in a.seeds]
    env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")

    def run(case):
        t, v, s = case
        key = f"{t}-{v}-{s}"
        proof = a.output/key/"result.private.json"
        if proof.exists():
            r = json.loads(proof.read_text())
            ok = valid_proof(r, v, a.record, proof.parent)
            return dict(task=t, variant=v, seed=s, success=ok, existing=True, result=str(proof))
        cmd = [sys.executable, str(ROOT/"simulator/tabletop50/tools/record.py"), "--task", t,
               "--variant", v, "--seed", str(s), "--output", str(a.output)]
        if a.record: cmd += ["--record"]
        with (a.output/(key+".log")).open("x") as log:
            proc = subprocess.run(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        r = json.loads(proof.read_text()) if proof.exists() else {}
        return dict(task=t, variant=v, seed=s, success=bool(proc.returncode == 0
                    and valid_proof(r, v, a.record, proof.parent)),
                    exit_code=proc.returncode, error=r.get("error", "No proof produced" if not r else None), result=str(proof))

    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(a.workers, 8))) as pool:
        for future in concurrent.futures.as_completed([pool.submit(run, case) for case in cases]):
            r = future.result(); rows.append(r); print(json.dumps(r), flush=True)
            summary = dict(revision=REVISION, expected=len(cases), finished=len(rows),
                           succeeded=sum(x["success"] for x in rows), rows=rows)
            (a.output/"batch.private.json").write_text(json.dumps(summary, indent=2)+"\n")
    if not all(r["success"] for r in rows): raise SystemExit(1)


if __name__ == "__main__": main()
