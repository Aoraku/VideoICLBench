"""Privileged engineering controller; NEVER report these as agent results."""
import math
import json
import numpy as np

from simulator.benchmark.pilot import Author


class TabletopAuthor(Author):
    def __init__(self, env, folder, seed=0):
        super().__init__(env, folder, record=False, seed=seed)
        self.yaws = [0., 0.]
        self.pitches = [0., 0.]
        self.rest_orientation = [self.wrist_matrix(arm) for arm in (0, 1)]

    def wrist_matrix(self, arm):
        site = self.env.robots[arm].eef_site_id["right"]
        return self.env.sim.data.site_xmat[site].reshape(3, 3).copy()

    def restore_wrist(self, arm):
        from scipy.spatial.transform import Rotation
        for _ in range(120):
            error = Rotation.from_matrix(self.rest_orientation[arm]@self.wrist_matrix(arm).T).as_rotvec()
            if np.linalg.norm(error) < .035:
                self.yaws[arm] = self.pitches[arm] = 0.
                return
            axis = int(np.argmax(np.abs(error)))
            token = ["ROLL", "PITCH", "YAW"][axis]+("_POS" if error[axis] > 0 else "_NEG")
            if abs(error[axis]) < .16: token += "_FINE"
            self.act(arm, token)
        raise RuntimeError("Physical wrist orientation did not converge")

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
        for name, state in self.env.snapshot().items():
            if "hinge_angle" in state:
                snapshot[name].update(hinge_angle=state["hinge_angle"], hinge_velocity=state["hinge_velocity"],
                                      leaf_pos=state["leaf_pos"].tolist(), leaf_mat=state["leaf_mat"].tolist())
        with (self.folder/"trace.private.jsonl").open("a") as stream:
            stream.write(json.dumps(dict(index=len(self.actions), action=pair,
                eef0=self.eef(0).tolist(), eef1=self.eef(1).tolist(), objects=snapshot))+"\n")
        for arm, token in enumerate(pair):
            if token.startswith("YAW_"):
                self.yaws[arm] += math.radians(1 if token.endswith("_FINE") else 10)*(1 if token.startswith("YAW_POS") else -1)
            if token.startswith("PITCH_"):
                self.pitches[arm] += math.radians(1 if token.endswith("_FINE") else 10)*(1 if token.startswith("PITCH_POS") else -1)

    def align(self, arm, angle):
        for _ in range(20):
            error = (angle-self.yaws[arm]+math.pi) % (2*math.pi)-math.pi
            if abs(error) < .1:
                return
            self.act(arm, "YAW_POS" if error > 0 else "YAW_NEG")
        raise RuntimeError("Wrist orientation did not converge")

    def park(self, arm):
        super().park(arm)
        for _ in range(40):
            error = self.pitches[arm]
            if abs(error) < .01: break
            token = "PITCH_NEG" if error > 0 else "PITCH_POS"
            self.act(arm, token+"_FINE" if abs(error) < .09 else token)
        else: raise RuntimeError("Park wrist pitch did not converge")
        self.align(arm, 0.)

    def pick(self, name, arm, grasp_offset=None, lift=True):
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
        if s["kind"] == "ring" and grasp_offset is None: local[0] = (s["size"][0]+s["inner_radius"])/2
        if s["kind"] == "key": local[:2] = [-.015, -.005]
        point = p+self.state(name)["mat"]@local
        approach_height = s.get("approach_height", 1.14)
        self.act(arm, "RELEASE"); self.move(arm, [*point[:2], approach_height])
        offset = min(.005, s["size"][2]*.3)
        target = point+[0., 0., offset]
        self.move(arm, target, axes=(2,))
        self.fine_move(arm, target)
        for attempt in range(3):
            if s["kind"] == "bottle":
                # Cylinders can roll when the descending fingers brush them.
                # Reacquire the actual centre instead of closing repeatedly
                # at an obsolete coordinate.
                current = self.state(name)
                updated = current["pos"]+current["mat"]@local
                if np.linalg.norm(updated-point) > .008:
                    self.move(arm, [*self.eef(arm)[:2], max(.98, updated[2]+.12)], axes=(2,))
                    axis = current["mat"][:, 2]
                    if abs(axis[2]) < .5:
                        self.align(arm, math.atan2(axis[1], axis[0]))
                    point = self.state(name)["pos"]+self.state(name)["mat"]@local
                    target = point+[0., 0., offset]
                    self.move(arm, target, axes=(0, 1))
                    self.move(arm, target, axes=(2,)); self.fine_move(arm, target)
            for _ in range(3): self.act(arm, "GRASP")
            if self.state(name)["grasp"][arm]: break
            self.act(arm, "RELEASE")
            self.fine_move(arm, target+[0., 0., -.003*(attempt+1)], axes=(2,))
        else: raise RuntimeError(f"Physical grasp failed for {name}")
        if lift:
            self.move(arm, [*point[:2], approach_height], axes=(2,))
            if not self.state(name)["grasp"][arm]: raise RuntimeError(f"Dropped {name} after lift")

    def fine_move(self, arm, target, axes=(0, 1, 2), tol=.0018):
        for axis in axes:
            for _ in range(60):
                error = target[axis]-self.eef(arm)[axis]
                if abs(error) <= tol: break
                self.act(arm, (["FWD", "LEFT", "UP"] if error > 0 else ["BACK", "RIGHT", "DOWN"])[axis]+"_FINE")
            else: raise RuntimeError("Fine positioning did not converge")

    def put(self, name, arm, target, fine=False, approach=None, surface_release=False, object_yaw=None, release=True):
        target = np.asarray(target)
        self.move(arm, [*self.eef(arm)[:2], max(1.14, target[2]+.18)], axes=(2,))
        offset = self.eef(arm)-self.state(name)["pos"]
        if approach is None:
            self.move(arm, target+offset, axes=(0, 1)); self.wait(2)
        if object_yaw is not None:
            self.align_object_yaw(arm, name, object_yaw)
            point = self.state(name)["pos"].copy(); point[:2] = target[:2]
            self.object_move(arm, name, point, axes=(0, 1), level=False)
            offset = self.eef(arm)-self.state(name)["pos"]
        if approach is not None:
            # The object approaches from the open end, then translates through
            # both apertures. It is never lowered through the frame roof.
            self.horizontal(arm, name)
            entry = np.asarray(approach).copy(); entry[0] -= .05
            self.object_move(arm, name, entry, axes=(0, 1))
            self.object_move(arm, name, np.asarray(approach), axes=(2, 0, 1))
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
        if not release: return
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

    def align_object_yaw(self, arm, name, target):
        # A held object can twist between the fingertips. Wrist command counts
        # alone do not establish its physical heading.
        for _ in range(70):
            state = self.state(name)
            if not state["grasp"][arm]: raise RuntimeError("Object slipped during yaw alignment")
            heading = math.atan2(state["mat"][1, 0], state["mat"][0, 0])
            # These guide boards have identical ends. Use the nearest
            # equivalent axis heading rather than twisting the wrist 180°.
            error = (target-heading+math.pi/2) % math.pi-math.pi/2
            if abs(error) < .035: return
            token = "YAW_POS" if error > 0 else "YAW_NEG"
            self.act(arm, token+"_FINE" if abs(error) < .17 else token)
        raise RuntimeError("Object yaw did not converge")

    def object_move(self, arm, name, target, axes=(0, 1, 2), stop_goal=None, level=True):
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
                if level and step % 8 == 0: self.horizontal(arm, name)
            else: raise RuntimeError("Shaft positioning did not converge")

    def transport(self, name, arm, xy, bottom=.8, yaw=None, fine=False, approach=None, surface_release=False):
        if self.env.spec["id"] in ("F03", "F07", "F10"):
            self.restore_wrist(arm)
        self.pick(name, arm)
        if yaw is not None:
            a = self.state(name)["mat"]
            current = math.atan2(a[1, 0], a[0, 0])
            self.align(arm, self.yaws[arm]+yaw-current)
        self.put(name, arm, [*xy, bottom+self.env.by_spec[name]["size"][2]], fine, approach, surface_release=surface_release)
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
            if p.get("operation") == "guide_roll":
                self.guide_roll(name, p)
                continue
            if p.get("operation") == "clip_transport":
                self.clip_transport(name, p)
                continue
            if p.get("operation") == "unlock_box":
                self.unlock_box(name, p)
                continue
            if p.get("operation") == "extend_hook":
                self.extend_hook(name, p)
                continue
            if p.get("operation") == "shovel":
                self.shovel(name, p)
                continue
            if p.get("operation") == "corner_push":
                self.corner_push(name, p)
                continue
            if p.get("operation") == "sweep":
                self.sweep(name, p)
                continue
            if p.get("operation") == "fold_display":
                self.fold_display(name, p)
                continue
            if p.get("operation") == "pass_gate":
                self.pass_gate(name, p)
                continue
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
            target_arm = p.get("arm", 0 if p["xy"][1] < -.07 else 1 if p["xy"][1] > .07 else arm)
            if abs(src[1]) < .10: arm = target_arm
            if self.env.spec["id"] == "F07":
                # This compact tabletop classification has no handoff
                # requirement; retain the source-side arm for direct delivery.
                target_arm = arm
            if arm != target_arm:
                state = self.env.snapshot()
                candidates = [[-.08, 0.], [0., 0.], [-.10, .10], [-.10, -.10], [-.28, 0.]]
                free = [xy for xy in candidates if all(n == name or
                    np.any(np.abs(np.asarray(xy)-a["pos"][:2]) >
                        np.asarray(self.env.by_spec[n]["size"][:2])+np.asarray(self.env.by_spec[name]["size"][:2])+.012)
                    for n, a in state.items())]
                if not free: raise RuntimeError("No physically clear hand-relay location")
                self.transport(name, arm, free[0], surface_release=True)
                arm = target_arm
            self.transport(name, arm, p["xy"], p["bottom"], p.get("yaw"), p.get("fine", False),
                           p.get("approach"), surface_release=self.env.spec["id"] in ("F03", "F07", "F10"))
        if self.env.spec["id"] == "F07":
            self.repair_classification()
        if self.env.spec["id"] == "F10":
            self.repair_mosaic()
        self.wait(6)

    def repair_mosaic(self):
        zones = {z["id"]: z for z in self.env.spec["zones"]}
        for _ in range(2):
            for goal in self.env.spec["goals"]:
                state = self.env.snapshot()
                if self.env.predicate(goal, state): continue
                name = goal["object"]
                arm = 0 if state[name]["pos"][1] < 0 else 1
                self.transport(name, arm, zones[goal["target"]]["xy"], surface_release=True)
            if all(self.env.predicate(g, self.env.snapshot()) for g in self.env.spec["goals"]): return

    def repair_classification(self):
        # Containers are movable. A valid classifier follows their actual
        # poses and repairs a spilled item, rather than treating nominal table
        # coordinates as the goal.
        goals = [g for g in self.env.spec["goals"] if g["type"] == "nest"]
        for _ in range(2):
            for goal in goals:
                state = self.env.snapshot()
                if self.env.predicate(goal, state): continue
                name, target = goal["object"], goal["target"]
                siblings = [g["object"] for g in goals if g["target"] == target]
                offset = (siblings.index(name)-.5)*.065
                bowl = state[target]
                point = bowl["pos"]+bowl["mat"]@np.array([0., offset, 0.])
                bottom = bowl["pos"][2]-self.env.by_spec[target]["size"][2]+.008
                arm = 0 if state[name]["pos"][1] < 0 else 1
                self.transport(name, arm, point[:2], bottom, surface_release=True)
            if all(self.env.predicate(g, self.env.snapshot()) for g in goals): return

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
            self.act(arm, "FWD" if self.state(block)["pos"][0] < .13 else "FWD_FINE")
        if ("pushed", block) not in self.env.events: raise RuntimeError("No tool-driven displacement")
        self.put(name, arm, [*plan["return_xy"], resting_height])
        self.park(arm)
        target_arm = 0 if plan["xy"][1] < -.07 else 1 if plan["xy"][1] > .07 else arm
        if target_arm != arm:
            self.transport(block, arm, [-.15, .10], fine=True)
            arm = target_arm
        self.transport(block, arm, plan["xy"], fine=True)

    def sweep(self, name, plan):
        arm = 0 if plan["xy"][1] < 0 else 1
        self.pick(name, arm)
        initial = np.array([self.state(n)["pos"][:2] for n in plan["contents"]])
        centre = initial.mean(axis=0)
        direction = np.array(plan["xy"])-centre; direction /= np.linalg.norm(direction)
        angle = math.atan2(direction[1], direction[0])
        mat = self.state(name)["mat"]
        self.align(arm, self.yaws[arm]+angle-math.atan2(mat[1, 0], mat[0, 0]))
        rear = np.min((initial-centre)@direction)-.045
        start = centre+direction*rear
        self.object_move(arm, name, np.array([*start, .875]), axes=(0, 1, 2, 0, 1))
        finish = np.array(plan["xy"])-direction*.035
        for point in np.linspace(start, finish, 40)[1:]:
            self.object_move(arm, name, np.array([*point, .875]), axes=(0, 1, 2))
            state = self.env.snapshot()
            if all(self.env.predicate(g, state) for g in self.env.spec["goals"]): break
        self.put(name, arm, [*plan["return_xy"], .875], surface_release=True)
        self.park(arm)

    def shovel(self, name, plan):
        block = plan["block"]
        arm = 0 if plan["xy"][1] < 0 else 1
        self.pick(name, arm)
        self.align(arm, self.yaws[arm]-math.atan2(self.state(name)["mat"][1, 0], self.state(name)["mat"][0, 0]))
        p = self.state(block)["pos"].copy()
        entry = np.array([p[0]-.19, p[1], .884])
        self.object_move(arm, name, entry, axes=(0, 1, 2, 0, 1))
        self.object_move(arm, name, np.array([p[0]-.06, p[1], .884]), axes=(0,))
        self.object_move(arm, name, self.state(name)["pos"]+[0., 0., .09], axes=(2,))
        self.wait(3)
        if ("scooped", block) not in self.env.events: raise RuntimeError("No real scoop support after lift")
        destination = np.array([plan["xy"][0]-.11, plan["xy"][1], .94])
        self.object_move(arm, name, destination, axes=(0, 1, 2))
        # Tip the smooth lip toward the pad. Lowering a loaded blade and pulling
        # it backwards can drag the wooden feet instead of releasing the load.
        for _ in range(25): self.act(arm, "PITCH_POS_FINE")
        self.wait(8)
        # The feet now meet the table. Withdraw while still tilted so levelling
        # the blade cannot scoop the deposited coaster up again.
        for _ in range(100):
            tool, load = self.state(name), self.state(block)
            if not tool["grasp"][arm]: raise RuntimeError("Scoop slipped during unloading")
            lip = tool["pos"][0]+tool["mat"][0]@np.array([.14, 0., -.073])
            lip += .022*abs(tool["mat"][0, 1])+.002*abs(tool["mat"][0, 2])
            back = load["pos"][0]-(np.abs(load["mat"])@self.env.by_spec[block]["size"])[0]
            if lip < back-.01 and not self.env.check_contact(self.env.items[name], self.env.items[block]): break
            self.act(arm, "BACK_FINE")
        else: raise RuntimeError("Scoop could not clear the deposited coaster")
        self.fine_move(arm, self.eef(arm)+[0., 0., .08], axes=(2,))
        self.horizontal(arm, name)
        self.put(name, arm, [*plan["return_xy"], .875], surface_release=True)
        self.park(arm)

    def extend_hook(self, name, plan):
        hook, ring = plan["hook"], plan["ring"]
        arm = 0 if self.state(ring)["pos"][1] < 0 else 1; other = 1-arm
        # Pick the rod while the other wrist is parked, then hold it clear of
        # the hook workspace. Crowding two wrists at table level bumps parts.
        self.pick(name, arm)
        self.align_object_yaw(arm, name, 0.)
        self.horizontal(arm, name)
        self.move(arm, [-.35, -.28 if arm == 0 else .28, 1.25])
        self.pick(hook, other)
        self.align_object_yaw(other, hook, 0.); self.horizontal(other, hook)
        self.put(hook, other, [-.12, .15 if other else -.15, .89], release=False)
        self.align_object_yaw(other, hook, 0.)
        target = self.state(hook)["pos"].copy(); target[0] -= .25
        self.object_move(arm, name, target, axes=(1, 2, 0))
        target[0] = self.state(hook)["pos"][0]-.16
        self.object_move(arm, name, target, axes=(0,))
        self.act(other, "RELEASE"); self.move(other, [*self.eef(other)[:2], 1.14], axes=(2,)); self.park(other)
        # Enter below the real canopy; only the extended shaft reaches the ring.
        ring_pos = self.state(ring)["pos"].copy()
        target = [ring_pos[0]-.16-.16, ring_pos[1], .89]
        self.object_move(arm, name, np.array([target[0]-.26, target[1], 1.04]))
        self.object_move(arm, name, np.array([target[0]-.26, target[1], .89]), axes=(2,))
        self.object_move(arm, name, np.array(target), axes=(0,))
        for _ in range(180):
            if self.state(ring)["pos"][0] < .035: break
            self.act(arm, "BACK_FINE")
        else: raise RuntimeError("Extended hook did not retrieve the ring")
        if ("extended_hook", ring) not in self.env.events: raise RuntimeError("No real load transfer through the assembled tool")
        self.object_move(arm, name, self.state(name)["pos"]+[0., 0., .10], axes=(2,))
        self.put(name, arm, [-.19, 0., .89])
        self.park(arm)
        self.pick(hook, other, lift=False)
        self.pick(name, arm, lift=False)
        target = self.state(name)["pos"].copy(); target[0] -= .13
        self.object_move(arm, name, target, axes=(0,))
        self.put(name, arm, [*plan["return_xy"], .89]); self.park(arm)
        self.put(hook, other, [*plan["hook_home"], .89]); self.park(other)
        self.pick(ring, 0, grasp_offset=[-.0325, 0., 0.])
        self.put(ring, 0, [*plan["xy"], .808]); self.park(0)

    def unlock_box(self, name, plan):
        bolt = plan["bolt"]
        bolt_arm = plan["bolt_arm"]; arm = 1-bolt_arm
        self.pick(bolt, bolt_arm, lift=False)
        point = self.state(bolt)["pos"]-self.state(name)["mat"]@np.array([0., .23, 0.])
        self.object_move(bolt_arm, bolt, point, axes=(1,), level=False)
        self.put(bolt, bolt_arm, [*plan["bolt_rest"], .927], surface_release=True)
        self.park(bolt_arm)
        self.panel_grasp(name, arm)
        self.fold_to(name, arm, 1.45)
        for _ in range(3): self.act(arm, "RELEASE")
        # Leave the inclined lid along its outward normal. A vertical retreat
        # sweeps the wrist through the lid and physically knocks it closed.
        normal = self.state(name)["leaf_mat"][:, 2]
        clearance = self.eef(arm)+normal*.12
        axes = tuple(int(i) for i in np.argsort(-np.abs(normal)))
        self.move(arm, clearance, axes=axes)
        safe = [.10, -.28 if arm == 0 else .28, 1.26]
        self.move(arm, safe, axes=(2, 1, 0)); self.park(arm)
        self.restore_wrist(arm)
        self.tip_lid(name, arm, opening=True)
        # Items form a Y row inside the box; close across X so the fingers
        # descend through the empty side lanes rather than neighbouring items.
        item_arm = 0 if self.state(plan["item"])["pos"][1] < 0 else 1
        self.restore_wrist(item_arm)
        self.align(item_arm, math.pi/2)
        self.pick(plan["item"], item_arm)
        self.put(plan["item"], item_arm, [*plan["xy"], .8+self.env.by_spec[plan["item"]]["size"][2]])
        self.park(item_arm)
        self.restore_wrist(arm)
        self.tip_lid(name, arm, opening=False)
        self.panel_grasp(name, arm)
        self.fold_to(name, arm, .002)
        self.act(arm, "RELEASE")
        self.move(arm, safe, axes=(2, 1, 0)); self.park(arm)
        self.restore_wrist(bolt_arm)
        self.pick(bolt, bolt_arm)
        self.align_object_yaw(bolt_arm, bolt, math.atan2(self.state(name)["mat"][1, 0], self.state(name)["mat"][0, 0]))
        box = self.state(name)
        target = box["pos"]+box["mat"]@np.array([.165, -.23, .065])
        self.object_move(bolt_arm, bolt, target, axes=(0, 1, 2, 0), level=False)
        target = box["pos"]+box["mat"]@np.array([.165, 0., .065])
        self.object_move(bolt_arm, bolt, target, axes=(1,), level=False)
        for _ in range(3): self.act(bolt_arm, "RELEASE")
        self.move(bolt_arm, [*self.eef(bolt_arm)[:2], 1.14], axes=(2,)); self.park(bolt_arm)

    def tip_lid(self, name, arm, opening):
        angle = self.state(name)["hinge_angle"]
        if (opening and angle > 1.75) or (not opening and angle < 1.35): return
        self.restore_wrist(arm)
        self.act(arm, "GRASP")
        panel = self.state(name)
        point = panel["leaf_pos"]+panel["leaf_mat"]@np.array([.18, 0., .006])
        direction = 1 if opening else -1
        entry = point+[-direction*.055, 0., 0.]
        self.move(arm, [*entry[:2], 1.32])
        self.move(arm, entry, axes=(2,)); self.fine_move(arm, entry)
        for _ in range(100):
            angle = self.state(name)["hinge_angle"]
            if (opening and angle > 1.75) or (not opening and angle < 1.35): break
            self.act(arm, "FWD_FINE" if opening else "BACK_FINE")
        else: raise RuntimeError("Lid side push did not reach the clear angle")
        self.move(arm, self.eef(arm)+[-direction*.08, 0., 0.], axes=(0,))
        self.move(arm, [*self.eef(arm)[:2], 1.32], axes=(2,))
        self.act(arm, "RELEASE"); self.park(arm)
        self.restore_wrist(arm)

    def clip_transport(self, name, plan):
        plate = plan["plate"]
        arm = 0 if self.state(plate)["pos"][1] < 0 else 1
        handles = [-.055, 0., -.055]
        self.pick(name, arm, grasp_offset=handles)
        angle = self.state(name)["hinge_angle"]
        if angle < .20: raise RuntimeError("Clip jaws did not open under handle pressure")
        point = self.state(plate)["pos"]
        middle = (-.025+.080*math.sin(angle)+.025*math.cos(angle))/2
        target = [point[0]-.080, point[1]-middle, .90]
        self.put(name, arm, target)
        self.park(arm)
        self.pick(name, arm)
        if ("clipped", plate) not in self.env.events: raise RuntimeError("No real two-jaw support after clip lift")
        delta = self.state(plate)["pos"]-self.state(name)["pos"]
        target = [plan["xy"][0]-delta[0], plan["xy"][1]-delta[1], .90]
        self.put(name, arm, target, surface_release=True, release=False)
        # Keep the rigid grip steady while the other hand opens the spring
        # clip. Releasing the whole tool first can tip its upright grip.
        other = 1-arm
        self.pick(name, other, grasp_offset=handles, lift=False)
        if self.state(name)["hinge_angle"] < .20: raise RuntimeError("Clip did not release the racked plate")
        for _ in range(6): self.act_pair("UP", "UP")
        self.act(other, "RELEASE")
        self.park(other)
        self.put(name, arm, [*plan["return_xy"], .90], surface_release=True)
        self.park(arm)

    def guide_roll(self, name, plan):
        start = self.state("ball")["pos"][:2].copy()
        # Leave the gate and its lifting handle unobstructed. The ball first
        # rolls down the open approach, then meets the short guide segments.
        start[0] += .105
        destination = self.state(plan["target"])["pos"][:2].copy()
        end = destination.copy(); end[0] -= .09
        vector = end-start; length = np.linalg.norm(vector)
        direction = vector/length; normal = np.array([-direction[1], direction[0]])
        side = 1 if vector[1] < 0 else -1
        angle = math.atan2(direction[1], direction[0])
        points = [start+direction*.04+normal*side*.038,
                  start+direction*.17+normal*side*.038,
                  start+direction*(length-.04)-normal*side*.050]
        ramp_x = self.env.spec["fixtures"][0]["xy"][0]
        for guide, xy in zip(plan["guides"], points):
            arm = 0 if xy[1] < 0 else 1
            self.pick(guide, arm)
            self.align_object_yaw(arm, guide, angle)
            height = .87-math.tan(plan["slope"])*(xy[0]-ramp_x)
            self.put(guide, arm, [*xy, height+.06], surface_release=True, object_yaw=angle)
            self.park(arm)
        arm = 0 if destination[1] < 0 else 1
        self.pick(name, arm)
        self.put(name, arm, [*plan["return_xy"], .88], surface_release=True)
        self.park(arm)
        self.wait(20)

    def corner_push(self, name, plan):
        block = plan["block"]
        arm = 0 if plan["waypoints"][0][1] < 0 else 1
        self.pick(name, arm)
        for waypoint in plan["waypoints"]:
            target = np.array(waypoint)
            delta = target-self.state(block)["pos"][:2]
            if np.linalg.norm(delta) < .025: continue
            direction = delta/np.linalg.norm(delta)
            angle = math.atan2(direction[1], direction[0])
            self.object_move(arm, name, self.state(name)["pos"]+[0., 0., .12], axes=(2,))
            mat = self.state(name)["mat"]
            self.align(arm, self.yaws[arm]+angle-math.atan2(mat[1, 0], mat[0, 0]))
            start = self.state(block)["pos"][:2]-direction*.051
            self.object_move(arm, name, np.array([*start, .875]), axes=(0, 1, 2))
            for _ in range(200):
                position = self.state(block)["pos"][:2]
                remaining = (target-position)@direction
                if remaining < .008: break
                if not self.state(name)["grasp"][arm]: raise RuntimeError("Corner paddle slipped")
                step = min(.008, remaining)
                point = self.state(name)["pos"].copy()
                point[:2] = position-direction*(.043-step)
                self.object_move(arm, name, point, axes=(0, 1, 2))
            else: raise RuntimeError("Corner pushing did not converge")
        self.object_move(arm, name, self.state(name)["pos"]+[0., 0., .12], axes=(2,))
        self.put(name, arm, [*plan["return_xy"], .875], surface_release=True)
        self.park(arm)

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
            # Leave enough clearance for the palm, not only the ring edge.
            if self.state(ring)["pos"][0] < -.12: break
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

    def pass_gate(self, name, plan):
        arm = 0
        self.pick(name, arm)
        mat = self.state(name)["mat"]
        self.align(arm, self.yaws[arm]-math.atan2(mat[1, 0], mat[0, 0]))
        self.horizontal(arm, name)
        self.object_move(arm, name, np.asarray(plan["approach"]), axes=(0, 1, 2, 0, 1))
        for x in np.linspace(plan["approach"][0], plan["xy"][0], 13)[1:]:
            self.object_move(arm, name, np.array([x, plan["xy"][1], plan["approach"][2]]), axes=(0, 1, 2))
        if ("passed_gate", name) not in self.env.events:
            raise RuntimeError("The complete bar did not pass through the doorway")
        self.move(arm, [*self.eef(arm)[:2], 1.14], axes=(2,))
        mat = self.state(name)["mat"]
        self.align(arm, self.yaws[arm]+plan["yaw"]-math.atan2(mat[1, 0], mat[0, 0]))
        self.put(name, arm, [*plan["xy"], .8+self.env.by_spec[name]["size"][2]],
                 fine=True, surface_release=True)
        self.park(arm)

    def panel_grasp(self, name, arm):
        state = self.state(name)
        angle = state["hinge_angle"]
        grasp = self.env.by_spec[name].get("leaf_grasp", [.145, 0., .018])
        point = state["leaf_pos"]+state["leaf_mat"]@np.array(grasp)
        self.act(arm, "RELEASE")
        self.move(arm, [*point[:2], max(1.10, point[2]+.08)])
        desired_pitch = self.env.by_spec[name].get("leaf_pitch_sign", -1)*angle
        for _ in range(100):
            error = desired_pitch-self.pitches[arm]
            if abs(error) < .025: break
            self.act(arm, "PITCH_POS_FINE" if error > 0 else "PITCH_NEG_FINE")
        self.move(arm, point, axes=(2,)); self.fine_move(arm, point)
        for _ in range(3): self.act(arm, "GRASP")
        if not self.state(name)["grasp"][arm]: raise RuntimeError("Panel handle grasp failed")

    def fold_to(self, name, arm, target, support=None):
        start_state = self.state(name)
        start = start_state["hinge_angle"]
        grasp = self.env.by_spec[name].get("leaf_grasp", [.145, 0., .018])
        if self.env.by_spec[name].get("leaf_grasp_feedback"):
            grasp = start_state["leaf_mat"].T@(self.eef(arm)-start_state["leaf_pos"])
        count = max(1, int(abs(target-start)/math.radians(5)))
        for angle in np.linspace(start, target, count+1)[1:]:
            state = self.state(name)
            if not state["grasp"][arm]: raise RuntimeError("Panel handle slipped")
            if support is not None and self.env.predicate(support, self.env.snapshot()): return
            desired_pitch = self.env.by_spec[name].get("leaf_pitch_sign", -1)*angle
            for _ in range(8):
                error = desired_pitch-self.pitches[arm]
                if abs(error) < .02: break
                self.act(arm, "PITCH_POS_FINE" if error > 0 else "PITCH_NEG_FINE")
            c, s = math.cos(angle), math.sin(angle)
            rotation = np.array([[c, 0., -s], [0., 1., 0.], [s, 0., c]])
            point = state["leaf_pos"]+state["mat"]@rotation@np.array(grasp)
            if self.env.by_spec[name].get("leaf_grasp_feedback"):
                # A jointed lid couples X and Z motion. Correct the current
                # largest error rather than letting it sag during an entire
                # single-axis phase. All corrections are public actions.
                for _ in range(100):
                    error = point-self.eef(arm)
                    if np.max(np.abs(error)) < .004: break
                    axis = int(np.argmax(np.abs(error)))
                    self.act(arm, (["FWD_FINE", "LEFT_FINE", "UP_FINE"] if error[axis] > 0 else
                                   ["BACK_FINE", "RIGHT_FINE", "DOWN_FINE"])[axis])
                else: raise RuntimeError("Coupled lid arc positioning failed")
                continue
            for axis in (2, 0, 1):
                for _ in range(25):
                    if support is not None and self.env.predicate(support, self.env.snapshot()): return
                    error = point[axis]-self.eef(arm)[axis]
                    if abs(error) < .003: break
                    self.act(arm, (["FWD_FINE", "LEFT_FINE", "UP_FINE"] if error > 0 else
                                   ["BACK_FINE", "RIGHT_FINE", "DOWN_FINE"])[axis])
                else: raise RuntimeError("Panel arc positioning failed")

    def fold_display(self, name, plan):
        arm = 0 if plan["xy"][1] < 0 else 1
        self.panel_grasp(name, arm)
        self.fold_to(name, arm, 1.45)
        self.act(arm, "RELEASE"); self.park(arm)
        panel = self.state(name)
        xy = (panel["pos"]+panel["mat"]@np.array([-.04, 0., 0.]))[:2]
        self.pick(plan["support"], arm)
        self.put(plan["support"], arm, [*xy, .83+self.env.by_spec[plan["support"]]["size"][2]],
                 fine=True, surface_release=True)
        self.park(arm)
        support = dict(type="leaf_support", object=name, target=plan["support"])
        state = self.state(name)
        handle = state["leaf_pos"]+state["leaf_mat"]@np.array([.145, 0., .018])
        behind = handle+[-.035, 0., 0.]
        self.act(arm, "GRASP")
        self.move(arm, behind, axes=(0, 1, 2)); self.fine_move(arm, behind)
        for _ in range(90):
            state = self.state(name)
            if 1.02 <= state["hinge_angle"] <= 1.35 and self.env.predicate(support, self.env.snapshot()): break
            self.act(arm, "FWD_FINE")
        else: raise RuntimeError("Display panel did not settle onto its support")
        self.act(arm, "RELEASE"); self.park(arm)
