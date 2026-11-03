"""First bilateral contact must not authorize a pull during fast closure."""
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e18_reference import E18MeasuredAuthor
from videoicl_isaaclab.realworld_mechanism_expert import _Author,MechanismExecutionError


def worker(monkeypatch,samples):
    monkeypatch.setattr(_Author,'acquire',lambda self,role,closing_push=False:'left')
    w=E18MeasuredAuthor.__new__(E18MeasuredAuthor)
    data=SimpleNamespace(joint_pos=np.zeros((1,2)),joint_vel=np.zeros((1,2)))
    robot=SimpleNamespace(data=data,find_joints=lambda pattern:([0,1],['panda_finger_joint1','panda_finger_joint2']))
    w.a=SimpleNamespace(scene=SimpleNamespace(robots={'left':robot}));w.operations=[];w.calls=[]
    w.stage=lambda name:None
    samples=iter(samples)
    def act(side,token):
        q,v,contact=next(samples);data.joint_pos[:]=q;data.joint_vel[:]=v;w.contact=contact;w.calls.append(token)
    w.act=act;w.touching=lambda role,side,both=False:w.contact and both
    return w


def test_transient_touch_waits_for_three_measured_stable_samples(monkeypatch):
    w=worker(monkeypatch,[(.008,.03,True),(.007,.001,True),(.007,0.,True),(.007,0.,True)])
    assert w.acquire('drawer')=='left'
    assert w.calls==['GRASP']*4
    assert len(w.operations)==4


@pytest.mark.parametrize('sample',[(.001,0.,True),(.007,0.,False),(float('nan'),0.,True)])
def test_lost_or_empty_or_invalid_closure_never_authorizes_pull(monkeypatch,sample):
    w=worker(monkeypatch,[sample])
    with pytest.raises(MechanismExecutionError):w.acquire('drawer')
    assert w.calls==['GRASP']


def test_unsettled_closure_is_bounded_without_pull(monkeypatch):
    w=worker(monkeypatch,[(.007,.01,True)]*8)
    with pytest.raises(MechanismExecutionError,match='did not settle'):w.acquire('drawer')
    assert w.calls==['GRASP']*8


def test_panel_push_does_not_require_a_tensile_grip(monkeypatch):
    w=worker(monkeypatch,[])
    assert w.acquire('drawer',closing_push=True)=='left'
    assert not w.calls


def test_explicit_local_short_pull_uses_one_actual_contact_without_extra_grasp_actions(monkeypatch):
    from videoicl_isaaclab.execution_design import REVISION_V3
    w=worker(monkeypatch,[])
    w._engineering_single_handle_observation=True
    w.spec={'execution_design':{'revision':REVISION_V3}}
    w.a.control_report={'engineering_reference_only':True}
    w.a.scene.spec={'e18_support_layout':{'lift_m':.035}}
    robot=w.a.scene.robots['left'];robot.data.joint_pos[:]=.0014;robot.data.joint_vel[:]=.03;w.contact=True
    assert w.acquire('drawer')=='left'
    assert w.calls==[] and len(w.operations)==1
    assert w.operations[0]['engineering_grip_gate']=='single_bilateral_nonempty_observation'
