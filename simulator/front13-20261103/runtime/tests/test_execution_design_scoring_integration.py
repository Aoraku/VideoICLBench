"""Real scene schemas, synthetic measured-state fixtures; NOT native validation."""
from pathlib import Path
from copy import deepcopy
import math
import numpy as np
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_scenes import build_execution_scene,TASKS
from videoicl_isaaclab.execution_design_evidence import ExecutionDesignEvaluator
BINDINGS=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json'


def correct_fixture(spec):
    d=spec['execution_design'];objects={o['id']:o for o in spec['objects']};state={};contacts=set()
    def put(n,p,yaw=0):
        c,s=math.cos(yaw),math.sin(yaw)
        state[n]=dict(pos=np.array(p,float),mat=np.array([[c,-s,0],[s,c,0],[0,0,1.]]),grasp=(False,False))
    def touch(a,b):contacts.add(frozenset((a,b)))
    def inside(n,actor,local):
        a=state[actor];o=objects[n]
        put(n,a['pos']+a['mat']@np.asarray(local));touch(n,actor)
    for n,o in objects.items():
        put(n,[*o['xy'],o.get('center_z',o['bottom']+o['size'][2])],o.get('yaw',0));touch(n,'table')
    z=next(z for z in spec['zones'] if z['id']==d['destination_zone']);delivery=d['delivery_actor']
    put(delivery,[*z['xy'],.8+objects[delivery]['size'][2]-objects[delivery].get('local_bounds_center',[0,0,0])[2]])
    for p in reversed(d['packages']):
        for i,n in enumerate(p['members']):
            y=(i-(len(p['members'])-1)/2)*.12
            inside(n,p['container'],[0,y,p['lower'][2]+objects[n]['size'][2]-objects[n].get('local_bounds_center',[0,0,0])[2]])
        if p.get('lid'):inside(p['lid'],p['container'],p['lid_local_center'])
    for i,r in enumerate(d['local_regions']):
        if spec['id']=='E09':members=d['unordered_expected_groups'][i]
        elif spec['id']=='E20':
            members=list(d['initial_preserved'][r['id']]);pool=[n for n in r['candidates']if n.startswith(r['required_color']+'_') and n not in members]
            members+=pool[:r['count']-len(members)]
        else:members=r['members']
        for j,n in enumerate(sorted(members)):
            mid=(np.asarray(r['lower'])+r['upper'])/2
            x=mid[0]+((j%2)-.5)*.044;y=mid[1]+((j//2)-.5)*.044
            inside(n,r['actor'],[x,y,r['lower'][2]+objects[n]['size'][2]])
    if d.get('local_order'):
        r=d['local_order']
        for i,n in enumerate(r['expected_order']):
            xy=[0,.12-i*.12]
            tops=[shape.get('pos',[0,0,0])[2]+shape['size'][2] for shape in objects[r['actor']]['collision_shapes']
                  if shape.get('type')=='box' and all(abs(xy[k]-shape.get('pos',[0,0,0])[k])<=shape['size'][k] for k in (0,1))]
            inside(n,r['actor'],[*xy,max(tops)+objects[n]['size'][2]])
            yaw=r['expected_yaws'][n];pos=state[n]['pos'].copy();put(n,pos,yaw)
    for r in d['cleanup_regions']:
        stack_height=r['lower'][2]
        below=r['actor']
        for i,n in enumerate(r['members']):
            mid=(np.asarray(r['lower'])+r['upper'])/2
            if r['actor']:
                # Stack the real packing box and raised-tab lid; offsets of
                # their full collision bounds are not object-origin offsets.
                inside(n,r['actor'],[mid[0],mid[1],stack_height+objects[n]['size'][2]-objects[n].get('local_bounds_center',[0,0,0])[2]])
                if below!=r['actor']:
                    contacts.discard(frozenset((n,r['actor'])));touch(n,below)
                stack_height+=2*objects[n]['size'][2];below=n
            else:
                support=r.get('support',d.get('initial_storage',{}).get(n,'table'))
                surface=.8
                if support.startswith('fixture'):
                    f=spec['fixtures'][int(support[7:])];surface=f['z']+f['size'][2]
                    touch(n,support)
                put(n,[mid[0]+i*.002,mid[1],surface+objects[n]['size'][2]-objects[n].get('local_bounds_center',[0,0,0])[2]])
    if spec['id']=='E20':
        used={n for r in d['local_regions']for n in r['candidates'] if any(n in c and r['actor'] in c for c in contacts)}
        bounds=d['unused_supply_bounds'];mid=(np.asarray(bounds['lower'])+bounds['upper'])/2
        support=d.get('unused_supply_support','table');surface=.8
        if support.startswith('fixture'):
            f=spec['fixtures'][int(support[7:])];surface=f['z']+f['size'][2]
        for i,n in enumerate(set(d['target_members'])-used):
            put(n,[mid[0]+i*.001,mid[1],surface+objects[n]['size'][2]])
            touch(n,support)
    # Remove obsolete table edges for every carried nested object.
    for n in objects:
        if abs(state[n]['pos'][2]+(state[n]['mat']@np.asarray(objects[n].get('local_bounds_center',[0,0,0])))[2]-objects[n]['size'][2]-.8)>.015:contacts.discard(frozenset((n,'table')))
    return state,contacts


def initial_fixture(spec):
    state={};contacts=set();d=spec['execution_design']
    from scipy.spatial.transform import Rotation
    for o in spec['objects']:
        if 'quaternion' in o:
            q=o['quaternion'];mat=Rotation.from_quat([*q[1:],q[0]]).as_matrix()
        else:mat=Rotation.from_euler('z',o.get('yaw',0)).as_matrix()
        state[o['id']]=dict(pos=np.array([*o['xy'],o.get('center_z',o['bottom']+o['size'][2])]),mat=mat,grasp=(False,False))
        contacts.add(frozenset((o['id'],'table')))
    # Synthetic contacts cover the authored initial rack/packing surfaces.
    for n,v in state.items():
        for i,f in enumerate(spec.get('fixtures',[])):
            contacts.add(frozenset((n,'fixture'+str(i))))
        if spec['id']=='E17' and (n in d['target_members'] or n=='packing_lid'):
            contacts.add(frozenset((n,'packing_box')))
        if spec['id']=='E39':
            if n in d['local_order']['pieces']:contacts.add(frozenset((n,'work_tray')))
            if n in d['local_order']['reference_pieces']:contacts.add(frozenset((n,'reference_tray')))
    for region,names in d.get('initial_preserved',{}).items():
        r=next(r for r in d['local_regions'] if r['id']==region)
        for n in names:
            contacts.discard(frozenset((n,'table')));contacts.add(frozenset((n,r['actor'])))
    return state,contacts


def evaluate(spec,state,contacts):
    e=ExecutionDesignEvaluator(spec);initial,initial_contacts=initial_fixture(spec)
    for _ in range(6):e.update(initial,initial_contacts,.1)
    e.seal_initial()
    for _ in range(6):e.update(state,contacts,.1)
    return e,e.result()


@pytest.mark.parametrize('task',TASKS)
@pytest.mark.parametrize('variant',list('ABC'))
@pytest.mark.parametrize('seed',[1,2,3])
@pytest.mark.parametrize('condition',['I','E'])
def test_scene_predicates_correct_and_counterexamples(task,variant,seed,condition):
    spec=build_execution_scene(load(task,variant,seed,BINDINGS,verify_files=False),condition=condition,seed=seed)
    state,contacts=correct_fixture(spec);e,r=evaluate(spec,state,contacts)
    assert r['process_score']==100,(task,r['observation'],r['errors'],e.grounded())
    assert not r['task_score_native_physics_verified']
    # Wrong destination while preserving cargo-relative state.
    changed=deepcopy(spec);changed['execution_design']['destination_zone']='delivery_'+str(1-seed%2)
    assert not evaluate(changed,state,contacts)[1]['strict_success']
    # Same physical state evaluated under the next distinct private ABC rule.
    next_variant='ABC'[('ABC'.index(variant)+1)%3]
    other=build_execution_scene(load(task,next_variant,seed,BINDINGS,verify_files=False),condition=condition,seed=seed)
    assert not evaluate(other,state,contacts)[1]['strict_success']
    # Incorrect rule result / missing member and unreleased target.
    target=spec['execution_design']['target_members'][0]
    wrong=deepcopy(state);wrong[target]['pos'][0]+=1
    assert not evaluate(spec,wrong,contacts)[1]['strict_success']
    held=deepcopy(state);held[target]['grasp']=(True,False)
    for _ in range(6):e.update(held,contacts,.1)
    assert not e.result()['strict_success']


def test_real_scene_inner_box_lid_must_fit_shipping_crate():
    # Actual E09 authored geometry; measured poses/contacts here are synthetic.
    spec=build_execution_scene(load('E09','A',1,BINDINGS,verify_files=False))
    state,contacts=correct_fixture(spec)
    e,result=evaluate(spec,state,contacts)
    assert result['strict_success']
    outer=next(p for p in e.design['packages'] if p['container']=='shipping_crate')
    inner=next(p for p in e.design['packages'] if p['container']=='group_box0')
    names=[inner['container'],inner['lid'],*e.design['unordered_expected_groups'][0]]
    # Move an otherwise closed, loaded inner box just inside the outer rim.
    offset=outer['upper'][0]-e.objects[inner['container']]['size'][0]
    changed=deepcopy(state)
    for n in names:changed[n]['pos'][0]+=offset
    e,ok=evaluate(spec,changed,contacts)
    assert ok['strict_success'] and e.package_correct(outer)
    # A 7mm cap offset is locally within the 8mm closure tolerance but extends
    # outside the crate by more than the outer 3mm containment tolerance.
    changed[inner['lid']]['pos'][0]+=.007
    for _ in range(6):e.update(changed,contacts,.1)
    assert e.package_correct(inner)
    assert e.contained(inner['container'],dict(outer,actor=outer['container']))
    assert not e.contained(inner['lid'],dict(outer,actor=outer['container']))
    assert not e.package_correct(outer) and not e.result()['strict_success']


def test_grasp_tab_counts_toward_complete_delivery_footprint():
    spec=build_execution_scene(load('E01','A',1,BINDINGS,verify_files=False))
    state,contacts=correct_fixture(spec);e,result=evaluate(spec,state,contacts)
    assert result['strict_success']
    box=e.objects['meal_box']
    # The physical tab extends the original 128mm half-width to -134mm.
    low=np.asarray(box['local_bounds_center'])-np.asarray(box['size'])
    high=np.asarray(box['local_bounds_center'])+np.asarray(box['size'])
    for shape in box['collision_shapes']:
        if shape['type']=='box' and shape.get('quat',[1,0,0,0])==[1,0,0,0]:
            assert np.all(np.asarray(shape['pos'])-shape['size']>=low-1e-9)
            assert np.all(np.asarray(shape['pos'])+shape['size']<=high+1e-9)
    e.zones[e.design['destination_zone']]['half_size'][0]=.128
    assert not e.destination_correct()
    # Omitting the same-body tab would incorrectly accept this boundary case.
    box['size'][0]=.128;box['local_bounds_center']=[0,0,0]
    assert e.destination_correct()


def test_e09_source_piece_rails_preserve_geometry_and_leave_finger_clearance():
    base=load('E09','A',4201,BINDINGS,verify_files=False)
    spec=build_execution_scene(base,seed=4201)
    original={o['id']:o for o in base['objects']};objects={o['id']:o for o in spec['objects']}
    d=spec['execution_design'];supports=set()
    for name in d['target_members']:
        o=objects[name];fixture=d['initial_storage'][name];supports.add(fixture)
        rail=spec['fixtures'][int(fixture[7:])]
        assert rail['size']==[.003,.024,.014]
        assert rail['z']-rail['size'][2]==pytest.approx(.808)
        assert o['bottom']==pytest.approx(rail['z']+rail['size'][2])
        assert o['source_asset']==original[name]['source_asset'] and o['size']==original[name]['size']
        assert o['size'][0]-rail['size'][0]>.007
    assert len(supports)==9


@pytest.mark.parametrize('task',TASKS)
@pytest.mark.parametrize('revision',['embodied50-execution-v2-20261102','embodied50-execution-v3-20261102'])
def test_actual_workflow_scene_preserves_pinned_revision(task,revision):
    spec=build_execution_scene(load(task,'A',4201,BINDINGS,verify_files=False),condition='I',seed=4201,revision=revision)
    state,contacts=correct_fixture(spec);e,result=evaluate(spec,state,contacts)
    assert result['process_score']==100
    assert result['execution_design_revision']==revision
    assert result['execution_design_source_sha256']==spec['execution_design']['source_sha256']


def test_e20_unused_chip_requires_one_of_declared_real_supply_supports():
    spec=build_execution_scene(load('E20','A',4201,BINDINGS,verify_files=False),condition='I',seed=4201)
    state,contacts=correct_fixture(spec);baseline,result=evaluate(spec,state,contacts)
    assert result['process_score']==100
    used=set().union(*baseline.observation['region_members'].values())
    spare=next(n for n in spec['execution_design']['target_members']if n not in used)
    objects={o['id']:o for o in spec['objects']};d=spec['execution_design']
    support='fixture'+str(len(spec['fixtures']));pos=state[spare]['pos'].copy()
    top=float(pos[2]-objects[spare]['size'][2]+.03)
    spec['fixtures'].append(dict(type='box',xy=pos[:2].tolist(),z=top-.005,size=[.03,.03,.005]))
    d['unused_supply_supports']=[d['unused_supply_support'],support]
    state[spare]['pos'][2]+= .03
    contacts={c for c in contacts if spare not in c};contacts.add(frozenset((spare,support)))
    e,result=evaluate(spec,state,contacts);assert result['process_score']==100
    # Geometrically in the supply region and stable is insufficient if its
    # actual support is not a declared storage surface.
    spec['execution_design']['unused_supply_supports']=[d['unused_supply_support']]
    e,result=evaluate(spec,state,contacts)
    assert not result['strict_success'] and not e.observation['cleanup_valid']


def test_e39_cradle_support_rejects_side_contact_floating_and_off_center():
    spec=build_execution_scene(load('E39','A',4201,BINDINGS,verify_files=False),condition='I',seed=4201)
    state,contacts=correct_fixture(spec);e,result=evaluate(spec,state,contacts)
    assert result['strict_success']
    name=spec['execution_design']['local_order']['pieces'][0]
    # Keep the same tray contact bit; this must not turn its empty enclosing
    # box into a solid support platform over the entire tray.
    for delta in ([.025,0,0],[.04,0,0],[0,0,.025]):
        bad=deepcopy(state);bad[name]['pos']+=np.asarray(delta)
        e,result=evaluate(spec,bad,contacts)
        assert name not in e.grounded('work_tray')
        assert not result['strict_success']


@pytest.mark.parametrize('variant',list('ABC'))
def test_e39_initial_pose_contract_includes_roll_pitch_and_b_xyz(variant):
    from scipy.spatial.transform import Rotation
    spec=build_execution_scene(load('E39',variant,4201,BINDINGS,verify_files=False),condition='I',seed=4201)
    state,contacts=correct_fixture(spec);e,result=evaluate(spec,state,contacts)
    assert result['strict_success']
    rule=e.initial_order_rule;name=rule['pieces'][0]
    assert name in rule['expected_rotations']
    if variant=='B':assert len(rule['preserved_positions'][name])==3
    # Isolate the orientation contract from support rejection: the same yaw
    # with a 20-degree roll must fail even when all support checks are true.
    e.state[name]['mat']=e.state[name]['mat']@Rotation.from_euler('x',20,degrees=True).as_matrix()
    e.grounded=lambda root=None:set(e.objects)
    e.contained=lambda n,r:True
    assert not e.order_correct(rule)
    if variant=='B':
        e.state[name]['mat']=e.state[rule['actor']]['mat']@np.asarray(rule['expected_rotations'][name])
        e.state[name]['pos']+=e.state[rule['actor']]['mat']@np.array([0,0,.03])
        assert not e.order_correct(rule)
