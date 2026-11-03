"""E09 real source pinch: measured triangle site and immediate native holding.

No source geometry, material, body state or task scoring is changed. The
triangle site comes from the original successful native v8 pre-grasp3917;
the left-hand site/liftoff was physically reproduced in debug v13.
"""
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .execution_design_e09_reference import scope,log,SOURCE_TRIANGLE_PREGRIP_LOCAL


def relay_if_required(p,name):
    """B's far red circle uses the actually vacated original blue-circle rail.

    This is the same original red actor throughout two real native grips. No
    hand reaches the source-to-destination pair directly with a level pinch.
    The normal B ordering has already removed blue/green circles from supply.
    """
    if (p.variant!='B' or name!='red_circle' or not p.d.get('operable_packaging')
            or float(p.frame({'actor':name})[0][1])>-.25):return False
    scope(p)
    from .execution_design_e09_reference import measured_approach_height,park_empty_other
    from .execution_design_e09_liftoff import lift_piece
    from .execution_design_e09_operable import release_sweep
    rail=p.d['initial_storage']['blue_circle'];index=int(rail.removeprefix('fixture'))
    fixture=p.spec['fixtures'][index];surface=p.d['storage_surfaces']['piece_rail_blue_circle']
    if (surface['actor']!=rail or not np.allclose(fixture['size'],[.003,.024,.014],atol=1e-10)
            or not np.allclose(surface['xy'],fixture['xy'],atol=1e-10)
            or abs(surface['surface_z']-fixture['z']-.014)>1e-9):
        raise ToolExecutionError('Original fixed blue-circle supply rail required for real relay')
    state,contacts=p.snapshot()
    if any(frozenset((n,rail))in contacts for n in state if n!=name):
        raise ToolExecutionError('Original circle relay rail is not actually vacant')
    side='right';ref=p.ref(name);park_empty_other(p,side,lateral_first=True)
    previous=p.clearance;p.clearance=measured_approach_height(p,side)
    try:acquire(p,ref,side)
    finally:p.clearance=previous
    lift_piece(p,ref,side)
    control={'actor':name,'local':p.bottom_local(name).tolist()}
    target=np.r_[surface['xy'],surface['surface_z']+.0005]
    def guard():p.require_held(ref,side)
    height=p.measured_transport_clearance(name,side)
    p.stage('e09-B-original-red-circle-real-rail-relay')
    current=p.point(control)
    p.move_point(side,control,[*current[:2],height],guard)
    p.move_point(side,control,[*target[:2],height],guard)
    p.move_point(side,control,target,guard,tolerance=.0005)
    release_sweep(p,name,side,grasp_ref=ref);p.release(ref,side)
    p.move(side,np.asarray(p.tip(side))+[0,0,.06])
    body=p.snapshot()[0][name]
    if (any(body['grasp']) or not p.contact(name,rail)
            or np.max(abs(np.asarray(body['pos'])[:2]-target[:2]))>.002
            or float(body['mat'][2,2])<.995):
        raise ToolExecutionError('Original red circle failed actual released support on the original relay rail')
    log(p,'native-original-red-circle-rail-relay',actor=name,support=rail,
        actual_pose=body['pos'],next_hand='left',identity_preserved=True)
    return True


def acquire(p,ref,side):
    scope(p);name=ref['actor'];obj=p.objects[name]
    if name not in set(p.d['target_members'])|set(p.d.get('batch_members',{}).get('distractor',[])):
        raise ToolExecutionError('Original E09 source piece required')
    from .author_clearance import prepare_single_hand
    p.stage('acquire-'+name);prepare_single_hand(p.a,side,p.clearance);p.act(side,'RELEASE')
    _,rotation=p.frame(ref);axis=rotation@np.asarray(ref['jaw_axis_local'],float)
    p.a.align_gripper_axis(side,axis)
    source=obj.get('source_asset',{});triangle=source.get('relative_path')=='source_three_hole_triangle_v2.usda'
    if triangle and source.get('sha256')!='caae5e783af9afae7ee6c1933e42a1654d746635873c7a1bb221ea4554a70e7b':
        raise ToolExecutionError('Original measured three-hole triangle source asset required')
    pinch=dict(ref,local=SOURCE_TRIANGLE_PREGRIP_LOCAL.tolist())if triangle else ref
    point=p.point(pinch);recording=p.a.scene.embodiment.config.get('author_recording',{})
    if recording.get('palm_down_grasp',False)or recording.get('grasp_table_clearance',False):
        point=point.copy();point[2]=max(point[2],p.a.floor_clear_tcp(side))
    height=max(p.clearance,float(point[2])+.07,float(p.tip(side)[2]))
    p.move(side,[*p.tip(side)[:2],height]);p.move(side,[*point[:2],height])
    if recording.get('pre_grasp_opening_m')is not None:p.a.prepare_generated_gripper(side)
    p.move(side,point,tolerance=.0003 if triangle else .002)
    for _ in range(5):
        p.act(side,'GRASP')
        if p.held(ref,side):
            log(p,'native-source-piece-bilateral-pinch',actor=name,side=side,
                actual_tcp=p.tip(side),material_pinch_local=pinch['local'],extra_hold_actions=0)
            return
    raise ToolExecutionError('Original E09 piece lacks actual bilateral source pinch')
