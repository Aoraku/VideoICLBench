"""Native capacity/control probe: one Kit process, one shared physics clock.

Accept same-task ABC copies or heterogeneous case JSON, up to 15 rooms. This
executes internal engineering controls, not the final GUI-only agent protocol.
It does not prove task success, independent physics pause, or RTX light parity.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def normalize_cases(rows, *, base, default_bindings=None, default_robot='franka'):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 15:
        raise ValueError('Use one to fifteen explicit room cases')
    checked = []
    seen = set()
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            raise ValueError('Each room case must be an object')
        task, variant, seed = item.get('task'), item.get('variant', 'A'), item.get('seed', 0)
        if not isinstance(task, str) or not re.fullmatch(r'E(?:0[1-9]|[1-4][0-9]|50)', task):
            raise ValueError('Task must be E01-E50')
        if variant not in ('A', 'B', 'C') or type(seed) is not int or seed < 0:
            raise ValueError('Invalid case variant or seed')
        identity = item.get('episode_id', f'room-{index:02d}-{task}-{variant}-s{seed}')
        if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', identity) or identity in seen:
            raise ValueError('Unique path-safe episode_id required for every room')
        seen.add(identity)
        bindings = item.get('bindings', default_bindings)
        if not isinstance(bindings, (str, Path)):
            raise ValueError('Each room needs explicit bindings or --bindings')
        bindings = Path(bindings).expanduser()
        if not bindings.is_absolute():
            bindings = Path(base) / bindings
        bindings = bindings.resolve(strict=True)
        if not bindings.is_file():
            raise ValueError('Bindings must be a saved file')
        robot = item.get('robot', default_robot)
        if not isinstance(robot, str) or not robot:
            raise ValueError('An explicit robot name or profile is required')
        if '/' in robot or robot.endswith('.json'):
            profile = Path(robot).expanduser()
            if not profile.is_absolute():
                profile = Path(base) / profile
            robot = str(profile.resolve(strict=True))
            if not Path(robot).is_file():
                raise ValueError('Robot profile must be a file')
        checked.append(dict(episode_id=identity, task=task, variant=variant, seed=seed,
            bindings=str(bindings), robot=robot))
    return checked


def parse_cases(args):
    if args.cases:
        payload = json.loads(args.cases.read_text())
        rows = payload.get('cases') if isinstance(payload, dict) else payload
        return normalize_cases(rows, base=args.cases.resolve().parent,
            default_bindings=args.bindings.resolve() if args.bindings else None, default_robot=args.robot)
    count = args.rooms if args.rooms is not None else len(args.tasks)
    variants = args.variants or [args.variant]
    rows = [dict(task=args.tasks[i % len(args.tasks)], variant=variants[i % len(variants)], seed=args.seed)
            for i in range(count)]
    return normalize_cases(rows, base=Path.cwd(), default_bindings=args.bindings, default_robot=args.robot)


class GPUSampler:
    """Whole visible GPU measurements; never attribute these totals to one pool."""
    def __init__(self):
        self.rows, self.errors = [], []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        while not self.stop.is_set():
            try:
                text = subprocess.check_output(['nvidia-smi',
                    '--query-gpu=index,uuid,memory.used,memory.free,utilization.gpu',
                    '--format=csv,noheader,nounits'], text=True, timeout=3)
                for line in text.splitlines():
                    index, gpu, used, free, utilization = [v.strip() for v in line.split(',')]
                    self.rows.append(dict(time_unix=time.time(), index=index, uuid=gpu,
                        memory_used_mib=int(used), memory_free_mib=int(free), utilization_percent=int(utilization)))
            except Exception as exc:
                self.errors.append(type(exc).__name__)
            self.stop.wait(.5)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=4)
        return dict(scope='whole_visible_GPU_not_per_pool', samples=self.rows, errors=self.errors,
                    peak_used_mib=max((r['memory_used_mib'] for r in self.rows), default=None),
                    visible_gpu_uuids=sorted({r['uuid'] for r in self.rows}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases', type=Path)
    p.add_argument('--bindings', type=Path)
    p.add_argument('--tasks', nargs='+', default=['E05', 'E06'])
    p.add_argument('--rooms', type=int)
    p.add_argument('--robot', default='franka')
    p.add_argument('--variant', choices=['A', 'B', 'C'], default='A')
    p.add_argument('--variants', nargs='+', choices=['A', 'B', 'C'])
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--ticks', type=int, default=125)
    p.add_argument('--settle-ticks', type=int, default=240)
    p.add_argument('--spacing', type=float, default=8.)
    p.add_argument('--camera-resolution', type=int, nargs=2, metavar=('WIDTH', 'HEIGHT'))
    p.add_argument('--include-overview', action='store_true')
    p.add_argument('--legacy-unlinked-lights', action='store_true')
    p.add_argument('--verify-terminal-cache', action='store_true')
    p.add_argument('--legacy-shared-render', action='store_true', help='Diagnostic comparison only: foreign lights/geometry remain visible')
    p.add_argument('--verify-render-isolation', action='store_true', help='Compare visible 1/2/all rooms without advancing frozen physics')
    p.add_argument('--start-gate', type=Path, help='Optional private file gate for simultaneous multi-process capacity tests')
    p.add_argument('--start-gate-timeout', type=float, default=120.)
    p.add_argument('--validate-only', action='store_true')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--experience', default='')
    p.add_argument('--defer-stage-creation', action='store_true')
    p.add_argument('--capture-passes', type=int, default=3)
    p.add_argument('--headless', action='store_true')
    p.add_argument('--enable_cameras', action='store_true', default=True)
    p.add_argument('--device', default='cpu')
    p.add_argument('--kit_args', default='--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0')
    args = p.parse_args()
    if not math.isfinite(args.start_gate_timeout) or not 1 <= args.start_gate_timeout <= 300:
        p.error('Use a finite start gate timeout from 1 to 300 seconds')
    if not 1 <= args.capture_passes <= 128:
        p.error('Use 1..128 explicit isolated render passes')
    if not 25 <= args.ticks <= 5000 or not 0 <= args.settle_ticks <= 1000 or not 5 <= args.spacing <= 20:
        p.error('Use 25..5000 measured ticks, 0..1000 settle ticks, and 5..20m spacing')
    if args.camera_resolution and (min(args.camera_resolution) < 32 or max(args.camera_resolution) > 4096):
        p.error('Camera resolution override must be 32..4096 pixels')
    cases = parse_cases(args)
    from videoicl_isaaclab.embodiments import select
    from videoicl_isaaclab.room_pool import RoomPool, filter_room_collisions, global_scene_signature
    profiles = {c['episode_id']: select(c['task'], c['robot']) for c in cases}
    signatures = {room: global_scene_signature(profile.config) for room, profile in profiles.items()}
    if len({s['sha256'] for s in signatures.values()}) != 1:
        raise ValueError('Case profiles have incompatible shared physics, timing or lighting')
    preflight = dict(schema='videoicl-room-pool-cases-v2', room_count=len(cases),
                     cases=cases, global_signature=next(iter(signatures.values())))
    if args.validate_only:
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return 0
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out/'cases.private.json').write_text(json.dumps(preflight, indent=2)+'\n')
    sampler = GPUSampler()
    sampler.thread.start()
    app, code = None, 1
    started = time.perf_counter()
    try:
        from isaaclab.app import AppLauncher
        if args.defer_stage_creation:
            from isaacsim import SimulationApp
            SimulationApp.DEFAULT_LAUNCHER_CONFIG['create_new_stage']=False
        app = AppLauncher(headless=args.headless, enable_cameras=True, device=args.device,
                          experience=args.experience,kit_args=args.kit_args).app
        if args.defer_stage_creation:
            import omni.usd
            omni.usd.get_context().new_stage()
        import numpy as np
        import isaaclab.sim as sim
        from isaaclab.utils.math import quat_apply
        from PIL import Image
        from videoicl_isaaclab.control import Controller
        from videoicl_isaaclab.realworld_scenes import load
        from videoicl_isaaclab.realworld_evaluator_selector import create_evaluator
        from videoicl_isaaclab.scene import TabletopScene
        first = profiles[cases[0]['episode_id']]
        options = {k: first.config['physics'][k] for k in ('enable_stabilization',) if k in first.config['physics']}
        context = sim.SimulationContext(sim.SimulationCfg(dt=first.config['physics']['dt'], device=args.device,
            enable_scene_query_support=True, physx=sim.PhysxCfg(**options)))
        scenes, controllers = {}, {}
        columns = math.ceil(math.sqrt(len(cases)))
        for index, case in enumerate(cases):
            room = case['episode_id']
            spec = load(case['task'], case['variant'], case['seed'], Path(case['bindings']))
            scenes[room] = TabletopScene(spec, embodiment=case['robot'],
                camera_resolution=tuple(args.camera_resolution) if args.camera_resolution else None,
                root_path=f'/World/Rooms/room_{index:02d}',
                origin=((index % columns)*args.spacing, (index // columns)*args.spacing, 0.),
                include_overview=args.include_overview, light_isolation=not args.legacy_unlinked_lights)
        groups = filter_room_collisions(context.stage, [s.root_path for s in scenes.values()])
        context.reset()
        for scene in scenes.values():
            for robot in scene.robots.values():
                robot.write_joint_state_to_sim(robot.data.default_joint_pos, robot.data.default_joint_vel)
                robot.set_joint_position_target(robot.data.default_joint_pos)
                robot.write_data_to_sim()
        for _ in range(8):
            for scene in scenes.values():scene.apply_passive_efforts()
            context.step(render=False)
            for scene in scenes.values():scene.update_physics(context.get_physics_dt())
        for room, scene in scenes.items():
            controllers[room] = Controller(scene, context)
        pool = RoomPool(context, controllers, render_isolation=not args.legacy_shared_render)
        for _ in range(args.settle_ticks):pool.tick()
        for room, controller in controllers.items():
            controller.evaluator = create_evaluator(controller.scene.spec)
            controller.evaluator.reset_episode()
            state, contacts = controller.snapshot()
            update = getattr(controller.evaluator, 'update_mechanisms', None)
            if update:update(controller.snapshot_mechanisms())
            update = getattr(controller.evaluator, 'update_contact_forces', None)
            if update:update(controller.contact_forces)
            controller.evaluator.update(state, contacts, controller.dt)
        for scene in scenes.values():scene.initialize_cameras(context.device)
        for room in controllers:pool.render_room(room, passes=args.capture_passes)
        gate_wait = None
        if args.start_gate:
            ready = dict(pid=os.getpid(), room_count=len(cases), ready_unix=time.time(),
                         shared_tick=pool.physics_ticks, physics_time=float(context.current_time))
            (out/'pool-ready.private.json').write_text(json.dumps(ready, indent=2)+'\n')
            wait_started = time.monotonic()
            while not args.start_gate.exists():
                if time.monotonic()-wait_started > args.start_gate_timeout:
                    raise TimeoutError('Private simultaneous-pool start gate was not released')
                time.sleep(.05)  # No physics or render ticks while waiting.
            gate_wait = dict(ready, released_unix=time.time(), wait_seconds=time.monotonic()-wait_started,
                             tick_after_wait=pool.physics_ticks, physics_time_after_wait=float(context.current_time))
        def task_tcp(controller):
            robot = controller.scene.robots['left']
            position = robot.data.root_pos_w + quat_apply(robot.data.root_quat_w, controller.pose('left')[0])
            return controller.scene.world_to_task(position[0].cpu().numpy())
        before = {room: task_tcp(c).copy() for room, c in controllers.items()}
        initial = {room: c.evaluator.result() for room, c in controllers.items()}
        tick_before, clock_before = pool.physics_ticks, float(context.current_time)
        requested = {room: .02 if i % 2 == 0 else -.01 for i, room in enumerate(controllers)}
        receipts = pool.action_batch({room: dict(left='UP' if delta > 0 else 'DOWN', right='STILL',
            step_mm=abs(delta)*1000, rotation_deg=10.) for room, delta in requested.items()})
        cached = None
        if args.verify_terminal_cache:
            cached = pool.seal(cases[0]['episode_id'])
        for tick in range(args.ticks):pool.tick(render=tick % 25 == 0)
        pool.tick(render=True)
        elapsed_ticks, elapsed_clock = pool.physics_ticks-tick_before, float(context.current_time)-clock_before
        rows = []
        for case in cases:
            room = case['episode_id'];controller = controllers[room];scene = controller.scene
            folder = out/room;folder.mkdir()
            def capture_cameras():
                cameras = {}
                for name in ('head', 'left_wrist', 'right_wrist'):
                    camera = scene.cameras[name];camera.update(0., force_recompute=True)
                    rgb = camera.data.output['rgb'][0, :, :, :3].cpu().numpy()
                    if rgb.ndim!=3 or rgb.shape[2]!=3 or min(rgb.shape[:2])<2 or rgb.dtype!=np.uint8:
                        raise ValueError('Invalid native RGB shape/type: '+room+'/'+name)
                    Image.fromarray(rgb).save(folder/(name+'.png'))
                    cameras[name] = dict(shape=list(rgb.shape),dtype=str(rgb.dtype),delivery_valid=True,
                        spatial_stddev=float(rgb.std(axis=(0,1)).mean()))
                return cameras
            cameras = pool.render_room(room, passes=args.capture_passes, capture=capture_cameras)
            state, _ = controller.snapshot()
            (folder/'state.private.json').write_text(json.dumps(dict(
                objects={n:dict(position_task=s['pos'].tolist(),rotation_task=s['mat'].tolist()) for n,s in state.items()},
                robot_feedback=controller.public_feedback(), physics_tick=controller.physics_ticks), indent=2)+'\n')
            diagnostics = scene.contact_diagnostics()
            (folder/'contacts.private.json').write_text(json.dumps(diagnostics, indent=2)+'\n')
            paths = [p for b in diagnostics['bodies'].values() for p in b['root_physx_paths']]
            filters = [p for s in diagnostics['sensors'].values() for p in s['configured_filter_paths']]
            movement = task_tcp(controller)-before[room]
            final = pool.terminal_result(room)['native'] if room in pool.terminal else controller.evaluator.result()
            (folder/'native-evidence.private.json').write_text(json.dumps(dict(initial=initial[room], final=final), indent=2)+'\n')
            rows.append(dict(episode_id=room, task=case['task'], variant=case['variant'], seed=case['seed'],
                root_path=scene.root_path, physics_ticks=controller.physics_ticks, steps=controller.steps,
                left_tcp_delta_task_m=movement.tolist(), cameras=cameras, actual_camera_count=len(scene.cameras),
                finite_state=all(np.isfinite(s['pos']).all() for s in state.values()),
                namespace_isolated=bool(paths) and all(p.startswith(scene.root_path+'/') for p in paths+filters),
                evaluator_task=controller.evaluator.task, requested_z_delta_task_m=requested[room],
                control_moved=float(movement[2])*(1 if requested[room] > 0 else -1) > .001,
                initial_history_valid=initial[room].get('history_valid') is not False,
                initial_source_state_valid=all(c.get('passed') is True for c in initial[room].get('conditions', [])
                    if c.get('type') == 'source_initial_state'),
                native_history_valid=final.get('history_valid') is not False,
                light_link_paths=scene.room_light_links, source_binding_sha256=scene.spec['source_binding_sha256'],
                embodiment_config_sha256=scene.embodiment.config_hash, receipt=receipts[room]))
        clock_ok = abs(elapsed_clock-elapsed_ticks*context.get_physics_dt()) < 1e-6
        terminal_ok = cached is None or cached == pool.terminal_result(cases[0]['episode_id'])
        # Finalize every remaining room explicitly. A previously sealed room
        # retains its earlier tick while other rooms advance on the same world.
        for room in controllers:
            if room not in pool.terminal:pool.seal(room)
        terminal_receipts={room:pool.terminal_result(room) for room in controllers}
        passed = clock_ok and terminal_ok and all(r['namespace_isolated'] and r['finite_state'] and r['control_moved']
            and r['initial_history_valid'] and r['initial_source_state_valid'] and r['native_history_valid']
            and r['evaluator_task'] == r['task']
            and all(c['delivery_valid'] for c in r['cameras'].values()) for r in rows)
        render_parity = None
        if args.verify_render_isolation:
            from videoicl_isaaclab.rig import visible_rooms_render
            first_room = cases[0]['episode_id'];c = controllers[first_room];scene = c.scene
            roots = [s.root_path for s in scenes.values()]
            parity_dir=out/'render-parity';parity_dir.mkdir()
            def raw_physx_state():
                # Read live native views directly; cached Isaac data buffers
                # alone cannot prove that a render callback preserved physics.
                result={}
                for room,control in controllers.items():
                    result[room]={}
                    for name,asset in control.scene.objects.items():
                        view=asset.root_physx_view
                        result[room]['object:'+name]=dict(transform=view.get_transforms().cpu().tolist(),
                            velocity=view.get_velocities().cpu().tolist())
                    for name,asset in {**control.scene.robots,**control.scene.mechanisms}.items():
                        view=asset.root_physx_view
                        result[room]['articulation:'+name]=dict(root_transform=view.get_root_transforms().cpu().tolist(),
                            joint_position=view.get_dof_positions().cpu().tolist(),joint_velocity=view.get_dof_velocities().cpu().tolist())
                return result
            frozen_before = dict(tick=pool.physics_ticks, clock=float(context.current_time),
                raw_native_physx=raw_physx_state(), robot=c.public_feedback(),
                objects={n:dict(position_task=s['pos'].tolist(),rotation_task=s['mat'].tolist()) for n,s in c.snapshot()[0].items()})
            captures = {}
            def read_rgb():
                images = {}
                for name in ('head','left_wrist','right_wrist'):
                    camera=scene.cameras[name];camera.update(0.,force_recompute=True)
                    images[name]=camera.data.output['rgb'][0,:,:,:3].cpu().numpy().copy()
                return images
            counts=sorted({1,min(2,len(roots)),len(roots)})
            for count in counts:
                with visible_rooms_render(context.stage,roots,roots[:count]):
                    for _ in range(64):
                        scene.prepare_render();context.render();scene.update_render_cameras()
                    captures['legacy-'+str(count)] = read_rgb()
                    captures['isolated-'+str(count)] = pool.render_room(first_room,passes=64,capture=read_rgb)
            captures['isolated-repeat'] = pool.render_room(first_room,passes=64,capture=read_rgb)
            for repeat in range(2):
                captures['isolated-repeat-'+str(repeat+2)] = pool.render_room(first_room,passes=64,capture=read_rgb)
            captures['production-clean-3'] = pool.render_room(first_room,passes=3,capture=read_rgb)
            for repeat in range(3):
                captures['production-repeat-3-'+str(repeat+1)] = pool.render_room(first_room,passes=3,capture=read_rgb)
            for foreign in controllers:
                if foreign!=first_room:pool.render_room(foreign,passes=3)
            captures['production-after-foreign-3'] = pool.render_room(first_room,passes=3,capture=read_rgb)
            captures['diagnostic-after-foreign-64'] = pool.render_room(first_room,passes=64,capture=read_rgb)
            baseline=captures['isolated-1'];metrics={}
            for label,images in captures.items():
                metrics[label]={}
                for name,rgb in images.items():
                    Image.fromarray(rgb).save(parity_dir/(label+'-'+name+'.png'))
                    delta=rgb.astype(float)-baseline[name].astype(float)
                    metrics[label][name]=dict(mae=float(np.abs(delta).mean()),mean_rgb=float(rgb.mean()),
                        white_fraction=float(np.mean(np.all(rgb>=250,axis=-1))),max_abs_delta=float(np.abs(delta).max()))
            frozen_after=dict(tick=pool.physics_ticks,clock=float(context.current_time),robot=c.public_feedback(),
                raw_native_physx=raw_physx_state(),
                objects={n:dict(position_task=s['pos'].tolist(),rotation_task=s['mat'].tolist()) for n,s in c.snapshot()[0].items()})
            natural_noise={};mixed_delta={}
            for name,rgb in captures['production-clean-3'].items():
                natural_noise[name]=max(float(np.abs(captures['production-repeat-3-'+str(i)][name].astype(float)-rgb.astype(float)).mean()) for i in range(1,4))
                mixed_delta[name]=float(np.abs(captures['production-after-foreign-3'][name].astype(float)-rgb.astype(float)).mean())
            render_parity=dict(scope='same native process, identical frozen physical scene; foreign visibility/light membership only',
                reference_render_passes=64,production_render_passes=3,production_acceptance='not_frozen',
                production_repeated_noise_mae=natural_noise,production_after_foreign_mae=mixed_delta,
                frozen_state_unchanged=frozen_before==frozen_after, before=frozen_before,after=frozen_after,
                metrics=metrics,passed=frozen_before==frozen_after and all(
                    row['mae']<=1. for label,views in metrics.items() if label.startswith('isolated-') for row in views.values()))
            (out/'render-parity.private.json').write_text(json.dumps(render_parity,indent=2)+'\n')
        report = dict(schema='videoicl-mixed-room-pool-probe-v2', passed=bool(passed), pid=os.getpid(),
            kit_processes_launched=1, physics_context_count=1, room_count=len(rows),
            shared_clock_verified=clock_ok, measured_ticks=elapsed_ticks, measured_physics_seconds=elapsed_clock,
            barrier_action_verified=all(r['receipt']['step_after']==1 for r in rows),
            terminal_cache_verified=terminal_ok if args.verify_terminal_cache else None,
            all_rooms_sealed=bool(len(pool.terminal)==len(controllers)),terminal_receipts=terminal_receipts,
            simultaneous_pool_gate=gate_wait,
            render_isolation=pool.render_isolation, render_isolation_verified=None,
            static_render_reference_verified=render_parity['passed'] if render_parity else None,
            collision_groups=groups, global_signature=pool.global_signature, wall_seconds=time.perf_counter()-started,
            observation_resolution_override=args.camera_resolution, include_overview=args.include_overview,
            observation_capture_passes=args.capture_passes,
            light_linking='USD_render_visibility_and_light_intensity_isolation' if pool.render_isolation else 'authored_links_unverified_shared_render',
            physical_worlds_independently_paused=False, task_success_tested=False, final_agent_interface_tested=False,
            scope='native engineering controls and capacity only; GUI-only model evaluation not tested', rooms=rows,
            runtime_source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted((ROOT/'videoicl_isaaclab').glob('*.py'))})
        (out/'probe.private.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report), flush=True)
        code = 0 if passed else 2
    except BaseException:
        (out/'failure.txt').write_text(traceback.format_exc())
        traceback.print_exc()
    finally:
        measurements = sampler.close()
        (out/'gpu-monitor.private.json').write_text(json.dumps(measurements, indent=2)+'\n')
        sys.stdout.flush();sys.stderr.flush()
        if os.environ.get('VIC_SKIP_APP_CLOSE') == '1':os._exit(code)
        if app is not None:app.close(wait_for_replicator=False)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
