from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_thin_edge import table_bounds_task,edge_slide_target,check_under_table_clearance
from videoicl_isaaclab.execution_design_fold_public import fold_public


def test_actual_table_bounds_remove_nonzero_shared_room_origin():
    origin=np.array([4.,-3.,.1]);scene=SimpleNamespace(origin=origin,
        embodiment=SimpleNamespace(config={'layout':{'table':{'position':[.2,0,.4],'size':[1.,.8,.8],'top':.8}}}),
        world_to_task=lambda p:np.asarray(p)-origin-[.1,0,0])
    bounds=table_bounds_task(scene)
    np.testing.assert_allclose(bounds['lower'],[-.4,-.4,.8]);np.testing.assert_allclose(bounds['upper'],[.6,.4,.8])


@pytest.mark.parametrize('axis,grasp,base,target',[
    ([1,0,0],[.1,0,.8],[-.05,0,.8],[.53,0,.8]),
    ([-1,0,0],[-.1,0,.8],[.05,0,.8],[-.53,0,.8]),
    ([0,1,0],[0,.15,.8],[0,0,.8],[0,.43,.8])])
def test_measured_edge_exposure_keeps_base_inside_actual_table(axis,grasp,base,target):
    b={'lower':np.array([-.5,-.4,.8]),'upper':np.array([.5,.4,.8]),'top':.8}
    if axis[0]:b['upper'][0]=.45;b['lower'][0]=-.45;target[0]=np.sign(axis[0])*.48
    plan=edge_slide_target(grasp,base,axis,b)
    np.testing.assert_allclose(plan['target_grasp'],target)
    assert plan['distance']<=.4


def test_bad_direction_and_loss_of_base_support_rejected():
    b={'lower':[-.5,-.4,.8],'upper':[.5,.4,.8],'top':.8}
    for axis in ([0,0,0],[1,1,0],[1,0,.5]):
        with pytest.raises(ValueError):edge_slide_target([.2,0,.8],[.1,0,.8],axis,b)
    with pytest.raises(ValueError,match='lose'):
        edge_slide_target([.2,0,.8],[.3,0,.8],[1,0,0],b)


def geometry(low_x=.0):
    return {'fingers':[{'aabb_min_task_m':[low_x,-.02,.75],'aabb_max_task_m':[low_x+.02,.02,.78]},
                       {'aabb_min_task_m':[low_x,-.02,.82],'aabb_max_task_m':[low_x+.02,.02,.85]}]}


def test_actual_lower_finger_must_clear_finite_edge_before_lowering():
    b={'lower':[-.5,-.4,.8],'upper':[.5,.4,.8],'top':.8}
    with pytest.raises(RuntimeError,match='intersect'):
        check_under_table_clearance([.5,0,.8],[0,0,.8],geometry(),b,0,1)
    assert check_under_table_clearance([.502,0,.8],[0,0,.8],geometry(),b,0,1)
    with pytest.raises(ValueError,match='Both'):
        check_under_table_clearance([1,0,.8],[0,0,.8],{'fingers':[]},b,0,1)


def test_public_fold_rejects_nonengineering_before_any_motion():
    p=SimpleNamespace(a=SimpleNamespace(control_report={}),spec={'id':'E44','execution_design':{}})
    with pytest.raises(ValueError,match='Isolated'):
        fold_public(p)


def test_trailing_edge_pose_uses_measured_toe_band_not_upper_finger_bounds():
    from videoicl_isaaclab.execution_design_thin_edge import trailing_edge_push_pose
    material=np.array([[x,y,z]for x in (-.11,0)for y in (-.1,.1)for z in (.8,.8012)])
    # High finger bulk reaches forward .04 but the near-floor toe only .006.
    finger=np.array([[x,y,z]for x,y,z in [(-.004,-.01,.81),(.006,-.01,.81),(-.004,.01,.81),(.006,.01,.81),(.04,.01,.85)]])
    target,receipt=trailing_edge_push_pose(material,finger,[0,0,.82],[1,0,0],.8)
    np.testing.assert_allclose(target,[-.119,0,.8102]);assert receipt['finger_band_vertices']==4
    moved=finger+target-[0,0,.82];assert moved[:,2].min()==pytest.approx(.8002)
    assert max(moved[moved[:,2]<.8013,0])==pytest.approx(-.113)


def test_too_thin_to_clear_table_is_explicitly_rejected():
    from videoicl_isaaclab.execution_design_thin_edge import trailing_edge_push_pose
    points=np.array([[x,y,z]for x in (-.1,.1)for y in (-.1,.1)for z in (.8,.8001)])
    with pytest.raises(ValueError,match='thickness'):
        trailing_edge_push_pose(points,points,[0,0,.81],[1,0,0],.8)


def test_native_finger_side_pinch_keeps_card_center_supported():
    import json
    from pathlib import Path
    from videoicl_isaaclab.execution_design_thin_edge import card_side_pinch_plan
    source=json.loads((Path(__file__).parent/'fixtures/cutlery_native_finger_section.json').read_text())
    current=np.asarray(source['rotation']);tcp=np.asarray(source['tcp'])
    outward=np.array([1.,0.,0.]);up=np.array([0.,0.,1.]);tangent=np.cross(up,outward)
    target_rotation=np.column_stack((-tangent,up,-outward))
    fingers=[(np.asarray(v)-tcp)@current@target_rotation.T for v in source['fingers']]
    material=np.array([[x,y,z]for x in(-.04415272,.04415272)for y in(-.0315,.0315)for z in(.8,.80035)])
    bounds=dict(lower=np.array([-.35,-.4,.8]),upper=np.array([.35,.4,.8]),top=.8)
    plan=card_side_pinch_plan(material,[0,0,.800175],fingers,bounds)
    assert .009<plan['required_exterior_m']<.012
    assert bounds['upper'][0]-plan['translated_center'][0]>.025
    assert .3<plan['translation'][0]<.35
    for mesh in fingers:
        world=mesh+plan['target_grasp'];low=world[world[:,2]<.801]
        if len(low):assert low[:,0].min()>=bounds['upper'][0]+.001-1e-12
    # A shorter card cannot safely bridge the same lower-finger geometry.
    short=material.copy();short[:,0]*=.2
    with pytest.raises(ValueError,match='support'):
        card_side_pinch_plan(short,[0,0,.800175],fingers,bounds)


def test_card_edge_acquire_rejects_model_route_before_actuation():
    from videoicl_isaaclab.execution_design_card_edge import acquire_card
    from videoicl_isaaclab.execution_design import REVISION_V3,source_sha256
    policy=SimpleNamespace(a=SimpleNamespace(control_report={}),task='E50',spec={
        'execution_design':dict(revision=REVISION_V3,source_sha256=source_sha256(REVISION_V3))})
    with pytest.raises(ValueError,match='engineering'):
        acquire_card(policy,dict(actor='card',local=[0,0,0]),'left')


def test_left_edge_candidate_avoids_overlong_right_edge_slide():
    import json
    from pathlib import Path
    from videoicl_isaaclab.execution_design_thin_edge import card_side_pinch_plan
    x=json.loads((Path(__file__).parent/'fixtures/cutlery_native_finger_section.json').read_text())
    local=[(np.asarray(v)-x['tcp'])@np.asarray(x['rotation'])for v in x['fingers']]
    card=np.array([[a-.1,b+.1,z]for a in(-.04415272,.04415272)for b in(-.0315,.0315)for z in(.8,.80035)])
    bounds=dict(lower=np.array([-.35,-.4,.8]),upper=np.array([.35,.4,.8]),top=.8)
    for sign in(1.,-1.):
        outward=np.array([sign,0.,0.]);up=np.array([0.,0.,1.]);r=np.column_stack((-np.cross(up,outward),up,-outward))
        fingers=[m@r.T for m in local]
        if sign>0:
            with pytest.raises(ValueError,match='bounded'):card_side_pinch_plan(card,[-.1,.1,.800175],fingers,bounds,outward)
        else:
            p=card_side_pinch_plan(card,[-.1,.1,.800175],fingers,bounds,outward)
            assert .2<np.linalg.norm(p['translation'])<.25
            assert p['translated_center'][0]>-.325


def test_thin_card_specific_clearance_keeps_geometry_above_table():
    from videoicl_isaaclab.execution_design_thin_edge import trailing_edge_push_pose
    material=np.array([[x,y,z]for x in(-.144,-.056)for y in(.068,.132)for z in(.8,.80035)])
    fingers=np.array([[x,y,z]for x in(-.006,.006)for y in(-.015,.015)for z in(.81,.82)])
    target,receipt=trailing_edge_push_pose(material,fingers,[0,0,.82],[-1,0,0],.8,clearance=.00002)
    moved=fingers+target-[0,0,.82]
    assert moved[:,2].min()==pytest.approx(.80002)
    assert receipt['finger_clearance_m']==.00002
    for value in(0.,-.0001,.002,float('nan')):
        with pytest.raises(ValueError,match='clearance'):
            trailing_edge_push_pose(material,fingers,[0,0,.82],[-1,0,0],.8,clearance=value)


def test_yawed_panel_reseat_uses_edge_at_real_toe_not_far_corner():
    from videoicl_isaaclab.execution_design_thin_edge import trailing_edge_push_pose
    # v12 native E44 ends with yaw2.90deg; its distant corner falsely
    # adds~5mm to the3mm approach gap and exhausts12 half-mm searches.
    yaw=.050619878;rotation=np.array([[np.cos(yaw),-np.sin(yaw),0],[np.sin(yaw),np.cos(yaw),0],[0,0,1.]])
    material=np.array([[x,y,z]for x in(-.1105,0.)for y in(-.10625,.10625)for z in(-.0006,.0006)])@rotation.T+[.097454637,-.005890964,.800600049]
    fingers=np.array([[x,y,z]for x in(-.006,.006)for y in(-.015,.015)for z in(.81,.82)])
    target,r=trailing_edge_push_pose(material,fingers,[0,0,.82],[1,0,0],.8)
    assert r['material_trailing_edge_m']-r['global_material_trailing_edge_m']>.004
    probe=np.array([r['material_trailing_edge_m'],r['contact_tangent_m'],.8006])
    local=(probe-[.097454637,-.005890964,.800600049])@rotation
    assert local[0]==pytest.approx(-.1105,abs=1e-7)
    assert r['section_candidates']>0


def test_last_public_seek_action_can_establish_contact_and_stop_without_replay():
    from videoicl_isaaclab.execution_design_thin_edge import seek_actual_contact
    count=[0]
    def advance():count[0]+=1
    assert seek_actual_contact(lambda:count[0]>=12,advance,12)==12
    assert count[0]==12
    assert seek_actual_contact(lambda:True,advance,12)==0
    assert count[0]==12
    count[0]=0
    assert seek_actual_contact(lambda:False,advance,12)is None
    assert count[0]==12


def test_asymmetric_leading_toe_centres_force_line_without_lowering_into_table():
    from videoicl_isaaclab.execution_design_thin_edge import trailing_edge_push_pose
    material=np.array([[x,y,z]for x in(-.144,-.056)for y in(.068,.132)for z in(.8,.80035)])
    # One leading toe is displaced7mm sideways; its opposite finger trails.
    fingers=np.array([[x,y,z]for x,y in((-.012,.007),(-.012,.009),(.006,-.007),(.006,-.009))for z in(.81,.82)])
    tip=np.array([0.,0.,.82])
    target,r=trailing_edge_push_pose(material,fingers,tip,[-1,0,0],.8,clearance=.00002,center_leading_toe=True)
    moved=fingers+target-tip;front=moved[moved[:,0]<=moved[:,0].min()+.0001]
    assert front[:,1].mean()==pytest.approx(.1)
    assert front[:,0].min()==pytest.approx(-.056+.003)
    assert moved[:,2].min()==pytest.approx(.80002)
    assert r['center_leading_toe'] is True


def test_compression_fold_cannot_run_in_model_route():
    from videoicl_isaaclab.execution_design_fold_compress import compress_fold
    from videoicl_isaaclab.execution_design import REVISION_V3,source_sha256
    p=SimpleNamespace(task='E44',a=SimpleNamespace(control_report={}),spec={
        'execution_design':dict(revision=REVISION_V3,source_sha256=source_sha256(REVISION_V3))})
    with pytest.raises(ValueError,match='engineering'):compress_fold(p)
