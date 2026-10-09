"""Real MuJoCo contacts and dual-Panda actions, with a first-person-like camera.

This is a simulated camera, not evidence that a human recording has been made.
"""
import math
import xml.etree.ElementTree as ET

import numpy as np
from robosuite.models.arenas import TableArena
from robosuite.models.tasks import ManipulationTask
from robosuite.models.objects import CompositeObject
from robosuite.utils.transform_utils import mat2quat
from .geometry import make_prop
from .protocol import TOKENS

from simulator.benchmark.environment import DesktopDual, make_object


def marker(body, xy, index, radius=.045, z=.803):
    count = (16, 3, 4)[index]
    points = [[xy[0]+radius*math.cos(2*math.pi*i/count),
               xy[1]+radius*math.sin(2*math.pi*i/count), z] for i in range(count)]
    for i, a in enumerate(points):
        b = points[(i+1) % count]
        ET.SubElement(body, "geom", type="capsule", size=".002",
                      fromto=" ".join(map(str, a+b)), rgba=".95 .85 .15 1",
                      contype="0", conaffinity="0", group="1")


class TabletopDual(DesktopDual):
    def _load_model(self):
        # Preserve existing motor/controller physics; build a new tabletop scene.
        super(DesktopDual, self)._load_model()
        for robot, offset in zip(self.robots, (-.25, .25)):
            base = np.array(robot.robot_model.base_xpos_offset["table"](.8))+[0, offset, 0]
            robot.robot_model.set_base_xpos(base)
        arena = TableArena(table_full_size=(.8, .8, .05), table_offset=self.table_offset,
                           table_friction=(1, .005, .0001))
        arena.set_origin([0, 0, 0])
        for i, f in enumerate(self.spec.get("fixtures", [])):
            ET.SubElement(arena.worldbody, "geom", name=f"fixture{i}", type=f["type"],
                          size=" ".join(map(str, f["size"])),
                          pos=" ".join(map(str, f["xy"]+[f["z"]])),
                          rgba=" ".join(map(str, f["rgba"])), friction="1 .005 .0001")
        for zone in self.spec["zones"]:
            ET.SubElement(arena.worldbody, "geom", name="zone_"+zone["id"], type="box",
                          size=" ".join(map(str, zone["half_size"]+[.001])),
                          pos=" ".join(map(str, zone["xy"]+[.801])),
                          rgba=".30 .37 .44 1", contype="0", conaffinity="0", group="1")
            marker(arena.worldbody, zone["xy"], zone.get("marker", 0))
        position = np.array([-.55, 0., 1.48])
        target = np.array([.03, 0., .82])
        back = (position-target)/np.linalg.norm(position-target)
        right = np.cross([0, 0, 1], back); right /= np.linalg.norm(right)
        up = np.cross(back, right)
        q = mat2quat(np.column_stack([right, up, back]))[[3, 0, 1, 2]]
        ET.SubElement(arena.worldbody, "camera", name="fpv", fovy="65",
                      pos=" ".join(map(str, position)), quat=" ".join(map(str, q)))
        self.items = {}
        for s in self.spec["objects"]:
            if s["kind"] == "lid":
                x, y, z = s["size"]
                item = CompositeObject(name=s["id"], total_size=[x, y, z],
                    geom_types=["box", "box"], geom_sizes=[[x, y, .004], [.018, .018, z-.004]],
                    geom_locations=[[0, 0, -z+.004], [0, 0, .004]],
                    geom_rgbas=[s["rgba"]]*2, locations_relative_to_center=True,
                    density=200, geom_frictions=[(1, .005, .0001)]*2)
            else:
                item = make_prop(s)
            if s["kind"] == "arrow_bar":
                b = item.get_obj()
                x, y, z = s["size"]
                for a, end in (([-x*.6, 0, z+.002], [x*.6, 0, z+.002]),
                               ([x*.6, 0, z+.002], [x*.2, y*.65, z+.002]),
                               ([x*.6, 0, z+.002], [x*.2, -y*.65, z+.002])):
                    ET.SubElement(b, "geom", type="capsule", size=".002",
                                  fromto=" ".join(map(str, a+end)), rgba="1 1 1 1",
                                  contype="0", conaffinity="0", group="1")
            if s["id"].startswith("bin"):
                # Marker at rim height, just beyond the interior contents.
                marker(item.get_obj(), [0, -s["size"][1]+.012], int(s["id"][-1]), radius=.008, z=s["size"][2]+.002)
            self.items[s["id"]] = item
        self.model = ManipulationTask(mujoco_arena=arena,
            mujoco_robots=[r.robot_model for r in self.robots], mujoco_objects=list(self.items.values()))
        # Flat convex mesh faces need a contact manifold rather than a single
        # libccd contact. Otherwise triangular pieces slowly slide while idle.
        option = self.model.root.find("option")
        if option is None: option = ET.SubElement(self.model.root, "option")
        flag = option.find("flag")
        if flag is None: flag = ET.SubElement(option, "flag")
        flag.set("multiccd", "enable")

    def _reset_internal(self):
        super()._reset_internal()
        if not self.deterministic_reset:
            for s in self.spec["objects"]:
                if "bottom" in s:
                    q = [math.cos(s["yaw"]/2), 0, 0, math.sin(s["yaw"]/2)]
                    self.sim.data.set_joint_qpos(self.items[s["id"]].joints[0],
                        (np.array(s["xy"])+self.layout_jitter).tolist()+[s["bottom"]+s["size"][2]]+q)
            self.sim.forward()

    def predicate(self, g, state):
        if g["type"] == "bridge":
            beam = state[g["object"]]
            return bool(beam["mat"][2, 2] > .97 and
                all(self.check_contact(self.items[g["object"]], self.items[s]) for s in g["supports"]))
        if g["type"] == "cap_on":
            a, b = state[g["object"]], state[g["target"]]
            top = b["pos"][2]+self.by_spec[g["target"]]["size"][2]
            return bool(np.linalg.norm(a["pos"][:2]-b["pos"][:2]) < .008
                and a["mat"][2, 2] > .97 and abs(a["pos"][2]+.014-top) < .008
                and self.check_contact(self.items[g["object"]], self.items[g["target"]]))
        if g["type"] == "count_in":
            count = sum(self.predicate(dict(type="nest", object=n, target=g["target"]), state) for n in g["objects"])
            return count == g["count"]
        if g["type"] == "local_position":
            a, b = state[g["object"]], state[g["target"]]
            local = b["mat"].T@(a["pos"]-b["pos"])
            return bool(np.linalg.norm(local[:2]-g["xy"]) < g["tolerance"])
        if g["type"] == "row_lengths":
            used, totals = set(), []
            for ref in g["references"]:
                r = state[ref]; length = self.by_spec[ref]["size"][0]
                if abs(math.atan2(r["mat"][1, 0], r["mat"][0, 0])) > .12: return False
                end = r["pos"][0]+length
                candidates = [n for n in g["candidates"] if abs(state[n]["pos"][1]-r["pos"][1]) < .012
                    and abs(state[n]["pos"][0]-self.by_spec[n]["size"][0]-end) < .006
                    and abs(math.atan2(state[n]["mat"][1, 0], state[n]["mat"][0, 0])) < .12]
                if len(candidates) != 1 or candidates[0] in used: return False
                used.add(candidates[0]); totals.append(2*(length+self.by_spec[candidates[0]]["size"][0]))
            if g["relation"] == "equal": return max(totals)-min(totals) < .003
            delta = np.diff(totals)
            return bool(np.all(delta > .005) if g["relation"] == "increasing" else np.all(delta < -.005))
        if g["type"] in ("insert", "threaded"):
            a, b = state[g["object"]], state[g["target"]]
            sa = self.by_spec[g["object"]]
            sb = self.by_spec[g["target"]]
            local = b["mat"].T@(a["pos"]-b["pos"])
            tolerance = g.get("tolerance", .015)
            target_bottom = g.get("relative_bottom", -sb["size"][2]+.008)
            contact = self.check_contact(self.items[g["object"]], self.items[g["target"]]) if g["type"] == "threaded" else self.check_contact(self.items[g["object"]], "table_collision")
            return bool(np.linalg.norm(local[:2]) < tolerance and a["mat"][2, 2] > .97
                and abs(local[2]-sa["size"][2]-target_bottom) < .008 and contact)
        if g["type"] == "shaft_height":
            return bool(abs(state[g["object"]]["pos"][2]-g["z"]) < .008)
        if g["type"] == "cover":
            a, b = state[g["object"]], state[g["target"]]
            size = np.array(self.by_spec[g["object"]]["size"])
            target = np.array(self.by_spec[g["target"]]["size"])
            return bool(np.linalg.norm(a["pos"][:2]-b["pos"][:2]) < .018
                and a["mat"][2, 2] > .97
                and abs(a["pos"][2]-size[2]-b["pos"][2]-target[2]) < .012
                and self.check_contact(self.items[g["object"]], self.items[g["target"]]))
        return super().predicate(g, state)

    def action(self, left="STILL", right="STILL"):
        if left not in TOKENS or right not in TOKENS:
            raise ValueError("Unknown action token")
        motion = {"FWD": (0, 1), "BACK": (0, -1), "LEFT": (1, 1), "RIGHT": (1, -1),
                  "UP": (2, 1), "DOWN": (2, -1), "ROLL_POS": (3, 1), "ROLL_NEG": (3, -1),
                  "PITCH_POS": (4, 1), "PITCH_NEG": (4, -1), "YAW_POS": (5, 1), "YAW_NEG": (5, -1)}
        action = np.zeros(14)
        for i, token in enumerate((left, right)):
            if token == "GRASP": self.grips[i] = 1.
            if token == "RELEASE": self.grips[i] = -1.
            fine = token.endswith("_FINE")
            base = token[:-5] if fine else token
            if base in motion:
                axis, sign = motion[base]
                delta = (.002 if fine else .02) if axis < 3 else math.radians(1 if fine else 10)
                action[i*7+axis] = sign*delta/(.05 if axis < 3 else .5)
            action[i*7+6] = self.grips[i]
        for _ in range(8):
            self.step(action); self.track()
            action[:6] = 0.; action[7:13] = 0.

    def track(self):
        state = self.snapshot()
        for name, a in state.items():
            extent = (np.abs(a["mat"]) @ self.by_spec[name]["size"])[2]
            airborne = a["pos"][2]-extent > .83
            if not airborne: self._left_airborne.discard(name)
            if a["grasp"][0] and airborne: self._left_airborne.add(name)
            receive = a["grasp"][1] and not a["grasp"][0] and airborne and name in self._left_airborne
            self._receive_hold[name] = self._receive_hold.get(name, 0)+1 if receive else 0
            if self._receive_hold[name] >= 4: self.events.add(("handover", name))
        support_names = ["table_collision"]+[f"fixture{i}" for i in range(len(self.spec.get("fixtures", [])))]
        grounded = {k for k, item in self.items.items() if any(self.check_contact(item, geom) for geom in support_names)}
        pending = set(state)-grounded
        while pending:
            supported = {k for k in pending if any(self.check_contact(self.items[k], self.items[b]) for b in grounded)}
            if not supported: break
            grounded.update(supported); pending -= supported
        stable = all(np.linalg.norm(a["pos"]-self.last_positions[k]) < .002 for k,a in state.items())
        released = not any(any(a["grasp"]) for a in state.values())
        valid = all(self.predicate(g, state) for g in self.spec["goals"]) and released and not pending and stable
        self.terminal_hold = self.terminal_hold+1 if valid else 0
        self.last_positions = {k:a["pos"].copy() for k,a in state.items()}

    def images(self):
        import base64
        import io
        from PIL import Image
        out = {}
        for camera in ("fpv", "robot0_eye_in_hand", "robot1_eye_in_hand"):
            pixels = self.sim.render(width=640, height=480, camera_name=camera)[::-1]
            stream = io.BytesIO(); Image.fromarray(pixels).save(stream, format="JPEG", quality=85)
            out[camera] = base64.b64encode(stream.getvalue()).decode()
        return out

    def score(self):
        result = super().score()
        # The only benchmark metric is terminal success. Hold time is settling,
        # never an additional weighted score or a mandated human motion.
        result["metric"] = "success"
        return result
