"""Independent private E42 author. Defaults and official scoring are untouched.

Native execution requires the dedicated wrapper, real 22-link contact sensors,
a verified source-edge group plan and a caller-assigned worker slot. A contact
entry is not task completion; fresh native feedback drives every short push.
"""
from __future__ import annotations
import json,os
from pathlib import Path
import numpy as np
from .author_e42_edge_policy import reviewed_source,edge_conditions
from .author_mplib_planner import _matrix,_quat,_rotation,edge_preserving_tcp_goal,plan

ROBOT_LINKS=[f'panda_link{i}'for i in range(8)]+['panda_hand','panda_leftfinger','panda_rightfinger']


def rotation_distance_degrees(a,b):
    # PhysX float32 matrices have small nonorthogonality. Polar projection is
    # measurement normalization only; it never changes any native pose.
    u,_,v=np.linalg.svd(a);left=u@v;u,_,v=np.linalg.svd(b);right=u@v;d=left@right.T
    sine=np.linalg.norm([d[2,1]-d[1,2],d[0,2]-d[2,0],d[1,0]-d[0,1]])/2
    return float(np.rad2deg(np.arctan2(sine,np.clip((np.trace(d)-1)/2,-1.,1.))))


def grip_hold_sample(previous,current,joint_velocity,dt):
    speed=float(np.linalg.norm(current[:3,3]-previous[:3,3])/dt)
    angular_speed=rotation_distance_degrees(current[:3,:3],previous[:3,:3])/dt
    joint_speed=float(np.max(np.abs(joint_velocity)))
    return dict(relative_linear_speed_m_s=speed,relative_angular_speed_deg_s=angular_speed,
                actual_arm_joint_speed_max_rad_s=joint_speed,
                stable=speed<=.001 and angular_speed<=1. and joint_speed<=.005)


def grip_hold_window(rows,dt,rotation_envelope_limit_deg=.25):
    """Separate bounded contact jitter from real drift using native samples."""
    if not np.isfinite(rotation_envelope_limit_deg)or not 0<rotation_envelope_limit_deg<=.5:raise ValueError('Private angular hold envelope must be finite and no greater than.5degree')
    count=int(np.ceil(.12/dt-1e-8))+1
    if len(rows)<count:return dict(stable=False,reason='Insufficient actual .12s pose window')
    window=rows[-count:];ticks=np.asarray([r['physics_tick']for r in window]);duration=float((ticks[-1]-ticks[0])*dt)
    if np.any(np.diff(ticks)!=1)or duration<.12-1e-9:return dict(stable=False,reason='Missing actual physics ticks')
    poses=np.asarray([r['actual_tcp_to_tool']for r in window]);p=poses[:,:3,3];rotations=[]
    for pose in poses:
        u,_,v=np.linalg.svd(pose[:3,:3]);rotations.append(u@v)
    rotations=np.asarray(rotations);cosines=np.clip((np.einsum('ikm,jkm->ij',rotations,rotations)-1)/2,-1,1)
    angle_envelope=float(np.rad2deg(np.arccos(cosines.min())))
    position_envelope=float(np.linalg.norm(p[:,None]-p[None,:],axis=-1).max())
    vectors=[]
    for rotation in rotations:
        d=rotation@rotations[0].T;s=np.array([d[2,1]-d[1,2],d[0,2]-d[2,0],d[1,0]-d[0,1]])/2;length=np.linalg.norm(s)
        theta=np.arctan2(length,np.clip((np.trace(d)-1)/2,-1,1));vectors.append(np.rad2deg(s if length<1e-10 else s*theta/length))
    vectors=np.asarray(vectors);times=(ticks-ticks[0])*dt;centered=times-times.mean();denominator=float(centered@centered)
    translation_net=float(np.linalg.norm(p[-1]-p[0])/duration);translation_regression=float(np.linalg.norm(centered@p/denominator))
    angle_net=float(np.linalg.norm(vectors[-1]-vectors[0])/duration);angle_regression=float(np.linalg.norm(centered@vectors/denominator))
    qvel=float(np.max(abs(np.asarray([r['native_arm_qvel']for r in window]))))
    passed=position_envelope<=.00025 and angle_envelope<=rotation_envelope_limit_deg and max(translation_net,translation_regression)<=.001 and max(angle_net,angle_regression)<=1. and qvel<=.005
    return dict(stable=passed,window_seconds=duration,actual_samples=count,
                translation_envelope_m=position_envelope,rotation_envelope_deg=angle_envelope,rotation_envelope_limit_deg=rotation_envelope_limit_deg,
                net_translation_drift_m_s=translation_net,regression_translation_drift_m_s=translation_regression,
                net_rotation_drift_deg_s=angle_net,regression_rotation_drift_deg_s=angle_regression,
                actual_arm_joint_speed_max_rad_s=qvel,criterion='Actual pose envelope and net/regression drift; instantaneous jitter retained')


def trailing_group_entry(positions,radii,target_xy):
    """Put the real edge behind EVERY source ball before lowering it."""
    center=np.mean(list(positions.values()),axis=0);d=np.array([*(np.asarray(target_xy)-center[:2]),0.]);length=np.linalg.norm(d)
    if not np.isfinite(d).all()or length<1e-9:raise ValueError('Measured group needs a nonzero target direction')
    d/=length;name=min(positions,key=lambda n:float(np.asarray(positions[n])@d));point=np.asarray(positions[name],float)
    edge=point-d*(float(radii[name])+.006);edge[2]=max(float(v[2])for v in positions.values())+.002
    return name,d,edge


def slower_contact_profile(profile,caps):
    """Copy planning limits; the native source limits and geometry stay intact."""
    result=dict(profile)
    for key in('joint_velocity_cap','joint_acceleration_cap'):
        value=float(caps[key]);base=float(profile[key])
        if not np.isfinite(value)or not 0<value<=base:raise ValueError('Private contact caps must only slow the original verified trajectory')
        result[key]=value
    return result


def empty_arm_world_profile(profile):
    """No held tool/contact exception exists during the empty-arm parking."""
    result=dict(profile);result.pop('e42_edge_group',None);result['intentional_contacts']={}
    result['allow_measured_grasp_palm_contact']=False
    return result


def measured_group_feedback_goal(edge,positions,direction,horizon):
    """Refresh the real ball-equator height instead of accumulating TCP error."""
    edge=np.asarray(edge,float);d=np.asarray(direction,float);d=d/np.linalg.norm(d)
    if not np.isfinite(d).all()or abs(d[2])>1e-9 or not 0<horizon<=.006:raise ValueError('Bounded horizontal feedback direction/horizon required')
    goal=edge+d*horizon;goal[2]=max(float(v[2])for v in positions.values())+.002
    delta=goal-edge;distance=np.linalg.norm(delta)
    return edge+delta*min(1.,horizon/distance)


def bounded_recontact_target(tool_pose,positions,review,direction,follow_height=False):
    """A measured 2mm approach inside the existing source-edge near band."""
    d=np.asarray(direction,float);d=d/np.linalg.norm(d)
    if not np.isfinite(d).all()or abs(d[2])>1e-9:raise ValueError('Recontact direction must be finite and horizontal')
    eligible=[]
    for name in review['balls']:
        center=np.asarray(positions[name],float);g=edge_conditions(tool_pose,center,review['radius'][name],review)
        if g['eligible']:eligible.append((g['source_edge_distance_m'],name,g))
    if not eligible:return None
    _,name,g=min(eligible);edge=np.asarray(review['edge_segment']).mean(0)
    current=tool_pose[:3,:3]@edge+tool_pose[:3,3]
    outward=tool_pose[:3,:3]@np.asarray(review['outward_local']);horizontal=outward.copy();horizontal[2]=0
    if np.linalg.norm(horizontal)<1e-9 or float(horizontal@d/np.linalg.norm(horizontal))<.99:return None
    goal=measured_group_feedback_goal(current,positions,d,.002)if follow_height else current+d*.002
    return dict(ball=name,edge_goal=goal,source_edge_geometry=g,maximum_commanded_approach_m=.002,
                actual_force_required_for_push_evidence=True)


def check_native_observation(state,forces,robot_ball_forces,review,side,holding_required=True):
    balls=review['balls'];tool=review['tool_actor'];expected={(s,b,n)for s in ('left','right')for b in ROBOT_LINKS for n in balls}
    for name in [tool,*balls]:
        if not np.isfinite(np.asarray(state[name]['pos'])).all()or not np.isfinite(np.asarray(state[name]['mat'])).all():raise RuntimeError('Invalid actual native actor pose: '+name)
    if set(robot_ball_forces)!=expected:raise RuntimeError('Real native 22-link/two-ball force coverage missing')
    values=np.array(list(robot_ball_forces.values()),float)
    if not np.isfinite(values).all()or np.any(values<0):raise RuntimeError('Invalid native robot-ball force samples')
    if values.max(initial=0.)>.001:raise RuntimeError('Actual native robot/hand contact with target ball')
    def force(a,b):
        value=forces.get(frozenset((a,b)))
        if value is None or not np.isfinite(value)or value<0:raise RuntimeError('Actual force matrix sample missing: '+a+'/'+b)
        return float(value)
    held=bool(state[tool]['grasp'][0 if side=='left'else 1])
    bilateral=all(force(tool,f'{side}_finger{i}')>.001 for i in (1,2))
    if holding_required and not(held and bilateral):raise RuntimeError('Actual bilateral tool grasp lost')
    tv=state[tool];pose=np.eye(4);pose[:3,:3]=tv['mat'];pose[:3,3]=tv['pos'];rows={}
    for name in balls:
        value=state[name];center=np.asarray(value['pos'])+np.asarray(value['mat'])@np.asarray(review['local_bounds_center'][name]);radius=review['radius'][name]
        table=force(name,'table');tool_force=force(name,tool)
        if table<=.001 or abs(float(center[2]-radius-.8))>=.012:raise RuntimeError('Target ball lost actual native table support: '+name)
        if any(value['grasp']):raise RuntimeError('Target ball directly grasped')
        geometry=edge_conditions(pose,center,radius,review)
        if tool_force>.001 and(not held or not bilateral or not geometry['eligible']):raise RuntimeError('Tool-ball force outside actual front-edge policy: '+name+' '+json.dumps(geometry))
        rows[name]=dict(position_task=center.tolist(),table_force_n=table,tool_force_n=tool_force,edge_geometry=geometry)
    return dict(tool_held=held,bilateral_native_grasp=bilateral,tool_pose_task=pose.tolist(),
                force_quantity='PhysX ContactSensor normal-force matrix norm; friction forces are not included',
                measured_grasp_force_n=[force(tool,f'{side}_finger{i}')for i in (1,2)],
                robot_ball_force_max_n=float(values.max(initial=0.)),native_robot_ball_pairs_sampled=len(expected),
                native_robot_ball_force_n={'/'.join(key):float(value)for key,value in sorted(robot_ball_forces.items())},balls=rows)


def check_native_robot_tool_contacts(panel,side,held,bilateral,table_force,table_forbidden,allow_held_palm=True):
    expected={(s,b)for s in ('left','right')for b in ROBOT_LINKS}
    if set(panel)!=expected:raise RuntimeError('Actual native 22-link/tool contact coverage missing')
    if not np.isfinite([*panel.values(),table_force]).all()or min([*panel.values(),table_force])<0:raise RuntimeError('Invalid native robot/tool or table force sample')
    allowed={(side,'panda_leftfinger'),(side,'panda_rightfinger')}
    if held and bilateral and allow_held_palm:allowed.add((side,'panda_hand'))
    forbidden=[(s,b,float(v))for(s,b),v in panel.items()if v>.001 and(s,b)not in allowed]
    if forbidden:raise RuntimeError('Actual native non-grasp robot/tool contact: '+json.dumps(forbidden))
    if table_forbidden and table_force>.001:raise RuntimeError('Actual held tool hit the native table after clearance')
    return dict(native_robot_tool_pairs_sampled=22,native_robot_tool_force_n={'/'.join(k):float(v)for k,v in sorted(panel.items())},
                allowed_native_grasp_links=['/'.join(k)for k in sorted(allowed)],tool_table_force_n=float(table_force),tool_table_forbidden=table_forbidden)


class NativeRobotBallSensors:
    """Read actual PhysX contact matrices, without entering the score contact map."""
    def __init__(self,scene):
        from isaaclab.sensors import ContactSensor,ContactSensorCfg
        self.balls=list(scene.spec['semantic']['groups']['balls']);self.tool=scene.spec['semantic']['tools']['main']['actor'];self.filter_actors=[*self.balls,self.tool]
        self.sensors={};self.ready=False;self._tool_panel=None
        for side in ('left','right'):
            for body in ROBOT_LINKS:
                path=f'/World/{side}_robot/{body}'
                self.sensors[(side,body)]=ContactSensor(ContactSensorCfg(prim_path=path,
                    filter_prim_paths_expr=['/World/Props/'+n for n in self.filter_actors],history_length=0,update_period=0.))
    def update(self,dt):
        for sensor in self.sensors.values():sensor.update(dt)
    def panel(self):
        import torch
        arrays=[];keys=[]
        for key,sensor in self.sensors.items():
            matrix=sensor.data.force_matrix_w
            if matrix is None or matrix.shape[-2]!=len(self.filter_actors):raise RuntimeError('Native private robot/ball/tool contact matrix unavailable')
            arrays.append(matrix.norm(dim=-1).amax(dim=1)[0]);keys.append(key)
        values=torch.stack(arrays).cpu().tolist();result={};self._tool_panel={}
        for key,row in zip(keys,values):
            for ball,value in zip(self.balls,row):result[(*key,ball)]=float(value)
            self._tool_panel[key]=float(row[-1])
        return result
    def tool_panel(self):
        if self._tool_panel is None:self.panel()
        return self._tool_panel
    def validate_ready(self):
        for sensor in self.sensors.values():sensor.update(0.,force_recompute=True)
        panel=self.panel()
        if len(panel)!=44 or len(self.tool_panel())!=22:raise RuntimeError('All actual 22-link/two-ball/tool sensor pairs required')
        self.ready=True


class NativeE42Guard:
    covers_e42_native_contacts=False
    def __init__(self,author,review,side,sensors):
        self.author=author;self.controller=author.c;self.review=review;self.side=side;self.sensors=sensors;self.require_holding=False;self.tool_table_forbidden=False;self.allow_held_palm=True;self.last=None;self.last_tick=None
        sensors.validate_ready();self.covers_e42_native_contacts=True
    def __call__(self):
        if self.last_tick==self.controller.physics_ticks and self.last is not None:
            if self.require_holding and not(self.last['tool_held']and self.last['bilateral_native_grasp']):raise RuntimeError('Actual bilateral tool grasp lost')
            if self.tool_table_forbidden and self.last['tool_table_force_n']>.001:raise RuntimeError('Actual held tool hit the native table after clearance')
            return self.last
        state,_=self.controller.snapshot();panel=self.sensors.panel();tool_panel=self.sensors.tool_panel()
        try:
            row=check_native_observation(state,self.controller.contact_forces,panel,self.review,self.side,self.require_holding)
            row.update(check_native_robot_tool_contacts(tool_panel,self.side,row['tool_held'],row['bilateral_native_grasp'],self.controller.contact_forces[frozenset((self.review['tool_actor'],'table'))],self.tool_table_forbidden,self.allow_held_palm))
        except Exception as exc:
            robots=getattr(getattr(self.author,'scene',None),'robots',{})
            failure=dict(error=repr(exc),stage=self.author.stage,physics_tick=self.controller.physics_ticks,actors=state,
                         native_robot_ball_force_n={'/'.join(k):v for k,v in panel.items()},native_robot_tool_force_n={'/'.join(k):v for k,v in tool_panel.items()},
                         native_score_contact_forces_n={'/'.join(sorted(k)):v for k,v in self.controller.contact_forces.items()},
                         robots={side:dict(joint_names=list(robot.joint_names),qpos=robot.data.joint_pos[0].cpu().tolist(),qvel=robot.data.joint_vel[0].cpu().tolist(),
                                           body_names=list(robot.body_names),body_pos_w=robot.data.body_pos_w[0].cpu().tolist(),body_quat_w=robot.data.body_quat_w[0].cpu().tolist())for side,robot in robots.items()})
            with(self.author.out/'E42-native-guard-failures.private.jsonl').open('a')as stream:stream.write(json.dumps(failure,default=lambda value:value.tolist())+'\n')
            raise
        vectors={}
        for actor,(sensor,filters)in getattr(getattr(self.author,'scene',None),'contacts',{}).items():
            if actor not in self.review['balls']:continue
            matrix=sensor.data.force_matrix_w
            vectors[actor]=dict(force_on_sensor_actor_normal_world_n=matrix[0].sum(dim=0).cpu().tolist(),filter_actors=list(filters))
        row.update(physics_tick=self.controller.physics_ticks,stage=self.author.stage,ball_normal_force_vectors=vectors)
        self.last=row
        if self.last_tick!=self.controller.physics_ticks:
            with(self.author.out/'E42-native-guard.private.jsonl').open('a')as stream:stream.write(json.dumps(row)+'\n')
            self.last_tick=self.controller.physics_ticks
        return row
    def tick(self,controller,render):
        self.sensors.update(controller.dt);self()


class SteepE42Author:
    def __init__(self,author):
        from .realworld_tool_expert import ToolAuthor
        self.a=author;self.c=author.c;self.scene=author.scene;self.t=ToolAuthor(author);self.spec=self.scene.spec
        if self.spec['id']!='E42'or not author.smooth:raise ValueError('Dedicated smooth E42 author only')
        self.review=reviewed_source(self.spec['objects'],self.spec['semantic'],self.spec['source_binding_sha256'])
        if len(set(self.review['mapping'].values()))!=1:raise ValueError('E42 same-zone ball group required')
        # ToolAuthor.tool() also acquires. Keep construction motion-free so the
        # real contact guard is registered before the one allowed acquisition.
        self.tool=self.spec['semantic']['tools']['main'];self.actor=self.tool['actor'];self.side=self.tool.get('hand','right')
        self.grip=dict(actor=self.actor,local=self.tool['grasp_local'],jaw_axis_local=self.tool['jaw_axis_local'])
        self.edge=np.asarray(self.review['edge_segment']).mean(0)
        sensors=getattr(self.scene,'_e42_robot_ball_sensors',None)
        if sensors is None:raise RuntimeError('Dedicated native 22-link sensors were not initialized before simulation reset')
        self.guard=NativeE42Guard(author,self.review,self.side,sensors);self.number=0;self.pitch=None;self.last_direction=None
        if self.spec['semantic'].get('near_com_handle_grasp_review'):
            if os.environ.get('VIC_E42_RAW_CONTACTS')!='1'or os.environ.get('VIC_E42_REQUIRE_SOURCE_HANDLE_CONTACTS')!='1'or os.environ.get('VIC_E42_FORBID_PALM_TOOL')!='1':
                raise RuntimeError('Near-COM private grasp requires actual handle-patch and no-palm native guards')
        self.guard.allow_held_palm=os.environ.get('VIC_E42_FORBID_PALM_TOOL')!='1'
        self.raw_probe=None
        self.ball_support_probe=None
        if os.environ.get('VIC_E42_RAW_BALL_SUPPORT')=='1':
            from .author_native_ball_support_probe import NativeBallSupportProbe
            self.ball_support_probe=NativeBallSupportProbe(author,self.review['balls'])
        if os.environ.get('VIC_E42_RAW_CONTACTS')=='1':
            from .author_native_grip_probe import NativeGripPatchProbe
            self.raw_probe=NativeGripPatchProbe(author,sensors,self.side,self.actor,lambda:self.guard.require_holding)
        self.continuous_contact=self.scene.embodiment.config.get('author_recording',{}).get('e42_native_cartesian_contact',False) is True
        self.zone=next(z for z in self.spec['zones']if z['id']==self.review['mapping'][self.review['balls'][0]])
        (author.out/'E42-camera-profile.private.json').write_text(json.dumps(dict(head_view=self.spec.get('head_view'),camera_profile=self.spec.get('camera_profile'),private_override=self.scene.embodiment.config.get('author_recording',{}).get('e42_head_view')),indent=2)+'\n')
    def tool_frame(self):
        state,_=self.c.snapshot();v=state[self.actor];pose=np.eye(4);pose[:3,:3]=v['mat'];pose[:3,3]=v['pos'];return pose,state
    def tcp_frame(self):
        robot=self.scene.robots[self.side];_,q=self.c.pose(self.side);rotation=self.scene.layout.task_rotation.T@_rotation(robot.data.root_quat_w[0].cpu().tolist())@_rotation(q[0].cpu().tolist())
        pose=np.eye(4);pose[:3,:3]=rotation;pose[:3,3]=self.a.tip(self.side);return pose
    def relative_grip(self):
        tool,_=self.tool_frame();return np.linalg.inv(self.tcp_frame())@tool
    def park_inactive_arm(self):
        goal=self.scene.embodiment.config.get('author_recording',{}).get('e42_inactive_arm_park_task')
        if goal is None:return
        from .author_mplib_planner import capture_scene,plan_snapshot
        side='left'if self.side=='right'else'right';self.a.stage='E42-park-empty-'+side
        self.guard();state,_=self.c.snapshot()
        if any(value['grasp'][0 if side=='left'else 1]for value in state.values()):raise RuntimeError('Inactive parking requires an actually empty hand')
        snapshot=capture_scene(self.scene,self.c,side,list(goal));profile=empty_arm_world_profile(json.loads(Path(os.path.expandvars(snapshot['profile'])).read_text()))
        (self.a.out/'E42-empty-arm-park-snapshot.private.json').write_text(json.dumps(snapshot,indent=2)+'\n')
        (self.a.out/'E42-empty-arm-park-profile.private.json').write_text(json.dumps(profile,indent=2)+'\n')
        result=plan_snapshot(snapshot,profile)
        (self.a.out/'E42-empty-arm-park-plan.private.json').write_text(json.dumps(result,indent=2)+'\n')
        if result.get('verified')is not True:raise RuntimeError('Inactive empty-arm fullworld park refused: '+str(result['diagnostics'].get('error',result['status'])))
        receipt=self.a.execute_joint_path(side,result,guard=self.guard)
        actual=self.a.tip(side);error=float(np.linalg.norm(np.asarray(actual)-goal))
        (self.a.out/'E42-empty-arm-park-receipt.private.json').write_text(json.dumps(dict(receipt=receipt,actual_tcp_task=np.asarray(actual).tolist(),goal_task=goal,actual_tcp_error_m=error,robot_state_written=False,props_changed=False),indent=2)+'\n')
        if error>.001:raise RuntimeError('Actual inactive empty arm did not reach verified park within1mm')
    def orient_empty_active_grasp(self):
        yaw=self.scene.embodiment.config.get('author_recording',{}).get('e42_empty_grasp_yaw_rad')
        if yaw is None:return
        yaw=float(yaw)
        if not np.isfinite(yaw)or abs(yaw)>np.pi+1e-12:raise ValueError('Bounded explicit empty grasp yaw required')
        from .author_mplib_planner import capture_scene,plan_snapshot
        from .realworld_tool_expert import _axis_rotation
        self.a.stage='E42-empty-forward-grasp-orientation';self.guard();state,_=self.c.snapshot();index=0 if self.side=='left'else 1
        if any(value['grasp'][index]for value in state.values())or any(self.c.contact_forces.get(frozenset((name,f'{self.side}_finger{i}')),0.)>.001 for name in state for i in(1,2)):
            raise RuntimeError('Equivalent handle approach orientation requires a genuinely empty hand')
        current=self.tcp_frame();rotation=_axis_rotation([0,0,1],yaw)@current[:3,:3]
        point=current[:3,3].copy();point[2]=max(point[2],self.t.clearance)
        request=dict(position=point.tolist(),quaternion=_quat(rotation).tolist())
        snapshot=capture_scene(self.scene,self.c,self.side,request);profile=empty_arm_world_profile(json.loads(Path(os.path.expandvars(snapshot['profile'])).read_text()))
        (self.a.out/'E42-empty-grasp-orientation-snapshot.private.json').write_text(json.dumps(snapshot,indent=2)+'\n')
        result=plan_snapshot(snapshot,profile)
        (self.a.out/'E42-empty-grasp-orientation-plan.private.json').write_text(json.dumps(result,indent=2)+'\n')
        if result.get('verified')is not True:raise RuntimeError('Empty equivalent-grasp fullworld orientation refused: '+str(result['diagnostics'].get('error',result['status'])))
        def empty_guard():
            row=self.guard();values,_=self.c.snapshot()
            if any(value['grasp'][index]for value in values.values())or any(self.c.contact_forces.get(frozenset((name,f'{self.side}_finger{i}')),0.)>.001 for name in values for i in(1,2)):
                raise RuntimeError('Empty orientation acquired unexpected native finger/prop contact')
            return row
        receipt=self.a.execute_joint_path(self.side,result,guard=empty_guard);actual=self.tcp_frame()
        error=float(np.linalg.norm(actual[:3,3]-point));angle=rotation_distance_degrees(actual[:3,:3],rotation)
        (self.a.out/'E42-empty-grasp-orientation-receipt.private.json').write_text(json.dumps(dict(receipt=receipt,request_task=request,actual_tcp_task=actual.tolist(),position_error_m=error,orientation_error_deg=angle,object_state_written=False,robot_state_written=False),indent=2)+'\n')
        if error>.001 or angle>1.:raise RuntimeError('Actual empty equivalent-grasp orientation missed1mm/1degree target')
    def settle_grip(self):
        """Real servo hold, never a sleep or a source-object state write."""
        previous=self.relative_grip();window=dict(stable=False);rows=[]
        angle_limit=float(self.scene.embodiment.config.get('author_recording',{}).get('e42_hold_rotation_envelope_deg',.25))
        def observe(controller,render):
            nonlocal previous,window
            current=self.relative_grip();robot=self.scene.robots[self.side];arm=self.c.ids[self.side][0]
            qvel=np.asarray(robot.data.joint_vel[0,arm].cpu().tolist());row=grip_hold_sample(previous,current,qvel,controller.dt)
            previous=current
            row.update(physics_tick=controller.physics_ticks,
                       actual_tcp_to_tool=current.tolist(),native_arm_qvel=qvel.tolist(),
                       native_tool_velocity_world=self.scene.objects[self.actor].data.root_vel_w[0].cpu().tolist())
            rows.append(row);window=grip_hold_window(rows,controller.dt,rotation_envelope_limit_deg=angle_limit);row['pose_window']=window
        self.c.tick_hooks.append(observe)
        try:
            for _ in range(4):
                self.guard();self.t.wait(1)
                if window['stable']:return
            raise RuntimeError('Actual held tool/arm velocities did not settle within bounded .8s hold')
        finally:
            self.c.tick_hooks.remove(observe)
            with(self.a.out/'E42-real-grip-settle.private.jsonl').open('a')as stream:
                stream.write(json.dumps(dict(stage=self.a.stage,stable_seconds=window.get('window_seconds',0.)if window['stable']else 0.,minimum_stable_seconds=.12,maximum_hold_seconds=.8,
                                             accepted_window=window,physics_ticks=len(rows),samples=rows))+'\n')
    def inside(self,state):
        margin=float(self.scene.embodiment.config.get('author_recording',{}).get('e42_finish_inset_m',0.))
        return all(np.all(np.abs(np.asarray(state[n]['pos'])[:2]-self.zone['xy'])+self.review['radius'][n]<=np.asarray(self.zone['half_size'])+.005-margin)for n in self.review['balls'])
    def direction(self,state):
        center=np.mean([state[n]['pos']for n in self.review['balls']],axis=0);delta=np.array([*(np.asarray(self.zone['xy'])-center[:2]),0.]);length=np.linalg.norm(delta)
        if length>1e-9:return delta/length
        furthest=max(self.review['balls'],key=lambda n:np.linalg.norm(np.asarray(state[n]['pos'])[:2]-self.zone['xy']));delta=np.array([*(np.asarray(self.zone['xy'])-np.asarray(state[furthest]['pos'])[:2]),0.]);return delta/np.linalg.norm(delta)
    def any_contact(self):
        row=self.guard();return any(v['tool_force_n']>.001 for v in row['balls'].values())
    def proposed(self,edge_goal,direction,pitch):
        tool,_=self.tool_frame();tcp=self.tcp_frame();goal,geometry=edge_preserving_tcp_goal(tool,tcp,self.edge,self.spec['semantic']['blade_support_normal_local'],self.spec['semantic']['edge_outward_normal_local'],direction,edge_goal,pitch)
        recording=self.scene.embodiment.config.get('author_recording',{});caps=recording.get('e42_contact_planner_caps')
        contact_stage=any(token in self.a.stage for token in('contact-entry','seek-real-edge-contact','feedback-push','disengage','bounded-recontact'))
        if caps and contact_stage:
            from .author_mplib_planner import capture_scene,plan_snapshot
            if getattr(self.c,'_e42_native_contact_guard',None)is not self.guard or not self.guard.covers_e42_native_contacts:raise RuntimeError('Actual registered full native guard required')
            self.guard();snapshot=capture_scene(self.scene,self.c,self.side,dict(position=goal[:3,3].tolist(),quaternion=_quat(goal[:3,:3]).tolist()))
            profile=json.loads(Path(os.path.expandvars(snapshot['profile'])).read_text());base_v=profile['joint_velocity_cap'];base_a=profile['joint_acceleration_cap']
            v=float(caps['joint_velocity_cap']);acc=float(caps['joint_acceleration_cap'])
            profile=slower_contact_profile(profile,caps)
            proposal=getattr(self,'contact_proposal',0)+1;self.contact_proposal=proposal
            (self.a.out/f'E42-contact-snapshot-{proposal:05d}.private.json').write_text(json.dumps(snapshot,indent=2)+'\n')
            (self.a.out/f'E42-contact-profile-{proposal:05d}.private.json').write_text(json.dumps(profile,indent=2)+'\n')
            result=plan_snapshot(snapshot,profile);result['diagnostics']['explicit_contact_caps']=dict(stage=self.a.stage,base_velocity_cap=base_v,base_acceleration_cap=base_a,effective_velocity_cap=v,effective_acceleration_cap=acc)
        else:result=plan(self.scene,self.c,self.side,goal[:3,3].tolist(),task_tcp_quaternion=_quat(goal[:3,:3]).tolist())
        result['diagnostics']['E42_source_edge_goal']=geometry
        if result.get('verified')is True:
            end=np.asarray(result['position'][-1]);previous=getattr(self,'previous_goal_q',None)
            hand=np.asarray(result['target_world']['hand'])[:3,:3]
            result['diagnostics']['E42_goal_branch']=dict(end_q=end.tolist(),
                distance_from_previous_verified_goal_q_rad=None if previous is None else float(np.linalg.norm(end-previous)),
                max_joint_distance_from_previous_verified_goal_rad=None if previous is None else float(np.max(abs(end-previous))),
                target_hand_quaternion_world=_quat(hand).tolist())
        return result
    def execute(self,result,stage,done=None):
        self.a.stage=stage;self.number+=1
        (self.a.out/f'E42-plan-{self.number:05d}.private.json').write_text(json.dumps(result,indent=2)+'\n')
        if result.get('verified')is not True:raise RuntimeError('E42 private plan refused: '+str(result['diagnostics'].get('error',result['status'])))
        self.previous_goal_q=np.asarray(result['position'][-1]).copy()
        start_tool,_=self.tool_frame();start_relative=np.linalg.inv(self.tcp_frame())@start_tool;slip={}
        def native_stop():
            current_tool,_=self.tool_frame();relative=np.linalg.inv(self.tcp_frame())@current_tool
            position=float(np.linalg.norm(relative[:3,3]-start_relative[:3,3]));rotation=relative[:3,:3]@start_relative[:3,:3].T
            angle=float(np.arccos(np.clip((np.trace(rotation)-1)/2,-1.,1.)))
            if position>.001 or angle>np.deg2rad(1.):
                slip.update(reason='Measured in-grip transform changed; fresh capture required',position_m=position,angle_rad=angle);return True
            return bool(done is not None and done())
        receipt=self.a.execute_joint_path(self.side,result,guard=self.guard,done=native_stop)
        tool,state=self.tool_frame();actual=tool[:3,:3]@self.edge+tool[:3,3]
        target=result['diagnostics']['E42_source_edge_goal'];error=float(np.linalg.norm(actual-np.asarray(target['edge_goal_world'])))
        delta=tool[:3,:3]@np.asarray(target['tool_goal_world'])[:3,:3].T;orientation=float(np.rad2deg(np.arccos(np.clip((np.trace(delta)-1)/2,-1.,1.))))
        initial_error=float(np.linalg.norm(start_tool[:3,:3]@self.edge+start_tool[:3,3]-np.asarray(target['edge_goal_world'])))
        initial_orientation=rotation_distance_degrees(start_tool[:3,:3],np.asarray(target['tool_goal_world'])[:3,:3])
        measured=dict(edge_position_error_m=error,tool_orientation_error_deg=orientation,
                      initial_edge_position_error_m=initial_error,net_edge_goal_progress_m=initial_error-error,
                      initial_tool_orientation_error_deg=initial_orientation,net_orientation_progress_deg=initial_orientation-orientation,
                      actual_source_goal_reached=error<=.001 and orientation<=1.)
        with(self.a.out/'E42-steep-actions.private.jsonl').open('a')as stream:stream.write(json.dumps(dict(stage=stage,receipt=receipt,in_grip_stop=slip,measured_source_goal=measured,actual_edge_task=actual.tolist(),actual_ball_positions={n:np.asarray(state[n]['pos']).tolist()for n in self.review['balls']},physics_task_completed=False))+'\n')
        return dict(receipt,e42_measured_source_goal=measured,e42_in_grip_stop=slip)
    def contact_translate(self,edge_goal,stage,done=None):
        from .author_e42_cartesian_contact import contact_tcp_goal,relative_grip_stop
        if not self.guard.covers_e42_native_contacts or getattr(self.c,'_e42_native_contact_guard',None)is not self.guard:
            raise RuntimeError('Registered actual native contact guard required for private contact translation')
        self.a.stage=stage;self.guard()
        tool,start_state=self.tool_frame();tcp=self.tcp_frame();goal,geometry=contact_tcp_goal(tcp,tool,self.edge,edge_goal)
        initial=np.linalg.inv(tcp)@tool;slip={};first_tick=self.c.physics_ticks
        # Actuator command only: hold the measured quaternion rather than an
        # unreachable nominal wrist orientation. Native robot/object states are
        # never assigned, and all source joint limits remain in Controller.
        p,q=self.c.pose(self.side);self.c.targets[self.side]=(p.clone(),q.clone())
        other='left'if self.side=='right'else'right';robot=self.scene.robots[other]
        frozen=robot.data.joint_pos[0].cpu().numpy().copy();names=list(robot.joint_names)
        def guarded():
            row=self.guard();actual=robot.data.joint_pos[0].cpu().numpy()
            limits=np.array([.0001 if 'finger'in n else .001 for n in names])
            if np.any(abs(actual-frozen)>limits):raise RuntimeError('Frozen other-arm native joint drift during E42 Cartesian contact')
            return row
        def stopped():
            current,_=self.tool_frame();measurement=relative_grip_stop(initial,np.linalg.inv(self.tcp_frame())@current)
            if measurement['stop']:slip.update(measurement);return True
            return bool(done is not None and done())
        # Keep the parked arm at its measured native joint target; this is a
        # servo command, never a reset/state assignment. The9q guard stays on.
        overrides=self.c._author_joint_override;previous_override=overrides.get(other)
        arm=self.c.ids[other][0];held_q=robot.data.joint_pos[:,arm].clone()
        overrides[other]=(held_q,held_q*0.);partial_error=None
        try:
            self.a.move_smooth({self.side:goal[:3,3]},tolerance=.0005 if np.linalg.norm(np.asarray(geometry['translation_task']))<.002 else .001,guard=guarded,done=stopped,max_speed=.025,max_acceleration=.15)
        except RuntimeError as exc:
            enabled=self.scene.embodiment.config.get('author_recording',{}).get('e42_partial_contact_feedback')is True
            dynamic=stage in('E42-feedback-push-group','E42-bounded-recontact','E42-seek-real-edge-contact')
            if not enabled or not dynamic or not str(exc).startswith('Continuous author waypoint unreachable at '+stage+';'):raise
            # This is an intermediate actuator error, never source task success.
            # All real guards must still hold before the outer loop remeasures
            # both balls and the edge. Other native failures always propagate.
            guarded();partial_error=str(exc)
        finally:
            if previous_override is None:overrides.pop(other,None)
            else:overrides[other]=previous_override
        tool,state=self.tool_frame();edge=tool[:3,:3]@self.edge+tool[:3,3];error=float(np.linalg.norm(edge-np.asarray(edge_goal)))
        measured=dict(edge_position_error_m=error,actual_source_goal_reached=error<=.001,net_edge_goal_progress_m=float(np.linalg.norm(np.asarray(geometry['actual_edge_task'])-edge_goal))-error)
        delta=np.asarray(geometry['translation_task']);length=float(np.linalg.norm(delta));direction=delta/max(length,1e-12)
        measured['actual_forward_edge_motion_m']=float((edge-np.asarray(geometry['actual_edge_task']))@direction)
        measured['actual_forward_ball_motion_m']={n:float((np.asarray(state[n]['pos'])-np.asarray(start_state[n]['pos']))@direction)for n in self.review['balls']}
        receipt=dict(control='private_native_cartesian_contact',whole_path_FCL_certified=False,physics_ticks=self.c.physics_ticks-first_tick,e42_measured_source_goal=measured,e42_in_grip_stop=slip,e42_intermediate_waypoint_partial=partial_error is not None,intermediate_actuator_error=partial_error)
        with(self.a.out/'E42-cartesian-contact.private.jsonl').open('a')as stream:
            stream.write(json.dumps(dict(stage=stage,receipt=receipt,geometry=geometry,actual_edge_task=edge.tolist(),actual_ball_positions={n:np.asarray(state[n]['pos']).tolist()for n in self.review['balls']},frozen_other_arm_joint_names=names,frozen_other_arm_qpos=frozen.tolist(),physics_task_completed=False))+'\n')
        return receipt
    def choose(self,edge_goal,direction,stage,done=None,fallback_edge_goals=None):
        self.a.stage=stage
        from .author_e42_cartesian_contact import CONTACT_STAGES
        if getattr(self,'continuous_contact',False) and stage in CONTACT_STAGES:
            from .author_e42_cartesian_contact import bounded_edge_target
            for _ in range(40):
                if done is not None and done():return dict(done_reached=True,e42_stage_not_claimed_complete=True)
                tool,_=self.tool_frame();edge=tool[:3,:3]@self.edge+tool[:3,3]
                if np.linalg.norm(np.asarray(edge_goal)-edge)<=.001:return dict(e42_measured_source_goal=dict(actual_source_goal_reached=True))
                point=bounded_edge_target(edge,edge_goal)
                receipt=self.contact_translate(point,stage,done)
                if receipt.get('e42_intermediate_waypoint_partial'):return receipt
                if done is not None and done():return receipt
                tool,_=self.tool_frame();edge=tool[:3,:3]@self.edge+tool[:3,3]
                if np.linalg.norm(np.asarray(edge_goal)-edge)<=.001:return receipt
                if receipt['e42_in_grip_stop']:self.settle_grip()
            raise RuntimeError('Bounded native Cartesian contact failed measured1mm edge goal')
        for retry in range(20):
            if done is not None and done():return dict(done_reached=True,e42_stage_not_claimed_complete=True)
            selected=None
            for pitch in dict.fromkeys(([self.pitch]if self.pitch is not None else [])+[75.,90.]):
                if pitch is None:continue
                for candidate_index,point in enumerate([edge_goal,*(fallback_edge_goals or [])]):
                    result=self.proposed(point,direction,pitch)
                    with(self.a.out/'E42-plan-attempts.private.jsonl').open('a')as stream:
                        stream.write(json.dumps(dict(stage=stage,replan=retry,pitch_degrees=pitch,feedback_candidate_index=candidate_index,edge_goal_task=np.asarray(point).tolist(),direction_task=np.asarray(direction).tolist(),status=result.get('status'),verified=result.get('verified'),diagnostics=result.get('diagnostics')))+'\n')
                    if result.get('verified')is True:selected=result;self.pitch=pitch;break
                if selected is not None:break
            if selected is None:raise RuntimeError('No verified E42 source-edge pose/path at reviewed steep angles')
            receipt=self.execute(selected,stage,done=done)
            if self.raw_probe is not None and os.environ.get('VIC_E42_PATCH_DIAGNOSTIC_ONLY')=='1':
                self.settle_grip()
                raise RuntimeError('Read-only E42 patch diagnostic prefix complete; no task completion claimed')
            if done is not None and done():return receipt
            if receipt['e42_measured_source_goal']['actual_source_goal_reached']:return receipt
            # A native done on relative grip motion is only a replan request.
            # Keep the original logical source-edge goal and stage until its
            # measured position/orientation actually converge. Never descend
            # or seek a ball from an unfinished high preapproach.
            self.settle_grip()
        raise RuntimeError('Actual E42 source-edge stage did not converge after bounded fresh replanning')
    def run(self):
        self.c._e42_native_contact_guard=self.guard
        if self.raw_probe is not None:self.c.tick_hooks.append(self.raw_probe.tick)
        if self.ball_support_probe is not None:self.c.tick_hooks.append(self.ball_support_probe.tick)
        self.c.tick_hooks.append(self.guard.tick)
        try:
            self.park_inactive_arm()
            self.orient_empty_active_grasp()
            self.guard();self.t.acquire(self.grip,self.side);self.guard.require_holding=True;self.guard()
            self.a.stage='E42-held-clearance';self.t.move(self.side,[*self.a.tip(self.side)[:2],max(self.t.clearance,self.a.tip(self.side)[2])],guard=self.guard)
            self.guard.tool_table_forbidden=True
            self.settle_grip()
            progress_history=[]
            for iteration in range(140):
                self.guard();tool,state=self.tool_frame()
                if self.scene.embodiment.config.get('author_recording',{}).get('e42_bounded_recontact'):
                    progress_history.append(np.array([state[n]['pos']for n in self.review['balls']]))
                    if len(progress_history)>=12 and np.max(np.linalg.norm(progress_history[-1]-progress_history[-12],axis=-1))<.00025:
                        enabled=self.scene.embodiment.config.get('author_recording',{}).get('e42_global_escape_after_real_stall')is True
                        attempts=getattr(self,'real_stall_escapes',0)
                        if not enabled or attempts>=2:raise RuntimeError('E42 real ball displacement below .25mm across12 fresh control iterations; no task progress')
                        self.real_stall_escapes=attempts+1;d=self.last_direction if self.last_direction is not None else self.direction(state)
                        edge=tool[:3,:3]@self.edge+tool[:3,3]
                        point=measured_group_feedback_goal(edge,{n:np.asarray(state[n]['pos'])for n in self.review['balls']},d,.006)
                        self.a.stage='E42-stall-global-escape'
                        result=self.proposed(point,d,self.pitch if self.pitch is not None else 75.)
                        with(self.a.out/'E42-stall-escape.private.jsonl').open('a')as stream:
                            stream.write(json.dumps(dict(attempt=self.real_stall_escapes,actual_window_ball_motion_m=np.linalg.norm(progress_history[-1]-progress_history[-12],axis=-1).tolist(),source_edge_goal_task=point.tolist(),status=result.get('status'),verified=result.get('verified'),error=result.get('diagnostics',{}).get('error')))+'\n')
                        self.execute(result,self.a.stage);progress_history=[]
                        continue
                if self.inside(state):
                    direction=self.last_direction if self.last_direction is not None else np.array([1.,0.,0.])
                    edge=tool[:3,:3]@self.edge+tool[:3,3]
                    self.choose(edge-direction*.025,direction,'E42-disengage-completed-group')
                    if self.scene.embodiment.config.get('author_recording',{}).get('e42_end_after_verified_source_score')is True:
                        self.a.stage='E42-verify-original-source-after-disengage';self.t.wait(5);self.guard()
                        result=self.c.evaluator.result()
                        (self.a.out/'E42-original-source-score-checkpoint.private.json').write_text(json.dumps(result,indent=2)+'\n')
                        if result.get('success')is True:return
                    tool,_=self.tool_frame();edge=tool[:3,:3]@self.edge+tool[:3,3];self.choose(edge+[0,0,.055],direction,'E42-lift-after-push');self.t.wait(5);return
                contact=self.any_contact();group_entry=bool(self.scene.embodiment.config.get('author_recording',{}).get('e42_trailing_group_entry'))
                direction=self.last_direction if group_entry and contact and self.last_direction is not None else self.direction(state)
                if not contact:
                    if iteration>0 and self.last_direction is not None and self.scene.embodiment.config.get('author_recording',{}).get('e42_bounded_recontact'):
                        proposal=bounded_recontact_target(tool,{n:np.asarray(state[n]['pos'])for n in self.review['balls']},self.review,self.last_direction,follow_height=bool(self.scene.embodiment.config.get('author_recording',{}).get('e42_feedback_height_from_balls')))
                        if proposal is not None:
                            anchor={n:np.asarray(state[n]['pos']).copy()for n in self.review['balls']}
                            def disturbed_recontact():
                                current,_=self.c.snapshot()
                                return any(np.linalg.norm(np.asarray(current[n]['pos'])-anchor[n])>.002 for n in self.review['balls'])
                            with(self.a.out/'E42-bounded-recontact.private.jsonl').open('a')as stream:
                                stream.write(json.dumps(dict(physics_tick=self.c.physics_ticks,source_edge_geometry=proposal['source_edge_geometry'],ball=proposal['ball'],maximum_commanded_approach_m=.002,force_at_start=False,physics_task_completed=False))+'\n')
                            self.choose(proposal['edge_goal'],self.last_direction,'E42-bounded-recontact',done=disturbed_recontact)
                            continue
                    if iteration>0:
                        edge=tool[:3,:3]@self.edge+tool[:3,3];self.choose(edge-direction*.02,direction,'E42-disengage-before-recovery')
                        tool,state=self.tool_frame()
                    # All planning uses fresh measured ball and in-grip poses.
                    # During transit, any unexpected >2mm target disturbance
                    # stops the actual path and causes a new scene capture.
                    anchor={n:np.asarray(state[n]['pos']).copy()for n in self.review['balls']}
                    def disturbed():
                        current,_=self.c.snapshot();return any(np.linalg.norm(np.asarray(current[n]['pos'])-anchor[n])>.002 for n in self.review['balls'])
                    if group_entry:
                        lead,d,entry=trailing_group_entry({n:np.asarray(state[n]['pos'])for n in self.review['balls']},self.review['radius'],self.zone['xy'])
                    else:
                        lead=self.review['balls'][0];p=np.asarray(state[lead]['pos']);d=np.array([*(np.asarray(self.zone['xy'])-p[:2]),0.]);d/=np.linalg.norm(d);entry=p-d*(self.review['radius'][lead]+.006)
                    self.last_direction=d
                    self.choose(entry+[0,0,.055],d,'E42-steep-preapproach',done=disturbed)
                    if disturbed():continue
                    if group_entry:
                        self.choose(entry+[0,0,.025],d,'E42-free-precontact',done=disturbed)
                        if disturbed():continue
                    # Contact-entry must stop at first real group/tool force.
                    # It is never reported as the original TCP goal reached.
                    self.choose(entry,d,'E42-steep-contact-entry',done=lambda:self.any_contact()or disturbed())
                    if self.any_contact():continue
                    for _ in range(6):
                        tool,_=self.tool_frame();edge=tool[:3,:3]@self.edge+tool[:3,3]
                        self.choose(edge+d*.002,d,'E42-seek-real-edge-contact',done=self.any_contact)
                        if self.any_contact():break
                    if not self.any_contact():raise RuntimeError('No real front-edge contact after bounded source-gap closure')
                else:
                    # A short horizon is shorter than half a source radius;
                    # native ball motion invalidates no long stale world plan.
                    edge=tool[:3,:3]@self.edge+tool[:3,3];anchor={n:np.asarray(state[n]['pos']).copy()for n in self.review['balls']}
                    def lost_or_disturbed():
                        row=self.guard();active=[v for v in row['balls'].values()if v['tool_force_n']>.001]
                        if not active:return True
                        for n,value in row['balls'].items():
                            delta=np.asarray(value['position_task'])-anchor[n];lateral=delta-direction*float(delta@direction)
                            if np.linalg.norm(lateral)>.003:return True
                        return False
                    goal=measured_group_feedback_goal(edge,anchor,direction,.006)if self.scene.embodiment.config.get('author_recording',{}).get('e42_feedback_height_from_balls')else edge+direction*.006
                    horizons=self.scene.embodiment.config.get('author_recording',{}).get('e42_feedback_fallback_horizons_m',[])
                    alternatives=[measured_group_feedback_goal(edge,anchor,direction,float(h))for h in horizons]
                    self.choose(goal,direction,'E42-feedback-push-group',done=lost_or_disturbed,fallback_edge_goals=alternatives)
            raise RuntimeError('E42 bounded private feedback/replanning budget exhausted')
        except Exception as exc:
            from .author_mplib_planner import capture_scene
            try:
                snapshot=capture_scene(self.scene,self.c,self.side,self.a.tip(self.side).tolist())
                (self.a.out/'E42-native-failure-world.private.json').write_text(json.dumps(snapshot,indent=2)+'\n')
            except Exception as capture_error:
                (self.a.out/'E42-native-failure-capture-error.private.json').write_text(json.dumps(dict(policy_error=repr(exc),capture_error=repr(capture_error)))+'\n')
            raise
        finally:
            self.c.tick_hooks.remove(self.guard.tick)
            if self.ball_support_probe is not None:self.c.tick_hooks.remove(self.ball_support_probe.tick)
            if self.raw_probe is not None:self.c.tick_hooks.remove(self.raw_probe.tick);self.raw_probe.close()
            if getattr(self.c,'_e42_native_contact_guard',None)is self.guard:delattr(self.c,'_e42_native_contact_guard')


def solve_E42_steep(author):
    SteepE42Author(author).run()
