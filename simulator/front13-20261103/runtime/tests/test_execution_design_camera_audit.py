from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_camera_audit import camera_audit,VIEWS


def fixture():
    m=np.eye(4);m[:3,3]=[0,0,1.7];m[:3,:3]=np.diag([1,-1,-1])
    scene=SimpleNamespace(spec={'head_view':dict(eye_task=[0,0,1.7],target_task=[0,0,.8])},
        rgb_camera_calibration=lambda name:dict(available=True,T_world_from_camera_optical=m.tolist(),T_task_from_camera_optical=m.tolist()))
    images={n:np.zeros((16,16,3),dtype=np.uint8)for n in VIEWS}
    images['head'][:8,:,0]=255
    return scene,images,m


def test_two_occluded_wrists_do_not_reject_valid_head_view():
    scene,images,_=fixture();d=camera_audit(scene,images)
    assert d['admission_passed'] and d['views']['left_wrist']['near_uniform_gray']
    assert d['views']['head']['actual_view_axis_error_deg']==0
    assert d['visual_acceptance']=='requires_content_review'


def test_entire_gray_set_is_rejected_without_touching_physics_or_calibration():
    scene,images,m=fixture();images={n:np.full((16,16,3),180,np.uint8)for n in VIEWS}
    before=m.copy();d=camera_audit(scene,images)
    assert not d['admission_passed'] and d['physics_changed']is False
    assert 'All three' in d['errors'][0]
    np.testing.assert_array_equal(m,before)


@pytest.mark.parametrize('defect',['origin','axis','unavailable','nonfinite'])
def test_actual_camera_transform_not_just_authored_intent_is_required(defect):
    scene,images,m=fixture()
    if defect=='origin':m[0,3]+=8
    elif defect=='axis':m[:3,:3]=np.eye(3)
    elif defect=='unavailable':scene.rgb_camera_calibration=lambda name:dict(available=False)
    else:m[0,0]=float('nan')
    assert not camera_audit(scene,images)['admission_passed']

def test_recorded_shaded_wall_in_all_three_cameras_is_rejected():
    from pathlib import Path
    from PIL import Image
    p=Path(__file__).parent/'fixtures/e26_gray_camera'
    scene,_,_=fixture();scene.spec['id']='E26'
    images={name:np.array(Image.open(p/f'reference-final-{name}.png'))for name in VIEWS}
    result=camera_audit(scene,images)
    assert not all(v['near_uniform_gray']for v in result['views'].values())
    assert result['low_content_gray_set'] and not result['admission_passed']
    # Preserve useful head evidence even if both wrists see a blank surface.
    images['head']=np.array(Image.open(p/'reference-initial-head.png'))
    assert camera_audit(scene,images)['admission_passed']

def test_low_content_guard_does_not_change_other_sessions_tasks():
    from pathlib import Path
    from PIL import Image
    p=Path(__file__).parent/'fixtures/e26_gray_camera'
    scene,_,_=fixture();scene.spec['id']='E01'
    images={name:np.array(Image.open(p/f'reference-final-{name}.png'))for name in VIEWS}
    assert camera_audit(scene,images)['admission_passed']
