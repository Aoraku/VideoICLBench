"""Public-action mock checks; native grasp acceptance remains separate."""
from types import SimpleNamespace
import math
import numpy as np
import pytest
from videoicl_isaaclab.author_orientation import _quaternion_matrix
from videoicl_isaaclab.execution_design_tabletop_grasp import level_empty_palm


def rotation(axis,angle):
    unit=np.eye(3)[axis];q=np.r_[math.cos(angle/2),unit*math.sin(angle/2)]
    return _quaternion_matrix(q)


class Reference:
    def __init__(self,task='E13'):
        self.scene=SimpleNamespace(spec=dict(id=task,execution_design=dict(revision='embodied50-execution-v3-20261102')),
                                   embodiment=SimpleNamespace(name='franka'))
        self.control_report={'engineering_reference_only':True};self.smooth=False
        self.matrix=rotation(1,math.radians(7.3))@np.diag([1.,-1.,-1.])
        self.position=np.array([0.,.13,.96]);self.held=False;self.blocked=False;self.calls=[]
        self.c=SimpleNamespace(snapshot=lambda:({'phone':dict(grasp=[self.held,False])},set()))
    def tip(self,side):return self.position.copy()
    def tcp_rotation_task(self,side):return self.matrix.copy()
    def finger_geometry(self,side):
        axis=self.matrix[:,1]
        return dict(source='actual_collision_mesh_current_body_pose',fingers=[
            dict(body_origin_task_m=(self.position+axis*.04).tolist()),dict(body_origin_task_m=(self.position-axis*.04).tolist())])
    def act(self,left,right,rotation_deg):
        self.calls.append((left,right,rotation_deg))
        labels={'ROLL_LEFT':(0,1),'ROLL_RIGHT':(0,-1),'PITCH_UP':(1,1),'PITCH_DOWN':(1,-1),'ROTATE_CCW':(2,1),'ROTATE_CW':(2,-1)}
        axis,sign=labels[left]
        if not self.blocked:self.matrix=rotation(axis,math.radians(rotation_deg*sign)*.9)@self.matrix


@pytest.mark.parametrize('task',['E08','E13'])
def test_removes_realistic_residual_tilt_with_public_rotations(task):
    a=Reference(task);level_empty_palm(a,'left',[0,1,0])
    assert a.calls and all(r=='STILL' and .5<=deg<=5 for _,r,deg in a.calls)
    assert a.matrix[2,2]<-math.cos(math.radians(.75))
    assert a.control_report['empty_palm_alignment']['native_grasp_validated'] is False


def test_actual_stall_is_not_target_completion():
    a=Reference();a.blocked=True
    with pytest.raises(RuntimeError,match='did not converge'):level_empty_palm(a,'left',[0,1,0])
    assert len(a.calls)==32


@pytest.mark.parametrize('change',[lambda a:setattr(a,'held',True),lambda a:a.position.__setitem__(2,.81)])
def test_refuses_loaded_or_table_level_rotation(change):
    a=Reference();change(a)
    with pytest.raises(RuntimeError):level_empty_palm(a,'left',[0,1,0])
    assert not a.calls


@pytest.mark.parametrize('change',[lambda a:a.scene.spec.update(id='E14'),lambda a:a.control_report.clear(),lambda a:setattr(a,'smooth',True),lambda a:setattr(a.scene.embodiment,'name','ur5_wsg')])
def test_other_tasks_profiles_and_formal_paths_untouched(change):
    a=Reference();change(a)
    with pytest.raises(ValueError):level_empty_palm(a,'left',[0,1,0])
    assert not a.calls


def test_real_acquire_stages_empty_e08_before_strict_palm_rotation(monkeypatch):
    from videoicl_isaaclab.realworld_tool_expert import ToolAuthor
    from videoicl_isaaclab import execution_design_tabletop_grasp as module
    # Exercise the production acquire caller with real helper ordering. This is
    # a command-routing test, not a synthetic native-grasp success certificate.
    a=Reference('E08');a.position[2]=.902
    a.scene.embodiment.config={'author_recording':{}}
    a.floor_clear_tcp=lambda side,**kwargs:.85
    a.align_gripper_axis=lambda side,axis:None
    a.finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=float(a.position[2]-.02))
    calls=[]
    p=SimpleNamespace(a=a,task='E08',spec=a.scene.spec,clearance=1.15,stage=lambda s:None,
        snapshot=lambda:({'shoe':dict(grasp=[False,False])},set()),
        tip=lambda side:a.position.copy(),point=lambda ref:np.array([0,.13,.86]),frame=lambda ref:(np.zeros(3),np.eye(3)),
        held=lambda ref,side:True,act=lambda *args,**kw:calls.append(('act',args)))
    def move(side,target):a.position=np.asarray(target,float);calls.append(('move',a.position.copy()))
    p.move=move
    def level(author,side,axis):
        assert author.position[2]>=.96 and author.finger_geometry(side)['lowest_z_task_m']>=.82
        calls.append(('level',author.position.copy()))
    monkeypatch.setattr(module,'level_empty_palm',level)
    from videoicl_isaaclab import execution_design_e08_approach
    def measured_approach(policy,side,ref):
        assert any(row[0]=='level' for row in calls)
        policy.move(side,policy.point(ref))
    monkeypatch.setattr(execution_design_e08_approach,'approach',measured_approach)
    ToolAuthor.acquire(p,{'actor':'shoe','jaw_axis_local':[0,1,0]},'left')
    index=next(i for i,row in enumerate(calls)if row[0]=='level')
    assert calls[index-1][0]=='move' and calls[index-1][1][2]==.96
    assert calls[-1][0]=='act' and calls[-1][1][1]=='GRASP'


def test_staging_target_without_actual_lift_cannot_bypass_floor_guard(monkeypatch):
    from videoicl_isaaclab import execution_design_tabletop_grasp as module
    a=Reference('E08');a.position[2]=.81;a.floor_clear_tcp=lambda side,**kwargs:.86
    a.finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=.79)
    p=SimpleNamespace(a=a,task='E08',snapshot=lambda:({'shoe':dict(grasp=[False,False])},set()),
       tip=lambda side:a.position.copy(),move=lambda *args:None)
    with pytest.raises(RuntimeError,match='actual fingers'):module.prepare_e08_empty_palm(p,'left',[0,1,0])


@pytest.mark.parametrize('lowest,passes',[(.814,True),(.8002,False),(float('nan'),False)])
def test_e08_actual_table_clearance_after_descent(lowest,passes):
    from types import SimpleNamespace
    from videoicl_isaaclab.execution_design_tabletop_grasp import require_e08_table_clearance
    a=SimpleNamespace(scene=SimpleNamespace(spec={'id':'E08','execution_design':{'revision':'embodied50-execution-v3-20261102'}}),control_report={'engineering_reference_only':True},finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=lowest))
    if passes:require_e08_table_clearance(a,'left')
    else:
        with pytest.raises(RuntimeError,match='clearance'):require_e08_table_clearance(a,'left')
