import math
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e13_camera import camera_entry
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def actual1337_rotation():
    # Rounded actual native camera and back vectors are reorthogonalized here.
    x=np.array([.28382895,-.95887099,-.00274888]);x/=np.linalg.norm(x)
    z=np.array([-.75811420,-.22615775,.61164984]);z-=x*float(z@x);z/=np.linalg.norm(z)
    return np.column_stack((x,np.cross(z,x),z))


def test_camera_entry_places_contact_at_camera_end_and_reverses_jaw_normal():
    r=actual1337_rotation();p=np.array([-.06849205,-.12728964,.83149210]);point,target=camera_entry(p,r)
    np.testing.assert_allclose((point-p-[0,0,.016])@r,[.085,.012,0],atol=1e-12)
    np.testing.assert_allclose(target.T@target,np.eye(3),atol=1e-12)
    assert np.linalg.det(target)>1-1e-12
    np.testing.assert_allclose(target[:,1],-r[:,2],atol=1e-12)
    assert -target[:,2]@r[:,0]==pytest.approx(math.cos(math.radians(30)),abs=.001)
    assert point[2]>.85


def test_camera_entry_refuses_unreviewed_portrait_and_improper_frames():
    with pytest.raises(ToolExecutionError):camera_entry([0,0,.9],np.eye(3))
    r=actual1337_rotation();r[:,0]*=-1
    with pytest.raises(ValueError):camera_entry([0,0,.9],r)
    with pytest.raises(ValueError):camera_entry([0,float('nan'),.9],actual1337_rotation())


def test_reacquire_refuses_to_replay_earlier_prefix_or_completed_lift():
    from videoicl_isaaclab.execution_design_e13_camera import _reacquire
    for phase in('empty_left_park','right_unpark_x','free_held_above_stand','lift_above_stand'):
        with pytest.raises(ValueError):_reacquire(None,dict(camera_end_strategy='actual_supported1337_right_camera_end_v1',camera_end_phase=phase),1500)


def test_finish_lift_dispatch_does_not_repeat_empty_route_or_grasp(monkeypatch):
    from types import SimpleNamespace
    import videoicl_isaaclab.execution_design_e13_branch as original
    import videoicl_isaaclab.execution_design_e13_camera as camera
    calls=[];p=SimpleNamespace(c=SimpleNamespace(steps=1500),variant='A',snapshot=lambda:({'phone':{'grasp':[False,True]}},[]),require_held=lambda ref,side:calls.append(('held',side)))
    monkeypatch.setattr(original,'_policy',lambda a,c:p)
    monkeypatch.setattr(camera,'AcquisitionGeometry',lambda *a,**k:'right-held-guard')
    monkeypatch.setattr(camera,'install_public_guard',lambda *a:calls.append(('guard',a[1])))
    monkeypatch.setattr(camera,'_finish_lift',lambda *a:dict(lift_only=True))
    monkeypatch.setattr(camera,'camera_entry',lambda *a,**k:pytest.fail('Repeated empty entry'))
    result=camera.run_branch(None,dict(camera_end_strategy='actual_supported1337_right_camera_end_v1',camera_end_phase='lift_above_stand'),'camera_end_finish_lift')
    assert result==dict(lift_only=True)
    assert calls==[('held','right'),('guard','right-held-guard')]


def test_phone_envelope_keeps_every_actual_cooked_vertex_and_logs_native_evidence(monkeypatch,tmp_path):
    from types import SimpleNamespace
    import hashlib,json,itertools
    import videoicl_isaaclab.execution_design_e13_camera as camera
    parts=[np.array(list(itertools.product([-.075,.075],[-.037,.037],[z])))for z in(-.0047,.0047)]
    monkeypatch.setattr(camera,'collision_parts_task',lambda *args:parts)
    p=SimpleNamespace(spec=dict(objects=[dict(id='phone',source_asset=dict(sha256='877328ef32ace63e63f7ed3c60de990f5f3532a17208e1e74143bfb794c7f6bb'))]),a=SimpleNamespace(out=tmp_path),frame=lambda ref:(np.zeros(3),np.eye(3)),_camera_context={})
    envelope=camera.closed_phone_obstacle(p)
    np.testing.assert_array_equal(envelope[0],np.concatenate(parts))
    raw=(tmp_path/'camera-phone-cooked-envelope.private.json').read_bytes();data=json.loads(raw)
    assert data['actual_piece_count']==2 and not data['source_geometry_modified']
    assert hashlib.sha256(raw).hexdigest()==p._camera_context['actual_phone_cooked_envelope_evidence']['sha256']
    from videoicl_isaaclab.execution_design_branch_geometry import swept_pose_clearance
    palm=np.array(list(itertools.product([.105,.15],[-.03,.03],[.1,.2])))
    proof=camera.phone_sweep_separation({'palm':palm},[0,0,.2],[0,0,.01],np.eye(3),envelope[0],np.eye(3))
    assert proof['bodies']['palm']['expanded_separation_m']>.02
    swept_pose_clearance({'palm':palm},[0,0,.2],[0,0,.1],np.eye(3),{'phone':envelope},-.2)
    with pytest.raises(ToolExecutionError):swept_pose_clearance({'palm':envelope[0]},[0,0,0],[0,0,0],np.eye(3),{'phone':envelope},-.2)


def test_native1559_resume_retires_initial_contact_without_repeating_release(monkeypatch):
    from types import SimpleNamespace
    import videoicl_isaaclab.execution_design_e13_camera as camera
    import videoicl_isaaclab.execution_design_contact_retreat as retreat
    calls=[]
    p=SimpleNamespace(variant='A',s=dict(stand='stand'),contact=lambda *a:True,
        act=lambda *a,**k:pytest.fail('Native1559 is already released'),tip=lambda s:np.array([0.,0.,1.]))
    class StopAtRaise(Exception):pass
    class Geometry:
        def move(self,target):
            calls.append(('raise',target.tolist()));raise StopAtRaise
    monkeypatch.setattr(retreat,'retreat_phone_contact',lambda *args:calls.append('retreat'))
    monkeypatch.setattr(camera,'AcquisitionGeometry',lambda *a,**k:Geometry())
    monkeypatch.setattr(camera,'install_public_guard',lambda *a:None)
    context=dict(camera_end_strategy='actual_supported1337_right_camera_end_v1',camera_end_phase='inset_raise',
        camera_end_first_actual_hold_action=1548,camera_end_previous_actual_hold_actions=[1548])
    with pytest.raises(StopAtRaise):camera._inset_regrasp(p,context,1559)
    assert calls==['retreat',('raise',[0.,0.,1.024])]
    assert context['camera_end_previous_actual_hold_actions']==[1548]
