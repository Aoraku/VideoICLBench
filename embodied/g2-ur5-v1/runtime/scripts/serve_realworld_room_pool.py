"""Start a controller-private single-wave room pool for GUI sidecars.

No model is called here. Kit owns native state; CPU sidecars communicate using
private file RPC and expose only assigned RGB/button/mm GUI interactions.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from probe_realworld_room_pool import normalize_cases, GPUSampler
from videoicl_isaaclab.room_pool import RoomPool, filter_room_collisions, global_scene_signature
from videoicl_isaaclab.pool_rpc import PoolRPCWorker, atomic_json


def write_kit_settings_evidence(settings, output, *, requested_kit_args):
    """Read effective process settings without changing the Kit registry."""
    paths=(
        '/persistent/physics/useLocalMeshCache',
        '/physics/cooking/ujitsoCollisionCooking',
        '/physics/cooking/ujitsoRemoteCacheEnabled',
        '/renderer/activeGpu',
        '/renderer/multiGpu/enabled',
    )
    values={};errors={}
    for path in paths:
        try:
            value=settings.get(path)
            # Preserve None for unavailable settings; never infer a default
            # from a requested flag or confuse unavailable with False.
            if value is not None and type(value) not in (bool,int,float,str):
                raise TypeError('Unexpected Kit setting type: '+type(value).__name__)
            values[path]=value
        except Exception as exc:
            values[path]=None;errors[path]=repr(exc)
    evidence=dict(schema='videoicl-effective-kit-settings-v1',
        phase='after_app_launcher_before_stage_construction',pid=os.getpid(),
        captured_unix=time.time(),requested_kit_args=requested_kit_args,
        effective_settings=values,read_errors=errors,
        missing_settings=[path for path,value in values.items() if value is None])
    atomic_json(Path(output)/'kit-settings.private.json',evidence)
    return evidence


def native_rgb(array, *, diagnostic_root, room, name, tick, sensor=None):
    """Validate delivery, keeping uniform valid backgrounds as real evidence."""
    import numpy as np
    from PIL import Image
    array=np.asarray(array)
    valid=(array.ndim==4 and array.shape[0]==1 and array.shape[1]>=2 and
           array.shape[2]>=2 and array.shape[3] in (3,4) and array.dtype==np.uint8)
    quality=dict(annotator_shape=list(array.shape),dtype=str(array.dtype),delivery_valid=bool(valid),
                 sensor=sensor)
    image=array[0,:,:,:3] if valid else None
    if image is not None:
        quality.update(shape=list(image.shape),spatial_stddev=float(image.std(axis=(0,1)).mean()),
            minimum=int(image.min()),maximum=int(image.max()))
    # Preserve the actual pixels before any exception. Low variance is a
    # diagnostic trigger only; empty/NaN/non-uint8 annotators stay invalid.
    if not valid or quality['spatial_stddev']<=5:
        target=Path(diagnostic_root)/room/('tick-'+str(tick)+'-'+name)
        target.mkdir(parents=True,exist_ok=True,mode=0o700)
        if array.dtype.kind!='O':np.save(target/'annotator.npy',array,allow_pickle=False)
        if image is not None:Image.fromarray(image).save(target/'rgb.png')
        atomic_json(target/'camera.private.json',dict(room_id=room,camera=name,shared_tick=tick,**quality))
    if not valid:raise ValueError('Native RGB delivery shape/type invalid for '+room+'/'+name)
    return image,quality


def camera_clock(camera):
    """Only read actual sensor counters; unavailable attributes remain null."""
    import numpy as np
    result={}
    for key in ('frame','timestamp'):
        try:
            value=getattr(camera,key)
            if hasattr(value,'cpu'):value=value.cpu().numpy()
            values=np.asarray(value)
            result[key]=values.tolist() if np.isfinite(values).all() else None
        except (AttributeError,TypeError,ValueError,RuntimeError):result[key]=None
    return result


def identities(cases, raw, *, suite, epoch):
    source = {row.get('episode_id'): row for row in raw if row.get('episode_id')}
    result = {}
    for case in cases:
        room = case['episode_id']
        identity = source.get(room, {}).get('identity')
        if identity is None:
            identity = dict(run_id='embodied-'+uuid.uuid4().hex, task_id=case['task'],
                variant=case['variant'], seed=case['seed'], suite=suite, epoch=epoch)
        expected = {'run_id', 'task_id', 'variant', 'seed', 'suite', 'epoch'}
        if not isinstance(identity, dict) or set(identity) != expected:
            raise ValueError('Case identity must contain exactly six fields')
        if type(identity['seed']) is not int or any(
            not isinstance(identity[k], str) or not identity[k].strip() for k in expected-{'seed'}):
            raise ValueError('Invalid typed case identity')
        if (identity['task_id'], identity['variant'], identity['seed']) != (case['task'], case['variant'], case['seed']):
            raise ValueError('Case and identity task/variant/seed disagree')
        result[room] = dict(identity)
    if len({r['run_id'] for r in result.values()}) != len(result):
        raise ValueError('Each room must have a unique run identity')
    return result


def prepare_initial_progress(pool, controllers, output, *, physics_dt,
                             initial_window_ticks, max_extra_settle_seconds=2.):
    """Persist every room before bounded extra physics and baseline sealing."""
    import math
    from videoicl_isaaclab.realworld_progress_evidence import initial_diagnostics, seal_initial
    output=Path(output)
    folder=output/'initial-progress'
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    def snapshot(phase):
        diagnostics={}
        # Collect *all* rooms before raising, so a failure in one room cannot
        # hide the native initial evidence of its siblings.
        for room,controller in controllers.items():
            evaluator=controller.evaluator
            diagnostics[room]=initial_diagnostics(evaluator,room_id=room)
            atomic_json(folder/(room+'.'+phase+'.private.json'),dict(
                diagnostic=diagnostics[room],native_result=evaluator.result()))
        return diagnostics
    before=snapshot('pre-seal')
    diagnostics=before
    extra_ticks=0
    max_ticks=math.ceil(max_extra_settle_seconds/physics_dt)
    def native_rejected(ds):
        return any(not d['native_evidence_valid'] or d['source_initial_failures'] or d['initial_layout_failures'] or d['missing_required_groups'] for d in ds.values())
    # Source-invalid states are never repaired or reset by this progress helper.
    # Only still-moving denominator actors may receive bounded real settle ticks.
    while (not native_rejected(diagnostics) and extra_ticks<max_ticks and
           any(d['required_unstable_actors'] for d in diagnostics.values())):
        pool.tick();extra_ticks+=1
        diagnostics={room:initial_diagnostics(c.evaluator,room_id=room) for room,c in controllers.items()}
    diagnostics=snapshot('post-settle')
    metadata=dict(schema='videoicl-initial-progress-diagnostics-v2',
        shared_tick=pool.physics_ticks,initial_window_ticks=initial_window_ticks,
        extra_physics_ticks=extra_ticks,max_extra_settle_seconds=max_extra_settle_seconds,
        initial_diagnostics=before,final_diagnostics=diagnostics,
        all_rooms_can_seal=all(d['can_seal'] for d in diagnostics.values()))
    atomic_json(output/'initial-progress-diagnostics.private.json',metadata)
    failures=[(room,d) for room,d in diagnostics.items() if not d['can_seal']]
    if failures:
        details=[]
        for room,d in failures:
            actors=','.join(x['actor_id'] for x in d['required_unstable_actors']) or 'none'
            details.append(f"room={room} task={d['task']}/{d['variant']} unstable_required_actors={actors} source_failures={d['source_initial_failures']} layout_failures={d['initial_layout_failures']} errors={d['native_errors']} missing_groups={d['missing_required_groups']}")
        raise ValueError('Native initial admission rejected; '+ '; '.join(details)+
            '; evidence='+str(output/'initial-progress-diagnostics.private.json'))
    initial_snapshots={}
    for room,controller in controllers.items():
        seal_initial(controller.evaluator)
        initial_snapshots[room]=controller.evaluator.result()['progress_evidence']['initial']
    atomic_json(output/'initial-progress-evidence.private.json',dict(
        schema='videoicl-sealed-initial-progress-v2',shared_tick=pool.physics_ticks,
        measured_initial_window_ticks=initial_window_ticks,extra_physics_ticks=extra_ticks,
        rooms=initial_snapshots))
    return metadata


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--suite', default='videoicl-realworld50')
    p.add_argument('--epoch', required=True)
    p.add_argument('--barrier-timeout', type=float, required=True)
    p.add_argument('--barrier-policy',choices=['wait','fail_after_timeout'],default='wait')
    p.add_argument('--spacing', type=float, default=8.)
    p.add_argument('--initial-settle-extra-seconds',type=float,default=2.,
                   help='Bounded additional true-physics settling for dynamic-denominator actors; never reset/resample')
    p.add_argument('--capture-passes', type=int, default=3,
                   help='Explicit isolated render convergence; 64 is the correctness-first diagnostic candidate')
    p.add_argument('--experience', default='', help='Optional private Kit experience matching installed Isaac version')
    p.add_argument('--defer-stage-creation', action='store_true',
                   help='Use native SimulationApp option to skip default viewport wait, then explicitly create an empty stage')
    p.add_argument('--headless', action='store_true')
    p.add_argument('--enable_cameras', action='store_true', default=True)
    p.add_argument('--device', default='cpu')
    p.add_argument('--kit_args', default='--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0')
    args = p.parse_args()
    if not args.epoch.strip() or not 5 <= args.spacing <= 20 or not args.barrier_timeout > 0:
        p.error('Explicit epoch, valid spacing and positive barrier timeout required')
    if not 0 <= args.initial_settle_extra_seconds <= 10:
        p.error('initial-settle-extra-seconds must be between 0 and 10')
    if not 1 <= args.capture_passes <= 128:
        p.error('capture-passes must be between 1 and 128')
    payload = json.loads(args.cases.read_text())
    raw = payload['cases'] if isinstance(payload, dict) else payload
    cases = normalize_cases(raw, base=args.cases.resolve().parent)
    identity = identities(cases, raw, suite=args.suite, epoch=args.epoch)
    from videoicl_isaaclab.embodiments import select
    profiles = {case['episode_id']: select(case['task'], case['robot']) for case in cases}
    signatures = [global_scene_signature(profile.config) for profile in profiles.values()]
    if len({s['sha256'] for s in signatures}) != 1:
        raise ValueError('Incompatible physics, timing or lighting profiles in one pool')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    atomic_json(out/'cases.private.json', cases)
    sampler = GPUSampler();sampler.thread.start()
    app, code = None, 1
    try:
        from isaaclab.app import AppLauncher
        if args.defer_stage_creation:
            from isaacsim import SimulationApp
            # Lab2.3 filters create_new_stage out of forwarded kwargs. The
            # documented SimulationApp default applies in this private process.
            SimulationApp.DEFAULT_LAUNCHER_CONFIG['create_new_stage'] = False
        app = AppLauncher(headless=args.headless, enable_cameras=True, device=args.device,
                          experience=args.experience, kit_args=args.kit_args).app
        import carb.settings
        write_kit_settings_evidence(carb.settings.get_settings(),out,requested_kit_args=args.kit_args)
        if args.defer_stage_creation:
            import omni.usd
            omni.usd.get_context().new_stage()
        import base64
        import io
        import math
        from PIL import Image
        import isaaclab.sim as sim
        from videoicl_isaaclab.scene import TabletopScene
        from videoicl_isaaclab.control import Controller
        from videoicl_isaaclab.realworld_scenes import load, public_metadata
        from videoicl_isaaclab.realworld_evaluator_selector import create_evaluator
        from videoicl_isaaclab.realworld_progress_evidence import seal_initial
        first = profiles[cases[0]['episode_id']]
        options = {k: first.config['physics'][k] for k in ('enable_stabilization',) if k in first.config['physics']}
        context = sim.SimulationContext(sim.SimulationCfg(dt=first.config['physics']['dt'], device=args.device,
            enable_scene_query_support=True, physx=sim.PhysxCfg(**options)))
        scenes = {}
        columns = math.ceil(math.sqrt(len(cases)))
        for index, case in enumerate(cases):
            spec = load(case['task'], case['variant'], case['seed'], Path(case['bindings']))
            scenes[case['episode_id']] = TabletopScene(spec, embodiment=case['robot'],
                root_path=f'/World/Rooms/room_{index:02d}',
                origin=((index%columns)*args.spacing, (index//columns)*args.spacing, 0.),
                include_overview=False, light_isolation=True)
        filter_room_collisions(context.stage, [s.root_path for s in scenes.values()])
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
        controllers = {room: Controller(scene, context) for room, scene in scenes.items()}
        pool = RoomPool(context, controllers, render_isolation=True)
        for _ in range(240):pool.tick()
        for room, controller in controllers.items():
            controller.evaluator = create_evaluator(controller.scene.spec)
            controller.evaluator.reset_episode()
        # These are real shared physics ticks before ready/model admission, not
        # repeated copies of one snapshot. No room is reset or resampled here.
        initial_progress_ticks=math.ceil(.5/context.get_physics_dt())+2
        for _ in range(initial_progress_ticks):pool.tick()
        prepare_initial_progress(pool,controllers,out,physics_dt=context.get_physics_dt(),
            initial_window_ticks=initial_progress_ticks,
            max_extra_settle_seconds=args.initial_settle_extra_seconds)
        for room in controllers:
            scenes[room].initialize_cameras(context.device)

        captured_images = {}
        captured_calibration = {}

        def capture(room):
            if room in captured_images and captured_images[room][0] == pool.physics_ticks:
                return dict(captured_images[room][1])
            def readback():
                images = {};quality={};calibration={};depth={}
                for name in ('head', 'left_wrist', 'right_wrist'):
                    camera = scenes[room].cameras[name]
                    camera.update(0., force_recompute=True)
                    raw=camera.data.output['rgb'].cpu().numpy()
                    image,quality[name]=native_rgb(raw,diagnostic_root=out/'camera-diagnostics.private',
                        room=room,name=name,tick=pool.physics_ticks,sensor=camera_clock(camera))
                    buffer = io.BytesIO();Image.fromarray(image).save(buffer, format='JPEG', quality=94)
                    images[name] = base64.b64encode(buffer.getvalue()).decode()
                    calibration[name] = scenes[room].rgb_camera_calibration(name)
                    if 'distance_to_image_plane' in camera.data.output:
                        from videoicl_isaaclab.sensor_depth import encode_depth_packet
                        packet=encode_depth_packet(camera.data.output['distance_to_image_plane'].cpu().numpy(),
                            rgb_bytes=buffer.getvalue(), observation_tick=pool.physics_ticks)
                        if (packet['height'],packet['width']) != image.shape[:2]:
                            raise ValueError('RGB and sensor depth dimensions differ')
                        depth[name]=packet
                path=out/'native-camera-quality.private.jsonl'
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
                with os.fdopen(fd,'a') as stream:
                    stream.write(json.dumps(dict(room_id=room,shared_tick=pool.physics_ticks,
                        simulation_time=float(context.current_time),capture_passes=args.capture_passes,
                        cameras=quality),allow_nan=False)+'\n')
                captured_calibration[room] = dict(camera_calibration=calibration, observation_tick=pool.physics_ticks, _sensor_depth=depth)
                return images
            images = pool.render_room(room, passes=args.capture_passes, capture=readback)
            captured_images[room] = (pool.physics_ticks, images)
            return images

        hashes = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted((ROOT/'videoicl_isaaclab').glob('*.py'))}
        rooms = {}
        for case in cases:
            room = case['episode_id'];scene = scenes[room]
            limits = scene.embodiment.config['control']
            schema = dict(tokens=['STILL','GRASP','RELEASE','FWD','BACK','LEFT','RIGHT','UP','DOWN',
                'ROTATE_CCW','ROTATE_CW','PITCH_UP','PITCH_DOWN','ROLL_LEFT','ROLL_RIGHT'],
                step_mm=dict(minimum=limits['step_mm'][0], maximum=limits['step_mm'][1], default=min(limits['step_mm'][1],max(limits['step_mm'][0],20.))),
                rotation_deg=dict(minimum=limits['rotation_deg'][0],maximum=limits['rotation_deg'][1],default=min(limits['rotation_deg'][1],max(limits['rotation_deg'][0],10.))))
            rooms[room] = dict(identity=identity[room], case=case, public=public_metadata(case['task']),
                action_schema=schema, fingerprints=dict(runtime_source_sha256=hashes,
                    source_binding_sha256=scene.spec['source_binding_sha256'],
                    embodiment_config_sha256=scene.embodiment.config_hash,
                    provenance=scene.spec.get('provenance'), camera_profile=scene.spec['camera_profile']))
            capture(room)  # Verify RGB delivery before publishing ready.json.
        worker = PoolRPCWorker(pool, out/'rpc', rooms, capture,
            feedback=lambda room: dict(controllers[room].public_feedback(), **captured_calibration.get(room, {})),
            barrier_timeout_seconds=args.barrier_timeout,barrier_policy=args.barrier_policy, metadata=dict(global_signature=pool.global_signature,
                light_linking='USD_render_visibility_and_light_intensity_isolation',
                capture_passes=args.capture_passes,
                render_strategy='diagnostic_correctness_candidate' if args.capture_passes>=64 else 'production_candidate_unaccepted',
                final_agent_interface='GUI_only_sidecars'))
        print('POOL_READY '+str(out/'rpc/ready.json'), flush=True)
        while worker.poll_once():
            time.sleep(.02)  # Network/model wait never steps the shared world.
        code = 0 if not worker.failures else 2
    except BaseException:
        atomic_json(out/'failure.private.json', dict(kind='infrastructure_error', scored=False,
                    traceback=traceback.format_exc()))
        traceback.print_exc()
    finally:
        atomic_json(out/'gpu-monitor.private.json', sampler.close())
        sys.stdout.flush();sys.stderr.flush()
        if os.environ.get('VIC_SKIP_APP_CLOSE') == '1':os._exit(code)
        if app is not None:app.close(wait_for_replicator=False)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
