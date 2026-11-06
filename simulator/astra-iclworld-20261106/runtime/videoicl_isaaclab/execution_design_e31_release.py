"""Private E31 plate placement using real material geometry and public actions.

A short ordinary gravity drop is only an author stop condition. Actual release,
plate/bowl contact, stability, face and coverage remain native physics checks.
"""
import json
import numpy as np
from .execution_design import REVISION_V3
from .execution_design_e31_orientation import requested_face


def release_ready(*,gap_m,covered,plate_face_ok,bowl_up,held,hand_on_bowl,plate_bowl_contact=False,maximum_gap_m=.030):
    if not np.isfinite(gap_m):raise ValueError('Finite measured material gap required')
    if not np.isfinite(maximum_gap_m)or not .030<=maximum_gap_m<=.080:
        raise ValueError('Bounded 30..80mm engineering gravity drop required')
    return bool(covered and plate_face_ok and bowl_up and held and not hand_on_bowl
                and (plate_bowl_contact or 0.<=gap_m<=maximum_gap_m))


class _View:
    def __init__(self,a):self.a=a
    def frame(self,ref):
        b=self.a.c.snapshot()[0][ref['actor']]
        return np.asarray(b['pos']),np.asarray(b['mat'])


def check_actual_limits(a,side):
    """Fresh reconstruction has no previous public-action feedback yet."""
    robot=a.scene.robots[side];arm=a.c.ids[side][0]
    def array(value):return np.asarray(value.detach().cpu().numpy()if hasattr(value,'detach')else value,float)
    q=array(robot.data.joint_pos[0,arm]);limits=array(robot.data.joint_pos_limits[0,arm])
    if np.min(np.minimum(q-limits[:,0],limits[:,1]-q))<.002:
        raise RuntimeError('E31 final lowering is at an actual joint limit')
    if getattr(a.c,'_public_action',None) is not None:
        feedback=a.c.action_feedback()['control_feedback'][side]
        if feedback.get('joint_limit_names'):
            raise RuntimeError('E31 final lowering has actual joint-limit feedback')


def lower_for_release(a,name,side,goal,*,maximum_drop_gap_m=None,require_bowl_contact=False,centering_offset_xy=(0.,0.)):
    spec=a.scene.spec;semantic=spec['semantic']
    if not(getattr(a,'_execution_design_reference_authorized',False)
           and spec['id']=='E31' and spec.get('execution_design',{}).get('revision')==REVISION_V3
           and name==semantic['plate'] and side in ('left','right')):
        raise ValueError('Explicit E31 plate reference placement required')
    from .execution_design_thin_edge import material_collision_points_task
    bowl=semantic['bowl'];objects={o['id']:o for o in spec['objects']};index=0 if side=='left'else 1
    face=requested_face(semantic,'plate',goal);face_sign=1. if face=='up'else-1.
    # A down-facing lid may be dropped normally from a modest clearance.
    # This private author stop is never evidence of final contact or success.
    drop_limit=(.080 if face=='down'else.030)if maximum_drop_gap_m is None else float(maximum_drop_gap_m)
    centering_offset=np.asarray(centering_offset_xy,float)
    if centering_offset.shape!=(2,)or not np.isfinite(centering_offset).all()or np.max(abs(centering_offset))>.025:
        raise ValueError('Bounded actual cover placement offset required')
    if not np.isfinite(drop_limit)or not .030<=drop_limit<=.080 or(face!='down'and drop_limit>.030):
        raise ValueError('Only an actual down-face goal may use the bounded 80mm gravity drop')
    state,_=a.c.snapshot();local={}
    for actor in (name,bowl):
        points=material_collision_points_task(_View(a),{'actor':actor})
        body=state[actor];local[actor]=(points-np.asarray(body['pos']))@np.asarray(body['mat'])
    labels=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))
    signs=getattr(a,'generated_axis_signs',{}).get(side,{0:1,1:1,2:1})
    def act_axis(axis,distance):
        token=labels[axis][0 if np.sign(distance)==signs.get(axis,1)else 1]
        mm=float(min(8.,max(.5,abs(distance)*1000)))
        a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',mm)
    history=[]
    for _ in range(100):
        state,contacts=a.c.snapshot();body=state[name];support=state[bowl]
        held=a.carried_payload==(name,side) and bool(body['grasp'][index])
        bilateral=all(frozenset((name,side+'_finger'+str(i)))in contacts for i in (1,2))
        if not held or not bilateral:raise RuntimeError('E31 final lowering lost actual bilateral plate grip')
        hand=any(frozenset((bowl,s+'_finger'+str(i)))in contacts for s in ('left','right')for i in (1,2))
        if hand:raise RuntimeError('E31 final lowering hand contacts receiving bowl')
        pp=local[name]@np.asarray(body['mat']).T+body['pos'];bp=local[bowl]@np.asarray(support['mat']).T+support['pos']
        gap=float(pp[:,2].min()-bp[:,2].max())
        pc=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(objects[name].get('local_bounds_center',[0,0,0]))
        bc=np.asarray(support['pos'])+np.asarray(support['mat'])@np.asarray(objects[bowl].get('local_bounds_center',[0,0,0]))
        ph=abs(np.asarray(body['mat']))@np.asarray(objects[name]['size']);bh=abs(np.asarray(support['mat']))@np.asarray(objects[bowl]['size'])
        covered=bool(np.all(abs(pc[:2]-bc[:2])+bh[:2]<=ph[:2]+.005)and pc[2]>bc[2])
        plate_face=face_sign*float((np.asarray(body['mat'])@np.asarray(objects[name].get('up_axis',[0,0,1])))[2])>.85
        bowl_up=float((np.asarray(support['mat'])@np.asarray(objects[bowl].get('up_axis',[0,0,1])))[2])>.85
        check_actual_limits(a,side)
        xy=bc[:2]+centering_offset-pc[:2]
        ready=release_ready(gap_m=gap,covered=covered,plate_face_ok=plate_face,bowl_up=bowl_up,held=held,hand_on_bowl=hand,plate_bowl_contact=frozenset((name,bowl))in contacts,maximum_gap_m=drop_limit)
        if require_bowl_contact:ready=ready and frozenset((name,bowl))in contacts
        row=dict(step=a.c.steps,plate=name,bowl=bowl,material_gap_m=gap,actual_plate_center=pc.tolist(),actual_bowl_center=bc.tolist(),covered=covered,plate_face_ok=plate_face,bowl_up=bowl_up,real_bilateral_grasp=True,hand_on_bowl=hand,release_ready=ready,author_drop_limit_m=drop_limit,require_real_bowl_contact=bool(require_bowl_contact),native_success_claimed=False)
        with(a.out/'e31-material-release.private.jsonl').open('a')as stream:stream.write(json.dumps(row)+'\n')
        # Centre to a coarse physical margin before releasing, rather than
        # demanding submillimetre agreement with a frozen TCP offset.
        if np.max(abs(xy))>.012:
            axis=int(np.argmax(abs(xy)));act_axis(axis,float(xy[axis]));continue
        if ready:return row
        if not plate_face or not bowl_up:raise RuntimeError('E31 material placement face is not physically compliant')
        if gap<0. and not require_bowl_contact:raise RuntimeError('E31 material gap crossed support without real contact')
        history.append(gap)
        if len(history)>=12 and min(history[-12:-8])-min(history[-4:])<.001:
            raise RuntimeError('E31 actual material lowering stalled above gravity-release range')
        act_axis(2,-min(.008,max(.0005,gap-(0. if require_bowl_contact else .020))))
    raise RuntimeError('E31 measured material placement action bound exhausted')
