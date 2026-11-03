from types import SimpleNamespace
import pytest
import videoicl_isaaclab.execution_design_e08_pair as pair
import videoicl_isaaclab.execution_design_e08_branch as branch


def test_pair_native_readback_requires_both_original_released_supported_direction_conditions(monkeypatch):
    rows={a:dict(correct_label_direction=True,inside_original_cavity=True,actual_supported_in_box=True,native_grasp=[False,False],hand_force_n=0.)for a in('left_shoe','right_shoe')}
    monkeypatch.setattr(branch,'_native_landing_conditions',lambda p,c:rows[c['actor']])
    assert pair._native_pair(None)['all_original_conditions']
    rows['right_shoe']['inside_original_cavity']=False
    assert not pair._native_pair(None)['all_original_conditions']
    rows['right_shoe']['inside_original_cavity']=True;rows['left_shoe']['hand_force_n']=1.
    assert not pair._native_pair(None)['all_original_conditions']


def test_right_scope_cannot_use_left_checkpoint_entry_without_measured_com_context():
    with pytest.raises(ValueError,match='source shoe branch scope'):branch.run_branch(None,dict(actor='right_shoe'),'yaw_short_chunk')
    with pytest.raises(ValueError,match='COM acquisition'):branch.run_branch(None,dict(actor='right_shoe'),'yaw_short_chunk',_source_actor='right_shoe')


def test_actual_downward_drift_is_recovered_before_each_horizontal_payload_move(monkeypatch):
    import numpy as np
    import videoicl_isaaclab.execution_design_branch_geometry as geometry
    import videoicl_isaaclab.execution_design_thin_edge as material
    pos=np.array([-.025,.001,1.011]);lowest=[.9032];actions=[]
    monkeypatch.setattr(geometry,'install_public_guard',lambda *a:None)
    monkeypatch.setattr(geometry,'collision_parts_task',lambda *a:[np.array([[0.,0.,.91]])])
    monkeypatch.setattr(material,'material_collision_points_task',lambda *a:np.array([[0.,0.,lowest[0]]]))
    def act(side,token,mm):
        assert len(actions)<100
        if token=='UP':lowest[0]+=mm/1000;pos[2]+=mm/1000
        else:
            assert lowest[0]>=.935
            axis,sign={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1)}[token];pos[axis]+=sign*mm/1000
            lowest[0]-=.002;pos[2]-=.002
        actions.append(token)
    p=SimpleNamespace(tip=lambda s:pos.copy(),min_mm=.5,act=act);context={}
    pair.transport_above_rim(p,context,lambda:None,np.array([-.2,-.08]))
    assert actions[0]=='UP'and actions.count('UP')>3
    assert max(abs(pos[:2]-[-.2,-.08]))<=.002 and lowest[0]>=.935


def test_right_hard_q7_detour_keeps_clockwise_until_shortest_branch_is_unambiguous():
    import numpy as np
    def yaw(d):
        a=np.deg2rad(d);return np.array([[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1]])
    c=dict(right_yaw_detour_direction='CW')
    assert branch.right_clockwise_detour(c,yaw(80),yaw(180))==('ROTATE_CW',10.)
    assert branch.right_clockwise_detour(c,yaw(1),yaw(180))==('ROTATE_CW',10.)
    assert branch.right_clockwise_detour(c,yaw(-20),yaw(180))is None
    assert c['right_yaw_detour_complete']
    c=dict(right_yaw_detour_direction='CW')
    assert branch.right_clockwise_detour(c,yaw(177),yaw(180))is None
