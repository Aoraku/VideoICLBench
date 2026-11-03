from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e28_contact_guard import ensure_contact
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def setup(tmp_path,recover=True):
    normal=np.array([.310511,.003563,.950563]);normal/=np.linalg.norm(normal);size=np.array([.017,.025,.007]);x=.131
    z=(.0308164+np.abs(normal)@size+.0003-normal[0]*x)/normal[2]
    tool=dict(actor='blade',support_bounds={'lower':[.070,-.037,-.014],'upper':[.125,.037,.014]},support_normal_local=normal.tolist(),support_plane_offset=.0308164)
    state={'blade':dict(pos=np.zeros(3),mat=np.eye(3)),'food':dict(pos=np.array([x,0.,z]),mat=np.eye(3),grasp=[False,False])}
    c=SimpleNamespace(steps=0,physics_ticks=0,contact=True,hand=False);actions=[]
    p=SimpleNamespace(c=c,spec={'id':'E28','seed':4201,'objects':[dict(id='food',size=size)],'execution_design':{'condition':'I','revision':'embodied50-execution-v3-20261102'}},
        a=SimpleNamespace(stage='carry',out=tmp_path,control_report={'engineering_reference_only':True}),snapshot=lambda:(state,set()))
    p.contact=lambda food,other:c.contact if other=='blade'else c.hand if 'finger'in other else False
    def act():actions.append('STILL/STILL');c.steps+=1;c.physics_ticks+=100;c.contact=recover
    p.act=act;p.stage=lambda name:setattr(p.a,'stage',name)
    return p,tool,state,actions


def test_native_contact_must_really_return_after_the_one_public_wait(tmp_path):
    p,t,state,actions=setup(tmp_path)
    ensure_contact(p,'food',t,lambda:None);p.c.contact=False
    assert ensure_contact(p,'food',t,lambda:None)['recovered']
    assert p.c.contact and actions==['STILL/STILL']and p.a.stage=='carry'


def test_failed_contact_waits_are_bounded_and_cannot_manufacture_support(tmp_path):
    p,t,state,actions=setup(tmp_path,recover=False)
    ensure_contact(p,'food',t,lambda:None);p.c.contact=False
    for _ in range(3):
        with pytest.raises(ToolExecutionError,match='did not recover actual'):
            ensure_contact(p,'food',t,lambda:None)
    with pytest.raises(ToolExecutionError,match='near-plane recovery'):
        ensure_contact(p,'food',t,lambda:None)
    assert actions==['STILL/STILL']*3 and not p.c.contact


def test_real_separation_is_not_relabelled_as_contact_flicker(tmp_path):
    p,t,state,actions=setup(tmp_path);ensure_contact(p,'food',t,lambda:None)
    p.c.contact=False;state['food']['pos'][2]+=.005
    with pytest.raises(ToolExecutionError,match='near-plane recovery'):
        ensure_contact(p,'food',t,lambda:None)
    assert actions==[]


def test_food_hand_contact_prevents_any_recovery_wait(tmp_path):
    p,t,state,actions=setup(tmp_path);ensure_contact(p,'food',t,lambda:None);p.c.contact=False;p.c.hand=True
    with pytest.raises(ToolExecutionError,match='touched a robot hand'):
        ensure_contact(p,'food',t,lambda:None)
    assert actions==[]


def test_real_supported_slide_does_not_add_an_author_com_motion_gate(tmp_path):
    p,t,state,actions=setup(tmp_path);ensure_contact(p,'food',t,lambda:None)
    p.c.contact=False;normal=np.asarray(t['support_normal_local']);state['food']['pos']+=np.array([.0016,0.,-.0016*normal[0]/normal[2]])
    assert ensure_contact(p,'food',t,lambda:None)['actual_contact']
    assert actions==['STILL/STILL']


def test_yaw_on_the_blade_is_not_a_final_settle_orientation_gate(tmp_path):
    p,t,state,actions=setup(tmp_path);ensure_contact(p,'food',t,lambda:None)
    angle=np.radians(30.);c,s=np.cos(angle),np.sin(angle);rotation=np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])
    state['food']['mat']=rotation;normal=np.asarray(t['support_normal_local']);size=np.asarray(p.spec['objects'][0]['size'])
    state['food']['pos'][2]=(.0308164+np.abs(rotation.T@normal)@size+.0003-normal[0]*state['food']['pos'][0])/normal[2]
    p.c.contact=False
    assert ensure_contact(p,'food',t,lambda:None)['actual_contact']
    assert actions==['STILL/STILL']
