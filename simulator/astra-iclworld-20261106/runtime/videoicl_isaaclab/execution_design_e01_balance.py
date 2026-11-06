"""E01 loaded tray: a robot-near right rim balances the existing left hold."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation
from .author_orientation import _axis_angle


def _coarse(p):
    import os
    return bool(p.a.control_report.get('engineering_reference_only')and os.environ.get('VIC_ENGINEERING_FUNCTIONAL_ACCEPTANCE')=='1')


def _geometry(p,*,target=None,rotation=None):
    if _coarse(p):return
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_branch_geometry import collision_parts_task,swept_pose_clearance
    from .execution_design_thin_edge import table_bounds_task
    bounds=table_bounds_task(p.a.scene);thickness=float(p.a.scene.embodiment.config['layout']['table']['size'][2])
    table=np.array([[x,y,z]for x in(bounds['lower'][0],bounds['upper'][0])
        for y in(bounds['lower'][1],bounds['upper'][1])for z in(bounds['top']-thickness,bounds['top'])])
    obstacles={name:collision_parts_task(p,name)for name in('meal_box','meal_box_lid')}
    obstacles['finite_table']=[table]
    names=('panda_link3','panda_link4','panda_link5','panda_link6','panda_link7','panda_hand',*p.a.scene.embodiment.fingers)
    for name in names:obstacles['left_'+name]=[actual_mesh(p.a,'left',name)]
    tip=p.tip('right');bodies={name:actual_mesh(p.a,'right',name)for name in names}
    # Arm links follow their actual readback.  Only the rigid hand may use a
    # TCP-frame proposal; rotating arm meshes about the TCP would be fictitious.
    swept_pose_clearance(bodies,tip,tip,np.eye(3),obstacles,bounds['top']-10.,margin=.0003)
    hand={name:bodies[name]for name in('panda_hand',*p.a.scene.embodiment.fingers)}
    obstacles.update({name:collision_parts_task(p,name)for name in p.d['target_members']})
    swept_pose_clearance(hand,tip,tip if target is None else target,
        np.eye(3)if rotation is None else rotation,obstacles,bounds['top']-10.,margin=.0003)
    # Intentional opposing rim contact is allowed for the pads, never the palm.
    swept_pose_clearance({'panda_hand':hand['panda_hand']},tip,tip if target is None else target,
        np.eye(3)if rotation is None else rotation,{'tray':collision_parts_task(p,'tray')},
        bounds['top']-10.,margin=.0003)


def _physical_support(p):
    from .execution_design_e01_package import _meal_on_tray
    p.require_held({'actor':'tray'},'left');_meal_on_tray(p)
    if not p.contact('meal_box','table')and(not _coarse(p)or p.frame({'actor':'meal_box'})[0][2]<.8):
        raise ToolExecutionError('E01 original loading carton lost actual table support')


def _rotate(p,state,goal):
    tokens=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    while True:
        if state.get('pending'):
            feedback=p.c.action_feedback()['control_feedback']['right']
            before=float(feedback['orientation_error_rad']);tolerance=float(feedback.get('orientation_tolerance_rad',.05))
            if before>tolerance:
                p.act('right','STILL');_physical_support(p);_geometry(p)
                after=float(p.c.action_feedback()['control_feedback']['right']['orientation_error_rad'])
                state['no_progress']=state.get('no_progress',0)+1 if after>=before-.0005 else 0
                if state['no_progress']>=3:raise ToolExecutionError('E01 accepted empty right rotation has no actual progress')
                continue
            state['pending']=False
        axis,angle=_axis_angle(goal@np.asarray(p.a.tcp_rotation_task('right')).T)
        tolerance=float(p.c.action_feedback()['control_feedback']['right'].get('orientation_tolerance_rad',.05))
        actual=np.asarray(p.a.tcp_rotation_task('right'));tray=p.frame({'actor':'tray'})[1];local=tray.T@actual
        forward=float(local[0,2])*(-1 if state.get('coarse_far_rim')else 1)
        if _coarse(p)and state.get('coarse_end_rim'):
            if abs(local[0,1])>.95 and local[1,2]>.5 and local[2,2]<-.2:return
        elif _coarse(p)and abs(local[1,1])>.95 and forward>.5 and local[2,2]<-.2:return
        if angle<=max(math.radians(1.5),math.sqrt(3)*tolerance):return
        i=int(np.argmax(abs(axis)));degrees=min(10.,max(.5,abs(math.degrees(angle*axis[i]))))
        signed=degrees*(1 if axis[i]>=0 else-1)
        _geometry(p,rotation=_axis_rotation(np.eye(3)[i],math.radians(signed)))
        state.update(pending=True,no_progress=0)
        p.act('right',tokens[i][int(axis[i]<0)],degrees=degrees);_physical_support(p);_geometry(p)


def acquire_right_balance(p):
    if p.task!='E01'or not p.a.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('E01 independent physical balance reference required')
    if p.objects['tray'].get('source_asset',{}).get('sha256')!='f3de40e9b8aeabc426e1f7056d596d9e01baaf8cb961274d7405b459349fa56c':
        raise ToolExecutionError('E01 original cooked rim source required')
    state=getattr(p,'_e01_balance_progress',None)
    if state is None:
        state=dict(phase='wake',local=[-.075,-.148421757616071,.008],pending=False)
        p._e01_balance_progress=state
    if _coarse(p)and not state.get('coarse_end_rim'):
        # The original X-end rim keeps this wrist in front of the tray.  The
        # negative-Y wall approach met the neighbouring original carton/lid.
        state.update(local=[.1002265351110735,0.,.011578460015396315],phase='stage-x',
                     pending=False,no_progress=0,coarse_far_rim=True,coarse_end_rim=True,
                     coarse_unfold_done=True,box_gap_pushed=True)
        p.act('right','PITCH_UP',degrees=2.)
    ref=dict(actor='tray',local=state['local'],jaw_axis_local=[1,0,0]if state.get('coarse_end_rim')else[0,1,0])
    if state['phase']=='wake':
        # Leave the failed empty BACK intention with an intended positive move.
        p.stage('loaded-tray-near-right-contact-rebuild');p.act('right','FWD',mm=1.)
        _physical_support(p);_geometry(p);state['phase']='stage-x'
    def guard():_physical_support(p);_geometry(p)
    for phase,next_phase in(('stage-x','stage-y'),('stage-y','stage-z'),('stage-z','rotate')):
        if state['phase']!=phase:continue
        if _coarse(p)and phase=='stage-x'and p.tip('right')[2]<1.17:
            p.move('right',np.r_[p.tip('right')[:2],1.18],guard,tolerance=.008)
        p.stage('loaded-tray-near-right-'+phase);point=p.tip('right').copy()
        values={'stage-x':-.25,'stage-y':-.25,'stage-z':1.18}if _coarse(p)else{'stage-x':-.35,'stage-y':-.15,'stage-z':1.04}
        point[{'stage-x':0,'stage-y':1,'stage-z':2}[phase]]=values[phase]
        p.move('right',point,guard);state['phase']=next_phase
    if state['phase']=='rotate':
        if _coarse(p)and not state.get('coarse_unfold_done'):
            p.stage('loaded-tray-empty-unfold-from-measured-pose')
            p.act('right','PITCH_UP',degrees=2.);state.update(pending=False,no_progress=0)
            p.act('right','FWD',mm=50.);guard()
            p.move('right',np.r_[p.tip('right')[:2],1.18],guard,tolerance=.008)
            p.move('right',[-.25,-.25,1.18],guard,tolerance=.008)
            state['coarse_unfold_done']=True
        if float(p.tip('right')[2])<1.038:
            p.stage('loaded-tray-near-right-raise-before-rotation')
            p.move('right',np.r_[p.tip('right')[:2],1.04],guard)
        if not state.get('table_gap_shift_done'):
            # The open outer finger needs room beside the nearby original box.
            # A short, physically supported tray slide creates that gap without
            # moving actors at reset or asking the loaded hand to hold a moment.
            p.stage('loaded-tray-supported-box-gap-shift')
            goal=state.setdefault('table_gap_target_y',float(p.frame({'actor':'tray'})[0][1])+.015)
            stalled=0
            while goal-float(p.frame({'actor':'tray'})[0][1])>.002:
                before=float(p.frame({'actor':'tray'})[0][1]);guard()
                p.act('left','LEFT',mm=min(5.,max(2.5,(goal-before)*1000)));guard()
                after=float(p.frame({'actor':'tray'})[0][1])
                stalled=stalled+1 if after-before<.0003 else 0
                if stalled>=3:raise ToolExecutionError('E01 supported tray gap shift has no actual progress')
            state['table_gap_shift_done']=True
        p.stage('loaded-tray-near-right-angled-empty-hand')
        _,r=p.frame(ref);tilt=135 if state.get('coarse_far_rim')else 45
        relative=_axis_rotation([0,1,0],math.radians(tilt))@np.array([[0,0,1],[0,1,0],[-1,0,0]])
        if state.get('coarse_end_rim'):
            z=math.sqrt(.5);relative=np.array([[0,1,0],[z,0,z],[z,0,-z]])
        _rotate(p,state,r@relative);state['phase']='above'
    if state['phase']=='above':
        if _coarse(p)and not state.get('box_gap_pushed'):
            p.stage('functional-original-carton-supported-gap-push')
            # The measured empty right palm already meets the near wall.
            # Slide that real empty carton outward before descending to the
            # tray; lifting against the wall had tipped it toward the wrist.
            stale=0
            while float(p.frame({'actor':'meal_box'})[0][1])>-.415:
                before=float(p.frame({'actor':'meal_box'})[0][1])
                p.act('right','RIGHT',mm=50.);_physical_support(p)
                after=float(p.frame({'actor':'meal_box'})[0][1])
                stale=stale+1 if before-after<.002 else 0
                if stale>=3:raise ToolExecutionError('E01 empty carton gap push has no actual progress')
            p.move('right',p.tip('right')+[0,0,.12],guard,tolerance=.008)
            state['box_gap_pushed']=True
        p.stage('loaded-tray-near-right-over-rim');target=p.point(ref).copy();target[2]=.92
        p.move('right',target,guard,tolerance=.008 if _coarse(p)else .002);state['phase']='lower'
    if state['phase']=='lower':
        p.stage('loaded-tray-near-right-descend')
        p.move('right',p.point(ref),guard,tolerance=.006 if _coarse(p)else .0015);state['phase']='grasp'
    if state['phase']=='grasp':
        p.stage('loaded-tray-near-right-real-grasp')
        for _ in range(5):
            p.act('right','GRASP');guard()
            if p.held(ref,'right'):break
        else:raise ToolExecutionError('E01 near original right rim lacks actual bilateral hold')
        state['phase']='complete'
    p.require_held(ref,'right');p.require_held({'actor':'tray'},'left')
    p.a.control_report['e01_loaded_right_balance']=dict(original_rim_local=state['local'],
        measured_right_held=True,measured_left_held=True,
        empty_hand_tilt_degrees=45. if state.get('coarse_end_rim')else 135. if state.get('coarse_far_rim')else 45.,
        original_x_end_rim=bool(state.get('coarse_end_rim')),source_geometry_changed=False)
    return dict(local_completed=True,actual_dual_hold=True,whole_task_score=None)


def complete_balanced_load(p):
    if _coarse(p):p.max_mm=float(p.a.scene.embodiment.config['control']['step_mm'][1])
    if _coarse(p)and p.held({'actor':'tray'},'left')and p.held({'actor':'tray'},'right'):
        return coarse_load(p)
    state=getattr(p,'_e01_balance_progress',{})
    if _coarse(p)and state.get('phase')=='complete'and any(p.snapshot()[0]['tray']['grasp']):
        if not p.held({'actor':'tray'},'right')and p.held({'actor':'tray'},'left'):
            ref=dict(actor='tray',local=state['local'])
            p.stage('functional-right-rim-contact-rebuild')
            p.move('right',p.point(ref),lambda:p.require_held({'actor':'tray'},'left'),tolerance=.006)
            p.act('right','GRASP')
        return coarse_load(p)
    acquire_right_balance(p)
    if _coarse(p):return coarse_load(p)
    from .execution_design_e01_package import load_meal_tray
    return load_meal_tray(p)


def coarse_load(p):
    from .execution_design_e01_package import _state,_meal_on_tray
    state=_state(p);control=dict(actor='tray',local=p.bottom_local('tray').tolist())
    base,r=p.frame({'actor':'meal_box'});box=p.objects['meal_box']
    rim=float((base+r@np.asarray(box.get('local_bounds_center',[0,0,0])))[2]+abs(r[2])@np.asarray(box['size']))
    point=p.point(control);high=rim+.10
    def guard():
        if not any(p.snapshot()[0]['tray']['grasp']):raise ToolExecutionError('E01 carried tray has no actual held hand')
        _meal_on_tray(p)
    # The new X-end wrist is reachable vertically; the earlier low forward
    # detour was only needed by the discarded rear-wall hand pose.
    for label,target in [('lift',np.array([point[0],point[1],high])),
                         ('over-box-front',np.array([point[0],base[1]+.04,high])),
                         ('align-box-x',np.array([base[0]+.01,base[1]+.04,high]))]:
        p.stage('functional-loaded-tray-'+label)
        while max(abs(target-p.point(control)))>.012:
            guard();error=target-p.point(control);axis=int(np.argmax(abs(error)))
            token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
            held=p.snapshot()[0]['tray']['grasp'];side='left'if held[0]else'right';other='right'if side=='left'else'left'
            p.act(side,token,mm=min(20.,abs(float(error[axis]))*1000),follower=other)
    guard();p.stage('functional-release-hinge-side-while-finishing-carry')
    # The hinge-side open finger cannot fit next to the upright lid. Open it
    # while the opposite real hand performs the final short public translation.
    if p.c.steps-p.start>=p.limit:raise ToolExecutionError('E01 functional action budget exhausted')
    held=p.snapshot()[0]['tray']['grasp'];side='left'if held[0]else'right';other='right'if side=='left'else'left'
    p.a.act(**{side:'RIGHT',other:'RELEASE'},mm=50.,rotation_deg=5.)
    p.require_held({'actor':'tray'},side);_meal_on_tray(p)
    p.stage('functional-tray-real-gravity-release')
    p.a.act(**{side:'RELEASE',other:'UP'},mm=50.,rotation_deg=5.)
    p.act(side,'UP',mm=50.,follower=other)
    snapshot,_=p.snapshot()
    if any(snapshot['tray']['grasp']):raise ToolExecutionError('E01 functional tray failed to release')
    _meal_on_tray(p);state['phase']='loaded'
    p.a.control_report['e01_functional_loaded_tray']=dict(actual_released=True,
        actual_box_contact=p.contact('tray','meal_box'),native_final_precision_not_required=True)
    return dict(local_completed=True,phase='loaded',functional_stage_completed=True,whole_task_score=None)
