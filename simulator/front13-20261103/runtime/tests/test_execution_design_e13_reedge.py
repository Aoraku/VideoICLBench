import itertools
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e13_reedge import finite_table_sweep,centered_face_plan,SIDE_ROTATION
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def box(lo,hi):return np.array(list(itertools.product(*zip(lo,hi))))
bounds=dict(lower=[-.35,-.6],upper=[.35,.6],top=.8)


def test_finite_table_permits_real_exterior_lower_finger_and_rejects_table_crossing():
    outside=box([-.39,-.2,.78],[-.352,-.16,.82]);origin=np.zeros(3)
    assert finite_table_sweep({'lower_finger':outside},origin,origin,np.eye(3),bounds)['actual_finite_table_fullhand_clear']
    with pytest.raises(ToolExecutionError,match='finite Table'):finite_table_sweep({'lower_finger':outside},origin,[.003,0,0],np.eye(3),bounds)
    with pytest.raises(ToolExecutionError):finite_table_sweep({'palm':box([-.36,-.2,.79],[-.34,-.16,.82])},origin,origin,np.eye(3),bounds)


def test_centered_face_plan_keeps_actual_com_supported_and_both_finger_clearance():
    yaw=-.76;r=np.array([[np.cos(yaw),-np.sin(yaw),0],[np.sin(yaw),np.cos(yaw),0],[0,0,1.]])
    rel=[box([-.10,-.04,.05],[.01,.04,.10]),box([-.02,-.01,.03],[.009,.01,.05]),box([-.02,-.01,-.05],[.009,.01,-.03])]
    plan=centered_face_plan([0,-.21,.805],r,[0,0,0],rel,bounds)
    assert plan['grasp_local'][1:]==[0.,0.]
    assert plan['grasp_local'][0]==-.065
    assert -.345<plan['translated_com'][0]<-.30
    assert plan['target_grasp'][0]<-.35-.001
    assert plan['planning_table_margin_m']>.001


def test_yawed_phone_contact_gap_uses_real_toe_section_and_keeps_true_overlap():
    from videoicl_isaaclab.execution_design_e13_reedge import sectional_contact_gap
    from videoicl_isaaclab.execution_design_e13_edge import trailing_contact_gap
    angle=np.pi/4;r=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1.]])
    phone=box([-.075,-.037,-.004],[.075,.037,.004])@r.T+[0,0,.805]
    toe=box([.061,-.002,.801],[.080,.002,.808]);axis=[-1.,0.,0.]
    assert trailing_contact_gap(phone,[toe],axis,.8)<-.001
    gap=sectional_contact_gap(phone,[toe],axis,.8);assert .001<gap<.020
    assert sectional_contact_gap(phone,[toe+[-.020,0,0]],axis,.8)<-.001
