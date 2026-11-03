"""Offline public-action/guard regressions, never native physics acceptance."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import math
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3, source_sha256
from videoicl_isaaclab.execution_design_e15_wrist import prepare_empty, rotate_prepared_payload
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation


class Author:
    def __init__(self,tmp_path,q=-.65):
        obj=dict(id='blue_t',size=[.025,.025,.005],grasp_point_local=[0,0,0])
        spec=dict(id='E15',variant='C',objects=[obj],zones=[dict(id='target',xy=[.065,-.04],surface_z=.8)],
            execution_design=dict(revision=REVISION_V3,source_sha256=source_sha256(REVISION_V3)))
        self.scene=SimpleNamespace(spec=spec,embodiment=SimpleNamespace(name='franka'))
        data=SimpleNamespace(joint_pos=np.array([[0.,0.,0.,-1.,0.,1.,q]]),soft_joint_pos_limits=np.array([[[-2.8973,2.8973]]*7]))
        self.scene.robots={'right':SimpleNamespace(data=data,find_joints=lambda pattern:([6],['panda_joint7'])if pattern=='panda_joint7'else(list(range(7)),['panda_joint'+str(i)for i in range(1,8)]))}
        self.feedback={'status':'reached','joint_limit_names':[],'consecutive_ik_refusals':0}
        self.c=SimpleNamespace(snapshot=self.snapshot,action_feedback=lambda:{'control_feedback':{'right':self.feedback}});self._execution_design_reference_authorized=True
        self.out=tmp_path;self.smooth=False;self.control_report={'engineering_reference_only':True}
        self.stage='test';self.p=np.array([-.19,-.15,.96]);self.r=np.diag([1.,-1.,-1.]);self.actions=[]
        self.state={'blue_t':dict(pos=np.array([-.06,.06,.805]),mat=_axis_rotation([0,0,1],-math.pi/2),grasp=[False,False])}
        self.contacts={frozenset(('blue_t','table'))};self.goal=dict(object='blue_t',target='target',yaw=math.pi/2)
        self.targets=[]
    def snapshot(self):return self.state,self.contacts
    def tip(self,side):return self.p.copy()
    def tcp_rotation_task(self,side):return self.r.copy()
    def floor_clear_tcp(self,side):return .81
    def finger_geometry(self,side):return dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=self.p[2]-.01)
    def move_generated(self,positions):self.actions.append(('public_move',positions));self.p=np.asarray(positions['right'])
    def act(self,left,right,rotation_deg):
        self.actions.append((left,right,rotation_deg));delta=math.radians(rotation_deg)*(1 if right=='ROTATE_CCW'else-1)
        r=_axis_rotation([0,0,1],delta);self.r=r@self.r
        self.scene.robots['right'].data.joint_pos[0,6]-=delta
        if self.state['blue_t']['grasp'][1]:self.state['blue_t']['mat']=r@self.state['blue_t']['mat']
    def probe(self,author,controller,side,targets):
        self.targets=deepcopy(targets)
        return [dict(kinematically_reachable=True,minimum_joint_margin_rad=.3)for _ in targets]


def test_real_q7_failure_gets_opposed_empty_branch_and_original_loaded_goal(tmp_path):
    a=Author(tmp_path);before=deepcopy(a.scene.spec);source=deepcopy(a.state)
    row=prepare_empty(a,'right','blue_t',a.goal,1.1,a.probe)
    assert row['empty_turn_rad']==-math.pi and row['planned_loaded_turn_rad']==math.pi
    assert len(a.targets)==17 and row['native_route_passed']is False
    assert a.scene.spec==before and np.array_equal(a.state['blue_t']['pos'],source['blue_t']['pos'])
    assert np.array_equal(a.state['blue_t']['mat'],source['blue_t']['mat'])
    assert all(x[1]=='ROTATE_CW'for x in a.actions if x[0]!='public_move')
    # The fake only models yaw/joint bookkeeping. It does not assert reachability,
    # source grip, collisions, or successful physical transport.
    a.state['blue_t']['grasp']=[False,True]
    a.contacts={frozenset(('blue_t','right_finger1')),frozenset(('blue_t','right_finger2'))}
    assert rotate_prepared_payload(a,'blue_t','right',a.goal)
    assert abs(a.scene.robots['right'].data.joint_pos[0,6]+.65)<.06
    assert '_e15_wrist_branch'not in a.__dict__ and a.scene.spec==before
    assert not a.control_report['e15_loaded_wrist'][-1]['native_route_passed']


def test_original_a_no_halfturn_remains_action_for_action_unchanged(tmp_path):
    a=Author(tmp_path);a.scene.spec['variant']='A';a.goal['yaw']=-math.pi/2
    assert prepare_empty(a,'right','blue_t',a.goal,1.1,a.probe)is None
    assert not a.actions and not a.targets
    assert rotate_prepared_payload(a,'blue_t','right',a.goal)is False


def test_empty_raise_angular_settling_rebases_turn_to_original_checked_pose(tmp_path):
    a=Author(tmp_path);original=a.r.copy();move=a.move_generated
    def settling(positions):
        move(positions)
        # Native B replay: the old angular target advanced during the raise.
        a.r=_axis_rotation([0,0,1],math.radians(4.4))@a.r
        a.scene.robots['right'].data.joint_pos[0,6]-=math.radians(4.4)
    a.move_generated=settling
    row=prepare_empty(a,'right','blue_t',a.goal,1.1,a.probe)
    expected=_axis_rotation([0,0,1],-math.pi)@original
    assert row['after_raise_remaining_turn_rad']==pytest.approx(math.radians(-184.4))
    assert math.acos(float(np.clip((np.trace(expected@a.r.T)-1)/2,-1,1)))<math.radians(1)


@pytest.mark.parametrize('fault',['source','legacy','unauthorized','smooth','held','support','palm','wrist','ik','margin'])
def test_no_pregrasp_actuation_with_bad_scope_or_native_rejection(tmp_path,fault):
    a=Author(tmp_path)
    if fault=='source':a.scene.spec['execution_design']['source_sha256']='bad'
    elif fault=='legacy':a.scene.spec['execution_design']['revision']='legacy'
    elif fault=='unauthorized':a._execution_design_reference_authorized=False
    elif fault=='smooth':a.smooth=True
    elif fault=='held':a.state['blue_t']['grasp']=[False,True]
    elif fault=='support':a.contacts=set()
    elif fault=='palm':a.r=np.eye(3)
    elif fault=='wrist':a.scene.robots['right'].data.joint_pos[0,6]=0
    def probe(*args):
        rows=a.probe(*args)
        if fault=='ik':rows[3]['kinematically_reachable']=False
        if fault=='margin':rows[3]['minimum_joint_margin_rad']=.001
        return rows
    with pytest.raises((ValueError,RuntimeError)):prepare_empty(a,'right','blue_t',a.goal,1.1,probe)
    assert not a.actions


@pytest.mark.parametrize('fault',['lost_contact','wrong_goal','wrong_side','lost_grasp'])
def test_loaded_winding_never_hides_actual_grasp_failure_or_different_goal(tmp_path,fault):
    a=Author(tmp_path);prepare_empty(a,'right','blue_t',a.goal,1.1,a.probe)
    a.state['blue_t']['grasp']=[False,True]
    a.contacts={frozenset(('blue_t','right_finger1')),frozenset(('blue_t','right_finger2'))}
    if fault=='lost_contact':a.contacts.pop()
    elif fault=='wrong_goal':a.goal['yaw']=0
    elif fault=='lost_grasp':a.state['blue_t']['grasp']=[False,False]
    before=len(a.actions)
    with pytest.raises(RuntimeError):rotate_prepared_payload(a,'blue_t','left'if fault=='wrong_side'else'right',a.goal)
    assert len(a.actions)==before


@pytest.mark.parametrize('fault',['blocked','local_ik_refusal','joint_hit','measured_limit'])
def test_continuous_public_controller_and_actual_joint_guards_are_not_bypassed(tmp_path,fault):
    a=Author(tmp_path);old=a.act
    def act(*args,**kwargs):
        old(*args,**kwargs)
        if fault=='blocked':a.feedback['status']='blocked'
        elif fault=='local_ik_refusal':a.feedback['consecutive_ik_refusals']=1
        elif fault=='joint_hit':a.feedback['joint_limit_names']=['panda_joint7']
        else:a.scene.robots['right'].data.joint_pos[0,2]=2.897
    a.act=act
    with pytest.raises(RuntimeError,match='intermediate'):
        prepare_empty(a,'right','blue_t',a.goal,1.1,a.probe)
    assert len([x for x in a.actions if x[0]!='public_move'])==1


@pytest.mark.parametrize('task,revision,permission',[('E14',REVISION_V3,True),('E25',REVISION_V3,True),('E15','old',True),('E15',REVISION_V3,False),('E15',REVISION_V3,True)])
def test_actual_generated_prepare_hook_is_narrow_and_original_a_is_noop(tmp_path,task,revision,permission):
    import ast
    tree=ast.parse((Path(__file__).parents[1]/'videoicl_isaaclab/demonstration.py').read_text())
    method=next(n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name=='solve_generated')
    block=next(n for n in ast.walk(method)if isinstance(n,ast.If)and any(isinstance(x,ast.Call)and isinstance(x.func,ast.Name)and x.func.id=='prepare_e15_empty'for stmt in n.body for x in ast.walk(stmt)))
    a=Author(tmp_path);a.scene.spec['id']=task;a.scene.spec['execution_design']['revision']=revision
    a._execution_design_reference_authorized=permission;a.goal['yaw']=-math.pi/2
    ns={'self':a,'side':'right','name':'blue_t','goal':a.goal,'clear_z':1.1,'REVISION_V3':REVISION_V3,'__package__':'videoicl_isaaclab'}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[block],type_ignores=[])),'<actual hook>','exec'),ns)
    assert not a.actions and not a.targets


def test_B_preflight_and_caller_share_actual_empty_height_corner(tmp_path):
    from videoicl_isaaclab.execution_design_e15_wrist import prepared_empty_height
    a=Author(tmp_path);a.scene.spec['variant']='B'
    prepare_empty(a,'right','blue_t',a.goal,1.10,a.probe)
    assert len(a.targets)==18
    assert a._e15_wrist_branch['empty_height']==pytest.approx(.96)
    assert a.targets[7]['position']==pytest.approx([-.06,.06,.96])
    assert a.targets[8]['position'][2]==pytest.approx(.81)
    assert prepared_empty_height(a,'right','blue_t',a.goal,1.10)==pytest.approx(.96)
    assert all(p['position'][2]==1.10 for p in a.targets[9:16])


@pytest.mark.parametrize('variant,expected',[('B',.96),('C',1.10),('A',1.10)])
def test_actual_full_pregrasp_first_two_moves_use_only_B_screened_height(tmp_path,variant,expected):
    import ast
    tree=ast.parse((Path(__file__).parents[1]/'videoicl_isaaclab/demonstration.py').read_text())
    method=next(n for n in ast.walk(tree)if isinstance(n,ast.FunctionDef)and n.name=='solve_generated')
    statements=None
    for owner in ast.walk(method):
        for _,value in ast.iter_fields(owner):
            if not isinstance(value,list):continue
            for i,node in enumerate(value):
                if isinstance(node,ast.Assign)and isinstance(node.value,ast.Name)and node.value.id=='approach_z'and any(isinstance(t,ast.Name)and t.id=='empty_approach_z'for t in node.targets):statements=value[i:i+4]
    assert statements is not None
    a=Author(tmp_path);a.scene.spec['variant']=variant
    a._e15_wrist_branch=dict(object='blue_t',side='right',goal_yaw=a.goal['yaw'],loaded_turn=math.pi,empty_height=.96)
    ns={'self':a,'side':'right','name':'blue_t','goal':a.goal,'approach_z':1.10,'xy':[.065,-.04],
        'REVISION_V3':REVISION_V3,'__package__':'videoicl_isaaclab'}
    exec(compile(ast.fix_missing_locations(ast.Module(body=statements,type_ignores=[])),'<actual B empty moves>','exec'),ns)
    assert len(a.actions)==2
    assert all(x[1]['right'][2]==expected for x in a.actions)
