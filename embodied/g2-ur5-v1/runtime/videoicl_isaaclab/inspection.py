"""Private QA: actual box intersections, wall impacts and wrist projections."""
import json
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from pxr import Usd, UsdGeom
import omni.usd
from isaaclab.utils.math import quat_apply, matrix_from_quat


def box_overlap(a, ra, ha, b, rb, hb):
    """Separating-axis intersection depth; zero means separated/touching."""
    axes = [*ra.T, *rb.T, *(np.cross(x, y) for x in ra.T for y in rb.T)]
    axes = np.asarray([x/np.linalg.norm(x) for x in axes if np.linalg.norm(x) > 1e-7])
    overlap = np.abs(axes @ ra) @ ha + np.abs(axes @ rb) @ hb - np.abs(axes @ (b-a))
    return max(0., float(overlap.min()))


def intersections(controller):
    shapes = {}
    for spec in controller.scene.spec['objects']:
        obj = controller.scene.objects[spec['id']]
        pos = obj.data.root_pos_w[0].cpu().numpy()
        rot = matrix_from_quat(obj.data.root_quat_w)[0].cpu().numpy()
        shapes[spec['id']] = [(pos+rot @ np.asarray(g.get('pos', [0, 0, 0])), rot,
                              np.asarray(g['size'])) for g in spec['collision_shapes']]
    names = list(shapes); worst = dict(depth_m=0., pair=None)
    for i, name in enumerate(names):
        for other in names[i+1:]:
            for a, ra, ha in shapes[name]:
                for b, rb, hb in shapes[other]:
                    if np.any(np.abs(a-b) > np.abs(ra) @ ha + np.abs(rb) @ hb):
                        continue
                    depth = box_overlap(a, ra, ha, b, rb, hb)
                    if depth > worst['depth_m']:
                        worst = dict(depth_m=depth, pair=[name, other])
    return worst


def check_environment(controller, out):
    """F22-only independent diagnostic. Never run against an assigned episode."""
    c = controller; scene = c.scene; out = Path(out)
    if scene.spec['id'] != 'F22':
        raise ValueError('Container impact QA is currently defined for F22 only')
    initial = {n: o.data.root_state_w.clone() for n, o in scene.objects.items()}
    report = dict(validation_only=True, initial_intersections=intersections(c), impacts=[])
    robot_initial = {s: r.data.joint_pos.clone() for s, r in scene.robots.items()}
    targets_initial = {s: tuple(t.clone() for t in pair) for s, pair in c.targets.items()}

    def restore():
        for name, obj in scene.objects.items():
            obj.write_root_state_to_sim(initial[name])
        for side, robot in scene.robots.items():
            robot.write_joint_state_to_sim(robot_initial[side], torch.zeros_like(robot_initial[side]))
            c.targets[side] = tuple(t.clone() for t in targets_initial[side])
        scene.update(c.dt)

    # An isolated impulse/drop test intentionally initializes one cube at each
    # wall. This is a QA fixture, never a demonstration or evaluated trajectory.
    for axis, sign in [(0, -1), (0, 1), (1, -1), (1, 1)]:
        restore()
        tray = scene.objects['upper']; cube = scene.objects['upper_piece1']
        tray_spec=next(o for o in scene.spec['objects'] if o['id']=='upper')
        cube_spec=next(o for o in scene.spec['objects'] if o['id']=='upper_piece1')
        extent=tray_spec['inner_size'][axis];half=cube_spec['size'][axis]
        # Isolate wall contact from cube-cube impacts, in this disposable world.
        for i in (0,2):
            other=scene.objects['upper_piece'+str(i)]
            parked=initial['upper_piece'+str(i)].clone();parked[:, :3]=torch.tensor([2.+i,2.,1.],device=c.device);parked[:,7:]=0.
            other.write_root_state_to_sim(parked)
        state = initial['upper_piece1'].clone()
        tray_rotation=matrix_from_quat(tray.data.root_quat_w)[0]
        shift=torch.zeros(3,device=c.device);shift[axis]=sign*(extent-half-.025)
        state[:, :3] = tray.data.root_pos_w + (tray_rotation@shift)[None,:]
        # Keep the cube on its original floor rather than at the tray center.
        state[:,2]=initial['upper_piece1'][:,2]
        state[:, 7:] = 0.
        direction=torch.zeros(3,device=c.device);direction[axis]=sign*1.0
        state[:,7:10]=(tray_rotation@direction)[None,:]
        cube.write_root_state_to_sim(state);scene.update(c.dt)
        maximum = dict(depth_m=0., pair=None); crossed = False; contact = False;nearest_wall=1.
        for i in range(round(1/c.dt)):
            c.tick(render=i % round(1/(15*c.dt)) == 0)
            overlap = intersections(c)
            if overlap['depth_m'] > maximum['depth_m']: maximum = overlap
            pose = matrix_from_quat(tray.data.root_quat_w)[0]
            local = pose.T @ (cube.data.root_pos_w[0]-tray.data.root_pos_w[0])
            clearance=extent-sign*local[axis].item()-half
            nearest_wall=min(nearest_wall,clearance)
            crossed |= bool(sign*local[axis].item() > extent+half+.01)
            _, contacts = c.snapshot()
            contact |= frozenset(('upper_piece1', 'upper')) in contacts
        report['impacts'].append(dict(axis=axis, sign=sign, speed_m_s=1.,
            contacted_tray=contact, nearest_wall_clearance_m=nearest_wall,
            escaped_through_wall=crossed, maximum_overlap=maximum))
    restore()

    def capture(label):
        for _ in range(4):c.sim.render();scene.update(c.dt)
        result={}
        for name in ('head', 'overview', 'left_wrist', 'right_wrist'):
            cam=scene.cameras[name]
            Image.fromarray(cam.data.output['rgb'][0, :, :, :3].cpu().numpy()).save(out/(label+'-'+name+'.png'))
            if name.endswith('_wrist'):
                side=name.split('_')[0];robot=scene.robots[side];bid=c.ids[side][2]
                tip=robot.data.body_pos_w[:,bid]+quat_apply(robot.data.body_quat_w[:,bid],
                    torch.tensor([scene.embodiment.tcp],device=c.device))
                rotation=matrix_from_quat(cam.data.quat_w_ros)[0]
                point=rotation.T @ (tip[0]-cam.data.pos_w[0])
                pixel=cam.data.intrinsic_matrices[0] @ point;pixel=pixel[:2]/pixel[2]
                result[side]=dict(grasp_center_pixel=pixel.cpu().tolist(),depth_m=point[2].item(),
                    centered=bool(point[2]>0 and 64<pixel[0]<576 and 48<pixel[1]<432),
                    tip_world=tip[0].cpu().tolist(),camera_world=cam.data.pos_w[0].cpu().tolist(),
                    camera_quat_ros=cam.data.quat_w_ros[0].cpu().tolist())
                stage=omni.usd.get_context().get_stage()
                matrices={}
                for link in (scene.embodiment.hand,scene.embodiment.camera_link):
                    prim=stage.GetPrimAtPath('/World/'+side+'_robot/'+link)
                    matrices[link]=np.asarray(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())).tolist()
                result[side]['usd_world_matrices']=matrices
        return result
    report['wrist_initial']=capture('initial')
    offset=torch.tensor([scene.embodiment.tcp],device=c.device)
    # Bring both hands above separate tray handles with ordinary bounded motion.
    tray=next(o for o in scene.spec['objects'] if o['id']=='upper')
    from .demonstration import Demonstration
    recorder=Demonstration(c,out,video_prefix='qa-motion')
    try:
        for _ in range(80):
            tokens={};errors={}
            for side,handle in [('left',tray['grasp_sides'][1]),('right',tray['grasp_sides'][0])]:
                robot=scene.robots[side];bid=c.ids[side][2]
                tip_world=(robot.data.body_pos_w[:,bid]+quat_apply(robot.data.body_quat_w[:,bid],offset))[0]
                tip=torch.as_tensor(scene.world_to_task(tip_world.cpu().numpy()),device=c.device,dtype=tip_world.dtype)
                target=torch.tensor([tray['xy'][0],tray['xy'][1]+handle[1],1.10],device=c.device)
                error=target-tip;errors[side]=error
                if error.abs().max().item()>.004:
                    axis=int(error.abs().argmax());tokens[side]=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
            if not tokens:break
            mm=min(20.,max(.5,min(e.abs().max().item()*1000 for s,e in errors.items() if s in tokens)))
            c.action(tokens.get('left','STILL'),tokens.get('right','STILL'),mm)
        report['wrist_approach']=capture('approach')
    finally:
        recorder.close()
    report['approach_error_m']={s:float(e.norm()) for s,e in errors.items()}
    report['passed'] = (report['initial_intersections']['depth_m'] < .002
        and all(x['contacted_tray'] and x['nearest_wall_clearance_m'] < .002 and not x['escaped_through_wall']
                and x['maximum_overlap']['depth_m'] < .002 for x in report['impacts'])
        and max(report['approach_error_m'].values()) < .01
        and all(x['centered'] for group in ('wrist_initial','wrist_approach') for x in report[group].values()))
    (out/'environment_check.private.json').write_text(json.dumps(report,indent=2)+'\n')
    print('VIDEOICL_ENVIRONMENT_CHECK '+json.dumps(report),flush=True)
    if not report['passed']:raise RuntimeError('Environment QA failed; inspect physical and optical evidence')
