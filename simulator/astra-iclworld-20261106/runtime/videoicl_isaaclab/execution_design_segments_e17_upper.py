"""One E17C blue upper placement from measured historical boundary490."""
from copy import deepcopy
import math
import numpy as np
from .execution_design_expert import ExecutionDesignAuthor
from .execution_design import REVISION_V3,source_sha256
from .realworld_tool_expert import ToolExecutionError


def _native_parts(policy):
    """Keep native collision prims separate, including generated Cube walls."""
    from pxr import Usd,UsdGeom,UsdPhysics
    import omni.usd
    author=policy.a
    if not hasattr(author,'_e17_upper_collision_parts'):
        stage=omni.usd.get_context().get_stage();xforms=UsdGeom.XformCache();cache={}
        corners=np.array([[x,y,z]for x in(-1,1)for y in(-1,1)for z in(-1,1)],float)
        for name in policy.objects:
            root=stage.GetPrimAtPath(author.scene.root_path+'/Props/'+name)
            if not root:raise ToolExecutionError('Missing E17 native collision actor '+name)
            inverse=xforms.GetLocalToWorldTransform(root).GetInverse();parts=[]
            for prim in Usd.PrimRange(root,Usd.TraverseInstanceProxies()):
                if not prim.IsA(UsdGeom.Gprim):continue
                parent=prim;enabled=False
                while parent:
                    if parent.HasAPI(UsdPhysics.CollisionAPI):
                        enabled=UsdPhysics.CollisionAPI(parent).GetCollisionEnabledAttr().Get()is not False;break
                    if parent==root:break
                    parent=parent.GetParent()
                if not enabled:continue
                if prim.IsA(UsdGeom.Cube):
                    local=[corners*float(UsdGeom.Cube(prim).GetSizeAttr().Get())/2]
                elif prim.IsA(UsdGeom.Mesh):
                    mesh=UsdGeom.Mesh(prim);points=np.asarray(mesh.GetPointsAttr().Get(),float)
                    mode=UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get()
                    if mode=='none':
                        local=[];offset=0;indices=mesh.GetFaceVertexIndicesAttr().Get()
                        for count in mesh.GetFaceVertexCountsAttr().Get():
                            if count!=3:raise ToolExecutionError('E17 native triangle face required')
                            local.append(points[list(indices[offset:offset+count])]);offset+=count
                    elif mode in('convexHull','convexDecomposition'):local=[points]
                    else:raise ToolExecutionError('Unreviewed E17 native mesh collider')
                else:raise ToolExecutionError('Unreviewed E17 native collider primitive')
                t=np.asarray(xforms.GetLocalToWorldTransform(prim)*inverse,float)
                parts.extend(points@t[:3,:3]+t[3,:3]for points in local)
            if not parts:raise ToolExecutionError('Empty E17 native collision actor '+name)
            cache[name]=parts
        author._e17_upper_collision_parts=cache
    state,_=policy.snapshot();result=[]
    for name,parts in author._e17_upper_collision_parts.items():
        row=state[name]
        for index,points in enumerate(parts):
            p=points@np.asarray(row['mat']).T+row['pos']
            result.append(dict(actor=name,name=name+'/'+str(index),points=p,lo=p.min(0),hi=p.max(0)))
    return result


def _check(policy,point=None,*,carrying=True,payload='blue_square',wrist_only=False,rotation=None,ignored_components=(),maximum_swept_bound_m=None):
    """Reject a next small public increment near the unchanged native colliders."""
    from scipy.optimize import least_squares
    from .execution_design_e24_transit import capture_model,screen_joint_segment
    from .execution_design_drawer_ik_probe import forward_at_delta
    from .author_orientation import _axis_angle
    model,_=capture_model(policy,'right');idle,_=capture_model(policy,'left');parts=_native_parts(policy)
    # Released blue contact is intentional during the single upward exit.
    env=[r for r in parts if r['actor']!=payload and r['name']not in ignored_components]
    for i,f in enumerate(policy.spec.get('fixtures',[])):
        if f.get('type')!='box':raise ToolExecutionError('Unreviewed E17 fixture collider')
        center=np.array([*f['xy'],f['z']],float);half=np.asarray(f['size'],float)
        env.append(dict(name='fixture'+str(i),lo=center-half,hi=center+half))
    from .execution_design_e24_lid import table_bounds
    low,high=table_bounds(policy);env.append(dict(name='table',lo=low,hi=high))
    env.extend(dict(name='left:'+c['name'],points=c['points'],lo=c['points'].min(0),hi=c['points'].max(0))for c in idle['clouds'])
    if wrist_only:
        names={'panda_link7','panda_hand','panda_leftfinger','panda_rightfinger'}
        model=dict(model,clouds=[c for c in model['clouds']if c['name']in names])
    if carrying:
        model['clouds']=model['clouds']+[dict(name='held:'+r['name'],influence=7,points=r['points'])for r in parts if r['actor']==payload]
    q=model['q'];candidate=q
    if point is not None or rotation is not None:
        point=model['position']if point is None else point
        desired_rotation=model['rotation']if rotation is None else np.asarray(rotation,float)
        lo=model['limits'][:,0]+.05;hi=model['limits'][:,1]-.05
        if np.any(q<=lo)or np.any(q>=hi):raise ToolExecutionError('E17 actual arm lacks native joint margin')
        def residual(value):
            p,r=forward_at_delta(model['position'],model['rotation'],model['jacobian'],value-q)
            axis,angle=_axis_angle(desired_rotation@r.T)
            return np.r_[10*(p-point),axis*angle,.005*(value-q)]
        fit=least_squares(residual,q,bounds=(lo,hi),max_nfev=100)
        error=residual(fit.x)
        if np.linalg.norm(error[:3])/10>=.001 or np.linalg.norm(error[3:6])>=math.radians(1.5)or np.max(abs(fit.x-q))>=.15:
            raise ToolExecutionError('E17 upper next public increment has no nearby IK')
        candidate=fit.x
    if maximum_swept_bound_m is not None:
        # A released palm has a measured~3mm cap gap. Refine the unchanged
        # swept proof there rather than enlarging its2mm solid clearance.
        if maximum_swept_bound_m!=.0005:raise ToolExecutionError('Reviewed E17 short swept bound required')
        from .execution_design_e24_transit import swept_vertex_bound
        largest=max(swept_vertex_bound(model,c,candidate-q)for c in model['clouds'])
        count=max(1,int(math.ceil(largest/maximum_swept_bound_m)))
        if count>4000:raise ToolExecutionError('E17 refined short segment has excessive joint travel')
        return [screen_joint_segment(model,q+(candidate-q)*(i/count),q+(candidate-q)*((i+1)/count),env,margin=.002)for i in range(count)]
    return screen_joint_segment(model,q,candidate,env,margin=.002)


def _move(policy,material,target,*,carrying=True):
    target=np.asarray(target,float)
    for _ in range(500):
        current=policy.point(material)if material is not None else policy.tip('right');error=target-current
        if np.max(abs(error))<=.002:return
        i=int(np.argmax(abs(error)));distance=min(.004,abs(float(error[i])));delta=np.zeros(3);delta[i]=math.copysign(distance,error[i])
        _check(policy,policy.tip('right')+delta,carrying=carrying)
        token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[i][int(error[i]<0)]
        before=policy.tip('right').copy();policy.act('right',token,mm=distance*1000)
        feedback=policy.c.action_feedback().get('control_feedback',{}).get('right',{})
        if feedback.get('status')=='blocked'or feedback.get('joint_limit_names')or feedback.get('consecutive_ik_refusals',0)>0:
            raise ToolExecutionError('E17 upper public controller rejected the increment')
        if np.max(abs(policy.tip('right')-before))<.0001:raise ToolExecutionError('E17 upper public move failed to advance')
        _check(policy,carrying=carrying)
    raise ToolExecutionError('E17 upper short segment waypoint exhausted')


def run_segment(author,segment,parameters):
    if segment!='e17_c_place_held_blue_upper_south'or not isinstance(parameters,dict)or parameters:
        raise ToolExecutionError('Explicit E17C blue upper short segment with empty parameters required')
    spec=author.scene.spec;d=spec.get('execution_design',{});cp=getattr(author,'_engineering_resume_checkpoint',{});source=cp.get('source',{})
    if (spec.get('id')!='E17'or spec.get('variant')!='C'or spec.get('seed')!=4201 or d.get('condition')!='I'
            or d.get('revision')!=REVISION_V3 or d.get('source_sha256')!=source_sha256(REVISION_V3)
            or not author.control_report.get('engineering_reference_only')or not getattr(author,'_execution_design_reference_authorized',False)
            or author.smooth or cp.get('diagnostic_only')is not True or source.get('steps')!=490 or source.get('physics_ticks')!=49840):
        raise ToolExecutionError('Pinned E17C490 independent diagnostic boundary required')
    policy=ExecutionDesignAuthor(author)
    from .execution_design_e17_stand import descriptor,native_readback
    actual=native_readback(author.scene)
    if (policy.objects['stand'].get('e17_stand_geometry')!=descriptor()or not actual or actual.get('measured')is not True
            or actual.get('derived_geometry_sha256')!=descriptor()['derived_geometry_sha256']
            or actual.get('kinematic_enabled')is not False or actual.get('gravity_disabled')is not False):
        raise ToolExecutionError('E17 live reviewed stand geometry/dynamics required')
    upper=[r for r in d['local_regions']if r['id']=='upper']
    if len(upper)!=1 or 'blue_square'not in upper[0]['members']:raise ToolExecutionError('Original upper blue assignment required')
    obj=policy.objects['blue_square']
    if obj.get('source_asset',{}).get('sha256')!='fed57b9b0e69a5b8b98d75324ed6856c0cdb21ebc56c8f98cb372670255b61bb':
        raise ToolExecutionError('Original source blue square geometry required')
    ref=policy.ref('blue_square');base,rotation=policy.frame({'actor':'stand'});base=base.copy();rotation=rotation.copy()
    if np.linalg.norm(base-[.04,.05,.8])>.003 or np.linalg.norm(rotation-np.eye(3))>.025:
        raise ToolExecutionError('E17 stand is not at the uncollided source boundary')
    carrying=True
    def guard():
        state,contacts=policy.snapshot();p,r=policy.frame({'actor':'stand'})
        if np.linalg.norm(p-base)>.002 or np.linalg.norm(r-rotation)>.02 or any(frozenset(('stand',f'{hand}_finger{i}'))in contacts for hand in('left','right')for i in(1,2)):
            raise ToolExecutionError('E17 upper actual stand moved or has robot contact')
        if any(v['grasp'][0]for v in state.values()):raise ToolExecutionError('E17 upper left hand must remain empty')
        if carrying:
            policy.require_held(ref,'right')
            if not all(frozenset(('blue_square','right_finger'+str(i)))in contacts for i in(1,2)):
                raise ToolExecutionError('E17 upper blue requires actual bilateral grip')
        if float(state['blue_square']['mat'][2,2])<.98:raise ToolExecutionError('E17 upper source blue must remain near horizontal')
    guard();before=policy.c.steps;old_act=author.act;had='act'in author.__dict__;old_local=author.__dict__.get('act')
    def guarded(*args,**kwargs):
        guard();value=old_act(*args,**kwargs);guard();return value
    author.act=guarded
    try:
        from .execution_design_e17_reference import collision_shelf_target,measured_shelf_release
        local=collision_shelf_target(policy,'stand','upper',[-.044,-.044,0.])
        local=measured_shelf_release(policy,'blue_square','right','stand','upper',local)
        goal=base+rotation@np.asarray(local);entry=base+rotation@np.array([-.044,-.230,local[2]])
        bottom={'actor':'blue_square','local':policy.bottom_local('blue_square')}
        current=policy.point(bottom);high=max(1.12,float(current[2]),float(goal[2])+.05)
        policy.stage('local-e17-upper-blue-south-carry')
        _move(policy,bottom,[*current[:2],high])
        _move(policy,bottom,[current[0],entry[1],high])
        _move(policy,bottom,[entry[0],entry[1],high])
        policy.stage('local-e17-upper-blue-south-insert')
        _move(policy,bottom,entry);_move(policy,bottom,goal);_check(policy)
        carrying=False;policy.release(ref,'right')
        state,contacts=policy.snapshot()
        if any(state['blue_square']['grasp'])or frozenset(('blue_square','stand'))not in contacts:
            raise ToolExecutionError('E17 released upper blue lacks actual stand support')
        # This local goal ends at real released stand support. An optional
        # empty-arm exit is a different suffix and must not erase that result.
        guard()
    finally:
        if had:author.act=old_local
        else:del author.act
    return dict(local_completed=True,operations=deepcopy(policy.operations),active_actions=policy.c.steps-before)
