"""E37 private author: travel before tilting the actual screwdriver vertical.

Only public actions; no joint, object or evaluator mutation. Native v3 became
locally blocked after rotating at the source, 24cm short of the target screw.
"""
import json
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .execution_design_author_rotation import command_degrees, update_loss


def above_head(policy, ref, side, driver, entry, axis, head, *, resume_at_current_pose=False):
    guard=lambda:policy.require_held(ref,side)
    actor=driver['actor'];axis=np.asarray(axis,float);axis/=np.linalg.norm(axis)
    anchor=np.asarray(policy.tip(side),float).copy()
    if not resume_at_current_pose:anchor[:2]=np.asarray(head(),float)[:2]
    policy.stage('horizontal-driver-transit-above-head'if not resume_at_current_pose else'checkpoint-driver-current-pose')
    # This is only a clear-space staging pose. Final blade/head engagement
    # is separately measured at the unchanged native submillimetre tolerance.
    if not resume_at_current_pose:policy.move(side,anchor,guard,tolerance=.005)
    anchor=np.asarray(policy.tip(side),float).copy()
    policy.stage('orient-driver-at-actual-head')
    history=[];rotation_loss_degrees=0.;last_rotation_token=None
    def clear_space():
        state,contacts=policy.snapshot()
        obj=next(o for o in policy.spec['objects'] if o['id']==actor)
        body=state[actor]
        tool_bottom=float(body['pos'][2]-(np.abs(body['mat'])@np.asarray(obj['size'],float))[2])
        finger_bottom=float(policy.a.finger_geometry(side)['lowest_z_task_m'])
        floor=float(head()[2])+.010
        if tool_bottom<floor or finger_bottom<floor or frozenset((actor,'table')) in contacts:
            raise ToolExecutionError('E37 actual tool/fingers lost clear space during head orientation')
        return dict(tool_bottom=tool_bottom,finger_bottom=finger_bottom,obstacle_floor=floor)
    def restore_clearance():
        nonlocal last_rotation_token
        # A long driver descends while the wrist rotates. Raise from measured
        # tool/finger geometry before the next rotation; no fixed TCP anchor.
        measured=clear_space();lowest=min(measured['tool_bottom'],measured['finger_bottom'])
        if lowest>=measured['obstacle_floor']+.020:return
        # A translation preserves an unfinished orientation promise. Before
        # lifting, explicitly request a small real rotation near the achieved
        # pose; never overwrite the controller quaternion behind its API.
        if last_rotation_token is not None:
            policy.act(side,last_rotation_token,degrees=1.);guard();last_rotation_token=None
        for _ in range(12):
            measured=clear_space();lowest=min(measured['tool_bottom'],measured['finger_bottom'])
            missing=measured['obstacle_floor']+.032-lowest
            if missing<=.001:return
            policy.act(side,'UP',mm=min(12.,max(5.,1000*missing)));guard()
        raise ToolExecutionError('E37 real tool clearance did not recover before rotation')
    # The measured extended-arm pose can make safe fractional progress even
    # while the requested endpoint is rejected. Continue only with actual
    # angular improvement; the old120-command bound cut off a real rotation.
    for index in range(300):
        restore_clearance()
        guard();state,_=policy.snapshot();current=np.asarray(state[actor]['mat'],float)
        if policy.contact(actor,'table'):
            raise ToolExecutionError('E37 driver contacted table during clear-space head alignment')
        # Actual blade broad axis is local Z; actual screw slot runs along its
        # declared radial axis. Its two signs represent the same slot plane.
        slot=np.asarray(state[entry['screw']]['mat'])@np.asarray(entry['radial_local'],float)
        slot-=axis*float(slot@axis);slot/=np.linalg.norm(slot)
        if float(slot@current[:,2])<0:slot=-slot
        x=-axis;y=np.cross(slot,x);y/=np.linalg.norm(y)
        desired=np.column_stack((x,y,np.cross(x,y)))
        delta=desired@current.T
        angle=float(np.arccos(np.clip((np.trace(delta)-1)/2,-1,1)))
        history.append(dict(step=policy.c.steps,error_degrees=math.degrees(angle),tcp=np.asarray(policy.tip(side)).tolist(),**clear_space()))
        with (policy.a.out/'E37-head-orientation.private.json').open('w') as stream:
            json.dump(dict(initial_anchor=anchor.tolist(),history=history,public_actions_only=True,fixed_tcp_anchor_required=False),stream,indent=2)
        if angle<=math.radians(.5):
            # A physically reached orientation can still retain the previous
            # unfinished8-degree controller promise. Use the smallest explicit
            # public rotation toward the remaining measured error before a
            # later translation, then recheck the actual source alignment.
            if angle>1e-7:
                tiny_axis=np.array([delta[2,1]-delta[1,2],delta[0,2]-delta[2,0],delta[1,0]-delta[0,1]])/(2*math.sin(angle))
                tiny_component=int(np.argmax(abs(tiny_axis)))
                tiny_token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[tiny_component][int(tiny_axis[tiny_component]<0)]
            else:tiny_token='ROTATE_CCW'
            policy.act(side,tiny_token,degrees=.5);guard();clear_space()
            final=np.asarray(policy.snapshot()[0][actor]['mat'])
            final_error=float(np.arccos(np.clip((np.trace(desired@final.T)-1)/2,-1,1)))
            history[-1].update(final_public_rotation_degrees=.5,final_actual_error_degrees=math.degrees(final_error))
            with (policy.a.out/'E37-head-orientation.private.json').open('w')as stream:
                json.dump(dict(initial_anchor=anchor.tolist(),history=history,public_actions_only=True,fixed_tcp_anchor_required=False),stream,indent=2)
            if final_error<=math.radians(.5)+1e-7:return
            continue
        if math.pi-angle<.01:
            values,vectors=np.linalg.eigh((delta+np.eye(3))/2);turn=vectors[:,np.argmax(values)]
        else:turn=np.array([delta[2,1]-delta[1,2],delta[0,2]-delta[2,0],delta[1,0]-delta[0,1]])/(2*math.sin(angle))
        component=int(np.argmax(abs(turn)))
        token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[component][int(turn[component]<0)]
        # Public orientation tracking has a finite settling tolerance. Learn
        # the actual shortfall from the achieved tool rotation rather than
        # issuing progressively smaller commands inside that dead band.
        requested=command_degrees(angle*turn[component],rotation_loss_degrees)
        policy.act(side,token,degrees=requested)
        last_rotation_token=token
        guard()
        updated_loss,actual_degrees=update_loss(current,policy.snapshot()[0][actor]['mat'],
            component,turn[component],requested,rotation_loss_degrees)
        raw_feedback=(policy.c.action_feedback()
            if callable(getattr(policy.c,'action_feedback',None))else {})
        feedback=raw_feedback.get('control_feedback',raw_feedback).get(side,{})
        # A constrained IK route is not an angular settling dead band. Retain
        # its measured progress but never learn compensation from a refusal.
        if feedback.get('status')!='blocked' and not feedback.get('joint_limit_names'):
            rotation_loss_degrees=updated_loss
        history[-1].update(requested_rotation_degrees=requested,
            achieved_component_degrees=actual_degrees,estimated_rotation_loss_degrees=rotation_loss_degrees,
            actual_controller_status=feedback.get('status'),actual_controller_reason=feedback.get('reason'))
        # Public wrist rotation has real translational drift. There is no
        # source requirement to restore an arbitrary clear-space TCP anchor.
        # Guard actual geometry instead; final material tip alignment remains
        # independently measured at the unchanged 0.5mm engagement tolerance.
        clear_space()
        if len(history)>=20 and history[-20]['error_degrees']-min(r['error_degrees']for r in history[-5:])<1.:
            raise ToolExecutionError('E37 actual blade orientation stalled above head')
    raise ToolExecutionError('E37 blade orientation action bound exhausted')
