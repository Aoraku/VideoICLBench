import itertools
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e08_midfoot import midfoot_section
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def shoe_face():
    # Sole width88mm exceeds Panda opening; the upper section narrows to60mm.
    return np.array([[x,y,z]for z,width in[(-.05,.044),(.05,.022)]for x,y in itertools.product([-.13,.13],[-width,width])])


def test_midfoot_uses_actual_com_x_and_full_pad_band_above_com():
    result=midfoot_section(shoe_face(),[-.018,.001,-.010])
    assert result['grasp_local'][0]==pytest.approx(-.018)
    assert .055<result['conservative_source_section_width_m']<.070
    assert result['panda_opening_residual_m']>.010
    assert result['grasp_above_com_m']==pytest.approx(.030)
    assert result['native_grasp_not_yet_verified']


def test_midfoot_refuses_a_shoe_too_wide_and_unstable_com():
    wide=np.array(list(itertools.product([-.13,.13],[-.045,.045],[-.05,.05])))
    with pytest.raises(ToolExecutionError):midfoot_section(wide,[0,0,0])
    with pytest.raises(ToolExecutionError):midfoot_section(shoe_face(),[0,0,.03])
def test_measured_table_departure_payload_can_only_lift_up_and_never_waives_hand_clearance(monkeypatch):
    import itertools
    import pytest
    from types import SimpleNamespace
    import videoicl_isaaclab.execution_design_e33_grasp as source
    import videoicl_isaaclab.execution_design_thin_edge as thin
    import videoicl_isaaclab.execution_design_branch_geometry as geometry
    from videoicl_isaaclab.execution_design_e08_midfoot import SoleAcquisitionGeometry
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    def box(lo,hi):return np.array(list(itertools.product(*zip(lo,hi))))
    hand=box([-.02,-.02,.881],[.02,.02,.94]);payload=box([-.1,-.04,.79998479],[.1,.04,.87]);tip=np.array([0.,0.,.9]);bad_hand=[False]
    monkeypatch.setattr(source,'actual_mesh',lambda a,s,n:(hand-[0,0,.082]if bad_hand[0]else hand)if s=='right'else hand+[2,2,2])
    monkeypatch.setattr(thin,'table_bounds_task',lambda *a:dict(top=.8))
    monkeypatch.setattr(thin,'material_collision_points_task',lambda *a:payload)
    monkeypatch.setattr(geometry,'collision_parts_task',lambda *a:[payload])
    p=SimpleNamespace(a=SimpleNamespace(scene=SimpleNamespace(embodiment=SimpleNamespace(fingers=['panda_leftfinger','panda_rightfinger']))),tip=lambda s:tip,snapshot=lambda:({'right_shoe':dict(grasp=[False,True])},set()),require_held=lambda *a:None,contact=lambda *a:False)
    with pytest.raises(ToolExecutionError,match='table clearance'):SoleAcquisitionGeometry(p,'right_shoe','right',mode='held').check()
    g=SoleAcquisitionGeometry(p,'right_shoe','right',mode='held',allow_table_departure=True)
    assert g.check(target=tip+[0,0,.012])['payload_table_departure']
    # Native134 first-UP tilted the supported shoe by .742mm while all hand
    # meshes remained >89mm above Table; this is legal source contact exit.
    payload[:,2]-=.00075
    assert g.check(target=tip+[0,0,.012])['payload_table_departure']
    payload[:,2]-=.002
    with pytest.raises(ToolExecutionError,match='sank over2mm'):g.check(target=tip+[0,0,.012])
    payload[:,2]+=.00275
    with pytest.raises(ToolExecutionError,match='only public UP'):g.check(target=tip+[.004,0,0])
    bad_hand[0]=True
    with pytest.raises(ToolExecutionError,match='table clearance'):g.check(target=tip+[0,0,.012])
