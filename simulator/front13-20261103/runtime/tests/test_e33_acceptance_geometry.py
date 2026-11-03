"""Offline E33 geometry controls using the real pinned source meshes."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from videoicl_isaaclab.e33_source_geometry import augment_e33_bindings
from videoicl_isaaclab.realworld_native_evidence import NativeTaskEvaluator
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.source_cavity_walls import SourceCavityWalls

ROOT=Path(__file__).resolve().parents[1]
BASE=json.loads((ROOT/'configs/realworld_full50_bindings.json').read_text())

def fixture(tmp_path, variant='C'):
    bindings=augment_e33_bindings(BASE,ROOT)
    path=tmp_path/'candidate.json';path.write_text(json.dumps(bindings))
    spec=load('E33',variant,4201,path,verify_files=False)
    return NativeTaskEvaluator(spec)

def state(pos, mat=None, grasp=(False,False)):
    return dict(pos=np.asarray(pos,float),mat=np.eye(3) if mat is None else mat,grasp=grasp)

def place(ev, offset=(0,0,.04), rotation=None, contacts=True, grasp=(False,False)):
    rot=np.eye(3) if rotation is None else rotation
    origin=np.array([.4,-.1,1.]); ev.state={'bin':state(origin,rot),'fanta':state(origin+rot@offset,rot,grasp)}
    ev.contacts={frozenset(('bin','fanta'))} if contacts else set()
    return ev.container_members('bin',['fanta'])

def test_upgrade_changes_only_acceptance_metadata():
    original=deepcopy(BASE);upgraded=augment_e33_bindings(BASE,ROOT)
    assert BASE==original
    for obj in upgraded['tasks']['E33']['objects'].values():obj.pop('source_containment_hull',None)
    for variant in upgraded['tasks']['E33']['variants'].values():
        variant['semantic'].pop('source_acceptance_geometry')
        variant['semantic']['containers']['bin'].pop('source_sidewall_triangles')
    assert upgraded==BASE

def test_real_bottle_inside_rotated_bin_not_double_world_aabb(tmp_path):
    ev=fixture(tmp_path);rot=Rotation.from_euler('z',45,degrees=True).as_matrix()
    assert place(ev,rotation=rot)==(['fanta'],['fanta'])
    center,half=ev.bounds('fanta');local=rot.T@(center-ev.state['bin']['pos']);radius=np.abs(rot.T)@half
    entry=ev.semantic['containers']['bin']
    assert not (np.all(local-radius>=np.asarray(entry['lower'])-.003) and np.all(local+radius<=np.asarray(entry['upper'])+.003))

def test_original_curved_sidewall_accepts_actual_mesh_not_box(tmp_path):
    ev=fixture(tmp_path);assert place(ev,(.08,0,.04))==(['fanta'],['fanta'])
    points=np.asarray(ev.objects['fanta']['source_containment_hull']['vertices_local'])+[.08,0,.04]
    assert points[:,0].max()>.103  # Old rectangular envelope wrongly rejects.

@pytest.mark.parametrize('offset',[(.16,0,.04),(-.16,0,.04),(0,.08,.04),(0,-.08,.04),(0,0,.15),(0,0,-.1)])
def test_outside_wall_floor_or_rim_rejected(tmp_path,offset):
    assert place(fixture(tmp_path),offset)==([],[])

def test_inside_without_contact_not_supported(tmp_path):
    assert place(fixture(tmp_path),contacts=False)==(['fanta'],[])

def test_grasped_bottle_not_disposed(tmp_path):
    assert place(fixture(tmp_path),grasp=(False,True))==([],[])

@pytest.mark.parametrize('field,value',[('size',[.1,.1,.1]),('source_rotation',[1,0,0,0]),('sha256','0'*64)])
def test_mismatched_source_rejected(field,value):
    base=deepcopy(BASE);obj=base['tasks']['E33']['objects']['fanta']
    (obj if field=='size' else obj['source_asset'])[field]=value
    with pytest.raises(ValueError,match='mismatch'):augment_e33_bindings(base,ROOT)

def test_versioned_geometry_cannot_silently_drop_back_to_aabb(tmp_path):
    ev=fixture(tmp_path);spec=deepcopy(ev.spec)
    next(o for o in spec['objects'] if o['id']=='fanta').pop('source_containment_hull')
    with pytest.raises(ValueError):NativeTaskEvaluator(spec)

def test_every_original_collision_vertex_matches_hull_envelope_and_wall():
    source=ROOT.parent/'deployment/real-text300-20261030/asset_roots/VIC_FULL50_RIGID_ASSETS'
    spec=importlib.util.spec_from_file_location('e33_export',ROOT/'scripts/build_e33_acceptance_geometry.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    task=augment_e33_bindings(BASE,ROOT)['tasks']['E33'];entry=task['variants']['C']['semantic']['containers']['bin']
    walls=SourceCavityWalls(entry['source_sidewall_triangles'],task['objects']['bin'])
    for name in ('sprite','water','coca_cola','pepsi','fanta'):
        points,_=module.extract(name,task['objects'][name],source)
        hull=np.asarray(task['objects'][name]['source_containment_hull']['vertices_local'])
        for angles in [(0,0,0),(10,20,30),(40,50,60)]:
            r=Rotation.from_euler('xyz',angles,degrees=True).as_matrix()
            assert np.allclose((points@r.T).min(0),(hull@r.T).min(0),atol=1e-12)
            assert np.allclose((points@r.T).max(0),(hull@r.T).max(0),atol=1e-12)
        if name=='fanta':
            assert walls.contains(points+[.08,0,.04],entry['lower'],entry['upper'])
            assert not walls.contains(points+[.16,0,.04],entry['lower'],entry['upper'])

def test_compiler_default_includes_both_geometry_fixes_and_preserves_other48(tmp_path):
    import os,subprocess,sys
    out=tmp_path/'candidate.json'
    subprocess.run([sys.executable,str(ROOT/'scripts/build_inference_generalization.py'),
        '--g2-profile',str(ROOT/'configs/inference-generalization-ur5-wsg-v1.json'),
        '--out',str(out)],check=True,env=dict(os.environ,PYTHONPATH=str(ROOT)),capture_output=True)
    candidate=json.loads(out.read_text())
    legacy=json.loads((ROOT/'inference-generalization-v1/inference-bindings.json').read_text())
    assert {t for t in candidate['tasks'] if candidate['tasks'][t]!=legacy['tasks'][t]}=={'E08','E33'}
    assert candidate['acceptance_geometry_revision']=='source-geometry-v2-E08-E33'
    assert candidate['tasks']['E08']['objects']['right_shoe']['containment_points_local']
    for variant in 'ABC':
        assert candidate['tasks']['E33']['variants'][variant]['semantic']['containers']['bin']['source_sidewall_triangles']
        NativeTaskEvaluator(load('E33',variant,4201,out,verify_files=False))
    for task in candidate['tasks']:
        for variant in 'ABC':
            upgraded=load(task,variant,4201,out,verify_files=False)
            original=load(task,variant,4201,ROOT/'inference-generalization-v1/inference-bindings.json',verify_files=False)
            assert upgraded['goals']==original['goals']
            assert upgraded['instruction']==original['instruction']

def test_compiler_protects_existing_canonical_binding(tmp_path):
    import os,subprocess,sys,hashlib
    target=ROOT/'inference-generalization-v1/inference-bindings.json'
    before=hashlib.sha256(target.read_bytes()).hexdigest()
    run=subprocess.run([sys.executable,str(ROOT/'scripts/build_inference_generalization.py'),
        '--g2-profile',str(ROOT/'configs/inference-generalization-ur5-wsg-v1.json'),
        '--out',str(target)],env=dict(os.environ,PYTHONPATH=str(ROOT)),capture_output=True,text=True)
    assert run.returncode!=0 and 'requires a new candidate output path' in run.stderr
    assert hashlib.sha256(target.read_bytes()).hexdigest()==before

def test_empty_points_cannot_pass_cavity():
    task=augment_e33_bindings(BASE,ROOT)['tasks']['E33'];entry=task['variants']['C']['semantic']['containers']['bin']
    walls=SourceCavityWalls(entry['source_sidewall_triangles'],task['objects']['bin'])
    assert not walls.contains(np.empty((0,3)),entry['lower'],entry['upper'])

def recorded_curved_floor(tmp_path):
    evidence=json.loads((ROOT/'tests/fixtures/e33_native_curved_floor.json').read_text())
    ev=fixture(tmp_path,'A')
    assert ev.objects['sprite']['source_asset']['sha256']==evidence['source_asset_sha256']
    ev.objects['sprite']['source_containment_hull']['vertices_local']=(
        np.asarray(ev.objects['sprite']['source_containment_hull']['vertices_local'])*evidence['instance_scale']).tolist()
    ev.state={k:state(v['pos'],np.asarray(v['mat']),v['grasp'])for k,v in evidence['state'].items()}
    ev.contacts={frozenset(pair)for pair in evidence['contacts']}
    return ev

def test_recorded_bottle_above_local_curved_floor_passes(tmp_path):
    ev=recorded_curved_floor(tmp_path)
    bottle=ev.state['sprite'];bin=ev.state['bin']
    points=(np.asarray(ev.objects['sprite']['source_containment_hull']['vertices_local'])@bottle['mat'].T+bottle['pos']-bin['pos'])@bin['mat']
    entry=ev.semantic['containers']['bin']
    assert np.count_nonzero(points[:,2]<entry['lower'][2]-.003)==72
    assert ev.container_members('bin',['sprite'])==(['sprite'],['sprite'])

@pytest.mark.parametrize('shift',[(0,0,-.02),(0,0,-.10),(.20,0,0),(0,.10,0),(0,0,.30)])
def test_recorded_bottle_below_inner_floor_or_outside_still_rejected(tmp_path,shift):
    ev=recorded_curved_floor(tmp_path)
    ev.state['sprite']['pos']+=ev.state['bin']['mat']@np.asarray(shift)
    assert ev.container_members('bin',['sprite'])==([],[])

def test_curved_floor_does_not_invent_support_or_release(tmp_path):
    ev=recorded_curved_floor(tmp_path);ev.contacts=set()
    assert ev.container_members('bin',['sprite'])==(['sprite'],[])
    ev.state['sprite']['grasp']=(True,False)
    assert ev.container_members('bin',['sprite'])==([],[])

def test_compiler_allows_only_the_known_e08_geometry_marker():
    spec=importlib.util.spec_from_file_location('geometry_compiler',ROOT/'scripts/build_inference_generalization.py')
    compiler=importlib.util.module_from_spec(spec);spec.loader.exec_module(compiler)
    base=json.loads((ROOT/'configs/initial-admission-e13-e25-20261030/e13-hframe-v2-bindings.candidate.json').read_text())
    catalog=json.loads((ROOT/'inference-generalization-v1/catalog.private.json').read_text())
    g1=json.loads((ROOT/'inference-generalization-v1/g1-bindings-patch.json').read_text())
    g2=json.loads((ROOT/'inference-generalization-v1/g2-bindings-patch.json').read_text())
    for v in g1['tasks']['E08']['variants'].values():v['semantic']['source_acceptance_geometry']='E08-source-geometry-v1'
    result,_=compiler.compile_bindings(base,catalog,[g1,g2],g2_profile='pinned',g2_profile_sha256='1'*64)
    assert result['tasks']['E08']['variants']['A']['semantic']['source_acceptance_geometry']=='E08-source-geometry-v1'
    g1['tasks']['E08']['variants']['A']['semantic']['source_acceptance_geometry']='unknown'
    with pytest.raises(ValueError,match='silently change ABC'):
        compiler.compile_bindings(base,catalog,[g1,g2],g2_profile='pinned',g2_profile_sha256='1'*64)


def recorded_curved_y_wall(tmp_path):
    evidence=json.loads((ROOT/'tests/fixtures/e33_native_curved_y_wall.json').read_text())
    ev=fixture(tmp_path,'B')
    assert ev.objects['coca_cola']['source_asset']['sha256']==evidence['source_asset_sha256']
    ev.objects['coca_cola']['source_containment_hull']['vertices_local']=(
        np.asarray(ev.objects['coca_cola']['source_containment_hull']['vertices_local'])*evidence['instance_scale']).tolist()
    ev.state={k:state(v['pos'],np.asarray(v['mat']),v['grasp']) for k,v in evidence['state'].items()}
    ev.contacts={frozenset(pair) for pair in evidence['contacts']}
    return ev


def test_recorded_cola_within_actual_y_wall_passes_same_tolerance(tmp_path):
    ev=recorded_curved_y_wall(tmp_path);bottle=ev.state['coca_cola'];bin=ev.state['bin']
    points=(np.asarray(ev.objects['coca_cola']['source_containment_hull']['vertices_local'])@bottle['mat'].T+bottle['pos']-bin['pos'])@bin['mat']
    entry=ev.semantic['containers']['bin']
    assert np.count_nonzero(points[:,1]>entry['upper'][1]+.003)==13
    assert np.count_nonzero(points[:,2]<entry['lower'][2]-.003)==26
    assert np.isclose(points[:,1].max(),.04767042314451664,atol=1e-12)
    assert ev.container_members('bin',['coca_cola'])==(['coca_cola'],['coca_cola'])


@pytest.mark.parametrize('shift',[(0,.01,0),(0,.10,0),(0,-.15,0),(.20,0,0),(0,0,-.02),(0,0,.30)])
def test_recorded_cola_real_wall_floor_rim_crossing_rejected(tmp_path,shift):
    ev=recorded_curved_y_wall(tmp_path)
    ev.state['coca_cola']['pos']+=ev.state['bin']['mat']@np.asarray(shift)
    assert ev.container_members('bin',['coca_cola'])==([],[])


def test_curved_y_wall_does_not_invent_contact_or_release(tmp_path):
    ev=recorded_curved_y_wall(tmp_path);ev.contacts=set()
    assert ev.container_members('bin',['coca_cola'])==(['coca_cola'],[])
    ev.state['coca_cola']['grasp']=(False,True)
    assert ev.container_members('bin',['coca_cola'])==([],[])


@pytest.mark.parametrize('sign',[-1,1])
def test_y_wall_first_surface_not_outer_thickness_or_nearly_horizontal(tmp_path,sign):
    ev=fixture(tmp_path);entry=ev.semantic['containers']['bin'];walls=ev.source_cavity_walls['bin']
    # Intersections are already pinned at construction. Override only these
    # ray arrays to isolate nearest-surface selection, not native evidence.
    walls.y_a=np.array([[0,sign*.05,0],[0,sign*.08,0]],float)
    walls.y_u=np.array([[1,0,0],[1,0,0]],float)
    walls.y_v=np.array([[0,0,1],[0,0,1]],float)
    walls.y_det=np.ones(2);walls.normal_y=np.ones(2)
    assert walls.contains(np.array([[.01,sign*.052,.04]]),entry['lower'],entry['upper'])
    assert not walls.contains(np.array([[.01,sign*.075,.04]]),entry['lower'],entry['upper'])
    walls.normal_y[0]=.1
    assert not walls.contains(np.array([[.01,sign*.052,.04]]),entry['lower'],entry['upper'])
    # No sidewall crossing at this X/Z cannot be interpreted as open space.
    walls.y_a[:,0]=10
    assert not walls.contains(np.array([[.01,sign*.052,.04]]),entry['lower'],entry['upper'])
