"""Bounded physical contact seeking; contact, not a sub-mm waypoint, ends it."""
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def native_edge_progress(a,name):
    """Read measured contact counters; never read or alter a completion label."""
    e=getattr(getattr(a,'c',None),'evaluator',None)
    if e is None or not hasattr(e,'progress_causal'):return None
    record=e.progress_causal.get(e.label(name),{})
    if record.get('effective_push_forbidden_intervention'):return None
    return(int(record.get('effective_push_valid_increments',0)),int(record.get('effective_push_fragment_count',0)))


def edge_progress_advanced(before,after):
    return before is not None and after is not None and any(b>a for a,b in zip(before,after))


def remember_native_contact(a,edge,name,before):
    after=native_edge_progress(a,name)
    if not edge_progress_advanced(before,after):return False
    records=getattr(a,'_engineering_recent_edge_contacts',None)
    if records is None:records={};a._engineering_recent_edge_contacts=records
    records[name]=dict(step=int(a.c.steps),counters=after,tool=edge['actor'])
    return True


def current_or_recent_edge_contact(a,edge,name):
    if a.contact(name,edge['actor']):return True
    record=getattr(a,'_engineering_recent_edge_contacts',{}).get(name)
    if record is None or int(a.c.steps)-record['step']>1:return False
    counters=native_edge_progress(a,name)
    if counters is None or any(b<a for a,b in zip(record['counters'],counters)):return False
    state,_=a.snapshot();body=state[edge['actor']];ball=state[name]
    if (not any(body['grasp'])or any(ball['grasp'])or not a.contact(name,'table')
            or any(a.contact(name,f'{s}_finger{i}')for s in('left','right')for i in(1,2))):return False
    from .execution_design_e42_edge import edge_distance
    obj=next(o for o in a.spec['objects']if o['id']==edge['actor'])
    radius=max(next(o for o in a.spec['objects']if o['id']==name)['size'])
    local=np.asarray(body['mat']).T@(np.asarray(ball['pos'])-body['pos'])
    return edge_distance(local,obj)<=radius+.006


def seek_edge_contact(a, side, edge, name, target, guard):
    if a.task!='E42' or not a.a.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('E42 isolated contact search only')
    for probe in range(9):
        guard()
        if not a.contact(name,'table'):
            raise ToolExecutionError('Contact search ball lost actual table support')
        if a.contact(name,edge['actor']):return
        p=a.snapshot()[0][name]['pos'];direction=np.asarray(target)-p;direction[2]=0
        norm=float(np.linalg.norm(direction))
        if norm<1e-9:raise ToolExecutionError('Missing contact search direction')
        direction/=norm
        point=np.asarray(a.point(edge));goal=point+direction*.002
        # Keep the leading edge near the actual ball centre; each axis gets
        # at most one public step per probe. In-grip vibration cannot cause an
        # unbounded attempt to converge an intermediate imaginary point.
        goal[2]=p[2]
        for axis in sorted(range(3),key=lambda i:-abs(float(goal[i]-point[i]))):
            guard()
            if a.contact(name,edge['actor']):return
            error=float(goal[axis]-a.point(edge)[axis])
            if abs(error)<.0005:continue
            token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error<0)]
            before=native_edge_progress(a,name)
            a.act(side,token,mm=min(abs(error)*1000.,2.))
            if remember_native_contact(a,edge,name,before):return
        if a.contact(name,edge['actor']):return
    raise ToolExecutionError('No actual blade-edge contact after bounded physical microsteps')
