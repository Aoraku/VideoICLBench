"""Public-action bottle handoff and insertion for isolated E33 v3 engineering.

The world, task goals, mesh containment and evaluator are never modified. A
geometric waypoint is a proposal; actual bilateral grip is required throughout.
"""
import json
import numpy as np
from .execution_design import REVISION_V3
from .execution_design_e33_grasp import grasp_position
from .execution_design_thin_edge import table_bounds_task


def hull_world(obj,body):
    hull=obj['source_containment_hull']
    if hull['source_asset_sha256']!=obj['source_asset']['sha256']or not np.allclose(hull['descriptor_half_size'],obj['size']):
        raise ValueError('E33 requires the pinned actual bottle collision hull')
    return np.asarray(hull['vertices_local'],float)@np.asarray(body['mat']).T+np.asarray(body['pos'])


def rim_and_center(container,body):
    lo,hi=np.asarray(container['lower'],float),np.asarray(container['upper'],float)
    if np.any(hi<=lo):raise ValueError('Ordered original cavity bounds required')
    corners=np.array([[x,y,z]for x in (lo[0],hi[0])for y in (lo[1],hi[1])for z in (lo[2],hi[2])])
    world=corners@np.asarray(body['mat']).T+np.asarray(body['pos'])
    return float(world[:,2].max()),(np.asarray(body['pos'])+np.asarray(body['mat'])@((lo+hi)/2))[:2]


def insertion_plane(tcp,bottle_vertices,finger_geometry,rim,margin=.015):
    tcp=np.asarray(tcp,float);points=np.asarray(bottle_vertices,float)
    if margin<.01 or not np.isfinite(np.r_[tcp,points.ravel(),rim]).all():raise ValueError('Finite measured geometry and positive rim margin required')
    lowest=float(finger_geometry['lowest_z_task_m'])
    depth=max(float(tcp[2]-points[:,2].min()),float(tcp[2]-lowest),0.)
    return float(rim+depth+margin)


def handoff_position(spec,state,bounds,name):
    # Search a free real tabletop patch towards the robot bases, outside the
    # bin footprint. No added fixture, teleport or speculative virtual support.
    candidates=[[-.30,y]for y in (0.,-.10,.10)]+[[-.25,y]for y in (0.,-.10,.10)]
    # A sideways bottle can extend beyond the table at both legacy columns.
    # Search the adjacent shared-reach corridor too, with the same complete
    # footprint and obstacle checks; do not rotate it just to fit a waypoint.
    candidates.extend([[x,y]for x in (-.225,-.20)for y in (0.,-.10,.10,-.20,.20)])
    obj=next(o for o in spec['objects']if o['id']==name)
    half=(np.abs(np.asarray(state[name]['mat']))@np.asarray(obj.get('bounds_half_extent',obj['size'])))[:2]+.025
    for xy in candidates:
        p=np.asarray(xy,float)
        if np.any(p-half<np.asarray(bounds['lower'])[:2])or np.any(p+half>np.asarray(bounds['upper'])[:2]):continue
        clear=True
        for o in spec['objects']:
            if o['id']==name:continue
            b=state[o['id']];extent=np.abs(np.asarray(b['mat']))@np.asarray(o.get('bounds_half_extent',o['size']))
            if np.all(abs(p-np.asarray(b['pos'])[:2])<=extent[:2]+half):clear=False;break
        if clear:return p
    raise RuntimeError('No collision-clear physical tabletop handoff patch')


def solve(author):
    a=author;spec=a.scene.spec
    if not getattr(a,'_execution_design_reference_authorized',False)or spec['id']!='E33'or spec.get('execution_design',{}).get('revision')!=REVISION_V3 or a.smooth:
        raise ValueError('Explicit E33 v3 public-action engineering route required')
    if a.scene.embodiment.name!='franka':raise ValueError('Reviewed Panda E33 route required')
    start=a.c.steps;home={s:a.tip(s).copy()for s in ('left','right')};operations=[]
    if not a.smooth:a.calibrate_generated_axes()
    a.act('RELEASE','RELEASE')
    active=None
    def log(kind,**row):
        row=dict(kind=kind,step=a.c.steps,**row);operations.append(row)
        with (a.out/'e33-physical-transfer.private.jsonl').open('a')as f:f.write(json.dumps(row)+'\n')
    def move(side,target):a.move_generated({side:np.asarray(target,float)},tolerance=.003)
    def park(side):
        if a.carried_payload is not None:raise RuntimeError('Cannot park a loaded hand')
        a.stage='e33-park-'+side
        move(side,[*a.tip(side)[:2],max(1.10,float(a.tip(side)[2]))])
        move(side,[*home[side][:2],max(1.10,float(a.tip(side)[2]))])
        # Keep the idle hand at its verified initial home: outside the bottle
        # transfer corridor. It is measured here, not a guessed foreign origin.
        move(side,home[side])
    def switch(side):
        nonlocal active
        if side!=active and active is not None:park(active)
        active=side
    def pickup(name,side):
        switch(side);a.stage='e33-acquire-'+name
        a.act('RELEASE'if side=='left'else'STILL','RELEASE'if side=='right'else'STILL')
        obj=next(o for o in spec['objects']if o['id']==name)
        target=grasp_position(a,side,obj)
        pre=max(float(target[2])+.055,float(a.tip(side)[2]))
        move(side,[*a.tip(side)[:2],pre]);move(side,[*target[:2],pre]);move(side,target)
        for _ in range(3):a.act('GRASP'if side=='left'else'STILL','GRASP'if side=='right'else'STILL')
        state,_=a.c.snapshot()
        if not state[name]['grasp'][0 if side=='left' else 1]:raise RuntimeError('E33 pickup lacks actual bilateral finger grasp: '+name)
        a.carried_payload=(name,side);a.stage='grasped-'+name
        log('actual_grasp',object=name,side=side,tcp=a.tip(side).tolist())
    def released(name,side):
        a.act('RELEASE'if side=='left'else'STILL','RELEASE'if side=='right'else'STILL')
        a.carried_payload=None
        for _ in range(3):a.act()
        state,_=a.c.snapshot()
        if any(state[name]['grasp']):raise RuntimeError('E33 handoff/release still physically held')
    for goal in spec['goals']:
        name=goal['object'];obj=next(o for o in spec['objects']if o['id']==name)
        state,_=a.c.snapshot();body=state[name]
        container=spec['semantic']['containers']['bin'];bin_body=state[container['object']]
        rim,destination=rim_and_center(container,bin_body)
        bases={}
        for side in ('left','right'):
            value=a.scene.robots[side].data.root_pos_w[0]
            if hasattr(value,'cpu'):value=value.cpu().numpy()
            bases[side]=np.asarray(a.scene.world_to_task(value))
        pickup_side=min(bases,key=lambda s:np.linalg.norm(np.asarray(body['pos'])[:2]-bases[s][:2]))
        receiver=min(bases,key=lambda s:np.linalg.norm(destination-bases[s][:2]))
        pickup(name,pickup_side);side=pickup_side
        if side!=receiver:
            state,_=a.c.snapshot();bounds=table_bounds_task(a.scene)
            buffer=handoff_position(spec,state,bounds,name)
            # Move towards the bases before crossing the midline, keeping the
            # held bottle and palm outside the tall bin's sidewall corridor.
            transfer=max(1.08,float(a.tip(side)[2])+.06)
            move(side,[*a.tip(side)[:2],transfer]);move(side,[buffer[0],a.tip(side)[1],transfer]);move(side,[*buffer,transfer])
            # The intermediate table release has no upright requirement.
            # Keep a sideways bottle's achieved pose here; rotating an
            # off-centre grasp before lowering can put the source hand in
            # a wrist configuration that cannot reach the table. The receiving
            # hand performs the required insertion alignment afterwards.
            state,_=a.c.snapshot();vertices=hull_world(obj,state[name]);offset=a.tip(side)-np.asarray(state[name]['pos'])
            target_xy=buffer+offset[:2];target_z=bounds['top']+.002+float(a.tip(side)[2]-vertices[:,2].min())
            move(side,[*target_xy,transfer]);move(side,[*target_xy,target_z]);released(name,side)
            state,contacts=a.c.snapshot()
            if not any(set(pair)=={name,'table'}for pair in contacts):raise RuntimeError('E33 handoff requires actual tabletop support')
            log('actual_table_handoff',object=name,from_side=side,to_side=receiver,position=np.asarray(state[name]['pos']).tolist())
            move(side,[*a.tip(side)[:2],transfer]);park(side);active=None
            pickup(name,receiver);side=receiver
        # Upright at the near-base waypoint, then lift the entire true bottle
        # hull above the actual bin rim before crossing over its sidewall.
        a.stage='grasped-'+name
        move(side,[*a.tip(side)[:2],max(1.10,float(a.tip(side)[2])+.06)])
        a.rotate_held(name,side,dict(roll=0.,pitch=0.,yaw=0.))
        state,_=a.c.snapshot();vertices=hull_world(obj,state[name]);rim,destination=rim_and_center(container,state[container['object']])
        move(side,[-.25,a.tip(side)[1],a.tip(side)[2]])
        state,_=a.c.snapshot();vertices=hull_world(obj,state[name])
        plane=insertion_plane(a.tip(side),vertices,a.finger_geometry(side),rim)
        offset=a.tip(side)-np.asarray(state[name]['pos']);target_xy=destination+offset[:2]
        log('true_shape_rim_clearance',object=name,side=side,rim=rim,clearance_tcp_z=plane,target_xy=target_xy.tolist())
        move(side,[*a.tip(side)[:2],plane]);move(side,[*target_xy,plane])
        release_z=a.floor_clear_tcp(side,floor=rim+.012)
        move(side,[*target_xy,release_z]);released(name,side)
        move(side,[*a.tip(side)[:2],plane]);park(side);active=None
        for _ in range(8):a.act()
        log('released_into_bin',object=name,native_success_not_asserted=True)
    return dict(task='E33',actions=a.c.steps-start,operations=operations,physics_success_not_asserted=True)
