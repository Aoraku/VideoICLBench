"""Engineering segment tails; local completion never represents task scoring."""
from copy import deepcopy
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .author_orientation import _rotation


def _scope(a,task,variant):
    s=a.scene.spec;d=s.get('execution_design',{})
    if (s.get('id')!=task or s.get('variant')!=variant or d.get('revision')!=REVISION_V3
            or d.get('source_sha256')!=source_sha256(REVISION_V3)
            or not getattr(a,'_execution_design_reference_authorized',False)
            or not a.control_report.get('engineering_reference_only')
            or a.scene.embodiment.name!='franka'or a.smooth):
        raise ValueError('Explicit pinned v3 Panda engineering segment required')


def _finite(x,shape):
    x=np.asarray(x,float)
    if x.shape!=shape or not np.isfinite(x).all():raise ValueError('Finite segment context required')
    return x


def _empty(a):
    state,contacts=a.c.snapshot()
    if getattr(a,'carried_payload',None)is not None or any(any(b.get('grasp',[]))for b in state.values()):
        raise RuntimeError('Actual empty hands and released objects required')
    return state,contacts


def _pose(state,name,p):
    expected=p['expected_source_pose'];pos=_finite(expected['pos'],(3,));r=_rotation(expected['mat'],'checkpoint source')
    if np.linalg.norm(np.asarray(state[name]['pos'])-pos)>.002 or np.linalg.norm(np.asarray(state[name]['mat'])-r)>.02:
        raise RuntimeError('Actual source differs from measured checkpoint context')


def approach_e25_piece(a,side,xy,center_z,approach_z,tolerance):
    """Identical original generated approach, shared with the full E25 route."""
    if a.scene.spec.get('id')!='E25':raise ValueError('E25 approach only')
    xy=_finite(xy,(2,))
    if not np.isfinite([center_z,approach_z,tolerance]).all():raise ValueError('Finite approach required')
    a.move_generated({side:[*a.tip(side)[:2],approach_z]})
    a.move_generated({side:[*xy,approach_z]})
    a.move_generated({side:[*xy,center_z+.045]})
    a.prepare_generated_gripper(side)
    a.move_generated({side:[*xy,center_z]},tolerance=tolerance)


def _acquire(a,variant,name,p):
    _scope(a,'E25',variant)
    from .execution_design_e25_reference import grasp_spec,prepare_source_palm
    from .execution_design_e25_parking import source_pickup_spec
    from .execution_design_e07_reference import verify_relay_release
    source_fork=variant=='C'and name=='fork'
    side='right'if variant=='B'or source_fork else'left'
    if p['side']!=side:raise ValueError('Explicit reviewed acquisition hand required')
    state,contacts=_empty(a);_pose(state,name,p)
    if frozenset((name,'table'))not in contacts:raise RuntimeError('Actual source table support required')
    goal=deepcopy(p['goal'])
    if goal.get('object')!=name:raise ValueError('Original actor goal required')
    if variant=='B':
        if goal.get('_e07_relay_phase')!='place_on_table'or'_e07_after_relay'in goal:raise ValueError('Source relay context required')
    elif source_fork:
        original=next(g for g in a.scene.spec['goals']if g['object']=='fork')
        if ('_e07_after_relay'in goal or any(goal.get(k)!=original.get(k)for k in ('target','yaw'))):
            raise ValueError('Original direct C fork acquisition goal required')
    else:
        if '_e07_after_relay'not in goal:raise ValueError('C receiver relay context required')
        verify_relay_release(a,goal)
    obj=next(o for o in a.scene.spec['objects']if o['id']==name);spec=grasp_spec(a,obj)
    if variant=='B':spec=source_pickup_spec(a,spec,goal)
    a.align_gripper_axis(side,np.asarray(state[name]['mat'])@np.asarray(spec['grasp_axis_local']))
    prepare_source_palm(a,side,name,goal)
    state,_=_empty(a);_pose(state,name,p)
    point=np.asarray(state[name]['pos'])+np.asarray(state[name]['mat'])@np.asarray(spec.get('grasp_point_local',[0,0,0]))
    z=max(float(point[2]),float(a.floor_clear_tcp(side)));height=float(p['approach_z'])
    if not np.isfinite(height)or height<z+.045:raise ValueError('Original measured approach clearance required')
    a.stage='segment-e25-acquire-'+name
    approach_e25_piece(a,side,point[:2],z,height,min(.0035,max(.0008,min(spec['size'])*.2)))
    for _ in range(3):a.act('GRASP'if side=='left'else'STILL','GRASP'if side=='right'else'STILL')
    def held():
        state,contacts=a.c.snapshot()
        if not state[name]['grasp'][('left','right').index(side)]or not all(frozenset((name,side+'_finger'+str(i)))in contacts for i in (1,2)):
            raise RuntimeError('Actual bilateral segment grip absent')
    held();a.carried_payload=(name,side);a.act('STILL','STILL',20.);held()
    return [dict(operation='actual_source_acquisition',actor=name,side=side)]


def run_segment(author,segment,parameters):
    """Checkpoint restoration is external; any local failure raises immediately."""
    a=author;p=parameters;before=a.c.steps
    if segment=='e19_c_reacquire_red_water':
        _scope(a,'E19','C')
        from .execution_design_e19_reacquire import run
        operations=run(a,p)
    elif segment=='e19_release_red_water':
        _scope(a,'E19','C')
        from .realworld_structural_expert import StructuralAuthor
        from .execution_design_e19_reference import gravity_seat_red_water
        t=StructuralAuthor(a);ref=deepcopy(p['ref']);control=deepcopy(p['control'])
        if p['side']!='left'or ref.get('actor')!='cap_red'or control.get('actor')!='cap_red':raise ValueError('Reviewed actual held red cap required')
        _finite(ref['local'],(3,));jaw=_finite(ref['jaw_axis_local'],(3,))
        if np.linalg.norm(jaw)<1e-8:raise ValueError('Nonzero actual source jaw axis required')
        if not np.allclose(_finite(control['local'],(3,)),t.s['caps']['cap_red']['center_local'],atol=1e-10,rtol=0):raise ValueError('Original cap opening point required')
        t.start=int(p['policy_start']);t.limit=int(p['policy_limit'])
        if t.start<0 or t.start>before or not 1<=t.limit<=3000 or before-t.start>=t.limit:raise ValueError('Original policy budget context required')
        state,contacts=t.snapshot();_pose(state,'water_bottle',p)
        if (not state['cap_red'].get('grasp',[False,False])[0]
                or not all(frozenset(('cap_red','left_finger'+str(i)))in contacts for i in (1,2))
                or any(b.get('grasp',[False,False])[1]or(n!='cap_red'and b.get('grasp',[False,False])[0])for n,b in state.items())):
            raise RuntimeError('Actual bilateral red-cap hold and empty peer hand required')
        t.require_held(ref,'left')
        opening=t.point(control);mouth=t.body_point({'actor':'water_bottle'},t.s['mouths']['water_bottle']['center_local'])
        phase=p.get('entry_phase','rim_release')
        if phase not in ('alignment','rim_release'):raise ValueError('Reviewed release entry phase required')
        if np.max(abs(opening[:2]-mouth[:2]))>.01 or opening[2]<mouth[2]+(.012 if phase=='alignment'else .003):raise RuntimeError('Actual held cap is outside near-mouth entry')
        gravity_seat_red_water(t,'cap_red',ref,'left',control,'water_bottle',entry_phase=phase);operations=list(t.operations)
    elif segment=='e25_a_place_settled_relay_knife':
        _scope(a,'E25','A')
        from .execution_design_e25_a_receiver import place_settled_knife
        operations=place_settled_knife(a,p)
    elif segment=='e25_a_place_held_knife_from73':
        _scope(a,'E25','A')
        from .execution_design_e25_a_receiver import continue_held_knife
        operations=continue_held_knife(a,p)
    elif segment=='e25_a_place_held_knife_from21':
        _scope(a,'E25','A')
        from .execution_design_e25_a_receiver import continue_held_knife
        operations=continue_held_knife(a,p,source_boundary=(21,2111))
    elif segment=='e25_empty_return_a':
        _scope(a,'E25','A');_empty(a)
        from .execution_design_generated_route import park_before_hand_switch
        home={s:_finite(p['home_xy'][s],(2,)).tolist()for s in ('left','right')}
        rotations={s:_rotation(p['home_rotations'][s],'checkpoint home').copy()for s in ('left','right')}
        old=getattr(a,'_e25_home_rotations',None)
        if old is not None and any(not np.allclose(old[s],rotations[s],atol=1e-10,rtol=0)for s in rotations):raise ValueError('Home context differs from restored policy')
        if old is None:a._e25_home_rotations=rotations
        clearance=float(p['clearance'])
        if not np.isfinite(clearance)or not .84<=clearance<=1.3:raise ValueError('Original measured return clearance required')
        park_before_hand_switch(a,'left','right',home,clearance);_empty(a)
        if np.max(abs(a.tip('left')-np.r_[home['left'],clearance]))>.004:raise RuntimeError('Actual home return did not converge')
        operations=[dict(operation='released_empty_return',side='left')]
    elif segment=='e25_source_spoon_b':operations=_acquire(a,'B','spoon',p)
    elif segment=='e25_source_fork_c':
        clearance=float(p['clearance'])
        if not np.isfinite(clearance)or not .84<=clearance<=1.3:raise ValueError('Original measured lift clearance required')
        operations=_acquire(a,'C','fork',p)
        a.stage='grasped-fork';a.move_generated({'right':[*a.tip('right')[:2],clearance]})
        state,contacts=a.c.snapshot()
        if (not state['fork'].get('grasp',[False,False])[1]
                or not all(frozenset(('fork','right_finger'+str(i)))in contacts for i in (1,2))
                or float(state['fork']['pos'][2])<float(p['expected_source_pose']['pos'][2])+.02):
            raise RuntimeError('Actual fork lift lacks bilateral grip or 20mm source clearance')
        operations.append(dict(operation='actual_held_source_lift',actor='fork',side='right'))
    elif segment=='e25_b_winding_transport':
        _scope(a,'E25','B')
        from .execution_design_e25_b_transport import rotate_transport_payload
        if p.get('side','left')!='left'or p.get('object','spoon')!='spoon':raise ValueError('Reviewed actual left spoon receiver required')
        state,contacts=a.c.snapshot()
        if not state['spoon'].get('grasp',[False,False])[0]or not all(frozenset(('spoon','left_finger'+str(i)))in contacts for i in (1,2)):
            raise RuntimeError('Actual bilateral spoon receiver hold required')
        carried=getattr(a,'carried_payload',None)
        if carried not in (None,('spoon','left')):raise RuntimeError('Restored policy payload differs from actual spoon hold')
        a.carried_payload=('spoon','left')
        # The checkpoint gate already checked source identity, physical drift
        # and real contacts. Replan from the achieved held pose; a second old
        # pose match must not reject an admitted 2mm/2deg restoration.
        goal=deepcopy(p.get('goal',next(g for g in a.scene.spec['goals']if g['object']=='spoon')))
        goal.setdefault('_e07_after_relay',{})
        rotate_transport_payload(a,'spoon','left',goal)
        operations=[dict(operation='actual_held_winding_transport',actor='spoon',side='left')]
    elif segment=='e25_b_release_spoon_from187':
        from .execution_design_e25_b_release import run
        operations=run(a,p)
    elif segment=='e25_c_relay_knife_from404':
        from .execution_design_e25_c_relay import run
        operations=run(a,p)
    elif segment=='e25_c_release_knife_from209':
        from .execution_design_e25_c_release import run
        operations=run(a,p)
    elif segment=='e25_relay_knife_c':operations=_acquire(a,'C','knife',p)
    else:raise ValueError('Unknown reviewed E19/E25 segment')
    return dict(local_completed=True,operations=operations,active_actions=a.c.steps-before)
