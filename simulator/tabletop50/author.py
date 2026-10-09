"""Privileged engineering controller; NEVER report these as agent results."""
import math
import json
import numpy as np

from simulator.benchmark.pilot import Author


class TabletopAuthor(Author):
    def __init__(self, env, folder, seed=0):
        super().__init__(env, folder, record=False, seed=seed)
        self.yaws = [0., 0.]

    def act(self, arm, token):
        if len(self.actions) >= self.env.spec["action_budget"]:
            raise RuntimeError("Action budget exhausted")
        pair = ["STILL", "STILL"]; pair[arm] = token
        self.env.action(*pair)
        self.actions.append(dict(left=pair[0], right=pair[1]))
        self.frame()
        snapshot = {k: dict(pos=v["pos"].tolist(), grasp=v["grasp"]) for k, v in self.env.snapshot().items()}
        with (self.folder/"trace.private.jsonl").open("a") as stream:
            stream.write(json.dumps(dict(index=len(self.actions), action=pair,
                eef0=self.eef(0).tolist(), eef1=self.eef(1).tolist(), objects=snapshot))+"\n")
        if token.startswith("YAW_"):
            self.yaws[arm] += math.radians(10)*(1 if token == "YAW_POS" else -1)

    def align(self, arm, angle):
        for _ in range(20):
            error = (angle-self.yaws[arm]+math.pi) % (2*math.pi)-math.pi
            if abs(error) < .1:
                return
            self.act(arm, "YAW_POS" if error > 0 else "YAW_NEG")
        raise RuntimeError("Wrist orientation did not converge")

    def park(self, arm):
        super().park(arm); self.align(arm, 0.)

    def pick(self, name, arm, grasp_offset=None):
        s = self.env.by_spec[name]
        if s["kind"] == "bottle" or (s["kind"] not in ("ring", "key", "lid", "tray", "bowl") and s["size"][0] < s["size"][1]):
            self.align(arm, math.pi/2)
        if s["kind"] == "bar" and s["size"][1] > .04:
            self.align(arm, math.pi/2)
        if s["kind"] == "cup":
            self.align(arm, math.pi/2)
            return super().pick(name, arm, .015)
        p = self.state(name)["pos"].copy()
        local = np.zeros(3)
        if "grasp_local" in s: local = np.array(s["grasp_local"], dtype=float)
        if s["kind"] in ("tray", "bowl"):
            mat = self.state(name)["mat"]
            self.align(arm, math.atan2(mat[1, 0], mat[0, 0]))
            local[1] = (-1 if arm == 0 else 1)*(s["size"][1]-.004)
        if s["kind"] == "ring": local[0] = (s["size"][0]+s["inner_radius"])/2
        if s["kind"] == "key": local[:2] = [-.015, -.005]
        point = p+self.state(name)["mat"]@local
        self.act(arm, "RELEASE"); self.move(arm, [*point[:2], 1.14])
        offset = min(.005, s["size"][2]*.3)
        target = point+[0., 0., offset]
        self.move(arm, target, axes=(2,))
        self.fine_move(arm, target)
        for attempt in range(3):
            for _ in range(3): self.act(arm, "GRASP")
            if self.state(name)["grasp"][arm]: break
            self.act(arm, "RELEASE")
            self.fine_move(arm, target+[0., 0., -.003*(attempt+1)], axes=(2,))
        else: raise RuntimeError(f"Physical grasp failed for {name}")
        self.move(arm, [*point[:2], 1.14], axes=(2,))
        if not self.state(name)["grasp"][arm]: raise RuntimeError(f"Dropped {name} after lift")

    def fine_move(self, arm, target, axes=(0, 1, 2), tol=.0018):
        for axis in axes:
            for _ in range(60):
                error = target[axis]-self.eef(arm)[axis]
                if abs(error) <= tol: break
                self.act(arm, (["FWD", "LEFT", "UP"] if error > 0 else ["BACK", "RIGHT", "DOWN"])[axis]+"_FINE")
            else: raise RuntimeError("Fine positioning did not converge")

    def put(self, name, arm, target, fine=False, approach=None):
        target = np.asarray(target)
        self.move(arm, [*self.eef(arm)[:2], max(1.14, target[2]+.18)], axes=(2,))
        offset = self.eef(arm)-self.state(name)["pos"]
        self.move(arm, target+offset, axes=(0, 1)); self.wait(2)
        if approach is not None:
            # The object approaches from the open end, then translates through
            # both apertures. It is never lowered through the frame roof.
            p = np.asarray(approach)+offset
            self.move(arm, p, axes=(0, 1, 2)); self.fine_move(arm, p)
            self.move(arm, target+offset, axes=(0,))
            self.fine_move(arm, target+offset)
        elif fine:
            self.fine_move(arm, target+offset, axes=(0, 1))
        for _ in range(35):
            state = self.state(name)
            extent = (np.abs(state["mat"]) @ self.env.by_spec[name]["size"])[2]
            if state["pos"][2]-extent <= target[2]-self.env.by_spec[name]["size"][2]+.018:
                break
            self.act(arm, "DOWN")
        if approach is None:
            self.fine_move(arm, target+offset+[0., 0., .003], axes=(2,))
        for _ in range(3): self.act(arm, "RELEASE")
        self.move(arm, [*self.eef(arm)[:2], 1.14], axes=(2,)); self.wait(3)

    def transport(self, name, arm, xy, bottom=.8, yaw=None, fine=False, approach=None):
        self.pick(name, arm)
        if yaw is not None:
            a = self.state(name)["mat"]
            current = math.atan2(a[1, 0], a[0, 0])
            self.align(arm, self.yaws[arm]+yaw-current)
        self.put(name, arm, [*xy, bottom+self.env.by_spec[name]["size"][2]], fine, approach)
        self.park(arm)

    def solve(self):
        self.park(0); self.park(1)
        for p in self.env.spec["author_plan"]:
            name = p["object"]
            src = self.state(name)["pos"]
            arm = 0 if src[1] < 0 else 1
            target_arm = 0 if p["xy"][1] < -.07 else 1 if p["xy"][1] > .07 else arm
            if arm != target_arm:
                state = self.env.snapshot()
                candidates = [[-.08, 0.], [0., 0.], [-.10, .10], [-.10, -.10], [-.28, 0.]]
                free = [xy for xy in candidates if all(n == name or
                    np.any(np.abs(np.asarray(xy)-a["pos"][:2]) >
                        np.asarray(self.env.by_spec[n]["size"][:2])+np.asarray(self.env.by_spec[name]["size"][:2])+.012)
                    for n, a in state.items())]
                if not free: raise RuntimeError("No physically clear hand-relay location")
                self.transport(name, arm, free[0])
                arm = target_arm
            self.transport(name, arm, p["xy"], p["bottom"], p.get("yaw"), p.get("fine", False), p.get("approach"))
        self.wait(6)
