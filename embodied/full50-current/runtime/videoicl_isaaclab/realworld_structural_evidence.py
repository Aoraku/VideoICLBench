"""Actual geometric/contact/history evidence for the last ten RealWorld50 tasks.

StructuralTaskEvaluator supports E01/E03/E08/E10/E12/E17/E19/E23/E24/E37.
Controller supplies fresh force maps and (when referenced) mechanism snapshots
before every update. No goal, desired slot, selected set, desired color order or
expert command is read. ABC rules remain solely in check_task.

All geometry below is reviewed *loaded body-local* geometry, after source
centering/scaling. ref={actor:rigidID} or {mechanism,body,contact_body}.

containers.<key>={ref,shape:'box'|'cylinder',lower:[3],upper:[3],axis:2,
  radius_profile:[[height,inner_radius],...] (cylinder)}. E01 uses plate and
only footprint/floor seating; E08/E24 use box and full containment.
cups.<actor>={axis_local:[3],bottom_local:[3],rim_local:[3],
  inner_profile:[[height,radius],...],outer_profile:[[height,radius],...]};
height is measured from bottom_local along axis_local. Taper/partial nesting is
checked against the actual overlapping profiles, not an all-AABB-inside test.
shoe_axes.<actor>={toe_local,heel_local}; label_end={ref,point_local}.
posts=[{ref,base_local,tip_local,radius}], holes.<actor>=[{center_local,
 axis_local,radius,half_depth},...]. Every source hole needs a distinct real post.
slots.<integer string>={ref,holes:[{center_local,axis_local,u_local,
 half_size:[2],depth},...]}; pins.<charger>=[{tip_local,axis_local,u_local,
 half_size:[2],length},...]. Both pins need depth, axis, cross-section and contact.
shelves.<lower|upper>={ref,center_local,normal_local,u_local,half_size:[2]}.
mouths.<bottle>={center_local,axis_local,inner_radius,outer_radius};
caps.<cap>={center_local,axis_local,inner_radius,outer_radius,depth}.
branches.<id>={ref,base_local,tip_local,radius}; levels derive from actual tip Z.
lid_geometry={ref,box_ref,cover_center_local,normal_local,half_size:[2],
 box_rim_center_local,box_rim_half_size:[2],closed_offset_m}; lid has a free
rigid body. Close events require real covering/contact and a hand release.
screw_roles.<left|right>={screw,fixture:{ref,origin_local,axis_local,
 interval:[lo,hi],bore_radius},thread_base_local,axis_local,radial_local,
 thread_length,thread_radius,pitch_m,unscrew_direction:+1|-1,
 head_socket_local,socket_radius,socket_depth,
 driver:{actor,tip_local,axis_local,tip_radius}}. Free-body screw rotation is
unwrapped against the fixture frame. Thread overlap is geometric and initial
engagement requires real fixture contact; no nonexistent helical joint assumed.
"""
from collections.abc import Mapping
from copy import deepcopy
import itertools
import math
import numpy as np

from .inference_generalization import e24_yarn_rule
from .realworld_tool_evidence import ToolTaskEvaluator, _unit
from .realworld_mechanism_evidence import _finite, _rotation, FINGERS
from .realworld_stability import for_evaluator as stability_policy

SUPPORTED=('E01','E03','E08','E10','E12','E17','E19','E23','E24','E37')
GROUPS={'E01':'food','E03':'cups','E08':'shoes','E10':'pieces','E12':'chargers','E17':'pieces','E19':'caps','E23':'cups','E24':'cups','E37':'screws'}


def _profile(value):
    p=np.asarray(value,float)
    if p.ndim!=2 or p.shape[1]!=2 or len(p)<2 or not np.isfinite(p).all() or np.any(np.diff(p[:,0])<=0) or np.any(p[:,1]<=0):raise ValueError('Measured monotonic height/radius profile required')
    return p


def _radius(profile,height):
    p=_profile(profile)
    if height<p[0,0]-.001 or height>p[-1,0]+.001:return None
    return float(np.interp(height,p[:,0],p[:,1]))


def _basis(axis,u):
    axis=_unit(axis);u=_unit(u);u=u-axis*float(u@axis)
    if np.linalg.norm(u)<.9:raise ValueError('Reviewed cross axis must be perpendicular to insertion axis')
    u=_unit(u);return axis,u,np.cross(axis,u)


def _refs(value):
    if isinstance(value,Mapping):
        if all(k in value for k in ('mechanism','body','contact_body')):yield value
        for child in value.values():yield from _refs(child)
    elif isinstance(value,(list,tuple)):
        for child in value:yield from _refs(child)


class StructuralTaskEvaluator(ToolTaskEvaluator):
    def __init__(self,spec):
        self.spec=deepcopy(spec);self.task,self.variant=spec['id'],spec['variant']
        if self.task not in SUPPORTED:raise NotImplementedError(self.task+': structural evidence unavailable')
        if self.task=='E08':
            from .e08_original_source_geometry import bind_original_e08_evaluator_geometry
            bind_original_e08_evaluator_geometry(self.spec)
            spec=self.spec
        self.objects={o['id']:o for o in spec['objects']};self.zones={z['id']:z for z in spec.get('zones',[])};self.semantic=spec['semantic']
        if len(self.objects)!=len(spec['objects']):raise ValueError('Duplicate structural actor IDs')
        self.fingers=self.semantic.get('interactors',list(FINGERS));self.tool=None;self.clips={};self.crease=None
        self.references=list(_refs(self.semantic));self.required_mechanisms={r['mechanism'] for r in self.references}
        self.targets=self.group(GROUPS[self.task],[])
        if self.task=='E37':self.targets=[r['screw'] for r in self.semantic.get('screw_roles',{}).values()]
        if self.task=='E24':
            lid=self.semantic.get('lid_geometry',{}).get('ref',{}).get('actor')
            if lid:self.targets=[*self.targets,lid]
        if not self.targets or len(set(self.targets))!=len(self.targets) or not set(self.targets)<=set(self.objects):raise ValueError('Explicit structural target identities required')
        if self.task=='E37' and set(self.semantic.get('screw_roles',{}))!={'left','right'}:raise ValueError('Two measured screw fixtures required')
        self._validate_shoe_geometry_contract()
        self.check=self._check;self.reset_episode()

    def _validate_shoe_geometry_contract(self):
        if self.task!='E08' or 'source_acceptance_geometry' not in self.semantic:return
        if self.semantic['source_acceptance_geometry']!='E08-source-geometry-v1':
            raise ValueError('Unknown E08 source geometry contract')
        for name in self.group('shoes',[]):
            obj=self.objects[name];source_sha=obj.get('source_asset',{}).get('sha256')
            if (not isinstance(source_sha,str) or len(source_sha)!=64
                    or any(c not in '0123456789abcdef' for c in source_sha)
                    or obj.get('containment_points_source_sha256')!=source_sha):
                raise ValueError('E08 source geometry contract requires matching source SHA')
            points=np.asarray(obj.get('containment_points_local'),float)
            if points.ndim!=2 or points.shape[1]!=3 or len(points)<4 or not np.isfinite(points).all():
                raise ValueError('E08 source geometry contract requires actual containment points')

    def reset_episode(self):
        super().reset_episode();self.touched=set();self.release_pending=set();self.first_insertions={};self.lid_close_step=None;self.lid_previous_closed=None
        self.branch_levels=None;self.screw_initial={};self.screw_previous={};self.screw_angles={};self.screw_traces={};self.thread_history_valid=True
        self.progress_screw_drives={}
        self.event_history.update(placement_events=[],lid_events=[],screw_records={})

    def frame(self,ref,state=None):
        if 'actor' in ref:
            value=(self.state if state is None else state)[ref['actor']];return value['pos'],value['mat']
        return self.body(ref['mechanism'],ref['body'])
    def contact_id(self,ref):return ref['actor'] if 'actor' in ref else ref['contact_body']
    def point(self,ref,local,state=None):
        p,r=self.frame(ref,state);return p+r@_finite(local,(3,))
    def axis(self,ref,local):return self.frame(ref)[1]@_unit(local)
    def corners(self,name,ref):
        obj=self.objects[name];v=self.state[name];half=_finite(obj['size'],(3,));center=_finite(obj.get('local_bounds_center',[0,0,0]),(3,))
        points=np.array(list(itertools.product((-1,1),repeat=3)))*half+center
        world=points@v['mat'].T+v['pos'];p,r=self.frame(ref);return (world-p)@r
    def _target_stable(self,released):
        settling=stability_policy(self)
        anchored=self.target_anchor is not None and all(np.linalg.norm(self.state[n]['pos']-self.target_anchor[n]['pos'])<=settling.translation_m and np.linalg.norm(self.state[n]['mat']-self.target_anchor[n]['mat'])<=settling.rotation_matrix for n in self.targets)
        if released and self.history_valid:
            if not anchored:self.target_anchor={n:deepcopy(self.state[n]) for n in self.targets};self.target_hold=0.
            else:self.target_hold+=self.dt
        else:self.target_anchor=None;self.target_hold=0.
        self.hold_seconds=self.target_hold;return self.target_hold>=settling.seconds

    def contained(self,key,names,footprint_only=False):
        self._validate_shoe_geometry_contract()
        c=self.semantic['containers'][key];ref=c['ref'];lo=_finite(c['lower'],(3,));hi=_finite(c['upper'],(3,));axis=int(c.get('axis',2))
        if axis not in (0,1,2) or np.any(hi<=lo) or c.get('shape') not in ('box','cylinder'):raise ValueError('Reviewed cavity geometry required')
        lateral=[i for i in range(3) if i!=axis];inside=[];supported=[]
        if c['shape']=='cylinder':_profile(c['radius_profile'])
        for name in names:
            obj=self.objects[name]
            if self.task=='E08' and 'containment_points_local' in obj:
                # An irregular source shoe's bounding-box corners are empty
                # space, and can lie outside a box that contains its real mesh.
                # Use only explicitly reviewed, source-bound body-local points;
                # cavity bounds, contacts and tolerances below are unchanged.
                source_sha=obj.get('source_asset',{}).get('sha256')
                declared_sha=obj.get('containment_points_source_sha256')
                if (not isinstance(source_sha,str) or len(source_sha)!=64
                        or any(char not in '0123456789abcdef' for char in source_sha)
                        or declared_sha!=source_sha):
                    raise ValueError('E08 containment points require matching source asset SHA256')
                local=np.asarray(obj['containment_points_local'],float)
                if (local.ndim!=2 or local.shape[1]!=3 or len(local)<4
                        or not np.isfinite(local).all()):
                    raise ValueError('E08 containment points require finite Nx3 source geometry')
                value=self.state[name];origin,rotation=self.frame(ref)
                points=(local@value['mat'].T+value['pos']-origin)@rotation
            else:
                points=self.corners(name,ref)
            axial=np.min(points[:,axis])>=lo[axis]-.003 and (footprint_only or np.max(points[:,axis])<=hi[axis]+.003)
            if c['shape']=='box':radial=np.all(points[:,lateral]>=lo[lateral]-.002) and np.all(points[:,lateral]<=hi[lateral]+.002)
            else:
                radial=True
                for point in points:
                    height=float(np.clip(point[axis],lo[axis],hi[axis]));radius=_radius(c['radius_profile'],height)
                    radial=radial and radius is not None and np.linalg.norm(point[lateral])<=radius+.001
            if axial and radial:
                inside.append(name)
                if self.force(name,self.contact_id(ref))>0 and abs(float(points[:,axis].min()-lo[axis]))<=.012:supported.append(name)
        if self.task=='E08' and self.semantic.get('require_box_floor_or_other_shoe_contact'):
            # Start with shoes directly seated on the measured box floor, then
            # follow real shoe contacts. Floating cycles, outside shoes and
            # robot-held shoes cannot seed a support path.
            free={n for n in inside if not any(self.state[n]['grasp']) and self.hand_force(n)==0}
            grounded=set(supported)&free
            while True:
                more={n for n in free-grounded if any(self.force(n,b)>0 for b in grounded)}
                if not more:break
                grounded.update(more)
            supported=[n for n in inside if n in grounded]
        return inside,supported

    def cup(self,name):
        g=self.semantic['cups'][name];v=self.state[name];axis=v['mat']@_unit(g['axis_local']);bottom=v['pos']+v['mat']@_finite(g['bottom_local'],(3,));rim=v['pos']+v['mat']@_finite(g['rim_local'],(3,))
        _profile(g['inner_profile']);_profile(g['outer_profile'])
        if float((rim-bottom)@axis)<=0:raise ValueError('Cup bottom/mouth axis contradicts measured geometry')
        return g,axis,bottom,rim

    def nested(self,outer,inner):
        a,aa,ab,ar=self.cup(outer);b,ba,bb,br=self.cup(inner)
        if aa[2]<.95 or ba[2]<.95 or float(aa@ba)<.995 or self.force(outer,inner)<=0:return False
        height=float((bb-ab)@aa);rimheight=float((ar-ab)@aa);offset=np.linalg.norm((bb-ab)-height*aa)
        if height<-.001 or rimheight-height<.008:return False
        profile=_profile(b['outer_profile']);upper=min(profile[-1,0],rimheight-height)
        if upper<=0:return False
        samples=sorted(set([0.,upper,*[float(x) for x in profile[:,0] if 0<x<upper]]))
        for local_z in samples:
            ri=_radius(profile,local_z);ro=_radius(a['inner_profile'],height+local_z)
            if ri is None or ro is None or offset+ri>ro+.001:return False
        return True

    def threaded(self,name,posts):
        holes=self.semantic['holes'][name];matches=[]
        if not holes:raise ValueError('Measured physical hole list required')
        for h in holes:
            center=self.point({'actor':name},h['center_local']);normal=self.axis({'actor':name},h['axis_local']);candidates=[]
            for i,p in enumerate(posts):
                base=self.point(p['ref'],p['base_local']);tip=self.point(p['ref'],p['tip_local']);axis=_unit(tip-base);length=float(np.linalg.norm(tip-base));cos=float(axis@normal)
                if abs(cos)<.98:continue
                along=float((center-base)@normal/cos);cross=base+along*axis;offset=float(np.linalg.norm(cross-center))
                # The shaft must cross the bore midplane and extend beyond
                # its upper face. Real board support is checked separately;
                # a lower-face seating window wrongly rejects native contact
                # settlement below the analytical base datum.
                if 0<along<length-h['half_depth']-.001 and offset+p['radius']<=h['radius']+.0005:candidates.append(i)
            matches.append(candidates)
        return any(len(set(assignment))==len(holes) for assignment in itertools.product(*matches))

    def inserted_slot(self,name,slot):
        pins=self.semantic['pins'][name];holes=slot['holes'];ref=slot['ref']
        if len(pins)!=2 or len(holes)!=2:return False
        if self.force(name,self.contact_id(ref))<=0:return False
        pmat=self.state[name]['mat'];hmat=self.frame(ref)[1];possible=[]
        for pin in pins:
            tip=self.point({'actor':name},pin['tip_local']);pa,pu,pv=_basis(pin['axis_local'],pin['u_local']);pa,pu,pv=(pmat@x for x in (pa,pu,pv));radii=_finite(pin['half_size'],(2,));matched=[]
            for i,hole in enumerate(holes):
                center=self.point(ref,hole['center_local']);ha,hu,hv=_basis(hole['axis_local'],hole['u_local']);ha,hu,hv=(hmat@x for x in (ha,hu,hv));offset=tip-center;depth=-float(offset@ha)
                extent=np.array([abs(float(pu@hu))*radii[0]+abs(float(pv@hu))*radii[1],abs(float(pu@hv))*radii[0]+abs(float(pv@hv))*radii[1]])
                lateral=np.abs([float(offset@hu),float(offset@hv)])
                if float(pa@ha)<-.98 and .5*pin['length']<=depth<=hole['depth']+.0005 and np.all(lateral+extent<=np.asarray(hole['half_size'])+.0002):matched.append(i)
            possible.append(matched)
        return any(a!=b for a in possible[0] for b in possible[1])

    def layer(self,name,shelf):
        ref=shelf['ref'];p=self.point(ref,shelf['center_local']);axis,u,v=_basis(shelf['normal_local'],shelf['u_local']);r=self.frame(ref)[1];axis,u,v=(r@x for x in (axis,u,v))
        center,half=self.bounds(name);bottom=center-np.array([0,0,half[2]]);delta=bottom-p
        if axis[2]<.95:return False
        points=self.corners(name,ref);local_center=_finite(shelf['center_local'],(3,));_,lu,lv=_basis(shelf['normal_local'],shelf['u_local'])
        footprint=np.max(np.abs((points-local_center)@np.stack([lu,lv],axis=1)),axis=0)
        return abs(float(delta@axis))<=.012 and np.all(footprint<=np.asarray(shelf['half_size'])+.002)

    def covering_cap(self,bottle,cap):
        mouth=self.semantic['mouths'][bottle];cover=self.semantic['caps'][cap];bp=self.point({'actor':bottle},mouth['center_local']);ba=self.axis({'actor':bottle},mouth['axis_local']);cp=self.point({'actor':cap},cover['center_local']);ca=self.axis({'actor':cap},cover['axis_local']);delta=bp-cp;depth=float(delta@ca);offset=float(np.linalg.norm(delta-depth*ca))
        return (float(ba@ca)>.98 and 0<=depth<=cover['depth']+.001 and offset+mouth['outer_radius']<=cover['inner_radius']+.001
                and cover['outer_radius']>=mouth['inner_radius'] and self.force(bottle,cap)>0)

    def branch_inside(self,cup,branch):
        g,axis,bottom,rim=self.cup(cup);ref=branch['ref'];base=self.point(ref,branch['base_local']);tip=self.point(ref,branch['tip_local']);delta=tip-base;den=float(delta@axis)
        if abs(den)<1e-7:return False
        t=float((rim-base)@axis/den)
        if not 0<=t<=1:return False
        cross=base+t*delta;height=float((rim-bottom)@axis);radius=_radius(g['inner_profile'],height)
        if radius is None or np.linalg.norm(cross-rim)+branch['radius']>radius+.001:return False
        penetration=-float((tip-rim)@axis)
        if penetration<.008:return False
        h=float((tip-bottom)@axis);r=_radius(g['inner_profile'],h);radial=np.linalg.norm((tip-bottom)-h*axis)
        return r is not None and radial+branch['radius']<=r+.001 and self.force(cup,self.contact_id(ref))>0

    def lid_closed(self):
        lid=self.semantic['lid_geometry'];lr=lid['ref'];br=lid['box_ref'];lp=self.point(lr,lid['cover_center_local']);bp=self.point(br,lid['box_rim_center_local']);normal=self.axis(lr,lid['normal_local']);bmat=self.frame(br)[1];delta=lp-bp
        # Source box/lid planes are local XY. Reviewed normals are explicit,
        # and source conversion must align the box cavity axis to local +Z.
        expected=bmat[:,2];required=_finite(lid['box_rim_half_size'],(2,));lmat=self.frame(lr)[1]
        rim_corners=np.array([[sx*required[0],sy*required[1],0.] for sx,sy in itertools.product((-1,1),repeat=2)])@bmat.T+bp
        in_lid=(rim_corners-lp)@lmat
        return (float(normal@expected)>.98 and abs(float(delta@expected)-lid['closed_offset_m'])<=.008
                and np.all(np.abs(in_lid[:,:2])<=_finite(lid['half_size'],(2,))+.002) and self.force(self.contact_id(lr),self.contact_id(br))>0)

    def _placements(self,inside,supported):
        touched={n for n in self.targets if any(self.state[n]['grasp']) or self.hand_force(n)>0}
        self.touched.update(touched)
        if self.previous is not None:
            for name in self.targets:
                was=any(self.previous[name]['grasp']) or name in getattr(self,'previous_touched',set())
                if was and name not in touched:self.release_pending.add(name)
        self.previous_touched=touched
        for name in inside:
            if name in supported and name in self.release_pending and name not in touched and name not in self.first_insertions:
                event=dict(object=self.label(name),target='box',step=self.steps,released=True,support_contact=True)
                self.first_insertions[name]=event;self.event_history['placement_events'].append(event);self.events.append(dict(event='first_released_in_box',**event))
        closed=self.lid_closed();lidname=self.contact_id(self.semantic['lid_geometry']['ref'])
        if closed and lidname in self.release_pending and lidname not in touched and self.lid_previous_closed is False:
            self.lid_close_step=self.steps;event=dict(event='lid_closed_after_release',step=self.steps);self.events.append(event);self.event_history['lid_events'].append(event)
        # Closed while still held is not a release event. Its first subsequent
        # release remains a legitimate closing transition.
        self.lid_previous_closed=closed and lidname not in touched

    def screw_measure(self,entry):
        name=entry['screw'];fixture=entry['fixture'];ref=fixture['ref'];origin=self.point(ref,fixture['origin_local']);axis=self.axis(ref,fixture['axis_local']);base=self.point({'actor':name},entry['thread_base_local']);sa=self.axis({'actor':name},entry['axis_local']);delta=base-origin;low=float(delta@axis);high=low+entry['thread_length']*float(sa@axis);a,b=fixture['interval'];overlap=max(0.,min(high,b)-max(low,a));radial=np.linalg.norm(delta-low*axis)
        radial_axis=self.axis({'actor':name},entry['radial_local']);fr=self.frame(ref)[1];local=fr.T@radial_axis;fa=_unit(fixture['axis_local']);seed=np.array([1.,0,0]) if abs(fa[0])<.9 else np.array([0.,1,0]);u=_unit(seed-fa*float(seed@fa));v=np.cross(fa,u);angle=math.atan2(float(local@v),float(local@u))
        aligned=float(sa@axis)>.98 and radial+entry['thread_radius']<=fixture['bore_radius']+.001
        driver=entry['driver'];tip=self.point({'actor':driver['actor']},driver['tip_local']);head=self.point({'actor':name},entry['head_socket_local']);td=tip-head;depth=-float(td@sa);offset=np.linalg.norm(td+depth*sa);toolaxis=self.axis({'actor':driver['actor']},driver['axis_local']);cos=abs(float(toolaxis@sa))
        engaged=0<depth<=entry['socket_depth']+.001 and offset+driver['tip_radius']<=entry['socket_radius']+.0003
        return dict(angle=angle,axial=low,overlap=overlap,aligned=aligned,fixture_contact=self.force(name,self.contact_id(ref)),driver_force=self.force(name,driver['actor']),depth=depth if engaged else 0.,cos=cos)

    def _screws(self):
        initial=[];separated=[];retained=[];records={};progress={}
        for role,entry in self.semantic['screw_roles'].items():
            if entry['pitch_m']<=0 or entry['unscrew_direction'] not in (-1,1):raise ValueError('Actual thread pitch/direction required')
            m=self.screw_measure(entry)
            if role not in self.screw_initial:
                self.screw_initial[role]=deepcopy(m);self.screw_angles[role]=0.;self.screw_traces[role]=[]
            init=self.screw_initial[role];previous=self.screw_previous.get(role)
            if init['overlap']>.001 and init['aligned'] and init['fixture_contact']>0:initial.append(role)
            if previous:
                delta=(m['angle']-previous['angle']+math.pi)%(2*math.pi)-math.pi;self.screw_angles[role]+=delta*entry['unscrew_direction']
            angle=self.screw_angles[role];axial=m['axial']-init['axial'];is_separated=m['overlap']<=1e-6 and m['fixture_contact']==0
            sample=dict(step=self.steps,angle_rad=angle,axial_m=axial,thread_overlap_m=m['overlap'],driver_contact_force=m['driver_force'],tip_engagement_depth_m=m['depth'],tool_axis_alignment_cos=m['cos'],separated=is_separated)
            self.screw_traces[role].append(sample)
            # During engagement, axial travel must track the measured thread
            # pitch. A free spin followed by a straight pull is not unscrewing.
            engaged_interval=m['overlap']>0 or (previous is not None and previous['overlap']>0)
            if engaged_interval and (abs(angle)>.05 or abs(axial)>.001):
                helix=abs(axial-angle*entry['pitch_m']/(2*math.pi))<=max(.0005,entry['pitch_m']*.20)
                self.thread_history_valid=self.thread_history_valid and helix and m['aligned']
            if is_separated:separated.append(role);records[role]=self.screw_traces[role]
            elif m['overlap']>.001 and m['fixture_contact']>0 and m['aligned']:retained.append(role)
            trace=self.screw_traces[role]
            drive=self.progress_screw_drives.setdefault(role,dict(rotation=0.,axial=0.,valid=True,undriven_anchor=None))
            if len(trace)>=2 and trace[-2]['thread_overlap_m']>0:
                a,b=trace[-2:]
                engaged=b['driver_contact_force']>0 and b['tip_engagement_depth_m']>0 and b['tool_axis_alignment_cos']>=.9
                if engaged:
                    drive['rotation']+=b['angle_rad']-a['angle_rad'];drive['axial']+=b['axial_m']-a['axial_m'];drive['undriven_anchor']=None
                else:
                    if drive['undriven_anchor'] is None:drive['undriven_anchor']=a['angle_rad']
                    if abs(b['angle_rad']-drive['undriven_anchor'])>.02:drive['valid']=False
            progress[role]=bool(role in initial and self.thread_history_valid and drive['valid'] and drive['rotation']>.05 and drive['axial']>.001 and angle>.05 and axial>.001)
            self.screw_previous[role]=m
        self.extra_checks['actual_thread_pitch_coupled_motion']=self.thread_history_valid
        return dict(initial_fastened=initial,separated=separated,remaining_fastened=retained,screw_records=records,screw_progress=progress)

    def derive(self,stable):
        self.extra_checks={};released=not any(any(self.state[n]['grasp']) or self.hand_force(n)>0 for n in self.targets)
        obs=dict(released=released,stable=self._target_stable(released) and self._mechanism_stable(),contacts=[list(p) for p in self.contacts]);t=self.task;names=self.group(GROUPS[t],[]) if t!='E37' else self.targets;labels=lambda ns:[self.label(n) for n in ns]
        for ref in self.references:self.frame(ref)
        if t=='E01':
            inside,supported=self.contained('plate',names,True);obs.update(in_plate=labels(inside),outside_plate=labels(set(names)-set(inside)),supported_in_plate=labels(supported))
        elif t=='E03':
            edges=[(a,b) for a in names for b in names if a!=b and self.nested(a,b)];orders=[order for order in itertools.permutations(names) if (order[0],order[1]) in edges and (order[1],order[2]) in edges]
            order=list(orders[0]) if len(orders)==1 else [];obs.update(outside_to_inside=labels(order),upright=labels([n for n in names if self.cup(n)[1][2]>.95]),nested_pairs=[self.label(a)+'>'+self.label(b) for a,b in zip(order[:-1],order[1:])],contacts=[[self.label(a),self.label(b)] for a,b in edges])
            self.extra_checks['outer_cup_has_actual_support']=bool(order and self.on_table(order[0]))
            # The legacy checker consumes only the unique full chain. Partial
            # scoring also needs real edges before all three cups are nested.
            obs['progress_nested_pairs']=[self.label(a)+'>'+self.label(b) for a,b in edges]
            obs['outer_supported']=labels([n for n in names if self.on_table(n)])
        elif t=='E08':
            inside,supported=self.contained('box',names);label=self.semantic['label_end'];center=self.frame(label['ref'])[0];direction=_unit(self.point(label['ref'],label['point_local'])-center);toward={}
            for name in names:
                g=self.semantic['shoe_axes'][name];axis=_unit(self.point({'actor':name},g['toe_local'])-self.point({'actor':name},g['heel_local']));cos=float(axis@direction)
                if abs(cos)>.9:toward[self.label(name)]='toe' if cos>0 else 'heel'
            obs.update(toward_label=toward,in_box=labels(inside),supported_in_box=labels(supported))
        elif t=='E10':
            posts=self.semantic['posts'];threaded=[n for n in names if self.threaded(n,posts)];supported=[]
            supports={self.contact_id(p['ref']) for p in posts}
            pending=set(names)
            while True:
                more={n for n in pending if any(self.force(n,base)>0 for base in supports)}
                if not more:break
                supported.extend(more);pending-=more;supports.update(more)
            on_post=set(threaded)
            for n in names:
                center,half=self.bounds(n)
                for p in posts:
                    base=self.point(p['ref'],p['base_local']);tip=self.point(p['ref'],p['tip_local']);axis=_unit(tip-base);delta=center-base;axial=float(delta@axis);radial=np.linalg.norm(delta-axis*axial)
                    extent=float(np.linalg.norm(half));near=radial<=extent+p['radius'] and -extent<=axial<=np.linalg.norm(tip-base)+extent
                    if near and self.force(n,self.contact_id(p['ref']))>0 and not self.on_table(n):on_post.add(n)
            obs.update(on_post=labels(on_post),threaded=labels(threaded),supported_on_post=labels(set(threaded)&set(supported)),off_post=labels(set(names)-on_post))
        elif t=='E12':
            matches={n:[int(k) for k,s in self.semantic['slots'].items() if self.inserted_slot(n,s)] for n in names};assign={self.label(n):v[0] for n,v in matches.items() if len(v)==1}
            obs.update(charger_to_slot=assign,physically_inserted=list(assign),supported=list(assign))
        elif t=='E17':
            layers={};supports={}
            for n in names:
                found=[(key,s) for key,s in self.semantic['shelves'].items() if self.layer(n,s)]
                if len(found)==1:
                    key,s=found[0];layers[self.label(n)]=key
                    if self.force(n,self.contact_id(s['ref']))>0:supports[self.label(n)]=key
            obs.update(layers=layers,support_layers=supports)
        elif t=='E19':
            matches={b:[c for c in self.semantic['caps'] if self.covering_cap(b,c)] for b in self.semantic['mouths']};mapping={self.label(b):self.label(cs[0]).removeprefix('cap_') for b,cs in matches.items() if len(cs)==1}
            obs.update(cap_for_bottle=mapping,seated=list(mapping),contacts=[[self.label(b),'cap_'+self.label(cs[0]).removeprefix('cap_')] for b,cs in matches.items() if len(cs)==1])
        elif t=='E23':
            branches=self.semantic['branches'];height={k:float(self.point(v['ref'],v['tip_local'])[2]) for k,v in branches.items()};levels={};clusters=[]
            for k in sorted(height,key=height.get,reverse=True):
                if not clusters or abs(height[k]-height[clusters[-1][0]])>.01:clusters.append([])
                clusters[-1].append(k)
            if len(clusters)==3:levels={k:level for group,level in zip(clusters,['high','middle','low']) for k in group}
            matches={n:[k for k,b in branches.items() if self.branch_inside(n,b)] for n in names};mapping={self.label(n):v[0] for n,v in matches.items() if len(v)==1}
            obs.update(branch_for_cup=mapping,branch_levels=levels,mouth_contains_branch=list(mapping),contacts=[[n,b] for n,b in mapping.items()])
        elif t=='E24':
            inside,supported=self.contained('box',names);self._placements(inside,supported);order=sorted(names,key=lambda n:self.state[n]['pos'][1],reverse=True)
            obs.update(placement_events=self.event_history['placement_events'],in_box=labels(inside),supported_in_box=labels(supported),lid_closed=self.lid_closed(),lid_close_step=self.lid_close_step)
            if e24_yarn_rule(self.spec):
                obs['inference_rule_profile']='e24-yarn-insertion-v1'
            else:
                obs.update(upright=labels([n for n in names if self.cup(n)[1][2]>.95]),left_to_right=labels(order))
        elif t=='E37':obs.update(self._screws())
        return obs

    def result(self):
        result=super().result();result['protocol']='realworld50-native-structural-v1';return result


__all__=['StructuralTaskEvaluator','SUPPORTED']
