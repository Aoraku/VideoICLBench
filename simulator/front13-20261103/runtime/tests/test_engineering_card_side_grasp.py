import numpy as np
from videoicl_isaaclab.engineering_card_side_grasp import side_placement


def box(center,half):
    return np.asarray(center)+np.asarray([[x,y,z]for x in(-half[0],half[0])for y in(-half[1],half[1])for z in(-half[2],half[2])])


def test_twenty_micron_band_is_feasible_where_tool_handle_margin_would_erase_thin_card():
    fingers=[box([0,y,.025],[.005,.005,.025])for y in(-.05,.05)]
    palm=box([0,0,.08],[.025,.02,.01]);points=np.array([[0,-.0315,.800324],[0,.0315,.800324]])
    feasible=side_placement(points,fingers,fingers,palm,np.array([0.,-1.,0.]),.8,margin=.00002)
    assert feasible and all(p['position'][2]>=.80002-1e-10 for p in feasible)
    assert all(abs(p['closure_m']-.01352)<.000031 for p in feasible)
    assert not side_placement(points,fingers,fingers,palm,np.array([0.,-1.,0.]),.8,margin=.0002)
    centred=side_placement(points,fingers,fingers,palm,np.array([0.,-1.,0.]),.8,
        margin=.00002,preferred_translation=[0.,0.,.81])
    assert centred and abs(centred[0]['position'][0])<1e-10


def test_tilted_closing_path_cannot_hide_an_open_toe_below_the_table():
    fingers=[box([0,-.05,.025],[.005,.005,.025]),
             box([0,.05,.02532],[.005,.005,.025])]
    palm=box([0,0,.08],[.025,.02,.01])
    jaw=np.array([0.,-1.,-.004]);jaw/=np.linalg.norm(jaw)
    points=np.array([[0,-.0315,.800324],[0,.0315,.800324]])
    plans=side_placement(points,fingers,fingers,palm,jaw,.8,margin=.00002)
    assert plans
    for plan in plans:
        for sign,mesh in zip((-1.,1.),fingers):
            opened=mesh+plan['position']
            closed=opened+sign*plan['closure_m']*jaw
            assert opened[:,2].min()>=.80002-1e-9
            assert closed[:,2].min()>=.80002-1e-9


def test_nearby_feasible_pose_does_not_certify_the_achieved_tcp():
    fingers=[box([0,y,.025],[.005,.005,.025])for y in(-.05,.05)]
    palm=box([0,0,.08],[.025,.02,.01]);points=np.array([[0,-.0315,.800324],[0,.0315,.800324]])
    args=(points,fingers,fingers,palm,np.array([0.,-1.,0.]),.8)
    good=side_placement(*args)[0]['position']
    assert side_placement(*args,fixed_translation=good)
    assert not side_placement(*args,fixed_translation=good+np.array([0.,0.,.0005]))


def test_two_native_driven_fingers_need_not_stop_at_identical_contact_q():
    fingers=[box([0,y,.025],[.005,.005,.025])for y in(-.05,.05)]
    palm=box([0,0,.08],[.025,.02,.01]);points=np.array([[0,-.0315,.800324],[0,.0315,.800324]])
    args=(points,fingers,fingers,palm,np.array([0.,-1.,0.]),.8)
    centred=side_placement(*args)[0]['position'];achieved=centred+np.array([0.,.0002,0.])
    assert not side_placement(*args,fixed_translation=achieved)
    plans=side_placement(*args,fixed_translation=achieved,independent_closures=True)
    assert plans and .00035<plans[0]['closure_difference_m']<.00045
    assert all(0.<=v<=.039 for v in plans[0]['closures_m'])
    offcenter=centred+np.array([0.,.0015,0.])
    assert not side_placement(*args,fixed_translation=offcenter,independent_closures=True,maximum_closure_difference_m=.001)
    actual=side_placement(*args,fixed_translation=offcenter,independent_closures=True)
    assert actual and .0029<actual[0]['closure_difference_m']<.0031
    assert all(0.<=value<=.039 for value in actual[0]['closures_m'])


def test_oblique_side_points_follow_the_cooked_card_and_cross_real_com():
    from videoicl_isaaclab.engineering_card_side_grasp import com_side_points
    vertices=box([0,0,0],[.044,.0315,.000175]);yaw=np.deg2rad(-20.)
    jaw=np.array([-np.sin(yaw),np.cos(yaw),0.]);com=np.array([.0001,-.0002,0.])
    points=com_side_points(vertices,np.zeros(3),np.eye(3),com,jaw,.000175,.5)
    assert np.allclose(points[:,1],[-.0315,.0315])
    assert abs(points[0,0]-points[1,0])>.02
    assert abs(np.cross(points[1,:2]-points[0,:2],com[:2]-points[0,:2]))<1e-12


def test_near_com_section_reintersects_the_real_boundary_and_rejects_large_offsets():
    import pytest
    from videoicl_isaaclab.engineering_card_side_grasp import com_side_points
    vertices=box([0,0,0],[.044,.0315,.000175]);jaw=np.array([.2,.98,0.]);jaw/=np.linalg.norm(jaw)
    points=com_side_points(vertices,np.zeros(3),np.eye(3),np.zeros(3),jaw,.000175,.5,long_offset_m=.00004)
    assert np.allclose(abs(points[:,1]),.0315)
    assert abs(points[:,0].mean()-.00004)<1e-12
    with pytest.raises(ValueError):
        com_side_points(vertices,np.zeros(3),np.eye(3),np.zeros(3),jaw,.000175,.5,long_offset_m=.00051)


def test_real_side_height_can_absorb_tracking_residual_without_moving_card():
    # A thin side remains physical across its thickness; an engineering
    # reference must not insist on exactly one arbitrary height on that side.
    fingers=[box([0,y,.025],[.005,.005,.025])for y in(-.05,.05)]
    palm=box([0,0,.08],[.025,.02,.01]);jaw=np.array([0.,-1.,0.])
    points=np.array([[0,-.0315,.80018],[0,.0315,.80018]])
    args=(fingers,fingers,palm,jaw,.8)
    target=side_placement(points,*args)[0]['position']
    target[2]=.80016
    achieved=target+np.array([0.,0.,.00005])
    assert not side_placement(points,*args,fixed_translation=achieved)
    real_higher=points+np.array([0.,0.,.00005])
    assert real_higher[:,2].max()<.80035
    assert side_placement(real_higher,*args,fixed_translation=achieved)
