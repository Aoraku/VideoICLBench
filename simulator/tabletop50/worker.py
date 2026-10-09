"""Private JSON-lines worker; only images cross the actor observation boundary."""
import contextlib
import json
import sys
import traceback


def main():
    env = None
    try:
        for line in sys.stdin:
            try:
                req = json.loads(line)
                with contextlib.redirect_stdout(sys.stderr):
                    if req["op"] == "init":
                        from .catalog import task_spec
                        from .environment import TabletopDual
                        env = TabletopDual(task_spec(req["task"], req["variant"], req["seed"]), seed=req["seed"])
                        result = {"ready": True}
                    elif req["op"] == "observe": result = {"images": env.images()}
                    elif req["op"] == "action":
                        env.action(req["left"], req["right"]); result = {"accepted": True}
                    elif req["op"] == "score": result = env.score()
                    elif req["op"] == "close": result = {"closed": True}
                    else: raise ValueError("Unknown operation")
                print(json.dumps({"result": result}), flush=True)
                if req["op"] == "close": break
            except Exception:
                traceback.print_exc(file=sys.stderr)
                print(json.dumps({"error": "Private simulation operation failed"}), flush=True)
    finally:
        if env:
            with contextlib.redirect_stdout(sys.stderr): env.close()


if __name__ == "__main__": main()
