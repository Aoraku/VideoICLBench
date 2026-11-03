"""Source cardboard edge pinch and contact-driven folding at the table edge."""
import json
import math
from contextlib import contextmanager

import numpy as np

from .author_mplib_planner import _quat, _rotation, plan
from .realworld_tool_expert import ToolExecutionError, _axis_rotation, _unit


def fold_source_edge(policy):
    p = policy
    author = p.a
    geometry = p.s['crease']['expert']
    mechanism = p.s['crease']['mechanism']
    fold = dict(mechanism=mechanism, **geometry['fold_grasp'])
    reviewed_grasp=author.scene.embodiment.config.get('author_recording',{}).get('e44_grasp_point_local')
    if reviewed_grasp is not None:fold['local']=list(reviewed_grasp)
    base = dict(mechanism=mechanism, **geometry['base_press'])
    outward = np.array([-1., 0., 0.])
    hand = np.column_stack(([0., 1., 0.], [0., 0., 1.], [1., 0., 0.]))

    def actual_hand(side):
        robot = author.scene.robots[side]
        return (author.scene.layout.task_rotation.T
                @ _rotation(robot.data.root_quat_w[0].cpu().tolist())
                @ _rotation(p.c.pose(side)[1][0].cpu().tolist()))

    def verified_pose(side, target, rotation, guard=None):
        proposal = plan(author.scene, p.c, side, np.asarray(target).tolist(),
                        task_tcp_quaternion=_quat(rotation).tolist())
        with (author.out/'E44-empty-hand-plans.private.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(stage=author.stage, side=side,
                target=np.asarray(target).tolist(), rotation=rotation.tolist(),
                status=proposal.get('status'), verified=proposal.get('verified'),
                diagnostics=proposal.get('diagnostics')), default=lambda v:v.tolist())+'\n')
        if proposal.get('status') != 'Success' or proposal.get('verified') is not True:
            raise ToolExecutionError('No fullworld verified E44 free hand approach')
        author.execute_joint_path(side, proposal, guard=guard)

    acquired=False

    def held():
        if not acquired:return
        if author.scene.embodiment.config.get('author_recording',{}).get('e44_contact_driven_bending',False):
            # E44's source task requires physical finger-driven crease motion,
            # rather than a rigid two-finger transport attachment. A remaining
            # real pushing finger is sufficient during the contact phase.
            if not any(p.contact(fold['contact_body'],f'right_finger{i}') for i in (1,2)):
                raise ToolExecutionError('Fold lost all actual actuating finger contact')
        else:p.require_held(fold, 'right')

    @contextmanager
    def hold_actual_arm(side):
        robot=author.scene.robots[side];ids=p.c.ids[side][0]
        q=robot.data.joint_pos[:,ids].clone();overrides=p.c._author_joint_override
        previous=overrides.get(side);overrides[side]=(q,q*0.)
        try:yield
        finally:
            if previous is None:overrides.pop(side,None)
            else:overrides[side]=previous
            pos,quat=p.c.pose(side);p.c.targets[side]=(pos.clone(),quat.clone())

    with hold_actual_arm('right'):
        # An open downward hand presses the original base panel. The target uses
        # actual native finger toes; the panel point is not a TCP coordinate.
        p.stage('E44-actual-base-panel-press')
        p.act('left', 'RELEASE')
        press = p.point(base)
        down = np.diag([1., -1., -1.])
        recording=author.scene.embodiment.config.get('author_recording',{})
        corner_press=recording.get('e44_native_surface_corner_press',False)
        if corner_press:
            press=press.copy()
            if recording.get('e44_symmetric_base_press',False):
                press[:2]=[-.19,0.]
                down=_axis_rotation([0,1,0],math.pi/4)@np.diag([-1.,1.,-1.])
            else:
                press[:2]=[-.20,.15]
                down=(_axis_rotation([1,0,0],math.radians(5))
                      @_axis_rotation([0,1,0],math.pi/4)@np.diag([-1.,1.,-1.]))
        elif recording.get('e44_base_press_palm_outside_leaf',False):
            # Keep the wide native palm outside the entire moving leaf. Actual
            # source STL vertices prove >6mm Y and >19mm table clearance at55deg.
            press=press.copy();press[1]=.09
            down=(_axis_rotation([1,0,0],math.radians(-55))
                  @_axis_rotation([0,0,1],math.pi/2)@down)
            p.act('left','GRASP')
        verified_pose('left', press+[0., 0., .14], down, held)
        press_tcp = np.array([*press[:2], author.floor_clear_tcp('left', floor=press[2]+.0006)-.0005])
        if corner_press:
            import carb,omni.physx
            from pxr import PhysicsSchemaTools
            from .source_reviewed_collisions import ray_hit_value
            query=omni.physx.get_physx_scene_query_interface()
            robot=author.scene.robots['left'];rays=[];all_hits=[];all_toes=[]
            # Use the exact native finger vertices already cached by floor_clear_tcp.
            # A ray must hit the finite source base, not its bounding rectangle.
            for bid,points in author._finger_collision_points['left']:
                rotation=author.scene.layout.task_rotation.T@_rotation(robot.data.body_quat_w[0,bid].cpu().tolist())
                position=author.scene.world_to_task(robot.data.body_pos_w[0,bid].cpu().numpy())
                toes=points@rotation.T+position
                for toe in toes[toes[:,2]<=toes[:,2].min()+.0002]:
                    all_toes.append(toe.tolist())
                    hits=[]
                    def report(hit):
                        value=ray_hit_value(hit,'rigidBody','rigid_body');body=str(value if isinstance(value,str)else PhysicsSchemaTools.intToSdfPath(value))
                        all_hits.append(dict(body=body,position_world=list(ray_hit_value(hit,'position'))))
                        if body.endswith('/BasePanel') and '/Mechanisms/'in body:
                            point=author.scene.world_to_task(np.asarray(ray_hit_value(hit,'position'),float))
                            hits.append(dict(body=body,point=point.tolist(),normal=list(ray_hit_value(hit,'normal'))))
                        return True
                    origin=author.scene.task_to_world([*toe[:2],max(press[2]+.08,float(toe[2])+.01)])
                    query.raycast_all(carb.Float3(*map(float,origin)),carb.Float3(0.,0.,-1.),.4,report)
                    for hit in hits:
                        shift=float(hit['point'][2]-toe[2])
                        rays.append(dict(toe_task=toe.tolist(),hit=hit,tcp_downward_shift_m=shift))
            (author.out/'E44-all-toe-ray-hits.private.json').write_text(json.dumps(dict(
                toes_task=all_toes,hits=all_hits,base_frame_position=p.frame(base)[0].tolist()),indent=2)+'\n')
            if not rays:raise ToolExecutionError('No actual finger toe ray intersects original finite base surface')
            selected=max(rays,key=lambda x:x['tcp_downward_shift_m'])
            press_tcp=np.array([*press[:2],p.tip('left')[2]+selected['tcp_downward_shift_m']-.00015])
            (author.out/'E44-native-base-surface-rays.private.json').write_text(json.dumps(dict(
                rays=rays,selected=selected,target_tcp=press_tcp.tolist()),indent=2)+'\n')

        def base_contact():
            return any(p.contact(base['contact_body'], f'left_finger{i}') for i in (1, 2))

        stable_press_ticks=0;last_press_tick=-1
        def base_seated():
            finger=max(float(p.c.contact_forces.get(frozenset((base['contact_body'],f'left_finger{i}')),0.))for i in (1,2))
            table=float(p.c.contact_forces.get(frozenset((base['contact_body'],'table')),0.))
            return finger>.02 and table>.02
        def stable_base_seated():
            nonlocal stable_press_ticks,last_press_tick
            if last_press_tick!=p.c.physics_ticks:
                stable_press_ticks=stable_press_ticks+1 if base_seated()else 0
                last_press_tick=p.c.physics_ticks
            return stable_press_ticks>=8
        author.move_smooth({'left':press_tcp+[0.,0.,.004]},tolerance=.001,guard=held,
                           max_speed=.08,max_acceleration=.3)
        for _ in range(8):
            if base_seated():break
            author.move_smooth({'left':p.tip('left')-[0.,0.,.002]},tolerance=.001,
                guard=held,done=stable_base_seated,max_speed=.005,max_acceleration=.025)
        if not base_seated():
            raise ToolExecutionError('Original base lacks sustained actual press and table support')

    with hold_actual_arm('left'):
        p.stage('E44-outside-table-source-edge-acquire')
        p.act('right', 'RELEASE')
        point = p.point(fold)
        tcp = point+outward*.0029
        verified_pose('right', tcp+outward*.06, hand)
        # Enter along the material edge, with one open finger above and the other
        # below the original sheet, while both remain outside the table front.
        verified_pose('right', tcp+outward*.02, hand)
        verified_pose('right', tcp, hand)
        # The paper is1.2mm thick. A valid millimetre-scale joint-path endpoint
        # still needs actual TCP centering before closing these opposed pads.
        author.move_smooth({'right':p.point(fold)+outward*.0029},
            tolerance=.0003,max_speed=.015,max_acceleration=.08)
        stable=0
        for _ in range(5):
            p.act('right', 'GRASP')
            stable=stable+1 if p.held(fold,'right') else 0
            if stable>=3:break
        else:
            raise ToolExecutionError('No actual opposed two-finger cardboard edge grip')

        acquired=True
        base_position, base_rotation = p.frame(base)
        hinge = base_position+base_rotation@np.asarray(geometry['hinge_point_local'], float)
        axis = base_rotation@_unit(geometry['axis_local'])
        vector = p.point(fold)-hinge
        initial_hand = actual_hand('right')
        direction = float(geometry['direction'])
        if direction not in (-1., 1.):
            raise ToolExecutionError('Reviewed fold direction required')
        total = 180.-(90., 120., 45.)[p.index]
        def measured_fold_degrees():
            crease=p.s['crease']
            bn=p.frame(base)[1]@_unit(crease['base']['normal_local'])
            fn=p.frame(fold)[1]@_unit(crease['fold']['normal_local'])
            return math.degrees(math.acos(float(np.clip(bn@fn,-1.,1.))))
        p.stage('E44-source-edge-contact-driven-fold')
        for degrees in np.arange(5., total+5., 5.):
            turn = _axis_rotation(axis, math.radians(min(degrees, total))*direction)
            target = hinge+turn@vector
            desired_hand = turn@initial_hand

            def hand_reached():
                difference = desired_hand@actual_hand('right').T
                return float(np.arccos(np.clip((np.trace(difference)-1)/2, -1., 1.))) < math.radians(1.)

            # A rigid held panel on a real hinge cannot first translate while the
            # wrist keeps its previous orientation. Rotate AND translate the TCP
            # about the actual hinge in the same native physical trajectory.
            from .author_orientation import native_rotate
            def material_reached():
                return abs(measured_fold_degrees()-min(degrees,total))<1.5
            for attempt in range(5):
                if material_reached():break
                before=measured_fold_degrees()
                remaining=float(min(degrees,total))-before
                receipt=native_rotate(p.c,'right',_axis_rotation(axis,math.radians(remaining)*direction),
                    guard=held,done=material_reached,pivot_task=hinge,
                    max_angular_speed=.25,max_angular_acceleration=.5)
                after=measured_fold_degrees()
                with (author.out/'E44-coupled-pivot-motion.private.jsonl').open('a') as stream:
                    stream.write(json.dumps(dict(receipt,attempt=attempt,actual_fold_before_deg=before,
                        actual_fold_after_deg=after,material_target_deg=float(min(degrees,total))))+'\n')
                if material_reached():break
                if after-before<.2:raise ToolExecutionError('Actual panel stalled under real hinge torque')
            if not material_reached():raise ToolExecutionError('Actual source panel angle did not reach bounded hinge waypoint')
            with (author.out/'E44-source-edge-fold-feedback.private.jsonl').open('a') as stream:
                stream.write(json.dumps(dict(commanded_fold_degrees=float(min(degrees,total)),
                    actual_fold_point_task=p.point(fold).tolist(), target_task=target.tolist(),
                    actual_fold_rotation=p.frame(fold)[1].tolist(),
                    actual_hand_rotation=actual_hand('right').tolist(),
                    actual_bilateral_grasp=p.held(fold,'right'), base_contact=base_contact()))+'\n')
        p.release(fold, 'right')
        p.move('right', p.tip('right')-actual_hand('right')[:, 2]*.06)
    p.move('left', p.tip('left')+[0., 0., .07])
    p.wait(8)
