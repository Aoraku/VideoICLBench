import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e34_reference import pad_capture,placement,scope
from videoicl_isaaclab.execution_design import REVISION_V3


def test_recorded_stalled_tcp_already_has_material_between_real_open_pads():
    d=json.loads((Path(__file__).parent/'fixtures/e34b_actual_open_pad_capture.json').read_text())
    assert np.linalg.norm(np.array(d['tcp'])-d['virtual_tcp_goal'])>.004
    assert pad_capture(d['point'],d['meshes'],d['floor'])
    # Passing a virtual waypoint is insufficient when the real material lies
    # beyond the pads, below their toes, or against the table.
    for shift in ([.025,0,0],[0,.1,0],[0,0,-.003]):
        assert not pad_capture(np.array(d['point'])+shift,d['meshes'],d['floor'])
    assert not pad_capture(d['point'],d['meshes'],d['floor']+.01)


def author(rotation=np.eye(3)):
    state={'fork':dict(pos=np.array([.1,.2,1.]),mat=rotation,grasp=[False,True]),'tray':dict(pos=np.array([.02,.12,.82]),mat=np.eye(3),grasp=[False,False])}
    semantic=dict(container='tray',handle_points={'fork':[-.08,0,0]},compartment_bounds_local=dict(lower=[.005,.005,-.012],upper=[.098,.076,.019]))
    spec=dict(id='E34',execution_design=dict(revision=REVISION_V3),objects=[dict(id='fork',size=[.09,.012,.008])],semantic=semantic)
    a=SimpleNamespace(_execution_design_reference_authorized=True,scene=SimpleNamespace(spec=spec),c=SimpleNamespace(snapshot=lambda:(state,set()),steps=1),tip=lambda side:np.array([.1,.2,1.03]))
    return a,state


def test_handle_goal_uses_live_container_and_fits_true_compartment(tmp_path):
    a,state=author();a.out=tmp_path
    tcp=placement(a,'fork','right',{})
    offset=a.tip('right')-(state['fork']['pos']+state['fork']['mat']@[-.08,0,0])
    handle=tcp-offset
    assert np.allclose(handle[:2],[.0715,.1605])
    assert .82-.012<=handle[2]<=.82+.019
    state['tray']['pos'][0]+=.03
    assert np.allclose(placement(a,'fork','right',{})[:2]-tcp[:2],[.03,0])


def test_recorded_30_degree_handle_cannot_be_marked_ready(tmp_path):
    angle=np.deg2rad(30);rotation=np.array([[np.cos(angle),0,np.sin(angle)],[0,1,0],[-np.sin(angle),0,np.cos(angle)]])
    a,_=author(rotation);a.out=tmp_path
    with pytest.raises(RuntimeError,match='height cannot fit'):placement(a,'fork','right',{})


def test_reference_scope_does_not_change_other_tasks():
    a,_=author();a.scene.spec['id']='E27'
    with pytest.raises(ValueError):scope(a)
