"""CPU planning/guard tests, not physical acceptance."""
import copy,json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3,REVISION_V2
from videoicl_isaaclab.execution_design_e07_reference import plan_transfers,staging_target,verify_relay_release
from videoicl_isaaclab.realworld_scenes import load


def author(tmp_path,variant='A',seed=4201,condition='I',task='E07'):
    binding=json.loads((Path(__file__).parents[1]/'configs/realworld_full50_bindings.json').read_text());binding['execution_design']=dict(revision=REVISION_V3,condition=condition)
    p=tmp_path/'binding.json';p.write_text(json.dumps(binding));spec=load(task,variant,seed,p,verify_files=False)
    state={o['id']:dict(pos=np.array([*o['xy'],o['bottom']+o['size'][2]]),mat=np.eye(3),grasp=[False,False])for o in spec['objects']};contacts=set()
    scene=SimpleNamespace(spec=spec,embodiment=SimpleNamespace(name='franka'),origin=np.zeros(3),world_to_task=lambda p:p,
        layout=SimpleNamespace(config={'table':dict(position=[0,0,.775],size=[.7,1.2,.05])}),
        robots={side:SimpleNamespace(data=SimpleNamespace(root_pos_w=np.array([[-.65,y,.81]])))for side,y in [('left',.3),('right',-.3)]})
    return SimpleNamespace(scene=scene,c=SimpleNamespace(snapshot=lambda:(state,contacts)),out=tmp_path,
        _execution_design_reference_authorized=True,control_report={'engineering_reference_only':True},smooth=False,floor_clear_tcp=lambda side:.81,tcp_rotation_task=lambda side:np.eye(3))


def feasible(author,controller,side,targets):return [dict(kinematically_reachable=True,collision_verified=False)for _ in targets]


@pytest.mark.parametrize('task',['E04','E07','E16','E25'])
@pytest.mark.parametrize('variant',['A','B','C'])
@pytest.mark.parametrize('seed',[4201,4202,4203])
@pytest.mark.parametrize('condition',['I','E'])
def test_relay_keeps_source_contract_and_final_order(tmp_path,variant,seed,condition,task):
    a=author(tmp_path,variant,seed,condition,task);before=copy.deepcopy(a.scene.spec);goals=a.scene.spec['goals'];plan=plan_transfers(a,goals,feasible)
    assert a.scene.spec==before
    final=[g for g in plan if '_e07_engineering_target'not in g]
    assert [(g['object'],g['target'])for g in final]==[(g['object'],g['target'])for g in goals]
    assert any('_e07_after_relay'in g for g in final)
    for g in final:
        if '_e07_after_relay'in g:
            prev=plan[plan.index(g)-1];assert prev['object']==g['object']
            assert prev['_e07_engineering_arm']!=g['_e07_engineering_arm']
    record=json.loads((tmp_path/'e07-relay-plan.private.json').read_text())
    assert not record['native_passed'] and not record['collision_verified']


def test_unreachable_endpoint_and_unknown_revision_refuse(tmp_path):
    a=author(tmp_path)
    with pytest.raises(RuntimeError,match='unreachable measured endpoint'):
        plan_transfers(a,a.scene.spec['goals'],lambda a,c,s,t:[{'kinematically_reachable':False}for _ in t])
    a.scene.spec['execution_design']['revision']=REVISION_V2
    with pytest.raises(ValueError,match='explicit v3'):staging_target(a)


def test_relay_requires_actual_release_table_contact_and_position(tmp_path):
    a=author(tmp_path);plan=plan_transfers(a,a.scene.spec['goals'],feasible);goal=next(g for g in plan if '_e07_after_relay'in g)
    state,contacts=a.c.snapshot();name=goal['object'];site=goal['_e07_after_relay'];state[name]['pos'][:2]=site['xy']
    with pytest.raises(RuntimeError,match='release and table support'):verify_relay_release(a,goal)
    contacts.add(frozenset((name,'table')));state[name]['grasp']=[True,False]
    with pytest.raises(RuntimeError,match='release and table support'):verify_relay_release(a,goal)
    state[name]['grasp']=[False,False];verify_relay_release(a,goal)
    state[name]['pos'][0]+=.2
    with pytest.raises(RuntimeError,match='outside'):verify_relay_release(a,goal)


def test_occupied_table_rejects_invented_staging_site(tmp_path):
    a=author(tmp_path);a.scene.layout.config['table']['size']=[.1,.1,.05]
    with pytest.raises(RuntimeError,match='No measured empty'):staging_target(a)


def test_inline_staging_targets_are_strictly_e07_engineering_only():
    import ast
    tree=ast.parse((Path(__file__).parents[1]/'videoicl_isaaclab/demonstration.py').read_text())
    method=next(n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name=='solve_generated')
    target=next(n for n in ast.walk(method)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='target'for t in n.targets))
    assert isinstance(target.value,ast.IfExp)
    guard=ast.unparse(target.value.test)
    assert 'measured_route_enabled'in guard and "in ('E04', 'E07', 'E16', 'E25')"in guard


def test_e16_relay_does_not_reuse_final_placement_override(tmp_path):
    a=author(tmp_path,task='E16');goal=a.scene.spec['goals'][0]
    goal['placement_xy']=[-.08,.14];before=copy.deepcopy(a.scene.spec)
    plan=plan_transfers(a,[goal],feasible)
    assert len(plan)==2
    assert 'placement_xy'not in plan[0] and 'required_support'not in plan[0]
    assert plan[1]['placement_xy']==goal['placement_xy']
    assert plan[1]['required_support']=='tray'
    assert a.scene.spec==before
    assert plan[0]['_e07_engineering_target']['half_size'][0]<.06


def test_relay_rejects_other_tasks_and_missing_authorization(tmp_path):
    a=author(tmp_path);a.scene.spec['id']='E24'
    with pytest.raises(ValueError):staging_target(a)
    a.scene.spec['id']='E16';a._execution_design_reference_authorized=False
    with pytest.raises(ValueError):staging_target(a)


def test_e25_source_relay_defers_absolute_orientation_and_uses_tail_grasp(tmp_path):
    from videoicl_isaaclab.execution_design_e25_reference import TAIL_GRASPS
    a=author(tmp_path,task='E25');original=copy.deepcopy(a.scene.spec)
    plan=plan_transfers(a,a.scene.spec['goals'],feasible)
    record=json.loads((tmp_path/'e07-relay-plan.private.json').read_text())
    for g in plan:
        if '_e07_engineering_target'in g:
            assert not any(k in g for k in ('roll','pitch','yaw','placement_xy','required_support'))
            assert g['_e07_engineering_arm']=='right'
        else:assert g['yaw']==0 and g['_e07_engineering_arm']=='left'
    for r in record['records']:
        if r['object']in TAIL_GRASPS:
            np.testing.assert_allclose(r['private_grasp_local'],TAIL_GRASPS[r['object']]['point'])
            np.testing.assert_allclose(r['destination_grasp_task_m'][:2],np.asarray(next(z['xy']for z in a.scene.spec['zones']if z['id']==r['object']+'_target'))+TAIL_GRASPS[r['object']]['point'][:2])
    assert a.scene.spec==original


def test_e25_absolute_orientation_changes_destination_offset_and_ik_rotation(tmp_path):
    a=author(tmp_path,task='E25');goal=copy.deepcopy(a.scene.spec['goals'][0]);goal['yaw']=np.pi/2
    checked=[]
    def probe(a,c,side,targets):checked.extend(targets);return feasible(a,c,side,targets)
    plan=plan_transfers(a,[goal],probe)
    expected=np.array([[0,-1,0],[1,0,0],[0,0,1.]])
    assert any(np.allclose(row['rotation'],expected)for row in checked)
    assert plan[-1]['yaw']==np.pi/2


def test_e25_relay_real_rotated_table_and_native_settled_cutlery_bounds(tmp_path):
    """Regression for native slot7 refusal: real table is .7 by 1.2 in task XY.

    These matrices/positions were captured from the original initial seal.
    This only checks planning; real grip/relay/support remain native pending.
    """
    a=author(tmp_path,task='E25');state,_=a.c.snapshot()
    measured={
      'fork':([-.0001094598847,-.1450023651123,.8090247488022],[[.9999294877,-.0000127554,-.0118772509],[.0000127554,1.,-.0000034817],[.0118772499,.0000033304,.9999294877]]),
      'spoon':([.0000021131709,-.1995668411255,.8086617565155],[[.999999702,-.0004689693,.0007768814],[.0004252195,.9984704852,.0552869476],[-.0008016154,-.0552865937,.9984701872]]),
      'knife':([-.00045187585,-.0894184112549,.8068033432961],[[.9986509681,.0000920296,-.0519244783],[.0044620037,.9961473346,.087581031],[.0517324843,-.0876945704,.9948031902]]),
      'tray':([-.0000069688249,.1200089454651,.8199954009056],[[.9999997616,.0000004172,-.000355924],[-.0000002384,.999999702,.0005228775],[.0003559241,-.0005228774,.9999998212]])}
    for n,(pos,mat)in measured.items():state[n].update(pos=np.array(pos),mat=np.array(mat))
    # Actual world table, transformed into the task frame used by the robot.
    origin=np.array([8.,0.,0.]);a.scene.origin=origin
    a.scene.world_to_task=lambda p:np.array([p[1],-(p[0]-origin[0]),p[2]+.06])
    a.scene.layout.config['table']=dict(position=[0,0,.715],size=[1.2,.7,.05])
    for side,y in [('left',.3),('right',-.3)]:a.scene.robots[side].data.root_pos_w=np.array([[origin[0]-y,-.65,.75]])
    site=staging_target(a);np.testing.assert_allclose(site['xy'],[-.2,-.03],atol=1e-6)
    assert .125<site['half_size'][0]<.126 and .044<site['half_size'][1]<.045
    assert site['footprint_source']=='measured_orientation_preserved_payload_bounds_plus_25mm'
    xy=np.array(site['xy']);half=np.array(site['half_size'])
    assert np.all(abs(xy)+half<np.array([.35,.6]))
    for obj in a.scene.spec['objects']:
        body=state[obj['id']];R=body['mat'];p=body['pos']+R@np.array(obj.get('local_bounds_center',[0,0,0]));extent=abs(R)@np.array(obj.get('bounds_half_extent',obj['size']))
        assert np.any(abs(xy-p[:2])>=extent[:2]+half)
    assert plan_transfers(a,a.scene.spec['goals'],feasible)
    # A rotation which really occupies the corridor must not reuse the old thin
    # footprint. The same fixed source/target world can legitimately be blocked.
    R=np.array([[0,-1,0],[1,0,0],[0,0,1.]])
    for name in ('fork','spoon','knife'):state[name]['mat']=R
    try:
        rotated=staging_target(a)
    except RuntimeError:pass
    else:assert rotated['half_size'][1]>.12


def test_e25_native_endpoint_refusal_retries_checked_empty_receiver_only(tmp_path):
    a=author(tmp_path,task='E25');original=copy.deepcopy(a.scene.spec)
    a.scene.embodiment=SimpleNamespace(name='franka');a.tip=lambda side:np.array([-.49,.52,1.245])
    a.finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',fingers=[dict(aabb_min_task_m=[-.51,.45,1.235],aabb_max_task_m=[-.48,.59,1.291])])
    calls={'left':0,'right':0}
    def probe(a,c,side,targets):
        calls[side]+=1;valid=side=='right'or calls[side]>1
        return [dict(kinematically_reachable=valid,minimum_joint_margin_rad=.3)for t in targets]
    plan=plan_transfers(a,a.scene.spec['goals'],probe)
    assert calls=={'left':2,'right':1}
    assert all('_e25_receiver_rotation_task'in g for g in plan if '_e07_after_relay'in g)
    assert all('_e25_receiver_rotation_task'not in g for g in plan if '_e07_engineering_target'in g)
    assert a.scene.spec==original
    with pytest.raises(RuntimeError,match='unreachable measured endpoint'):
        plan_transfers(a,a.scene.spec['goals'],lambda a,c,s,targets:[dict(kinematically_reachable=False)for _ in targets])
    record=json.loads((tmp_path/'e07-relay-plan.private.json').read_text())
    assert record['unreachable_sides']==['left','right']and 'receiver_pitch_8deg'in record['ik_candidates']['left']


@pytest.mark.parametrize('accept',[True,False])
def test_e25_b_receiver_candidate_requires_new_measured_ik_before_plan(tmp_path,accept):
    a=author(tmp_path,'B',4201,'I','E25');saved=copy.deepcopy(a.scene.spec)
    a.tip=lambda side:np.array([-.2,0,1.]);a.tcp_rotation_task=lambda side:np.diag([1.,-1.,-1.])
    a.finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',fingers=[
        dict(body_origin_task_m=[-.2,y,1.04],aabb_min_task_m=[-.215,y-.01,.99],aabb_max_task_m=[-.185,y+.01,1.05])for y in (-.04,.04)])
    calls=[];left_calls=0
    def probe(author,controller,side,targets):
        nonlocal left_calls
        if side=='left':left_calls+=1
        valid=side=='right'or(accept and left_calls>1)
        calls.append(dict(side=side,targets=copy.deepcopy(targets)))
        return [dict(kinematically_reachable=valid,minimum_joint_margin_rad=.2,collision_verified=False)for _ in targets]
    if accept:
        plan=plan_transfers(a,a.scene.spec['goals'],probe)
        receivers=[g for g in plan if '_e07_after_relay'in g]
        assert len(receivers)==3 and all('_e25_receiver_rotation_task'in g for g in receivers)
        assert left_calls==2
        report=json.loads((tmp_path/'e07-relay-plan.private.json').read_text())
        assert all(r['private_grasp_local'][0]>.059 for r in report['records'])
        assert 'e25_b_receiver_20deg'in report['ik_candidates']['left']
    else:
        with pytest.raises(RuntimeError,match='unreachable'):plan_transfers(a,a.scene.spec['goals'],probe)
        assert left_calls==3 # original,20deg,24deg, each actually checked
    assert a.scene.spec==saved
