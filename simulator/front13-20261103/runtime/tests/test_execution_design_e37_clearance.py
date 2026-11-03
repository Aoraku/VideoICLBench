"""The E37 author must not rotate a held driver against the real tabletop."""
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.realworld_structural_expert import StructuralAuthor
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError

class ReachedRotation(Exception):pass


def author(v3=True,engineering=True,table_after_lift=False):
    a=StructuralAuthor.__new__(StructuralAuthor)
    a.spec={'execution_design':{'revision':'embodied50-execution-v3-20261102' if v3 else 'legacy'}}
    a.a=SimpleNamespace(scene=SimpleNamespace(embodiment=SimpleNamespace(config={})),control_report={'engineering_reference_only':engineering})
    a.index=0;a.clearance=1.12;a.geometry={'driver_grasp':{'local':[0,0,0],'jaw_axis_local':[0,1,0]}}
    a.s={'screw_roles':{'left':{'driver':{'actor':'driver','axis_local':[1,0,0],'tip_local':[.1,0,0]},'fixture':{'ref':{},'axis_local':[0,0,1]},'screw':'screw','head_socket_local':[0,0,0]}}}
    a.calls=[];a.z=.83
    a.acquire=lambda ref,side:a.calls.append('real-grasp')
    a.stage=lambda stage:a.calls.append(stage)
    a.tip=lambda side:np.array([0,0,a.z])
    a.require_held=lambda ref,side:a.calls.append('grasp-guard')
    def move(side,target,guard):
        guard();a.z=target[2];a.calls.append('real-lift')
    a.move=move;a.contact=lambda n,s:table_after_lift
    a.frame=lambda ref:(np.zeros(3),np.eye(3))
    def rotate(*args):a.calls.append('rotate');raise ReachedRotation
    a.align_axis=rotate
    return a


def test_v3_engineering_lifts_with_grip_guard_before_rotation(monkeypatch):
    a=author()
    monkeypatch.setattr('videoicl_isaaclab.execution_design_e37_approach.above_head',lambda *args:a.align_axis())
    with pytest.raises(ReachedRotation):a.screws()
    assert a.z>=1.12
    assert a.calls.index('grasp-guard')<a.calls.index('real-lift')<a.calls.index('rotate')


def test_remaining_table_collision_fails_before_rotation():
    a=author(table_after_lift=True)
    with pytest.raises(ToolExecutionError,match='still contacts table'):a.screws()
    assert 'rotate' not in a.calls


@pytest.mark.parametrize('v3,engineering',[(False,True),(True,False)])
def test_legacy_and_non_engineering_paths_unchanged(v3,engineering):
    a=author(v3,engineering)
    with pytest.raises(ReachedRotation):a.screws()
    assert 'real-lift'not in a.calls


@pytest.mark.parametrize('deadband,slow_ik',[(0.,False),(3.5,False),(0.,True)])
def test_driver_transits_before_rotation_without_chasing_arbitrary_tcp_anchor(tmp_path,deadband,slow_ik):
    from videoicl_isaaclab.execution_design_e37_approach import above_head
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    a=SimpleNamespace(a=SimpleNamespace(out=tmp_path),c=SimpleNamespace(steps=0))
    a.tcp=np.array([-.18,-.25,1.10]);a.mat=np.eye(3);calls=[]
    if slow_ik:a.c.action_feedback=lambda:{'control_feedback':{'right':dict(status='blocked',reason='no_safe_ik_step',joint_limit_names=[])}}
    a.tip=lambda side:a.tcp.copy();a.stage=lambda name:calls.append(('stage',name))
    a.require_held=lambda *args:None;a.contact=lambda *args:False
    a.spec={'objects':[{'id':'driver','size':[.02,.01,.01]}]}
    a.a.finger_geometry=lambda side:{'lowest_z_task_m':a.tcp[2]-.02}
    a.snapshot=lambda:({'driver':{'mat':a.mat,'pos':a.tcp},'screw':{'mat':np.eye(3)}},set())
    def move(side,target,guard,tolerance=.002):
        guard();assert tolerance==.005
        a.tcp=np.asarray(target).copy();calls.append(('move',a.tcp.copy()))
    def act(side,token,degrees=None,mm=None):
        if token=='UP':
            assert degrees is None and 0<mm<=12
            a.tcp[2]+=mm/1000;a.c.steps+=1;calls.append(('raise',mm));return
        assert 0<degrees<=8
        axis=0 if token.startswith('ROLL')else 1 if token.startswith('PITCH')else 2
        sign=1 if token in ('ROLL_LEFT','PITCH_UP','ROTATE_CCW')else -1
        a.mat=_axis_rotation(np.eye(3)[axis],np.radians((min(.43,degrees)if slow_ik else max(0.,degrees-deadband))*sign))@a.mat
        a.tcp[2]-=(.001 if slow_ik else .012)*(degrees/8);a.c.steps+=1;calls.append(('rotate',token))
    a.move=move;a.act=act
    above_head(a,{'actor':'driver'},'right',{'actor':'driver'},
               {'screw':'screw','radial_local':[1,0,0]},[0,0,1],lambda:np.array([.06,.07,.8525]))
    first_move=next(x[1]for x in calls if x[0]=='move')
    assert np.allclose(first_move,[.06,.07,1.10])
    assert len([x for x in calls if x[0]=='move'])==1
    assert abs(a.tcp[2]-1.10)>.006
    assert min(a.tcp[2]-.02,a.tcp[2]-.02)>.8625
    assert len([x for x in calls if x[0]=='rotate'])<300
    if slow_ik:
        import json
        data=json.loads((tmp_path/'E37-head-orientation.private.json').read_text())
        assert len([x for x in calls if x[0]=='rotate'])>120
        assert all(x.get('estimated_rotation_loss_degrees',0.)== 0. for x in data['history'])
    if deadband:assert any(x[0]=='raise'for x in calls)
    assert (a.mat[:,0]@np.array([0,0,-1]))>.9999
    assert (tmp_path/'E37-head-orientation.private.json').exists()
