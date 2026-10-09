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

# Calibrated by public OSC translations into the common neutral park pose.
# These are robot reset joint angles, never object poses or execution shortcuts.
PARKED_QPOS = [
    [-.03395135, -.22716472, -.10953163, -2.63339316, -.01123396, 2.53422036, .65174551],
    [.03257663, -.22772450, .10904006, -2.63434086, .01100924, 2.53488572, .91832738],
]


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
        for robot, offset, qpos in zip(self.robots, (-.25, .25), PARKED_QPOS):
            base = np.array(robot.robot_model.base_xpos_offset["table"](.8))+[0, offset, 0]
            robot.robot_model.set_base_xpos(base)
            robot.init_qpos = np.array(qpos)
        arena = TableArena(table_full_size=(.8, .8, .05), table_offset=self.table_offset,
                           table_friction=(1, .005, .0001))
        arena.set_origin([0, 0, 0])
        for i, f in enumerate(self.spec.get("fixtures", [])):
            ET.SubElement(arena.worldbody, "geom", name=f"fixture{i}", type=f["type"],
                          group="1",
                          quat=" ".join(map(str, f.get("quat", [1, 0, 0, 0]))),
                          size=" ".join(map(str, f["size"])),
                          pos=" ".join(map(str, f["xy"]+[f["z"]])),
                          rgba=" ".join(map(str, f["rgba"])), friction="1 .005 .0001")
        for zone in self.spec["zones"]:
            ET.SubElement(arena.worldbody, "geom", name="zone_"+zone["id"], type="box",
                          size=" ".join(map(str, zone["half_size"]+[.001])),
                          pos=" ".join(map(str, zone["xy"]+[.801])),
                          rgba=".30 .37 .44 1", contype="0", conaffinity="0", group="1")
            if zone.get("marker", 0) is not None:
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
                z = s.get("arrow_z", z)
                for a, end in (([-x*.6, 0, z+.002], [x*.6, 0, z+.002]),
                               ([x*.6, 0, z+.002], [x*.2, y*.65, z+.002]),
                               ([x*.6, 0, z+.002], [x*.2, -y*.65, z+.002])):
                    ET.SubElement(b, "geom", type="capsule", size=".002",
                                  fromto=" ".join(map(str, a+end)), rgba="1 1 1 1",
                                  contype="0", conaffinity="0", group="1")
            if s["id"].startswith("bin"):
                # Marker at rim height, just beyond the interior contents.
                marker(item.get_obj(), [0, -s["size"][1]+.012], int(s["id"][-1]), radius=.008, z=s["size"][2]+.002)
            if "marker" in s:
                z = -s["size"][2]+.009 if s["kind"] == "post" else s["size"][2]+.002
                marker(item.get_obj(), [0, -s["size"][1]+.016], s["marker"], radius=.012, z=z)
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
        self._pour_inside = {}
        self._manually_handled = set()
        self._tool_contact_origins = {}
        self._gate_entered = set()
        self._scoop_hold = {}
        if not self.deterministic_reset:
            for s in self.spec["objects"]:
                if "bottom" in s:
                    q = [math.cos(s["yaw"]/2), 0, 0, math.sin(s["yaw"]/2)]
                    self.sim.data.set_joint_qpos(self.items[s["id"]].joints[0],
                        (np.array(s["xy"])+self.layout_jitter).tolist()+[s["bottom"]+s["size"][2]]+q)
            self.sim.forward()

    def snapshot(self):
        state = super().snapshot()
        for name, spec in self.by_spec.items():
            if spec["kind"] not in ("hinged_panel", "spring_clip", "latched_box"): continue
            prefix = self.items[name].naming_prefix
            state[name]["hinge_angle"] = float(self.sim.data.get_joint_qpos(prefix+"hinge"))
            state[name]["hinge_velocity"] = float(self.sim.data.get_joint_qvel(prefix+"hinge"))
            state[name]["leaf_pos"] = self.sim.data.get_body_xpos(prefix+"leaf").copy()
            state[name]["leaf_mat"] = self.sim.data.get_body_xmat(prefix+"leaf").reshape(3, 3).copy()
        return state

    def predicate(self, g, state):
        if g["type"] == "rack_slot":
            item = state[g["object"]]
            extent = np.abs(item["mat"])@np.asarray(self.by_spec[g["object"]]["size"])
            inside = np.all(np.abs(item["pos"][:2]-g["xy"])+extent[:2]
                            <= np.asarray(g["half_opening"])+.0005)
            bottom = item["pos"][2]-extent[2]
            return bool(inside and .799 <= bottom <= .805 and item["mat"][2, 2] > .97
                        and self.check_contact(self.items[g["object"]], "table_collision"))
        if g["type"] == "extended_hook":
            return ("extended_hook", g["object"]) in self.events
        if g["type"] == "bolt_engaged":
            rod, box = state[g["object"]], state[g["target"]]
            shaft = rod["pos"]+rod["mat"]@np.array([0., 0., -.030])
            rings = [(box["pos"]+box["mat"]@np.array([.165, yy, .035]), box["mat"], .010)
                     for yy in [-.075, .075]]
            rings.append((box["leaf_pos"]+box["leaf_mat"]@np.array([.285, 0., -.020]), box["leaf_mat"], .008))
            # Both faces of all three rings must contain the shaft, allowing
            # different insertion depths through the real rectangular holes.
            for center, frame, depth in rings:
                mat = frame.T@rod["mat"]; origin = frame.T@(shaft-center)
                direction = mat[:, 1]
                if abs(direction[1]) < .95: return False
                u = mat[:, 0]-direction*(mat[1, 0]/direction[1])
                w = mat[:, 2]-direction*(mat[1, 2]/direction[1])
                extent = np.abs(u[[0, 2]])*.007+np.abs(w[[0, 2]])*.007
                for side in [-1, 1]:
                    t = (side*depth-origin[1])/direction[1]
                    if abs(t) > .108: return False
                    cross = origin+t*direction
                    if np.any(np.abs(cross[[0, 2]])+extent > .013): return False
            return True
        if g["type"] == "place" and self.by_spec[g["object"]]["kind"] == "sphere":
            zone = next(z for z in self.spec["zones"] if z["id"] == g["target"])
            radius = self.by_spec[g["object"]]["size"][0]; p = state[g["object"]]["pos"]
            return bool(np.all(np.abs(p[:2]-zone["xy"])+radius < np.array(zone["half_size"])+.008)
                        and .8 < p[2] < .8+radius+.025)
        if g["type"] == "swept":
            return ("swept", g["object"]) in self.events and g["object"] not in self._manually_handled
        if g["type"] == "scooped":
            return ("scooped", g["object"]) in self.events and g["object"] not in self._manually_handled
        if g["type"] == "clipped":
            return ("clipped", g["object"]) in self.events and g["object"] not in self._manually_handled
        if g["type"] == "guided_roll":
            return ("guided_roll", g["object"]) in self.events and g["object"] not in self._manually_handled
        if g["type"] == "hinge_angle":
            a = state[g["object"]]
            return bool(g["bounds"][0] <= a["hinge_angle"] <= g["bounds"][1]
                        and abs(a["hinge_velocity"]) < .04 and a["mat"][2, 2] > .98)
        if g["type"] == "leaf_support":
            panel = self.items[g["object"]]
            return self.check_contact(panel.naming_prefix+"leaf_collision", self.items[g["target"]])
        if g["type"] == "through_apertures":
            a = state[g["object"]]; mat = a["mat"]; direction = mat[:, 0]
            if abs(direction[0]) < .9: return False
            half_length, sy, sz = self.by_spec[g["object"]]["size"]
            u = mat[:, 1]-direction*(mat[0, 1]/direction[0])
            w = mat[:, 2]-direction*(mat[0, 2]/direction[0])
            extent = np.abs(u[1:])*sy+np.abs(w[1:])*sz
            for aperture in g["apertures"]:
                for side in [-1, 1]:
                    t = (aperture[0]+side*g["half_depth"]-a["pos"][0])/direction[0]
                    if abs(t) >= half_length: return False
                    cross = a["pos"]+t*direction
                    if np.any(np.abs(cross[1:]-aperture[1:])+extent > np.array(g["half_opening"])+.001): return False
            return True
        if g["type"] in ("pushed", "hooked", "passed_gate"):
            return (g["type"], g["object"]) in self.events
        if g["type"] == "not_place":
            return not super().predicate(dict(g, type="place"), state)
        if g["type"] == "poured":
            return ("poured", g["object"]) in self.events
        if g["type"] == "collared":
            a, b = state[g["object"]], state[g["target"]]
            local = b["mat"].T@(a["pos"]-b["pos"])
            half = self.by_spec[g["object"]]["size"][2]
            return bool(np.linalg.norm(local[:2]) < .008 and a["mat"][2, 2] > .97
                        and abs(local[2]+half-.024) < .006
                        and self.check_contact(self.items[g["object"]], self.items[g["target"]]))
        if g["type"] == "nest" and ("inner_size" in self.by_spec[g["target"]]
                or self.by_spec[g["target"]]["kind"] in ("bowl", "tray")):
            a, b = state[g["object"]], state[g["target"]]
            size = np.array(self.by_spec[g["object"]]["size"])
            target = self.by_spec[g["target"]]
            inner = np.array(target.get("inner_size", target["size"]))
            local = b["mat"].T@(a["pos"]-b["pos"])
            extent = np.abs(b["mat"].T@a["mat"])@size
            if self.by_spec[g["object"]]["kind"] == "sphere": extent = size
            return bool(np.all(np.abs(local[:2])+extent[:2] < inner[:2]-.003+.005)
                and abs(local[2]-extent[2]-(-inner[2]+.008)) < .015
                and local[2]+extent[2] < inner[2]+.12
                and self.check_contact(self.items[g["object"]], self.items[g["target"]]))
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
        if g["type"] == "container_half":
            a, b = state[g["object"]], state[g["target"]]
            local = b["mat"].T@(a["pos"]-b["pos"])
            extent = np.abs(b["mat"].T@a["mat"])@np.asarray(self.by_spec[g["object"]]["size"])
            return bool(g["side"]*local[1] >= extent[1]-.004)
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
            if g["type"] == "threaded":
                # Completion is a post passing through the real annular hole
                # with the ring seated on its base, not concentric centres.
                center = a["mat"].T@(b["pos"]-a["pos"])
                axis = a["mat"].T@b["mat"][:, 2]
                if abs(axis[2]) < .5: return False
                angles = np.arange(24)*2*np.pi/24
                normals = np.column_stack([np.cos(angles), np.sin(angles)])
                radius = sb["post_radius"]
                extent = radius*np.sqrt(1+(normals@axis[:2]/axis[2])**2)
                for side in (-1, 1):
                    t = (side*sa["size"][2]-center[2])/axis[2]
                    point = center+t*axis
                    if not (-sb["size"][2]+.008-.001 <= t <= sb["size"][2]+.001): return False
                    if np.any(normals@point[:2]+extent > sa["inner_radius"]+.0005): return False
                seated = abs(local[2]-sa["size"][2]+sb["size"][2]-.008) < .008
                return bool(seated and self.check_contact(self.items[g["object"]], self.items[g["target"]]))
            if sa["kind"] == "key" and "hole_polygon" in sb:
                # Test the L-shaped key against the same concave aperture
                # used to build its collision walls, including edge crossings.
                polygon = np.asarray(sb["hole_polygon"])
                low, high = polygon.min(axis=0), polygon.max(axis=0)
                notch = polygon[3]+.0005
                rotation = b["mat"].T@a["mat"]
                for part in sa["components"]:
                    vertices = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)])
                    vertices = (vertices*np.asarray(part["size"])+part["pos"])@rotation.T+local
                    points = vertices[:, :2]
                    if np.any(points < low-.0005) or np.any(points > high+.0005): return False
                    if np.any((points[:, 0] > notch[0]) & (points[:, 1] > notch[1])): return False
                    for p in points:
                        for q in points:
                            if p[0] < notch[0] < q[0]:
                                y = p[1]+(q[1]-p[1])*(notch[0]-p[0])/(q[0]-p[0])
                                if y > notch[1]: return False
                return bool(a["mat"][2, 2] > .97
                            and abs(local[2]-sa["size"][2]+sb["size"][2]) < .008
                            and self.check_contact(self.items[g["object"]], "table_collision"))
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
        for goal in self.spec["goals"]:
            if goal["type"] != "extended_hook": continue
            name, rod, hook = goal["object"], goal["rod"], goal["hook"]
            a, b, load = state[rod], state[hook], state[name]
            local = b["mat"].T@(a["pos"]-b["pos"])
            aligned = abs(a["mat"][:, 0]@b["mat"][:, 0]) > .97
            walls = self.items[hook].contact_geoms[:4]
            connected = (aligned and -.20 < local[0] < -.12 and abs(local[1]) < .006
                         and abs(local[2]) < .006
                         and sum(self.check_contact(self.items[rod], wall) for wall in walls) >= 2)
            initial = self.by_spec[name]["xy"][0]+self.layout_jitter[0]
            if (connected and any(a["grasp"]) and not any(b["grasp"]) and not any(load["grasp"])
                    and load["pos"][0] < initial-.10 and self.check_contact(self.items[hook], self.items[name])):
                self.events.add(("extended_hook", name))
        for goal in self.spec["goals"]:
            if goal["type"] != "clipped": continue
            name, tool = goal["object"], goal["target"]
            load, clip = state[name], state[tool]
            if any(load["grasp"]): self._manually_handled.add(name)
            prefix = self.items[tool].naming_prefix
            fixed_jaw = self.items[tool].contact_geoms[1]
            extent = (np.abs(load["mat"])@self.by_spec[name]["size"])[2]
            if (any(clip["grasp"]) and name not in self._manually_handled
                    and load["pos"][2]-extent > .835
                    and self.check_contact(self.items[name], fixed_jaw)
                    and self.check_contact(self.items[name], prefix+"leaf_collision")):
                self.events.add(("clipped", name))
        for g in self.spec["goals"]:
            if g["type"] != "guided_roll": continue
            name = g["object"]
            if any(state[name]["grasp"]) or any(self.check_contact(self.items[name], gripper.contact_geoms)
                    for robot in self.robots for gripper in robot.gripper.values()):
                self._manually_handled.add(name)
            if (name not in self._manually_handled and self.check_contact(self.items[name], g["ramp"])
                    and any(self.check_contact(self.items[name], self.items[n]) for n in g["guides"])):
                self.events.add(("guided_roll", name))
        for g in self.spec["goals"]:
            if g["type"] != "scooped": continue
            name, tool = g["object"], g["target"]
            a, b = state[name], state[tool]
            if any(a["grasp"]): self._manually_handled.add(name)
            local = b["mat"].T@(a["pos"]-b["pos"])
            extent = (np.abs(a["mat"])@self.by_spec[name]["size"])[2]
            # Actual underside contact while the scoop bears an airborne load.
            supported = (any(b["grasp"]) and name not in self._manually_handled
                         and a["pos"][2]-extent > .84 and b["mat"][2, 2] > .95
                         and -.01 < local[0] < .13 and abs(local[1]) < .025
                         and -.08 < local[2] < -.035
                         and self.check_contact(self.items[name], self.items[tool]))
            self._scoop_hold[name] = self._scoop_hold.get(name, 0)+1 if supported else 0
            if self._scoop_hold[name] >= 4: self.events.add(("scooped", name))
        sweep_goals = [g for g in self.spec["goals"] if g["type"] == "swept"]
        if sweep_goals:
            # Force chains through contacting beads count as tool-mediated
            # sweeping. Every link must currently be in physical contact.
            tool = sweep_goals[0]["target"]
            names = {g["object"] for g in sweep_goals}
            self._manually_handled.update(n for n in names if any(state[n]["grasp"]))
            active = set()
            if any(state[tool]["grasp"]):
                active = {n for n in names if self.check_contact(self.items[n], self.items[tool])}
                while True:
                    reached = {n for n in names-active if any(self.check_contact(self.items[n], self.items[b]) for b in active)}
                    if not reached: break
                    active.update(reached)
            for g in sweep_goals:
                name = g["object"]
                if name not in active or name in self._manually_handled: continue
                origin = self._tool_contact_origins.setdefault(name, state[name]["pos"][:2].copy())
                if np.linalg.norm(state[name]["pos"][:2]-origin) >= g["distance"]:
                    self.events.add(("swept", name))
        for g in self.spec["goals"]:
            if g["type"] != "passed_gate": continue
            name = g["object"]; a = state[name]
            if self.predicate(dict(g, type="through_apertures"), state):
                self._gate_entered.add(name)
            extent = (np.abs(a["mat"]) @ self.by_spec[name]["size"])[0]
            if name in self._gate_entered and a["pos"][0]-extent > g["apertures"][0][0]+g["half_depth"]:
                self.events.add(("passed_gate", name))
        for g in self.spec["goals"]:
            if g["type"] not in ("pushed", "hooked"): continue
            name, tool = g["object"], g["target"]
            a, b = state[name], state[tool]
            if any(a["grasp"]) and (g["type"], name) not in self.events: self._manually_handled.add(name)
            contact = self.check_contact(self.items[name], self.items[tool])
            if contact and any(b["grasp"]) and name not in self._manually_handled:
                origin = self._tool_contact_origins.setdefault(name, a["pos"][:2].copy())
                if np.linalg.norm(a["pos"][:2]-origin) >= g["distance"]:
                    self.events.add((g["type"], name))
        for g in self.spec["goals"]:
            if g["type"] != "poured": continue
            piece, cup = state[g["object"]], state[g["target"]]
            local = cup["mat"].T@(piece["pos"]-cup["pos"])
            size = self.by_spec[g["target"]].get("cavity_size", self.by_spec[g["target"]]["size"])
            outside = abs(local[0]) > size[0] or abs(local[1]) > size[1] or local[2] > size[2]+.012
            if any(piece["grasp"]): self._manually_handled.add(g["object"])
            was_inside = self._pour_inside.get(g["object"], True)
            if (cup["mat"][2, 2] < .85 and any(cup["grasp"]) and g["object"] not in self._manually_handled
                    and was_inside and outside):
                self.events.add(("poured", g["object"]))
            self._pour_inside[g["object"]] = not outside
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
        result["joint_angles"] = {name: a["hinge_angle"] for name, a in self.snapshot().items()
                                  if "hinge_angle" in a}
        return result
