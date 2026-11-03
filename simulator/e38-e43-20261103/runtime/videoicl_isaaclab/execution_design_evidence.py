"""Opt-in physical evidence for execution-design-v1.

Inputs are measured poses/contact pairs. Specification predicates are private;
no model claims, action counts, or caller-supplied success bits are accepted.
Synthetic tests validate predicates, not PhysX reachability or asset acceptance.
"""
from copy import deepcopy
import math
import numpy as np

SUPPORTED = {'E01', 'E09', 'E17', 'E20', 'E39'}


class ExecutionDesignEvaluator:
    def __init__(self, spec):
        self.spec = deepcopy(spec)
        self.task, self.variant = spec['id'], spec['variant']
        self.design = self.spec['execution_design']
        if self.task not in SUPPORTED or self.design['schema'] not in ('execution-design-v1','execution-design-v2','execution-design-v3'):
            raise ValueError('Unsupported execution design')
        # The physical schema can stay v2 while the document contract advances
        # to v3. Validate the pinned contract, never silently select the latest.
        revision=self.design.get('revision')
        if revision is not None or self.design['schema']!='execution-design-v1':
            from .execution_design import SUPPORTED_REVISIONS, source_sha256
            if revision not in SUPPORTED_REVISIONS:
                raise ValueError('Unsupported execution-design contract revision')
            if self.design.get('source_sha256')!=source_sha256(revision):
                raise ValueError('Execution-design contract source checksum mismatch')
            if spec.get('task_revision',revision)!=revision:
                raise ValueError('Execution-design task revision mismatch')
        self.objects = {o['id']: o for o in spec['objects']}
        self.zones = {z['id']: z for z in spec['zones']}
        if not self.design.get('local_regions') and not self.design.get('local_order'):
            raise ValueError('Measured local regions required')
        if self.task != 'E17' and not self.design.get('packages'):
            raise ValueError('Physical packaging required')
        self.reset_episode()

    def reset_episode(self):
        self.initial = None
        self.initial_sealed = False
        self.previous = None
        self.anchor = None
        self.state = {}
        self.contacts = set()
        self.steps = 0
        self.elapsed = 0.
        self.hold_seconds = 0.
        self.history_valid = True
        self.errors = []
        self.events = []
        self.observation = {}
        self.current_conditions = []
        self.current = dict(local=False, packaging=False, delivery=False)
        self.preservation_failed = False
        self.reference_failed = False
        self.milestones = []
        self.initial_order_rule = None

    def update_contact_forces(self, snapshot):
        # Boolean contacts passed to update are already derived from native forces.
        pass

    def update_mechanisms(self, snapshot):
        pass

    def initial_diagnostics(self, *, room_id=None):
        unstable=[]
        if not self.state or self.hold_seconds < self.design.get('stability',{}).get('seconds',.5):
            unstable=list(self.objects)
        elif any(not self.released(n) for n in self.objects):
            unstable=[n for n in self.objects if not self.released(n)]
        grounded=self.grounded() if self.state else set()
        missing=[n for n in self.objects if n not in grounded]
        storage_failures=[]
        if self.state:
            supports={}
            for n,support in self.design.get('initial_storage',{}).items():
                if support not in supports:supports[support]=self.grounded(support)
                if n not in supports[support]:storage_failures.append('initial_storage:'+n+':'+support)
        ready=self.history_valid and bool(self.state) and not unstable and not missing and not storage_failures
        return dict(task=self.task,variant=self.variant,room_id=room_id,physics_step=self.steps,
                    native_evidence_valid=bool(self.history_valid and self.state and self.steps),can_seal=ready,ready=ready,
                    initial_sealed=self.initial_sealed,source_initial_failures=storage_failures,
                    initial_layout_failures=[],missing_required_groups=missing,
                    required_unstable_actors=unstable,native_errors=list(self.errors))

    def measured_joint_support(self, child):
        for j in self.spec.get('joints',[]):
            parent=j.get('parent')
            if j.get('type')!='revolute' or j.get('child')!=child or parent not in self.state: continue
            a,b=self.state[parent],self.state[child]
            if np.linalg.norm(a['pos']+a['mat']@np.asarray(j['anchor0'])-b['pos']-b['mat']@np.asarray(j['anchor1']))>=.008:continue
            axis=j.get('axis');rotation=a['mat'].T@b['mat']
            if axis not in ('X','Y','Z'):continue
            i='XYZ'.index(axis);unit=np.eye(3)[:,i]
            if np.linalg.norm(rotation@unit-unit)>.03:continue
            indices={'X':(2,1,1,1),'Y':(0,2,0,0),'Z':(1,0,0,0)}[axis]
            angle=math.degrees(math.atan2(rotation[indices[0],indices[1]],rotation[indices[2],indices[3]]))
            limits=j.get('limits')
            if not isinstance(limits,(list,tuple)) or len(limits)!=2:continue
            if limits[0]-2<=angle<=limits[1]+2:return True
        return False

    def seal_initial(self):
        if not self.initial_diagnostics()['can_seal']:
            raise ValueError('Stable released native initial snapshot with contacts required')
        for region,names in self.design.get('initial_preserved',{}).items():
            r=next(r for r in self.design['local_regions'] if r['id']==region)
            if not set(names)<=self.members(r):raise ValueError('Authored initial preserved members absent from measured cavity')
        self.initial = deepcopy(self.state)
        self.initial_sealed = True
        if self.task=='E39':
            r=deepcopy(self.design['local_order']);mapping=r.get('reference_map') or {n:n.replace('_active','_ref') for n in r['pieces']}
            ref_actor=r.get('reference_actor','reference_tray');a=self.initial[r['actor']];ref=self.initial[ref_actor]
            coord=lambda n:float((a['mat'].T@(self.initial[n]['pos']-a['pos']))[r.get('axis',1)])
            rc=lambda n:float((ref['mat'].T@(self.initial[mapping[n]]['pos']-ref['pos']))[r.get('axis',1)])
            r['expected_order']=sorted(r['pieces'],key=coord if self.variant=='B' else rc,reverse=r.get('descending',False))
            r['expected_yaws']={}
            r['expected_rotations']={}
            r['preserved_positions']={n:(a['mat'].T@(self.initial[n]['pos']-a['pos'])).tolist() for n in r['pieces']} if self.variant=='B' else {}
            for n in r['pieces']:
                v=self.initial[n] if self.variant=='A' else self.initial[mapping[n]]
                frame=a if self.variant=='A' else ref
                mat=frame['mat'].T@v['mat'];r['expected_yaws'][n]=math.atan2(mat[1,0],mat[0,0])
                r['expected_rotations'][n]=mat.tolist()
            self.initial_order_rule=r
        self.preservation_failed = False
        self.reference_failed = False
        self.milestones = []
        self.hold_seconds = 0.

    def released(self, name):
        return not any(self.state[name]['grasp']) and not any(
            name in pair and any('finger' in x for x in pair) for pair in self.contacts)

    def world_bounds(self,name):
        v=self.state[name];o=self.objects[name]
        center=v['pos']+v['mat']@np.asarray(o.get('local_bounds_center',[0,0,0]),float)
        half=np.abs(v['mat'])@np.asarray(o['size'],float)
        return center,half

    def contact(self, a, b):
        return frozenset((a, b)) in self.contacts

    def contained(self, name, region):
        s = self.state[name]; anchor = self.state[region['actor']] if region['actor'] else dict(pos=np.zeros(3),mat=np.eye(3))
        if self.task=='E17':
            from .execution_design_e17_geometry import contained
            return contained(self.objects[name],s,anchor,region,self.design.get('geometry_tolerance_m',.003))
        if self.task=='E09':
            from .execution_design_e09_geometry import contained
            return contained(self.objects[name],s,anchor,region['lower'],region['upper'],
                             self.design.get('geometry_tolerance_m',.003))
        center = s['pos'] + s['mat'] @ np.asarray(self.objects[name].get('local_bounds_center', [0, 0, 0]))
        local = anchor['mat'].T @ (center - anchor['pos'])
        radius = np.abs(anchor['mat'].T @ s['mat']) @ np.asarray(self.objects[name]['size'])
        if self.objects[name].get('kind') == 'sphere':
            radius = np.full(3, max(self.objects[name]['size']))
        tolerance = self.design.get('geometry_tolerance_m', .003)
        return bool(np.all(local-radius >= np.asarray(region['lower'])-tolerance)
                    and np.all(local+radius <= np.asarray(region['upper'])+tolerance))

    def seated(self,name,base,region):
        if base == (region['actor'] or 'table'):
            a=self.state[region['actor']] if region['actor'] else dict(pos=np.zeros(3),mat=np.eye(3))
            v=self.state[name];o=self.objects[name]
            if self.task=='E17':
                from .execution_design_e17_geometry import bounds
                low,_=bounds(o,v,a)
                return abs(low[2]-region['lower'][2])<.018
            center=v['pos']+v['mat']@np.asarray(o.get('local_bounds_center',[0,0,0]))
            local=a['mat'].T@(center-a['pos'])
            radius=np.abs(a['mat'].T@v['mat'])@np.asarray(o['size'])
            return abs(local[2]-radius[2]-region['lower'][2]) < .018
        bc,bh=self.world_bounds(base);vc,vh=self.world_bounds(name)
        return vc[2]>bc[2] and abs(vc[2]-vh[2]-bc[2]-bh[2])<.015 and np.all(np.abs(vc[:2]-bc[:2])<vh[:2]+bh[:2])

    def members(self, region):
        candidates = region.get('candidates', region.get('members', self.design['target_members']))
        if region.get('id') in {r['id'] for r in self.design['local_regions']}:
            candidates = sorted(set(candidates) | set(self.design.get('unused_members', [])) | set(self.design.get('distractor_members', [])))
        inside = [n for n in candidates if n != region['actor'] and self.contained(n, region)]
        if region['actor'] is None:
            roots={};result=set()
            for n in inside:
                support=region.get('support',self.design.get('initial_storage',{}).get(n,'table'))
                if support not in roots:roots[support]=self.grounded(support)
                if n in roots[support] and self.released(n):result.add(n)
            return result
        supported = {region['actor'] or 'table'}
        while True:
            more = {n for n in inside if n not in supported and self.released(n)
                    and any(self.contact(n, b) and self.seated(n,b,region) for b in supported)}
            if not more: break
            supported.update(more)
        return {n for n in inside if n in supported and self.released(n)}

    def region_correct(self, region, members):
        if 'count' in region:
            color = region.get('required_color')
            requested=set(self.design['target_members'])
            return len(members) == region['count'] and set(members)<=requested and all(
                color is None or self.objects[n].get('color_name', self.objects[n].get('identity', '').split('_')[0]) == color
                for n in members)
        return members == set(region['members'])

    def unchanged(self, name):
        a, b = self.state[name], self.initial[name]
        return np.linalg.norm(a['pos']-b['pos']) <= .003 and np.linalg.norm(a['mat']-b['mat']) <= .03

    def order_correct(self, rule):
        anchor = self.state[rule['actor']]
        relative = {n: anchor['mat'].T @ (self.state[n]['pos']-anchor['pos']) for n in rule['pieces']}
        order = sorted(rule['pieces'], key=lambda n: relative[n][rule.get('axis', 0)], reverse=rule.get('descending',False))
        if order != rule['expected_order']: return False
        if any(np.max(np.abs(relative[n][:len(xyz)]-np.asarray(xyz)))>.015 for n,xyz in rule.get('preserved_positions',{}).items()):return False
        for n, yaw in rule['expected_yaws'].items():
            rot = anchor['mat'].T @ self.state[n]['mat']
            actual = math.atan2(rot[1, 0], rot[0, 0])
            if abs((actual-yaw+math.pi) % (2*math.pi)-math.pi) > math.radians(12): return False
            if n in rule.get('expected_rotations',{}):
                error=rot@np.asarray(rule['expected_rotations'][n]).T
                angle=math.acos(float(np.clip((np.trace(error)-1)/2,-1,1)))
                if angle>math.radians(12):return False
        h=np.asarray(self.objects[rule['actor']]['size'])
        region=dict(actor=rule['actor'],lower=(-h+np.array([.006,.006,.006])).tolist(),upper=h.tolist())
        supported=self.grounded(rule['actor'])
        return all(self.released(n) and self.contact(n, rule['actor']) and self.contained(n,region) and n in supported for n in rule['pieces'])

    def package_correct(self, package):
        region = dict(package, actor=package['container'], candidates=package['members'])
        if package['members'] and self.members(region) != set(package['members']): return False
        # Check every level of the physical shipment, including inner box lids.
        # The outer box's own lid caps its cavity; it is not cavity contents.
        packages={p['container']:p for p in self.design['packages']}
        order=self.design.get('local_order')
        def descendants(actor,trail):
            if actor in trail:return None
            direct=set(packages.get(actor,{}).get('members',[]))
            if actor!=package['container'] and packages.get(actor,{}).get('lid'):
                direct.add(packages[actor]['lid'])
            for r in self.design['local_regions']:
                if r['actor']==actor:direct.update(self.members(r))
            if order and order['actor']==actor:direct.update(order['pieces'])
            result=set(direct)
            for child in direct:
                nested=descendants(child,trail|{actor})
                if nested is None:return None
                result.update(nested)
            return result
        children=descendants(package['container'],set())
        if children is None:return False
        if children and any(not self.contained(n,region) for n in children):return False
        lid = package.get('lid')
        if lid:
            a, b = self.state[package['container']], self.state[lid]
            local = a['mat'].T @ (b['pos']-a['pos'])
            if np.linalg.norm(local-np.asarray(package['lid_local_center'])) > package.get('lid_position_tolerance',.008): return False
            if np.linalg.norm(a['mat'].T @ b['mat']-np.eye(3)) > package.get('lid_orientation_tolerance',.08): return False
            support=self.contact(lid, package['container'])
            index=package.get('hinge_joint_index')
            if index is not None:
                j=self.spec['joints'][index]
                valid=j.get('type')=='revolute' and j.get('parent')==package['container'] and j.get('child')==lid
                valid=valid and np.linalg.norm(a['pos']+a['mat']@np.asarray(j['anchor0'])-b['pos']-b['mat']@np.asarray(j['anchor1'])) < .008
                support=support or valid
            if not support or not self.released(lid): return False
        return True

    def destination_correct(self):
        name = self.design['delivery_actor']; zone = self.zones[self.design['destination_zone']]
        s = self.state[name]; center,half=self.world_bounds(name)
        within = np.all(np.abs(center[:2]-np.asarray(zone['xy']))+half[:2] <= np.asarray(zone['half_size'])+.003)
        support = self.design.get('delivery_support_actor', zone.get('support', 'table'))
        return bool(within and self.released(name) and self.contact(name, support))

    def grounded(self, required_root=None):
        # Roots require real table contact and matching bottom height. A floating
        # contact-connected cluster cannot establish a support root.
        reached = set()
        for n,o in self.objects.items():
            s = self.state[n];center,half=self.world_bounds(n)
            if required_root in (None,'table') and self.contact(n,'table') and abs(center[2]-half[2]-.8) < .02:
                reached.add(n)
            for i,f in enumerate(self.spec.get('fixtures',[])):
                if required_root not in (None,'fixture'+str(i)) or f.get('type')!='box' or not self.contact(n,'fixture'+str(i)):continue
                top=f['z']+f['size'][2]
                if abs(center[2]-half[2]-top)<.015 and np.all(np.abs(center[:2]-np.asarray(f['xy'])) <= np.asarray(f['size'][:2])+.003):
                    reached.add(n)
        if required_root in self.objects:
            reached={required_root} if required_root in self.grounded() else set()
        edges = []
        for base,o in self.objects.items():
            a=self.state[base]
            if a['mat'][2,2]<.95:continue
            for n in self.objects:
                if n==base or not self.contact(n,base):continue
                center,half=self.world_bounds(n);bc,bh=self.world_bounds(base)
                # The top of a compound's enclosing bounds can be empty space
                # between its walls. Only a covering plate may use that rim
                # envelope; smaller cargo must match an actual support face.
                covering_rim=np.all(np.abs(center[:2]-bc[:2])+bh[:2] <= half[:2]+.003)
                if (not o.get('collision_shapes') or covering_rim) and center[2]>bc[2] and abs(center[2]-half[2]-bc[2]-bh[2])<.012 and np.all(np.abs(center[:2]-bc[:2])<half[:2]+bh[:2]):
                    edges.append((base,n))
                for shape in o.get('collision_shapes',[]):
                    if shape.get('type')!='box':continue
                    pos=np.asarray(shape.get('pos',[0,0,0]));size=np.asarray(shape['size'])
                    q=np.asarray(shape.get('quat',[1,0,0,0]),float)
                    if q.shape!=(4,) or not np.isfinite(q).all() or abs(np.linalg.norm(q)-1)>.001:continue
                    w,x,y,z=q
                    rotation=np.array([[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],
                                       [2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],
                                       [2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]])
                    world_rotation=a['mat']@rotation
                    # Only an upward-facing physical top can support cargo;
                    # a touching wall does not become a floor. Recipe boxes
                    # all author quat, including the identity quaternion.
                    if world_rotation[2,2]<.95:continue
                    local=world_rotation.T@(center-a['pos']-a['mat']@pos)
                    radius=np.abs(world_rotation.T@self.state[n]['mat'])@np.asarray(self.objects[n]['size'])
                    # A genuine narrow cradle can carry a wider object. Its
                    # measured contact, bottom height and center projection
                    # must agree with this upward support face; requiring the
                    # entire cargo bounds inside the face rejects real rails.
                    if abs(local[2]-radius[2]-size[2])<.012 and np.all(np.abs(local[:2]) <= size[:2]+.003):
                        edges.append((base,n));break
        for region in [*self.design['local_regions'],*self.design.get('cleanup_regions',[])]:
            if region['actor']:
                edges += [(region['actor'],n) for n in self.members(region)]
        for p in self.design['packages']:
            r = dict(p,actor=p['container'],candidates=p['members'])
            edges += [(p['container'],n) for n in self.members(r)]
            if p.get('lid') and self.package_correct(p): edges.append((p['container'],p['lid']))
        for j in self.spec.get('joints',[]):
            if j.get('parent') in self.state and j.get('child') in self.state and self.measured_joint_support(j['child']):
                edges.append((j['parent'],j['child']))
        # Ordered pieces use the same measured upward support faces as every
        # other actor. A side contact with their carrier is not a support edge.
        while True:
            more={b for a,b in edges if a in reached and b not in reached}
            if not more: break
            reached.update(more)
        return reached

    def update(self, state, contacts, dt):
        try:
            if not math.isfinite(dt) or dt <= 0 or dt > .1: raise ValueError('Fresh native substep required')
            clean = {}
            for n in self.objects:
                s = state[n]; p = np.asarray(s['pos'], float); m = np.asarray(s['mat'], float); g = s['grasp']
                if p.shape != (3,) or m.shape != (3,3) or not np.isfinite(p).all() or not np.isfinite(m).all() or not np.allclose(m.T@m, np.eye(3), atol=1e-4) or not np.isclose(np.linalg.det(m), 1) or len(g) != 2 or any(not isinstance(v,(bool,np.bool_)) for v in g):
                    raise ValueError('Invalid native pose/grasp')
                clean[n] = dict(pos=p.copy(), mat=m.copy(), grasp=tuple(g))
            if any(not isinstance(p, frozenset) or len(p) != 2 for p in contacts): raise ValueError('Native contact pairs required')
            self.state, self.contacts = clean, set(contacts)
            if self.initial is None: self.initial = deepcopy(clean)
            self.steps += 1; self.elapsed += dt
            regions = self.design['local_regions']
            observed = {r['id']: self.members(r) for r in regions}
            local = all(self.region_correct(r, observed[r['id']]) for r in regions) if self.task != 'E09' else True
            if self.task == 'E09':
                local = sorted(sorted(v) for v in observed.values()) == sorted(sorted(r) for r in self.design['unordered_expected_groups'])
            if 'local_order' in self.design: local = local and self.initial_order_rule is not None and self.order_correct(self.initial_order_rule)
            for r in regions:
                candidates=set(self.design['target_members']) | set(self.design.get('unused_members',[])) | set(self.design.get('distractor_members',[]))
                inside={n for n in candidates if n!=r['actor'] and self.contained(n,r)}
                if inside != observed[r['id']]: local=False
            for region, names in self.design.get('initial_preserved', {}).items():
                cavity=next(r for r in regions if r['id']==region)
                # A brief contact dropout/bounce during physical tray transport
                # is not removal. Taking out or gripping an original chip is.
                if self.initial_sealed and any(not self.contained(n,cavity) or not self.released(n) for n in names):self.preservation_failed=True
            if self.initial_sealed and any(not self.unchanged(n) or not self.released(n) for n in self.design.get('reference_objects', [])): self.reference_failed = True
            preservation = not self.preservation_failed and not self.reference_failed
            packaging = all(self.package_correct(p) for p in self.design['packages'])
            cleanup = all(self.region_correct(r, self.members(r)) for r in self.design.get('cleanup_regions', []))
            # Unused objects may be handled but must return to their designated supply region.
            if self.task == 'E20':
                used = set().union(*observed.values())
                supply = self.design.get('unused_supply_bounds')
                supply_roots=self.design.get('unused_supply_supports',[self.design.get('unused_supply_support','table')])
                if not isinstance(supply_roots,list) or not supply_roots or any(not isinstance(x,str) for x in supply_roots):
                    raise ValueError('Explicit unused supply support roots required')
                supported=set().union(*(self.grounded(root) for root in supply_roots))
                cleanup = cleanup and supply is not None and all(self.contained(n,dict(supply,actor=None)) and self.released(n) and n in supported for n in set(self.design['target_members'])-used)
            if self.task == 'E17': packaging = packaging and cleanup
            delivery = self.destination_correct() and cleanup and preservation
            relevant = set(self.design['target_members']) | {self.design['delivery_actor']}
            for p in self.design['packages']:
                relevant.add(p['container'])
                if p.get('lid'): relevant.add(p['lid'])
            relevant |= set(self.design.get('reference_objects', []))
            for r in self.design.get('cleanup_regions',[]):
                relevant.update(r.get('members',[]))
                if r['actor']: relevant.add(r['actor'])
            stable = self.anchor is not None and all(np.linalg.norm(clean[n]['pos']-self.anchor[n]['pos']) <= self.design.get('stability',{}).get('translation_envelope_m',.002) and np.linalg.norm(clean[n]['mat']-self.anchor[n]['mat']) <= self.design.get('stability',{}).get('rotation_matrix_envelope',.02) for n in relevant)
            released = all(self.released(n) for n in relevant)
            grounded = self.grounded()
            local_supported = set(self.design['target_members']) <= grounded
            physically_supported = relevant <= grounded
            if not stable or not released or not physically_supported: self.anchor = deepcopy(clean); self.hold_seconds = 0.
            if released and physically_supported: self.hold_seconds += dt
            settled = self.initial_sealed and local_supported and self.hold_seconds >= self.design.get('stability', {}).get('seconds', .5)
            self.current = dict(local=bool(local and preservation and settled), packaging=bool(local and packaging and physically_supported and preservation and settled), delivery=bool(local and packaging and physically_supported and delivery and settled))
            self.observation = dict(region_members={k:sorted(v) for k,v in observed.items()},preservation_valid=preservation,cleanup_valid=cleanup,settled=settled)
            for key,value in self.current.items():
                if value and not any(m['stage']==key for m in self.milestones):
                    self.milestones.append(dict(stage=key,step=self.steps,elapsed_seconds=self.elapsed,poses={n:dict(pos=clean[n]['pos'].tolist(),mat=clean[n]['mat'].tolist()) for n in relevant},contacts=[sorted(p) for p in self.contacts]))
            self.previous = deepcopy(clean)
        except (KeyError, ValueError, TypeError, IndexError) as exc:
            self.history_valid = False; self.errors.append(str(exc)); self.current = dict(local=False,packaging=False,delivery=False)

    def result(self):
        available = self.history_valid and bool(self.state) and self.steps>0 and self.initial_sealed
        checks = {k: bool(v and available) for k,v in self.current.items()}
        missing=[]
        if not self.state or not self.steps:missing.append('missing_native_snapshot')
        if not self.initial_sealed:missing.append('initial_state_not_sealed')
        if not self.history_valid:missing.append('invalid_native_history')
        score = sum(w for k,w in [('local',35),('packaging',25),('delivery',40)] if checks[k]) if available else None
        return deepcopy(dict(success=all(checks.values()),strict_success=all(checks.values()),process_score=score,task_score_100=score,engineering_score_100=score,scored=available,unscored=not available,progress_available=available,native_evidence_valid=available,missing_evidence=missing,
            conditions=[dict(index=i,type=k,passed=v)for i,(k,v)in enumerate(checks.items())],failed_checks=[k for k,v in checks.items()if not v],observation=self.observation,hold_seconds=self.hold_seconds,
            history_valid=bool(self.history_valid and self.state and self.steps),errors=self.errors,progress_evidence=dict(initial=dict(sealed=self.initial_sealed,poses={n:dict(pos=v['pos'].tolist(),mat=v['mat'].tolist())for n,v in (self.initial or {}).items()})),milestones=self.milestones,events=self.events,event_history={},backend='isaaclab_physx',protocol=self.design['schema'],execution_design_revision=self.design.get('revision'),execution_design_source_sha256=self.design.get('source_sha256'),task_score_native_physics_verified=False,scoring_validation_status='native_positive_negative_controls_pending'))
