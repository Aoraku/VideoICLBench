import copy,itertools
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e08_source_plan import make_source_plan
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError,_axis_rotation


def fixture(variant='A'):
    half=np.array([.13,.04422009824739785,.051902870300350894]);points=np.array(list(itertools.product((-1,1),repeat=3)))*half
    spec=dict(id='E08',variant=variant,execution_design={'revision':'embodied50-execution-v3-20261102'},objects={'left_shoe':{'size':half,'source_asset':{'sha256':'fdd7d78b574ad7bd52485d063fbb48621a02651cd174235cfd6bd9f7b2e40b32','source_rotation':[.5,.5,.5,.5]}}},semantic={'toe_axis_local':[1,0,0],'shoe_axes':{'left_shoe':{'toe_local':[.12,-.01,-.03],'heel_local':[-.12,.01,-.03]}},'label_end':{'point_local':[-.175,0,-.0275]},'containers':{'box':{'ref':{'actor':'box'},'lower':[-.171,-.096,-.05264],'upper':[.171,.096,.055]}},'container_interior':{'floor_local_z':-.0478544},'structural_expert':{'box_positions':{'left_shoe':[0,.046,-.05264]}},'expert_clearance_z':1.12})
    return spec,points


@pytest.mark.parametrize('variant,sign',[('A',1),('B',-1),('C',1)])
def test_source_goal_tracks_actual_rotated_box_label_without_historical166(variant,sign):
    spec,points=fixture(variant);box_r=_axis_rotation([0,0,1],np.pi/2)
    plan=make_source_plan(spec,'left_shoe',[.02,-.16,.855],box_r,points)
    assert plan['not_historical_action166'] and plan['native_placement_verified']is False
    assert plan['geometry']['toe_toward_label_alignment']*sign>.98
    assert plan['geometry']['up_alignment']==pytest.approx(1.)
    assert min(plan['geometry']['native_containment_margin_xyz_m'])>0
    assert plan['whole_task_score']is None


def test_source_plan_refuses_too_low_unchanged_native_cavity():
    spec,points=fixture();spec['semantic']['containers']['box']['upper'][2]=.04
    with pytest.raises(ToolExecutionError,match='unchanged native'):make_source_plan(spec,'left_shoe',[0,0,.855],np.eye(3),points)


def test_source_plan_rejects_unbound_geometry_or_wrong_sha():
    spec,points=fixture();bad=points.copy();bad[0,0]-=.01
    with pytest.raises(ValueError,match='source bounds'):make_source_plan(spec,'left_shoe',[0,0,.855],np.eye(3),bad)
    spec['objects']['left_shoe']['source_asset']['sha256']='0'*64
    with pytest.raises(ValueError,match='Pinned source'):make_source_plan(spec,'left_shoe',[0,0,.855],np.eye(3),points)


def test_source_sole_material_control_targets_measured_floor_plus_release_gap():
    spec,points=fixture();box=np.array([0.,-.16,.855]);plan=make_source_plan(spec,'left_shoe',box,np.eye(3),points)
    assert plan['control_local'][2]==pytest.approx(points[:,2].min())
    assert plan['destination_point_task'][2]-box[2]==pytest.approx(-.0478544+.0005)
    assert plan['reference_orientation_acceptance']=='native_direction_and_actual_shape_cavity_margin'


def test_actual_cooked_floor_incompatible_with_original_cavity_refuses_new_plan():
    spec,points=fixture()
    with pytest.raises(ValueError,match='floor ray'):
        make_source_plan(spec,'left_shoe',[0,0,.855],np.eye(3),points,measured_floor_local_z=.055)


def test_drop_forecast_accepts_actual_dynamic_motion_that_stays_inside_cavity():
    from videoicl_isaaclab.execution_design_e08_source_plan import drop_envelope
    spec,points=fixture();corners=points+[0,.046,.13];lower=[-.171,-.096,-.05264];upper=[.171,.096,.055]
    # Shift from source sole height .0781 to the original floor -.04785.
    height=float(corners[:,2].min()+.0478544)
    result=drop_envelope(corners,height,-.0478544,[0,0,0],np.eye(3),[.0001,0,0],[0,0,0],[0,0,-9.81],.15,lower,upper)
    assert min(result['residual_native_cavity_margin_xyz_m'])>0
    assert not result['native_landed_support_verified']
    moving=drop_envelope(corners,height,-.0478544,[0,0,0],np.eye(3),[.002,0,0],[0,0,.02],[0,0,-9.81],.15,lower,upper)
    assert moving['horizontal_speed_m_s']>.001 and moving['angular_speed_rad_s']>.01
    assert min(moving['residual_native_cavity_margin_xyz_m'])>0
    with pytest.raises(ToolExecutionError,match='full-shape'):
        drop_envelope(corners,height,-.0478544,[0,0,0],np.eye(3),[0,.1,0],[0,0,0],[0,0,-9.81],.15,lower,upper)
    with pytest.raises(ToolExecutionError,match='full-shape'):
        drop_envelope(corners+[0,.02,0],height,-.0478544,[0,0,0],np.eye(3),[0,0,0],[0,0,0],[0,0,-9.81],.15,lower,upper)


def test_actual_source_geometry_accepts_imprecise_goal_and_rejects_native_bounds_or_direction():
    from videoicl_isaaclab.execution_design_e08_source_plan import settled_pose_geometry
    spec,points=fixture();plan=make_source_plan(spec,'left_shoe',[0,0,0],np.eye(3),points)
    cavity=spec['semantic']['containers']['box'];axes=spec['semantic']['shoe_axes']['left_shoe'];toe=np.array(axes['toe_local'])-axes['heel_local']
    def review(yaw):
        return settled_pose_geometry(points,points,_axis_rotation([0,0,1],np.deg2rad(yaw)),[0,0,0],np.eye(3),
            plan['control_local'],plan['destination_point_task'],-.0478544,cavity['lower'],cavity['upper'],toe,spec['semantic']['label_end']['point_local'],1)
    assert review(181)['acceptable']  # 1degree from recipe, task geometry already fits.
    assert not review(190)['inside_original_cavity']
    wrong=review(0);assert wrong['inside_original_cavity']and not wrong['correct_label_direction']


def test_measured_side_mesh_fits_when_empty_obb_corners_do_not():
    from videoicl_isaaclab.execution_design_e08_source_plan import measured_source_pose_plan,settled_pose_geometry
    import itertools
    points=np.r_[np.diag([.13,.04,.05]),-np.diag([.13,.04,.05])]
    corners=np.array(list(itertools.product([-1,1],repeat=3)))*[.13,.04,.05]
    r=_axis_rotation([0,1,0],np.deg2rad(6))@_axis_rotation([1,0,0],np.pi/2)
    lo=[-.171,-.096,-.05264];hi=[.171,.096,.055];floor=-.0478544
    actual=measured_source_pose_plan(points,r,[0,0,0],np.eye(3),[0,0,0],floor,lo,hi,[0,.046,0],[1,0,0],[1,0,0],1)
    assert actual['acceptable'] and actual['no_source_up_or_flat_requirement']
    assert abs(r[2,2])<1e-10
    old=settled_pose_geometry(points,corners,r,[0,0,0],np.eye(3),[0,0,0],actual['destination_point_task'],floor,lo,hi,[1,0,0],[1,0,0],1)
    assert not old['acceptable']
    vertices=points@r.T+actual['anticipated_body_origin_box_m']
    assert np.all(vertices>=np.array(lo)-[.002,.002,.003])
    assert np.all(vertices<=np.array(hi)+[.002,.002,.003])


def test_measured_mesh_keeps_original_true_vertex_bounds_and_direction():
    from videoicl_isaaclab.execution_design_e08_source_plan import measured_source_pose_plan
    import itertools
    vertices=np.array(list(itertools.product([-.13,.13],[-.044,.044],[-.05,.05])))
    args=(vertices,np.eye(3),[0,0,0],np.eye(3),[0,0,0],-.04785,[-.171,-.096,-.05264],[.171,.096,.055],[0,.046,0],[1,0,0],[1,0,0],1)
    assert measured_source_pose_plan(*args)['acceptable']
    wrong=list(args);wrong[1]=_axis_rotation([0,0,1],np.pi)
    assert not measured_source_pose_plan(*wrong)['acceptable']
    high=vertices.copy();high[:,2]*=2;wrong=list(args);wrong[0]=high
    assert not measured_source_pose_plan(*wrong)['acceptable']
