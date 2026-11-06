"""E24 engineering candidate using measured empty/loaded clearance only.

This retains the source cups, box/lid, colour order, public actions and native
rubric. A completed reference is not a physical success certificate.
"""
import numpy as np
from .realworld_structural_expert import StructuralAuthor
from .realworld_tool_expert import ToolExecutionError


CUP_SHA256='c9d82475379f3bc83666d97222a3c55a39f3334f97eb9ed02df4efab84183b5b'
# Intersect the actual part_25 convex collision hull at X=-4mm, Z=31mm.
# Its negative-Y wall interval is [-39.8336197,-37.5431763]mm. Choosing
# the midpoint makes the fingers close across one wall away from the cup row.
OUTER_CUP_GRASP=[-.004,-.038688398004925996,.031]


def outside_cup_grasps(spec,grasps):
    from copy import deepcopy
    if spec.get('id')!='E24' or spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102':
        raise ToolExecutionError('E24 v3 outer-wall reference required')
    objects={obj['id']:obj for obj in spec['objects']};result=deepcopy(grasps)
    for name in ('red','green','blue'):
        obj=objects[name];source=obj.get('source_asset',{})
        if (source.get('sha256')!=CUP_SHA256 or source.get('source_rotation')!=[1,0,0,0]
                or not np.allclose(obj['size'],[.04127701522395277,.04098903641349957,.04400000116457628],rtol=1e-7,atol=1e-9)):
            raise ToolExecutionError('E24 outer-wall grasp requires reviewed actual cup mesh')
        if result[name]['local']!=[-.036,0,.031] or result[name]['jaw_axis_local']!=[1,0,0]:
            raise ToolExecutionError('E24 outer-wall grasp refuses an unknown grasp revision')
        result[name]['local']=OUTER_CUP_GRASP.copy();result[name]['jaw_axis_local']=[0,1,0]
    return result


def measured_clearance(policy, side, *, carried=None, local_point=None):
    state,_=policy.snapshot();top=.8;tops={}
    for name,body in state.items():
        if name==carried:continue
        obj=policy.objects[name];mat=np.asarray(body['mat'],float)
        center=np.asarray(body['pos'],float)+mat@np.asarray(obj.get('local_bounds_center',[0,0,0]),float)
        half=np.asarray(obj.get('bounds_half_extent',obj['size']),float)
        value=float(center[2]+np.abs(mat[2])@half)
        if not np.isfinite(value):raise ToolExecutionError('Nonfinite actual E24 obstacle geometry')
        tops[name]=value;top=max(top,value)
    for i,fixture in enumerate(policy.spec.get('fixtures',[])):
        if fixture.get('type')!='box':raise ToolExecutionError('Unreviewed E24 fixture shape')
        if fixture.get('quat',[1,0,0,0])!=[1,0,0,0]:raise ToolExecutionError('Unreviewed rotated E24 fixture')
        value=float(fixture['z'])+float(fixture['size'][2]);tops['fixture'+str(i)]=value;top=max(top,value)
    tip=np.asarray(policy.tip(side),float)
    fingers=policy.a.finger_geometry(side)
    if fingers.get('source')!='actual_collision_mesh_current_body_pose':
        raise ToolExecutionError('Actual E24 finger collision geometry required')
    lowest=float(fingers['lowest_z_task_m']);point=tip;depth=max(0.,float(tip[2])-lowest)
    if carried is not None:
        body=state[carried];obj=policy.objects[carried];mat=np.asarray(body['mat'],float)
        # Cup upright alignment and flat lid yaw are the only reviewed changes.
        if float(mat[2,2])<.98:raise ToolExecutionError('E24 measured route requires nearly upright carried body')
        center=np.asarray(body['pos'])+mat@np.asarray(obj.get('local_bounds_center',[0,0,0]))
        bottom=float(center[2]-np.abs(mat[2])@np.asarray(obj.get('bounds_half_extent',obj['size'])))
        point=np.asarray(policy.point(dict(actor=carried,local=local_point)),float)
        depth=max(0.,float(point[2])-min(bottom,lowest))
    height=top+depth+.040
    if not np.isfinite(np.r_[tip,point,lowest,height]).all():raise ToolExecutionError('Nonfinite E24 clearance measurement')
    return dict(source='actual_pose_physical_bounds_and_finger_collision_mesh',side=side,
                carried_actor=carried,point_task_m=point.tolist(),obstacle_tops_task_m=tops,
                obstacle_top_z_m=top,lowest_finger_z_m=lowest,point_to_lowest_m=depth,
                margin_m=.040,clearance_z_m=float(height),native_reachability_verified=False)


class MeasuredE24Author(StructuralAuthor):
    def __init__(self,author):
        super().__init__(author)
        if (self.task!='E24' or self.spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102'
                or not getattr(author,'control_report',{}).get('engineering_reference_only')
                or self.spec.get('author_smooth_recording',False)):
            raise ToolExecutionError('E24 v3 discrete independent engineering reference required')
        self.grasps=outside_cup_grasps(self.spec,self.grasps)

    def pickup(self,name):
        if name=='lid':
            from .execution_design_e24_lid import pickup_lid_overhang
            return pickup_lid_overhang(self)
        # The first two source cups use the outward Y wall. Once they are
        # physically released into the box, the third source cup has an empty
        # X-side corridor and can use the perpendicular actual wall instead.
        # This keeps its fingers away from the box's long end during insertion.
        order=(['red','green','blue'],['green','blue','red'],['blue','red','green'])[self.index]
        if name==self.identity[order[2]]:
            state,contacts=self.snapshot();box=self.s['containers']['box']['ref']['actor']
            previous=[self.identity[x]for x in order[:2]]
            if any(any(state[x]['grasp']) or frozenset((x,box))not in contacts for x in previous):
                raise ToolExecutionError('E24 perpendicular grasp requires both earlier cups actually released in box')
            if any(state[name]['grasp']) or frozenset((name,'table'))not in contacts:
                raise ToolExecutionError('E24 third cup must remain physically supported at source before reoriented grasp')
            from copy import deepcopy
            self.grasps=deepcopy(self.grasps)
            self.grasps[name]['local']=[-.038688398004925996,.004,.031]
            self.grasps[name]['jaw_axis_local']=[1,0,0]
            self.operations.append(dict(stage='E24-third-source-perpendicular-wall',actor=name,
                source_collision_part='part_01',source_sha256=CUP_SHA256,
                earlier_cups_released_on_box=previous,public_grasp_attempt_only=True))
        return super().pickup(name)

    def acquire(self,ref,side):
        evidence=measured_clearance(self,side);self.operations.append(dict(stage='measured-empty-clearance',**evidence))
        previous=self.clearance;self.clearance=evidence['clearance_z_m']
        try:return super().acquire(ref,side)
        finally:self.clearance=previous

    def lower_place(self,name,ref,side,local_point,target,rotation=None,support=None):
        if rotation is not None and float(np.asarray(rotation)[2,2])<.98:
            raise ToolExecutionError('E24 placement rotation leaves reviewed upright clearance')
        evidence=measured_clearance(self,side,carried=name,local_point=local_point)
        self.operations.append(dict(stage='measured-loaded-clearance',**evidence))
        previous=self.clearance;self.clearance=evidence['clearance_z_m']
        try:return super().lower_place(name,ref,side,local_point,target,rotation,support)
        finally:self.clearance=previous


def solve_e24_reference(author):
    policy=MeasuredE24Author(author);policy.box_and_lid();policy.wait(4)
    return dict(task=policy.task,variant=policy.variant,actions=policy.c.steps-policy.start,
                operations=policy.operations,route='actual_source_box_measured_clearance',
                execution_finished=True,physics_success_not_asserted=True)


class NegativeE24Author(MeasuredE24Author):
    """Actual public-action interventions; evaluator/spec remain untouched."""
    def __init__(self,author,control):
        if control not in ('wrong_rule','wrong_destination','not_released'):
            raise ValueError('Unreviewed E24 physical counterexample')
        from .execution_design import REVISION_V3,source_sha256
        design=author.scene.spec.get('execution_design',{})
        if (design.get('revision')!=REVISION_V3 or design.get('source_sha256')!=source_sha256(REVISION_V3)
                or not getattr(author,'control_report',{}).get('engineering_reference_only')):
            raise ValueError('E24 counterexample requires explicit v3 independent engineering authorization')
        super().__init__(author);self.control=control
        self.perturbation=dict(control=control,native_condition_observed=None,
            implementation='public_robot_actions_only',score_not_overridden=True)

    def box_and_lid(self):
        orders=(['red','green','blue'],['green','blue','red'],['blue','red','green'])
        expected=orders[self.index];order=list(expected)
        if self.control=='wrong_rule':order[0],order[1]=order[1],order[0]
        self.perturbation.update(expected_order=list(expected),attempted_order=order)
        box=self.s['containers']['box'];support=box['ref'].get('actor',box['ref'].get('contact_body'))
        for label,point in zip(order,self.geometry['box_positions']):
            name=self.identity[label];cup=self.s['cups'][name];ref,side=self.pickup(name)
            self.align_axis(name,side,cup['axis_local'],[0,0,1])
            self.stage('negative-source-box-insertion-'+label)
            self.lower_place(name,ref,side,cup['bottom_local'],self.body_point(box['ref'],point),support=support)
        if self.control=='wrong_destination':
            # Leave the original lid at its measured initial storage pose.
            # Correct cup insertion is retained; the required final lid pose
            # is physically absent, not manufactured in the score record.
            self.stage('negative-lid-left-at-source');self.wait(4)
            self.perturbation['lid_transfer_omitted']=True
            return
        lid=self.s['lid_geometry'];name=lid['ref']['actor'];ref,side=self.pickup(name)
        target=self.body_point(lid['box_ref'],lid['box_rim_center_local'])
        matrix=self.frame(lid['box_ref'])[1];target+=matrix[:,2]*lid['closed_offset_m']
        if self.control=='not_released':
            self.stage('negative-retain-lid-actual-grip')
            # Retain the true bilateral grip already verified by pickup.
            # A separately observed held lid is sufficient to refute release;
            # it must not be placed and secretly reattached after completion.
            self.wait(4);self.require_held(ref,side)
            self.perturbation['lid_release_omitted']=True
            return
        self.stage('close-real-lid-after-wrong-order')
        self.lower_place(name,ref,side,lid['cover_center_local'],target,matrix,support=support)


def solve_e24_negative_reference(author,control):
    policy=NegativeE24Author(author,control);policy.box_and_lid();policy.wait(4)
    return dict(task=policy.task,variant=policy.variant,actions=policy.c.steps-policy.start,
                operations=policy.operations,control=control,perturbation=policy.perturbation,
                execution_finished=True,physics_success_not_asserted=True,
                route='actual_source_box_negative_public_actions')


def measured_box_insertion_target(policy,name,side,local_point,target):
    """Fit actual held fingers and cup into the box, without changing its rule.

    Only the reference waypoint may move minimally inward. Desired Z, order,
    source geometry, native containment and support requirements are unchanged.
    Refuse if actual neighboring cups leave no safe XY interval.
    """
    from itertools import product
    state,contacts=policy.snapshot();box=policy.s['containers']['box'];box_name=box['ref']['actor']
    pos=np.asarray(state[box_name]['pos'],float);mat=np.asarray(state[box_name]['mat'],float)
    if float(mat[2,2])<.98:raise ToolExecutionError('E24 insertion requires upright measured box')
    point=np.asarray(policy.point(dict(actor=name,local=local_point)),float)
    desired=mat.T@(np.asarray(target,float)-pos)
    geometry=policy.a.finger_geometry(side)
    if geometry.get('source')!='actual_collision_mesh_current_body_pose':raise ToolExecutionError('Actual E24 finger mesh required')
    offsets=[]
    for finger in geometry['fingers']:
        lo=np.asarray(finger['aabb_min_task_m'],float);hi=np.asarray(finger['aabb_max_task_m'],float)
        for xyz in product(*zip(lo,hi)):offsets.append(mat.T@(np.asarray(xyz)-point))
    if not offsets:raise ToolExecutionError('Missing E24 actual finger bounds')
    def corners(actor):
        obj=policy.objects[actor];body=state[actor];half=np.asarray(obj.get('bounds_half_extent',obj['size']),float)
        center=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(obj.get('local_bounds_center',[0,0,0]),float)
        return np.asarray([mat.T@(center+np.asarray(body['mat'])@(np.asarray(sign)*half)-pos)for sign in product((-1,1),repeat=3)])
    cup=corners(name);cup_offsets=cup-(mat.T@(point-pos))
    offsets=np.concatenate([np.asarray(offsets),cup_offsets]);lo=np.asarray(box['lower'])[:2]+.002-offsets[:,:2].min(0);hi=np.asarray(box['upper'])[:2]-.002-offsets[:,:2].max(0)
    if not np.isfinite(np.r_[lo,hi,desired]).all()or np.any(lo>hi):raise ToolExecutionError('Actual fingers and cup cannot fit inside E24 box')
    proposed=desired.copy();proposed[:2]=np.clip(proposed[:2],lo,hi)
    # Only a small inward correction is reviewed. A larger change needs a new
    # genuine grasp/approach, not an arbitrary substitute destination.
    if np.linalg.norm(proposed[:2]-desired[:2])>.020:raise ToolExecutionError('E24 measured insertion correction exceeds reviewed 20mm')
    occupied={}
    proposed_cup=cup_offsets+proposed
    for other in policy.s['cups']:
        if other==name or frozenset((other,box_name))not in contacts:continue
        q=corners(other);occupied[other]=dict(lower=q.min(0).tolist(),upper=q.max(0).tolist())
        # Disjoint in either horizontal axis; do not force a cup through a
        # previously released target merely to satisfy the finger wall check.
        separated=np.any(proposed_cup[:,:2].max(0)+.001<=q[:,:2].min(0))or np.any(q[:,:2].max(0)+.001<=proposed_cup[:,:2].min(0))
        if not separated:raise ToolExecutionError('E24 actual neighboring cup blocks measured insertion')
    result=pos+mat@proposed
    policy.operations.append(dict(stage='E24-measured-box-insertion-target',actor=name,
        original_target_task=np.asarray(target).tolist(),target_task=result.tolist(),
        box_frame_target_before=desired.tolist(),box_frame_target_after=proposed.tolist(),
        finger_and_cup_offset_lower=offsets.min(0).tolist(),finger_and_cup_offset_upper=offsets.max(0).tolist(),
        occupied_cups=occupied,margin_m=.002,native_success_asserted=False))
    return result
