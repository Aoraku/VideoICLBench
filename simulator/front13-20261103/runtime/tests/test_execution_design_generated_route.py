"""Reference-route CPU geometry checks; these do not claim native reachability."""
from pathlib import Path
from types import SimpleNamespace
import ast
import json
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3,REVISION_V2
from videoicl_isaaclab.execution_design_generated_route import measured_generated_clearance
from videoicl_isaaclab.realworld_scenes import load


def author(spec):
    state={o['id']:dict(pos=np.array([*o['xy'],o.get('center_z',o.get('bottom',.8)+o['size'][2])]),mat=np.eye(3))for o in spec['objects']}
    return SimpleNamespace(scene=SimpleNamespace(spec=spec,embodiment=SimpleNamespace(name='franka')),c=SimpleNamespace(snapshot=lambda:(state,[])),
        _execution_design_reference_authorized=True,control_report={'engineering_reference_only':True},smooth=False,tip=lambda s:np.array([0,0,1.]),
        finger_geometry=lambda s:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=.99))


@pytest.mark.parametrize('task',['E02','E04','E05','E07','E11','E13','E14','E16','E21','E22','E25','E27','E31','E34','E35','E36','E41'])
def test_actual_v3_inputs_get_lower_collision_clear_plane(task,tmp_path):
    p=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json';binding=json.loads(p.read_text())
    binding['execution_design']=dict(revision=REVISION_V3,condition='I');path=tmp_path/'binding.json';path.write_text(json.dumps(binding))
    spec=load(task,'A',4201,path,verify_files=False);a=author(spec);route=measured_generated_clearance(a)
    assert route['clearance_z_m']<1.05
    assert route['clearance_z_m']>=route['obstacle_top_z_m']+route['payload_depth_allowance_m']+.024999
    assert route['native_reachability_verified'] is False


def test_live_rotated_bound_and_real_finger_mesh_change_clearance():
    s=dict(id='E04',execution_design={'revision':REVISION_V3},objects=[dict(id='cup',xy=[0,0],bottom=.8,size=[.02,.03,.04])],goals=[{'object':'cup'}])
    a=author(s);first=measured_generated_clearance(a)
    state,_=a.c.snapshot();state['cup']['pos'][2]+=.08
    state['cup']['mat']=np.array([[0,0,1],[0,1,0],[-1,0,0]])
    a.finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=.96)
    second=measured_generated_clearance(a)
    assert second['object_tops_task_m']['cup']==pytest.approx(.94)
    assert second['finger_below_tcp_m']['left']==pytest.approx(.04)
    assert second['clearance_z_m']>first['clearance_z_m']


@pytest.mark.parametrize('change',[{'_execution_design_reference_authorized':False},{'revision':REVISION_V2},{'task':'E30'}])
def test_legacy_and_unreviewed_tasks_cannot_use_engineering_override(change):
    s=dict(id=change.get('task','E04'),execution_design={'revision':change.get('revision',REVISION_V3)},objects=[],goals=[])
    a=author(s)
    if '_execution_design_reference_authorized'in change:a._execution_design_reference_authorized=False
    with pytest.raises(ValueError,match='restricted'):measured_generated_clearance(a)


def test_solve_generated_uses_strict_gate_and_remeasures_before_every_pickup():
    source=(Path(__file__).parents[1]/'videoicl_isaaclab/demonstration.py').read_text();tree=ast.parse(source)
    method=next(n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name=='solve_generated')
    gate=next(n for n in method.body if isinstance(n,ast.Assign)and ast.unparse(n.targets[0])=='measured_route_enabled')
    expression=ast.unparse(gate.value)
    assert '_execution_design_reference_authorized'in expression and 'REVISION_V3'in expression
    loop=next(n for n in method.body if isinstance(n,ast.For)and ast.unparse(n.iter)=='enumerate(goals)')
    code=ast.unparse(loop.body[0]);assert 'measured_generated_clearance(self)'in code
    assert "clear_z = approach_z = route['clearance_z_m']"in code
    assert 'measured-generated-route.private.jsonl'in code


def test_completed_stack_raises_next_pickup_clearance():
    s=dict(id='E14',execution_design={'revision':REVISION_V3},objects=[
        dict(id='red',xy=[0,0],bottom=.8,size=[.02,.02,.02]),
        dict(id='green',xy=[.1,0],bottom=.8,size=[.02,.02,.02])],goals=[{'object':'red'},{'object':'green'}])
    a=author(s);first=measured_generated_clearance(a)
    state,_=a.c.snapshot();state['red']['pos'][2]+=.08
    second=measured_generated_clearance(a)
    assert second['clearance_z_m']==pytest.approx(first['clearance_z_m']+.08)


def test_missing_or_nonfinite_real_finger_geometry_refuses_route():
    s=dict(id='E04',execution_design={'revision':REVISION_V3},objects=[],goals=[])
    a=author(s);a.finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=float('nan'))
    with pytest.raises(ValueError,match='Finite actual'):measured_generated_clearance(a)


@pytest.mark.parametrize('task,name,expected',[('E04','blue_cup','left'),('E04','red_cup','right'),('E07','block1','right'),('E07','block2','left')])
def test_new_input_uses_hand_nearest_both_actual_endpoints(task,name,expected,tmp_path):
    from videoicl_isaaclab.execution_design_generated_route import choose_generated_hand
    binding=json.loads((Path(__file__).parents[1]/'configs/realworld_full50_bindings.json').read_text())
    binding['execution_design']=dict(revision=REVISION_V3,condition='I');p=tmp_path/'b.json';p.write_text(json.dumps(binding))
    spec=load(task,'A',4201,p,verify_files=False);a=author(spec)
    a.scene.robots={side:SimpleNamespace(data=SimpleNamespace(root_pos_w=np.array([[-.65,y,.75]])))for side,y in [('left',.3),('right',-.3)]}
    a.scene.world_to_task=lambda p:p
    goal=next(g for g in spec['goals']if g['object']==name);target=next(z for z in spec['zones']if z['id']==goal['target'])
    report=choose_generated_hand(a,name,goal,target,spec['expert_arm'])
    assert report['chosen']==expected
    assert not report['native_reachability_verified']


def test_hand_switch_uses_real_actions_to_return_home_and_refuses_held_object():
    from videoicl_isaaclab.execution_design_generated_route import park_before_hand_switch
    a=SimpleNamespace(carried_payload=None,tip=lambda s:np.array([.15,-.12,.94]),c=SimpleNamespace(snapshot=lambda:({'cup':{'grasp':[False,False]}},[])))
    moves=[];a.move_generated=lambda goal:moves.append(goal)
    park_before_hand_switch(a,'right','left',{'right':[-.2,-.3]},.97)
    assert moves==[{'right':[.15,-.12,.97]},{'right':[-.2,-.3,.97]}]
    a.c.snapshot=lambda:({'cup':{'grasp':[False,True]}},[])
    with pytest.raises(RuntimeError,match='actual payload release'):park_before_hand_switch(a,'right','left',{'right':[-.2,-.3]},.97)
    assert len(moves)==2


def generated_move_author(fraction):
    source=(Path(__file__).parents[1]/'videoicl_isaaclab/demonstration.py').read_text();tree=ast.parse(source)
    method=next(n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name=='move_generated')
    module=ast.Module(body=[method],type_ignores=[]);namespace={'np':np,'json':json,'__package__':'videoicl_isaaclab'}
    exec(compile(ast.fix_missing_locations(module),'<actual move_generated>','exec'),namespace)
    tip=np.zeros(3);c=SimpleNamespace(steps=0,snapshot=lambda:({'cup':{'grasp':[True,False]}},[]))
    a=SimpleNamespace(smooth=False,scene=SimpleNamespace(embodiment=SimpleNamespace(name='franka'),spec={'id':'E04','execution_design':{'revision':REVISION_V3}}),
        _execution_design_reference_authorized=True,carried_payload=('cup','left'),stage='grasped-cup',c=c,tip=lambda s:tip.copy())
    labels={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}
    def act(left,right,mm):
        axis,sign=labels[left];tip[axis]+=sign*float(mm)*.001*fraction;c.steps+=1
    a.act=act;a.move_generated=namespace['move_generated'].__get__(a)
    return a


def test_long_loaded_transfer_continues_while_measured_partial_actions_progress():
    a=generated_move_author(.2);a.move_generated({'left':[.4,0,0]})
    assert 120<a.c.steps<=360
    assert np.max(np.abs(a.tip('left')-np.array([.4,0,0])))<=.004


def test_long_transfer_budget_does_not_keep_pushing_blocked_or_lost_payload():
    a=generated_move_author(0)
    with pytest.raises(RuntimeError,match='stalled'):a.move_generated({'left':[.4,0,0]})
    assert a.c.steps<40
    a=generated_move_author(.2);a.c.snapshot=lambda:({'cup':{'grasp':[False,False]}},[])
    with pytest.raises(RuntimeError,match='grip lost'):a.move_generated({'left':[.4,0,0]})
    assert a.c.steps==0


def test_legacy_generated_transfer_keeps_original_iteration_budget():
    a=generated_move_author(.2);a._execution_design_reference_authorized=False
    with pytest.raises(RuntimeError,match='unreachable'):a.move_generated({'left':[.4,0,0]})
    assert a.c.steps==120


@pytest.mark.parametrize('task',['E32','E33','E38','E47','E48','E49'])
def test_back25_waypoint_stops_immediately_on_actual_payload_loss(task):
    a=generated_move_author(.2);a.scene.spec['id']=task
    a.c.snapshot=lambda:({'cup':{'grasp':[False,False]}},[])
    with pytest.raises(RuntimeError,match='grip lost'):
        a.move_generated({'left':[.4,0,0]})
    assert a.c.steps==0


def test_back25_grip_guard_also_checks_arrived_waypoint():
    a=generated_move_author(.2);a.scene.spec['id']='E38'
    a.c.snapshot=lambda:({'cup':{'grasp':[False,False]}},[])
    with pytest.raises(RuntimeError,match='grip lost'):
        a.move_generated({'left':[0,0,0]})
    assert a.c.steps==0


@pytest.mark.parametrize('task',['E22','E25'])
@pytest.mark.parametrize('variant',['A','B','C'])
@pytest.mark.parametrize('condition',['I','E'])
def test_car_reference_and_cutlery_handle_routes_preserve_contract(task,variant,condition,tmp_path):
    import copy
    from videoicl_isaaclab.execution_design_generated_route import choose_generated_hand
    binding=json.loads((Path(__file__).parents[1]/'configs/realworld_full50_bindings.json').read_text())
    binding['execution_design']=dict(revision=REVISION_V3,condition=condition)
    p=tmp_path/'binding.json';p.write_text(json.dumps(binding))
    spec=load(task,variant,4201,p,verify_files=False);original=copy.deepcopy(spec);a=author(spec)
    a.scene.robots={side:SimpleNamespace(data=SimpleNamespace(root_pos_w=np.array([[-.65,y,.75]])))for side,y in [('left',.3),('right',-.3)]}
    a.scene.world_to_task=lambda p:p
    clearance=measured_generated_clearance(a)
    assert ('car'if task=='E22'else'tray')in clearance['object_tops_task_m']
    state,_=a.c.snapshot()
    if task=='E25':
        # Actual pickup yaw can differ from the final handle-direction goal.
        for goal in spec['goals']:state[goal['object']]['mat']=np.array([[0,-1,0],[1,0,0],[0,0,1.]])
    for goal in spec['goals']:
        target=next(z for z in spec['zones']if z['id']==goal['target'])
        obj=next(o for o in spec['objects']if o['id']==goal['object'])
        route=choose_generated_hand(a,obj['id'],goal,target,spec['expert_arm'])
        if task=='E25' and variant=='A' and obj['id'] in ('knife','fork'):
            from videoicl_isaaclab.execution_design_e25_reference import TAIL_GRASPS
            obj=dict(obj,grasp_point_local=TAIL_GRASPS[obj['id']]['point'])
        if task=='E25' and variant=='B':
            from videoicl_isaaclab.execution_design_e25_b_reference import SECTIONS
            section=SECTIONS[obj['id']]
            obj=dict(obj,grasp_point_local=((np.asarray(section['lower'])+np.asarray(section['upper']))/2).tolist())
        offset=state[obj['id']]['mat']@np.asarray(obj.get('grasp_point_local',[0,0,0]))
        assert np.allclose(route['source_grasp_task_m'],state[obj['id']]['pos']+offset)
        destination_offset=offset
        if task=='E25':
            yaw=goal.get('yaw',0.);rotation=np.array([[np.cos(yaw),-np.sin(yaw),0],[np.sin(yaw),np.cos(yaw),0],[0,0,1.]])
            destination_offset=rotation@np.asarray(obj.get('grasp_point_local',[0,0,0]))
        assert np.allclose(route['destination_grasp_task_xy_m'],np.asarray(goal.get('placement_xy',target['xy']))+destination_offset[:2])
        assert route['native_reachability_verified']is False
    assert spec==original  # No reference/sequence/yaw/score mutation.


@pytest.mark.parametrize('variant','ABC')
@pytest.mark.parametrize('condition','RIE')
@pytest.mark.parametrize('seed',[4201,4202,4203])
def test_e06_carry_plane_clears_measured_tray_without_changing_hand(tmp_path,variant,condition,seed):
    from videoicl_isaaclab.execution_design_generated_route import HAND_SELECTION_TASKS
    binding=json.loads((Path(__file__).parents[1]/'configs/realworld_full50_bindings.json').read_text())
    binding['execution_design']=dict(revision=REVISION_V3,condition=condition)
    p=tmp_path/'e06.json';p.write_text(json.dumps(binding))
    spec=load('E06',variant,seed,p,verify_files=False);a=author(spec)
    route=measured_generated_clearance(a)
    assert .85 < route['clearance_z_m'] < 1.0
    assert route['clearance_z_m'] >= route['object_tops_task_m']['eggtray'] + route['payload_depth_allowance_m'] + .024999
    assert spec['expert_arm']=='left' and 'E06' not in HAND_SELECTION_TASKS
    assert not route['native_reachability_verified']
