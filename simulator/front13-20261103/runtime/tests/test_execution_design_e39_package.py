import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e39_package import palm_clear_contact
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def meshes():
    tcp=np.array([.17,.30,.845])
    palm=tcp+np.array([[-.097,-.10,.01577],[-.015,.104,.0974]])
    fingers=[tcp+np.array([[-.039,-.027,-.0107],[.011,-.001,.0391]]),
             tcp+np.array([[-.039,.001,-.0107],[.011,.027,.0391]])]
    return tcp,palm,fingers


def test_palm_clearance_raises_contact_height_above_closed_cover():
    tcp,palm,fingers=meshes()
    p=palm_clear_contact(tcp,palm,fingers,.878,.8,.872,1,-1)
    assert p['tcp_z']==pytest.approx(.86623)
    assert p['palm_clearance_m']==pytest.approx(.004)
    assert p['leading_offset']==pytest.approx(-.027)
    assert p['wall_overlap_m']>.006


def test_actual_closed_finger_offset_is_not_tcp_or_open_finger_assumption():
    tcp,palm,fingers=meshes()
    p=palm_clear_contact(tcp,palm,fingers,.878,.8,.872,1,1)
    assert p['leading_offset']==pytest.approx(.027)
    assert p['leading_offset']!=pytest.approx(.0664)


def test_reject_palm_clear_height_above_wall_contact_range():
    with pytest.raises(ToolExecutionError,match='overlap'):
        palm_clear_contact(*meshes(),1.05,.8,.872,1,-1)


def test_reject_nonfinite_contact_geometry():
    tcp,palm,fingers=meshes();palm[0,2]=np.nan
    with pytest.raises(ToolExecutionError,match='geometry'):
        palm_clear_contact(tcp,palm,fingers,.878,.8,.872,1,-1)


def test_closed_mesh_preview_is_actual_prismatic_translation_not_pose_assignment():
    from videoicl_isaaclab.execution_design_e39_package import forecast_closed_meshes
    palm=np.array([[0,0,.1],[.01,0,.11],[0,.01,.1],[0,0,.11]])
    left=palm+[0,.04,-.05];right=palm+[0,-.04,-.05]
    meshes=forecast_closed_meshes([0,0,0],palm,[left,right],[0,1,0],[.04,.04],[0,0])
    assert np.allclose(meshes[1],left-[0,.04,0])
    assert np.allclose(meshes[2],right+[0,.04,0])
    assert np.allclose(meshes[0],palm) and np.allclose(left,palm+[0,.04,-.05])


def test_neutral_lid_checkpoint_does_not_repeat_bad_combined_turn(monkeypatch):
    from videoicl_isaaclab import execution_design_e39_package as module
    calls=[]
    monkeypatch.setattr(module,'_authorized',lambda p:None)
    monkeypatch.setattr(module,'_empty',lambda *a,**k:None)
    monkeypatch.setattr(module,'push_rotation',lambda *a,**k:'native-canonical-down')
    monkeypatch.setattr(module,'preflight_empty_orientation',lambda p,s,r:calls.append(('screen',r)))
    monkeypatch.setattr(module,'orient_empty',lambda p,s,r:calls.append(('turn',r)))
    monkeypatch.setattr(module,'preflight_lid_phase',lambda p:calls.append('rescreen-after-native-turn'))
    monkeypatch.setattr(module,'_log',lambda *a,**k:None)
    module.prepare_lid_from_empty_checkpoint(object(),force_neutral=True)
    assert calls==[('screen','native-canonical-down'),('turn','native-canonical-down'),'rescreen-after-native-turn']
