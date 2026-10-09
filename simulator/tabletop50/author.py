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
        pair = ["STILL", "STILL"]; pair[arm] = token
        self.act_pair(*pair)

    def act_pair(self, left, right):
        if len(self.actions) >= self.env.spec["action_budget"]:
            raise RuntimeError("Action budget exhausted")
        pair = [left, right]
        self.env.action(*pair)
        self.actions.append(dict(left=pair[0], right=pair[1]))
        self.frame()
        snapshot = {k: dict(pos=v["pos"].tolist(), mat=v["mat"].tolist(), grasp=v["grasp"]) for k, v in self.env.snapshot().items()}
        with (self.folder/"trace.private.jsonl").open("a") as stream:
            stream.write(json.dumps(dict(index=len(self.actions), action=pair,
                eef0=self.eef(0).tolist(), eef1=self.eef(1).tolist(), objects=snapshot))+"\n")
        for arm, token in enumerate(pair):
            if token.startswith("YAW_"):
                self.yaws[arm] += math.radians(1 if token.endswith("_FINE") else 10)*(1 if token.startswith("YAW_POS") else -1)

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
        if s["kind"] == "box" and any(b["kind"] in ("tray", "bowl")
                and np.all(np.abs(self.state(name)["pos"][:2]-self.state(n)["pos"][:2]) < np.asarray(b["size"][:2])-.01)
                for n,b in self.env.by_spec.items() if n != name):
            self.align(arm, math.pi/2)
        if s["kind"] == "bar" and s["size"][1] > .04:
            self.align(arm, math.pi/2)
        if s["kind"] == "cup" and "grasp_local" not in s:
            self.align(arm, math.pi/2)
            return super().pick(name, arm, .015)
        p = self.state(name)["pos"].copy()
        local = np.zeros(3)
        if "grasp_local" in s: local = np.array(s["grasp_local"], dtype=float)
        if s["kind"] == "cup" and "grasp_sides" in s:
            local = np.array(s["grasp_sides"][arm], dtype=float)
            self.align(arm, math.pi/2 if arm == 0 else -math.pi/2)
        if grasp_offset is not None: local = np.array(grasp_offset, dtype=float)
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

    def put(self, name, arm, target, fine=False, approach=None, surface_release=False):
        target = np.asarray(target)
        self.move(arm, [*self.eef(arm)[:2], max(1.14, target[2]+.18)], axes=(2,))
        offset = self.eef(arm)-self.state(name)["pos"]
        self.move(arm, target+offset, axes=(0, 1)); self.wait(2)
        if approach is not None:
            # The object approaches from the open end, then translates through
            # both apertures. It is never lowered through the frame roof.
            self.horizontal(arm, name)
            self.object_move(arm, name, np.asarray(approach))
            terminal = next((g for g in self.env.spec["goals"]
                             if g["object"] == name and g["type"] == "through_apertures"), None)
            self.object_move(arm, name, target, axes=(0,), stop_goal=terminal)
        elif fine:
            self.fine_move(arm, target+offset, axes=(0, 1))
        for _ in range(35):
            state = self.state(name)
            extent = (np.abs(state["mat"]) @ self.env.by_spec[name]["size"])[2]
            if state["pos"][2]-extent <= target[2]-self.env.by_spec[name]["size"][2]+.018:
                break
            self.act(arm, "DOWN")
        if approach is None:
            state = self.state(name)
            bottom = state["pos"][2]-(np.abs(state["mat"]) @ self.env.by_spec[name]["size"])[2]
            if not (surface_release and bottom <= target[2]-self.env.by_spec[name]["size"][2]+.018):
                self.fine_move(arm, target+offset+[0., 0., .003], axes=(2,))
        for _ in range(3): self.act(arm, "RELEASE")
        self.move(arm, [*self.eef(arm)[:2], 1.14], axes=(2,)); self.wait(3)

    def horizontal(self, arm, name):
        for _ in range(50):
            mat = self.state(name)["mat"]
            angle = math.atan2(mat[2, 0], math.hypot(mat[0, 0], mat[1, 0]))
            if abs(angle) < .025: return
            token = "PITCH_POS" if angle > 0 else "PITCH_NEG"
            self.act(arm, token+"_FINE" if abs(angle) < .09 else token)
        raise RuntimeError("Shaft pitch did not converge")

    def object_move(self, arm, name, target, axes=(0, 1, 2), stop_goal=None):
        # Off-centre grasps flex under load. Re-read physical pose rather than
        # assuming a fixed transform between the fingers and the shaft.
        for axis in axes:
            for step in range(180):
                state = self.state(name)
                if stop_goal is not None and self.env.predicate(stop_goal, self.env.snapshot()): return
                if not state["grasp"][arm]: raise RuntimeError("Shaft slipped")
                error = target[axis]-state["pos"][axis]
                if abs(error) < .0025: break
                token = (["FWD", "LEFT", "UP"] if error > 0 else ["BACK", "RIGHT", "DOWN"])[axis]
                if abs(error) < .035: token += "_FINE"
                self.act(arm, token)
                if step % 8 == 0: self.horizontal(arm, name)
            else: raise RuntimeError("Shaft positioning did not converge")

    def transport(self, name, arm, xy, bottom=.8, yaw=None, fine=False, approach=None):
        self.pick(name, arm)
        if yaw is not None:
            a = self.state(name)["mat"]
            current = math.atan2(a[1, 0], a[0, 0])
            self.align(arm, self.yaws[arm]+yaw-current)
        self.put(name, arm, [*xy, bottom+self.env.by_spec[name]["size"][2]], fine, approach)
        self.park(arm)

    def dual_transport(self, name, xy, bottom):
        """Opposite wall grasps balance the load; no object attachment."""
        s = self.env.by_spec[name]
        for arm in (0, 1):
            a = self.state(name)
            self.align(arm, math.atan2(a["mat"][1, 0], a["mat"][0, 0]))
            local = np.array(s["grasp_sides"][arm] if "grasp_sides" in s else
                             [0., (-1 if arm == 0 else 1)*(s["size"][1]-.004), .008])
            target = a["pos"]+a["mat"]@local
            self.act(arm, "RELEASE"); self.move(arm, [*target[:2], 1.15])
            self.move(arm, target, axes=(2,)); self.fine_move(arm, target)
            for _ in range(3): self.act(arm, "GRASP")
        for attempt in range(3):
            if all(self.state(name)["grasp"]): break
            for arm in (0, 1):
                state = self.state(name)
                if state["grasp"][arm]: continue
                local = np.array(s["grasp_sides"][arm] if "grasp_sides" in s else
                                 [0., (-1 if arm == 0 else 1)*(s["size"][1]-.004), .008])
                target = state["pos"]+state["mat"]@(local+[0., 0., -.003*attempt])
                self.act(arm, "RELEASE"); self.fine_move(arm, target)
                for _ in range(3): self.act(arm, "GRASP")
        if not all(self.state(name)["grasp"]): raise RuntimeError("Both tray wall grasps required")

        def axis_to(axis, target):
            history = []
            for _ in range(100):
                state = self.state(name)
                error = target-state["pos"][axis]
                if abs(error) < .003: return
                if not all(state["grasp"]): raise RuntimeError("Tray slipped during coordinated carry")
                history.append(state["pos"][axis])
                if len(history) > 12 and max(history[-10:])-min(history[-10:]) < .001:
                    raise RuntimeError("Tray translation blocked")
                token = (["FWD", "LEFT", "UP"] if error > 0 else ["BACK", "RIGHT", "DOWN"])[axis]
                if abs(error) < .024: token += "_FINE"
                self.act_pair(token, token)
            raise RuntimeError("Coordinated tray movement did not converge")

        axis_to(2, 1.05)
        axis_to(0, xy[0]); axis_to(1, xy[1])
        axis_to(2, bottom+s["size"][2]+.003)
        for _ in range(3): self.act_pair("RELEASE", "RELEASE")
        for _ in range(5): self.act_pair("UP", "UP")
        self.park(0); self.park(1); self.wait(3)

    def solve(self):
        self.park(0); self.park(1)
        for p in self.env.spec["author_plan"]:
            name = p["object"]
            if p.get("operation") == "hook":
                self.hook(name, p)
                continue
            if p.get("operation") == "push":
                self.push(name, p)
                continue
            if p.get("operation") == "pour":
                self.pour(name, p)
                continue
            if p.get("operation") == "handover":
                self.handover(name, p)
                continue
            if self.env.by_spec[name]["kind"] == "tray":
                self.dual_transport(name, p["xy"], p["bottom"])
                continue
            src = self.state(name)["pos"]
            arm = 0 if src[1] < 0 else 1
            target_arm = 0 if p["xy"][1] < -.07 else 1 if p["xy"][1] > .07 else arm
            if abs(src[1]) < .10: arm = target_arm
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

    def handover(self, name, plan):
        self.pick(name, 0, plan["giver_grasp"])
        self.object_move(0, name, np.array([-.08, 0., 1.04]))
        state = self.state(name)
        local = np.array(plan["receiver_grasp"])
        point = state["pos"]+state["mat"]@local
        self.align(1, math.pi/2)
        self.act(1, "RELEASE")
        self.move(1, [*point[:2], 1.15])
        self.move(1, point, axes=(2,)); self.fine_move(1, point)
        for attempt in range(3):
            state = self.state(name)
            point = state["pos"]+state["mat"]@(local+[0., 0., -.004*attempt])
            self.fine_move(1, point)
            for _ in range(3): self.act(1, "GRASP")
            if self.state(name)["grasp"][1]: break
            self.act(1, "RELEASE")
        else: raise RuntimeError("Receiver did not grasp baton")
        for _ in range(3): self.act(0, "RELEASE")
        self.park(0)
        self.wait(2)
        if ("handover", name) not in self.env.events: raise RuntimeError("No airborne transfer recorded")
        mat = self.state(name)["mat"]
        current = math.atan2(mat[1, 0], mat[0, 0])
        self.align(1, self.yaws[1]+plan["yaw"]-current)
        self.put(name, 1, [*plan["xy"], plan["bottom"]+self.env.by_spec[name]["size"][2]], fine=True)
        self.park(1)

    def pour(self, name, plan):
        arm = 0 if plan["xy"][1] < 0. else 1
        self.pick(name, arm)
        offset = self.eef(arm)-self.state(name)["pos"]
        target = np.array([plan["xy"][0]-.035, plan["xy"][1], 1.02])+offset
        self.move(arm, target); self.fine_move(arm, target)
        for _ in range(14): self.act(arm, "PITCH_POS")
        self.wait(12)
        if not all(("poured", n) in self.env.events for n in plan["contents"]):
            raise RuntimeError("Some contents did not physically pour from the cup")
        for _ in range(14): self.act(arm, "PITCH_NEG")
        self.put(name, arm, [*plan["return_xy"], .8+self.env.by_spec[name]["size"][2]])
        self.park(arm)

    def push(self, name, plan):
        block = plan["block"]
        arm = 0 if plan["start_xy"][1] < .05 else 1
        self.pick(name, arm)
        state = self.state(block)
        resting_height = .8+self.env.by_spec[name]["size"][2]
        point = np.array([state["pos"][0]-.022-.12-.012, state["pos"][1], resting_height])
        offset = self.eef(arm)-self.state(name)["pos"]
        self.move(arm, point+offset, axes=(0, 1, 2)); self.fine_move(arm, point+offset)
        for _ in range(150):
            if self.state(block)["pos"][0] > .17: break
            if not self.state(name)["grasp"][arm]: raise RuntimeError("Pusher slipped")
            self.act(arm, "FWD_FINE")
        if ("pushed", block) not in self.env.events: raise RuntimeError("No tool-driven displacement")
        self.put(name, arm, [*plan["return_xy"], resting_height])
        self.park(arm)
        target_arm = 0 if plan["xy"][1] < -.07 else 1 if plan["xy"][1] > .07 else arm
        if target_arm != arm:
            self.transport(block, arm, [-.15, .10], fine=True)
            arm = target_arm
        self.transport(block, arm, plan["xy"], fine=True)

    def hook(self, name, plan):
        ring = plan["block"]
        arm = 0 if plan["start_xy"][1] < .05 else 1
        self.pick(name, arm)
        p = self.state(ring)["pos"]
        above = np.array([p[0]-.10, p[1], .915])
        # Lower outside the stand, then enter below its roof. Lowering from
        # above the ring would drive the shaft through the solid roof.
        entry = np.array([-.08, p[1], .915])
        self.object_move(arm, name, entry, axes=(0, 1, 2))
        self.object_move(arm, name, above, axes=(0,))
        resting = above.copy(); resting[2] = .875
        self.object_move(arm, name, resting, axes=(2,))
        for _ in range(160):
            if self.state(ring)["pos"][0] < -.065: break
            if not self.state(name)["grasp"][arm]: raise RuntimeError("Hook slipped")
            self.act(arm, "BACK_FINE")
        if ("hooked", ring) not in self.env.events: raise RuntimeError("Ring was not pulled by the hook")
        # The hook is entirely outside the stand before raising the downturned
        # tip. This disengages it through the real ring opening.
        self.put(name, arm, [*plan["return_xy"], .875])
        self.park(arm)
        if arm != 0:
            self.transport(ring, arm, [-.15, .10], fine=True)
        self.pick(ring, 0)
        self.put(ring, 0, [*plan["xy"], .8+self.env.by_spec[ring]["size"][2]],
                 fine=True, surface_release=True)
        self.park(0)
