from itertools import product
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e33_grasp import plan_grasp,section

def box(lo,hi):return np.array(list(product(*zip(lo,hi))),float)

def geometry():
    return (box([-.02,-.02,.8],[.02,.02,1.]),np.array([0,0,1.1]),
        box([-.04,-.04,1.155],[.04,.04,1.22]),
        [box([-.015,y,1.09],[.015,y+.02,1.15])for y in (-.06,.04)])

def test_tall_bottle_has_actual_palm_clearance_and_finger_overlap():
    vertices,tcp,palm,fingers=geometry();r=plan_grasp(vertices,tcp,palm,fingers)
    assert r['palm_clearance_m']==pytest.approx(.006)
    assert .8<r['contact_plane_z_m']<1.
    assert r['actual_opening_m']>=r['bottle_section_width_m']+.004
    assert r['native_grasp_verified'] is False
    target=np.array(r['tcp_target_task_m']);translated_palm=palm+target-tcp
    assert translated_palm[:,2].min()>vertices[:,2].max()

@pytest.mark.parametrize('delta',[(.2,-.3,.06),(-8,0,0),(0,8,0)])
def test_room_frame_translation_preserves_geometry(delta):
    v,t,p,f=geometry();d=np.array(delta);a=plan_grasp(v,t,p,f)
    b=plan_grasp(v+d,t+d,p+d,[x+d for x in f],floor=.8+d[2])
    assert np.array(b['tcp_target_task_m'])==pytest.approx(np.array(a['tcp_target_task_m'])+d)
    assert b['palm_clearance_m']==pytest.approx(a['palm_clearance_m'])

def test_unavailable_overlap_or_insufficient_opening_fail_closed():
    v,t,p,f=geometry()
    with pytest.raises(ValueError,match='No palm-clear'):plan_grasp(v,t,p-[0,0,.05],f)
    with pytest.raises(ValueError,match='do not clear'):plan_grasp(v*np.array([1,3,1]),t,p,f)

def test_sloped_bottle_hull_section_is_interpolated_not_nearest_vertex():
    v=np.array([[-.03,-.03,0],[.03,-.03,0],[.03,.03,0],[-.03,.03,0],[-.01,-.01,1],[.01,-.01,1],[.01,.01,1],[-.01,.01,1]])
    x=section(v,.5)
    assert x.min(axis=0)==pytest.approx([-.02,-.02])
    assert x.max(axis=0)==pytest.approx([.02,.02])

def test_sideways_actual_bottle_requires_short_axis_before_grasp_proposal():
    import json
    from pathlib import Path
    from videoicl_isaaclab.execution_design_e33_grasp import narrow_horizontal_axis
    d=json.loads((Path(__file__).parent/'fixtures/e33_sideways_grasp.json').read_text())
    v,t,p=map(np.asarray,(d['vertices'],d['tcp'],d['palm']))
    fingers=[np.asarray(x)for x in d['fingers']]
    with pytest.raises(ValueError,match='do not clear'):plan_grasp(v,t,p,fingers)
    axis=narrow_horizontal_axis(v)
    old=(fingers[1].mean(0)-fingers[0].mean(0))[:2]
    angle=np.arctan2(axis[1],axis[0])-np.arctan2(old[1],old[0])
    c,s=np.cos(angle),np.sin(angle);rotation=np.array([[c,-s,0],[s,c,0],[0,0,1]])
    moved_palm=(p-t)@rotation.T+t
    moved_fingers=[(f-t)@rotation.T+t for f in fingers]
    plan=plan_grasp(v,t,moved_palm,moved_fingers)
    assert plan['bottle_section_width_m']<.05
    assert plan['actual_opening_m']>plan['bottle_section_width_m']+.004
    assert plan['palm_clearance_m']>=.005999
    assert plan['native_grasp_verified']is False
