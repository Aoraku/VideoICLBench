"""E18 engineering: select a whole-cabinet-clear closed fingertip approach."""
import hashlib,os
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from scipy.optimize import linprog
from .realworld_mechanism_expert import MechanismExecutionError


def cabinet_clouds(worker):
    from pxr import Usd,UsdGeom,UsdPhysics
    from .execution_design_e18_support import SOURCE_SHA
    cabinet=next(x for x in worker.spec['mechanisms']if x['id']=='cabinet')
    record=cabinet['mechanical_asset']
    path=Path(os.environ[record.get('root_env','VIC_MECHANISM_ASSETS')])/record['relative_path']
    if record['sha256']!=SOURCE_SHA or hashlib.sha256(path.read_bytes()).hexdigest()!=SOURCE_SHA or cabinet.get('yaw',0)!=0:
        raise ValueError('Pinned original E18 cabinet required')
    stage=Usd.Stage.Open(str(path));cache=UsdGeom.XformCache();result=[]
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh)or not prim.HasAPI(UsdPhysics.CollisionAPI):continue
        if UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()is False:continue
        points=np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(),float)
        matrix=np.asarray(cache.GetLocalToWorldTransform(prim),float)
        points=points@matrix[:3,:3]+matrix[3,:3]+np.asarray(cabinet['position'])
        if 'Left_link_1'in str(prim.GetPath()):points+=worker.axis('drawer')*worker.displacement('drawer')
        result.append(points)
    if len(result)!=32:raise ValueError('All original E18 cabinet collision pieces required')
    return result


def obstacles(clouds):
    return [(c.min(0),c.max(0),ConvexHull(c).equations)for c in clouds]


def intersects(points,parts,margin=.0015):
    low=points.min(0);high=points.max(0);hull=None
    for lo,hi,equations in parts:
        if np.any(high<lo-margin)or np.any(low>hi+margin):continue
        if hull is None:hull=ConvexHull(points).equations
        solution=linprog([0.,0.,0.],A_ub=np.r_[hull[:,:3],equations[:,:3]],
            b_ub=np.r_[-hull[:,3],-equations[:,3]]+margin,bounds=[(None,None)]*3,method='highs')
        if solution.success:return True
        if solution.status!=2:raise MechanismExecutionError('E18 cabinet geometry query failed')
    return False


def choose_cap_target(ball,clouds,parts):
    point=np.asarray(ball,float);fingers=np.concatenate(clouds[:2])
    for rear in (.004,.008,.012):
        for dy in (0.,-.006,.006):
            for cap in (.007,.011,.004):
                target=np.array([point[0]+rear-fingers[:,0].max(),point[1]+dy,
                    point[2]+cap-fingers[:,2].min()])
                if min(float((c+target)[:,2].min())for c in clouds)<.849:continue
                if not any(intersects(c+target,parts)for c in clouds):return target
    raise MechanismExecutionError('E18 current closed wrist has no whole-cabinet-clear upper-cap approach')


def run_segment(author,entry,parameters):
    cp=getattr(author,'_engineering_resume_checkpoint',{});spec=author.scene.spec
    if (entry!='e18_closed_cap_from3'or parameters!={}or
        (spec['id'],spec['variant'],spec['seed'])!=('E18','A',4201)or
        (cp.get('source',{}).get('steps'),cp.get('source',{}).get('physics_ticks'))!=(3,311)or
        not author.control_report.get('engineering_reference_only')or
        not getattr(author.c,'_engineering_diagnostic_only',False)or
        not getattr(author.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Explicit original E18 closed3 diagnostic required')
    from .execution_design_e18_reference import E18MeasuredAuthor
    from .execution_design_e18_geometry import actual_hand_clouds
    from .execution_design_e18_ball_roll import move_checked,tilt_empty_pusher
    from .realworld_tool_expert import _axis_rotation
    import json
    worker=E18MeasuredAuthor(author,allow_existing_e18_drawer=True);worker.max_actions=200
    side='left';name='red';opening=worker.displacement('drawer');start=worker.c.steps
    def guard():
        state,_=worker.c.snapshot()
        if worker.displacement('drawer')<opening-.005:raise MechanismExecutionError('E18 closed cap pushed drawer inward')
        if any(any(state[n]['grasp'])for n in ('green','blue')):raise MechanismExecutionError('E18 closed cap acquired wrong sphere')
    geometry=actual_hand_clouds(author,side);rotation=np.asarray(author.tcp_rotation_task(side),float)
    turn=_axis_rotation([0.,0.,1.],np.pi/2);proposed=turn@rotation
    clouds=[np.asarray(c)@proposed.T for c in geometry['clouds_tcp']]
    parts=obstacles(cabinet_clouds(worker));state,_=worker.c.snapshot();ball=np.asarray(state[name]['pos'],float)
    choose_cap_target(ball,clouds,parts)
    worker.stage('E18-closed-wrist-sideway-above-full-cabinet')
    move_checked(worker,side,[*worker.tip(side)[:2],1.03],tolerance=.006,guard=guard)
    tilt_empty_pusher(worker,side,proposed,guard,max_attempts=70)
    geometry=actual_hand_clouds(author,side);rotation=np.asarray(author.tcp_rotation_task(side),float)
    clouds=[np.asarray(c)@rotation.T for c in geometry['clouds_tcp']]
    state,_=worker.c.snapshot();ball=np.asarray(state[name]['pos'],float)
    target=choose_cap_target(ball,clouds,obstacles(cabinet_clouds(worker)))
    (author.out/'e18-whole-cabinet-cap-plan.private.json').write_text(json.dumps(dict(
        selected_ball_task=ball.tolist(),target_task=target.tolist(),source_collision_piece_count=32,
        hand_floor_minimum_m=min(float((c+target)[:,2].min())for c in clouds),native_grip_verified=False))+'\n')
    worker.stage('E18-closed-cap-short-physical-pinch')
    move_checked(worker,side,[*target[:2],worker.tip(side)[2]],tolerance=.002,guard=guard)
    move_checked(worker,side,target,tolerance=.002,guard=guard,max_step_mm=4.)
    worker.act(side,'GRASP');guard();before=np.asarray(worker.c.snapshot()[0][name]['pos'],float)
    move_checked(worker,side,worker.tip(side)+[0.,0.,.012],tolerance=.002,guard=guard,max_step_mm=4.)
    state,_=worker.c.snapshot();rise=float(state[name]['pos'][2]-before[2])
    if not state[name]['grasp'][0]or rise<.005:raise MechanismExecutionError('E18 real closed-cap pinch did not lift selected sphere')
    return dict(local_completed=True,selected_ball=name,actual_grip=True,actual_liftoff_m=rise,actions=worker.c.steps-start)
