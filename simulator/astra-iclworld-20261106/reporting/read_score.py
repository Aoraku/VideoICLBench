"""Read a sealed room's engineering score without modifying its artifact."""
import argparse
import json
from pathlib import Path


def valid_score(value):
    return type(value) in (float, int) and 0 <= value <= 100


def read_score(environment):
    native_path = environment / "terminal-native.private.json"
    evaluation_path = environment / "authoritative-evaluation.json"
    result = {"terminal": native_path.is_file(), "success": None, "score": None, "source": None}
    if not result["terminal"] or not evaluation_path.is_file():
        return result
    native = json.loads(native_path.read_bytes())["evidence"]
    evaluation = json.loads(evaluation_path.read_bytes())
    success = evaluation["success"]
    if type(success) is not bool or success is not native.get("success"):
        raise ValueError("Native and evaluation outcomes do not agree")
    result["success"] = success
    value = evaluation.get("task_score_100")
    if valid_score(value):
        return dict(result, score=value, source="authoritative-evaluation.task_score_100")
    if value is not None:
        raise ValueError("Unexpected score value")
    if native.get("errors") or native.get("history_valid") is not True:
        return result
    if native.get("protocol") == "execution-design-v2":
        value = native.get("engineering_score_100")
        if (native.get("scored") is True and native.get("native_evidence_valid") is True
                and native.get("missing_evidence") == [] and valid_score(value)
                and native.get("task_score_100") == native.get("process_score") == value):
            return dict(result, score=value, source="terminal-native.evidence.engineering_score_100")
    progress = native.get("progress_result") or {}
    if (evaluation.get("task_id") == progress.get("task") == "E26"
            and evaluation.get("variant") == progress.get("variant")
            and progress.get("protocol") == "realworld50-execution-v2-bell-progress"
            and progress.get("progress_available") is True and progress.get("missing_evidence") == []):
        value = progress.get("task_score_100")
        # Raw pre-gate scores may exceed the failure ceiling. The two audited
        # endpoints agree with the strict native decision.
        if valid_score(value) and ((success and value == 100) or (not success and value == 0)):
            return dict(result, score=value, source="terminal-native.evidence.progress_result.task_score_100")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", type=Path)
    print(json.dumps(read_score(parser.parse_args().environment)))
