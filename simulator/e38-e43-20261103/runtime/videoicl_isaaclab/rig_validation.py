"""Maintainer-only checks of native joints, optical mounts and counted actions."""
import json
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from isaaclab.utils.math import combine_frame_transforms,quat_apply,matrix_from_quat
from .demonstration import Demonstration


def check_rig(c,out):
    scene=c.scene;profile=scene.embodiment;out=Path(out)
    report=dict(embodiment=profile.name,config_sha256=profile.config_hash,validation_only=True,
        full_task_solved=False,checks=[],motions=[],gripper={})
    def check(name,passed,**data):report['checks'].append(dict(name=name,passed=bool(passed),**data))
    def tcp(side):
        r=scene.robots[side];bid=c.ids[side][2]
        return (r.data.body_pos_w[:,bid]+quat_apply(r.data.body_quat_w[:,bid],torch.tensor([profile.tcp],device=c.device)))[0].clone()
    def capture(name):
        for _ in range(3):c.sim.render();scene.update(0.)
        for key in ('head','left_wrist','right_wrist','overview'):
            Image.fromarray(scene.cameras[key].data.output['rgb'][0,:,:,:3].cpu().numpy()).save(out/(name+'-'+key+'.png'))
    def cameras(label):
        for side,r in scene.robots.items():
            ids,_=r.find_bodies(profile.camera_link);bid=ids[0]
            pos,q=combine_frame_transforms(r.data.body_pos_w[:,bid],r.data.body_quat_w[:,bid],
                torch.tensor([profile.camera_position],device=c.device,dtype=torch.float32),torch.tensor([profile.camera_rotation],device=c.device))
            camera=scene.cameras[side+'_wrist'];actual=camera.data
            distance=float((actual.pos_w-pos).norm())
            # All checked native profiles store the OpenGL optical convention.
            angle=float(2*torch.acos(torch.abs((actual.quat_w_opengl*q).sum()).clamp(max=1.)))
            check(label+'-'+side+'-optical-pose',distance<1e-5 and angle<.002,error_m=distance,error_rad=angle)
            point=matrix_from_quat(actual.quat_w_opengl)[0].T@(tcp(side)-actual.pos_w[0])
            k=actual.intrinsic_matrices[0];depth=float(-point[2])
            pixel=[float(k[0,2]+k[0,0]*point[0]/depth),float(k[1,2]-k[1,1]*point[1]/depth)]
            report.setdefault('tcp_projection',{})[label+'-'+side]=dict(depth_m=depth,pixel=pixel,
                near_clip_m=profile.config['cameras']['wrist']['intrinsics']['clipping_range'][0])
    for side,r in scene.robots.items():
        check(side+'-native-joints',set(profile.arm_joints+profile.finger_joints)<=set(r.joint_names))
        check(side+'-native-links',set([profile.hand,profile.camera_link,*profile.fingers])<=set(r.body_names))
    import omni.usd
    from pxr import Usd,UsdGeom
    stage=omni.usd.get_context().get_stage()
    cache=UsdGeom.BBoxCache(Usd.TimeCode.Default(),['default','render','proxy','guide'],False,True)
    for side,r in scene.robots.items():
        for name in r.body_names:
            body=stage.GetPrimAtPath(f'/World/{side}_robot/{name}')
            visuals=body.GetChild('visuals');collisions=body.GetChild('collisions')
            if not visuals or not collisions:continue
            a=cache.ComputeRelativeBound(visuals,body).ComputeAlignedRange()
            b=cache.ComputeRelativeBound(collisions,body).ComputeAlignedRange()
            if a.IsEmpty() or b.IsEmpty():continue
            difference=float(np.max(np.abs(np.array([list(a.GetMin()),list(a.GetMax())])-np.array([list(b.GetMin()),list(b.GetMax())]))))
            check(side+'-'+name+'-visual-collision-alignment',difference<.025,bounds_difference_m=difference)
    movie=Demonstration(c,out,video_prefix='rig-motion')
    try:
        capture('initial');cameras('initial')
        before={s:tcp(s) for s in scene.robots}
        c.action('STILL','STILL')
        hold={s:float((tcp(s)-before[s]).norm()) for s in scene.robots}
        check('idle-hold',max(hold.values())<.001,error_m=hold)
        for token,sign in [('UP',1),('DOWN',-1)]:
            before={s:tcp(s) for s in scene.robots};receipt=c.action(token,token,7.5)
            expected=torch.tensor(scene.layout.task_rotation@np.array([0,0,sign*.0075]),device=c.device)
            displacement={s:(tcp(s)-before[s]).cpu().tolist() for s in scene.robots}
            errors={s:float((tcp(s)-before[s]-expected).norm()) for s in scene.robots}
            report['motions'].append(dict(token=token,receipt=receipt,displacement_m=displacement,error_m=errors))
            check('both-arms-'+token,max(errors.values())<.002,error_m=errors)
        capture('moved');cameras('moved')
        for state,command,opening in [('closed','GRASP',0.),('open','RELEASE',1.)]:
            for _ in range(4):c.action(command,command)
            report['gripper'][state]={}
            for side,r in scene.robots.items():
                ids=c.ids[side][1];actual=r.data.joint_pos[0,ids]
                expected=torch.tensor(profile.gripper_values(opening),device=c.device)
                limits=r.data.joint_pos_limits[0,ids];expected=expected.clamp(limits[:,0],limits[:,1])
                error=float((actual-expected).abs().max())
                report['gripper'][state][side]=dict(actual=actual.cpu().tolist(),expected=expected.cpu().tolist(),error_m=error)
                check(side+'-gripper-'+state,error<.003,error_m=error)
            capture(state)
        for side in scene.robots:
            delta=np.array(report['gripper']['open'][side]['actual'])-report['gripper']['closed'][side]['actual']
            intended=np.array(profile.gripper_values(1.))-profile.gripper_values(0.)
            check(side+'-both-fingers-move',np.all(delta*intended>0) and np.min(np.abs(delta))>.015,displacement_m=delta.tolist())
        paused=float(c.sim.current_time)
        for _ in range(12):c.sim.render();scene.update(0.)
        check('render-pauses-physics',float(c.sim.current_time)==paused)
    finally:movie.close()
    report['passed']=all(x['passed'] for x in report['checks']);report['steps']=c.steps
    (out/'rig_check.private.json').write_text(json.dumps(report,indent=2)+'\n')
    print('VIDEOICL_RIG_CHECK '+json.dumps(report),flush=True)
    if not report['passed']:raise RuntimeError('Native rig QA failed; see rig_check.private.json')
