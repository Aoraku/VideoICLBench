"""Bounded, private physical reference control for versioned execution designs.

Uses public Cartesian/rotation/gripper actions via Demonstration.act, whose
native receipts are saved in demo-actions.private.jsonl. Does not modify object,
joint, or robot state. A finished route is not a scoring/physics certificate.
Reviewed grasp geometry is required; missing handles fail before any action.
"""
import math
from copy import deepcopy
import numpy as np
from .realworld_structural_expert import StructuralAuthor
from .realworld_tool_expert import ToolExecutionError, _axis_rotation


class ExecutionDesignAuthor(StructuralAuthor):
    def __init__(self, author):
        self.a=author;self.c=author.c;self.spec=author.scene.spec;self.s=self.spec['semantic']
        self.task,self.variant=self.spec['id'],self.spec['variant'];self.d=self.spec['execution_design']
        from .execution_design import SUPPORTED_REVISIONS
        if self.d.get('revision') not in SUPPORTED_REVISIONS:raise ValueError('Unsupported workflow revision')
        if self.task not in ('E01','E09','E17','E20','E39'):raise ValueError('Unknown workflow')
        self.index='ABC'.index(self.variant);self.start=self.c.steps;self.limit=self.spec.get('expert_action_budget',1500)
        config=author.scene.embodiment.config['control']
        self.min_mm=float(config['step_mm'][0]);self.max_mm=min(10.,float(config['step_mm'][1]));self.min_deg=float(config['rotation_deg'][0]);self.max_deg=min(10.,float(config['rotation_deg'][1]))
        if self.task=='E09'and author.control_report.get('engineering_reference_only'):
            self.max_mm=min(25.,float(config['step_mm'][1]))
        self.clearance=float(self.s.get('expert_clearance_z',1.15));self.operations=[]
        self.geometry=self.s.get('structural_expert',{});self.objects={o['id']:o for o in self.spec['objects']}
        self.identity={o.get('semantic_identity',o.get('identity',o['id'])):o['id'] for o in self.spec['objects']}
        self.grasps={**self.s.get('structural_grasps',{}),**self.d.get('grasps',{})}
        if self.task=='E17' and getattr(author,'control_report',{}).get('engineering_reference_only'):
            from .execution_design_e17_reference import measured_triangle_grasps
            self.grasps=measured_triangle_grasps(self.spec,self.grasps)
        if self.task=='E39':self._e39_home={side:self.tip(side).copy() for side in ('left','right')}
        required=set(self.d['target_members'])|{self.d['delivery_actor']}
        for p in self.d['packages']:
            required.update(p['members'])
            if p.get('lid'):required.add(p['lid'])
        for r in self.d['cleanup_regions']:
            if r['actor']:required.update(r['members'])
        missing=sorted(required-set(self.grasps))
        if missing:raise ToolExecutionError('Missing reviewed physical grasp/handle geometry: '+','.join(missing))
        if self.spec.get('author_smooth_recording',False):
            raise ToolExecutionError('Reference workflow requires individually recorded public action receipts')

    def move(self,side,target,guard=None,follower=None,tolerance=.002):
        if (self.task=='E09'and self.a.control_report.get('engineering_reference_only')
                and float(np.asarray(target)[2])>=.95
                and not any(v['grasp'][0 if side=='left'else 1]for v in self.snapshot()[0].values())):
            tolerance=max(tolerance,.008)
        if self.task=='E20'and self.a.control_report.get('engineering_reference_only'):
            goal=np.asarray(target,float);progress=[float(np.linalg.norm(goal-self.tip(side)))];original=self.act
            def checked_act(*args,**kwargs):
                result=original(*args,**kwargs);progress.append(float(np.linalg.norm(goal-self.tip(side))))
                if (np.max(abs(goal-self.tip(side)))>tolerance and len(progress)>=4
                        and progress[-4]-min(progress[-3:])<.0002):
                    raise ToolExecutionError('E20 Cartesian motion stalled after three actions: '+self.a.stage)
                return result
            self.act=checked_act
            try:return super().move(side,target,guard,follower,tolerance)
            finally:self.act=original
        if self.task=='E01':
            from .execution_design_e01_balance import _coarse
            if _coarse(self):
                from .execution_design_e01_functional import move_tool
                return move_tool(self,side,target,guard,follower,tolerance)
        if (self.task=='E09'and self.a.control_report.get('engineering_reference_only')
                and any(v['grasp'][0 if side=='left'else 1]for v in self.snapshot()[0].values())):
            package_step=getattr(self,'_e09_package_step_mm',2.)
            piece_step=getattr(self,'_e09_piece_transport_mm',None)
            if piece_step in(8.,25.):
                package_step=5. if float(np.asarray(target)[2])<float(self.tip(side)[2])-.001 else piece_step
            previous=self.max_mm;self.max_mm=min(previous,package_step if package_step in(2.,5.,8.,25.)else 2.)
            try:return super().move(side,target,guard,follower,tolerance)
            finally:self.max_mm=previous
        if (self.task=='E39' and follower is None
                and self.a.control_report.get('engineering_reference_only')
                and not any(v['grasp'][0 if side=='left' else 1]for v in self.snapshot()[0].values())):
            from .execution_design_e39_reference import move_empty_waypoint
            return move_empty_waypoint(self,side,target,guard,tolerance)
        return super().move(side,target,guard,follower,tolerance)

    def acquire(self,ref,side):
        if (self.task=='E09'and self.a.control_report.get('engineering_reference_only')
                and ref.get('actor')in set(self.d['target_members'])|set(self.d.get('batch_members',{}).get('distractor',[]))):
            from .execution_design_e09_piece import acquire
            return acquire(self,ref,side)
        if (self.task=='E39' and ref.get('actor')=='work_tray'
                and self.a.control_report.get('engineering_reference_only')):
            from .execution_design_e39_reference import acquire_work_tray_down
            return acquire_work_tray_down(self,ref,side)
        return super().acquire(ref,side)

    def move_point(self,side,ref,target,guard=None,follower=None,tolerance=.002):
        if self.task=='E01':
            from .execution_design_e01_balance import _coarse
            if _coarse(self):
                from .execution_design_e01_functional import move_material
                return move_material(self,side,ref,target,guard,follower,tolerance)
        return super().move_point(side,ref,target,guard,follower,tolerance)

    def pickup(self,name,*,side_override=None):
        if self.task=='E39':self.park_e39_idle_hand(self.hand_for(name))
        if (self.task=='E39' and name=='work_tray'
                and self.a.control_report.get('engineering_reference_only')):
            ref=self.ref(name);side=side_override or self.hand_for(name)
            self.acquire(ref,side)
            self.stage('workflow-measured-initial-tray-lift')
            initial=self.snapshot()[0]
            anchors={n:(np.asarray(initial[n]['pos']).copy(),np.asarray(initial[n]['mat']).copy())
                     for n in self.d['reference_objects']}
            def held_payload():
                self.require_held(ref,side)
                state,contacts=self.snapshot()
                if float(state[name]['mat'][2,2])<.995:
                    raise ToolExecutionError('E39 initial lift tilted its real tray')
                if any(frozenset((n,name))not in contacts for n in self.d['target_members']):
                    raise ToolExecutionError('E39 initial lift lost an actual carried T support')
                for n,(p,r)in anchors.items():
                    if np.linalg.norm(np.asarray(state[n]['pos'])-p)>.002 or np.linalg.norm(np.asarray(state[n]['mat'])-r)>.02:
                        raise ToolExecutionError('E39 initial lift disturbed the protected reference')
                    if any(frozenset((moving,n))in contacts for moving in [name,*self.d['target_members']]):
                        raise ToolExecutionError('E39 initial lift has obstructing reference contact')
            self.move_point(side,ref,self.point(ref)+[0,0,.07],held_payload)
            return ref,side
        if self.task in ('E17','E20') and name in self.d['target_members']:
            ref=self.ref(name);side=side_override or self.hand_for(name)
            previous=self.clearance
            if self.task=='E20' and side_override:
                from .execution_design_e20_reference import measured_empty_approach_height
                self.clearance=measured_empty_approach_height(self,side)
            try:self.acquire_chip_with_wrist_margin(ref,side)
            finally:self.clearance=previous
            self.move(side,self.tip(side)+[0,0,.07],lambda:self.require_held(ref,side))
            return ref,side
        if (self.task=='E09' and name in set(self.d['target_members'])|set(self.d.get('batch_members',{}).get('distractor',[]))
                and self.a.control_report.get('engineering_reference_only')):
            from .execution_design_e09_piece import relay_if_required
            relay_if_required(self,name)
            from .execution_design_e09_liftoff import lift_piece
            from .execution_design_e09_hand import piece_hand
            from .execution_design_e09_reference import measured_approach_height,park_empty_other
            ref=self.ref(name);side=side_override or piece_hand(self,name)
            park_empty_other(self,side)
            previous=self.clearance;self.clearance=measured_approach_height(self,side)
            try:self.acquire(ref,side)
            finally:self.clearance=previous
            lift_piece(self,ref,side)
            return ref,side
        if self.task=='E01' and name=='meal_box':
            # Both staging and delivery perform their own measured payload
            # lift. The legacy fixed 70mm TCP lift can fail at an unreachable
            # wrist waypoint even after the real package has cleared the rack.
            ref=self.ref(name);side=self.hand_for(name);self.acquire(ref,side)
            return ref,side
        return super().pickup(name)

    def acquire_chip_with_wrist_margin(self,ref,side):
        """E17/E20 flat pieces: select an equivalent empty-hand pinch direction.

        E17 near-stage reached the real q7 upper limit while approaching its
        first plate. The same measured empty-hand alternative that allowed
        E20's first two real placements also avoids spending that wrist margin.
        """
        from .author_clearance import prepare_single_hand
        self.stage('acquire-'+ref['actor']);prepare_single_hand(self.a,side,self.clearance)
        self.act(side,'RELEASE')
        if any(v['grasp'][0 if side=='left' else 1] for v in self.snapshot()[0].values()):
            raise ToolExecutionError('Empty-hand chip alignment requires actual release')
        _,rotation=self.frame(ref)
        desired=rotation@np.asarray(ref['jaw_axis_local'],float)
        self.align_empty_chip_axis(side,desired)
        point=self.point(ref);height=max(self.clearance,float(point[2])+.07,float(self.tip(side)[2]))
        self.move(side,[*self.tip(side)[:2],height]);self.move(side,[*point[:2],height])
        if self.a.scene.embodiment.config.get('author_recording',{}).get('pre_grasp_opening_m') is not None:
            raise ToolExecutionError('Chip reference requires public full-opening actions')
        self.move(side,point)
        from .execution_design_e20_reference import finish_chip_grip
        finish_chip_grip(self,ref,side)

    def align_empty_chip_axis(self,side,desired):
        robot=self.a.scene.robots[side];ids=robot.find_joints('panda_joint7')[0]
        if len(ids)!=1:raise ToolExecutionError('Measured Panda wrist identity required')
        index=ids[0]
        def wrist():
            return float(robot.data.joint_pos[0,index]),np.asarray(robot.data.joint_pos_limits[0,index].cpu(),float)
        def axis():
            f=self.a.finger_geometry(side)['fingers']
            v=np.asarray(f[0]['body_origin_task_m'])-np.asarray(f[1]['body_origin_task_m'])
            if not np.isfinite(v).all() or np.linalg.norm(v)<.001:raise ToolExecutionError('Missing measured finger axis')
            return v/np.linalg.norm(v)
        desired=np.asarray(desired,float);desired/=np.linalg.norm(desired);current=axis()
        if max(abs(float(desired[2])),abs(float(current[2])))>.1:
            raise ToolExecutionError('Chip equivalent-yaw route requires horizontal actual finger axis')
        q,limits=wrist();mid=float(np.mean(limits))
        def yaw(a,b):return math.atan2(float(np.cross(a,b)[2]),float(np.dot(a[:2],b[:2])))
        # Native v4's clockwise quarter turn consumed q7 headroom before
        # transport. Both antipodal axes pinch the same chip; choose the one
        # predicted toward the measured wrist-range centre, then verify every
        # actual rotation. This is a reference route, never a joint-state edit.
        candidates=[]
        for direction in (desired,-desired):
            principal=yaw(current,direction)
            for winding in (-1,0,1):
                angle=principal+2*math.pi*winding
                if abs(angle)<=2*math.pi and limits[0]+.10<=q-angle<=limits[1]-.10:
                    candidates.append((angle,direction.copy()))
        if not candidates:raise ToolExecutionError('No measured-margin equivalent pinch rotation')
        planned,target=min(candidates,key=lambda x:(abs(q-x[0]-mid),abs(x[0])))
        previous=current;travelled=0.
        orientation_progress=[]
        for _ in range(100):
            current=axis();travelled+=yaw(previous,current);previous=current
            angle=planned-travelled;q,limits=wrist()
            if min(q-limits[0],limits[1]-q)<.10:
                raise ToolExecutionError('Actual empty wrist exhausted joint margin')
            if abs(angle)<math.radians(5) and abs(yaw(current,target))<math.radians(5):return
            if self.task=='E20'and self.a.control_report.get('engineering_reference_only'):
                orientation_progress.append(abs(angle))
                if len(orientation_progress)>=4 and orientation_progress[-4]-min(orientation_progress[-3:])<math.radians(.1):
                    raise ToolExecutionError('E20 empty axis stopped progressing after three actions')
            self.act(side,'ROTATE_CCW' if angle>0 else 'ROTATE_CW',degrees=min(10.,max(.5,abs(math.degrees(angle)))))
        raise ToolExecutionError('Measured chip finger-axis alignment did not converge')

    def park_e39_idle_hand(self,active):
        """Use public moves to restore an empty sibling's measured home TCP."""
        from .author_clearance import _empty
        idle='right' if active=='left' else 'left'
        _empty(self.a,idle)
        target=np.asarray(self._e39_home[idle],float)
        if np.max(np.abs(self.tip(idle)-target))<=.003:return
        self.stage('workflow-park-empty-'+idle)
        height=max(self.clearance,float(self.tip(idle)[2]),float(target[2]))
        self.move(idle,[*self.tip(idle)[:2],height])
        self.move(idle,[*target[:2],height])
        self.move(idle,target)
        _empty(self.a,idle)

    def move_point(self,side,ref,target,guard=None,follower=None,tolerance=.002):
        """Replan from measured payload pose after each attainable TCP step.

        The old inner 0.8 mm TCP requirement can stall under a held load even
        when the actual payload meets the outer 2 mm target. Keep the payload
        acceptance unchanged; never infer its pose from a rigid attachment.
        """
        target=np.asarray(target,dtype=float)
        if target.shape!=(3,) or not np.isfinite(target).all() or not np.isfinite(tolerance) or tolerance<=0:
            raise ToolExecutionError('Invalid measured payload waypoint')
        if self.task=='E39':
            from .execution_design_e39_reference import move_payload_point
            return move_payload_point(self,side,ref,target,guard,follower,tolerance)
        material_progress=[]
        for _ in range(100):
            if guard:guard()
            error=target-self.point(ref)
            if np.max(np.abs(error))<=tolerance:return
            fast=self.task=='E20'and self.a.control_report.get('engineering_reference_only')
            if fast:
                material_progress.append(float(np.linalg.norm(error)))
                if len(material_progress)>=4 and material_progress[-4]-min(material_progress[-3:])<.0002:
                    raise ToolExecutionError('E20 actual working point stalled after three corrections')
            self.move(side,self.tip(side)+np.clip(error,-.012,.012),guard,follower,
                      tolerance=tolerance if fast and tolerance>=.004 else min(tolerance,.002))
        if guard:guard()
        if np.max(np.abs(target-self.point(ref)))<=tolerance:return
        raise ToolExecutionError('Measured working point failed to converge')

    def place(self,name,actor,local,yaw=None,*,actual_held_side=None):
        if actual_held_side is not None:
            if (self.task!='E20'or actual_held_side not in('left','right')
                    or not self.a.control_report.get('engineering_reference_only')
                    or not getattr(self.c,'_engineering_diagnostic_only',False)
                    or not getattr(self.c,'_engineering_checkpoint_readback_passed',False)):
                raise ToolExecutionError('Actual-held placement requires admitted E20 checkpoint')
            from .execution_design_segments_e17_e20 import _held_with_contacts
            _held_with_contacts(self,name,actual_held_side)
        if self.task=='E39' and name=='work_tray' and actor=='protective_box':
            if yaw not in (None,0,0.):raise ToolExecutionError('E39 tray route requires unchanged yaw')
            from .execution_design_e39_reference import place_work_tray
            return place_work_tray(self,actor,local)
        if self.task=='E01' and name=='tray':
            from .execution_design_e01_tray_reference import transport_tray
            base,rotation=self.frame(dict(actor=actor))
            if np.linalg.norm(rotation-np.eye(3))>.08 or yaw not in (None,0,0.):
                raise ToolExecutionError('E01 dual-tray reference requires level unrotated package')
            return transport_tray(self,base+rotation@np.asarray(local),actor)
        self.stage('workflow-place-'+name+'-on-'+actor)
        if actual_held_side is not None:
            ref,side=self.ref(name),actual_held_side
        elif self.task=='E20' and name in self.d['target_members']:
            from .execution_design_e20_reference import pickup_via_transfer_support
            source_frame=self.frame(dict(actor=actor));planned_target=source_frame[0]+source_frame[1]@np.asarray(local)
            ref,side=pickup_via_transfer_support(self,name,planned_target)
        else:ref,side=self.pickup(name)
        frame=self.frame(dict(actor=actor));target=frame[0]+frame[1]@np.asarray(local)
        rotation=frame[1]@_axis_rotation([0,0,1],yaw) if yaw is not None else None
        self.stage('workflow-place-'+name+'-on-'+actor)
        sorting_piece=self.task=='E09' and name in set(self.d['target_members'])|set(self.d.get('batch_members',{}).get('distractor',[])) and any(r['actor']==actor for r in self.d['local_regions'])
        if (sorting_piece and self.d.get('revision')=='embodied50-execution-v3-20261102'
                and self.a.control_report.get('engineering_reference_only')):
            from .execution_design_e09_reference import verify_held_piece_slot
            verify_held_piece_slot(self,name,actor,local)
        if sorting_piece:
            # Opening inside the shallow box can hook its rim and drag it to
            # the next pickup site (native v3 drop-v2). Measure finger mesh
            # clearance above the actual rim, then let gravity seat the cargo.
            if float(frame[1][2,2])<.98:
                raise ToolExecutionError('Sorting box is not upright for gravity placement')
            box=self.objects[actor]
            center=frame[0]+frame[1]@np.asarray(box.get('local_bounds_center',[0,0,0]))
            rim=float(center[2]+np.abs(frame[1][2])@np.asarray(box['size']))
            if self.d.get('operable_packaging'):
                # High exterior handling bars are outside the X-jaw sorting
                # sweep. Retain the real shallow shell rim for placement.
                rim=float(frame[0][2]+np.abs(frame[1][2])@np.asarray(box['e09_shell_half_size']))
            bottom_to_tcp=float(self.point(dict(actor=name,local=self.bottom_local(name)))[2]-self.tip(side)[2])
            target=target.copy();target[2]=max(target[2]+.020,self.a.floor_clear_tcp(side,floor=rim+.010)+bottom_to_tcp)
        chip_place=self.task=='E20' and name in self.d['target_members'] and actor=='compartment_tray'
        ordered_piece=self.task=='E39' and name in self.d['target_members'] and actor==self.d['local_order']['actor']
        sorting_package=self.task=='E09' and not sorting_piece
        low_transport=chip_place or ordered_piece or sorting_piece or sorting_package
        previous_clearance=self.clearance if low_transport else None
        if sorting_piece:
            # All E09 props and fixtures remain in the obstacle bound. Unlike
            # a fixed 1.15 m payload waypoint, the actual highest obstacle plus
            # measured finger-toe clearance does not force an extended wrist
            # into the high/far corner above the third sorting box.
            self.clearance=self.measured_transport_clearance(name,side)
        if sorting_package:
            from .execution_design_e09_clearance import measured_package_clearance
            self.clearance=measured_package_clearance(self,name,side)
        if chip_place:
            if float(frame[1][2,2])<.98:raise ToolExecutionError('Compartment tray is not upright for gravity placement')
            o=self.objects[actor]
            center=frame[0]+frame[1]@np.asarray(o.get('local_bounds_center',[0,0,0]))
            rim=float(center[2]+np.abs(frame[1][2])@np.asarray(o['size']))
            offset=float(self.point(dict(actor=name,local=self.bottom_local(name)))[2]-self.tip(side)[2])
            target=target.copy();target[2]=max(target[2],self.a.floor_clear_tcp(side,floor=rim+.010)+offset)
            self.clearance=self.measured_transport_clearance(name,side)
        if self.task=='E17' and actor=='stand' and name in self.d['target_members']:
            from .execution_design_e17_reference import measured_shelf_release
            layer=self.s['required_layers'][name]
            release_local=measured_shelf_release(self,name,side,actor,layer,local)
            target=frame[0]+frame[1]@release_local
        if ordered_piece:self.clearance=self.measured_transport_clearance(name,side,target=target)
        try:
            from .execution_design_e09_liftoff import piece_transport_steps
            with piece_transport_steps(self,name):
                from .execution_design_e20_far_blue import applies as far_blue_applies,place as place_far_blue
                if chip_place and far_blue_applies(self,name,actor,local):
                    place_far_blue(self,name,ref,side,actor,local)
                elif ordered_piece and self.a.control_report.get('engineering_reference_only'):
                    from .execution_design_e39_piece import place_held_piece
                    place_held_piece(self,name,ref,side,self.bottom_local(name),target,rotation,support=actor)
                else:
                    self.lower_place(name,ref,side,self.bottom_local(name),target,rotation,support=actor)
        finally:
            if low_transport:self.clearance=previous_clearance
        if sorting_piece or chip_place:
            state,contacts=self.snapshot()
            if any(state[actor]['grasp']) or any(frozenset((actor,f'{hand}_finger{i}')) in contacts for hand in ('left','right') for i in (1,2)):
                raise ToolExecutionError('Sorting box remains in finger contact after retreat')
            if np.linalg.norm(state[actor]['pos']-frame[0])>.015:
                raise ToolExecutionError('Sorting box displaced during cargo release')
            if chip_place:
                from .execution_design_e20_reference import remember_freed_source_rail
                remember_freed_source_rail(self,name)

    def measured_transport_clearance(self,name,side,target=None):
        """Reference height above real props/fixtures and real finger toes.

        There is no maximum-height clamp: if the necessary safe height is not
        reachable, normal measured public-action control must fail honestly.
        """
        state=self.snapshot()[0];top=.8;corridor=None
        if target is not None and self.task=='E39':
            target=np.asarray(target,float)
            if target.shape!=(3,) or not np.isfinite(target).all():
                raise ToolExecutionError('Invalid E39 transport corridor target')
            origin=self.point(dict(actor=name,local=self.bottom_local(name)))
            held=state[name];obj=self.objects[name]
            center=held['pos']+held['mat']@np.asarray(obj.get('local_bounds_center',[0,0,0]))
            radius=float(np.linalg.norm(center-origin)+np.linalg.norm(obj['size']))
            # A sphere about the measured working point covers the object
            # and both finger boxes under any intervening rotation. Sweep its
            # XY projection over the entire axis-aligned waypoint rectangle.
            for f in self.a.finger_geometry(side)['fingers']:
                lo=np.asarray(f['aabb_min_task_m']);hi=np.asarray(f['aabb_max_task_m'])
                radius=max(radius,float(np.linalg.norm((lo+hi)/2-origin)+np.linalg.norm((hi-lo)/2)))
            corridor=(np.minimum(origin[:2],target[:2])-radius-.010,
                      np.maximum(origin[:2],target[:2])+radius+.010)
        def crosses(center,extent):
            return corridor is None or bool(np.all(center[:2]+extent[:2]>=corridor[0]) and np.all(center[:2]-extent[:2]<=corridor[1]))
        for actor,value in state.items():
            if actor==name:continue
            o=self.objects[actor];mat=np.asarray(value['mat'])
            center=np.asarray(value['pos'])+mat@np.asarray(o.get('local_bounds_center',[0,0,0]))
            extent=np.abs(mat)@np.asarray(o['size'])
            if crosses(center,extent):top=max(top,float(center[2]+extent[2]))
        for f in self.spec.get('fixtures',[]):
            if f.get('type')!='box':raise ToolExecutionError('Unreviewed fixture shape for low transport')
            center=np.asarray([*f.get('xy',[0.,0.]),f['z']]);extent=np.asarray(f['size'])
            if crosses(center,extent):top=max(top,float(center[2]+extent[2]))
        offset=float(self.point(dict(actor=name,local=self.bottom_local(name)))[2]-self.tip(side)[2])
        measured=max(top+.050,self.a.floor_clear_tcp(side,floor=top+.050)+offset)
        # E20 native 437 held the chip but stalled near q4=-.467 during the
        # arbitrary 1m horizontal transit. Keep the full measured 50mm
        # obstacle/finger margin; do not force this shallow scene to 1m.
        # Reachability remains an independent engineering acceptance gate.
        return measured if self.task=='E20' else max(1.0,measured)

    def pickup_from_storage(self,name):
        route=self.d.get('storage_extraction',{}).get(name)
        if route is None:return self.pickup(name)
        self.stage('storage-approach-'+name)
        ref=self.ref(name);side=self.hand_for(name)
        approach=np.asarray(route['approach_offset_task'],float);exit_offset=np.asarray(route['exit_offset_task'],float)
        lift=float(route['lift_m'])
        if approach.shape!=(3,) or exit_offset.shape!=(3,) or not np.isfinite(approach).all() or not np.isfinite(exit_offset).all() or not 0<lift<=.025:
            raise ToolExecutionError('Invalid reviewed storage extraction geometry')
        from .author_clearance import prepare_single_hand
        prepare_single_hand(self.a,side,self.clearance)
        self.act(side,'RELEASE')
        point=self.point(ref);outside=point+approach
        height=max(self.clearance,float(point[2])+.10,float(self.tip(side)[2]))
        self.move(side,[*self.tip(side)[:2],height]);self.move(side,[*outside[:2],height])
        _,rotation=self.frame(ref)
        self.a.align_gripper_axis(side,rotation@np.asarray(ref['jaw_axis_local']))
        if self.a.scene.embodiment.config.get('author_recording',{}).get('pre_grasp_opening_m') is not None:
            self.a.prepare_generated_gripper(side)
        point=self.point(ref);outside=point+approach
        self.move(side,outside)
        if self.task=='E01' and name=='tray':
            value=self.snapshot()[0][name];obj=self.objects[name];rot=np.asarray(value['mat'])
            center=np.asarray(value['pos'])+rot@np.asarray(obj.get('local_bounds_center',[0,0,0]))
            rim=float(center[2]+np.abs(rot[2])@np.asarray(obj['size']))
            entry_height=max(float(point[2]),self.a.floor_clear_tcp(side,floor=rim+.005))
            self.approach_storage_tray(ref,side,entry_height=entry_height)
            self.stage('storage-descend-to-rim-'+name)
            self.move(side,self.point(ref))
        else:self.move(side,point)
        stable=0
        for _ in range(5):
            self.act(side,'GRASP');stable=stable+1 if self.held(ref,side) else 0
            if stable>=3:break
        if stable<3:raise ToolExecutionError('Storage rim grasp did not establish measured two-finger hold')
        guard=lambda:self.require_held(ref,side)
        self.stage('storage-lift-'+name)
        self.move(side,self.tip(side)+[0,0,lift],guard)
        self.stage('storage-side-extract-'+name)
        self.move(side,self.tip(side)+exit_offset,guard)
        return ref,side

    def approach_storage_tray(self,ref,side,entry_height=None):
        """Hold the measured approach plane while entering the lower shelf.

        Native body-place lost 13 mm of height during the long X move; the
        open front finger then met the real shelf edge. Re-read the TCP and
        tray every public action, correcting Z/Y before advancing X. This is
        an E01 reference route, not a controller or collision exception.
        """
        history=[]
        for _ in range(240):
            target=np.asarray(self.point(ref)).copy()
            if entry_height is not None:target[2]=entry_height
            tip=np.asarray(self.tip(side));error=target-tip
            if max(abs(error))<=.002:return
            axis=2 if abs(error[2])>.002 else 1 if abs(error[1])>.002 else 0
            token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
            self.act(side,token,mm=min(5.,max(self.min_mm,abs(float(error[axis]))*1000)))
            history.append(np.asarray(self.tip(side)).copy())
            if len(history)>=20 and np.max(np.ptp(np.asarray(history[-20:]),axis=0))<.0003:
                raise ToolExecutionError('Measured lower-shelf approach is blocked')
        raise ToolExecutionError('Measured lower-shelf approach action bound exceeded')

    def stage_on_table(self,name):
        entry=self.d.get('staging',{}).get(name)
        if not isinstance(entry,dict) or len(entry.get('xy',[]))!=2:
            raise ToolExecutionError('Explicit collision-reviewed staging required: '+name)
        target=[*entry['xy'],entry.get('surface_z',.8)]
        ref,side=self.pickup_from_storage(name)
        if name=='meal_box' and self.task=='E01':
            return self.stage_meal_box(name,ref,side,target)
        if name=='tray' and self.task=='E01':
            return self.stage_extracted_tray(name,ref,side,target)
        if self.task=='E17' and name=='packing_lid':
            return self.stage_packing_lid(name,ref,side,target)
        if self.task=='E39' and name in self.d['target_members']:
            # Native v2 genuinely held the piece; the old acquisition label
            # obscured a subsequent high cross-body transport failure.
            self.stage('workflow-stage-held-'+name)
            if 'xy_by_hand' in entry:target=[*entry['xy_by_hand'][side],target[2]]
            previous=self.clearance
            self.clearance=self.measured_transport_clearance(name,side,target=target)
            try:return self.lower_place(name,ref,side,self.bottom_local(name),target,support=entry.get('support_by_hand',{}).get(side,'table'))
            finally:self.clearance=previous
        self.lower_place(name,ref,side,self.bottom_local(name),target,support='table')

    def stage_packing_lid(self,name,ref,side,target):
        """Measured low L route avoids the stand and high forward reach."""
        control=dict(actor=name,local=self.bottom_local(name).tolist())
        start=self.point(control);target=np.asarray(target,float)
        points=[start[:2],np.array([start[0],target[1]]),target[:2]]
        height=self.measured_staging_route_height(name,side,points)
        self.stage('stage-held-packing_lid');guard=lambda:self.require_held(ref,side)
        self.move_point(side,control,[*start[:2],height],guard)
        for xy in points[1:]:self.move_point(side,control,[*xy,height],guard)
        previous=self.clearance;self.clearance=height
        try:self.lower_place(name,ref,side,self.bottom_local(name),target,support='table')
        finally:self.clearance=previous
        # The cover is now supported and released. Raising an empty hand at
        # this far-forward staging X can fail before the next acquisition.
        # Retract at the already-cleared height along the same negative-Y
        # corridor, then let the next acquisition lift near the source X.
        self.stage('retreat-empty-after-packing-lid')
        state,contacts=self.snapshot();index=0 if side=='left' else 1
        if any(v['grasp'][index] for v in state.values()) or any(
                frozenset((n,f'{side}_finger{i}'))in contacts for n in state for i in (1,2)):
            raise ToolExecutionError('Packing-lid retreat requires a genuinely empty hand')
        lid=state[name];o=self.objects[name];rot=np.asarray(lid['mat'])
        center=np.asarray(lid['pos'])+rot@np.asarray(o.get('local_bounds_center',[0,0,0]))
        top=float(center[2]+np.abs(rot[2])@np.asarray(o['size']))
        required=self.a.floor_clear_tcp(side,floor=top+.010)
        if self.tip(side)[2]<required:self.move(side,[*self.tip(side)[:2],required])
        self.move(side,[start[0],self.tip(side)[1],self.tip(side)[2]])

    def stage_extracted_tray(self,name,ref,side,target):
        from .execution_design_e01_tray_reference import extract_whole_tray_from_lower_shelf,settle_empty_tray_on_table
        if not hasattr(self,'_e01_native_bottom_local'):
            from .execution_design_e01_contact_diagnostic import install
            install(self)
        extract_whole_tray_from_lower_shelf(self,side)
        return settle_empty_tray_on_table(self,side,release_other=False)

    def measured_staging_route_height(self,name,side,points):
        if (self.task,name) not in (('E17','packing_lid'),('E01','tray')):raise ToolExecutionError('Unreviewed staging route')
        state=self.snapshot()[0]
        def bounds(actor):
            value=state[actor];o=self.objects[actor];rot=np.asarray(value['mat'])
            center=np.asarray(value['pos'])+rot@np.asarray(o.get('local_bounds_center',[0,0,0]))
            half=np.abs(rot)@np.asarray(o['size'])
            return center-half,center+half
        lo,hi=bounds(name);center=(lo+hi)/2
        bottom=self.point(dict(actor=name,local=self.bottom_local(name)))
        extent=(hi-lo)[:2]/2+np.abs(center[:2]-bottom[:2])+.010
        swept=[(np.minimum(a,b)-extent,np.maximum(a,b)+extent)for a,b in zip(points,points[1:])]
        obstacles=[bounds(actor)for actor in state if actor!=name]
        for f in self.spec.get('fixtures',[]):
            if f.get('type')!='box':raise ToolExecutionError('Unreviewed fixture on staging route')
            c=np.array([*f['xy'],f['z']],float);h=np.asarray(f['size'],float);obstacles.append((c-h,c+h))
        top=.8
        for lo,hi in obstacles:
            if any(np.all(hi[:2]>=a)and np.all(lo[:2]<=b)for a,b in swept):top=max(top,float(hi[2]))
        offset=float(bottom[2]-self.tip(side)[2])
        return max(.98,top+.050,self.a.floor_clear_tcp(side,floor=top+.050)+offset)

    def measured_lowest_z(self,name):
        """Conservative real-pose bound, including an attached movable lid."""
        names=[name]+[j['child'] for j in self.spec.get('joints',[]) if j['parent']==name]
        state=self.snapshot()[0];values=[]
        for actor in names:
            o=self.objects[actor];s=state[actor]
            center=np.asarray(s['pos'])+np.asarray(s['mat'])@np.asarray(o.get('local_bounds_center',[0,0,0]))
            values.append(float(center[2]-np.abs(np.asarray(s['mat'])[2])@np.asarray(o['size'])))
        return min(values)

    def raise_payload_bottom(self,name,ref,side,height):
        """Only UP until the measured lowest point clears its support.

        A tilted held box can move horizontally while its low edge is still on
        a shelf. Correcting that XY drift at this stage pushes the edge into
        the shelf. No XY command is issued here and TCP height is never used
        as a substitute for the actual payload clearance.
        """
        history=[]
        for _ in range(100):
            self.require_held(ref,side);z=self.measured_lowest_z(name)
            if z>=height:return
            # Clearance is a lower bound, not an exact pose. A loaded 2.4mm
            # request produced no vertical response in native testing while
            # larger public steps did. Keep a bounded 5mm minimum command and
            # stop only from the measured payload, never from the TCP target.
            self.act(side,'UP',mm=min(10.,max(5.,self.min_mm,(height-z)*1000)))
            history.append(self.measured_lowest_z(name))
            if len(history)>=15 and max(history[-15:])-min(history[-15:])<.0003:
                raise ToolExecutionError('Actual payload cannot clear its storage support: '+name)
        raise ToolExecutionError('Actual payload clearance action bound exceeded: '+name)

    def stage_meal_box(self,name,ref,side,target):
        route=self.d.get('storage_lift',{}).get(name)
        if not route:raise ToolExecutionError('Missing measured meal-box storage clearance route')
        height=float(route['support_top_z'])+float(route['clearance_m'])
        self.stage('clear-storage-'+name)
        self.raise_payload_bottom(name,ref,side,height)
        self.rotate_actor(name,side,np.eye(3))
        self.raise_payload_bottom(name,ref,side,height)
        control=dict(actor=name,local=self.bottom_local(name).tolist())
        self.stage('transport-cleared-'+name)
        # Native clearance-step reached real shelf clearance but simultaneous
        # XY correction drove the loaded wrist toward its high central reach
        # limit. First carry toward the selected arm's side at current X, then
        # traverse X. Both segments retain measured payload/clearance guards.
        self.translate_cleared_meal_box(name,ref,side,1,target[1],height)
        self.translate_cleared_meal_box(name,ref,side,0,target[0],height)
        self.stage('lower-staged-'+name)
        self.lower_measured_meal_box(ref,side,control,np.asarray(target)+[0,0,.001])
        self.release(ref,side);self.move(side,self.tip(side)+[0,0,.06])
        if not self.contact(name,'table'):raise ToolExecutionError('Staged box lacks actual table support')

    def lower_measured_meal_box(self,ref,side,control,target):
        if self.task!='E01' or ref.get('actor')!='meal_box':raise ToolExecutionError('Unreviewed measured box descent')
        target=np.asarray(target,float);history=[]
        for _ in range(180):
            self.require_held(ref,side)
            if self.contact('meal_box','table'):return
            point=self.point(control);error=target-point
            if np.max(np.abs(error))<=.002:return
            axis=int(np.argmax(np.abs(error)))
            token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
            # Every public action is replanned from the real payload point;
            # never wait for a surrogate TCP subtarget under this loaded box.
            self.act(side,token,mm=min(10.,max(2.5,abs(float(error[axis]))*1000)))
            history.append(self.point(control).copy())
            if len(history)>=15 and max(np.linalg.norm(p-history[-1])for p in history[-15:])<.0003:
                raise ToolExecutionError('Actual meal-box placement stalled')
        raise ToolExecutionError('Actual meal-box placement did not reach 2mm goal')

    def translate_cleared_meal_box(self,name,ref,side,axis,target,height):
        """E01-only loaded transit; actual clearance is a lower bound, not a Z goal.

        Native side-carry spent 178 actions correcting a first 12mm TCP
        subtarget after only two useful Y actions. Follow measured cargo-axis
        progress instead, keeping real hold, vertical clearance and a bounded
        lateral corridor. Final table placement still uses the full pose goal.
        """
        if self.task!='E01' or name!='meal_box' or axis not in (0,1):
            raise ToolExecutionError('Unreviewed loaded-axis route')
        control=dict(actor=name,local=self.bottom_local(name).tolist())
        start=self.point(control).copy();history=[]
        other=1-axis
        for _ in range(160):
            self.require_held(ref,side)
            current=self.point(control)
            if abs(float(current[other]-start[other]))>.05:
                raise ToolExecutionError('Loaded meal-box left reviewed transit corridor')
            if self.measured_lowest_z(name)<height:
                raise ToolExecutionError('Loaded meal-box lost real transit clearance')
            error=float(target-current[axis])
            if abs(error)<=.002:return
            if self.measured_lowest_z(name)<height+.008:
                self.raise_payload_bottom(name,ref,side,height+.012)
            token=(('FWD','BACK'),('LEFT','RIGHT'))[axis][int(error<0)]
            self.act(side,token,mm=min(10.,max(5.,abs(error)*1000)))
            history.append(float(self.point(control)[axis]))
            if len(history)>=15 and max(history[-15:])-min(history[-15:])<.0003:
                raise ToolExecutionError('Measured meal-box transit stalled')
        raise ToolExecutionError('Measured meal-box transit action bound exceeded')

    def free_chip_slot(self,r,name):
        """Choose from measured free cells, not the preserved-member count."""
        base,rot=self.frame(dict(actor=r['actor']));state=self.snapshot()[0]
        mid=(np.asarray(r['lower'])+r['upper'])/2
        half=np.abs(rot.T@state[name]['mat'])@np.asarray(self.objects[name]['size'])
        available=[]
        for x,y in ((-.019,-.019),(.019,-.019),(-.019,.019),(.019,.019)):
            xy=mid[:2]+[x,y]
            if np.any(xy-half[:2]<np.asarray(r['lower'])[:2]) or np.any(xy+half[:2]>np.asarray(r['upper'])[:2]):continue
            occupied=False
            for other in r['candidates']:
                if other==name:continue
                center=rot.T@(state[other]['pos']-base)
                extent=np.abs(rot.T@state[other]['mat'])@np.asarray(self.objects[other]['size'])
                if center[2]+extent[2]<r['lower'][2] or center[2]-extent[2]>r['upper'][2]:continue
                if np.all(np.abs(center[:2]-xy)<extent[:2]+half[:2]+.002):occupied=True;break
            if not occupied:available.append([*xy,r['lower'][2]])
        if available:
            if self.task=='E20':
                from .execution_design_e20_reference import robot_bases
                bases=robot_bases(self)
                # Count/colour rules permit every genuinely free cell. The
                # old fixed iteration order picked the farther X cell first,
                # forcing a held chip into a repeated extended-arm stall.
                return min(available,key=lambda p:min(float(np.linalg.norm((base+rot@p)[:2]-b[:2])) for b in bases.values()))
            return available[0]
        if (self.task=='E20'and self.d.get('revision')=='embodied50-execution-v3-20261102'
                and self.a.control_report.get('engineering_reference_only')):
            from .execution_design_e20_slots import boundary_slot
            return boundary_slot(self,r,name)
        raise ToolExecutionError('No measured free chip slot: '+r['id'])

    def region_local(self,r,n,i):
        if (self.task=='E09'and self.d.get('revision')=='embodied50-execution-v3-20261102'
                and self.a.control_report.get('engineering_reference_only')):
            from .execution_design_e09_reference import piece_slot_local
            return piece_slot_local(self,r,n,i)
        mid=(np.asarray(r['lower'])+r['upper'])/2
        return [mid[0]+(i%2-.5)*.044,mid[1]+(i//2-.5)*.044,r['lower'][2]]

    def order_rule(self):
        e=self.c.evaluator
        if not getattr(e,'initial_sealed',False) or not getattr(e,'initial_order_rule',None):
            raise ToolExecutionError('E39 requires sealed measured reference/work-tray baseline')
        return deepcopy(e.initial_order_rule)

    def place_lower_shelf(self,name,actor,target_local):
        if self.task=='E17' and self.objects[actor].get('e17_stand_geometry'):
            from .execution_design_e17_insertion import place_lower
            return place_lower(self,name,actor,target_local)
        route=self.d.get('shelf_insertion',{}).get('lower')
        if route is None:raise ToolExecutionError('Reviewed lower-shelf side insertion required')
        entry_x=float(route['entry_abs_x']);carry_z=float(route['carry_bottom_z'])
        retreat=float(route['retreat_lift_m'])
        if not (entry_x>.105 and .017<carry_z<.06 and 0<retreat<.06):
            raise ToolExecutionError('Invalid reviewed lower-shelf insertion clearance')
        self.stage('workflow-side-insert-'+name)
        ref,side=self.pickup(name);guard=lambda:self.require_held(ref,side)
        base,rot=self.frame(dict(actor=actor))
        from .execution_design_e17_reference import measured_shelf_entry
        signed_entry,height=measured_shelf_entry(self,name,side,actor,target_local,entry_x)
        entry_x=abs(signed_entry)
        self.stage('workflow-carry-to-lower-entry-'+name)
        control=dict(actor=name,local=self.bottom_local(name))
        self.move_point(side,control,[*self.point(control)[:2],height],guard)
        self.rotate_actor(name,side,rot)
        control['local']=self.bottom_local(name)
        # The stand is itself a movable body. Re-read it after the real high
        # carry/rotation; the failed native route had displaced it by 16mm.
        base,rot=self.frame(dict(actor=actor))
        signed_entry,fresh_height=measured_shelf_entry(self,name,side,actor,target_local,entry_x)
        entry_x=abs(signed_entry);height=max(height,fresh_height)
        self.move_point(side,control,[*self.point(control)[:2],height],guard)
        from .execution_design_e17_reference import measured_shelf_release
        release_local=measured_shelf_release(self,name,side,actor,'lower',target_local)
        carry_z=max(carry_z,float(release_local[2]))
        entry=np.asarray(target_local,float).copy()
        entry[0]=math.copysign(entry_x,entry[0]);entry[2]=carry_z
        inside=np.asarray(target_local,float).copy();inside[2]=carry_z
        outside=base+rot@entry;hover=base+rot@inside;goal=base+rot@release_local
        from .execution_design_e17_reference import clear_lower_ingress
        low_route=clear_lower_ingress(self,name,side,actor,entry,inside)
        outside=base+rot@low_route[0]
        # Descend outside both plates, carry over the bottom rim below the
        # upper plate, then lower onto the source-reviewed support point.
        self.move_point(side,control,[*outside[:2],height],guard)
        self.stage('workflow-side-insert-'+name)
        self.move_point(side,control,outside,guard)
        for waypoint in low_route[1:]:self.move_point(side,control,base+rot@waypoint,guard)
        self.move_point(side,control,goal,guard)
        self.release(ref,side)
        # The empty fingers must also exit sideways before any high lift.
        self.move(side,self.tip(side)+rot@[0,0,retreat])
        previous_waypoint=low_route[-1]
        for waypoint in reversed(low_route[:-1]):
            self.move(side,self.tip(side)+rot@[waypoint[0]-previous_waypoint[0],waypoint[1]-previous_waypoint[1],0])
            previous_waypoint=waypoint
        self.move(side,[*self.tip(side)[:2],height]);self.wait(3)
        if not self.contact(name,actor):raise ToolExecutionError('Inserted piece lacks actual shelf support: '+name)

    def food(self):
        if self.task=='E01'and self.a.control_report.get('engineering_reference_only'):
            from .execution_design_e01_food import food_local
            return food_local(self)
        return super().food()

    def local_stage(self):
        if self.task=='E01':
            self.stage_on_table('meal_box')
            self.stage_on_table('tray')
            self.food();return
        if self.task=='E39':
            r=self.order_rule()
            base,rot=self.frame(dict(actor=r['actor']));state=self.snapshot()[0]
            points={n:rot.T@(state[n]['pos']+state[n]['mat']@self.bottom_local(n)-base) for n in r['pieces']}
            slots=sorted(points.values(),key=lambda p:p[r.get('axis',1)],reverse=r.get('descending',True))
            # Clear every occupied cell before any permutation/rotation. For an
            # orientation-only rule restore each measured original position.
            for n in r['pieces']:self.stage_on_table(n)
            for i,n in enumerate(r['expected_order']):
                target=slots[i] if r.get('match_order',self.d['local_order'].get('match_order')) else points[n]
                self.place(n,r['actor'],target,r['expected_yaws'][n])
            return
        if self.task=='E17':
            # Open the rigid removable packing lid before accessing its contents.
            self.stage('open-packing-lid')
            self.stage_on_table('packing_lid')
        regions=self.d['local_regions']
        if self.task=='E20':
            from .execution_design_e20_reference import ordered_replenishment_regions
            regions=ordered_replenishment_regions(self)
        for i,r in enumerate(regions):
            if self.task=='E09':
                # Exercise the source triangle grasp first in each applicable
                # group; it was the remaining failure after two easy pieces.
                # Membership and the complete route remain unchanged.
                names=sorted(self.d['unordered_expected_groups'][i],key=lambda n:('triangle' not in n,n))
            elif self.task=='E20':
                preserved=set(self.d['initial_preserved'][r['id']])
                from .execution_design_e20_reference import replenishment_candidates
                available=replenishment_candidates(self,r)
                names=available[:r['count']-len(preserved)]
                if getattr(self,'_engineering_skip_actual_completed_regions',False):
                    if (not getattr(self.c,'_engineering_diagnostic_only',False)
                            or not getattr(self.c,'_engineering_checkpoint_readback_passed',False)):
                        raise ToolExecutionError('Actual completed-region suffix requires native checkpoint admission')
                    from .execution_design_e20_slots import _inside
                    actual=self.snapshot()[0]
                    completed={n for n in r['candidates']if not any(actual[n]['grasp'])
                        and _inside(self,r,n)and self.contact(n,r['actor'])}
                    if len(completed)>r['count']:
                        raise ToolExecutionError('Actual completed E20 region already exceeds original count: '+r['id'])
                    # Placement changes distance rankings. Re-select only the
                    # still-needed number, rather than reusing the old prefix
                    # length and accidentally adding a fourth already-full chip.
                    needed=r['count']-len(completed)
                    names=[n for n in available if n not in completed][:needed]
                # Actual occupied positions are checked before every placement.
            else:names=r['members']
            for j,n in enumerate(names):
                target=self.free_chip_slot(r,n) if self.task=='E20' else self.region_local(r,n,j)
                if self.task=='E17':
                    # Preserve the source-reviewed quadrants around the central
                    # stand post; the generic small-box grid is too close to it.
                    reviewed=self.geometry.get('shelf_positions',{}).get(n)
                    if reviewed is None:raise ToolExecutionError('Missing reviewed shelf placement: '+n)
                    target=[*reviewed[:2],self.s['shelves'][r['id']]['center_local'][2]]
                    if r['id']=='lower':
                        from .execution_design_e17_reference import source_side_lower_slot
                        target=source_side_lower_slot(self,j,len(names))
                        if self.objects[r['actor']].get('e17_stand_geometry'):
                            from .execution_design_e17_insertion import front_lower_slot
                            target=front_lower_slot(self,j,len(names))
                    from .execution_design_e17_reference import collision_shelf_target
                    target=collision_shelf_target(self,r['actor'],r['id'],target)
                if self.task=='E17' and r['id']=='lower':self.place_lower_shelf(n,r['actor'],target)
                else:self.place(n,r['actor'],target)

    def close_lid(self,p):
        if self.task=='E39'and self.a.control_report.get('engineering_reference_only'):
            from .execution_design_e39_package import preflight_lid_phase,close_lid_by_contact
            old=getattr(self.a,'_execution_design_reference_authorized',False)
            self.a._execution_design_reference_authorized=True
            try:preflight_lid_phase(self);return close_lid_by_contact(self,p)
            finally:self.a._execution_design_reference_authorized=old
        name=p['lid'];self.stage('workflow-close-'+name)
        ref=self.ref(name);side=self.hand_for(name)
        index=p.get('hinge_joint_index')
        if index is None:
            ref,side=self.pickup(name)
            base,rot=self.frame(dict(actor=p['container']))
            self.lower_place(name,ref,side,[0,0,0],base+rot@np.asarray(p['lid_local_center']),rot,support=p['container'])
            return
        joint=self.spec['joints'][index]
        if joint['type']!='revolute' or joint['parent']!=p['container'] or joint['child']!=name:raise ToolExecutionError('Unverified lid hinge')
        self.acquire(ref,side)
        guard=lambda:self.require_held(ref,side)
        axis={'X':[1,0,0],'Y':[0,1,0],'Z':[0,0,1]}[joint['axis']]
        # Track a physical hinge arc in short public motion increments. Never set
        # its joint position or attach the lid. Failure propagates with receipts.
        parent_rot=self.frame(dict(actor=p['container']))[1]
        child_rot=self.frame(dict(actor=name))[1]
        relative=parent_rot.T@child_rot
        skew=np.array([relative[2,1]-relative[1,2],relative[0,2]-relative[2,0],relative[1,0]-relative[0,1]])/2
        start_angle=math.atan2(float(np.dot(axis,skew)),float((np.trace(relative)-1)/2))
        if np.linalg.norm(relative-_axis_rotation(axis,start_angle))>.08:
            raise ToolExecutionError('Measured lid rotation is not a valid hinge pose')
        limits=joint.get('limits',[0,100])
        if not math.radians(limits[0])-0.05<=start_angle<=math.radians(limits[1])+0.05:
            raise ToolExecutionError('Measured lid outside authored hinge limits')
        samples=max(2,1+math.ceil(abs(start_angle)/math.radians(2)))
        for angle in np.linspace(start_angle,0,samples):
            base,rot=self.frame(dict(actor=p['container']))
            desired=rot@_axis_rotation(axis,float(angle))
            anchor=base+rot@np.asarray(joint['anchor0'])
            goal=anchor+desired@(np.asarray(ref['local'])-np.asarray(joint['anchor1']))
            self.move_point(side,ref,goal,guard,tolerance=.003)
            self.rotate_actor(name,side,desired)
        self.release(ref,side);self.move(side,self.tip(side)+[0,0,.07]);self.wait(4)

    def package_stage(self):
        if self.task=='E01'and self.a.control_report.get('engineering_reference_only'):
            from .execution_design_e01_package import package_stage
            return package_stage(self)
        if (self.task=='E09'and self.d.get('revision')=='embodied50-execution-v3-20261102'
                and self.a.control_report.get('engineering_reference_only')):
            from .execution_design_e09_reference import package_stage
            return package_stage(self)
        for p in self.d['packages']:
            for i,n in enumerate(p['members']):
                self.place(n,p['container'],[0,(i-(len(p['members'])-1)/2)*.12,p['lower'][2]])
            if p.get('lid'):self.close_lid(p)
        for r in self.d['cleanup_regions']:
            if r['actor']:
                if self.task=='E17' and set(r['members'])=={'packing_box','packing_lid'}:
                    self.place('packing_box',r['actor'],[0,0,r['lower'][2]])
                    self.place('packing_lid','packing_box',[0,0,self.objects['packing_box']['size'][2]],yaw=0.)
                else:
                    for i,n in enumerate(r['members']):self.place(n,r['actor'],[(r['lower'][0]+r['upper'][0])/2,(r['lower'][1]+r['upper'][1])/2,r['lower'][2]+i*.01])

    def deliver(self):
        if self.task=='E01'and self.a.control_report.get('engineering_reference_only'):
            from .execution_design_e01_package import deliver_supported_box
            return deliver_supported_box(self)
        if self.task=='E39'and self.a.control_report.get('engineering_reference_only'):
            from .execution_design_e39_delivery import deliver_supported_package,deliver_wall_package
            old=getattr(self.a,'_execution_design_reference_authorized',False)
            self.a._execution_design_reference_authorized=True
            try:
                route=deliver_wall_package if self.d.get('e39_engineering_reset_translation_x_m')==-.025 else deliver_supported_package
                if not route(self):raise ToolExecutionError('E39 actual delivery geometry not complete')
                return
            finally:self.a._execution_design_reference_authorized=old
        if (self.task=='E09'and self.d.get('revision')=='embodied50-execution-v3-20261102'
                and self.a.control_report.get('engineering_reference_only')):
            from .execution_design_e09_reference import deliver_loaded_crate
            return deliver_loaded_crate(self)
        name=self.d['delivery_actor'];zone=next(z for z in self.spec['zones']if z['id']==self.d['destination_zone'])
        self.stage('workflow-deliver-'+name);ref,side=self.pickup(name)
        previous=self.clearance
        if self.task=='E09':
            from .execution_design_e09_clearance import measured_package_clearance
            self.clearance=measured_package_clearance(self,name,side)
        try:self.lower_place(name,ref,side,self.bottom_local(name),[*zone['xy'],zone.get('surface_z',.8)],rotation=np.eye(3),support=self.d.get('delivery_support_actor','table'))
        finally:self.clearance=previous
        self.wait(6)


def solve_execution_design(author):
    policy=ExecutionDesignAuthor(author)
    policy.local_stage();policy.package_stage();policy.deliver()
    return dict(task=policy.task,variant=policy.variant,actions=policy.c.steps-policy.start,
                operations=policy.operations,execution_finished=True,physics_success_not_asserted=True,
                receipt_file=str(author.out/'demo-actions.private.jsonl'))
