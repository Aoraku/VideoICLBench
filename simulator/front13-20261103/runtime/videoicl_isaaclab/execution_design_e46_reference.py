"""Private E46 v3 candidate: insert source blade under the real thin block.

Adapted from the unaccepted E28 public scoop candidate; native success pending.

Only public robot motions; food is never acquired, repositioned or attached.
Every target is recomputed from native body transforms and geometry.
"""
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .execution_design_spatula_clearance import blade_edge_floor_height


def solve(a):
    t, grip, side = a.tool()
    work = dict(actor=t['actor'],local=t['working_local'])
    edge = dict(actor=t['actor'],local=np.asarray(t['edge_segment'],float).mean(axis=0))
    if a.task!='E46':raise ToolExecutionError('E46 scoop reference only')
    names=list(a.s['groups']['cargo'])
    guard=lambda:a.require_held(grip,side)
    a.stage('orient-spatula-edge-for-true-scoop')
    a.move(side,[*a.tip(side)[:2],1.02],guard)
    # Retain a shallow source-blade wedge while lifting the handle enough
    # for the real fingers to clear the table. The actual collision vertices
    # determine the lowest permitted edge waypoint; never command below it.
    rotation,direction=select_scoop_direction(a,t,side,names[0])
    a.rotate_actor(t['actor'],side,rotation)
    for i,name in enumerate(names):
        state=a.snapshot()[0][name]
        obj=next(o for o in a.spec['objects'] if o['id']==name)
        half=np.abs(state['mat'])@np.asarray(obj['size'],float)
        center=state['pos'].copy(); bottom=float(center[2]-half[2])
        start=center-direction*(float(np.abs(direction)@half)+.012)
        tool_obj=next(o for o in a.spec['objects']if o['id']==t['actor'])
        actual_rotation=a.snapshot()[0][t['actor']]['mat']
        start[2]=blade_edge_floor_height(tool_obj,actual_rotation,edge['local'],bottom)
        if start[2]>bottom+min(.004,1.5*half[2]):
            raise ToolExecutionError('Actual blade floor clearance exceeds underside entry band')
        a.stage('approach-blade-edge-'+name)
        a.move_point(side,edge,start+[0,0,.08],guard)
        a.move_point(side,edge,start,guard,tolerance=.001)
        a.stage('insert-blade-under-'+name)
        # The open other finger only prevents table-side sliding. Actual
        # insertion is measured relative to the food, and that finger leaves
        # the lift column before the independent hand-free lift below.
        from .execution_design_e46_backstop import insert
        insert(a,name,edge,side,direction,start[2],guard)
        if not a.contact(name,t['actor']):
            raise ToolExecutionError('True scoop: blade failed to contact food')
        a.stage('lift-food-on-blade-'+name)
        def loaded():
            guard()
            if not a.contact(name,t['actor']):
                raise ToolExecutionError('True scoop: food lost actual blade support')
        a.move_point(side,work,a.point(work)+[0,0,.065],loaded)
        state=a.snapshot()[0][name]
        actual_bottom=float(state['pos'][2]-(np.abs(state['mat'])@np.asarray(obj['size'],float))[2])
        if a.contact(name,'table') or actual_bottom-bottom<.006:
            raise ToolExecutionError('True scoop: food did not leave the table on blade')
        dest=a.destination(name,i)
        a.stage('carry-scooped-food-'+name)
        a.move_point(side,work,[*a.point(work)[:2],max(dest[2]+.08,.92)],loaded)
        a.move_point(side,work,[*dest[:2],max(dest[2]+.08,.92)],loaded)
        a.move_point(side,work,dest+[0,0,.003],loaded)
        a.stage('withdraw-blade-release-'+name)
        withdraw=a.frame(work)[1]@np.asarray(t['withdraw_local'],float)
        a.move_point(side,work,a.point(work)+withdraw*.10,guard)
        a.wait(3)
        a.move(side,a.tip(side)+[0,0,.07],guard)


def select_scoop_direction(a,t,side,name):
    """Screen real held-tool transforms at entry, insertion, and lift.

    Kinematic feasibility is only a filter. Public actuation and native tool
    support remain required; no candidate joint solution is written to robots.
    """
    import json
    from .execution_design_drawer_ik_probe import inspect
    state,_=a.snapshot();tool=state[t['actor']];body=state[name]
    obj=next(o for o in a.spec['objects']if o['id']==name)
    half=np.abs(body['mat'])@np.asarray(obj['size'],float);center=body['pos']
    bottom=float(center[2]-half[2]);edge=np.mean(t['edge_segment'],axis=0)
    local_tcp=tool['mat'].T@(a.tip(side)-tool['pos'])
    relative_hand=tool['mat'].T@np.asarray(a.a.tcp_rotation_task(side))
    candidates=[];targets=[];stride=5
    tool_obj=next(o for o in a.spec['objects']if o['id']==t['actor'])
    tilt=np.deg2rad(8.);pitch=np.array([[np.cos(tilt),0.,np.sin(tilt)],[0.,1.,0.],[-np.sin(tilt),0.,np.cos(tilt)]])
    for yaw in (0.,np.pi/2,np.pi,-np.pi/2):
        c,s=np.cos(yaw),np.sin(yaw);yaw_rotation=np.array([[c,-s,0.],[s,c,0.],[0,0,1.]]);r=yaw_rotation@pitch
        direction=yaw_rotation@np.array([1.,0,0]);start=center-direction*(float(abs(direction)@half)+.012);start=start.copy();start[2]=blade_edge_floor_height(tool_obj,r,edge,bottom)
        insertion=center+direction*.025;insertion=insertion.copy();insertion[2]=start[2]
        edge_points=[start+[0,0,.08],start,insertion,insertion+[0,0,.065]]
        positions=[a.tip(side),*[q+r@(local_tcp-edge)for q in edge_points]]
        candidates.append(dict(rotation=r,direction=direction))
        targets.extend(dict(position=q.tolist(),rotation=(r@relative_hand).tolist())for q in positions)
    rows=inspect(a.a,a.c,side,targets)
    valid=[]
    for i,candidate in enumerate(candidates):
        subset=rows[i*stride:(i+1)*stride]
        if all(row['kinematically_reachable'] and row['minimum_joint_margin_rad']>=.06 for row in subset):
            valid.append((min(row['minimum_joint_margin_rad']for row in subset),-sum(row['joint_distance_rad']for row in subset),i))
    chosen=max(valid)[2]if valid else None
    with (a.a.out/'scoop-direction-candidates.private.json').open('w')as f:
        json.dump(dict(chosen=chosen,candidates=rows,native_verified=False,collision_verified=False),f)
    if chosen is None:raise ToolExecutionError('No floor-clear scoop direction has measured IK margin along entry and lift')
    return candidates[chosen]['rotation'],candidates[chosen]['direction']
