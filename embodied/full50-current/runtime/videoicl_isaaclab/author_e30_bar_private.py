"""E30 absolute native hand frame and source-finger material grasp offset."""
from __future__ import annotations
import json
import numpy as np
from .realworld_mechanism_expert import _Author,MechanismExecutionError,_unit
from .author_mplib_planner import _rotation,_quat,plan


class SourceBarAuthor(_Author):
    def solve(self):
        config=self.a.scene.embodiment.config.get('author_recording',{})
        if self.variant!='C'or config.get('e30_lower_first_when_both')is not True:return super().solve()
        for role in('lower','upper'):self.drawer(role)
        for _ in range(3):self.act()
        self.stage('mechanism-actions-complete')
        return dict(task=self.task,variant=self.variant,operations=self.operations,execution='continuous_robot_targets_completed',physics_success_evaluated=False,author_order=['lower','upper'],source_joint_goals_unchanged=True)
    def hand_rotation(self,side):
        robot=self.a.scene.robots[side]
        return self.a.scene.layout.task_rotation.T@_rotation(robot.data.root_quat_w[0].cpu().tolist())@_rotation(self.c.pose(side)[1][0].cpu().tolist())
    def force_vectors(self,role,side):
        actor=self.roles[role]['contact_body'];sensor,labels=self.a.scene.contacts[actor];matrix=sensor.data.force_matrix_w
        if matrix is None:raise MechanismExecutionError('Actual mechanism force vectors unavailable')
        forces=matrix[0].sum(dim=0).cpu().numpy();R=self.a.scene.layout.task_rotation.T
        return [R@forces[labels.index(side+'_finger'+str(i))]for i in(1,2)]
    def touching(self,role,side,both=False):
        if not super().touching(role,side,both):return False
        if not both:return True
        _,r=self.frame(self.points[role],self.mechanisms());jaw=_unit(r@np.array([0,1,0.]));forces=self.force_vectors(role,side)
        return float(forces[0]@jaw)<-.001 and float(forces[1]@jaw)>.001
    def orient(self,role,side,inverse=False):
        # Acquisition below chooses an absolute measured frame. Retraction
        # must not apply the old relative Euler inverse a second time.
        return None
    def actual_pad_geometry(self,role,side):
        self.a.floor_clear_tcp(side);robot=self.a.scene.robots[side];body_p,body_R=self.frame(self.points[role],self.mechanisms());minimum=[]
        for bid,vertices in self.a._finger_collision_points[side]:
            R=self.a.scene.layout.task_rotation.T@_rotation(robot.data.body_quat_w[0,bid].cpu().tolist());p=self.a.scene.world_to_task(robot.data.body_pos_w[0,bid].cpu().numpy());world=np.asarray(vertices)@R.T+p;local=(world-body_p)@body_R
            minimum.append(dict(link=str(robot.body_names[bid]),minimum_source_front_coordinate=float(local[:,2].min()),source_front_board_plane=.06711854785680771,actual_finger_board_gap_m=float(local[:,2].min()-.06711854785680771)))
        R=self.hand_rotation(side);origin=self.tip(side)-R@np.array([0,0,.1034]);material=R.T@(self.point(role)-origin)
        return dict(native_fingers=minimum,source_bar_center_in_actual_hand=material.tolist(),source_flat_inner_pad_z_interval=[.09456482157111168,.10856620222330093])
    def acquire(self,role):
        side=self.hand(role);self.stage('mechanism-source-bar-free-pose-'+role);self.act(side,'RELEASE')
        source=self.point(role);_,body_R=self.frame(self.points[role],self.mechanisms());outward=self.axis(role);approach=-outward;jaw=_unit(body_R@np.array([0,1,0.]));x=_unit(np.cross(jaw,approach));jaw=_unit(np.cross(approach,x));target_R=np.column_stack((x,jaw,approach))
        if abs(float(jaw@np.array([0,0,1.]))-1.)>.01:raise MechanismExecutionError('Source bar vertical crosssection differs from reviewed frame')
        tcp_offset=.0029;target=source+outward*tcp_offset;stand=source+outward*.14
        config=self.a.scene.embodiment.config.get('author_recording',{})
        if role=='lower'and config.get('e30_lower_high_stand')is True:stand[2]=max(float(source[2])+.10,.98)
        snapshot_guard=lambda:all(self.no_touch(r)for r in self.roles)
        def released_guard():
            if not snapshot_guard():raise MechanismExecutionError('Unexpected cabinet contact during empty full-pose transit')
        if role=='lower'and config.get('e30_lower_high_stand')is True:
            from .author_mplib_planner import capture_scene,plan_snapshot
            import os
            from pathlib import Path
            snapshot=capture_scene(self.a.scene,self.c,side,dict(position=stand.tolist(),quaternion=_quat(target_R).tolist()))
            (self.a.out/f'E30-{role}-absolute-preapproach-snapshot.private.json').write_text(json.dumps(snapshot,indent=2)+'\n')
            profile=json.loads(Path(os.path.expandvars(snapshot['profile'])).read_text());result=plan_snapshot(snapshot,profile)
        else:result=plan(self.a.scene,self.c,side,stand.tolist(),task_tcp_quaternion=_quat(target_R).tolist())
        (self.a.out/f'E30-{role}-absolute-preapproach-plan.private.json').write_text(json.dumps(result,indent=2)+'\n')
        if result.get('verified')is not True:raise MechanismExecutionError('No fullworld verified free hand pose for source bar: '+str(result.get('diagnostics',{}).get('error',result.get('status'))))
        self.a.execute_joint_path(side,result,guard=released_guard)
        measured_R=self.hand_rotation(side);angle=float(np.rad2deg(np.arccos(np.clip((np.trace(measured_R@target_R.T)-1)/2,-1,1))))
        if angle>1.:raise MechanismExecutionError('Actual absolute bar hand orientation missed1degree')
        self.stage('mechanism-source-bar-front-approach-'+role)
        if role=='lower'and config.get('e30_lower_high_stand')is True:
            front=source+outward*.045;above=front.copy();above[2]=stand[2]
            self.move(side,above,tolerance=.001)
            # Narrow only the truly empty jaw before entering the lower lane;
            # the opened upper drawer is a real overhead obstacle in C.
            self.a.prepare_generated_gripper(side)
        self.move(side,source+outward*.045,tolerance=.001)
        self.move(side,target,tolerance=.001)
        for attempt in range(4):
            self.act(side,'GRASP');geometry=self.actual_pad_geometry(role,side);forces=self.force_vectors(role,side);actual_R=self.hand_rotation(side)
            row=dict(role=role,attempt=attempt,source_bar_center_task=self.point(role).tolist(),source_bar_point_local=self.points[role]['local'],target_tcp_task=target.tolist(),target_hand_rotation_task=target_R.tolist(),actual_hand_rotation_task=actual_R.tolist(),actual_tcp_task=self.tip(side).tolist(),tcp_offset_outward_m=tcp_offset,actual_force_on_source_task=[v.tolist()for v in forces],true_opposed_pad_pressure=self.touching(role,side,both=True),actual_joint_displacement_m=self.displacement(role),actual_native_pad_geometry=geometry,source_asset_or_joint_or_score_changed=False)
            with(self.a.out/'E30-source-bar-grasp.private.jsonl').open('a')as stream:stream.write(json.dumps(row)+'\n')
            if self.touching(role,side,both=True):
                if min(p['actual_finger_board_gap_m']for p in geometry['native_fingers'])<-.0004:raise MechanismExecutionError('Native finger penetrates source front panel instead of graspingbar')
                if not .0948<=geometry['source_bar_center_in_actual_hand'][2]<=.1083:raise MechanismExecutionError('Actual source bar outside real innerpad depth')
                return side
        raise MechanismExecutionError('Source bar has no real opposed vertical twofinger grasp')


def solve_e30_source_bar(author):
    if author.scene.spec['id']!='E30':raise ValueError('Independent source bar policy onlyE30')
    return SourceBarAuthor(author).solve()
