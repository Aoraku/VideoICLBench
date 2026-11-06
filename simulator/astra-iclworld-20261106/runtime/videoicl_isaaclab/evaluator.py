"""Private terminal evaluator. Requires actual PhysX contact evidence, not actor claims."""
import math
import numpy as np
from .profiles import PROTOCOL

class Evaluator:
    def __init__(self,spec):
        self.spec=spec;self.by_id={x['id']:x for x in spec['objects']}
        self.events=set();self.handled=set();self.origins={};self.hold_seconds=0.
        self.previous=None;self.current_conditions=[]
        self.no_touch={g['object'] for g in spec['goals'] if g['type']=='guided_roll'}
        self.no_touch.update(spec.get('no_direct_touch',[]))
        self.event_history={};self.event_active={};self.event_clear_seconds={};self.event_enabled=False

    def reset_episode(self):
        self.events.clear();self.handled.clear();self.origins.clear();self.hold_seconds=0.
        self.event_history.clear();self.event_active.clear();self.event_clear_seconds.clear()

    @staticmethod
    def rotation(q):
        w,x,y,z=q
        return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                         [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                         [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])

    def _pose(self,g,a,contacts,name):
        p=np.asarray(a['pos']);mat=np.asarray(a['mat'])
        if 'xy' in g and np.linalg.norm(p[:2]-g['xy'])>g.get('xy_tolerance',.02):return False
        if 'z' in g and abs(p[2]-g['z'])>g.get('z_tolerance',.012):return False
        if 'minimum_z' in g and p[2]<g['minimum_z']:return False
        if 'maximum_z' in g and p[2]>g['maximum_z']:return False
        if not .77<p[2]<1.5:return False
        if 'minimum_up_cos' in g and mat[2,2]<g['minimum_up_cos']:return False
        if 'maximum_up_cos' in g and mat[2,2]>g['maximum_up_cos']:return False
        if 'yaw' in g:
            yaw=math.atan2(mat[1,0],mat[0,0]);delta=math.atan2(math.sin(yaw-g['yaw']),math.cos(yaw-g['yaw']))
            if abs(delta)>g.get('yaw_tolerance',.16):return False
        if 'quaternion' in g:
            target=self.rotation(g['quaternion']);cos=(np.trace(target.T@mat)-1)/2
            if cos<math.cos(g.get('orientation_tolerance',.16)):return False
        supports=g.get('support_any',[])
        if g.get('required_support'):supports=[g['required_support']]
        if supports and not any(frozenset((name,x)) in contacts for x in supports):return False
        return True

    def predicate(self,g,state,contacts):
        typ=g['type'];name=g['object'];a=state[name];sa=self.by_id[name]
        p=np.asarray(a['pos']);mat=np.asarray(a['mat']);size=np.asarray(sa['size'])
        extent=np.abs(mat)@size
        contact=lambda x,y:frozenset((x,y)) in contacts
        if typ=='pose':return self._pose(g,a,contacts,name)
        if typ=='contact':return contact(name,g['target'])
        if typ=='zone_count':
            count=sum(self.predicate(dict(type='place',object=n,target=g['target'],required_support=g['required_support']),state,contacts) for n in g['members'])
            return count==g['count']
        if typ=='relative_pose':
            target=g['target'];b=state[target];bm=np.asarray(b['mat'])
            delta=bm.T@(p-np.asarray(b['pos']))-np.asarray(g.get('offset',[0,0,0]))
            if np.any(np.abs(delta)>np.asarray(g.get('tolerance',[.015]*3))):return False
            if g.get('require_contact') and not contact(name,target):return False
            return self._pose(g,a,contacts,name)
        if typ=='grasp_lift':return bool(any(a['grasp']) and p[2]>=g['minimum_z'])
        if typ=='sequence':return self.event_history.get(g['key'],[])==g['expected']
        if typ=='event_count':return self.event_history.get(g['key'],[]).count(g['label'])==g['count']
        if typ=='never_handled':return name not in self.handled
        if typ=='tool_contact':return bool(contact(name,g['target']) and any(state[g['target']]['grasp']))
        if typ=='tool_lift':return bool(contact(name,g['target']) and any(state[g['target']]['grasp']) and p[2]>=g['minimum_z']
                                       and (not g.get('second_contact') or contact(name,g['second_contact'])))
        if typ=='event_seen':return g['label'] in self.event_history.get(g['key'],[])
        if typ=='relative_angle':
            b=state[g['target']];relative=np.asarray(b['mat']).T@mat
            axis=g.get('axis',0);cos=relative[(axis+1)%3,(axis+1)%3]
            return bool(abs(math.acos(float(np.clip(cos,-1,1)))-g['angle'])<g.get('tolerance',.10)
                        and (not g.get('support') or contact(name,g['support'])))
        if typ=='position':return bool(np.linalg.norm(p[:2]-g['xy'])<g['tolerance'] and .8<p[2]<.96)
        if typ=='place':
            z=next(x for x in self.spec['zones'] if x['id']==g['target'])
            if sa['kind']=='sphere':extent=np.full(3,size[0])
            upright=not g.get('require_upright') or mat[2,2]>=g.get('minimum_up_cos',.97)
            support=not g.get('required_support') or contact(name,g['required_support'])
            base=float(z.get('surface_z',.8))
            bottom_ok=('bottom_tolerance' not in g or abs(p[2]-extent[2]-base)<g['bottom_tolerance'])
            margin=float(g.get('clearance_margin',.008))
            return bool(upright and support and bottom_ok and np.all(np.abs(p[:2]-z['xy'])+extent[:2]<np.asarray(z['half_size'])+margin) and base-.002<p[2]<base+extent[2]+.025)
        if typ in ('stack','nest','insert','threaded'):
            target=g['target'];b=state[target];sb=self.by_id[target];bp=np.asarray(b['pos']);bm=np.asarray(b['mat'])
            bs=np.asarray(sb['size']);local=bm.T@(p-bp)
            if typ=='stack':
                be=np.abs(bm)@bs
                return bool(np.linalg.norm(p[:2]-bp[:2])<max(.02,min(bs[:2])*.65) and abs((p[2]-extent[2])-(bp[2]+be[2]))<.012 and contact(name,target))
            if typ=='nest':
                inner=np.asarray(sb.get('inner_size',sb['size']));relative=bm.T@mat
                local_extent=np.abs(relative)@size
                if sa['kind']=='sphere':local_extent=size
                return bool(np.all(np.abs(local[:2])+local_extent[:2]<inner[:2]+.002) and abs(local[2]-local_extent[2]-(-inner[2]+.008))<.015 and local[2]+local_extent[2]<inner[2]+.12 and contact(name,target))
            if typ=='insert':
                return bool(np.linalg.norm(local[:2])<g.get('tolerance',.015) and mat[2,2]>.97 and abs(local[2]-size[2]-g.get('relative_bottom',-bs[2]+.008))<.008 and contact(name,'table'))
            center=mat.T@(bp-p);axis=mat.T@bm[:,2]
            if abs(axis[2])<.5:return False
            angles=np.arange(24)*2*np.pi/24;normals=np.column_stack((np.cos(angles),np.sin(angles)))
            radial=sb['post_radius']*np.sqrt(1+(normals@axis[:2]/axis[2])**2)
            for side in (-1,1):
                t=(side*size[2]-center[2])/axis[2];point=center+t*axis
                if not -bs[2]+.007<=t<=bs[2]+.001:return False
                if np.any(normals@point[:2]+radial>sa['inner_radius']+.0005):return False
            return bool(abs(local[2]-size[2]+bs[2]-.008)<.008 and contact(name,target))
        if typ in ('swept','guided_roll'):return (typ,name) in self.events and name not in self.handled
        raise ValueError('Unimplemented predicate: '+typ)

    def update(self,state,contacts,dt):
        contact=lambda x,y:frozenset((x,y)) in contacts
        for name,a in state.items():
            if any(a['grasp']) or (name in self.no_touch and any(contact(name,f'{s}_{f}') for s in ('left','right') for f in ('finger1','finger2'))):
                self.handled.add(name)
        if self.event_enabled:
            for i,rule in enumerate(self.spec.get('event_rules',[])):
                value=self.predicate(rule['predicate'],state,contacts)
                if rule.get('released'):value=value and not any(state[rule['predicate']['object']]['grasp'])
                if rule.get('held_tool'):value=value and any(state[rule['held_tool']]['grasp'])
                if rule.get('never_handled'):value=value and rule['never_handled'] not in self.handled
                if rule.get('require_finger_contact'):value=value and any(contact(rule['predicate']['object'],f'{side}_finger{i}') for side in ('left','right') for i in (1,2))
                active=self.event_active.get(i,False)
                if value:
                    if not active:self.event_history.setdefault(rule['key'],[]).append(rule['label'])
                    self.event_active[i]=True;self.event_clear_seconds[i]=0.
                elif active:
                    clear=self.event_clear_seconds.get(i,0.)+dt;self.event_clear_seconds[i]=clear
                    rearm=self.predicate(rule['rearm_predicate'],state,contacts) if rule.get('rearm_predicate') else True
                    if rearm and clear>=rule.get('rearm_seconds',.06):self.event_active[i]=False
        # Preserve the frozen F39 rule: force chains through other beads count,
        # but every link must be in contact while the brush is actually held.
        sweep_tools={g['target'] for g in self.spec['goals'] if g['type']=='swept'}
        active_by_tool={}
        for tool in sweep_tools:
            names={g['object'] for g in self.spec['goals'] if g['type']=='swept' and g['target']==tool}
            active={name for name in names if contact(name,tool)} if any(state[tool]['grasp']) else set()
            while True:
                more={name for name in names-active if any(contact(name,n) for n in active)}
                if not more:break
                active.update(more)
            active_by_tool[tool]=active
        for g in self.spec['goals']:
            name=g['object']
            if g['type']=='swept' and name in active_by_tool[g['target']] and name not in self.handled:
                origin=self.origins.setdefault(name,np.asarray(state[name]['pos']).copy())
                if np.linalg.norm(np.asarray(state[name]['pos'])[:2]-origin[:2])>=g['distance']:
                    self.events.add(('swept',name))
            if g['type']=='guided_roll' and name not in self.handled:
                if contact(name,g['ramp']) and any(contact(name,n) for n in g['guides']):self.events.add(('guided_roll',name))
        self.current_conditions=[dict(index=i,type=g['type'],passed=self.predicate(g,state,contacts)) for i,g in enumerate(self.spec['goals'])]
        grounded={name for name in state if contact(name,'table') or any(contact(name,f'fixture{i}') for i in range(len(self.spec['fixtures'])))}
        grounded.update(j['child'] for j in self.spec.get('joints',[]) if not j.get('parent'))
        while True:
            more={name for name in state if name not in grounded and any(contact(name,other) for other in grounded)}
            for joint in self.spec.get('joints',[]):
                parent=joint.get('parent');child=joint['child']
                if parent in grounded:more.add(child)
                if child in grounded and parent:more.add(parent)
            more.difference_update(grounded)
            if not more:break
            grounded.update(more)
        released=not any(any(x['grasp']) for x in state.values())
        stable=self.previous is not None and all(np.linalg.norm(np.asarray(a['pos'])-self.previous[n])<.002*dt/.05 for n,a in state.items())
        release_ok=released or not self.spec.get('success_release',True)
        held={n for n,a in state.items() if any(a['grasp'])} if not self.spec.get('success_release',True) else set()
        valid=all(x['passed'] for x in self.current_conditions) and release_ok and stable and len(grounded|held)==len(state)
        self.hold_seconds=self.hold_seconds+dt if valid else 0.
        self.previous={n:np.asarray(x['pos']).copy() for n,x in state.items()}
        self.extras=dict(released=released,supported=len(grounded)==len(state),stable=stable)

    def result(self):
        return dict(success=self.hold_seconds>=.5,hold_seconds=self.hold_seconds,conditions=self.current_conditions,
            events=[list(x) for x in sorted(self.events)],event_history=self.event_history,**getattr(self,'extras',{}),
            backend='isaaclab_physx',protocol=PROTOCOL)
