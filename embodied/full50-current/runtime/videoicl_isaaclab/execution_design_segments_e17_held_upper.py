"""At most30 public actions continuing actual held E17B triangle from native848."""
from copy import deepcopy
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .execution_design_expert import ExecutionDesignAuthor
from .execution_design_segments_e17 import STAND_ROTATION_MATRIX_LIMIT
from .realworld_tool_expert import ToolExecutionError


def run_segment(author,segment,parameters):
    boundaries={'e17_b_resume_held_upper_triangle_848':(848,84811,30),
                'e17_b_place_held_upper_from_hover_722':(722,72211,300)}
    if segment not in boundaries or not isinstance(parameters,dict)or parameters:
        raise ToolExecutionError('Pinned E17B848 held upper short entry with empty parameters required')
    steps,tick,budget=boundaries[segment]
    spec=author.scene.spec;d=spec.get('execution_design',{});cp=getattr(author,'_engineering_resume_checkpoint',{});source=cp.get('source',{})
    if (spec.get('id')!='E17'or spec.get('variant')!='B'or spec.get('seed')!=4201
            or d.get('revision')!=REVISION_V3 or d.get('condition')!='I'or d.get('source_sha256')!=source_sha256(REVISION_V3)
            or not author.control_report.get('engineering_reference_only')or not getattr(author,'_execution_design_reference_authorized',False)
            or author.smooth or cp.get('diagnostic_only')is not True or cp.get('state_quality')!='measured_native_state'
            or source.get('steps')!=steps or source.get('physics_ticks')!=tick):
        raise ToolExecutionError('Actual native E17B848 completed-action checkpoint required')
    p=ExecutionDesignAuthor(author);name='blue_triangle';ref=p.ref(name)
    from .execution_design_e17_stand import descriptor,native_readback
    actual=native_readback(author.scene)
    if (p.objects['stand'].get('e17_stand_geometry')!=descriptor()or not actual or actual.get('measured')is not True
            or actual.get('derived_geometry_sha256')!=descriptor()['derived_geometry_sha256']
            or actual.get('kinematic_enabled')is not False or actual.get('gravity_disabled')is not False):
        raise ToolExecutionError('Reviewed native dynamic stand required')
    if p.objects[name].get('source_asset',{}).get('sha256')!='caae5e783af9afae7ee6c1933e42a1654d746635873c7a1bb221ea4554a70e7b':
        raise ToolExecutionError('Original source blue triangle required')
    upper=[r for r in d['local_regions']if r['id']=='upper']
    if len(upper)!=1 or name not in upper[0]['members']:raise ToolExecutionError('Original blue upper-layer assignment required')
    base,rotation=p.frame({'actor':'stand'});base=base.copy();rotation=rotation.copy();state,contacts=p.snapshot();anchors={}
    for piece in ('blue_square','green_square'):
        row=state[piece]
        if any(row['grasp'])or frozenset((piece,'stand'))not in contacts:raise ToolExecutionError('Both previously placed lower squares require actual stand support')
        anchors[piece]=(rotation.T@(row['pos']-base),rotation.T@row['mat'])
    before=p.c.steps;carrying=True
    def guard():
        state,contacts=p.snapshot();position,rot=p.frame({'actor':'stand'})
        if np.linalg.norm(position-base)>.001 or np.linalg.norm(rot-rotation)>STAND_ROTATION_MATRIX_LIMIT:
            raise ToolExecutionError('E17 actual stand moved during held upper short segment')
        if any(row['grasp'][0]for row in state.values()):raise ToolExecutionError('E17 left hand must remain empty')
        for piece,(pos,mat)in anchors.items():
            row=state[piece]
            if (any(row['grasp'])or frozenset((piece,'stand'))not in contacts
                    or np.linalg.norm(rot.T@(row['pos']-position)-pos)>.002
                    or np.linalg.norm(rot.T@row['mat']-mat)>.02):
                raise ToolExecutionError('E17 previously placed lower square changed: '+piece)
        if carrying:
            p.require_held(ref,'right')
            if not all(frozenset((name,'right_finger'+str(i)))in contacts for i in(1,2)):
                raise ToolExecutionError('E17 held upper triangle requires actual bilateral contact')
    guard();old=author.act;had='act'in author.__dict__;previous=author.__dict__.get('act')
    def guarded(*args,**kwargs):
        if p.c.steps-before>=budget:raise ToolExecutionError('E17 held upper short segment exhausted'+str(budget)+' public actions')
        guard();value=old(*args,**kwargs);guard();return value
    author.act=guarded
    try:
        from .execution_design_e17_reference import collision_shelf_target,measured_shelf_release
        from .execution_design_segments_e17_upper import _check
        from .execution_design_e17_palm_escape import escape_to_default_tilt
        if steps==722:
            from .execution_design_segments_e17_remaining import _move
            bottom={'actor':name,'local':p.bottom_local(name)};point=p.point(bottom);height=max(1.12,float(point[2]))
            p.stage('local-e17b722-held-source-to-exterior-hover')
            _move(p,bottom,[*point[:2],height],payload=name,carrying=True)
            _move(p,bottom,[point[0],float(base[1]-.230),height],payload=name,carrying=True)
            _move(p,bottom,[float((base+rotation@np.array([-.044,-.046,0.]))[0]),float(base[1]-.230),height],payload=name,carrying=True)
        p.stage('local-e17b848-fixed-outward-palm-tilt')
        escape_to_default_tilt(p,name,guard)
        reviewed=np.array([-.044,-.046])
        vertices=np.array([[x,y,z]for x,y in[(-.02,-.017320508),(.02,-.017320508),(0.,.017320508)]for z in(-.003,.003)])
        body_rotation=p.frame({'actor':name})[1];envelope=vertices@body_rotation.T@rotation
        low=np.asarray(upper[0]['lower'])[:2]-envelope[:,:2].min(0)+.0005
        high=np.asarray(upper[0]['upper'])[:2]-envelope[:,:2].max(0)-.0005
        if np.any(low>=high):raise ToolExecutionError('Actual triangle cannot fit original upper region')
        reviewed=np.maximum(low,np.minimum(high,reviewed))  # planned goal only
        local=collision_shelf_target(p,'stand','upper',[*reviewed,p.s['shelves']['upper']['center_local'][2]])
        local=measured_shelf_release(p,name,'right','stand','upper',local);target=base+rotation@np.asarray(local)
        material={'actor':name,'local':p.bottom_local(name)};p.stage('local-e17b-held-upper-triangle-848')
        if steps==722:
            entry=target.copy();entry[1]=base[1]-.230
            _move(p,material,entry,payload=name,carrying=True)
            _move(p,material,target,payload=name,carrying=True)
        # Native848 is already over the original upper corner. Continue only
        # the remaining measured descent/alignment, never raise/replay transport.
        while True:
            guard();error=target-p.point(material)
            if np.max(abs(error))<=.002:break
            horizontal=np.flatnonzero(abs(error[:2])>.002)
            axis=int(horizontal[np.argmax(abs(error[horizontal]))])if len(horizontal)else 2
            delta=np.zeros(3);delta[axis]=np.sign(error[axis])*min(.010,abs(float(error[axis])))
            _check(p,p.tip('right')+delta,payload=name,wrist_only=True)
            token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
            old_tip=p.tip('right').copy();p.act('right',token,mm=abs(delta[axis])*1000)
            if np.max(abs(p.tip('right')-old_tip))<.0001:raise ToolExecutionError('E17 held upper public increment did not advance')
            _check(p,payload=name,wrist_only=True)
        _check(p,payload=name,wrist_only=True);carrying=False;p.release(ref,'right')
        state,contacts=p.snapshot();guard()
        if any(state[name]['grasp'])or frozenset((name,'stand'))not in contacts:
            raise ToolExecutionError('E17 upper triangle release lacks actual stand support')
    finally:
        if had:author.act=previous
        else:del author.act
    return dict(local_completed=True,operations=deepcopy(p.operations),active_actions=p.c.steps-before)
