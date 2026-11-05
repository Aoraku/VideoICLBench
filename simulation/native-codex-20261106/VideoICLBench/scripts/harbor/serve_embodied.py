"""Launch one RealWorld50 scene for VideoICL's native CLI harness.

The Isaac Python environment and audited task runtime are controller inputs.
Task/variant/seed and the assigned demonstration come from the Harbor package.
This launcher never imports an expert policy or runs a model API loop.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'packages/sdk'))


def resolve_path(value):
    value = os.path.expandvars(value)
    if '${' in value:
        raise ValueError('Resolve the deployment variables in the assigned file path')
    return Path(value).expanduser().resolve(strict=True)


def load_assignment(task_dir, condition):
    task_dir = Path(task_dir).resolve(strict=True)
    native = json.loads((task_dir / 'environment/native.json').read_text())
    if native.get('kind') != 'embodied' or native.get('backend') != 'videoicl-native-slurm':
        raise ValueError('Expected a VideoICL native embodied Harbor task')
    if native.get('action_interface') != 'bounded_dual_arm_tokens_v1':
        raise ValueError('The task action interface does not match the bounded robot adapter')
    if native.get('agent_interaction') != 'gui_only' or native.get('agent_protocol') != 'roboprobe_gui_v1':
        raise ValueError('This task requires the RoboProbe GUI protocol')
    raw = (task_dir / 'instruction.md').read_bytes()
    if native.get('instruction_hash_scheme') != 'sha256_utf8_exact_file_bytes' or hashlib.sha256(raw).hexdigest() != native['instruction_sha256']:
        raise ValueError('Harbor instruction checksum mismatch')
    instruction = raw.decode().strip()
    if condition == 'text_rule':
        rule = json.loads((task_dir / 'tests/rule.json').read_text())['rule']
        return native, instruction, None, rule
    field = 'demo' if condition == 'real' else 'demo_sim'
    demo = native.get(field)
    if not isinstance(demo, dict) or not demo.get('path') or not demo.get('sha256'):
        raise ValueError('This task has no assigned ' + condition + ' demonstration')
    demo = dict(demo, path=str(resolve_path(demo['path'])))
    if hashlib.sha256(Path(demo['path']).read_bytes()).hexdigest() != demo['sha256']:
        raise ValueError('Assigned demonstration checksum mismatch')
    return native, instruction, demo, None


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--task-dir', type=Path, required=True)
    p.add_argument('--runtime-root', type=Path, required=True, help='Audited runtime containing videoicl_isaaclab/')
    p.add_argument('--bindings', type=Path, required=True)
    p.add_argument('--robot', required=True, help='Native robot profile name or audited JSON path')
    p.add_argument('--condition', choices=['real', 'sim', 'text_rule'], required=True)
    p.add_argument('--max-actions', type=int, required=True)
    p.add_argument('--timeout', type=int, required=True)
    p.add_argument('--epoch', required=True)
    p.add_argument('--suite', default='videoicl-realworld50')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--port', type=int, default=0)
    p.add_argument('--frontend-root', type=Path, default=ROOT / 'apps/portal/public/embodied')
    p.add_argument('--allow-unvalidated-environment', action='store_true', help='Explicit validation-only session; never marks task ready')
    p.add_argument('--headless', action='store_true')
    p.add_argument('--enable-cameras', action='store_true', default=True)
    p.add_argument('--device', default='cpu')
    p.add_argument('--kit-args', default='--/renderer/multiGpu/enabled=false --/renderer/activeGpu=0')
    return p


def main():
    args = parser().parse_args()
    from vic_sdk.embodied_environment.episode import Episode, Identity, private_write
    from vic_sdk.embodied_environment.native import ControllerRuntime
    from vic_sdk.embodied_environment.server import serve
    native, instruction, demo, text_rule = load_assignment(args.task_dir, args.condition)
    validated = (native.get('readiness') in ('available', 'ready')
                 and native.get('native_interaction_validated') is True
                 and native.get('budget', {}).get('status') == 'frozen')
    if not validated and not args.allow_unvalidated_environment:
        raise ValueError('Native interaction is unvalidated; use the explicit validation-only flag for acceptance work')
    if validated and not args.allow_unvalidated_environment and (
        native['budget'].get('max_actions') != args.max_actions
        or native['budget'].get('timeout_sec') != args.timeout):
        raise ValueError('Formal episode budgets must match the frozen task package')
    if not 1 <= args.max_actions or not 0 <= args.timeout or not 0 <= args.port <= 65535:
        raise ValueError('Positive budgets and a valid local port are required')
    runtime = args.runtime_root.resolve(strict=True)
    if not (runtime / 'videoicl_isaaclab/realworld_scenes.py').is_file():
        raise ValueError('The selected runtime does not contain RealWorld50 scenes')
    sys.path.insert(0, str(runtime))
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    app = None
    try:
        from isaaclab.app import AppLauncher
        app = AppLauncher(headless=args.headless, enable_cameras=True, device=args.device,
                          kit_args=args.kit_args).app
        import isaaclab.sim as sim
        from videoicl_isaaclab.realworld_scenes import load, public_metadata
        from videoicl_isaaclab.scene import TabletopScene
        from videoicl_isaaclab.control import Controller
        from videoicl_isaaclab.embodiments import select
        from videoicl_isaaclab.realworld_evaluator_selector import create_evaluator
        profile = select(native['task_id'], args.robot)
        physics = profile.config['physics']
        physx = {}
        if 'enable_stabilization' in physics:
            physx['enable_stabilization'] = physics['enable_stabilization']
        context = sim.SimulationContext(sim.SimulationCfg(dt=physics['dt'], device=args.device,
            enable_scene_query_support=True, physx=sim.PhysxCfg(**physx)))
        spec = load(native['task_id'], native['variant'], native['seed'], args.bindings)
        if spec.get('provenance', {}).get('dataset_revision') != native.get('dataset_revision'):
            raise ValueError('Harbor task and native runtime dataset revisions differ')
        scene = TabletopScene(spec, embodiment=args.robot)
        context.reset()
        for robot in scene.robots.values():
            robot.write_joint_state_to_sim(robot.data.default_joint_pos, robot.data.default_joint_vel)
            robot.set_joint_position_target(robot.data.default_joint_pos)
            robot.write_data_to_sim()
        for _ in range(8):
            scene.apply_passive_efforts()
            context.step(render=False)
            scene.update_physics(context.get_physics_dt())
        controller = Controller(scene, context)
        for _ in range(240):
            controller.tick()
        controller.evaluator = create_evaluator(scene.spec)
        controller.evaluator.reset_episode()
        state, contacts = controller.snapshot()
        update = getattr(controller.evaluator, 'update_mechanisms', None)
        if update:
            update(controller.snapshot_mechanisms())
        update = getattr(controller.evaluator, 'update_contact_forces', None)
        if update:
            update(controller.contact_forces)
        controller.evaluator.update(state, contacts, controller.dt)
        initial = controller.evaluator.result()
        if initial.get('history_valid') is False or initial.get('errors') or any(
            c.get('type') == 'source_initial_state' and c.get('passed') is not True for c in initial.get('conditions', [])):
            raise ValueError('The native evaluator rejected the initial source state')
        scene.initialize_cameras(context.device)
        controller.started = True
        identity = Identity('embodied-' + uuid.uuid4().hex, native['task_id'], native['variant'],
                            native['seed'], args.suite, args.epoch)
        limits = profile.config['control']
        schema = dict(tokens=['STILL', 'GRASP', 'RELEASE', 'FWD', 'BACK', 'LEFT', 'RIGHT', 'UP', 'DOWN',
                'ROTATE_CCW', 'ROTATE_CW', 'PITCH_UP', 'PITCH_DOWN', 'ROLL_LEFT', 'ROLL_RIGHT'],
            step_mm=dict(minimum=limits['step_mm'][0], maximum=limits['step_mm'][1],
                         default=min(limits['step_mm'][1], max(limits['step_mm'][0], 20.))),
            rotation_deg=dict(minimum=limits['rotation_deg'][0], maximum=limits['rotation_deg'][1],
                              default=min(limits['rotation_deg'][1], max(limits['rotation_deg'][0], 10.))))
        episode = Episode(ControllerRuntime(controller), identity, title=public_metadata(native['task_id'])['title'],
            instruction=instruction, condition=args.condition, max_actions=args.max_actions,
            timeout_seconds=args.timeout, output=out / 'environment', action_schema=schema,
            demo=demo, text_rule=text_rule, require_rule_report=False,
            validation_only=bool(args.allow_unvalidated_environment or not validated))
        episode.observe()  # Require complete native RGB before publishing the connection.
        actor, admin = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        for name, value in [('actor-token', actor), ('admin-token', admin)]:
            p = out / name
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as stream:
                stream.write(value)
        hashes = {str(p.relative_to(runtime)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted((runtime / 'videoicl_isaaclab').glob('*.py'))}
        private_write(out / 'native-provenance.private.json', dict(identity=asdict(identity),
            runtime_root=str(runtime), runtime_source_sha256=hashes,
            source_binding_sha256=spec['source_binding_sha256'], embodiment_config_sha256=profile.config_hash,
            physics=physics, camera_profile=scene.spec['camera_profile'], initial_evidence=initial,
            validation_only=episode.validation_only))

        def ready(port):
            private_write(out / 'connection.private.json', dict(control_url=f'http://127.0.0.1:{port}',
                identity=asdict(identity), actor_token_file=str(out / 'actor-token'),
                admin_token_file=str(out / 'admin-token'), condition=args.condition,
                max_actions=args.max_actions, timeout_seconds=args.timeout, demo=demo,
                agent_interaction='gui_only', agent_protocol='roboprobe_gui_v1',
                validation_only=episode.validation_only,
                runtime_fingerprints=dict(source_binding_sha256=spec['source_binding_sha256'],
                    embodiment_config_sha256=profile.config_hash,
                    runtime_source_sha256=hashes, camera_profile=scene.spec['camera_profile']),
                task_dir=str(args.task_dir.resolve()), environment_output=str(out / 'environment')))
            print(json.dumps(dict(event='environment_ready', run_id=identity.run_id,
                                  connection=str(out / 'connection.private.json'))), flush=True)

        serve(episode, port=args.port, agent_token=actor, admin_token=admin,
              frontend=args.frontend_root, ready=ready)
        return 0
    except Exception:
        private_write(out / 'infrastructure-failure.private.json', dict(traceback=traceback.format_exc()))
        raise
    finally:
        if app is not None:
            app.close(wait_for_replicator=False)


if __name__ == '__main__':
    raise SystemExit(main())
