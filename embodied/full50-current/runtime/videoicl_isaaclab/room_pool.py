"""Small synchronous multi-task pool: one Kit process and one physics clock.

Rooms may have different assets and evaluators. All rooms advance together;
this probe does not implement per-room physics pause or task hot replacement.
"""
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
import math


def action_tick_limits(physics,dt):
    """Optional engineering settle window; legacy profiles keep exact duration."""
    base=physics['action_seconds']
    maximum=physics.get('public_action_max_seconds',base)
    check=physics.get('public_action_check_seconds',base)
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (base,maximum,check)) or maximum<base:
        raise ValueError('Invalid bounded public action timing')
    values=[v/dt for v in (base,maximum,check)]
    if any(not math.isclose(v,round(v),rel_tol=0.,abs_tol=1e-8) for v in values):
        raise ValueError('Public action windows must contain whole physics ticks')
    return tuple(round(v) for v in values)


def global_scene_signature(config):
    """Conservative compatibility key for this synchronous pool protocol.

    Actor-local gains, joint limits, friction and source assets may differ.
    Unknown physics keys are kept in the key rather than silently discarded.
    Timing and lighting are also cohort requirements until independent camera
    schedules and renderer light isolation have native acceptance evidence.
    """
    physics = config['physics']
    dt = physics['dt']
    if type(dt) not in (int, float) or not math.isfinite(dt) or dt <= 0:
        raise ValueError('A finite positive physics timestep is required')
    actor_local = {'render_hz', 'action_seconds', 'solver_position_iterations',
                   'solver_velocity_iterations', 'disable_gravity',
                   'self_collision', 'max_joint_delta'}
    global_physics = {key: value for key, value in physics.items() if key not in actor_local}
    global_physics.setdefault('enable_stabilization', 'simulator_default')
    for field in ('action_seconds', 'render_hz'):
        value = physics[field]
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError('Invalid synchronous cohort timing: ' + field)
    ticks = physics['action_seconds'] / dt
    if not math.isclose(ticks, round(ticks), rel_tol=0., abs_tol=1e-8):
        raise ValueError('Action duration must be an exact number of physics ticks')
    action_tick_limits(physics,dt)
    key = dict(global_physics=global_physics,
               cohort_timing={name: physics[name] for name in ('action_seconds', 'render_hz')},
               lighting=dict(kind=config['layout']['kind'], background=config['layout']['background']))
    # Also reject nonfinite configuration values in unknown global settings.
    encoded = json.dumps(key, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return dict(settings=key, sha256=hashlib.sha256(encoded.encode()).hexdigest())


def filter_room_collisions(stage, roots):
    """Exclude cross-room contacts, including each rig's large ground slab."""
    from pxr import Sdf, UsdPhysics
    paths = [Sdf.Path('/World/PoolCollisionGroups/room_' + str(i)) for i in range(len(roots))]
    for index, root in enumerate(roots):
        if not stage.GetPrimAtPath(root).IsValid():
            raise ValueError('Room root is missing: ' + root)
        group = UsdPhysics.CollisionGroup.Define(stage, paths[index])
        collection = group.GetCollidersCollectionAPI()
        collection.CreateExpansionRuleAttr().Set('expandPrims')
        collection.CreateIncludesRel().SetTargets([Sdf.Path(root)])
        group.CreateFilteredGroupsRel().SetTargets([p for p in paths if p != paths[index]])
    return [str(path) for path in paths]


class RoomPool:
    def __init__(self, simulation, controllers, *, render_isolation=False):
        if not controllers:
            raise ValueError('At least one room is required')
        if type(render_isolation) is not bool:
            raise ValueError('render_isolation must be explicitly boolean')
        self.sim = simulation
        self.render_isolation = render_isolation
        self.controllers = dict(controllers)
        self.physics_ticks = 0
        self.terminal = {}
        roots = []
        signatures = []
        for controller in self.controllers.values():
            if controller.sim is not simulation:
                raise ValueError('Every room must share exactly one SimulationContext')
            if not math.isclose(controller.dt, simulation.get_physics_dt(), rel_tol=0., abs_tol=1e-12):
                raise ValueError('Every room must use the shared physics timestep')
            if getattr(controller, '_room_pool', None) is not None:
                raise ValueError('Controller already belongs to a pool')
            root = controller.scene.root_path
            if any(root == r or root.startswith(r + '/') or r.startswith(root + '/') for r in roots):
                raise ValueError('Rooms require distinct, non-nested USD roots')
            roots.append(root)
            profile = getattr(controller.scene, 'embodiment', None)
            if profile is not None:
                signatures.append(global_scene_signature(profile.config))
        if signatures and (len(signatures) != len(self.controllers) or
                           len({s['sha256'] for s in signatures}) != 1):
            raise ValueError('Rooms have incompatible shared physics, timing or lighting settings')
        self.global_signature = signatures[0] if signatures else None
        for controller in self.controllers.values():
            controller._room_pool = self

    def render_room(self, room, *, passes=1, capture=None):
        """Render and read a target room before foreign render products run."""
        if type(passes) is not int or passes < 1:
            raise ValueError('A positive integer render pass count is required')
        controller = self.controllers[room]
        from contextlib import nullcontext
        scope = nullcontext()
        if self.render_isolation:
            from .rig import isolated_room_render
            scope = isolated_room_render(self.sim.stage,
                [c.scene.root_path for c in self.controllers.values()], controller.scene.root_path)
        with scope:
            before_clock=float(self.sim.current_time)
            for _ in range(passes):
                controller.scene.prepare_render()
                self.sim.render()
                controller.scene.update_render_cameras()
            if float(self.sim.current_time)!=before_clock:
                raise RuntimeError('A render-only capture advanced the shared physics clock')
            return capture() if capture is not None else None

    @contextmanager
    def engineering_recording_render_passes(self, passes):
        """Fresh engineering only: flush room visibility before one RGB sample.

        Repeated render passes do not run physics, evaluators or recorder hooks.
        Normal model pools keep their original one-pass rendering outside scope.
        """
        if type(passes) is not int or not 1 <= passes <= 64:
            raise ValueError('Engineering render passes must be an integer in [1, 64]')
        previous=getattr(self,'_engineering_recording_render_passes',1)
        self._engineering_recording_render_passes=passes
        try:
            yield
        finally:
            self._engineering_recording_render_passes=previous

    @contextmanager
    def engineering_reference_rendering(self, room):
        """Only an isolated serial engineering reference opts into this scope.

        Every room still advances and records every physics tick. Only unused
        idle RGB refreshes are skipped; explicit initial/final captures and
        normal pooled model actions retain their existing rendering behavior.
        """
        if room not in self.controllers or room in self.terminal:
            raise ValueError('A live engineering reference room is required')
        previous=getattr(self,'_engineering_reference_render_room',None)
        if previous is not None and previous!=room:
            raise RuntimeError('Overlapping engineering reference rooms')
        self._engineering_reference_render_room=room
        try:
            yield
        finally:
            self._engineering_reference_render_room=previous

    def _tick_hooks(self, room, render):
        if room not in self.terminal:
            controller = self.controllers[room]
            for hook in controller.tick_hooks:hook(controller, render)

    def tick(self, render=False):
        # Never call controller.action() or a full controller.tick() here:
        # both would step the entire shared world again for each room.
        for controller in self.controllers.values():
            controller.tick(phase='write')
        self.sim.step(render=False)
        for controller in self.controllers.values():
            controller.tick(phase='read')
        self.physics_ticks += 1
        if render and self.render_isolation:
            reference=getattr(self,'_engineering_reference_render_room',None)
            for room in self.controllers:
                if room not in self.terminal:
                    if reference is None or room==reference:
                        self.render_room(room,
                            passes=getattr(self,'_engineering_recording_render_passes',1),
                            capture=lambda room=room: self._tick_hooks(room, True))
                    else:
                        # NativeCapture and physical evidence still receive
                        # exactly one callback for this same shared tick.
                        self._tick_hooks(room, False)
        elif render:
            for controller in self.controllers.values():
                controller.scene.prepare_render()
            self.sim.render()
            for controller in self.controllers.values():
                controller.scene.update_render_cameras()
        if not (render and self.render_isolation):
            for room in self.controllers:self._tick_hooks(room, render)

    def action_batch(self, actions):
        """Advance one pair for every live room behind one action barrier.

        Missing policy replies mean no call to this function and no physics
        advancement. A finished room is never assigned a replacement episode
        by this API; its world can continue physically, but its terminal
        receipt and recorder are frozen at the explicit seal tick.
        """
        active = {room: c for room, c in self.controllers.items() if room not in self.terminal}
        if not active or set(actions) != set(active):
            raise ValueError('One action per active room is required at the shared barrier')
        checked = {}
        timings = set()
        for room, controller in active.items():
            action = actions[room]
            if not isinstance(action, dict) or set(action) - {'left', 'right', 'step_mm', 'rotation_deg'}:
                raise ValueError('Invalid public pair action fields')
            controller.validate_action(**action)
            checked[room] = dict(action)
            physics = controller.scene.embodiment.config['physics']
            timings.add((*action_tick_limits(physics,self.sim.get_physics_dt()),physics['render_hz']))
        if len(timings) != 1:
            raise ValueError('One synchronous action duration and camera rate are required')
        before = float(self.sim.current_time)
        tick_before = self.physics_ticks
        steps = {room: c.steps for room, c in active.items()}
        for room, controller in active.items():
            controller.begin_action(**checked[room])
        minimum_ticks,maximum_ticks,check_ticks,fps = next(iter(timings))
        dt = self.sim.get_physics_dt()
        from .recording_trajectory import frame_due
        executed_ticks=0
        for index in range(maximum_ticks):
            self.tick(render=frame_due(self.physics_ticks + 1, dt, fps))
            executed_ticks=index+1
            if executed_ticks>=minimum_ticks and (executed_ticks-minimum_ticks)%check_ticks==0:
                if maximum_ticks==minimum_ticks or all(controller.public_action_converged() for controller in active.values()):
                    break
        receipts = {}
        for room, controller in active.items():
            controller.steps += 1
            receipts[room] = dict(step_before=steps[room], step_after=controller.steps,
                shared_tick_before=tick_before, shared_tick_after=self.physics_ticks,
                simulation_seconds=float(self.sim.current_time)-before,
                physics_ticks=executed_ticks,settle_ticks=max(0,executed_ticks-minimum_ticks),
                maximum_action_ticks=maximum_ticks)
            if callable(getattr(controller,'action_feedback',None)):
                receipts[room].update(controller.action_feedback())
        return receipts

    def seal(self, room):
        """Latch private native terminal evidence; do not teleport or reset."""
        if room not in self.controllers:
            raise KeyError(room)
        if room not in self.terminal:
            controller = self.controllers[room]
            native = controller.evaluator.result()
            if not isinstance(native, dict) or type(native.get('success')) is not bool:
                raise ValueError('Native terminal evidence requires a boolean success')
            from .terminal_geometry_evidence import capture
            geometry = capture(controller.evaluator, shared_tick=self.physics_ticks,
                               controller_tick=controller.physics_ticks)
            self.terminal[room] = dict(room=room, terminal_shared_tick=self.physics_ticks,
                terminal_controller_tick=controller.physics_ticks, steps=controller.steps,
                native=deepcopy(native), physical_world_frozen=False,
                recorder_stopped=True, terminal_geometry=geometry)
        return deepcopy(self.terminal[room])

    def terminal_result(self, room):
        return deepcopy(self.terminal[room])
