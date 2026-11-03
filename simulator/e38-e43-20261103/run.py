"""Portable entry point. Defaults to inspection; never invokes a model API."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, sys, time

ROOT = Path(__file__).resolve().parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--check', action='store_true')
p.add_argument('--task', choices=[f'E{n:02}' for n in range(38, 44)])
p.add_argument('--variant', choices=list('ABC'), default='A')
p.add_argument('--out', type=Path)
p.add_argument('--allow-unverified', action='store_true')
p.add_argument('--serve', action='store_true')
p.add_argument('--experience', default='')
args = p.parse_args()
if args.task is None and not args.check:
    p.print_help(); raise SystemExit(0)
if not (ROOT / 'asset_roots').is_dir():
    p.error('Run python download_data.py first, or restore the matching HF assets.')
env = dict(os.environ)
for d in (ROOT / 'asset_roots').iterdir():
    if d.is_dir(): env[d.name] = str(d)
env['VIC_EXECUTION_DESIGN_ASSETS'] = str(ROOT / 'runtime/execution-design-v3/assets')
env['VIC_FRANKA_ROBOTWIN_USD'] = str(ROOT / 'robot/franka-panda/robot.usd')
env['VIC_ENGINEERING_E43_ANALYTIC_BALL'] = '1'
env['VIC_ENGINEERING_E43_PASSIVE_RAIL'] = '1'
env['PYTHONPATH'] = str(ROOT / 'runtime') + os.pathsep + env.get('PYTHONPATH', '')
if args.check or args.task is None:
    checks = json.loads((ROOT / 'assets-manifest.json').read_bytes())
    for name, expected in checks.items():
        data = (ROOT / name).read_bytes()
        assert len(data) == expected['bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256'], name
    os.environ.update(env)
    sys.path.insert(0, str(ROOT / 'runtime'))
    from videoicl_isaaclab.realworld_scenes import load
    for c in json.loads((ROOT / 'cases.json').read_bytes()):
        load(c['task'], c['variant'], 4201, ROOT / 'bindings/I.private.json', verify_files=True)
    print(json.dumps(dict(files_verified=len(checks), source_scenes_verified=18,
                          world_started=False, summary=json.loads((ROOT / 'delivery.json').read_bytes()))))
    raise SystemExit(0)
case = next(c for c in json.loads((ROOT / 'cases.json').read_bytes())
            if (c['task'], c['variant']) == (args.task, args.variant))
if not case['functional_verified'] and not args.allow_unverified:
    p.error('This case has no complete functional proof yet. Read evidence; use --allow-unverified to run it.')
if args.out is None or args.out.exists(): p.error('--out must be a new output directory')
args.out = args.out.resolve()
args.out.mkdir(parents=True, exist_ok=False)
profile_name = ('profiles/e40-reviewed-gripper.json' if args.task == 'E40' else
                'profiles/e43-reviewed.json' if args.task == 'E43' else
                'profiles/e39-reviewed.json' if args.task in ('E39', 'E42') else
                'runtime/configs/embodiments/franka.json')
profile = ROOT / profile_name
if not profile.is_file(): p.error('Missing task-specific reviewed profile')
spec = dict(episode_id=case['episode_id'], task=args.task, variant=args.variant, seed=4201,
            bindings=str(ROOT / 'bindings/I.private.json'), robot=str(profile))
casefile = args.out / 'cases.private.json'; casefile.write_text(json.dumps([spec]))
cmd = [sys.executable, str(ROOT / 'runtime/scripts' /
       ('serve_realworld_room_pool.py' if args.serve else 'probe_realworld_room_pool.py')),
       '--cases', str(casefile), '--out', str(args.out / 'result'), '--headless', '--device', 'cpu']
if args.experience: cmd += ['--experience', args.experience]
if args.serve:
    cmd += ['--epoch', 'delivery-' + str(time.time_ns()), '--barrier-timeout', '120']
else:
    env.update(VIC_ENGINEERING_COOPERATIVE_REFERENCES='1', VIC_ENGINEERING_RENDER_HZ='5',
               VIC_ENGINEERING_STAGE_CHECKPOINTS='1', VIC_SKIP_APP_CLOSE='1')
    if args.task == 'E40': env['VIC_ENGINEERING_E40_COLLISION_COORDINATES'] = '1'
    if args.task == 'E43': env['VIC_ENGINEERING_E43_CONTACT_RESPONSE'] = '1'
    cmd += ['--execution-control', 'positive', '--execution-action-budget', '3000',
            '--execution-settle-ticks', '600']
raise SystemExit(subprocess.call(cmd, env=env))
