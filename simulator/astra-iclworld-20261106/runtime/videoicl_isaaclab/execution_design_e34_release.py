"""Private E34 narrow-cell release through real gripper motors and public holds."""
import json
from pathlib import Path
import numpy as np
from .execution_design_e34_reference import scope


def release_supported(a,side,name):
    scope(a);spec=a.scene.spec;s=spec['semantic'];tray=s['container'];ix=('left','right').index(side)
    if name!=s['selected']or spec.get('variant')not in ('B','C')or name not in ('spoon','fork'):
        raise ValueError('Selected E34B/C real supported cutlery required')
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_branch_geometry import collision_parts_task
    from types import SimpleNamespace
    state,contacts=a.c.snapshot();fingers=[side+'_finger1',side+'_finger2'];trace=[]
    if a.carried_payload!=(name,side)or not state[name]['grasp'][ix]or frozenset((name,tray))not in contacts:
        raise RuntimeError('E34 release requires actual held utensil and actual tray support')
    baseline={n:dict(pos=np.asarray(b['pos']).copy(),mat=np.asarray(b['mat']).copy())for n,b in state.items()if n!=name}
    def force(x,y):return float(getattr(a.c,'contact_forces',{}).get(frozenset((x,y)),0.))
    def guard():
        state,contacts=a.c.snapshot()
        if spec.get('variant')=='B':
            from .execution_design_e34_acquire import check_pickup_neighbors
            check_pickup_neighbors(a,side,name,baseline)
        else:
            for n,old in baseline.items():
                b=state[n]
                if any(b['grasp'])or np.linalg.norm(np.asarray(b['pos'])-old['pos'])>.002 or np.linalg.norm(np.asarray(b['mat'])-old['mat'])>.03:
                    raise RuntimeError('E34 narrow release moved unselected body: '+n)
                if any(force(n,f)>.001 for f in fingers):raise RuntimeError('E34 narrow release hand touched unselected body: '+n)
        if frozenset((name,tray))not in contacts:raise RuntimeError('E34 narrow release lost actual tray support')
        return state,contacts
    def hold():
        a.act();return guard()
    def record(status,**extra):
        row=dict(object=name,side=side,status=status,step=a.c.steps,trace=trace,
            direct_joint_state_written=False,real_motor_targets_and_public_actions_only=True,**extra)
        with (Path(a.out)/'e34-supported-narrow-release.private.jsonl').open('a')as f:f.write(json.dumps(row,default=lambda v:v.tolist()if hasattr(v,'tolist')else str(v))+'\n')
    try:
        guard();robot=a.scene.robots[side];ids=a.c.ids[side][1]
        initial=float(robot.data.joint_pos[0,ids].detach().cpu().numpy().max())
        released=False
        # One millimetre per pad is already a real physical gap. Keep the jaw
        # within the narrow cell until both measured pad forces have vanished.
        # The source B grasp may close to only 6.8mm per pad. Its former
        # arbitrary +5mm loop stopped before the 14.5mm opening already shown
        # to separate the curved spoon. Keep real 1mm steps and the same
        # measured 18mm narrow-cell motor limit; C retains its proven route.
        extras=(tuple(i*.001 for i in range(1,19))if spec.get('variant')=='B'
                else(.001,.002,.003,.004,.005))
        for extra in extras:
            opening=initial+extra
            if opening>.018:break
            a.stage='e34-private-narrow-release';a.c.grips[side]=opening
            for _ in range(2):state,contacts=hold()
            forces=[force(name,f)for f in fingers]
            trace.append(dict(step=a.c.steps,per_finger_motor_target_m=opening,actual_grasp=state[name]['grasp'][ix],actual_pad_forces_n=forces))
            if not state[name]['grasp'][ix]and max(forces)<=.001:
                released=True;break
        if not released:raise RuntimeError('E34 narrow motor release did not establish true bilateral separation')
        a.carried_payload=None
        for _ in range(2):hold()
        def frame(ref):
            body=a.c.snapshot()[0][ref['actor']];return np.asarray(body['pos']),np.asarray(body['mat'])
        policy=SimpleNamespace(a=a,frame=frame)
        wall_top=max(float(p[:,2].max())for p in collision_parts_task(policy,tray))
        token='UP'if a.generated_axis_signs[side][2]==1 else'DOWN'
        a.stage='e34-narrow-empty-hand-withdraw'
        for _ in range(16):
            state,contacts=guard()
            if any(state[name]['grasp']):raise RuntimeError('E34 released utensil actually regrasped during withdrawal')
            if any(force(name,f)>.001 for f in fingers):raise RuntimeError('E34 released utensil touched pad during withdrawal')
            lowest=min(float(actual_mesh(a,side,n)[:,2].min())for n in a.scene.embodiment.fingers)
            if lowest>=wall_top+.012:break
            a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',5.);guard()
        else:raise RuntimeError('E34 empty narrow hand failed to clear real tray wall')
        # Only clear of every wall can the standard full opening be used.
        a.stage='e34-fully-open-above-tray';a.act('RELEASE'if side=='left'else'STILL','RELEASE'if side=='right'else'STILL',5.);state,contacts=guard()
        if any(state[name]['grasp'])or any(force(name,f)>.001 for f in fingers):raise RuntimeError('E34 full opening outside tray did not retain true release')
        record('actual_released_supported_and_hand_clear',actual_grasp=False,actual_pad_forces_n=[force(name,f)for f in fingers],actual_tray_support=True,wall_top=wall_top)
        return dict(actual_released=True,actual_bilateral_contact_released=True,actual_tray_support=True,trace=trace)
    except Exception as exc:
        record('failed',error=type(exc).__name__+': '+str(exc));raise
