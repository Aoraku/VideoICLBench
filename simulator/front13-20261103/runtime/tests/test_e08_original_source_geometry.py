"""Original rigid shoe regression at actual native721, with real-vertex negatives."""
from copy import deepcopy
import json
import numpy as np
import pytest
from videoicl_isaaclab.realworld_structural_evidence import StructuralTaskEvaluator
from videoicl_isaaclab.e08_original_source_geometry import bind_original_e08_evaluator_geometry


def spec():
    shas=['fdd7d78b574ad7bd52485d063fbb48621a02651cd174235cfd6bd9f7b2e40b32','d47101e06a14ea63e22b76f3444fce6bd4faf4e1a33ed3c38c0cd603c339e3b2']
    sizes=[[.13,.04422009824739785,.051902870300350894],[.13,.04553283416401324,.051902871849475]]
    shoes=[dict(id=n,size=size,source_asset=dict(sha256=sha,source_rotation=[.5,.5,.5,.5]))for n,size,sha in zip(('left_shoe','right_shoe'),sizes,shas)]
    return dict(id='E08',variant='A',objects=shoes+[dict(id='box',size=[.18,.105,.055])],semantic=dict(groups=dict(shoes=['left_shoe','right_shoe']),containers=dict(box=dict(ref=dict(actor='box'),shape='box',axis=2,lower=[-.171,-.096,-.05264],upper=[.171,.096,.055])),require_box_floor_or_other_shoe_contact=True))


def actual721():
    from scipy.spatial.transform import Rotation
    s=spec();before=json.dumps(s,sort_keys=True);e=StructuralTaskEvaluator(s)
    assert json.dumps(s,sort_keys=True)==before
    q=[.1264554928768775,-.13354018762229436,.7957107222859833,-.5770792606307972]
    r=Rotation.from_quat([*q[1:],q[0]]).as_matrix()
    e.state=dict(left_shoe=dict(pos=np.array([-.0014524259604514,-.15902338922023776,.8432044959068299]),mat=r,grasp=[False,False]),right_shoe=dict(pos=np.array([0.,.18,.85156]),mat=np.eye(3),grasp=[False,False]),box=dict(pos=np.array([0.,-.16,.855]),mat=np.eye(3),grasp=[False,False]))
    # Test force sign only; actual measured support is separately in native v12.
    pair=frozenset(('left_shoe','box'));e.contacts={pair};e.forces={pair:1.}
    return e


def test_actual721_real_vertices_fit_while_empty_bbox_corners_do_not():
    e=actual721();assert e.contained('box',['left_shoe'])==(['left_shoe'],['left_shoe'])
    c=e.semantic['containers']['box'];a=e.corners('left_shoe',c['ref']);lo=np.array(c['lower'])-[.002,.002,.003];hi=np.array(c['upper'])+[.002,.002,.003]
    assert np.any(a.min(0)<lo)or np.any(a.max(0)>hi)
    assert len(e.objects['left_shoe']['containment_points_local'])==3729


@pytest.mark.parametrize('axis',[0,1,2])
@pytest.mark.parametrize('upper',[False,True])
def test_one_actual_vertex_beyond_original_native_tolerance_is_rejected(axis,upper):
    e=actual721();n='left_shoe';c=e.semantic['containers']['box'];p=np.asarray(e.objects[n]['containment_points_local'])@e.state[n]['mat'].T+e.state[n]['pos']-e.state['box']['pos'];tol=.003 if axis==2 else .002
    bound=c['upper'][axis]+tol if upper else c['lower'][axis]-tol
    face=p[:,axis].max()if upper else p[:,axis].min();e.state[n]['pos'][axis]+=bound-face+(1e-6 if upper else-1e-6)
    assert e.contained('box',[n])==([],[])


def test_source_geometry_never_supplies_physical_support_or_release():
    e=actual721();e.forces={};assert e.contained('box',['left_shoe'])==(['left_shoe'],[])
    e=actual721();e.state['left_shoe']['grasp']=[True,True];assert e.contained('box',['left_shoe'])==(['left_shoe'],[])


def test_other_task_and_generated_source_inputs_remain_unchanged():
    s=spec();s['id']='E24';before=deepcopy(s);bind_original_e08_evaluator_geometry(s);assert s==before
    s=spec()
    for o in s['objects'][:2]:o['source_asset']['sha256']='0'*64
    before=deepcopy(s);bind_original_e08_evaluator_geometry(s);assert s==before


@pytest.mark.parametrize('shoe',['left_shoe','right_shoe'])
def test_cache_equals_every_enabled_original_source_collision_vertex(shoe):
    import ast,hashlib,re
    from pathlib import Path
    from scipy.spatial.transform import Rotation
    s=spec();obj=next(o for o in s['objects']if o['id']==shoe)
    path=Path(__file__).resolve().parents[2]/'deployment/real-text300-20261030/asset_roots/VIC_FULL50_RIGID_ASSETS'/('formal_shoe_left.usda'if shoe=='left_shoe'else'formal_shoe_right.usda')
    raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==obj['source_asset']['sha256']
    visual,collision=raw.decode().split('"Collisions"',1);q=obj['source_asset']['source_rotation'];r=Rotation.from_quat([*q[1:],q[0]]).as_matrix()
    def arrays(text):return[np.asarray(ast.literal_eval(a),float)@r.T for a in re.findall(r'point3f\[\] points = (\[[^\n]+\])',text)]
    vv=np.concatenate(arrays(visual));center=(vv.min(0)+vv.max(0))/2;parts=arrays(collision);assert len(parts)==22
    actual=(np.concatenate(parts)-center)*(2*np.asarray(obj['size'])/np.ptp(vv,axis=0))
    bind_original_e08_evaluator_geometry(s);bound=next(o for o in s['objects']if o['id']==shoe)
    np.testing.assert_allclose(bound['containment_points_local'],actual,atol=1e-12,rtol=0)
