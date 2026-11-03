"""Small measured yaw correction of the genuinely loaded E39 tray."""
from itertools import product
import json
import math
import numpy as np

from .realworld_tool_expert import ToolExecutionError, _axis_rotation


def yaw_error(current, target):
    a=math.atan2(float(current[1,0]),float(current[0,0]))
    b=math.atan2(float(target[1,0]),float(target[0,0]))
    return math.atan2(math.sin(b-a),math.cos(b-a))


def insertion_width_fits(policy,container):
    package=next(p for p in policy.d['packages']if p['container']==container)
    relative=np.asarray(policy.frame(dict(actor=container))[1]).T@np.asarray(policy.frame(dict(actor='work_tray'))[1])
    width=2.*np.abs(relative[:2])@np.asarray(policy.objects['work_tray']['size'])
    opening=(np.asarray(package['upper'])-np.asarray(package['lower']))[:2]
    return bool(np.all(width<=opening-.002))


def align_loaded_yaw(policy,container,side='left',maximum_degrees=3.,*,functional_insertion=False):
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_e39_delivery import _static_obstacles
    from .execution_design_e39_package import _native_route,body_bounds
    from .execution_design_clip_handover import public_rotation_poses,rotation_clear
    from .execution_design_thin_edge import table_bounds_task
    if policy.task!='E39'or side!='left'or not policy.a.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('Loaded E39 yaw correction requires its real engineering left grip')
    carried={'work_tray',*policy.d['target_members']};ref=policy.ref('work_tray')
    initial=policy.snapshot()[0]
    references={n:(np.asarray(initial[n]['pos']),np.asarray(initial[n]['mat']))for n in policy.d['reference_objects']}
    def guard():
        policy.require_held(ref,side);state,contacts=policy.snapshot()
        if any(frozenset((n,'work_tray'))not in contacts for n in policy.d['target_members']):
            raise ToolExecutionError('Loaded E39 yaw correction lost actual carried support')
        for n,(p,r)in references.items():
            if np.linalg.norm(np.asarray(state[n]['pos'])-p)>.002 or np.linalg.norm(np.asarray(state[n]['mat'])-r)>.02:
                raise ToolExecutionError('Loaded E39 yaw correction disturbed a protected reference')
    target=np.asarray(policy.frame(dict(actor=container))[1]);no_motion=0
    for _ in range(6):
        guard();current=np.asarray(policy.frame(dict(actor='work_tray'))[1]);delta=yaw_error(current,target)
        if insertion_width_fits(policy,container)if functional_insertion else abs(math.degrees(delta))<=.6:return
        if abs(math.degrees(delta))>maximum_degrees:
            raise ToolExecutionError('Loaded E39 tray needs more than the reviewed small yaw correction')
        # Public rotation tolerance is one degree. Compensate its measured
        # stopping band rather than issuing a sub-tolerance no-op repeatedly.
        degrees=min(maximum_degrees,abs(math.degrees(delta))+(0. if functional_insertion else .8))
        signed=math.copysign(degrees,delta);tcp=policy.tip(side);rotation=np.asarray(policy.a.tcp_rotation_task(side))
        desired=_axis_rotation([0,0,1],math.radians(signed))@rotation
        meshes=[actual_mesh(policy.a,side,n)for n in ('panda_hand',*policy.a.scene.embodiment.fingers)]
        for n in carried:
            lo,hi=body_bounds(policy,n);meshes.append(np.asarray(list(product(*zip(lo,hi)))))
        local=[(mesh-tcp)@rotation for mesh in meshes]
        obstacles=_static_obstacles(policy,carried)
        obstacles.extend(actual_mesh(policy.a,'right',n)for n in ('panda_hand',*policy.a.scene.embodiment.fingers))
        poses=public_rotation_poses(tcp,rotation,desired)
        if not rotation_clear(local,tcp,rotation,poses,obstacles,table_bounds_task(policy.a.scene)['top']):
            raise ToolExecutionError('Loaded E39 small yaw lacks actual assembly sweep clearance')
        _native_route(policy,side,desired,[tcp],'loaded-tray-small-yaw-before-box-alignment')
        policy.stage('e39-loaded-tray-small-yaw')
        policy.act(side,'ROTATE_CCW'if signed>0 else'ROTATE_CW',degrees=degrees)
        guard();after=yaw_error(np.asarray(policy.frame(dict(actor='work_tray'))[1]),target)
        with (policy.a.out/'e39-loaded-yaw.private.jsonl').open('a')as f:
            f.write(json.dumps(dict(before_error_deg=math.degrees(delta),after_error_deg=math.degrees(after),
                                   requested_rotation_deg=signed,actual_mesh_sweep_and_native_J_checked=True))+'\n')
        no_motion=no_motion+1 if abs(delta-after)<math.radians(.03)else 0
        if no_motion>=2:raise ToolExecutionError('Loaded E39 yaw commands made no actual rotation')
    raise ToolExecutionError('Loaded E39 small yaw correction did not converge')


def center_for_insertion(policy,container):
    """Only real physical aperture containment; no extra center target."""
    from .execution_design_e39_reference import assembly_contained_xy
    from .execution_design_e39_package import _native_route
    from .execution_design_e39_package import body_bounds
    from .execution_design_e39_delivery import _screen_translations
    from .execution_design_e33_grasp import actual_mesh
    side='left';ref=policy.ref('work_tray');policy.require_held(ref,side)
    box_p,box_r=policy.frame(dict(actor=container));last=None;bias=0.
    for _ in range(8):
        if assembly_contained_xy(policy,container,tolerance=0.):return
        tray_p,_=policy.frame(dict(actor='work_tray'))
        error=box_p-tray_p;axis=int(np.argmax(abs(error[:2])))
        before=float(tray_p[axis]);sign=1 if error[axis]>0 else-1
        amount=min(10.,abs(float(error[axis]))*1000+bias)
        tcp=policy.tip(side);goal=tcp.copy();goal[axis]+=sign*amount/1000
        rotation=np.asarray(policy.a.tcp_rotation_task(side))
        _native_route(policy,side,rotation,[tcp,goal],'measured-tray-aperture-centering')
        carried={'work_tray',*policy.d['target_members']}
        meshes=[actual_mesh(policy.a,side,n)for n in ('panda_hand',*policy.a.scene.embodiment.fingers)]
        for name in carried:
            lo,hi=body_bounds(policy,name);meshes.append(np.asarray(list(product(*zip(lo,hi)))))
        local=[(m-tcp)@rotation for m in meshes]
        _screen_translations(policy,side,local,rotation,[tcp,goal],carried)
        policy.stage('e39-real-aperture-centering')
        policy.act(side,(('FWD','BACK'),('LEFT','RIGHT'))[axis][int(sign<0)],mm=amount)
        policy.require_held(ref,side);after=float(policy.frame(dict(actor='work_tray'))[0][axis])
        bias=float(np.clip(amount-sign*(after-before)*1000,0.,4.))
        if last is not None and abs(after-before)<.00001:raise ToolExecutionError('E39 physical aperture centering made no progress')
        last=after
    raise ToolExecutionError('E39 measured assembly does not fit the actual box aperture')
