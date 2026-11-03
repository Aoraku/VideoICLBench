"""Original wall identity, real support margins and fixed-fixture drag guards."""
from copy import deepcopy
from pathlib import Path
import json
import numpy as np
import pytest
from types import SimpleNamespace
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_e09_reference import near_wall_ref,support_metrics,drag_waypoints
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
V=Path(__file__).resolve().parents[2]/'verification/task-design-revision-20261102'
BOUNDS=dict(lower=[-.35,-.6,.8],upper=[.35,.6,.8],top=.8)


def test_genuinely_held_e09_move_retains_two_mm_public_action_guard():
    from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
    p=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);p.task='E09';p.max_mm=10.;p.min_mm=.5;p.max_deg=10.;p.min_deg=.5
    p.a=SimpleNamespace(control_report={'engineering_reference_only':True},stage='held-original-lid')
    p.c=SimpleNamespace(steps=0);p.start=0;p.limit=20;p.spec={};tip=np.array([0.,0.,1.]);commands=[]
    p.snapshot=lambda:({'group_box0_lid':{'grasp':[True,False]}},set());p.tip=lambda side:tip.copy()
    def action(left,right,mm,rotation_deg):
        commands.append((left,right,mm));tip[0]+=mm/1000;p.c.steps+=1
    p.a.act=action
    p.move('left',[.01,0.,1.],tolerance=.0001)
    assert len(commands)==5 and all(mm<=2. for _,_,mm in commands)
    assert p.max_mm==10.

def spec(variant='A'):
    return load('E09',variant,4201,V/'release-v3-full50-r1/bindings/I.private.json',verify_files=False)

@pytest.mark.parametrize('variant',list('ABC'))
@pytest.mark.parametrize('name',['shipping_crate','group_box0','group_box1','group_box2'])
def test_near_wall_uses_original_collision_and_preserves_spec(variant,name):
    s=spec(variant);before=deepcopy(s);obj=next(o for o in s['objects']if o['id']==name);original=s['execution_design']['grasps'][name]
    ref=near_wall_ref(obj,original)
    assert ref['local'][0]==-original['local'][0]
    assert ref['local'][1:]==original['local'][1:]
    assert s==before

@pytest.mark.parametrize('change',['wall','size','axis','point'])
def test_changed_wall_descriptor_is_rejected(change):
    s=spec();obj=deepcopy(next(o for o in s['objects']if o['id']=='shipping_crate'));ref=deepcopy(s['execution_design']['grasps']['shipping_crate'])
    if change=='wall':obj['collision_shapes'][1]['pos'][0]-=.001
    if change=='size':obj['size'][0]+=.001
    if change=='axis':ref['jaw_axis_local']=[0,1,0]
    if change=='point':ref['local'][2]=.055
    with pytest.raises(ToolExecutionError):near_wall_ref(obj,ref)

@pytest.mark.parametrize('count,minimum',[(0,.058),(1,.027189),(2,.03348),(3,.058)])
def test_estimated_sequential_load_com_has_real_floor_support(count,minimum):
    center=np.array([-.15,-.54,.855]);mass=.55+.19*count;com=(center*.55+sum((center+[0,(i-1)*.12,-.02])*.19 for i in range(count)))/mass
    m=support_metrics(center,np.eye(3),[.09,.2,.055],BOUNDS,com)
    assert m['margin_m']>=minimum-1e-6

@pytest.mark.parametrize('center,com',[( [-.15,-.61,.855],[-.15,-.61,.855]),([-.15,-.54,.855],[-.15,-.599,.85])])
def test_com_outside_actual_supported_table_is_rejected(center,com):
    with pytest.raises(ToolExecutionError):support_metrics(center,np.eye(3),[.09,.2,.055],BOUNDS,com)

@pytest.mark.parametrize('variant',list('ABC'))
def test_original_three_leg_drag_retains_source_fixtures(variant):
    s=spec(variant);before=deepcopy(s['fixtures']);points=drag_waypoints([.22,-.16,.855],BOUNDS,s['fixtures'],[.09,.2,.055])
    assert np.allclose(points,[[.16,-.16,.855],[.16,-.54,.855],[-.15,-.54,.855]])
    assert s['fixtures']==before


def test_new_obstacle_in_drag_sweep_rejects_before_motion():
    s=spec();s['fixtures'].append(dict(type='box',xy=[.16,-.45],z=.82,size=[.01,.01,.02]))
    with pytest.raises(ToolExecutionError):drag_waypoints([.22,-.16,.855],BOUNDS,s['fixtures'],[.09,.2,.055])

@pytest.mark.parametrize('index',[0,1,2])
@pytest.mark.parametrize('yaw',[-2.,0.,2.])
def test_nearer_grid_contains_entire_40mm_original_square_with_two_mm_guard(index,yaw):
    from videoicl_isaaclab.execution_design_e09_reference import near_slot
    import itertools
    a=np.deg2rad(yaw);rotation=np.array([[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1.]])
    cloud=(np.array(list(itertools.product([-1,1],repeat=3)))*[.02,.02,.003])@rotation.T
    point=near_slot([-.055,-.047,-.016],[.055,.047,.022],index,cloud)
    assert np.all(cloud[:,:2]+point[:2]>=np.array([-.055,-.047])+.002)
    assert np.all(cloud[:,:2]+point[:2]<=np.array([.055,.047])-.002)


def test_nearer_grid_rejects_rotated_original_footprint_instead_of_clipping_it():
    from videoicl_isaaclab.execution_design_e09_reference import near_slot
    import itertools
    a=np.deg2rad(5);r=np.array([[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1.]])
    cloud=(np.array(list(itertools.product([-1,1],repeat=3)))*[.02,.02,.003])@r.T
    with pytest.raises(ToolExecutionError):near_slot([-.055,-.047,-.016],[.055,.047,.022],0,cloud)


def test_original_indirect_same_group_support_is_accepted():
    from videoicl_isaaclab.execution_design_e09_reference import connected_group_support
    members=['red_triangle','red_square','red_circle'];edges={frozenset(x)for x in [('red_triangle','group_box0'),('red_square','red_triangle'),('red_circle','group_box0')]}
    assert connected_group_support('group_box0',members,edges)


def test_external_support_cannot_replace_original_same_group_chain():
    from videoicl_isaaclab.execution_design_e09_reference import connected_group_support
    members=['red_triangle','red_square','red_circle'];edges={frozenset(x)for x in [('red_triangle','group_box0'),('red_square','other_batch_blue_circle'),('other_batch_blue_circle','group_box0'),('red_circle','group_box0')]}
    assert not connected_group_support('group_box0',members,edges)
