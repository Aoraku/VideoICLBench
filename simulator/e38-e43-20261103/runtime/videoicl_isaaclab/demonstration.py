"""Private expert demonstrations through the same bounded controls and contact physics."""
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
import numpy as np
import torch
from PIL import Image
from isaaclab.utils.math import quat_apply, subtract_frame_transforms, matrix_from_quat
from .profiles import PROTOCOL


class Demonstration:
    def __init__(self,controller,out,video_prefix='video'):
        self.c=controller;self.scene=controller.scene;self.out=Path(out);self.stage='initial';self.last_checkpoint=0
        head=self.scene.embodiment.config['cameras']['head']
        self.fps=self.scene.embodiment.config['physics']['render_hz']
        self.smooth=bool(self.scene.spec.get('author_smooth_recording',False))
        self.neutral_tcp_quaternions={side:controller.pose(side)[1].clone() for side in self.scene.robots}
        self.joint_velocity_feedforward=bool(getattr(controller,'author_joint_velocity_feedforward',False))
        self.carried_payload=None
        self.physics_ticks_recorded=0
        self.wall_started=time.perf_counter()
        self.offset=torch.tensor([self.scene.embodiment.tcp],device=controller.device)
        ffmpeg=os.environ.get('VIC_FFMPEG_BINARY') or shutil.which('ffmpeg')
        if not ffmpeg:
            import imageio_ffmpeg
            ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
        threads=int(self.scene.embodiment.config.get('author_recording',{}).get('video_encoder_threads',1))
        if not 1<=threads<=4:raise ValueError('Video encoder threads must be within 1..4')
        def encoder(width,height,filename):
            return subprocess.Popen([ffmpeg,'-v','error','-y','-f','rawvideo','-pix_fmt','rgb24',
                '-s',f'{width}x{height}','-r',str(self.fps),'-i','-','-an','-c:v','libx264','-preset','veryfast','-crf','21',
                '-threads',str(threads),'-pix_fmt','yuv420p','-movflags','+faststart',str(self.out/filename)],stdin=subprocess.PIPE)
        wrist=self.scene.embodiment.config['cameras']['wrist']
        self.camera_streams={name:dict(file=video_prefix+suffix+'.mp4',width=cfg['width'],height=cfg['height'])
            for name,suffix,cfg in [('head','',head),('left_wrist','-left_wrist',wrist),('right_wrist','-right_wrist',wrist)]}
        self.encoder=encoder(head['width'],head['height'],self.camera_streams['head']['file'])
        self.wrist_encoders={side:encoder(wrist['width'],wrist['height'],self.camera_streams[side+'_wrist']['file'])
                             for side in ('left','right')}
        self.review_encoder=encoder(1440,720,video_prefix+'-multiview.mp4')
        self.camera_frame_counts={name:0 for name in self.camera_streams}
        self.frame_physics_ticks=[]
        self.frames=0;controller.tick_hooks.append(self.record)
        self.control_report=dict(private_author_recording=True,smooth=self.smooth,
            joint_velocity_feedforward=self.joint_velocity_feedforward,
            profile_joint_velocity_feedforward_requested=self.scene.embodiment.config.get('author_recording',{}).get('joint_velocity_feedforward',False),
            physics_dt=controller.dt,video_fps=self.fps,
            velocity_target_mode='native_joint_velocity_targets' if self.joint_velocity_feedforward else 'unchanged_position_targets',
            velocity_hold_policy='zero_on_hold_done_guard_exception_and_finally',
            joint_state_written_by_recording=False,joint_path_attempts=0,joint_path_completed_calls=0,
            global_joint_planner_enabled_by_default=False,camera_streams=self.camera_streams,
            video_encoder_threads=threads,all_camera_streams_sampled_at_same_physics_tick=True)
        (self.out/'recording-control.private.json').write_text(json.dumps(self.control_report,indent=2)+'\n')

    def record(self,c,render):
        self.physics_ticks_recorded+=1
        if render:
            head=self.scene.cameras['head'].data.output['rgb'][0,:,:,:3].cpu().numpy()
            self.encoder.stdin.write(head.tobytes());self.frames+=1
            self.camera_frame_counts['head']+=1
            self.frame_physics_ticks.append(self.physics_ticks_recorded)
            panel=Image.new('RGB',(1440,720));panel.paste(Image.fromarray(head).resize((960,720)),(0,0))
            for i,side in enumerate(('left','right')):
                rgb=self.scene.cameras[side+'_wrist'].data.output['rgb'][0,:,:,:3].cpu().numpy()
                expected=self.camera_streams[side+'_wrist']
                if rgb.shape!=(expected['height'],expected['width'],3):
                    raise RuntimeError('Native wrist image dimensions changed: '+side)
                self.wrist_encoders[side].stdin.write(rgb.tobytes())
                self.camera_frame_counts[side+'_wrist']+=1
                panel.paste(Image.fromarray(rgb).resize((480,360)),(960,i*360))
            self.review_encoder.stdin.write(panel.tobytes())

    def tip(self,side):
        robot=self.scene.robots[side];bid=self.c.ids[side][2]
        return self.scene.world_to_task((robot.data.body_pos_w[:,bid]+quat_apply(robot.data.body_quat_w[:,bid],self.offset))[0].cpu().numpy()).copy()

    def pos(self,name):return self.scene.world_to_task(self.scene.objects[name].data.root_pos_w[0].cpu().numpy()).copy()

    def note(self,stage):
        self.stage=stage;state,contacts=self.c.snapshot()
        value=dict(stage=stage,steps=self.c.steps,objects={n:dict(pos=x['pos'].tolist(),mat=x['mat'].tolist(),grasp=x['grasp']) for n,x in state.items()},
            tips={s:self.tip(s).tolist() for s in ('left','right')},score=self.c.evaluator.result(),
            joint_velocity_feedforward=self.joint_velocity_feedforward)
        # Private diagnostics sample the same native instant as snapshot above.
        # Keep achieved finger positions separate from commanded grip targets;
        # two contact magnitudes alone cannot distinguish side pinching from
        # fingers pressing the top of a thin source object.
        def native_values(tensor):
            return None if tensor is None else tensor.detach().cpu().tolist()
        value['robot_joints']={}
        for side,robot in self.scene.robots.items():
            q=native_values(robot.data.joint_pos[0])
            indices=[int(i) for i in self.c.ids[side][1]]
            value['robot_joints'][side]=dict(names=list(robot.joint_names),q=q,
                limits=native_values(robot.data.joint_pos_limits[0]),
                finger_indices=indices,finger_q=[q[i] for i in indices],
                gripper_protocol_command_m=float(self.c.grips[side]))
        value['contact_force_vectors']={}
        for name,(sensor,labels) in self.scene.contacts.items():
            data=sensor.data
            # Preserve all native [environment,body,filter,world-axis] entries,
            # including signs and zeros. Do not infer a contact direction from
            # geometry or relabel possibly unmatched filter slots.
            value['contact_force_vectors'][name]=dict(filter_labels=list(labels),
                force_matrix_w_n=native_values(data.force_matrix_w),
                net_forces_w_n=native_values(data.net_forces_w))
        with (self.out/'expert.private.jsonl').open('a') as f:f.write(json.dumps(value)+'\n')
        for _ in range(2):self.c.sim.render();self.scene.update(0.)
        for key in ('head','left_wrist','right_wrist','overview'):
            if key not in self.scene.cameras:continue
            Image.fromarray(self.scene.cameras[key].data.output['rgb'][0,:,:,:3].cpu().numpy()).save(self.out/(stage+'-'+key+'.png'))
        print('DEMO_STAGE '+json.dumps(value),flush=True)

    def act(self,left='STILL',right='STILL',mm=20,rotation_deg=10.):
        limit=self.scene.spec.get('expert_action_budget',600)
        if self.c.steps>=limit:raise RuntimeError(f'Expert demo exceeded its {limit}-step bound')
        receipt=self.c.action(left,right,mm,rotation_deg=rotation_deg)
        with (self.out/'demo-actions.private.jsonl').open('a') as f:f.write(json.dumps(dict(stage=self.stage,left=left,right=right,step_mm=mm,rotation_deg=rotation_deg,
            tips={s:self.tip(s).tolist() for s in ('left','right')},**receipt))+'\n')

    def execute_joint_path(self,side,plan,guard=None,done=None,tracking_tolerance=.001,
                           minimum_settle_seconds=.12,maximum_settle_seconds=.8):
        """Explicit private entry; never promotes a planner result to success."""
        isolated_e37=(getattr(self,'_engineering_e37_verified_path',False) is True
            and self.control_report.get('engineering_reference_only') is True
            and self.scene.spec.get('id')=='E37' and self.scene.spec.get('seed')==4201
            and self.scene.spec.get('execution_design',{}).get('condition')=='R')
        isolated_e31=(getattr(self,'_engineering_e31_verified_path',False) is True
            and self.control_report.get('engineering_reference_only') is True
            and self.scene.spec.get('id')=='E31' and self.scene.spec.get('seed')==4201
            and self.scene.spec.get('execution_design',{}).get('condition')=='I'
            and self.scene.spec['execution_design'].get('revision')=='embodied50-execution-v3-20261102'
            and (self.scene.spec.get('variant')=='C' or
                 (self.scene.spec.get('variant')=='B' and getattr(self.c,'_engineering_diagnostic_only',False))))
        if not self.smooth and not isolated_e37 and not isolated_e31:
            raise ValueError('Joint-path entry requires private smooth recording or explicit isolated author')
        if (not isinstance(plan,dict) or plan.get('status')!='Success' or plan.get('verified') is not True):
            raise ValueError('Private joint path requires planner status Success and verified=True')
        expected=self.scene.embodiment.arm_joints
        if list(plan.get('joint_names',[]))!=expected:
            raise ValueError('Planner joint_names do not match the selected native arm ordering')
        if side not in self.scene.robots:raise ValueError('Unknown private joint-path hand')
        if self.c.steps>=self.scene.spec.get('expert_action_budget',600):
            raise RuntimeError('Private joint-path action budget exhausted')
        if guard is None and self.carried_payload is not None:
            name,payload_side=self.carried_payload
            def guard():
                state,_=self.c.snapshot()
                if not state[name]['grasp'][0 if payload_side=='left' else 1]:
                    raise RuntimeError('Physical payload grip lost during native joint-path transport: '+name)
        if (plan.get('metadata') or {}).get('requires_native_grasp_guard') is True and not callable(guard):
            raise ValueError('Held-geometry plan requires a callable native grasp guard')
        if ((plan.get('metadata') or {}).get('requires_native_e42_contact_guards') is True
                and not getattr(guard,'covers_e42_native_contacts',False)):
            raise ValueError('E42 contact-entry plan requires the full native contact guard')
        position=np.asarray(plan.get('position',[]),float)
        velocity=np.asarray(plan.get('velocity',[]),float)
        attempt=getattr(self,'_joint_path_attempts',0)+1;self._joint_path_attempts=attempt
        inputs=self.out/f'joint-path-input-{attempt:06d}.private.npz'
        np.savez_compressed(inputs,position=position,velocity=velocity,dt=plan.get('dt'))
        robot=self.scene.robots[side];arm=self.c.ids[side][0]
        metadata=dict(plan.get('metadata') or {})
        metadata.update(status='Success',verified=True,joint_names=expected)
        command=dict(stage=self.stage,side=side,step_before=self.c.steps,time_unix_s=time.time(),
            input_file=inputs.name,input_sha256=hashlib.sha256(inputs.read_bytes()).hexdigest(),
            native_start_joints=robot.data.joint_pos[0,arm].cpu().tolist(),
            native_start_tcp_task=self.tip(side).tolist(),planned_samples=len(position),
            dt=plan.get('dt'),planner_metadata=metadata,target_world=plan.get('target_world'),
            planner_diagnostics=plan.get('diagnostics'),
            tracking_tolerance_rad=tracking_tolerance,minimum_settle_seconds=minimum_settle_seconds,
            maximum_settle_seconds=maximum_settle_seconds,joint_velocity_feedforward=True)
        with (self.out/'joint-path-commands.private.jsonl').open('a') as stream:
            stream.write(json.dumps(command,default=lambda value:value.tolist())+'\n')
        self.control_report['joint_path_attempts']+=1
        receipt=self.c.author_joint_path(side,position,velocity,plan.get('dt'),guard=guard,done=done,
            metadata=metadata,tracking_tolerance=tracking_tolerance,
            minimum_settle_seconds=minimum_settle_seconds,maximum_settle_seconds=maximum_settle_seconds)
        self.control_report['joint_path_completed_calls']+=1
        with (self.out/'joint-path-receipts.private.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(stage=self.stage,tips={s:self.tip(s).tolist() for s in self.scene.robots},
                actual_task_score=self.c.evaluator.result(),**receipt),default=lambda value:value.tolist())+'\n')
        return receipt

    def plan_and_execute_joint_path(self,side,task_tcp_goal,guard=None,done=None,**execution_options):
        """One-shot engineering probe only; no existing expert calls this API."""
        from .author_mplib_planner import plan
        proposed=plan(self.scene,self.c,side,task_tcp_goal)
        with (self.out/'joint-planner-results.private.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(stage=self.stage,side=side,
                status=proposed.get('status'),verified=proposed.get('verified'),
                diagnostics=proposed.get('diagnostics')),default=lambda v:v.tolist())+'\n')
        if proposed.get('status')!='Success' or proposed.get('verified') is not True:
            raise RuntimeError('Private global waypoint recovery refused: '+json.dumps(dict(
                status=proposed.get('status'),diagnostics=proposed.get('diagnostics')),
                default=lambda v:v.tolist()))
        return self.execute_joint_path(side,proposed,guard=guard,done=done,**execution_options)

    def align_gripper_axis(self, side, direction):
        """Align the measured 3D finger axis using public rotation actions."""
        desired=np.asarray(direction,float)
        if desired.shape!=(3,) or not np.isfinite(desired).all() or np.linalg.norm(desired)<1e-6:
            raise ValueError('Reviewed finite 3D grasp axis required')
        desired/=np.linalg.norm(desired)
        robot=self.scene.robots[side]
        ids=[robot.find_bodies(name)[0][0] for name in self.scene.embodiment.fingers]
        recording=self.scene.embodiment.config.get('author_recording',{})
        if self.smooth and recording.get('palm_down_grasp',False):
            if self.scene.embodiment.name!='franka':
                raise ValueError('Downward grasp profile requires the native Panda hand')
            from .author_orientation import panda_downward_grasp_delta, _axis_angle
            for _ in range(3):
                axis=(robot.data.body_pos_w[0,ids[0]]-robot.data.body_pos_w[0,ids[1]]).cpu().numpy()
                axis=self.scene.layout.task_rotation.T@axis
                base_world=matrix_from_quat(robot.data.root_quat_w)[0].cpu().numpy()
                task_base=self.scene.layout.task_rotation.T@base_world
                current=task_base@matrix_from_quat(self.c.pose(side)[1])[0].cpu().numpy()
                joint7_state=None
                if recording.get('panda_choose_empty_grasp_assignment_joint7',False):
                    state,_=self.c.snapshot()
                    if any(value['grasp'][0 if side=='left' else 1] for value in state.values()):
                        raise RuntimeError('Equivalent empty-hand finger assignment requires a released hand')
                    joints,_=robot.find_joints('panda_joint7')
                    if len(joints)!=1:raise RuntimeError('Native Panda joint7 identity required')
                    joint=int(joints[0]);limits=robot.data.soft_joint_pos_limits[0,joint].cpu().tolist()
                    joint7_state=[float(robot.data.joint_pos[0,joint]),*limits]
                delta=panda_downward_grasp_delta(current,axis,desired,**({'joint7_state':joint7_state} if joint7_state is not None else {}))
                if _axis_angle(delta)[1]<np.deg2rad(.5):return
                self.rotate_tcp_smooth(side,delta)
            raise RuntimeError('Native Panda downward grasp orientation did not converge')
        labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
        for _ in range(72):
            axis=(robot.data.body_pos_w[0,ids[0]]-robot.data.body_pos_w[0,ids[1]]).cpu().numpy()
            axis=self.scene.layout.task_rotation.T@axis
            axis/=max(np.linalg.norm(axis),1e-9)
            # Pinching a wall is invariant to swapping the two real fingers.
            target=desired if axis@desired>=0 else -desired
            angle=float(np.arccos(np.clip(axis@target,-1,1)))
            if angle<np.deg2rad(5):return
            rotation=np.cross(axis,target);rotation/=max(np.linalg.norm(rotation),1e-9)
            if self.smooth and self.scene.embodiment.config.get('author_recording',{}).get('continuous_orientation',False):
                from .realworld_tool_expert import _axis_rotation
                self.rotate_tcp_smooth(side,_axis_rotation(rotation,angle))
                continue
            component=int(np.argmax(np.abs(rotation)))
            token=labels[component][int(rotation[component]<0)]
            self.act(token if side=='left' else 'STILL',token if side=='right' else 'STILL',
                     rotation_deg=min(10.,max(.5,abs(float(np.degrees(angle*rotation[component]))))))
        raise RuntimeError('Real gripper could not align to reviewed grasp axis')

    def rotate_tcp_smooth(self,side,delta_task,guard=None,done=None,verify_done=None):
        """Private physical rotation with a fixed measured TCP and no backlog."""
        from .author_orientation import native_rotate
        if self.c.steps>=self.scene.spec.get('expert_action_budget',2400):
            raise RuntimeError('Private author trajectory budget exhausted')
        recording=self.scene.embodiment.config.get('author_recording',{})
        options=dict(guard=guard,
            max_angular_speed=recording.get('max_angular_speed_rad_s'),
            max_angular_acceleration=recording.get('max_angular_acceleration_rad_s2'))
        if done is not None:options['done']=done
        receipt=native_rotate(self.c,side,delta_task,**options)
        verify=done if verify_done is None else verify_done
        actual_done=bool(done is not None and receipt.get('done_reached') and verify())
        receipt['actual_done_verified_after_settle']=actual_done
        with (self.out/'demo-actions.private.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(stage=self.stage,control='private_continuous_orientation',
                side=side,delta_task=np.asarray(delta_task).tolist(),**receipt))+'\n')
        if not receipt['target_reached'] and not actual_done:
            raise RuntimeError('Continuous orientation target not reached: '+json.dumps(receipt))
        return receipt

    def rotate_held_smooth(self,name,side,target,guard=None):
        target=np.asarray(target,float)
        recording=self.scene.embodiment.config.get('author_recording',{})
        face_goal=None
        if self.scene.spec.get('id')=='E31' and recording.get('e31_semantic_face_orientation',False):
            semantic=self.scene.spec['semantic']
            role=next((key for key in ('bowl','plate') if semantic[key]==name),None)
            if role is None:raise ValueError('E31 face alignment requires the reviewed bowl/plate actor')
            spec=next(value for value in self.scene.spec['objects'] if value['id']==name)
            face_goal=(spec.get('up_axis',[0,0,1]),semantic[role+'_face'])
        def requested_delta(state):
            if face_goal is None:
                delta=target@state[name]['mat'].T
                reached=float(np.arccos(np.clip((np.trace(delta)-1)/2,-1,1)))<np.deg2rad(4)
                return delta,reached
            from .author_face_orientation import face_alignment
            result=face_alignment(state[name]['mat'],*face_goal,
                tolerance_degrees=recording.get('e31_normal_tolerance_deg',10.))
            with (self.out/'orientation-goals.private.jsonl').open('a') as stream:
                stream.write(json.dumps(dict(stage=self.stage,object=name,side=side,
                    **{key:(value.tolist() if isinstance(value,np.ndarray) else value)
                       for key,value in result.items()}))+'\n')
            return result['delta_task'],result['reached']
        if guard is None:
            def guard():
                state,_=self.c.snapshot()
                if not state[name]['grasp'][0 if side=='left' else 1]:
                    raise RuntimeError('Lost physical grasp while rotating '+name)
        for _ in range(4):
            guard();state,_=self.c.snapshot();delta,reached=requested_delta(state)
            if reached:return
            self.rotate_tcp_smooth(side,delta,guard)
        state,_=self.c.snapshot()
        if requested_delta(state)[1]:return
        raise RuntimeError('Actual held-object orientation failed to converge: '+name)

    def neutralize_empty_wrist(self,side):
        robot=self.scene.robots[side]
        base_world=matrix_from_quat(robot.data.root_quat_w)[0].cpu().numpy()
        current=matrix_from_quat(self.c.pose(side)[1])[0].cpu().numpy()
        neutral=matrix_from_quat(self.neutral_tcp_quaternions[side])[0].cpu().numpy()
        task_base=self.scene.layout.task_rotation.T@base_world
        delta=task_base@(neutral@current.T)@task_base.T
        from .author_orientation import _axis_angle
        axis,angle=_axis_angle(delta)
        if angle<np.deg2rad(.5):
            position,quaternion=self.c.pose(side)
            self.c.targets[side]=(position.clone(),quaternion.clone())
            return
        # At an empty-hand 180-degree yaw, the same SO(3) endpoint has two
        # paths. Choose the one unwinding Panda joint7 toward its home value.
        if self.scene.embodiment.name=='franka' and angle>np.deg2rad(150) and abs(axis[2])>.9:
            ids,_=robot.find_joints('panda_joint7')
            if len(ids)==1:
                wanted=float(self.scene.embodiment.config['robots'][side]['initial_joints']['panda_joint7'])
                difference=wanted-float(robot.data.joint_pos[0,ids[0]])
                if abs(difference)>1e-3 and axis[2]*(-np.sign(difference))<0:
                    from .realworld_tool_expert import _axis_rotation
                    # Reverse direction using the complementary full angle;
                    # reversing only the axis would change a non-pi endpoint.
                    half=_axis_rotation(-axis,(2*np.pi-angle)/2)
                    self.rotate_tcp_smooth(side,half);self.rotate_tcp_smooth(side,half)
                    return
        self.rotate_tcp_smooth(side,delta)

    def release_generated(self,side):
        opening=self.scene.embodiment.config.get('author_recording',{}).get('release_opening_m')
        if opening is None:
            return self.act('RELEASE' if side=='left' else 'STILL','RELEASE' if side=='right' else 'STILL')
        opening=float(opening)
        if self.scene.embodiment.name!='franka' or not .01<=opening<=.04:
            raise ValueError('Private partial release needs a valid native Panda finger opening')
        self.c.grips[side]=opening
        with (self.out/'demo-actions.private.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(stage=self.stage,control='private_gripper_opening',side=side,
                per_finger_joint_target_m=opening))+'\n')
        return self.act()

    def prepare_generated_gripper(self,side):
        """Set a reviewed approach opening while the hand is above the source."""
        opening=self.scene.embodiment.config.get('author_recording',{}).get('pre_grasp_opening_m')
        if opening is None:return
        opening=float(opening)
        if self.scene.embodiment.name!='franka' or not np.isfinite(opening) or not .005<=opening<=.04:
            raise ValueError('Private pre-grasp opening requires a valid native Panda target')
        if self.carried_payload is not None:
            raise RuntimeError('Cannot prepare an open gripper while carrying a payload')
        self.c.grips[side]=opening
        with (self.out/'demo-actions.private.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(stage=self.stage,control='private_pre_grasp_opening',side=side,
                per_finger_joint_target_m=opening))+'\n')
        return self.act()

    def activate_generated_hand(self,side,previous,home_xy,clear_z):
        """Park the released hand before bringing its peer into the workspace."""
        if side==previous:return side
        if self.carried_payload is not None:
            raise RuntimeError('Cannot switch physical hands while holding a payload')
        if (getattr(self,'_execution_design_reference_authorized',False)
                and self.scene.spec.get('id')=='E25'):
            from .execution_design_e25_functional import withdraw_released
            withdraw_released(self,previous)
            # A peer still at its high idle pose enters through the known
            # reachable central workspace. The released hand stays at its
            # achieved safe pose; no neutral-wrist or exact-home cycle.
            if float(self.tip(side)[2])>1.05:
                self.move_generated({side:[*home_xy[side],float(self.tip(side)[2])]},tolerance=.008)
                self.move_generated({side:[*home_xy[side],max(.95,clear_z)]},tolerance=.008)
            return side
        recording=self.scene.embodiment.config.get('author_recording',{})
        park_z=float(recording.get('idle_park_z',1.25))
        base=self.scene.world_to_task(np.asarray(self.scene.embodiment.config['robots'][previous]['position'])+np.asarray(getattr(self.scene,'origin',(0.,0.,0.))))
        if not recording.get('idle_park_direct',False):
            self.move_generated({previous:[*self.tip(previous)[:2],park_z]},tolerance=.006)
        self.move_generated({previous:[base[0]+.15,base[1]+(.22 if previous=='left' else -.22),park_z]},tolerance=.006)
        # Unpark at the known reachable home XY before lowering. Directly
        # lowering at the near-base parking XY can cross the inner IK limit.
        self.move_generated({side:[*home_xy[side],park_z]},tolerance=.006)
        self.move_generated({side:[*home_xy[side],clear_z]},tolerance=.006)
        return side

    def tcp_rotation_task(self, side):
        """Read the achieved TCP rotation in the room task frame."""
        robot=self.scene.robots[side]
        base=matrix_from_quat(robot.data.root_quat_w)[0].cpu().numpy()
        local=matrix_from_quat(self.c.pose(side)[1])[0].cpu().numpy()
        return self.scene.layout.task_rotation.T@base@local

    def finger_geometry(self, side):
        """Actual collision mesh vertices transformed by current rigid-body poses."""
        from pxr import Usd,UsdGeom,UsdPhysics
        import omni.usd
        if not hasattr(self,'_finger_collision_points'):self._finger_collision_points={}
        robot=self.scene.robots[side]
        if side not in self._finger_collision_points:
            stage=omni.usd.get_context().get_stage();cache=UsdGeom.XformCache()
            entries=[]
            for name in self.scene.embodiment.fingers:
                body=stage.GetPrimAtPath(f'{self.scene.root_path}/{side}_robot/{name}')
                inverse=cache.GetLocalToWorldTransform(body).GetInverse()
                vertices=[]
                for prim in Usd.PrimRange(body,Usd.TraverseInstanceProxies()):
                    collision=prim;collidable=False
                    while collision and collision!=body:
                        if collision.HasAPI(UsdPhysics.CollisionAPI):collidable=True;break
                        collision=collision.GetParent()
                    if prim.IsA(UsdGeom.Mesh) and collidable:
                        points=np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(),float)
                        matrix=np.asarray(cache.GetLocalToWorldTransform(prim)*inverse,float)
                        vertices.append(points@matrix[:3,:3]+matrix[3,:3])
                if not vertices:raise RuntimeError('No actual finger collision mesh for '+name)
                entries.append((robot.find_bodies(name)[0][0],np.concatenate(vertices)))
            self._finger_collision_points[side]=entries
        fingers=[]
        for index,(bid,points) in enumerate(self._finger_collision_points[side]):
            rotation=self.scene.layout.task_rotation.T@matrix_from_quat(robot.data.body_quat_w[:,bid])[0].cpu().numpy()
            position=self.scene.world_to_task(robot.data.body_pos_w[0,bid].cpu().numpy())
            actual=points@rotation.T+position
            if actual.ndim!=2 or actual.shape[1]!=3 or not len(actual) or not np.isfinite(actual).all():
                raise RuntimeError('Invalid actual finger collision vertices')
            lo=actual.min(axis=0);hi=actual.max(axis=0)
            fingers.append(dict(name=self.scene.embodiment.fingers[index],body_index=int(bid),
                collision_vertex_count=len(actual),aabb_min_task_m=lo.tolist(),aabb_max_task_m=hi.tolist(),
                aabb_center_task_m=((lo+hi)/2).tolist(),mesh_centroid_task_m=actual.mean(axis=0).tolist(),
                lowest_point_task_m=actual[int(np.argmin(actual[:,2]))].tolist(),
                body_origin_task_m=position.tolist()))
        if not fingers:raise RuntimeError('No actual finger collision geometry')
        return dict(source='actual_collision_mesh_current_body_pose',coordinate_frame='room_task',
                    room_root=self.scene.root_path,side=side,fingers=fingers,
                    lowest_z_task_m=min(f['lowest_point_task_m'][2] for f in fingers))

    def floor_clear_tcp(self, side, floor=.8):
        """Measure real finger collision toes to avoid driving them into table."""
        lowest=self.finger_geometry(side)['lowest_z_task_m']
        return float(floor-(lowest-self.tip(side)[2])+.0003)

    def rotate_held(self, name, side, goal):
        """Rotate a held body with actual pose feedback, never edit its pose."""
        import math
        from .execution_design import REVISION_V3
        if (getattr(self,'_execution_design_reference_authorized',False)
                and self.scene.spec['id']=='E31'
                and self.scene.spec.get('execution_design',{}).get('revision')==REVISION_V3):
            from .execution_design_e31_orientation import align_face
            return align_face(self,name,side,goal)
        if (getattr(self,'_execution_design_reference_authorized',False)
                and self.scene.spec['id']=='E15'
                and self.scene.spec.get('execution_design',{}).get('revision')==REVISION_V3):
            from .execution_design_e15_wrist import rotate_prepared_payload
            if rotate_prepared_payload(self,name,side,goal):return
        if (getattr(self,'_execution_design_reference_authorized',False)
                and self.scene.spec.get('execution_design',{}).get('revision')==REVISION_V3
                and self.scene.spec['id']=='E25' and self.scene.spec['variant']=='B'):
            from .execution_design_e25_b_transport import rotate_transport_payload
            rotate_transport_payload(self,name,side,goal)
            return
        if (getattr(self,'_execution_design_reference_authorized',False)
                and self.scene.spec.get('execution_design',{}).get('revision')==REVISION_V3
                and self.scene.spec['id']=='E25' and self.scene.spec['variant']=='A'
                and name=='knife' and side=='left'):
            from .execution_design_e25_a_receiver import lift_knife_for_rotation
            lift_knife_for_rotation(self)
        roll,pitch,yaw=[float(goal.get(k,0.)) for k in ('roll','pitch','yaw')]
        cx,sx=math.cos(roll),math.sin(roll);cy,sy=math.cos(pitch),math.sin(pitch);cz,sz=math.cos(yaw),math.sin(yaw)
        target=np.array([[cz,-sz,0],[sz,cz,0],[0,0,1.]])@np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])@np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
        recording=self.scene.embodiment.config.get('author_recording',{})
        if self.scene.spec['id']=='E39' and recording.get('e39_equivalent_wrist_yaw',False):
            from .author_e39_wrist import rotate_held
            return rotate_held(self,name,side,goal)
        if self.scene.spec['id']=='E27' and recording.get('e27_working_axis_yaw_only',False):
            if 'roll' in goal or 'pitch' in goal:
                raise ValueError('E27 yaw-only author route cannot discard a declared roll/pitch goal')
            from .author_yaw_orientation import working_axis_yaw_target
            state,_=self.c.snapshot()
            axis=self.scene.spec['semantic']['orientation_targets'][name]['working_axis_local']
            target=working_axis_yaw_target(state[name]['mat'],axis,yaw)
            with (self.out/'orientation-goals.private.jsonl').open('a') as stream:
                stream.write(json.dumps(dict(stage=self.stage,object=name,
                    constraint='source_projected_working_axis_yaw',yaw=yaw,
                    actual_rotation=state[name]['mat'].tolist(),target_rotation=target.tolist(),
                    unrequested_roll_pitch_preserved=True))+'\n')
        if self.smooth and self.scene.embodiment.config.get('author_recording',{}).get('continuous_orientation',False):
            return self.rotate_held_smooth(name,side,target)
        labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
        for _ in range(80):
            state,_=self.c.snapshot();current=state[name]['mat'];delta=target@current.T
            cosine=np.clip((np.trace(delta)-1)/2,-1,1);angle=float(np.arccos(cosine))
            if angle<np.deg2rad(6):return
            if not state[name]['grasp'][0 if side=='left' else 1]:
                raise RuntimeError('Lost physical grasp while rotating '+name)
            if np.pi-angle<.01:
                values,vectors=np.linalg.eigh((delta+np.eye(3))/2)
                axis=vectors[:,int(np.argmax(values))]
            else:
                axis=np.array([delta[2,1]-delta[1,2],delta[0,2]-delta[2,0],delta[1,0]-delta[0,1]])/(2*np.sin(angle))
            component=int(np.argmax(np.abs(axis)));token=labels[component][0 if axis[component]>0 else 1]
            self.act(token if side=='left' else 'STILL',token if side=='right' else 'STILL',
                     rotation_deg=min(10.,max(.5,abs(float(np.degrees(angle*axis[component]))))))
        raise RuntimeError('Held object orientation did not converge: '+name)

    def move(self,goals,tolerance=.0035):
        if self.smooth:return self.move_smooth(goals,tolerance=tolerance)
        for _ in range(100):
            errors={s:np.asarray(p)-self.tip(s) for s,p in goals.items()}
            active={s:e for s,e in errors.items() if np.max(np.abs(e))>tolerance}
            if not active:return
            axes={s:int(np.argmax(np.abs(e))) for s,e in active.items()}
            mm=min(25.,max(.5,min(abs(e[axes[s]])*1000 for s,e in active.items())))
            tokens={s:(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axes[s]][int(e[axes[s]]<0)] for s,e in active.items()}
            self.act(tokens.get('left','STILL'),tokens.get('right','STILL'),mm)
        raise RuntimeError('Waypoint unreachable at '+self.stage+'; '+json.dumps({s:e.tolist() for s,e in errors.items()}))

    def move_smooth(self,goals,tolerance=.004,guard=None,done=None,max_speed=None,max_acceleration=None):
        """Direct 3D private author trajectory, measured actuator feedback."""
        targets={s:np.asarray(p,float) for s,p in goals.items()}
        if guard is None and self.carried_payload is not None:
            name,side=self.carried_payload
            def guard():
                state,_=self.c.snapshot()
                if not state[name]['grasp'][0 if side=='left' else 1]:
                    raise RuntimeError('Physical payload grip lost during continuous transport: '+name)
        loaded=self.stage.startswith(('grasped-','held-','mechanism-open-','mechanism-close-'))
        recording=self.scene.embodiment.config.get('author_recording',{})
        if max_speed is None:max_speed=float(recording.get('loaded_speed_m_s',.075)) if loaded or guard is not None else .18
        if max_acceleration is None:max_acceleration=float(recording.get('loaded_acceleration_m_s2',.35)) if loaded or guard is not None else .6
        from .recording_trajectory import scaled_motion_limits
        max_speed,max_acceleration=scaled_motion_limits(max_speed,max_acceleration,float(recording.get('trajectory_speed_scale',1.)))
        for attempt in range(3):
            if guard is not None:guard()
            if done is not None and done():return
            errors={s:targets[s]-self.tip(s) for s in targets}
            if all(np.max(np.abs(e))<=tolerance for e in errors.values()):return
            if self.c.steps>=self.scene.spec.get('expert_action_budget',600):
                raise RuntimeError('Private author trajectory budget exhausted')
            # Persist measured inputs BEFORE entering native motion, so a
            # blocked/abnormally long call remains diagnosable without a receipt.
            command=dict(stage=self.stage,attempt=attempt,step_before=self.c.steps,
                time_unix_s=time.time(),task_targets={s:p.tolist() for s,p in targets.items()},
                start_tips_task={s:self.tip(s).tolist() for s in targets},
                max_speed_m_s=max_speed,max_acceleration_m_s2=max_acceleration,
                joint_velocity_feedforward=bool(getattr(self.c,'author_joint_velocity_feedforward',False)),
                maximum_planned_physics_seconds=30.)
            with (self.out/'trajectory-commands.private.jsonl').open('a') as f:
                f.write(json.dumps(command)+'\n')
            receipt=self.c.author_move(targets,max_speed=max_speed,max_acceleration=max_acceleration,guard=guard,done=done,tracking_tolerance=tolerance)
            with (self.out/'demo-actions.private.jsonl').open('a') as f:
                f.write(json.dumps(dict(stage=self.stage,control='private_continuous_cartesian_minimum_jerk',
                    task_targets={s:p.tolist() for s,p in targets.items()},attempt=attempt,
                    tips={s:self.tip(s).tolist() for s in targets},**receipt))+'\n')
            if done is not None and done():return
        if all(np.max(np.abs(targets[s]-self.tip(s)))<=tolerance for s in targets):return
        if ((recording.get('global_empty_waypoint_recovery',False)
                or recording.get('global_waypoint_recovery',False)) and len(targets)==1):
            side=next(iter(targets));state,_=self.c.snapshot()
            empty=not any(v['grasp'][0 if side=='left' else 1] for v in state.values())
            payload=getattr(self,'carried_payload',None)
            held_recovery=(recording.get('global_waypoint_recovery',False)
                and payload is not None and payload[1]==side and state[payload[0]]['grasp'][0 if side=='left' else 1])
            if (empty and guard is None) or held_recovery:
                # A stalled local IK branch can have a different valid joint
                # solution. Plan against the fresh full native world once.
                self.plan_and_execute_joint_path(side,targets[side],guard=guard,done=done,
                    tracking_tolerance=.002)
                if np.max(np.abs(targets[side]-self.tip(side)))<=tolerance:return
        errors={s:(targets[s]-self.tip(s)).tolist() for s in targets}
        raise RuntimeError('Continuous author waypoint unreachable at '+self.stage+'; '+json.dumps(errors))

    def calibrate_generated_axes(self, sides=('left', 'right')):
        """Measure the sign of each public Cartesian token on this rig.

        The RoboTwin UR5 and the RoboDojo X5 expose the same public action
        names but their USD base rotations differ.  A three millimetre probe
        at the settled pose prevents the expert recorder from assuming a
        world-axis sign that is only valid for one embodiment.
        """
        self.generated_axis_signs = {}
        labels = (('FWD', 'BACK'), ('LEFT', 'RIGHT'), ('UP', 'DOWN'))
        for side in sides:
            self.generated_axis_signs[side] = {}
            for axis, (positive, negative) in enumerate(labels):
                before = self.tip(side)
                self.act(positive if side == 'left' else 'STILL',
                         positive if side == 'right' else 'STILL', 3.)
                delta = self.tip(side) - before
                response = float(delta[axis])
                if abs(response) < 1e-5:
                    raise RuntimeError(f'Unable to calibrate {side} axis {axis}: {delta.tolist()}')
                self.generated_axis_signs[side][axis] = 1 if response > 0 else -1
                self.act(negative if side == 'left' else 'STILL',
                         negative if side == 'right' else 'STILL', 3.)

    def move_generated(self, goals, tolerance=.004):
        """Move using the empirically calibrated public action directions."""
        if self.smooth:return self.move_smooth(goals,tolerance=tolerance)
        signs = getattr(self, 'generated_axis_signs', {})
        if self.scene.embodiment.name == 'arx_x5':
            tolerance = max(tolerance, .025)
        from .execution_design_generated_route import MEASURED_CLEARANCE_TASKS
        from .execution_design import REVISION_V3
        engineering = (getattr(self, '_execution_design_reference_authorized', False)
            and self.scene.spec.get('execution_design', {}).get('revision') == REVISION_V3
            and self.scene.spec.get('id') in MEASURED_CLEARANCE_TASKS)
        back25_payload_guard = (getattr(self, '_execution_design_reference_authorized', False)
            and self.scene.spec.get('execution_design', {}).get('revision') == REVISION_V3
            and self.scene.spec.get('id') in {f'E{i:02}' for i in range(26,51)})
        progress = []
        for _ in range(360 if engineering else 120):
            if (engineering or back25_payload_guard) and getattr(self, 'carried_payload', None) is not None:
                name, hand = self.carried_payload
                native, _ = self.c.snapshot()
                if not native[name]['grasp'][0 if hand == 'left' else 1]:
                    raise RuntimeError('Actual payload grip lost during engineering waypoint: '+name)
            errors = {s: np.asarray(p, dtype=float) - self.tip(s)
                      for s, p in goals.items()}
            active = {s: e for s, e in errors.items()
                      if np.max(np.abs(e)) > tolerance}
            if not active:
                return
            if engineering:
                progress.append(max(float(np.linalg.norm(e)) for e in active.values()))
                if (self.scene.spec['id']=='E25'and len(progress)>=4
                        and progress[-4]-min(progress[-3:])<.0002):
                    raise RuntimeError('Measured engineering waypoint stalled after three actions at '+self.stage)
                # More iterations are allowed only while measured error improves.
                # A blocked reference cannot spend the larger budget pushing.
                if (len(progress) >= 32
                        and min(progress[-32:-24])-min(progress[-8:]) < .0005):
                    raise RuntimeError('Measured engineering waypoint stalled at '+self.stage)
            axes = {s: int(np.argmax(np.abs(e))) for s, e in active.items()}
            # Loaded objects need a slower Cartesian stream than an empty
            # wrist.  The coarse 20 mm public step can momentarily unload a
            # finger on the last (left-edge) placement of permutation C;
            # keeping the carried box at 8 mm also makes the policy robust to
            # the small ARX contact margin.  Empty-arm routing retains the
            # faster step so the 600-action demo bound is preserved.
            max_mm = float(self.scene.spec.get('expert_loaded_step_mm',8.)) if self.stage.startswith('grasped-') else 20.
            mm = min(max_mm, max(.5, min(abs(e[axes[s]]) * 1000 for s, e in active.items())))
            tokens = {}
            labels = (('FWD', 'BACK'), ('LEFT', 'RIGHT'), ('UP', 'DOWN'))
            for side, error in active.items():
                axis = axes[side]
                desired = 1 if error[axis] > 0 else -1
                positive_sign = signs.get(side, {}).get(axis, 1)
                tokens[side] = labels[axis][0] if desired == positive_sign else labels[axis][1]
            self.act(tokens.get('left', 'STILL'), tokens.get('right', 'STILL'), mm)
        raise RuntimeError('Generated waypoint unreachable at '+self.stage+'; '+json.dumps({s:e.tolist() for s,e in errors.items()}))

    def lift_clear(self,sides=('left','right'),z=1.10):
        self.move({s:[*self.tip(s)[:2],z] for s in sides})

    def park(self):
        self.lift_clear();x=self.scene.embodiment.base_x+.20
        self.move({'left':[x,.25,1.10],'right':[x,-.25,1.10]})

    def carry_tray(self,name,xy,bottom):
        self.note('approach-'+name+'-'+str(self.c.steps));spec=next(o for o in self.scene.spec['objects'] if o['id']==name)
        self.park();self.act('RELEASE','RELEASE')
        state,_=self.c.snapshot();a=state[name]
        targets={s:a['pos']+a['mat']@np.asarray(spec['grasp_sides'][i]) for s,i in [('left',1),('right',0)]}
        self.move({s:[*p[:2],1.10] for s,p in targets.items()});self.move(targets)
        for _ in range(3):self.act('GRASP','GRASP')
        state,_=self.c.snapshot()
        if not all(state[name]['grasp']):
            self.note('grasp-failed-'+name);raise RuntimeError('Both physical tray-handle grasps required')
        self.note('held-'+name+'-'+str(self.c.steps))
        def axis_to(axis,value):
            history=[]
            for _ in range(65):
                p=self.pos(name);error=value-p[axis]
                if abs(error)<.0035:return
                state,_=self.c.snapshot()
                if not all(state[name]['grasp']):raise RuntimeError('Tray grip lost during '+self.stage)
                history.append(float(p[axis]))
                if len(history)>15 and max(history[-12:])-min(history[-12:])<.001:raise RuntimeError('Tray movement blocked')
                token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error<0)]
                self.act(token,token,min(20.,max(.5,abs(error)*1000)))
            raise RuntimeError('Tray axis did not converge')
        axis_to(2,1.01);axis_to(0,xy[0]);axis_to(1,xy[1]);axis_to(2,bottom+spec['size'][2]+.002)
        self.act('RELEASE','RELEASE');self.lift_clear();self.park()
        for _ in range(3):self.act()
        self.note('placed-'+name+'-'+str(self.c.steps))

    def extract(self,name,xy):
        self.note('extract-'+name);p=self.pos(name);side='left' if xy[1]>=0 else 'right'
        # Open across X rather than the narrow gap between the piece and tray Y wall.
        for _ in range(9):self.act('ROTATE_CCW' if side=='left' else 'STILL','ROTATE_CCW' if side=='right' else 'STILL')
        self.lift_clear((side,));self.move({side:[*p[:2],1.10]});self.note('above-'+name)
        self.move({side:p+[0,0,.008]});self.note('at-'+name)
        for _ in range(2):self.act('GRASP' if side=='left' else 'STILL','GRASP' if side=='right' else 'STILL')
        state,_=self.c.snapshot()
        if not state[name]['grasp'][0 if side=='left' else 1]:
            self.note('piece-grasp-failed');raise RuntimeError('Target piece not physically grasped')
        self.note('grasped-'+name);self.lift_clear((side,));self.note('lifted-'+name)
        self.move({side:[*xy,1.10]});self.note('over-goal-'+name)
        half=next(o['size'][2] for o in self.scene.spec['objects'] if o['id']==name)
        self.move({side:[*xy,.8+half+.004]})
        self.act('RELEASE' if side=='left' else 'STILL','RELEASE' if side=='right' else 'STILL');self.lift_clear((side,))
        for _ in range(9):self.act('ROTATE_CW' if side=='left' else 'STILL','ROTATE_CW' if side=='right' else 'STILL')
        self.park()
        for _ in range(3):self.act()
        self.note('extracted-'+name)

    def solve_execution_design(self):
        """Engineering reference only; never a model-facing local-rule demo."""
        from .execution_design_expert import solve_execution_design
        design=self.scene.spec['execution_design']
        if design.get('schema') not in ('execution-design-v1','execution-design-v2'):
            raise ValueError('Unknown execution design reference version')
        if not getattr(self.c.evaluator,'initial_sealed',False):
            raise ValueError('Engineering reference requires sealed measured initial state')
        self.control_report.update(media_scope='engineering_reference_only',
                                   eligible_as_model_demo=False,local_rule_demo=False)
        (self.out/'engineering-reference-only.private.json').write_text(json.dumps(dict(
            revision=design.get('revision'),eligible_as_model_demo=False,
            purpose='full workflow physical validation, not local-rule supervision'),indent=2)+'\n')
        self.note('engineering-reference-initial')
        route=solve_execution_design(self)
        self.note('engineering-reference-final')
        score=self.c.evaluator.result()
        (self.out/'engineering-reference-route.private.json').write_text(json.dumps(dict(
            route=route,native_result=score,eligible_as_model_demo=False),indent=2)+'\n')
        if not score.get('strict_success'):
            raise RuntimeError('Full-workflow reference did not pass native physical criteria')
        return score

    def solve(self):
        if self.scene.spec.get('execution_design'):
            return self.solve_execution_design()
        if self.scene.spec['id']!='F22' or self.scene.spec['seed']!=0:raise ValueError('F22 demo must use independent seed 0')
        goals=self.scene.spec['goals'];selected=next(g for g in goals if g['type']=='position' and g['object'].startswith('piece'))
        center=next(g['xy'] for g in goals if g['type']=='position' and g['object']=='upper')
        self.note('initial')
        self.carry_tray('upper',[-.16+center[0]-.12,center[1]],.8)
        self.extract(selected['object'],selected['xy'])
        self.carry_tray('upper',center,next(o['bottom'] for o in self.scene.spec['objects'] if o['id']=='upper'))
        for _ in range(5):self.act()
        self.note('final');score=self.c.evaluator.result()
        if not score['success']:raise RuntimeError('Demo final state did not pass the actual server evaluator')
        return score

    def solve_generated(self):
        """Execute reviewed placement goals through physical robot controls."""
        if (getattr(self,'_execution_design_reference_authorized',False)
                and self.scene.spec.get('id')=='E15'and self.scene.spec.get('variant')=='B'
                and self.scene.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                and not self.smooth):
            from .execution_design_e15_b_reference import solve
            return solve(self)
        if self.scene.spec.get('execution_design'):
            from .execution_design import WORKFLOW_TASKS
            if self.scene.spec['id'] in WORKFLOW_TASKS:
                return self.solve_execution_design()
            if not getattr(self,'_execution_design_reference_authorized',False):
                raise ValueError('Non-workflow execution reference requires explicit engineering routing')
        if (getattr(self,'_execution_design_reference_authorized',False)
                and self.scene.spec.get('id')=='E33'
                and self.scene.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'):
            from .execution_design_e33_transfer import solve as solve_e33_transfer
            return solve_e33_transfer(self)
        if not self.scene.spec.get('goals'):
            raise ValueError('Generated demo requires at least one goal')
        resume=getattr(self,'_engineering_e25_remaining',None)
        if resume is not None:
            from .execution_design_e25_remaining import validate_resume
            validate_resume(self,resume)
            home_xy={side:np.asarray(resume['home_xy'][side],float)for side in('left','right')}
            initial_generated_hand=resume['active_hand']
        else:
            home_xy = {s: self.tip(s)[:2].copy() for s in ('left', 'right')}
            from .execution_design_e16_parking import remember_empty_home
            remember_empty_home(self)
            if not self.smooth:self.calibrate_generated_axes()
            self.note('initial')
            self.act('RELEASE', 'RELEASE')
            if (getattr(self,'_execution_design_reference_authorized',False)
                    and self.scene.spec.get('id')=='E11'
                    and self.scene.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'):
                from .execution_design_e11_reference import move_empty_tray
                move_empty_tray(self)
            initial_generated_hand=None
            if self.scene.spec.get('task_adapter','').startswith(('realworld','full50')):
                active=self.scene.spec.get('expert_arm','left')
                if getattr(self,'_execution_design_reference_authorized',False):
                    from .execution_design_generated_route import initial_back25_hand
                    active=initial_back25_hand(self,active)
                    if (self.scene.spec.get('id') in ('E27','E34') and
                            self.scene.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'):
                        from .execution_design_cutlery_transfer import initial_pickup_hand
                        active=initial_pickup_hand(self)
                initial_generated_hand=active
                idle='right' if active=='left' else 'left'
                # Move the real idle arm out of the transfer volume. Leaving its
                # wrist at the centre made the loaded arm hit it above the table.
                self.stage='park-idle-'+idle
                base=self.scene.world_to_task(np.asarray(self.scene.embodiment.config['robots'][idle]['position'])+np.asarray(getattr(self.scene,'origin',(0.,0.,0.))))
                recording=self.scene.embodiment.config.get('author_recording',{})
                park_z=float(recording.get('idle_park_z',1.25))
                if not recording.get('idle_park_direct',False):
                    self.move_generated({idle:[*self.tip(idle)[:2],park_z]},tolerance=.006)
                self.move_generated({idle:[base[0]+.15,base[1]+(.22 if idle=='left' else -.22),park_z]},tolerance=.006)
        # Keep the carry waypoint below the UR5 shoulder singularity.  The
        # initial pose is higher, but 0.90 m leaves enough clearance for these
        # 44 mm boxes while keeping the loaded gripper in its stable workspace.
        # Keep the carried box above already placed boxes during the long
        # tabletop transfer. The X5 has a tighter vertical envelope and uses
        # its dedicated lower clearance below.
        # The UR5-W/S gripper drifts when a loaded wrist is lifted through
        # its upper shoulder band.  A 0.90 m carry plane clears these small
        # boxes while keeping the public Cartesian controller in its stable
        # workspace; Franka keeps the higher plane and X5 uses its lower one.
        if self.scene.embodiment.name == 'arx_x5':
            # The X5 policy uses a 25 mm waypoint tolerance.  At .86 m the
            # post-grasp lift is smaller than that tolerance, so the next
            # horizontal home move would start while the box is still near
            # the table.  Use a real 90 cm carry plane first.
            clear_z = .90
        elif self.scene.embodiment.name == 'ur5_wsg':
            clear_z = .90
        else:
            clear_z = 1.10
        clear_z=float(self.scene.embodiment.config.get('author_recording',{}).get('transfer_clearance_z',clear_z))
        if self.smooth and self.scene.spec['id'] in ('E35','E36'):
            clear_z=.98
        approach_z=float(self.scene.embodiment.config.get('author_recording',{}).get('pregrasp_clearance_z',clear_z))
        from .execution_design_generated_route import MEASURED_CLEARANCE_TASKS, HAND_SELECTION_TASKS, measured_generated_clearance
        from .execution_design import REVISION_V3
        measured_route_enabled = (getattr(self, '_execution_design_reference_authorized', False)
                and self.scene.spec.get('execution_design', {}).get('revision') == REVISION_V3
                and self.scene.spec['id'] in MEASURED_CLEARANCE_TASKS)
        measured_hand_enabled = (getattr(self, '_execution_design_reference_authorized', False)
                and self.scene.spec.get('execution_design', {}).get('revision') == REVISION_V3
                and self.scene.spec['id'] in HAND_SELECTION_TASKS)
        # Handle the goals in contract order.  A side is selected from the
        # achieved TCP pose so the same policy works for all three calibrated
        # embodiments and for both robot bases.
        # Generated scenes are pure placement contracts.  The identity
        # permutation A keeps the original right-to-left route; the B/C
        # permutations place the left target first so their target0 object is
        # not carried last through the loaded-wrist contact boundary.
        reverse_order = self.scene.spec.get('variant') == 'A'
        goals = sorted(self.scene.spec['goals'], key=lambda g: float(
            next(z for z in self.scene.spec['zones'] if z['id'] == g['target'])['xy'][0]),
            reverse=reverse_order)
        if self.scene.spec.get('expert_preserve_goal_order'):
            goals=list(self.scene.spec['goals'])
        if resume is not None:
            goals=[goal for goal in goals if goal['object']not in resume['completed_objects']]
        if measured_route_enabled and self.scene.spec['id'] in ('E04','E07','E16','E25'):
            from .execution_design_e07_reference import plan_transfers
            goals=plan_transfers(self,goals)  # local reference queue; source goals stay immutable
        cutlery_route = measured_route_enabled and self.scene.spec['id'] in ('E27','E34')
        if cutlery_route:
            from .execution_design_cutlery_transfer import plan_transfers as plan_cutlery_transfers
            goals=plan_cutlery_transfers(self,goals,prefer_single_hand=True)
        active_hand=initial_generated_hand or self.scene.spec.get('expert_arm','right' if self.scene.embodiment.name=='arx_x5' else 'left')
        for index, goal in enumerate(goals):
            if measured_route_enabled:
                # Re-read completed stacks and all other actual object poses
                # before each pickup, rather than trusting the initial layout.
                route = measured_generated_clearance(self)
                route['goal_index'] = index
                clear_z = approach_z = route['clearance_z_m']
                self.control_report['measured_generated_route'] = route
                with (self.out/'measured-generated-route.private.jsonl').open('a') as stream:
                    stream.write(json.dumps(route)+'\n')
            name = goal['object']
            spec = next(x for x in self.scene.spec['objects'] if x['id'] == name)
            if self.scene.spec['id']=='E25':
                from .execution_design_e25_reference import grasp_spec
                spec=grasp_spec(self,spec)  # private engineering choice; source spec stays immutable
                if '_e25_pickup_grasp_local'in goal:
                    from .execution_design_e25_parking import source_pickup_spec
                    spec=source_pickup_spec(self,spec,goal)
            elif self.scene.spec['id']=='E05':
                from .execution_design_e05_reference import grasp_spec
                spec=grasp_spec(self,spec)
            elif self.scene.spec['id']=='E11':
                from .execution_design_e11_reference import grasp_spec
                spec=grasp_spec(self,spec)
            elif self.scene.spec['id']=='E02':
                from .execution_design_e02_reference import grasp_spec
                spec=grasp_spec(self,spec)
            elif self.scene.spec['id']=='E21':
                from .execution_design_e21_reference import grasp_spec
                spec=grasp_spec(self,spec)
            elif (cutlery_route and self.scene.spec['id']=='E34'
                    and self.scene.spec.get('variant')=='C'
                    and self.scene.spec['execution_design'].get('condition')=='I'):
                from .execution_design_e34_balanced_grasp import grasp_spec
                spec=grasp_spec(self,spec)
            elif (cutlery_route and self.scene.spec['id']=='E34'
                    and self.scene.spec.get('variant')=='B'
                    and self.scene.spec['execution_design'].get('condition')=='I'):
                from .execution_design_e34b_balanced_grasp import grasp_spec
                spec=grasp_spec(self,spec)
            target = (goal['_e07_engineering_target'] if measured_route_enabled and self.scene.spec['id'] in ('E04','E07','E16','E25') and '_e07_engineering_target' in goal else next(x for x in self.scene.spec['zones'] if x['id'] == goal['target']))
            if measured_route_enabled and self.scene.spec['id'] in ('E04','E07','E16','E25'):
                from .execution_design_e07_reference import verify_relay_release
                verify_relay_release(self,goal)
            if cutlery_route:
                from .execution_design_cutlery_transfer import verify_relay_release as verify_cutlery_relay
                target=goal.get('_cutlery_target',target)
                verify_cutlery_relay(self,goal)
            # The calibrated left arm covers the complete generated tabletop
            # strip for all three supported embodiments.  Keeping one arm
            # active avoids handoff drift between outer-edge placements.
            side = 'right' if self.scene.embodiment.name == 'arx_x5' else 'left'
            side = self.scene.spec.get('expert_arm', side)
            side = goal.get('expert_arm',side)
            if side not in ('left','right'):
                raise ValueError('Invalid private expert arm selection')
            if measured_hand_enabled:
                from .execution_design_generated_route import choose_generated_hand, park_before_hand_switch
                if self.scene.spec['id'] in ('E04','E07','E16','E25') and '_e07_engineering_arm' in goal:
                    hand_route=dict(chosen=goal['_e07_engineering_arm'],object=name,
                        source=self.scene.spec['id']+'_local_reference_queue_measured_endpoint_IK',native_reachability_verified=False)
                elif cutlery_route:
                    hand_route=dict(chosen=goal['_cutlery_arm'],object=name,source='private_cutlery_table_handoff',native_reachability_verified=False)
                else:
                    hand_route = choose_generated_hand(self, name, goal, target, side)
                side = hand_route['chosen']
                with (self.out/'measured-generated-hands.private.jsonl').open('a') as stream:
                    stream.write(json.dumps(hand_route)+'\n')
                return_clear_z=clear_z
                if cutlery_route and active_hand!=side:
                    from .execution_design_cutlery_transfer import released_return_clearance
                    return_clear_z=released_return_clearance(self,active_hand,clear_z)
                park_before_hand_switch(self, active_hand, side, home_xy, return_clear_z)
            active_hand=self.activate_generated_hand(side,active_hand,home_xy,clear_z)
            other = 'right' if side == 'left' else 'left'
            side_index = 0 if side == 'left' else 1
            self.note(f'approach-{name}-{index}')
            # Leave the idle arm at its current pose.  A prior outer-edge
            # release can make its diagnostic TCP estimate temporarily drift;
            # moving it is unnecessary for the generated tabletop layout.
            state,_=self.c.snapshot()
            grasp_offset=state[name]['mat']@np.asarray(spec.get('grasp_point_local',[0,0,0]),float)
            grasp_position=self.pos(name)+grasp_offset
            xy = grasp_position[:2]
            center_z = float(grasp_position[2])
            if measured_route_enabled and self.scene.spec['id']=='E25':
                from .execution_design_e25_functional import prepare_next_pickup
                prepare_next_pickup(self,side,name)
            if self.scene.embodiment.config.get('author_recording',{}).get('acquire_align_above_source',False):
                staging=max(approach_z,float(self.tip(side)[2]))
                self.move_generated({side:[*self.tip(side)[:2],staging]})
                self.move_generated({side:[*xy,staging]})
            if 'grasp_axis_local' in spec and not (cutlery_route and self.scene.embodiment.name=='franka'):
                self.align_gripper_axis(side,state[name]['mat']@np.asarray(spec['grasp_axis_local'],float))
                if measured_route_enabled and self.scene.spec['id']=='E13':
                    from .execution_design_tabletop_grasp import level_empty_palm
                    self.move_generated({side:[*self.tip(side)[:2],max(approach_z,.96,float(self.tip(side)[2]))]})
                    level_empty_palm(self,side,state[name]['mat']@np.asarray(spec['grasp_axis_local'],float))
            if (getattr(self,'_execution_design_reference_authorized',False)
                    and self.scene.spec['id']=='E15'
                    and self.scene.spec.get('execution_design',{}).get('revision')==REVISION_V3):
                from .execution_design_e15_wrist import prepare_empty as prepare_e15_empty
                prepare_e15_empty(self,side,name,goal,clear_z)
            if measured_route_enabled and self.scene.spec['id']=='E25':
                from .execution_design_e25_reference import prepare_source_palm
                prepare_source_palm(self,side,name,goal)
            if measured_route_enabled and self.scene.spec['id']=='E25' and '_e25_receiver_rotation_task' in goal:
                from .execution_design_e25_reference import prepare_receiver
                prepare_receiver(self,side,name,goal,approach_z,xy)
            if self.scene.spec['id']=='E39' and self.scene.embodiment.config.get('author_recording',{}).get('e39_equivalent_wrist_yaw',False):
                from .author_e39_wrist import prepare_empty
                prepare_empty(self,side,name,goal)
            if (getattr(self, '_execution_design_reference_authorized', False)
                    and self.scene.spec.get('execution_design', {}).get('revision') == REVISION_V3
                    and self.scene.spec['id'] in ('E27','E34')):
                from .execution_design_cutlery_grasp import grasp_position as cutlery_grasp_position
                grasp_position=cutlery_grasp_position(self,side,spec)
                xy=grasp_position[:2];center_z=float(grasp_position[2])
                # The private cutlery reference just selected and reached a
                # safe high orientation site. Keep it until above the source.
                approach_z=max(approach_z,float(self.tip(side)[2]))
            if (getattr(self, '_execution_design_reference_authorized', False)
                    and self.scene.spec.get('execution_design', {}).get('revision') == REVISION_V3
                    and (self.scene.spec['id']=='E32' or self.scene.spec['id']=='E31' and name=='bowl')):
                from .execution_design_pickup_clearance import grasp_position as measured_grasp_position
                grasp_position=measured_grasp_position(self,side,spec)
                xy=grasp_position[:2];center_z=float(grasp_position[2])
            if (getattr(self, '_execution_design_reference_authorized', False)
                    and self.scene.spec.get('execution_design', {}).get('revision') == REVISION_V3
                    and self.scene.spec['id'] == 'E33'):
                from .execution_design_e33_grasp import grasp_position as e33_grasp_position
                grasp_position=e33_grasp_position(self,side,spec)
                xy=grasp_position[:2]
                center_z=float(grasp_position[2])
            e31_edge=(getattr(self,'_execution_design_reference_authorized',False)
                and self.scene.spec['id']=='E31'
                and self.scene.spec.get('execution_design',{}).get('revision')==REVISION_V3
                and name==self.scene.spec['semantic']['plate'])
            if e31_edge:
                from .execution_design_e31_edge import prepare_plate_edge
                grasp_position=prepare_plate_edge(self,name,side,approach_z)
                xy=grasp_position[:2];center_z=float(grasp_position[2])
            elif self.scene.spec.get('task_adapter','').startswith(('realworld','full50')):
                center_z=max(center_z,self.floor_clear_tcp(side))
            if measured_route_enabled and self.scene.spec['id']=='E21':
                from .execution_design_e21_reference import verify_pickup_ik
                verify_pickup_ik(self,side,[*xy,center_z])
            # X5's native wrist orientation reaches the tabletop at a much
            # tighter vertical margin than the UR5/Franka profile.  Keep the
            # pre-grasp waypoint close to the object on that embodiment;
            # lowering from the generic 45 mm staging height hits its IK
            # boundary and leaves the TCP several centimetres off target.
            if e31_edge:
                pass  # Already at the measured, table-clear horizontal rim entry.
            elif self.scene.embodiment.name == 'arx_x5':
                # X5 must clear the tabletop before translating over the next
                # object; its native TCP has a small vertical workspace margin.
                # Approach from the X5's stable high staging pose, then
                # descend to the compact grasp height. Its loaded wrist has
                # a much smaller lift envelope, handled by clear_z below.
                transit_z = 1.10
                current_xy = self.tip(side)[:2]
                self.move_generated({side: [current_xy[0], current_xy[1], transit_z]}, tolerance=.02)
                self.move_generated({side: [xy[0], xy[1], transit_z]}, tolerance=.02)
                self.move_generated({side: [xy[0], xy[1], .90]}, tolerance=.012)
                self.move_generated({side: [xy[0], xy[1], center_z]}, tolerance=.012)
            elif measured_route_enabled and self.scene.spec['id']=='E25':
                from .execution_design_segments_e19_e25 import approach_e25_piece
                approach_e25_piece(self,side,xy,center_z,approach_z,min(.0035,max(.0008,min(spec['size'])*.2)))
            else:
                # Route the open hand over the object before descending. A
                # diagonal approach from a previously placed pad can sweep a
                # source sideways even when the final TCP is accurate.
                empty_approach_z=approach_z
                if (getattr(self,'_execution_design_reference_authorized',False)
                        and self.scene.spec['id']=='E15' and self.scene.spec.get('variant')=='B'
                        and self.scene.spec.get('execution_design',{}).get('revision')==REVISION_V3):
                    from .execution_design_e15_wrist import prepared_empty_height
                    empty_approach_z=prepared_empty_height(self,side,name,goal,approach_z)
                self.move_generated({side: [*self.tip(side)[:2], empty_approach_z]})
                self.move_generated({side: [xy[0], xy[1], empty_approach_z]})
                self.move_generated({side: [xy[0], xy[1], center_z + .045]})
                self.prepare_generated_gripper(side)
                grasp_tolerance=min(.0035,max(.0008,min(spec['size'])*.2))
                if (cutlery_route and self.scene.spec['id']=='E34'
                        and self.scene.spec.get('variant')in('B','C')
                        and self.scene.spec['execution_design'].get('condition')=='I'):
                    from .execution_design_e34_acquire import narrow_material_approach
                    narrow_material_approach(self,side,spec,[*xy,center_z])
                    if self.scene.spec.get('variant')=='C':
                        self.stage='e34c-near-com-empty-pregrasp'
                elif cutlery_route and self.scene.spec['id']=='E34' and name=='spoon':
                    from .execution_design_e34_reference import approach as e34_approach
                    e34_approach(self,side,spec,[*xy,center_z])
                else:
                    self.move_generated({side: [xy[0], xy[1], center_z]},tolerance=grasp_tolerance)
            if (measured_route_enabled and self.scene.spec['id']=='E13'):
                from .execution_design_e13_edge import acquire_edge
                acquire_edge(self,side,name)
            if measured_route_enabled and self.scene.spec['id']=='E14':
                from .execution_design_e14_reference import align_single_layer
                align_single_layer(self,side,name)
            for _ in range(3):
                self.act('GRASP' if side == 'left' else 'STILL',
                         'GRASP' if side == 'right' else 'STILL')
            if measured_route_enabled and self.scene.spec['id']=='E14':
                from .execution_design_e14_reference import require_single_layer_grasp
                require_single_layer_grasp(self,side,name)
            state, _ = self.c.snapshot()
            if not state[name]['grasp'][side_index]:
                self.note(f'grasp-failed-{name}')
                raise RuntimeError(f'Generated object {name} was not physically grasped')
            self.note(f'grasped-{name}')
            self.carried_payload=(name,side)
            # Let the physical gripper settle while the box is still at the
            # source pose.  This helps the Franka/UR5 on the C permutation as
            # well as the lighter X5 box before the loaded lift.
            self.act('STILL', 'STILL', 20.)
            if (cutlery_route and self.scene.spec['id']=='E34'
                    and self.scene.spec.get('variant')in('B','C')
                    and self.scene.spec['execution_design'].get('condition')=='I'):
                if len(goals)!=1:raise ValueError('E34 selected-utensil tail requires one original goal')
                from .execution_design_e34_tail import finish_from_grasp
                finish_from_grasp(self,name,side)
                self.note('placed-'+name);self.note('final')
                score=self.c.evaluator.result()
                if not score['success']:raise RuntimeError('E34 full source reference failed native final conditions')
                return score
            if measured_route_enabled and self.scene.spec['id']=='E04':
                from .execution_design_e04_reference import lift_from_support
                lift_from_support(self,name,side)
            goal_xy = np.asarray(goal.get('placement_xy',target['xy']), dtype=float)
            if target.get('anchor_object'):
                current,_=self.c.snapshot();anchor=current[target['anchor_object']]
                goal_xy=(anchor['pos']+anchor['mat']@np.asarray(target.get('anchor_local_center',[0,0,0]),float))[:2]
            if measured_route_enabled and self.scene.spec['id']=='E11':
                from .execution_design_e11_reference import reachable_cell_xy
                goal_xy=reachable_cell_xy(self,name,target)
            if measured_route_enabled and self.scene.spec['id']=='E05':
                from .execution_design_e05_reference import placement_xy
                goal_xy=placement_xy(self,name,target)
            edge_case = max(abs(float(xy[0])), abs(float(goal_xy[0]))) > .10
            task_route = bool(self.scene.spec.get('task_adapter'))
            if task_route:
                # Task-specific cups and size blocks use the calibrated low
                # UR5 carry plane even when their target x exceeds 10 cm.
                # Sending a loaded WSG to the generic 1.10 m edge waypoint
                # crosses its wrist singularity. Transfer directly above the
                # target and explicitly lower before opening the fingers.
                if cutlery_route:
                    from .execution_design_cutlery_transfer import loaded_clearance
                    clear_z=loaded_clearance(self,name,side,clear_z)
                if (getattr(self, '_execution_design_reference_authorized', False)
                        and self.scene.spec.get('execution_design', {}).get('revision') == REVISION_V3
                        and self.scene.spec['id'] == 'E31'
                        and name == self.scene.spec['semantic']['plate']):
                    from .execution_design_e31_pickup import lift_plate
                    lift_plate(self,name,side,clear_z)
                    if (self.scene.spec.get('variant')=='C'and self.scene.spec.get('seed')==4201
                            and self.scene.spec['execution_design'].get('condition')=='I'):
                        from .execution_design_e31_c_finish import finish_after_lift
                        return finish_after_lift(self,name,side,goal)
                else:
                    self.move_generated({side: [*self.tip(side)[:2], clear_z]})
                if any(k in goal for k in ('roll','pitch','yaw')):
                    if cutlery_route:
                        from .execution_design_cutlery_transfer import orient_for_rule
                        orient_for_rule(self,name,side)
                    else:self.rotate_held(name,side,goal)
                if cutlery_route:
                    clear_z=loaded_clearance(self,name,side,clear_z)
                    self.move_generated({side:[*self.tip(side)[:2],clear_z]})
                if (self.scene.spec['id']=='E33' and
                        self.scene.embodiment.config.get('author_recording',{}).get('e33_upright_for_bin_insertion',False)):
                    from .realworld_tool_expert import _axis_rotation
                    current,_=self.c.snapshot();rotation=np.asarray(current[name]['mat'],float)
                    up=rotation@np.asarray(spec.get('up_axis',[0,0,1]),float);up/=np.linalg.norm(up)
                    vertical=np.array([0.,0.,1.]);turn_axis=np.cross(up,vertical)
                    angle=float(np.arccos(np.clip(up@vertical,-1.,1.)))
                    if angle>np.deg2rad(.25):
                        if np.linalg.norm(turn_axis)<1e-8:turn_axis=np.array([1.,0.,0.])
                        desired=_axis_rotation(turn_axis,angle)@rotation
                        def still_held():
                            values,_=self.c.snapshot()
                            if not values[name]['grasp'][side_index]:raise RuntimeError('Bottle grip lost during real upright rotation')
                        self.rotate_held_smooth(name,side,desired,guard=still_held)
                if (self.scene.spec['id']=='E33' and
                        self.scene.embodiment.config.get('author_recording',{}).get('e33_align_loaded_jaw_to_bin_width',False)):
                    from .realworld_tool_expert import _axis_rotation
                    robot=self.scene.robots[side]
                    ids=[robot.find_bodies(finger)[0][0] for finger in self.scene.embodiment.fingers]
                    jaw=(robot.data.body_pos_w[0,ids[0]]-robot.data.body_pos_w[0,ids[1]]).cpu().numpy()
                    jaw=self.scene.layout.task_rotation.T@jaw
                    angle=-float(np.arctan2(float(jaw[1]),float(jaw[0])))
                    angle=(angle+np.pi/2)%np.pi-np.pi/2
                    current,_=self.c.snapshot();desired=_axis_rotation([0,0,1],angle)@current[name]['mat']
                    def still_held():
                        values,_=self.c.snapshot()
                        if not values[name]['grasp'][side_index]:raise RuntimeError('Bottle grip lost during real bin-width alignment')
                    self.rotate_held_smooth(name,side,desired,guard=still_held)
                state,_=self.c.snapshot()
                actual_offset=self.tip(side)-state[name]['pos']
                height=float((np.abs(state[name]['mat'])@np.asarray(spec['size']))[2])
                tcp_xy=goal_xy+actual_offset[:2]
                if (getattr(self,'_execution_design_reference_authorized',False)
                        and self.scene.spec['id']=='E32'
                        and self.scene.spec.get('execution_design',{}).get('revision')==REVISION_V3):
                    from .execution_design_e32_transfer import transfer as e32_transfer
                    e32_transfer(self,name,side,tcp_xy,clear_z)
                elif measured_route_enabled and self.scene.spec['id']=='E21':
                    from .execution_design_e21_reference import transport_above_rim
                    transport_above_rim(self,side,name,target,clear_z)
                    # Re-measure the original tray-relative cell and held offset.
                    state,_=self.c.snapshot();anchor=state[target['anchor_object']]
                    goal_xy=(anchor['pos']+anchor['mat']@np.asarray(target['anchor_local_center'],float))[:2]
                    actual_offset=self.tip(side)-state[name]['pos']
                    height=float((np.abs(state[name]['mat'])@np.asarray(spec['size']))[2])
                    tcp_xy=goal_xy+actual_offset[:2]
                else:
                    if cutlery_route and goal.get('_cutlery_direct'):
                        from .execution_design_cutlery_transfer import screen_direct_translation
                        screen_direct_translation(self,name,side,[tcp_xy[0],tcp_xy[1],clear_z])
                    self.move_generated({side: [tcp_xy[0],tcp_xy[1],clear_z]})
                if (self.scene.spec['id']=='E33' and
                        self.scene.embodiment.config.get('author_recording',{}).get('e33_align_loaded_jaw_to_bin_width',False)):
                    state,_=self.c.snapshot();actual_offset=self.tip(side)-state[name]['pos']
                    tcp_xy=goal_xy+actual_offset[:2]
                    self.move_generated({side:[*tcp_xy,clear_z]})
                    state,_=self.c.snapshot();actual_offset=self.tip(side)-state[name]['pos']
                    height=float((np.abs(state[name]['mat'])@np.asarray(spec['size']))[2])
                goal_z=float(target.get('surface_z',.8))+height+float(actual_offset[2])+.004
                if measured_route_enabled and self.scene.spec['id']=='E11':
                    from .execution_design_e11_reference import release_height
                    goal_z=release_height(self,side,goal_z)
                if measured_route_enabled and self.scene.spec['id']=='E21':
                    from .execution_design_e21_reference import release_height
                    goal_z=release_height(self,side,name,target,goal_z)
                if self.scene.spec['id']=='E36':
                    container=self.scene.spec['semantic']['containers']['box']
                    body=state[container['object']]
                    lower=np.asarray(container['lower'],float);upper=np.asarray(container['upper'],float)
                    center=body['pos']+body['mat']@((lower+upper)/2)
                    extent=np.abs(body['mat'])@((upper-lower)/2)
                    rim=float(center[2]+extent[2])
                    # Drop the real ball from above the opening. Entering
                    # deeply and opening Panda's fingers under the rim can
                    # hook the entire box on the retracting hand.
                    goal_z=max(goal_z,rim+height+float(actual_offset[2])+.020,
                               self.floor_clear_tcp(side,floor=rim+.012))
                if (self.scene.spec['id']=='E33' and
                        self.scene.embodiment.config.get('author_recording',{}).get('e33_clear_bin_rim_on_release',False)):
                    container=self.scene.spec['semantic']['containers']['bin']
                    body=state[container['object']]
                    lower=np.asarray(container['lower'],float);upper=np.asarray(container['upper'],float)
                    center=body['pos']+body['mat']@((lower+upper)/2)
                    extent=np.abs(body['mat'])@((upper-lower)/2)
                    rim=float(center[2]+extent[2])
                    requested_z=goal_z
                    goal_z=max(goal_z,self.floor_clear_tcp(side,floor=rim+.012))
                    with (self.out/'container-release-goals.private.jsonl').open('a') as stream:
                        stream.write(json.dumps(dict(stage=self.stage,object=name,
                            actual_bin_rim_task_z=rim,original_tcp_z=requested_z,
                            finger_clear_release_tcp_z=goal_z,opening_margin_m=.012))+'\n')
                if (self.scene.spec['id']=='E38' and
                        self.scene.embodiment.config.get('author_recording',{}).get('e38_release_above_post_tip',False)):
                    semantic=self.scene.spec['semantic'];post=state[semantic['post']]
                    post_tip=post['pos']+post['mat']@np.asarray(semantic['post_tip'],float)
                    goal_z=max(goal_z,float(post_tip[2])+height+float(actual_offset[2])+.004,
                               self.floor_clear_tcp(side,floor=float(post_tip[2])+.008))
                    with (self.out/'ring-release-goals.private.jsonl').open('a') as stream:
                        stream.write(json.dumps(dict(object=name,actual_post_tip_task=post_tip.tolist(),
                            actual_root_to_tcp=actual_offset.tolist(),release_tcp_z=goal_z))+'\n')
                if cutlery_route and self.scene.spec['id']=='E34':
                    from .execution_design_e34_reference import placement as e34_placement, level_handle as e34_level_handle
                    e34_level_handle(self,name,side)
                    handle_tcp=e34_placement(self,name,side,target)
                    tcp_xy=handle_tcp[:2];goal_z=float(handle_tcp[2])
                    clear_z=max(clear_z,float(self.tip(side)[2]))
                    self.move_generated({side:[*tcp_xy,clear_z]})
                if (self.scene.spec['id']=='E33' and
                        self.scene.embodiment.config.get('author_recording',{}).get('e33_release_when_inside_near_floor',False)):
                    container=self.scene.spec['semantic']['containers']['bin']
                    points=np.asarray(spec['source_containment_hull']['vertices_local'],float)
                    lower=np.asarray(container['lower'],float);upper=np.asarray(container['upper'],float)
                    def actual_release_ready():
                        values,_=self.c.snapshot();bottle=values[name];bin_body=values[container['object']]
                        world=points@bottle['mat'].T+bottle['pos']
                        local=(world-bin_body['pos'])@bin_body['mat']
                        minimum=local.min(axis=0);maximum=local.max(axis=0)
                        return bool(np.all(minimum>=lower-.003) and np.all(maximum<=upper+.003)
                                    and minimum[2]-lower[2]<=.025)
                    def actually_carried():
                        values,_=self.c.snapshot()
                        if not values[name]['grasp'][side_index]:raise RuntimeError('Bottle grip lost during actual near-floor lowering')
                    self.move_smooth({side:[*tcp_xy,goal_z]},tolerance=.002,
                        guard=actually_carried,done=actual_release_ready)
                    with (self.out/'E33-actual-release-stop.private.jsonl').open('a') as stream:
                        stream.write(json.dumps(dict(object=name,actual_tcp=self.tip(side).tolist(),
                            actual_shape_inside_and_near_floor=actual_release_ready(),
                            original_cavity_bounds_and_3mm_tolerance_preserved=True))+'\n')
                elif (getattr(self,'_execution_design_reference_authorized',False)
                        and self.scene.spec['id']=='E31'
                        and self.scene.spec.get('execution_design',{}).get('revision')==REVISION_V3
                        and name==self.scene.spec['semantic']['plate']):
                    from .execution_design_e31_release import lower_for_release
                    lower_for_release(self,name,side,goal)
                elif (getattr(self,'_execution_design_reference_authorized',False)
                        and self.scene.spec['id']=='E38'
                        and self.scene.spec.get('execution_design',{}).get('revision')==REVISION_V3):
                    from .execution_design_ring_reference import align_above_post
                    align_above_post(self,name,side)
                else:
                    if cutlery_route and goal.get('_cutlery_direct'):
                        from .execution_design_cutlery_transfer import screen_direct_translation
                        screen_direct_translation(self,name,side,[tcp_xy[0],tcp_xy[1],goal_z])
                    if (getattr(self,'_execution_design_reference_authorized',False)
                            and self.scene.spec.get('execution_design',{}).get('revision')==REVISION_V3
                            and self.scene.spec['id']=='E25'and self.scene.spec['variant']=='C'
                            and name=='knife'and side=='left'and '_e07_after_relay'in goal):
                        from .execution_design_e25_c_release import release_height_for_knife
                        goal_z=release_height_for_knife(self,goal,target,goal_z)
                    if (measured_route_enabled and self.scene.spec['id']=='E25'
                            and self.scene.spec['variant']=='A'and name=='spoon'
                            and side=='left'and '_e07_after_relay'in goal):
                        from .execution_design_e25_a_spoon_release import lower_until_original_goal
                        lower_until_original_goal(self,goal,[tcp_xy[0],tcp_xy[1],goal_z])
                    else:self.move_generated({side: [tcp_xy[0],tcp_xy[1],goal_z]})
            elif edge_case:
                # At the outer x edge, lowering while carrying makes the
                # Cartesian controller drift.  Route in high clearance through
                # the center line before reaching the pad, then let real PhysX
                # support settle the released piece onto it.
                # Use the high transit pose for every embodiment at the outer
                # x edge.  The lower UR5/Franka clearance pose is inside a
                # narrow wrist workspace band for some randomized y layouts;
                # routing high keeps the carried object away from the table
                # while the arm crosses to the destination column.
                edge_z = 1.10
                self.move_generated({side: [xy[0], xy[1], edge_z]}, tolerance=.025)
                if abs(float(goal_xy[0])) > .10:
                    self.move_generated({side: [0.0, xy[1], edge_z]}, tolerance=.025)
                    self.move_generated({side: [goal_xy[0], xy[1], edge_z]}, tolerance=.025)
                self.move_generated({side: [goal_xy[0], goal_xy[1], edge_z]}, tolerance=.025)
                if self.scene.embodiment.name == 'arx_x5':
                    goal_z = .8 + float(spec['size'][2]) + .004
                    self.move_generated({side: [goal_xy[0], goal_xy[1], goal_z]}, tolerance=.025)
            else:
                # Separate vertical clearance from the long horizontal return.
                # At the edge of the workspace, solving all axes together can ask
                # the IK controller to translate while the gripper is low.
                self.move_generated({side: [*self.tip(side)[:2], clear_z]})
                self.move_generated({side: [home_xy[side][0], home_xy[side][1], clear_z]})
                self.move_generated({side: [goal_xy[0], goal_xy[1], clear_z]})
                # The box is released a few millimetres above the pad, then
                # settles under PhysX before the evaluator hold interval.
                goal_z = .8 + float(spec['size'][2]) + .004
                self.move_generated({side: [goal_xy[0], goal_xy[1], goal_z]})
            if measured_route_enabled and self.scene.spec['id']=='E21':
                from .execution_design_e21_reference import verify_before_release
                verify_before_release(self,side,name,target)
            if (getattr(self,'_execution_design_reference_authorized',False)
                    and self.scene.spec['id']=='E35'
                    and self.scene.spec.get('execution_design',{}).get('revision')==REVISION_V3):
                from .execution_design_e35_retreat import align_actual_stack_release
                align_actual_stack_release(self,name,side,goal,target)
            self.carried_payload=None
            had_relay_marker = hasattr(self, '_engineering_release_is_relay')
            previous_relay_marker = getattr(self, '_engineering_release_is_relay', False)
            self._engineering_release_is_relay = bool(measured_route_enabled and '_e07_engineering_target' in goal)
            try:
                self.release_generated(side)
            finally:
                if had_relay_marker:self._engineering_release_is_relay = previous_relay_marker
                else:del self._engineering_release_is_relay
            self.stage='released-'+name
            recording=self.scene.embodiment.config.get('author_recording',{})
            if (self.smooth and (recording.get('reset_empty_wrist_after_release',False) or
                    (index==len(goals)-1 and recording.get('reset_empty_wrist_before_retreat',False)))):
                tip=self.tip(side)
                self.move_smooth({side:[*tip[:2],tip[2]+.04]})
                self.neutralize_empty_wrist(side)
            # The edge branch is already at its clearance height; moving the
            # empty gripper again can trip a strict waypoint check while the
            # released object is settling.  Keep the camera and physics ticks.
            if task_route or not edge_case:
                self.move_generated({side: [*self.tip(side)[:2], clear_z]})
            elif self.scene.embodiment.name == 'arx_x5':
                self.move_generated({side: [goal_xy[0], goal_xy[1], 1.10]}, tolerance=.025)
            for _ in range(4):
                self.act()
            # Edge placements finish above the destination pad.  If the next
            # source is also at the outer x edge, route through the center of
            # the safe high workspace; a direct edge-to-edge transfer can
            # enter the UR5 middle singularity.
            if edge_case and not task_route and index < len(self.scene.spec['goals']) - 1:
                next_goal = goals[index + 1]
                next_spec = next(x for x in self.scene.spec['objects']
                                 if x['id'] == next_goal['object'])
                next_xy = np.asarray(next_spec['xy'], dtype=float)
                if abs(float(next_xy[0])) > .10:
                    self.move_generated({side: [0.0, goal_xy[1], clear_z]}, tolerance=.02)
                    self.move_generated({side: [0.0, next_xy[1], clear_z]}, tolerance=.02)
            self.note(f'placed-{name}')
        if self.scene.spec.get('task_adapter'):
            # A successful state hidden behind the wrist is not a useful
            # demonstration. Withdraw the empty hand toward its own base
            # before the final hold and author-review image.
            self.stage='retreat'
            if (getattr(self,'_execution_design_reference_authorized',False)
                    and self.scene.spec['id']=='E35'
                    and self.scene.spec.get('execution_design',{}).get('revision')==REVISION_V3):
                from .execution_design_e35_retreat import lift_above_stack
                clear_z=lift_above_stack(self,side,clear_z)
            self.move_generated({side:[*self.tip(side)[:2],clear_z]})
            if cutlery_route and self.scene.spec['id']=='E34':
                from .execution_design_e34_reference import retreat as e34_retreat
                e34_retreat(self,side)
            else:
                retreat_y=home_xy[side][1]+(.12 if side=='left' else -.12)
                self.move_generated({side:[home_xy[side][0],retreat_y,clear_z]})
        for _ in range(5):
            self.act()
        self.note('final')
        if resume is not None:
            return dict(remaining_generated_goals_executed=[goal['object']for goal in goals],engineering_only=True)
        score = self.c.evaluator.result()
        if not score['success']:
            from .execution_design_pose_negative import allow_original_terminal_failure
            if not allow_original_terminal_failure(self):
                raise RuntimeError('Generated demo final state did not pass the actual server evaluator')
        return score

    def close(self):
        self.c.tick_hooks.remove(self.record)
        self.control_report.update(frames=self.frames,physics_ticks_recorded=self.physics_ticks_recorded,
            feedforward_hands_active_at_close=sorted(getattr(self.c,'_author_ff_twists',{})),
            camera_frame_counts=self.camera_frame_counts)
        (self.out/'recording-control.private.json').write_text(json.dumps(self.control_report,indent=2)+'\n')
        encoders=(self.encoder,self.review_encoder,*self.wrist_encoders.values())
        for encoder in encoders:encoder.stdin.close()
        codes=[encoder.wait(timeout=60) for encoder in encoders]
        if any(codes):raise RuntimeError('Demo encoder failed')
        if any(count!=self.frames for count in self.camera_frame_counts.values()):
            raise RuntimeError('Native camera stream frame counts differ')
        (self.out/'camera-streams.private.json').write_text(json.dumps(dict(
            streams={name:dict(info,frames=self.camera_frame_counts[name],fps=self.fps,
                sha256=hashlib.sha256((self.out/info['file']).read_bytes()).hexdigest())
                for name,info in self.camera_streams.items()},
            physics_dt=self.c.dt,physics_ticks_recorded=self.physics_ticks_recorded,
            frame_physics_ticks=self.frame_physics_ticks,
            synchronized=True),indent=2)+'\n')


def record_f22(controller,out):
    author=Demonstration(controller,out);score=None
    try:score=author.solve()
    except Exception:
        author.note('diagnostic-error')
        raise
    finally:author.close()
    video=Path(out)/'video.mp4'
    result=dict(task='F22',variant=controller.scene.spec['variant'],seed=0,backend='isaaclab_physx',
        protocol=PROTOCOL,embodiment=controller.scene.embodiment.name,layout_profile=controller.scene.spec['layout_profile'],camera_profile=controller.scene.spec['camera_profile'],embodiment_config_sha256=controller.scene.spec['embodiment_config_sha256'],success=bool(score['success']),score=score,steps=controller.steps,
        frames=author.frames,fps=author.fps,camera='head',video_sha256=hashlib.sha256(video.read_bytes()).hexdigest(),
        real_physics=True,object_teleport=False,grasp_constraints=False,expert_private=True)
    (Path(out)/'demo.private.json').write_text(json.dumps(result,indent=2)+'\n')
    print('VIDEOICL_DEMO_VALIDATED '+json.dumps(result),flush=True)


def record_generated_demo(controller, out):
    """Record one generated A/B/C scene and always leave a review manifest."""
    if controller.scene.spec.get('execution_design'):
        raise ValueError('Full execution workflow cannot be exported as a local-rule model demo; use engineering reference entry')
    # Use the canonical workbench filename for the actor view.  The separate
    # multiview stream remains a maintainer diagnostic beside it.
    author = Demonstration(controller, out, video_prefix='demo')
    score = None
    error = None
    try:
        score = author.solve_generated()
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        try:
            author.note('diagnostic-error')
        except Exception:
            pass
    finally:
        author.close()
    video = Path(out) / 'demo.mp4'
    result = dict(task=controller.scene.spec['id'], variant=controller.scene.spec['variant'],
        seed=controller.scene.spec['seed'], backend='isaaclab_physx', protocol=PROTOCOL,
        embodiment=controller.scene.embodiment.name,
        layout_profile=controller.scene.spec['layout_profile'],
        camera_profile=controller.scene.spec['camera_profile'],
        embodiment_config_sha256=controller.scene.spec['embodiment_config_sha256'],
        success=bool(score and score.get('success')), score=score,
        steps=controller.steps, frames=author.frames, fps=author.fps, camera='head',
        joint_velocity_feedforward=author.joint_velocity_feedforward,
        video_sha256=hashlib.sha256(video.read_bytes()).hexdigest() if video.exists() else None,
        multiview_video_sha256=hashlib.sha256((Path(out) / 'demo-multiview.mp4').read_bytes()).hexdigest()
            if (Path(out) / 'demo-multiview.mp4').exists() else None,
        real_physics=True, object_teleport=False, grasp_constraints=False,
        expert_private=True, instruction=controller.scene.spec.get('instruction'),
        scene_status=controller.scene.spec.get('status','anchor'),
        task_revision=controller.scene.spec.get('task_revision',1),
        task_adapter=controller.scene.spec.get('task_adapter'),
        demo_protocol='robodojo-compatible-physx-rgb24-v1')
    if error:
        result['error'] = error
    (Path(out) / 'demo.private.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print('VIDEOICL_DEMO_VALIDATED ' + json.dumps(result, ensure_ascii=False), flush=True)
    return result
