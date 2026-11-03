"""Measured route geometry is a unit fixture, never native success evidence."""
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e24_reference import measured_clearance,MeasuredE24Author
from videoicl_isaaclab.realworld_structural_expert import StructuralAuthor
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def policy():
    state={'cup':dict(pos=np.array([0.,0.,.85]),mat=np.eye(3)),
           'box':dict(pos=np.array([.2,0.,.82]),mat=np.eye(3))}
    objects={'cup':dict(size=[.04,.04,.05]),'box':dict(size=[.1,.1,.08],local_bounds_center=[0,0,.04])}
    p=SimpleNamespace(snapshot=lambda:(state,set()),objects=objects,spec={'fixtures':[]},tip=lambda side:np.array([0.,0.,1.]),
        a=SimpleNamespace(finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=.97)))
    p.point=lambda ref:state[ref['actor']]['pos']+state[ref['actor']]['mat']@np.asarray(ref['local'])
    return p,state


def test_actual_box_origin_and_finger_depth_set_empty_clearance():
    p,_=policy();d=measured_clearance(p,'right')
    assert d['obstacle_top_z_m']==pytest.approx(.94)
    assert d['point_to_lowest_m']==pytest.approx(.03)
    assert d['clearance_z_m']==pytest.approx(1.01)
    assert d['native_reachability_verified']is False


def test_loaded_point_depth_uses_actual_carried_bottom_and_does_not_cap_obstacles():
    p,state=policy();state['cup']['pos'][2]=1.04
    d=measured_clearance(p,'right',carried='cup',local_point=[0,0,-.05])
    assert d['point_to_lowest_m']==pytest.approx(.02)
    assert d['clearance_z_m']==pytest.approx(1.0)
    assert 'cup'not in d['obstacle_tops_task_m']
    state['box']['pos'][2]+=1
    assert measured_clearance(p,'right',carried='cup',local_point=[0,0,-.05])['clearance_z_m']==pytest.approx(2.)


def test_unmeasured_finger_and_unreviewed_tilt_cannot_silently_use_low_height():
    p,state=policy();p.a.finger_geometry=lambda side:dict(source='guess',lowest_z_task_m=.97)
    with pytest.raises(RuntimeError,match='Actual E24'):measured_clearance(p,'right')
    p,state=policy();state['cup']['mat']=np.diag([1,-1,-1])
    with pytest.raises(RuntimeError,match='upright'):measured_clearance(p,'right',carried='cup',local_point=[0,0,0])


def test_measured_scope_keeps_original_physical_acquisition_and_restores_clearance(monkeypatch):
    p,state=policy()
    p.clearance=1.15;p.operations=[]
    seen=[]
    def physical(self,ref,side):seen.append((ref,side,self.clearance));raise RuntimeError('physical failure')
    monkeypatch.setattr(StructuralAuthor,'acquire',physical)
    obj=MeasuredE24Author.__new__(MeasuredE24Author);obj.__dict__.update(p.__dict__)
    with pytest.raises(RuntimeError,match='physical failure'):obj.acquire({'actor':'cup'},'right')
    assert seen==[({'actor':'cup'},'right',pytest.approx(1.01))]
    assert obj.clearance==1.15


def test_outer_wall_grasp_is_inside_real_collision_hull_not_between_neighbor_cups(tmp_path):
    import ast,re,hashlib,json
    from pathlib import Path
    from scipy.spatial import ConvexHull
    from videoicl_isaaclab.execution_design_e24_reference import outside_cup_grasps,OUTER_CUP_GRASP,CUP_SHA256
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    from videoicl_isaaclab.realworld_scenes import load
    rt=Path(__file__).parents[1]
    source=rt.parents[0]/'deployment/real-text300-20261030/asset_roots/VIC_MECHANISM_ASSETS/hollow_cup.usda'
    raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==CUP_SHA256
    block=raw.decode().split('def Mesh "part_25"')[1].split('def Mesh "part_26"')[0]
    points=np.asarray(ast.literal_eval(re.search(r'point3f\[\] points = (\[[^\n]+\])',block)[1]))
    # Reviewed authored SourceFrame: scale .088 then quaternion(√.5,√.5,0,0).
    q=points@np.array([[1,0,0],[0,0,1],[0,-1,0]])*.088;q[:,2]-=.044
    hull=ConvexHull(q);point=np.asarray(OUTER_CUP_GRASP)
    assert np.max(hull.equations[:,:3]@point+hull.equations[:,3])<1e-8
    spec=load('E24','A',4201,rt/'configs/realworld_full50_bindings.json',verify_files=False)
    spec['execution_design']={'revision':'embodied50-execution-v3-20261102'}
    original=json.dumps(spec,sort_keys=True)
    result=outside_cup_grasps(spec,spec['semantic']['structural_grasps'])
    assert json.dumps(spec,sort_keys=True)==original
    for name in ('red','green','blue'):
        assert result[name]['local']==OUTER_CUP_GRASP and result[name]['jaw_axis_local']==[0,1,0]
    assert result['lid']==spec['semantic']['structural_grasps']['lid']
    spec['objects'][-1]['source_asset']['sha256']='changed'
    with pytest.raises(ToolExecutionError,match='actual cup mesh'):outside_cup_grasps(spec,spec['semantic']['structural_grasps'])


@pytest.mark.parametrize('variant',list('ABC'))
@pytest.mark.parametrize('control',['wrong_rule','wrong_destination','not_released'])
def test_e24_counterexample_interventions_preserve_scene_and_use_actual_action_methods(variant,control):
    from copy import deepcopy
    from videoicl_isaaclab.execution_design_e24_reference import NegativeE24Author
    p=NegativeE24Author.__new__(NegativeE24Author);p.index='ABC'.index(variant);p.control=control
    p.perturbation={};p.identity={n:n for n in ('red','green','blue')}
    p.s={'containers':{'box':{'ref':{'actor':'box'}}},
         'cups':{n:dict(axis_local=[0,0,1],bottom_local=[0,0,-.04])for n in p.identity},
         'lid_geometry':dict(ref={'actor':'lid'},box_ref={'actor':'box'},box_rim_center_local=[0,0,.08],closed_offset_m=.004,cover_center_local=[0,0,0])}
    p.geometry={'box_positions':[[0,.10,0],[0,0,0],[0,-.10,0]]}
    before=deepcopy(p.s);log=[];held=set()
    def pickup(n):held.add(n);log.append(('pickup',n));return {'actor':n},'right'
    def lower(n,*args,**kwargs):assert n in held;held.remove(n);log.append(('place-release',n))
    p.pickup=pickup;p.lower_place=lower;p.align_axis=lambda *args:None;p.stage=lambda *args:None
    p.body_point=lambda ref,point:np.asarray(point,float)+[0,0,.8]
    p.frame=lambda ref:(np.array([0,0,.8]),np.eye(3));p.wait=lambda n:log.append(('wait',n))
    def require(ref,side):assert ref['actor']in held;log.append(('measured-held',ref['actor']))
    p.require_held=require
    p.box_and_lid()
    expected=(['red','green','blue'],['green','blue','red'],['blue','red','green'])[p.index]
    attempted=expected.copy()
    if control=='wrong_rule':attempted[0],attempted[1]=attempted[1],attempted[0]
    assert [n for action,n in log if action=='pickup'][:3]==attempted
    assert p.s==before
    assert held==({'lid'}if control=='not_released'else set())
    if control=='wrong_destination':assert ('pickup','lid')not in log
    if control=='wrong_rule':assert ('place-release','lid')in log
    if control=='not_released':assert ('measured-held','lid')in log and ('place-release','lid')not in log


def insertion_policy():
    p=SimpleNamespace(s={'containers':{'box':{'ref':{'actor':'box'},'lower':[-.16,-.09,0],'upper':[.16,.09,.11]}},'cups':{'cup':{},'middle':{}}},operations=[])
    state={'box':dict(pos=np.array([0,0,.8]),mat=np.eye(3)),
           'cup':dict(pos=np.array([-.095,0,1.]),mat=np.eye(3)),
           'middle':dict(pos=np.array([0,0,.844]),mat=np.eye(3))}
    p.objects={'cup':{'size':[.041,.041,.044]},'middle':{'size':[.041,.041,.044]}}
    p.snapshot=lambda:(state,{frozenset(('middle','box'))})
    p.point=lambda ref:state[ref['actor']]['pos']+np.asarray(ref['local'])
    p.a=SimpleNamespace(finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',fingers=[dict(aabb_min_task_m=[-.169,-.015,.99],aabb_max_task_m=[-.120,.015,1.04])]))
    return p,state


def test_measured_finger_wall_interference_moves_cup_only_minimally_inward():
    from videoicl_isaaclab.execution_design_e24_reference import measured_box_insertion_target
    p,state=insertion_policy()
    result=measured_box_insertion_target(p,'cup','right',[0,0,-.044],[-.095,0,.8046])
    np.testing.assert_allclose(result,[-.084,0,.8046],atol=1e-12)
    assert p.operations[-1]['native_success_asserted']is False
    # The cup remains on the same side of the middle cup; scoring targets
    # and original state were not rewritten by this geometric proposal.
    assert result[0]<0 and state['cup']['pos'][0]==-.095


def test_measured_inward_correction_cannot_push_through_previous_cup():
    from videoicl_isaaclab.execution_design_e24_reference import measured_box_insertion_target
    p,state=insertion_policy();state['middle']['pos'][0]=-.01
    with pytest.raises(ToolExecutionError,match='neighboring cup'):
        measured_box_insertion_target(p,'cup','right',[0,0,-.044],[-.095,0,.8046])


def test_insertion_rejects_missing_native_finger_source_and_large_target_substitution():
    from videoicl_isaaclab.execution_design_e24_reference import measured_box_insertion_target
    p,state=insertion_policy();p.a.finger_geometry=lambda side:{'source':'guessed'}
    with pytest.raises(ToolExecutionError,match='finger mesh'):
        measured_box_insertion_target(p,'cup','right',[0,0,-.044],[-.095,0,.8046])
    p,state=insertion_policy()
    with pytest.raises(ToolExecutionError,match='20mm'):
        measured_box_insertion_target(p,'cup','right',[0,0,-.044],[-.14,0,.8046])


@pytest.mark.parametrize('index,order',[(0,['red','green','blue']),(1,['green','blue','red']),(2,['blue','red','green'])])
def test_third_cup_perpendicular_grasp_requires_prior_actual_box_releases(monkeypatch,index,order):
    from copy import deepcopy
    first,second,third=order
    p=MeasuredE24Author.__new__(MeasuredE24Author);p.index=index;p.identity={n:n for n in ('red','green','blue')};p.operations=[]
    p.s={'containers':{'box':{'ref':{'actor':'box'}}}};p.grasps={n:dict(local=[-.004,-.038688398004925996,.031],jaw_axis_local=[0,1,0])for n in p.identity}
    state={n:dict(grasp=[False,False])for n in p.identity};contacts={frozenset((first,'box')),frozenset((second,'box')),frozenset((third,'table'))}
    p.snapshot=lambda:(state,contacts);calls=[]
    monkeypatch.setattr(StructuralAuthor,'pickup',lambda self,n:calls.append((n,deepcopy(self.grasps[n])))or ({'actor':n},'right'))
    p.pickup(first);assert calls[-1][1]['jaw_axis_local']==[0,1,0]
    contacts.remove(frozenset((second,'box')))
    with pytest.raises(ToolExecutionError,match='earlier cups'):p.pickup(third)
    assert len(calls)==1
    contacts.add(frozenset((second,'box')));state[second]['grasp']=[False,True]
    with pytest.raises(ToolExecutionError,match='earlier cups'):p.pickup(third)
    state[second]['grasp']=[False,False];p.pickup(third)
    assert calls[-1][1]['jaw_axis_local']==[1,0,0]
    assert calls[-1][1]['local']==[-.038688398004925996,.004,.031]
    assert p.grasps[first]['jaw_axis_local']==[0,1,0]


def test_perpendicular_third_grasp_lies_inside_actual_source_collision_wall():
    import ast,re,hashlib
    from pathlib import Path
    from scipy.spatial import ConvexHull
    from videoicl_isaaclab.execution_design_e24_reference import CUP_SHA256
    p=Path(__file__).parents[2]/'deployment/real-text300-20261030/asset_roots/VIC_MECHANISM_ASSETS/hollow_cup.usda'
    data=p.read_bytes();assert hashlib.sha256(data).hexdigest()==CUP_SHA256
    block=data.decode().split('def Mesh "part_01"')[1].split('def Mesh "part_02"')[0]
    points=np.asarray(ast.literal_eval(re.search(r'point3f\[\] points = (\[[^\n]+\])',block)[1]))
    points=points@np.array([[1,0,0],[0,0,1],[0,-1,0]])*.088;points[:,2]-=.044
    h=ConvexHull(points);target=np.array([-.038688398004925996,.004,.031])
    assert np.max(h.equations[:,:3]@target+h.equations[:,3])<1e-8
