"""Grade a sealed QA result offline against its original private source packet."""
import argparse
import hashlib
import json
from pathlib import Path


def grade(manifest, output_dir, packet_path):
    answer_bytes = (output_dir / "first-valid-answer.private.json").read_bytes()
    answer = json.loads(answer_bytes)
    identity = answer["identity"]
    records = [r for r in manifest["entries"] if r["qa_id"] == identity["qa_id"]]
    if len(records) != 1:
        raise ValueError("Expected exactly one matching QA identity")
    row = records[0]
    proof = json.loads((output_dir / "result.private.json").read_bytes())
    timing = proof["api_timing"]
    if (proof["identity"] != identity or proof.get("answer_recorded") is not True
            or proof["answer_sha256"] != hashlib.sha256(answer_bytes).hexdigest()
            or timing.get("transport_quiescent_confirmed") is not True
            or timing.get("ledger_integrity_valid") is not True or timing["active"] or timing["uncertain"]):
        raise ValueError("Incomplete first-answer or transport evidence")
    raw_packet = packet_path.read_bytes()
    if hashlib.sha256(raw_packet).hexdigest() != row["source_public_packet_sha256"]:
        raise ValueError("Wrong source packet")
    packet = json.loads(raw_packet)
    key = packet["qa_grading_private"]
    question = row["public_question"]
    if (identity != {k: row[k] for k in ("qa_id", "task", "variant", "seed")}
            or answer["source_sha256"] != row["video_sha256"] or answer["first_valid"] is not True
            or answer["selected_option"] not in ("A", "B", "C", "D")
            or key["correct_option"] not in ("A", "B", "C", "D")
            or any(question[k] != packet["qa_public_packet"][k] for k in question)
            or key["input_mode"] != "real" or key["task_id"] != row["task"] or key["variant"] != row["variant"]
            or not (key["question_id"] == question["question_id"] == answer["question_id"])
            or key["source_demo_sha256"] != row["original_source_demo_sha256"]):
        raise ValueError("QA identity, question or evidence mismatch")
    return {"qa_id": identity["qa_id"], "correct": answer["selected_option"] == key["correct_option"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--private-packet", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(grade(json.loads(args.manifest.read_bytes()), args.output_dir, args.private_packet)))
