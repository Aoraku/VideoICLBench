"""E17 A842/B822 diagnostic suffixes; completed prefix is never replayed."""
from copy import deepcopy
import math
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .execution_design_expert import ExecutionDesignAuthor
from .realworld_tool_expert import ToolExecutionError
from .author_orientation import _axis_angle,panda_downward_grasp_delta

ENTRIES={'e17_a_resume_after_lower_first':('A',842,85040,'green_square'),
         'e17_b_resume_after_lower_first':('B',822,83040,'blue_square')}
STAND_ROTATION_MATRIX_LIMIT=.03
TRIANGLE_SHA='caae5e783af9afae7ee6c1933e42a1654d746635873c7a1bb221ea4554a70e7b'


def _finite(value,shape):
    a=np.asarray(value,float)
    if a.shape!=shape or not np.isfinite(a).all():raise ToolExecutionError('Finite measured E17 suffix geometry required')
    return a


def _empty(policy):
    state,contacts=policy.snapshot()
    if any(any(v['grasp'])for v in state.values()) or any(
        frozenset((name,f'{side}_finger{i}'))in contacts for name in state for side in ('left','right')for i in (1,2)):
        raise ToolExecutionError('E17 empty-wrist suffix requires actual empty hands')


def _finger_axis(policy,side):
    fingers=policy.a.finger_geometry(side)['fingers']
    if len(fingers)!=2:raise ToolExecutionError('E17 actual two-finger geometry required')
    axis=_finite(fingers[0]['body_origin_task_m'],(3,))-_finite(fingers[1]['body_origin_task_m'],(3,))
    if np.linalg.norm(axis)<.001:raise ToolExecutionError('E17 actual finger axis unavailable')
    return axis/np.linalg.norm(axis)


def _rotation_clearance(policy,side):
    """The measured finger swept sphere must clear every actual body/fixture."""
    tip=policy.tip(side);radius=0.
    for f in policy.a.finger_geometry(side)['fingers']:
        lo=_finite(f['aabb_min_task_m'],(3,));hi=_finite(f['aabb_max_task_m'],(3,))
        radius=max(radius,float(np.linalg.norm(np.maximum(abs(lo-tip),abs(hi-tip)))))
    if not .02<radius<.20:raise ToolExecutionError('E17 unreviewed actual finger swept radius')
    state,_=policy.snapshot();bounds=[]
    for name,row in state.items():
        obj=policy.objects[name];rot=_finite(row['mat'],(3,3))
        center=_finite(row['pos'],(3,))+rot@np.asarray(obj.get('local_bounds_center',[0,0,0]),float)
        half=np.abs(rot)@_finite(obj['size'],(3,));bounds.append((name,center-half,center+half))
    for i,f in enumerate(policy.spec.get('fixtures',[])):
        if f.get('type')!='box':raise ToolExecutionError('E17 unreviewed empty-wrist fixture')
        center=np.array([*f['xy'],f['z']],float);half=_finite(f['size'],(3,));bounds.append(('fixture'+str(i),center-half,center+half))
    if tip[2]-radius<.815:raise ToolExecutionError('E17 empty rotation lacks actual table clearance')
    for name,lo,hi in bounds:
        gap=np.maximum(np.maximum(lo-tip,tip-hi),0.)
        if np.linalg.norm(gap)<radius+.015:raise ToolExecutionError('E17 empty rotation swept fingers near '+name)


def relevel_empty(policy,side='right',*,retreat_south=True):
    """Retreat south, then undo tilt through measured public rotation receipts."""
    _empty(policy)
    policy.stage('local-e17-empty-south-level')
    tip=policy.tip(side)
    # The original lower ingress already exits south at z~1.12m. Preserve
    # that attainable height and gain lateral swept clearance before turning.
    if tip[2]<1.08:raise ToolExecutionError('E17 suffix empty wrist is below reviewed high retreat')
    if retreat_south:policy.move(side,[tip[0],min(float(tip[1]),-.230),tip[2]])
    _rotation_clearance(policy,side)
    current=_finite(policy.a.tcp_rotation_task(side),(3,3));axis=_finger_axis(policy,side)
    horizontal=axis.copy();horizontal[2]=0.
    if np.linalg.norm(horizontal)<.1:raise ToolExecutionError('E17 empty wrist lacks a horizontal heading')
    target=panda_downward_grasp_delta(current,axis,horizontal)@current
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    for _ in range(180):
        _empty(policy);_rotation_clearance(policy,side)
        current=_finite(policy.a.tcp_rotation_task(side),(3,3));axis,angle=_axis_angle(target@current.T)
        if angle<math.radians(5.):
            if abs(float(_finger_axis(policy,side)[2]))>.1 or float(current[2,2])>-.98:
                raise ToolExecutionError('E17 empty wrist did not achieve downward horizontal pinch')
            return
        i=int(np.argmax(np.abs(axis)));token=labels[i][int(axis[i]<0)]
        policy.act(side,token,degrees=min(2.,abs(math.degrees(angle*axis[i]))))
    raise ToolExecutionError('E17 public empty wrist levelling did not converge')


def _tilted_triangle_reference(policy,name):
    """Candidate horizontal source-median pinch; not a native success claim."""
    if name!='green_triangle':return
    obj=policy.objects[name];_,rot=policy.frame({'actor':name});rot=_finite(rot,(3,3))
    original=policy.grasps[name]
    actual=rot@np.asarray(original['jaw_axis_local'],float)
    if abs(actual[2])<=.1:return
    if (obj.get('source_asset',{}).get('sha256')!=TRIANGLE_SHA
            or not np.allclose(obj['size'],[.02,.017320508,.003],atol=1e-8,rtol=0)
            or abs(float(rot[2,1]))>.03 or not .5<float(rot[2,2])<.98):
        raise ToolExecutionError('E17 tilted triangle outside source-median pinch candidate')
    # Identical source x=0 cross-section spans y=±17.320508mm. Its midpoint
    # is local zero; the actual local-y direction is horizontal at this boundary.
    # Only this private approach reference changes. The actual object does not.
    policy.grasps[name]={**deepcopy(original),'local':[0.,0.,0.],'jaw_axis_local':[0.,1.,0.]}
    policy.operations.append(dict(operation='candidate_actual_horizontal_triangle_median',actor=name,
                                  source_sha256=TRIANGLE_SHA,native_validation_required=True))


def run_segment(author,segment,parameters):
    if segment not in ENTRIES or not isinstance(parameters,dict) or parameters:
        raise ToolExecutionError('Pinned E17 suffix entry with empty parameters required')
    variant,steps,tick,completed=ENTRIES[segment];spec=author.scene.spec;d=spec.get('execution_design',{})
    cp=getattr(author,'_engineering_resume_checkpoint',{});source=cp.get('source',{})
    if (spec.get('id')!='E17' or spec.get('variant')!=variant or spec.get('seed')!=4201
            or d.get('revision')!=REVISION_V3 or d.get('source_sha256')!=source_sha256(REVISION_V3)
            or d.get('condition')!='I' or not author.control_report.get('engineering_reference_only')
            or not getattr(author,'_execution_design_reference_authorized',False) or author.smooth
            or author.scene.embodiment.name!='franka' or cp.get('diagnostic_only')is not True
            or source.get('steps')!=steps or source.get('physics_ticks')!=tick):
        raise ToolExecutionError('Pinned E17 A842/B822 measured terminal diagnostic boundary required')
    policy=ExecutionDesignAuthor(author)
    from .execution_design_e17_stand import descriptor,native_readback
    actual=native_readback(author.scene)
    mass=np.asarray((actual or {}).get('mass_kg'),float)
    if (policy.objects.get('stand',{}).get('e17_stand_geometry')!=descriptor() or not actual
            or actual.get('measured')is not True or actual.get('derived_geometry_sha256')!=descriptor()['derived_geometry_sha256']
            or actual.get('kinematic_enabled')is not False or actual.get('gravity_disabled')is not False
            or not mass.size or not np.isfinite(mass).all()
            or not np.allclose(mass,descriptor()['empty_mass_estimate_kg'],atol=1e-5,rtol=0)):
        raise ToolExecutionError('E17 actual reviewed stand dynamics required')
    _empty(policy)
    lower=[r for r in d['local_regions']if r['id']=='lower']
    if len(lower)!=1 or not lower[0]['members'] or lower[0]['members'][0]!=completed:
        raise ToolExecutionError('E17 previously completed lower prefix assignment differs')
    state,contacts=policy.snapshot()
    if frozenset(('packing_lid','table'))not in contacts or any(state['packing_lid']['grasp']):
        raise ToolExecutionError('E17 original packing lid must already be removed and table-supported')
    stand_pos,stand_rot=policy.frame({'actor':'stand'});stand_pos=stand_pos.copy();stand_rot=stand_rot.copy()
    protected={};delivery=False
    def anchor(name):
        state,contacts=policy.snapshot();row=state[name];base,rotation=policy.frame({'actor':'stand'})
        if any(row['grasp']) or frozenset((name,'stand'))not in contacts:
            raise ToolExecutionError('E17 completed prefix lacks actual released stand support: '+name)
        protected[name]=(rotation.T@(row['pos']-base),rotation.T@row['mat'])
    anchor(completed)
    def guard():
        state,contacts=policy.snapshot();base,rotation=policy.frame({'actor':'stand'})
        if not delivery and (np.linalg.norm(base-stand_pos)>.001 or np.linalg.norm(rotation-stand_rot)>STAND_ROTATION_MATRIX_LIMIT):
            raise ToolExecutionError('E17 actual stand moved during remaining local placements')
        for name,(p,r)in protected.items():
            row=state[name]
            if (any(row['grasp']) or frozenset((name,'stand'))not in contacts
                    or np.linalg.norm(rotation.T@(row['pos']-base)-p)>.002
                    or np.linalg.norm(rotation.T@row['mat']-r)>.02):
                raise ToolExecutionError('E17 previously completed stand piece changed: '+name)
    old_act=author.act;had='act'in author.__dict__;old_local=author.__dict__.get('act')
    def guarded(*args,**kwargs):
        guard();value=old_act(*args,**kwargs);guard();return value
    original_acquire=policy.acquire_chip_with_wrist_margin
    def acquire(ref,side):
        relevel_empty(policy,side)
        _tilted_triangle_reference(policy,ref['actor'])
        return original_acquire(policy.ref(ref['actor']),side)
    policy.acquire_chip_with_wrist_margin=acquire
    author.act=guarded
    try:
        from .execution_design_e17_insertion import front_lower_slot
        from .execution_design_e17_reference import collision_shelf_target
        # Do not call local_stage(): that would reopen/replay the lid and
        # already supported first piece. Execute only remaining original rows.
        for region in d['local_regions']:
            for index,name in enumerate(region['members']):
                if name==completed:continue
                if region['id']=='lower':
                    target=front_lower_slot(policy,index,len(region['members']))
                    policy.place_lower_shelf(name,region['actor'],target)
                else:
                    reviewed=policy.geometry['shelf_positions'][name]
                    target=[*reviewed[:2],policy.s['shelves'][region['id']]['center_local'][2]]
                    target=collision_shelf_target(policy,region['actor'],region['id'],target)
                    policy.place(name,region['actor'],target)
                anchor(name);guard()
        policy.package_stage();guard()
        delivery=True;policy.deliver();guard()
    finally:
        if had:author.act=old_local
        else:del author.act
    return dict(local_completed=True,operations=deepcopy(policy.operations),active_actions=policy.c.steps-policy.start)
