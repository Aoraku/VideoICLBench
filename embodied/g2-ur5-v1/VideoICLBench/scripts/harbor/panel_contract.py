"""Frozen optional sim-panel contract. Pure planning/validation; no GPU or API calls."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

SCHEMA = 'videoicl-frozen-panel-v1'
ISOLATED = {'E42', 'E43', 'E45'}
SIM20_TASKS = frozenset(('E01','E02','E03','E05','E07','E10','E13','E15','E18','E20',
                         'E23','E25','E27','E30','E31','E32','E35','E40','E46','E50'))
INFERENCE_SIX = (('E01','A'),('E02','B'),('E38','C'),('E04','A'),('E06','B'),('E49','C'))
INFERENCE_WAVE = 'inference_generalization_six'
BINDING_FIELDS = ('logical_gpu_index', 'physical_slot', 'ssh_user', 'hostname', 'gpu_uuid', 'expected_pool_count')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def identity(row):
    return {key: row[key] for key in ('task_id', 'variant', 'seed', 'input_condition')}


def key_for(row):
    return f"embodied-{row['task_id'].lower()}-{row['variant'].lower()}--{row['input_condition']}--seed{row['seed']}"


def wave_shape(wave, bindings=None):
    if wave == INFERENCE_WAVE:
        if not isinstance(bindings, list) or not 3 <= len(bindings) <= 6:
            raise ValueError('Inference six requires explicit 3..6 GPU bindings')
        slots = [b.get('physical_slot') for b in bindings]
        if any(type(s) is not int or s < 0 for s in slots) or len(set(slots)) != len(slots):
            raise ValueError('Inference six requires unique explicit physical slots')
        if any(type(b.get('expected_pool_count')) is not int or not 1 <= b['expected_pool_count'] <= 2 for b in bindings) or sum(b['expected_pool_count'] for b in bindings) != 6:
            raise ValueError('Inference six requires six pools, at most two per GPU')
        return {t for t,v in INFERENCE_SIX}, slots, 2
    if wave == 'e01_abc_sensor_harness':
        return {'E01'}, [27, 30], 2
    if wave == 'e31_bc_harness':
        return {'E31'}, [27], 2
    if wave == 'sim20_harness':
        return SIM20_TASKS, [25, 26], 2
    if wave == 'sim147':
        return {f'E{i:02d}' for i in range(1, 51)} - {'E37'}, list(range(25, 38)), 2
    if wave == 'pending3':
        return {'E37'}, [38], 1
    raise ValueError('Unknown frozen sim wave')



REMAINING300_IDENTITY_SHA = 'f188dacd023162fd1040793ac20620498f7907854ed87cf38d2c6841601b8455'
REMAINING300_EXCLUDED150_SHA = 'ba224ac51c2de931a298bd406cae16c9a9937aa9ecfdd9ed6d8d448f7855b63f'

def validate_remaining300_contract(contract):
    if contract.get('schema') != SCHEMA or contract.get('campaign_id') != 'inference450-remaining300-qa-20261102':
        raise ValueError('Remaining300 campaign mismatch')
    ids=contract.get('expected_identities',[])
    if len(ids)!=300 or digest(ids)!=REMAINING300_IDENTITY_SHA or contract.get('expected_identity_sha256')!=REMAINING300_IDENTITY_SHA or contract.get('excluded_first150_sha256')!=REMAINING300_EXCLUDED150_SHA:
        raise ValueError('Fixed450 minus first150 identity lock mismatch')
    if len({key_for(x)for x in ids})!=300 or any(set(x)!={'task_id','variant','seed','input_condition'} or x['seed']!=4201 for x in ids):
        raise ValueError('Remaining300 exact identities required')
    bindings=contract.get('bindings',[])
    if [b.get('logical_gpu_index')for b in bindings]!=list(range(10)) or [b.get('physical_slot')for b in bindings]!=[3,5,6,7,10,11,12,13,15,22]:
        raise ValueError('Only user authorized slots permitted')
    for b in bindings:
        if not isinstance(b.get('expected_pool_count'),int)or not 1<=b['expected_pool_count']<=(8 if b['logical_gpu_index']==0 else 6) or not 1<=b.get('max_concurrent_pool_count',0)<=6 or b.get('ssh_user')!=f"jiemingli.{b['physical_slot']}"or not b.get('hostname')or not re.fullmatch(r'GPU-[A-Za-z0-9-]+',b.get('gpu_uuid','')):
            raise ValueError('Pinned slot and pool count required')
    if len({b['gpu_uuid']for b in bindings})!=10 or contract.get('no_hot_add')is not True or contract.get('no_replay')is not True:
        raise ValueError('Independent first assignments and no replay required')
    return bindings

def validate_remaining300_panel(plan):
    c=plan['panel_contract'];bindings=validate_remaining300_contract(c)
    if plan.get('campaign_id')!=c['campaign_id']:raise ValueError('Campaign mismatch')
    rows=plan.get('episodes',[]);actual={r.get('episode_key'):r for r in rows};expected={key_for(r):r for r in c['expected_identities']}
    if len(rows)!=300 or len(actual)!=300 or set(actual)!=set(expected):raise ValueError('Missing or duplicate remaining identity')
    for key,r in actual.items():
        if identity(r)!=expected[key] or r.get('task_directory')!=f"embodied-{r['task_id'].lower()}-{r['variant'].lower()}" or r.get('campaign_id')!=plan['campaign_id']:raise ValueError('Room identity changed')
        blocked=r['task_id']=='E37' and r['input_condition']=='sim'
        if r.get('fresh_environment_required')is not True or r.get('fresh_agent_session_required')is not True or r.get('attempt_status')!='not_started' or r.get('status')!=('blocked_native_demo_missing'if blocked else'not_started'):raise ValueError('Cannot import started identity')
        for f in ('task_manifest_sha256','rule_file_sha256','comparison_contract_sha256','global_fingerprint'):
            if not re.fullmatch(r'[0-9a-f]{64}',r.get(f,'')):raise ValueError('Required room hash missing')
        if r['input_condition']=='text_rule':
            if r.get('input_material')is not None:raise ValueError('Text condition cannot have video')
        else:
            m=r.get('input_material')or{};field='demo_sim'if r['input_condition']=='sim'else'demo'
            if not(blocked and field=='demo_sim'and not m)and(m.get('field')!=field or not m.get('path')or not re.fullmatch(r'[0-9a-f]{64}',m.get('sha256',''))):raise ValueError('Wrong or missing source media')
    pools=plan.get('pools',[]);seen=[];assigned=set();allowed={b['logical_gpu_index']:b['expected_pool_count']for b in bindings}
    if len(pools)!=52:raise ValueError('52 frozen pools required')
    for p in pools:
        gpu,index=p['logical_gpu_index'],p['pool_index'];keys=p['episode_keys']
        if gpu not in allowed or not 0<=index<allowed[gpu]or(gpu,index)in assigned or p['pool_id']!=f'gpu-{gpu:02d}-pool-{index:02d}':raise ValueError('Duplicate or undeclared pool')
        assigned.add((gpu,index))
        if len(keys)not in(2,3,6)or p['planned_occupied_rooms']!=len(keys)or p['configured_room_capacity']!=len(keys):raise ValueError('Only 2, 3 or 6 independent rooms')
        members=[actual[k]for k in keys]
        if len({r['task_id']for r in members})!=1 or len({r['inference_group']for r in members})!=1 or {r['global_fingerprint']for r in members}!={p['global_fingerprint']}:raise ValueError('Pool cohort mismatch')
        for i,r in enumerate(members):
            if(r['pool_id'],r['logical_gpu_index'],r['room_slot'])!=(p['pool_id'],gpu,i):raise ValueError('Room binding mismatch')
        if any(r['task_id']=='E37'for r in members)and(gpu!=0 or len(members)!=2 or {r['input_condition']for r in members}!={'real','text_rule'} or p.get('status')!='planned' or p.get('dispatch_phase')!='after_initial_pools' or p.get('model_launch_enabled')is not False):raise ValueError('E37 real/text pool must remain queued')
        seen.extend(keys)
    blocked=[k for k,r in actual.items()if r['task_id']=='E37' and r['input_condition']=='sim']
    if len(blocked)!=3 or any(actual[k].get(f)is not None for k in blocked for f in ('pool_id','logical_gpu_index','room_slot')):raise ValueError('Missing sim must remain unassigned')
    if Counter(seen+blocked)!=Counter(actual.keys())or Counter(p['logical_gpu_index']for p in pools)!=allowed:raise ValueError('Pool membership mismatch')
    dispatch=plan.get('dispatch_pool_ids',[])
    expected_dispatch=[p['pool_id']for p in pools]
    if dispatch!=expected_dispatch or len(dispatch)!=52:raise ValueError('Dispatch must contain 52 reviewed executable pools; material blocked rooms have no pool')
    return rows

def validate_contract(contract):
    if contract.get("wave")=="frozen_remaining300":return validate_remaining300_contract(contract)
    if contract.get('schema') != SCHEMA:
        raise ValueError('Versioned frozen panel contract required')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', contract.get('campaign_id', '')):
        raise ValueError('Invalid campaign identity')
    tasks, slots, pool_count = wave_shape(contract.get('wave'), contract.get('bindings'))
    ids = contract.get('expected_identities', [])
    variants = {'sim20_harness': 'A', 'e31_bc_harness': 'BC'}.get(contract.get('wave'), 'ABC')
    expected = {(t, v, 'sim') for t in tasks for v in variants}
    if contract.get('wave') == INFERENCE_WAVE:
        expected = {(t,v,'sim') for t,v in INFERENCE_SIX}
    if len(ids) != len(expected) or {(r.get('task_id'), r.get('variant'), r.get('input_condition')) for r in ids} != expected:
        raise ValueError('Frozen wave must cover its complete exact task/variant/condition set')
    if any(type(r.get('seed')) is not int or r['seed'] < 0 or set(r) != {'task_id','variant','seed','input_condition'} for r in ids):
        raise ValueError('Explicit exact episode identity and seed required')
    if contract.get('wave') in {'e31_bc_harness','e01_abc_sensor_harness', INFERENCE_WAVE} and any(r['seed'] != 4201 for r in ids):
        raise ValueError('E31 B/C engineering test freezes seed 4201')
    if digest(ids) != contract.get('expected_identity_sha256'):
        raise ValueError('Expected identity lock differs')
    rows = contract.get('bindings', [])
    if [r.get('logical_gpu_index') for r in rows] != list(range(len(slots))) or [r.get('physical_slot') for r in rows] != slots:
        raise ValueError('Frozen wave physical/logical slot assignments differ')
    for row in rows:
        if (contract.get('wave') != INFERENCE_WAVE and row.get('expected_pool_count') != (1 if contract.get('wave') == 'e01_abc_sensor_harness' and row['physical_slot'] == 30 else pool_count)) or row.get('ssh_user') != f"jiemingli.{row['physical_slot']}" or not row.get('hostname') or not re.fullmatch(r'GPU-[A-Za-z0-9-]+', row.get('gpu_uuid','')):
            raise ValueError('Explicit frozen host/GPU/SSH/pool binding required')
    if len({r['gpu_uuid'] for r in rows}) != len(rows):
        raise ValueError('Duplicate physical GPU')
    if contract.get('no_hot_add') is not True or contract.get('no_replay') is not True:
        raise ValueError('Frozen panel prohibits hot additions and replay')
    return rows


def validate_frozen_panel(plan):
    if plan.get("panel_contract",{}).get("wave")=="frozen_remaining300":return validate_remaining300_panel(plan)
    contract = plan['panel_contract']; bindings = validate_contract(contract)
    if plan.get('campaign_id') != contract['campaign_id']:
        raise ValueError('Plan and frozen campaign differ')
    rows = plan.get('episodes', [])
    expected = {key_for(r): r for r in contract['expected_identities']}
    actual = {r.get('episode_key'): r for r in rows}
    if len(rows) != len(expected) or len(actual) != len(rows) or set(actual) != set(expected):
        raise ValueError('Plan must contain every frozen episode exactly once')
    for key, row in actual.items():
        if identity(row) != expected[key] or row.get('task_directory') != f"embodied-{row['task_id'].lower()}-{row['variant'].lower()}":
            raise ValueError('Frozen episode identity differs')
        if row.get('campaign_id') != plan['campaign_id'] or row.get('fresh_environment_required') is not True or row.get('fresh_agent_session_required') is not True:
            raise ValueError('Independent campaign environment/session required')
        if row.get('attempt_status') != 'not_started' or row.get('status') != 'not_started':
            raise ValueError('Frozen plan cannot import an already started episode')
        for field in ('task_manifest_sha256', 'rule_file_sha256', 'comparison_contract_sha256', 'global_fingerprint'):
            if not re.fullmatch(r'[0-9a-f]{64}', row.get(field, '')):
                raise ValueError('Frozen episode hash required: ' + field)
        media = row.get('input_material') or {}
        if media.get('field') != 'demo_sim' or not isinstance(media.get('path'), str) or not media['path'] or not re.fullmatch(r'[0-9a-f]{64}', media.get('sha256','')):
            raise ValueError('Exact sim demo path/hash required; no real fallback')
    pools = plan.get('pools', []); seen = []; pairs = set()
    allowed = {b['logical_gpu_index']: b['expected_pool_count'] for b in bindings}
    for pool in pools:
        gpu, index = pool['logical_gpu_index'], pool['pool_index']
        if gpu not in allowed or type(index) is not int or not 0 <= index < allowed[gpu] or (gpu,index) in pairs:
            raise ValueError('Duplicate or undeclared pool assignment')
        pairs.add((gpu,index))
        if pool['pool_id'] != f'gpu-{gpu:02d}-pool-{index:02d}':
            raise ValueError('Pool ID and assignment differ')
        keys = pool['episode_keys']
        if not 1 <= len(keys) <= 8 or len(keys) != pool['planned_occupied_rooms'] or any(k not in actual for k in keys):
            raise ValueError('Pool must have 1..8 frozen episodes')
        if contract.get('wave') == 'sim20_harness' and (len(keys) != 5 or pool.get('configured_room_capacity') != 5):
            raise ValueError('sim20_harness requires exactly five episodes per pool')
        if contract.get('wave') in {'e31_bc_harness','e01_abc_sensor_harness', INFERENCE_WAVE} and (len(keys) != 1 or pool.get('configured_room_capacity') != 1):
            raise ValueError('e31_bc_harness requires exactly one episode in each independent pool')
        if contract.get('wave') == 'e01_abc_sensor_harness':
            expected_variant = {(0,0):'A',(0,1):'B',(1,0):'C'}[(gpu,index)]
            if actual[keys[0]]['variant'] != expected_variant:
                raise ValueError('E01 ABC requires frozen A/B on slot27 and C on slot30')
        members = [actual[k] for k in keys]; tasks = {r['task_id'] for r in members}
        if tasks & ISOLATED and len(tasks) != 1:
            raise ValueError('Isolated tasks require same-task pools')
        if {r['global_fingerprint'] for r in members} != {pool['global_fingerprint']}:
            raise ValueError('Pool global simulation profiles differ')
        for slot, row in enumerate(members):
            if (row.get('pool_id'), row.get('logical_gpu_index'), row.get('room_slot')) != (pool['pool_id'], gpu, slot):
                raise ValueError('Episode pool/room membership differs')
        seen.extend(keys)
    if Counter(seen) != Counter(actual.keys()) or Counter(p['logical_gpu_index'] for p in pools) != allowed:
        raise ValueError('Frozen pool membership incomplete or duplicated')
    return rows


def validate_deployment_contract(cfg, plan=None):
    contract = cfg['panel_contract']; bindings = validate_contract(contract)
    if plan is not None and plan.get('panel_contract') != contract:
        raise ValueError('Deployment and plan frozen contracts differ')
    if cfg.get('campaign_id') != contract['campaign_id']:
        raise ValueError('Deployment and contract campaign differ')
    cfg_bindings = cfg.get('bindings', [])
    if len(cfg_bindings) != len(bindings) or [{k:r.get(k) for k in BINDING_FIELDS} for r in cfg_bindings] != [{k:r[k] for k in BINDING_FIELDS} for r in bindings]:
        raise ValueError('Deployment physical bindings differ from frozen contract')
    if contract.get('wave') == INFERENCE_WAVE:
        profiles = cfg.get('task_robot_profiles')
        if not isinstance(profiles, dict) or set(profiles) != {t for t,v in INFERENCE_SIX}:
            raise ValueError('Inference six requires six explicitly pinned task robot profiles')
        for task, profile in profiles.items():
            if (not isinstance(profile,dict) or set(profile) != {'path','sha256'}
                    or not isinstance(profile['path'],str) or not Path(profile['path']).is_absolute()
                    or '..' in Path(profile['path']).parts or not re.fullmatch(r'[0-9a-f]{64}', profile.get('sha256',''))):
                raise ValueError('Inference robot profile requires absolute path and SHA256')
        g1_hashes = {profiles[t]['sha256'] for t in ('E01','E02','E38')}
        g2_hashes = {profiles[t]['sha256'] for t in ('E04','E06','E49')}
        if len(g1_hashes) != 1 or len(g2_hashes) != 1 or g1_hashes == g2_hashes:
            raise ValueError('Inference G1/G2 require distinct, internally uniform robot/table profiles')
        if plan is not None:
            for row in plan['episodes']:
                profile = profiles[row['task_id']]
                if (row.get('robot_profile_path'), row.get('robot_profile_sha256')) != (profile['path'],profile['sha256']):
                    raise ValueError('Inference plan and deployment robot profiles differ')
    remote = Path(cfg.get('remote_deployment_path', ''))
    if not remote.is_absolute() or '..' in remote.parts or remote.name != 'deployment.private.json' or remote.parent.name != 'config' or remote.parent.parent.name != cfg['campaign_id']:
        raise ValueError('Explicit campaign/config/deployment.private.json remote path required')
    state = Path(cfg.get('state_root', ''))
    if not state.is_absolute() or '..' in state.parts or not state.is_relative_to(remote.parent.parent) or state == remote.parent.parent:
        raise ValueError('State root must be private to the frozen extension campaign')
    return bindings


def build_sim_plan(task_root, compatibility, bindings, *, paired_plan, campaign_id='sim147-20261030', wave='sim147', started_episode_keys=()):
    """Build a frozen full wave or sim20 harness test from canonical packages.

    All 150 native specs must exist. Only selected sim demo records are required;
    preflight later checks their bytes. paired_plan is the frozen original300.
    No existing attempt directory is read or reused; callers must supply any known
    prior started sim episode keys to reject replay, then use a new state root.
    """
    from plan_embodied_campaign import load_episodes
    from preflight_embodied300 import validate_panel
    validate_panel(paired_plan)
    tasks, slots, pool_count = wave_shape(wave, bindings)
    rows = [r for r in load_episodes(Path(task_root), compatibility) if r['input_condition'] == 'sim' and r['task_id'] in tasks]
    if wave == 'sim20_harness':
        rows = [r for r in rows if r['variant'] == 'A']
    if wave == 'e31_bc_harness':
        rows = [r for r in rows if r['variant'] in 'BC']
    if wave == INFERENCE_WAVE:
        rows = [r for r in rows if (r['task_id'],r['variant']) in INFERENCE_SIX]
    paired = {(r['task_id'], r['variant']):r for r in paired_plan['episodes'] if r['input_condition']=='real'}
    for row in rows:
        rule_file = Path(task_root)/row['task_directory']/'tests/rule.json'
        row['rule_file_sha256'] = hashlib.sha256(rule_file.read_bytes()).hexdigest()
        row['comparison_contract_sha256'] = digest(dict(base_contract_sha256=row['comparison_contract_sha256'], rule_file_sha256=row['rule_file_sha256']))
        if wave == INFERENCE_WAVE:
            spec = json.loads((Path(task_root)/row['task_directory']/'environment/native.json').read_text())
            profile = spec.get('robot_profile', {})
            if not isinstance(profile.get('path'), str) or not re.fullmatch(r'[0-9a-f]{64}', profile.get('sha256','')):
                raise ValueError('Inference native spec requires pinned robot profile')
            row.update(robot_profile_path=profile['path'],robot_profile_sha256=profile['sha256'])
        base = paired[(row['task_id'],row['variant'])]
        if wave == INFERENCE_WAVE:
            if row['seed'] != base['seed'] or row['rule_file_sha256'] != base.get('rule_file_sha256'):
                raise ValueError('Inference six preserves the original seed and rule file')
        elif (row['seed'],row['comparison_contract_sha256']) != (base['seed'],base['comparison_contract_sha256']):
            raise ValueError('Sim scene/seed/budget/rule contract differs from original real/text pair')
    if set(started_episode_keys) & {r['episode_key'] for r in rows}:
        raise ValueError('Refusing to replay a previously started sim episode')
    frozen_bindings = deepcopy(bindings)
    for b in frozen_bindings: b.setdefault('expected_pool_count', 1 if wave == 'e01_abc_sensor_harness' and b['physical_slot'] == 30 else pool_count)
    ids = [identity(r) for r in sorted(rows,key=lambda r:r['episode_key'])]
    contract = dict(schema=SCHEMA,campaign_id=campaign_id,wave=wave,expected_identities=ids,
        expected_identity_sha256=digest(ids),bindings=frozen_bindings,no_hot_add=True,no_replay=True)
    validate_contract(contract)
    ordinary = sorted([r for r in rows if r['task_id'] not in ISOLATED],key=lambda r:r['episode_key'])
    room_count = {INFERENCE_WAVE: 1, 'sim20_harness': 5, 'e31_bc_harness': 1, 'e01_abc_sensor_harness': 1}.get(wave, 6)
    if wave == INFERENCE_WAVE:
        ordinary.sort(key=lambda r: INFERENCE_SIX.index((r['task_id'],r['variant'])))
    buckets = [ordinary[i:i+room_count] for i in range(0,len(ordinary),room_count)]
    buckets += [[r for r in rows if r['task_id']==task] for task in sorted(ISOLATED) if any(r['task_id']==task for r in rows)]
    assignments=[(b['logical_gpu_index'],j) for b in frozen_bindings for j in range(b['expected_pool_count'])]
    if len(buckets) != len(assignments): raise ValueError('Frozen packing differs from wave shape')
    plan = {k:deepcopy(v) for k,v in paired_plan.items() if k not in ('episodes','pools','gpus','statistics','panel_contract')}
    plan.update(campaign_id=campaign_id,panel_contract=contract,selected_input_conditions=['sim'],episodes=[],pools=[],gpus=[],
        status='planned_not_authorized_for_launch',planning_only=True)
    plan['source_episode_plan_sha256'] = hashlib.sha256((Path(task_root)/'episode-plan.json').read_bytes()).hexdigest()
    plan['compatibility_manifest_sha256'] = digest(compatibility)
    for number, members in enumerate(buckets):
        gpu,index = assignments[number]; pool_id=f'gpu-{gpu:02d}-pool-{index:02d}'
        plan['pools'].append(dict(pool_id=pool_id,logical_gpu_index=gpu,pool_index=index,configured_room_capacity={INFERENCE_WAVE: 1, 'sim20_harness': 5, 'e31_bc_harness': 1, 'e01_abc_sensor_harness': 1}.get(wave, 8),
            planned_occupied_rooms=len(members),native_live_rooms=0,global_fingerprint=members[0]['global_fingerprint'],
            validation_group=members[0]['task_id'] if members[0]['task_id'] in ISOLATED else 'mixed',
            mixed_task_count=len({r['task_id'] for r in members}),episode_keys=[r['episode_key'] for r in members],
            status='planned',native_admission_validated=False,capacity_reserved=False))
        for slot,row in enumerate(members):
            plan['episodes'].append(dict(row,campaign_id=campaign_id,pool_id=pool_id,logical_gpu_index=gpu,room_slot=slot,
                initial_attempt=1,attempt_status='not_started',runtime_validation_required=True,suite='videoicl-realworld50',epoch=campaign_id,
                expected_identity_source='native_controller_creation_result'))
    for gpu in range(len(slots)):
        plan['gpus'].append(dict(logical_gpu_index=gpu,planned_episodes=sum(r['logical_gpu_index']==gpu for r in plan['episodes']),configured_pool_count=frozen_bindings[gpu]['expected_pool_count'],native_live_pools=0,allocation_reserved=False))
    plan['statistics'] = dict(planned_episodes=len(rows),logical_gpu_count=len(slots),configured_pool_count=len(buckets),
        planned_nonempty_pools=len(buckets),planned_occupied_room_count=len(rows),input_conditions={'sim':len(rows)},
        planned_rooms_per_pool_histogram=dict(Counter(str(len(b)) for b in buckets)),native_live_episodes=0,
        native_terminal_verified_episodes=0,actual_model_requests=0,resource_validation_status='unverified')
    validate_frozen_panel(plan)
    return plan
