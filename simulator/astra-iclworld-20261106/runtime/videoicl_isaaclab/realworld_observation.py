"""Translate native rigid-body snapshots into private RealWorld50 evidence.

Only E05 and E32 are wired to native state here. Other tasks fail explicitly.
``pos`` and ``mat`` must be in the task coordinate frame, as returned by
Controller.snapshot(). All sizes are local half-extents. Non-centred imported
assets may provide ``local_bounds_center`` in the same local frame.

Movement history is recorded on every physics update, irrespective of the
legacy ``event_enabled`` flag. Moving a distractor back does not erase it.
No pose, contact or success value is accepted from a policy action receipt.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import math
from typing import Any

import numpy as np

from .realworld_contracts import check_pilot, provenance


class RealWorldEvaluator:
    """Controller-compatible stateful evaluator for the first rigid pilots."""

    SUPPORTED_TASKS = ("E05", "E32")

    def __init__(self, spec: Mapping[str, Any]):
        self.spec = deepcopy(dict(spec))
        self.task = self.spec["id"]
        self.variant = self.spec.get("variant", "A")
        if self.task not in self.SUPPORTED_TASKS:
            raise NotImplementedError(f"Native RealWorld50 observation adapter unavailable for {self.task}")
        self.provenance = provenance(self.task, self.variant)
        self.by_id = {o["id"]: o for o in self.spec["objects"]}
        if not self.by_id or len(self.by_id) != len(self.spec["objects"]):
            raise ValueError("Objects must have unique nonempty IDs")
        self.identity = {name: obj.get("identity", name) for name, obj in self.by_id.items()}
        if (not all(isinstance(v, str) and v for v in self.identity.values())
                or len(set(self.identity.values())) != len(self.identity)):
            raise ValueError("Object identities must be unique nonempty strings")
        if self.task == "E05" and set(self.identity.values()) != {"cube", "sphere", "triangle"}:
            raise ValueError("E05 requires exactly cube, sphere and triangle identities")
        if self.task == "E32" and not {"sprite_bottle", "pink_cube", "cola_bottle"} <= set(self.identity.values()):
            raise ValueError("E32 requires all three source candidate identities")
        self.zones = {z["id"]: z for z in self.spec["zones"]}
        required = {"square", "circle", "triangle"} if self.task == "E05" else {"target"}
        if not required <= set(self.zones) or len(self.zones) != len(self.spec["zones"]):
            raise ValueError("Missing or duplicate RealWorld50 target zones")
        self.sizes = {}
        self.bounds_centers = {}
        for name, obj in self.by_id.items():
            size = np.asarray(obj["size"], dtype=float)
            center = np.asarray(obj.get("local_bounds_center", [0., 0., 0.]), dtype=float)
            if size.shape != (3,) or not np.isfinite(size).all() or np.any(size <= 0):
                raise ValueError(f"Invalid local half-extents for {name}")
            if center.shape != (3,) or not np.isfinite(center).all():
                raise ValueError(f"Invalid local bounds center for {name}")
            self.sizes[name], self.bounds_centers[name] = size, center
        for zone in self.zones.values():
            xy, half = np.asarray(zone["xy"], dtype=float), np.asarray(zone["half_size"], dtype=float)
            if (xy.shape != (2,) or half.shape != (2,) or not np.isfinite(xy).all()
                    or not np.isfinite(half).all() or np.any(half <= 0)
                    or not math.isfinite(float(zone.get("surface_z", .8)))):
                raise ValueError("Invalid target zone geometry")
        # Explicit numerical tolerances; the scene/asset adapter must calibrate
        # these against imported collision geometry rather than visible scale.
        self.table_z = float(self.spec.get("table_surface_z", .8))
        self.bottom_tolerance = .012
        self.zone_margin = .005
        self.movement_threshold = .015
        self.required_hold_seconds = .5
        self.position_window = .002
        self.rotation_window = .02  # Frobenius matrix distance, ~0.81 degrees.
        self.linear_speed_limit = .02
        self.rotation_rate_limit = .2  # Frobenius matrix distance / second.
        self.reset_episode()

    def reset_episode(self):
        """Call before capturing the new episode's initial native snapshot."""
        self.hold_seconds = 0.
        self.event_enabled = False
        self.event_history = {"moved_objects": []}
        self.events = []
        self.origins = {}
        self.previous = None
        self._anchor = None
        self._moved = set()
        self._step = 0
        self._elapsed = 0.
        self._history_valid = True
        self._errors = []
        self._observation = {}
        self._semantic = check_pilot(self.task, self.variant, {})
        self.current_conditions = []
        self.extras = dict(released=False, supported=False, stable=False,
                           snapshot_valid=False, history_valid=True)

    def _invalidate(self, reason):
        self.hold_seconds = 0.
        self._anchor = None
        self.previous = None
        self._history_valid = False
        if reason not in self._errors:
            self._errors.append(reason)
        self._observation = {}
        self._semantic = check_pilot(self.task, self.variant, {})
        self.extras = dict(released=False, supported=False, stable=False,
                           snapshot_valid=False, history_valid=False)
        self._set_conditions()

    def _normalize(self, state):
        if not isinstance(state, Mapping) or set(state) != set(self.by_id):
            raise ValueError("Snapshot must include exactly all configured objects")
        clean = {}
        for name, value in state.items():
            pos = np.asarray(value["pos"], dtype=float)
            mat = np.asarray(value["mat"], dtype=float)
            grasp = value["grasp"]
            if (pos.shape != (3,) or mat.shape != (3, 3)
                    or not np.isfinite(pos).all() or not np.isfinite(mat).all()):
                raise ValueError(f"Nonfinite or malformed pose: {name}")
            if (not np.allclose(mat.T @ mat, np.eye(3), atol=1e-4, rtol=0)
                    or not np.isclose(np.linalg.det(mat), 1., atol=1e-4, rtol=0)):
                raise ValueError(f"Pose matrix is not a rotation: {name}")
            if (not isinstance(grasp, (list, tuple, np.ndarray)) or len(grasp) != 2
                    or not all(isinstance(x, (bool, np.bool_)) for x in grasp)):
                raise ValueError(f"Missing or malformed two-gripper state: {name}")
            clean[name] = dict(pos=pos.copy(), mat=mat.copy(), grasp=tuple(bool(x) for x in grasp))
        return clean

    def _bounds(self, name, value):
        center = value["pos"] + value["mat"] @ self.bounds_centers[name]
        extent = np.abs(value["mat"]) @ self.sizes[name]
        if self.by_id[name].get("kind") == "sphere":
            extent = np.full(3, self.sizes[name][0])
        return center, extent

    def _on_table(self, name, value, contacts, surface_z=None):
        center, extent = self._bounds(name, value)
        base = self.table_z if surface_z is None else surface_z
        return (frozenset((name, "table")) in contacts
                and abs(float(center[2] - extent[2]) - base) <= self.bottom_tolerance)

    def _in_zone(self, name, value, zone, contacts):
        center, _ = self._bounds(name, value)
        # The task labels refer to marked paper regions, not exact object poses.
        # Classify the object's centre against the paper, with edge tolerance.
        return (not any(value["grasp"])
                and self._on_table(name, value, contacts, float(zone.get("surface_z", .8)))
                and bool(np.all(np.abs(center[:2] - np.asarray(zone["xy"]))
                                <= np.asarray(zone["half_size"]) + self.zone_margin)))

    def _grounded(self, state, contacts):
        grounded = {name for name, value in state.items() if self._on_table(name, value, contacts)}
        # Distractors may rest on other real objects in a clutter scene. A
        # closed contact cycle without a valid table root never counts.
        while True:
            more = {name for name in state if name not in grounded
                    and any(frozenset((name, base)) in contacts for base in grounded)}
            if not more:
                return grounded
            grounded.update(more)

    def _set_conditions(self):
        checks = dict(self._semantic["checks"])
        checks.update(snapshot_valid=self.extras["snapshot_valid"],
                      history_valid=self._history_valid, all_objects_supported=self.extras["supported"])
        self.current_conditions = [dict(index=i, type=name, passed=bool(passed))
                                   for i, (name, passed) in enumerate(checks.items())]

    def update(self, state, contacts, dt):
        """Observe one actual physics step; mutate only evaluator bookkeeping."""
        try:
            if isinstance(dt, (bool, np.bool_)) or not math.isfinite(float(dt)) or float(dt) <= 0:
                raise ValueError("Physics dt must be finite and positive")
            dt = float(dt)
            clean = self._normalize(state)
            if not isinstance(contacts, (set, frozenset)) or any(
                not isinstance(pair, frozenset) or len(pair) != 2
                or not all(isinstance(x, str) for x in pair) for pair in contacts
            ):
                raise ValueError("Contacts must be native object-pair frozensets")
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            self._invalidate(str(exc))
            return
        self._step += 1
        self._elapsed += dt
        if not self.origins:
            self.origins = {name: value["pos"].copy() for name, value in clean.items()}
        if self.task == "E32":
            for name, value in clean.items():
                distance = float(np.linalg.norm(value["pos"] - self.origins[name]))
                identity = self.identity[name]
                if distance > self.movement_threshold and identity not in self._moved:
                    self._moved.add(identity)
                    self.event_history["moved_objects"].append(identity)
                    self.events.append(dict(event="object_moved", object_id=name, identity=identity,
                                            step=self._step, elapsed_seconds=self._elapsed,
                                            displacement_m=distance))

        released = not any(any(value["grasp"]) for value in clean.values())
        grounded = self._grounded(clean, contacts)
        supported = len(grounded) == len(clean)
        observation = dict(released=released, stable=True)
        if self.task == "E05":
            placements = {}
            for name, value in clean.items():
                matches = [zone_id for zone_id in ("square", "circle", "triangle")
                           if self._in_zone(name, value, self.zones[zone_id], contacts)]
                if len(matches) == 1:
                    placements[self.identity[name]] = matches[0]
            observation.update(placements=placements,
                               supported=[self.identity[name] for name, value in clean.items()
                                          if self._on_table(name, value, contacts)])
        else:
            delivered = [self.identity[name] for name, value in clean.items()
                         if self._in_zone(name, value, self.zones["target"], contacts)]
            observation.update(delivered=delivered, moved_objects=sorted(self._moved))

        provisional = check_pilot(self.task, self.variant, observation)
        quiet = self.previous is not None and all(
            np.linalg.norm(value["pos"] - self.previous[name]["pos"]) <= self.linear_speed_limit * dt
            and np.linalg.norm(value["mat"] - self.previous[name]["mat"]) <= self.rotation_rate_limit * dt
            for name, value in clean.items())
        anchored = self._anchor is not None and all(
            np.linalg.norm(value["pos"] - self._anchor[name]["pos"]) <= self.position_window
            and np.linalg.norm(value["mat"] - self._anchor[name]["mat"]) <= self.rotation_window
            for name, value in clean.items())
        valid = provisional["success"] and supported and quiet and self._history_valid
        if valid:
            if not anchored:
                self._anchor = deepcopy(clean)
                self.hold_seconds = 0.
            self.hold_seconds += dt
        else:
            self._anchor = None
            self.hold_seconds = 0.
        stable = valid and self.hold_seconds + 1e-12 >= self.required_hold_seconds
        observation["stable"] = bool(stable)
        self._observation = observation
        self._semantic = check_pilot(self.task, self.variant, observation)
        self.previous = clean
        self.extras = dict(released=released, supported=supported, stable=bool(stable),
                           snapshot_valid=True, history_valid=self._history_valid)
        self._set_conditions()

    def result(self):
        """Return private diagnostics compatible with Demonstration.note()."""
        return deepcopy(dict(
            success=self._semantic["success"] and all(x["passed"] for x in self.current_conditions),
            hold_seconds=self.hold_seconds,
            conditions=self.current_conditions,
            events=self.events,
            event_history=self.event_history,
            observation=self._observation,
            failed_checks=[x["type"] for x in self.current_conditions if not x["passed"]],
            errors=self._errors,
            backend="isaaclab_physx",
            protocol="realworld50-native-pilot-v1",
            provenance=self.provenance,
            **self.extras,
        ))
