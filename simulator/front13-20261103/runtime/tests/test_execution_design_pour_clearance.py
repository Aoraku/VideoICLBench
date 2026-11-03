import numpy as np
import pytest
import json
from pathlib import Path
from videoicl_isaaclab.execution_design_pour_clearance import minimum_rim_height,outlet_offset,move_clear_rim


def test_exterior_body_grip_preserves_source_geometry_and_avoids_wall_pinch():
    from types import SimpleNamespace
    from copy import deepcopy
    from videoicl_isaaclab.execution_design_pour_clearance import body_grip_reference
    obj=dict(id='cup',source_asset=dict(sha256='c9d82475379f3bc83666d97222a3c55a39f3334f97eb9ed02df4efab84183b5b'))
    p=SimpleNamespace(task='E45',a=SimpleNamespace(control_report={'engineering_reference_only':True}),
        spec={'objects':[obj]},s={'containers':{'cup':{'lower':[-.04,-.04,-.03872],'upper':[.04,.04,.044]}}})
    old=deepcopy(p.spec);ref={'actor':'cup','local':[-.036,0,.031],'jaw_axis_local':[1,0,0]}
    assert body_grip_reference(p,ref)['local']==[0.,0.,-.024]
    side=body_grip_reference(p,ref,-.010,[0.,-.008])
    assert side['local']==[0.,-.008,-.010]
    assert body_grip_reference(p,side,-.010)['local']==side['local']
    for offset in([.004,0.],[0.,.013],[0.,float('nan')]):
        with pytest.raises(ValueError):body_grip_reference(p,ref,-.010,offset)
    assert p.spec==old and ref['local']==[-.036,0,.031]
    p.task='E46'
    with pytest.raises(ValueError):body_grip_reference(p,ref)


def test_engineering_opposite_tilt_keeps_source_axis_and_source_spec():
    from types import SimpleNamespace
    from copy import deepcopy
    from videoicl_isaaclab.execution_design_pour_clearance import pour_token
    p=SimpleNamespace(task='E45',a=SimpleNamespace(control_report={'engineering_reference_only':True}),
        s={'tool_expert':{'pour_rotation_token':'PITCH_DOWN'}})
    source=deepcopy(p.s);assert pour_token(p)=='PITCH_DOWN'
    p._engineering_pour_token='PITCH_UP';assert pour_token(p)=='PITCH_UP'and p.s==source
    p._engineering_pour_token='ROLL_RIGHT'
    with pytest.raises(ValueError):pour_token(p)
    p._engineering_pour_token='PITCH_UP';p.a.control_report['engineering_reference_only']=False
    with pytest.raises(ValueError):pour_token(p)


def test_fixed_tcp_rotation_arc_is_bounded_along_with_recenter():
    meshes={'palm':np.array([[.1,0,0],[.1,.01,0]])};rim=[.04,0,.02]
    result=minimum_rim_height(meshes,rim,'PITCH_UP',.84,maximum_angle_deg=90)
    assert result['minimum_rim_z_m']>.908+.005
    assert result['includes_fixed_tcp_rotation_and_recenter']
    assert not result['geometry_modified']and not result['native_success_asserted']


def test_source_mesh_height_scan_matches_independent_dense_sweep():
    mesh=np.array([[-.12,0,-.05],[.01,.02,.01]]);rim=np.array([.04,0,.01]);result=minimum_rim_height({'hand':mesh},rim,'PITCH_DOWN',.84)
    # Original fixed 0.938m target is insufficient for a long tilted palm.
    assert result['minimum_rim_z_m']>.95
    assert result['margin_m']==.008


def test_missing_or_nonfinite_actual_mesh_never_produces_clearance():
    for meshes in ({},{'hand':[[float('nan'),0,0]]}):
        with pytest.raises(ValueError,match='mesh'):minimum_rim_height(meshes,[0,0,0],'PITCH_UP',.84)


def test_actual_v9_loaded_palm_rejects_old_rim_height_and_preserves_meshes():
    x=json.loads((Path(__file__).parent/'fixtures/e45_actual_loaded_v9_clearance.json').read_text())
    before=json.dumps(x,sort_keys=True)
    result=minimum_rim_height(x['meshes_relative_tcp'],x['rim_relative_tcp'],'PITCH_DOWN',x['receiver_top'])
    assert .999<result['minimum_rim_z_m']<1.001
    assert result['minimum_rim_z_m']>x['old_rim_target_z']+.06
    assert result['controlling_samples'][-1]['body']=='panda_hand'
    assert json.dumps(x,sort_keys=True)==before


def test_outflow_targets_low_source_lip_and_ball_centre_not_mouth_centre():
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    rotation=_axis_rotation([0,1,0],np.deg2rad(-135))
    offset=outlet_offset(rotation,'PITCH_DOWN',.041,.013)
    assert np.allclose(offset,[.054/np.sqrt(2),0.],atol=1e-10)


def test_higher_rim_does_not_force_palm_down_into_tray(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from videoicl_isaaclab import execution_design_e33_grasp as hand
    from videoicl_isaaclab import execution_design_thin_edge as material
    p=SimpleNamespace(a=SimpleNamespace(stage='pour',out=tmp_path,scene=SimpleNamespace(embodiment=SimpleNamespace(fingers=['f1','f2']))),
        s={'container':'tray'},c=SimpleNamespace(steps=0),point=lambda ref:np.array([0,0,1.04]),tip=lambda side:np.array([0,0,1.02]))
    p.act=lambda *a,**kw:pytest.fail('Already clear higher cup must not be driven down')
    monkeypatch.setattr(hand,'actual_mesh',lambda *args:np.array([[0,0,.86]]))
    monkeypatch.setattr(material,'material_collision_points_task',lambda policy,ref:np.array([[0,0,.84 if ref['actor']=='tray'else.90]]))
    move_clear_rim(p,'right',{'actor':'cup'},[0,0,1.],lambda:None)
