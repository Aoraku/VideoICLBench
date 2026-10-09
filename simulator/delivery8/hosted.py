"""Standard-library HTTP model runner. No browser or simulation installation needed."""
import argparse
import json
import math
import os
from pathlib import Path
import time
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
PROMPT = (HERE/"prompt.txt").read_text()


def request(url, body=None, headers=None, timeout=300):
    req = Request(url, data=None if body is None else json.dumps(body).encode(),
                  headers={"Content-Type": "application/json", **(headers or {})})
    with urlopen(req, timeout=timeout) as response: return json.load(response)


def decision(text, tokens):
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {"left", "right", "step_mm", "rotation_deg", "finish", "summary"}:
        raise ValueError("Invalid model response fields")
    for key in ("left", "right"):
        if not isinstance(value[key], str) or value[key] not in tokens: raise ValueError("Invalid token")
    for key, maximum in (("step_mm", 50), ("rotation_deg", 20)):
        n = value[key]
        if type(n) not in (int, float) or not math.isfinite(n) or not .5 <= n <= maximum:
            raise ValueError("Invalid distance/angle")
    if type(value["finish"]) is not bool or not isinstance(value["summary"], str) or len(value["summary"]) > 500:
        raise ValueError("Invalid finish/summary")
    if value["finish"] and (value["left"] != "STILL" or value["right"] != "STILL"):
        raise ValueError("Finish must use STILL")
    return value


def payload(model, demos, obs, history):
    content = []
    def picture(label, data):
        content.extend([dict(type="text", text=label), dict(type="image_url",
            image_url=dict(url="data:image/jpeg;base64,"+data))])
    for i, frame in enumerate(demos): picture(f"Demonstration {i+1}/12 (chronological)", frame)
    for name, frame in obs["images"].items(): picture("Current camera: "+name, frame)
    public = {k: obs[k] for k in ("instruction", "observation_id", "actions", "remaining", "tokens", "motion")}
    content.append(dict(type="text", text=json.dumps(dict(observation=public, history=history[-8:]))))
    return dict(model=model, messages=[dict(role="system", content=PROMPT),
                dict(role="user", content=content)], max_completion_tokens=2048)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:18767")
    parser.add_argument("--task", default="F44")
    parser.add_argument("--variant", choices=list("ABC"), default="A")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--session", help="Resume an existing actor session; platform key not required")
    parser.add_argument("--max-calls", type=int, default=100)
    parser.add_argument("--log-dir", type=Path, default=HERE/"runs/hosted")
    parser.add_argument("--check", action="store_true", help="Check service/catalog; do not create a session or call a model")
    args = parser.parse_args()
    if args.max_calls < 1: parser.error("max-calls must be positive")
    url = args.url.rstrip("/")
    headers = {"Authorization": "Bearer "+os.environ.get("TABLETOP8_KEY", "")}
    if args.check:
        print(json.dumps(request(url+"/health"), ensure_ascii=False))
        print(json.dumps(request(url+"/control/tasks", headers=headers), ensure_ascii=False, indent=2))
        return
    model = os.environ.get("VLM_MODEL", "")
    base = os.environ.get("VLM_BASE_URL", "").rstrip("/")
    key = os.environ.get("VLM_API_KEY", "")
    if not all((model, base, key)): parser.error("Set VLM_BASE_URL, VLM_MODEL and VLM_API_KEY")
    sid = args.session
    if not sid:
        sid = request(url+"/control/sessions", dict(task=args.task, variant=args.variant,
            seed=args.seed, trial_kind="agent"), headers)["session"]
    actor = url+"/actor/"+sid
    print("Session:", sid, flush=True)
    print("Control panel:", url, flush=True)
    folder = args.log_dir/(time.strftime("%Y%m%d-%H%M%S")+"-"+sid)
    folder.mkdir(parents=True)
    (folder/"prompt.txt").write_text(PROMPT)
    demos = request(actor+"/demo-frames")["frames"]
    history = []
    try:
        for i in range(args.max_calls):
            obs = request(actor+"/observe")
            p = payload(model, demos, obs, history)
            (folder/f"{i+1:04}-request.json").write_text(json.dumps(p))
            response = request(base+"/chat/completions", p, {"Authorization": "Bearer "+key})
            d = decision(response["choices"][0]["message"]["content"], obs["tokens"])
            if d["finish"]:
                request(actor+"/submit", {})
                history.append(dict(decision=d, ended=True))
                print("Episode submitted; designer can inspect private results.", flush=True)
                break
            result = request(actor+"/action", dict(left=d["left"], right=d["right"],
                step_mm=d["step_mm"], rotation_deg=d["rotation_deg"], expected_observation=obs["observation_id"]))
            history.append(dict(decision=d, feedback=result))
            (folder/"history.json").write_text(json.dumps(history, ensure_ascii=False, indent=2))
            print(json.dumps(dict(call=i+1, **history[-1]), ensure_ascii=False), flush=True)
        else: print("Call limit reached; paused. Resume with --session "+sid, flush=True)
    except Exception as exc:
        # Provider responses can echo secrets. Persist neither their body nor str(exc).
        print("Paused after "+type(exc).__name__+". No automatic retry. Resume with --session "+sid, flush=True)
        raise SystemExit(1)
    finally:
        (folder/"history.json").write_text(json.dumps(history, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
