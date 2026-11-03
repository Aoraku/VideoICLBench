"""Supported E18 uses the physically verified public three-millimetre pull."""
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e18_reference import E18MeasuredAuthor
from videoicl_isaaclab.execution_design_e18_support import VERSION,LIFT_M,SOURCE_SHA
from videoicl_isaaclab.realworld_mechanism_expert import MechanismExecutionError


def worker():
    w=E18MeasuredAuthor.__new__(E18MeasuredAuthor)
    w.task='E18';w.spec={'id':'E18','execution_design':{'revision':'embodied50-execution-v3-20261102'},
        'e18_support_layout':dict(version=VERSION,lift_m=LIFT_M,source_cabinet_sha256=SOURCE_SHA)}
    w.a=SimpleNamespace(control_report=dict(engineering_reference_only=True),
        scene=SimpleNamespace(embodiment=SimpleNamespace(config={})))
    w.c=SimpleNamespace(action_feedback=lambda:dict(control_feedback=dict(left={})))
    w._public_pull_observation=lambda role,side,phase:dict(bilateral_contact=w.touching(role,side,both=True),
        finger_q_m=[.0014,.0014],contact_forces_n=[1.,1.],tcp_axial_offset_m=.008,
        tcp_lateral_offset_m=.0003,action_step=0)
    return w


def test_only_reviewed_engineering_opening_gets_three_mm_public_steps():
    w=worker();assert w.drawer_public_step_m('drawer',False)==.003
    assert w.drawer_public_step_m('drawer',True)is None
    w.a.control_report['engineering_reference_only']=False
    assert w.drawer_public_step_m('drawer',False)is None
    w.a.control_report['engineering_reference_only']=True
    w.spec['e18_support_layout']['lift_m']=.03
    assert w.drawer_public_step_m('drawer',False)is None


def test_short_pull_keeps_bilateral_guard_and_never_chases_cartesian_residuals():
    w=worker();w.motion={'drawer':dict(open_distance=.006)}
    w.roles={'drawer':dict(closed_tolerance=.001,open_threshold=.005)}
    q=[0.];calls=[];contacts=[True]
    w.operations=[];w.acquire=lambda role:'left';w.stage=lambda _:None
    w.displacement=lambda role:q[0];w.axis=lambda role:np.array([-1.,0.,0.])
    w.touching=lambda role,side,both:contacts[0] and both
    w.retreat=lambda *args:None;w.orient=lambda *args,**kwargs:None
    w.move=lambda *args,**kwargs:pytest.fail('must use one public axis action, not6mm waypoint tracking')
    def act(side=None,token='STILL',**kwargs):
        calls.append((side,token,kwargs))
        if token=='BACK':q[0]+=.003
    w.act=act
    w.drawer('drawer')
    assert [(t,k['mm'])for _,t,k in calls if t=='BACK']==[('BACK',3.),('BACK',3.)]
    assert [token for _,token,_ in calls[:4]]==['GRASP','BACK','GRASP','BACK']
    assert w.operations[-1]['end']==pytest.approx(.006)
    q[0]=0.;calls.clear();contacts[0]=False
    with pytest.raises(MechanismExecutionError,match='contact absent'):w.drawer('drawer')
    assert calls==[]


def test_native_refusal_stops_the_first_short_drawer_action():
    w=worker();w.motion={'drawer':dict(open_distance=.006)}
    w.roles={'drawer':dict(closed_tolerance=.001,open_threshold=.005)}
    w.acquire=lambda role:'left';w.stage=lambda _:None
    w.displacement=lambda role:0.;w.axis=lambda role:np.array([-1.,0.,0.])
    w.touching=lambda role,side,both:True
    calls=[];w.act=lambda *args,**kwargs:calls.append((args,kwargs))
    w.c.action_feedback=lambda:dict(control_feedback=dict(left=dict(status='blocked')))
    with pytest.raises(MechanismExecutionError,match='controller rejected'):w.drawer('drawer')
    assert len(calls)==1
