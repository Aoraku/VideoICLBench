from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_e37_handoff as transfer


def policy(tmp_path,unstable=False):
    p=SimpleNamespace(spec={'objects':[dict(id='driver',source_asset={'sha256':transfer.SOURCE})]},
        a=SimpleNamespace(out=tmp_path),hands={'right':True,'left':False},positions={'right':np.array([0.,0.,1.06]),'left':np.array([0.,0.,1.])},calls=[],closures=0)
    p.a.finger_geometry=lambda side:dict(fingers=[{'body_origin_task_m':[0.,0.,1.]},{'body_origin_task_m':[0.,0.,0.]}])
    p.snapshot=lambda:({'driver':dict(mat=np.eye(3),grasp=[p.hands['left'],p.hands['right']])},set())
    p.point=lambda ref:np.array([0.,0.,1.]);p.tip=lambda side:p.positions[side].copy()
    p.contact=lambda *args:False;p.stage=lambda name:None;p.held=lambda ref,side:p.hands[side]
    def held(ref,side):
        if not p.hands[side]:raise transfer.ToolExecutionError('lost grip')
    p.require_held=held
    def move(side,target,guard):guard();p.positions[side]=np.array(target);guard()
    p.move=move
    def act(side,token,**kw):
        p.calls.append((side,token))
        if token=='RELEASE':
            if side=='right':assert p.hands['left']and p.closures>=3
            p.hands[side]=False
        elif token=='GRASP':
            p.closures+=1;p.hands[side]=not unstable or p.closures%2==1
        else:
            axis,sign={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}[token]
            p.positions[side][axis]+=sign*kw['mm']/1000.
    p.act=act
    return p


def test_real_transfer_keeps_outgoing_closed_until_three_incoming_grips(tmp_path):
    p=policy(tmp_path);ref,side=transfer.handoff(p,{'actor':'driver'})
    assert side=='left'and ref['local']==transfer.POINT
    assert p.closures==3 and p.hands=={'left':True,'right':False}
    assert p.calls.index(('right','RELEASE'))>max(i for i,c in enumerate(p.calls)if c==('left','GRASP'))


def test_unstable_incoming_grip_never_releases_outgoing_driver(tmp_path):
    p=policy(tmp_path,unstable=True)
    with pytest.raises(transfer.ToolExecutionError,match='stable actual'):transfer.handoff(p,{'actor':'driver'})
    assert ('right','RELEASE')not in p.calls and p.hands['right']


def test_material_progress_rejects_sideways_drift_while_target_stays_far():
    point=np.zeros(3);calls=[]
    p=SimpleNamespace(max_mm=10.,point=lambda ref:point.copy())
    def act(side,token,**kwargs):
        calls.append(token);point[:]+=np.array([.0002,.001,0.])
    p.act=act
    with pytest.raises(transfer.ToolExecutionError,match='20-action progress'):
        transfer.move_tip(p,'right',{},[.2,0.,0.],lambda:None)
    assert len(calls)<60


def test_side_handoff_keeps_palm_lateral_to_outgoing_vertical_shaft():
    body=np.array([[0.,0.,1.],[0.,1.,0.],[-1.,0.,0.]])
    frame=transfer.side_approach_frame(body,[1.,0.,0.])
    assert np.allclose(frame.T@frame,np.eye(3))and np.linalg.det(frame)>.999
    assert frame[1,2]<-.99 and frame[:,1]@body[:,2]>.99
    # The palm lies behind its finger tips, outside the outgoing upper hand.
    assert (-.10*frame[:,2])[1]>.099


def test_equivalent_jaw_assignment_keeps_same_lateral_palm_lane():
    body=np.array([[0.,0.,1.],[0.,1.,0.],[-1.,0.,0.]])
    first=transfer.side_approach_frame(body,[1.,0.,0.],jaw_sign=1)
    second=transfer.side_approach_frame(body,[1.,0.,0.],jaw_sign=-1)
    assert np.allclose(first[:,2],second[:,2])
    assert np.allclose(first[:,:2],-second[:,:2])
    assert first[1,2]<-.99 and np.linalg.det(second)>.999


def test_actual_failed_side_wrist_has_a_continuous_equivalent_escape():
    from pathlib import Path
    import json
    from videoicl_isaaclab.execution_design_e31_continuation import screen
    case=json.loads((Path(__file__).parent/'fixtures/e37_actual_side_branch_before_rotation.json').read_text())
    assert case['actual_fk_position_error_m']<1e-6
    measured=case['measured']
    rejected=screen(measured,[dict(position=measured['position'],rotation=case['targets'][0])],margin=.04)
    accepted=screen(measured,[dict(position=measured['position'],rotation=case['targets'][1])],margin=.04)
    assert not rejected['passed']
    assert accepted['passed']and accepted['minimum_joint_margin_rad']>.5
    assert accepted['samples'][-1]['candidate_joints_rad'][6]<.5
