"""Measured tool interactions for E28/29/40/42/43/44/45/46/50.

Every physics tick must supply update_contact_forces({frozenset((a,b)): N})
before update(state, contacts, dt). N is the actual contact-matrix vector norm,
never a substituted boolean. Missing force samples fail closed. Articulated
recipes also call update_mechanisms with Controller.snapshot_mechanisms().

Private semantic geometry (all vectors are measured source-local coordinates):
* tools.main = {actor, support_bounds:{lower,upper}, support_normal_local:[3],
  support_plane_offset:m, edge_segment:[[3],[3]]}. Plane n dot x = offset.
  E29 uses tools.main.actor for mallet and keys {"1":actor,...,"8":actor}.
* groups.cargo / balls / cards list physical rigid IDs. Identity labels are
  attached to objects, e.g. yellow_rectangle, white_yellow_round, yellow_block.
* containers.plate / cup / green / blue / red = {object,lower,upper,
  floor_axis:2, floor_side:"lower", rim_axis:2, rim_side:"upper"}.
* launcher = {actor}: a physically fixed source fixture initially contacting
  the ball; tools.main is the held guide in E43. Groups.balls has one member.
* clips = {clip_id:{mechanism,joint,handle_contacts:[...],
  left:{body,contact_body,point_local:[3]},right:{...},capture_radius:m}}.
  Measured jaw-tip distance is the gap; both actual jaw contacts plus the
  intervening point geometry establish clamping. E40 zones additionally have
  edge_point:[task xyz], support:paperActor. E50 one clip and one card.
* crease = {mechanism,joint,base:{body,contact_body,normal_local:[3]},
  fold:{body,contact_body,normal_local:[3]}}. Actual panel orientations define
  the dihedral; joint displacement and hand contact must coincide with folding.

The force map must cover every positive contact pair. It may include zero
entries. Articulation body/joint identity and finite matrices are validated.
No commands, success flags, asset kind assumptions or desired joint values are
accepted as evidence. Loading a spatula by hand is allowed before transport.
"""
from copy import deepcopy
from collections.abc import Mapping
import math
import numpy as np

from .realworld_native_evidence import NativeTaskEvaluator
from . import realworld_progress_evidence as progress_evidence
from .realworld_semantic_checks import check_task
from .realworld_mechanism_evidence import _finite, _rotation, _number, FINGERS

SUPPORTED=('E28','E29','E40','E42','E43','E44','E45','E46','E50')


def _unit(value):
    value=_finite(value,(3,));norm=float(np.linalg.norm(value))
    if norm<1e-9:raise ValueError('Source direction cannot be zero')
    return value/norm


def _segment_distance(point,a,b):
    delta=b-a;den=float(delta@delta)
    if den<1e-12:raise ValueError('Source edge segment has zero length')
    return float(np.linalg.norm(point-(a+np.clip((point-a)@delta/den,0,1)*delta)))


class ToolTaskEvaluator(NativeTaskEvaluator):
    def __init__(self,spec):
        self.spec=deepcopy(spec);self.task,self.variant=spec['id'],spec['variant']
        if self.task not in SUPPORTED:raise NotImplementedError(self.task+': native tool evidence unavailable')
        self.objects={o['id']:o for o in spec['objects']};self.zones={z['id']:z for z in spec.get('zones',[])}
        if len(self.objects)!=len(spec['objects']):raise ValueError('Duplicate physical actor IDs')
        self.semantic=spec['semantic'];self.fingers=self.semantic.get('interactors',list(FINGERS))
        self.source_tray_walls=None
        if self.task=='E45'and self.semantic.get('source_compartment_geometry'):
            from .source_tray_compartments import SourceTrayCompartments
            self.source_tray_walls=SourceTrayCompartments(self.semantic['source_compartment_geometry'],self.objects[self.semantic['container']])
        self.tool=self.semantic.get('tools',{}).get('main');self.clips=self.semantic.get('clips',{});self.crease=self.semantic.get('crease')
        self.required_mechanisms={v['mechanism'] for v in self.clips.values()}
        self.required_mechanisms.update(v['mechanism'] for v in self.semantic.get('key_frames',{}).values())
        if self.crease:self.required_mechanisms.add(self.crease['mechanism'])
        if self.task in ('E28','E29','E42','E43','E46'):
            if not isinstance(self.tool,Mapping) or self.tool.get('actor') not in self.objects:raise ValueError('Explicit physical tool actor required')
        if self.task in ('E28','E46'):
            b=self.tool.get('support_bounds',{})
            if np.any(_finite(b['upper'],(3,))<=_finite(b['lower'],(3,))):raise ValueError('Reviewed blade bounds required')
            _unit(self.tool['support_normal_local'])
            if not _number(self.tool.get('support_plane_offset')):raise ValueError('Measured blade support plane required')
        if self.task=='E42':
            edge=_finite(self.tool['edge_segment'],(2,3))
            if np.linalg.norm(edge[1]-edge[0])<.001:raise ValueError('Reviewed blade edge segment required')
        if self.task=='E29':
            keys=self.semantic.get('keys',{})
            if set(keys)!=set(map(str,range(1,9))) or len(set(keys.values()))!=8:raise ValueError('Eight distinct actual key bodies required')
            for key,actor in keys.items():
                if actor not in self.objects:
                    frame=self.semantic.get('key_frames',{}).get(key,{})
                    if not frame.get('mechanism') or not frame.get('body') or frame.get('contact_body')!=actor:raise ValueError('Articulated key requires explicit measured body frame')
        if self.task in ('E40','E50') and (not self.clips or self.task=='E50' and len(self.clips)!=1):raise ValueError('Actual clip mechanism required')
        for clip in self.clips.values():
            if not clip.get('joint') or not clip.get('handle_contacts'):raise ValueError('Actual clip joint and handle contact bodies required')
            for side in ('left','right'):_finite(clip[side]['point_local'],(3,))
            if not _number(clip.get('capture_radius')) or clip['capture_radius']<=0:raise ValueError('Measured jaw capture radius required')
        self.card_collision={}
        if self.task=='E50':
            from .realworld_clip_card_geometry import collision_entity
            self.card_collision={name:collision_entity(self.objects[name]) for name in self.semantic['groups']['cards']}
        self.clip_contact_components={}
        for clip in self.clips.values():
            components=set(clip['handle_contacts'])|set(clip.get('grasp_contacts',[]))
            components.update(clip[side]['contact_body'] for side in ('left','right'))
            for mechanism in self.spec.get('mechanisms',[]):
                if mechanism['id']==clip['mechanism']:
                    components.update(clip['mechanism']+'/'+role for role in mechanism['mechanical_asset'].get('contact_links',{}))
            self.clip_contact_components[clip['mechanism']]=tuple(sorted(components))
        if self.task=='E44':
            if not self.crease or not self.crease.get('joint'):raise ValueError('Measured crease articulation required')
            for side in ('base','fold'):_unit(self.crease[side]['normal_local'])
        self.check=self._check
        self.reset_episode()

    def reset_episode(self):
        super().reset_episode()
        self.pending_forces=None;self.forces={};self.pending_mechanisms=None;self.mechanisms={};self.previous_mechanisms=None
        self.mechanism_anchor=None;self.mechanism_hold=0.;self.dt=0.;self.initial_tool=None
        self.transports={};self.active_transports={};self.pushes={};self.active_pushes={}
        self.strikes=[];self.pending_strikes={};self.release=None;self.trajectory=[];self.launcher_fixed=True
        self.initial_cup=None;self.previous_cup_local={};self.cup_contact={};self.exits={}
        self.clip_samples={n:[] for n in getattr(self,'clips',{})};self.clip_records={};self.fold_samples=[]
        self.clip_driven={};self.clip_opening_anchors={};self.crease_driven=False
        self.card_flip_step=None;self.card_release_step=None;self.clip_return_step=None;self.extra_checks={}
        self.target_anchor=None;self.target_hold=0.
        self.progress_causal={}
        self.event_history.update(strikes=self.strikes,exit_events=[],clip_records={})

    def _invalid(self,message):
        self.history_valid=False;self.hold_seconds=0.;self.anchor=None
        if str(message) not in self.errors:self.errors.append(str(message))
        self.last={'success':False,'checks':{'native_snapshot':False}}
        self.current_conditions=[dict(index=0,type='native_snapshot',passed=False)]

    def update_contact_forces(self,snapshot):
        try:
            if self.pending_forces is not None:raise ValueError('Unconsumed contact force snapshot')
            if not isinstance(snapshot,Mapping):raise ValueError('Measured contact force map required')
            clean={}
            for pair,force in snapshot.items():
                if not isinstance(pair,frozenset) or len(pair)!=2 or not all(isinstance(n,str) for n in pair) or not _number(force) or force<0:raise ValueError('Malformed measured contact force')
                clean[pair]=float(force)
            self.pending_forces=clean
        except (ValueError,KeyError,TypeError) as exc:self._invalid(exc)

    def update_mechanisms(self,snapshot):
        try:
            if self.pending_mechanisms is not None:raise ValueError('Unconsumed articulation snapshot')
            if not isinstance(snapshot,Mapping) or not self.required_mechanisms<=set(snapshot):raise ValueError('Missing measured articulation')
            clean={}
            for mid in self.required_mechanisms:
                v=snapshot[mid];names=v['joint_names'];bodies=v['body_names']
                if not isinstance(names,list) or len(set(names))!=len(names) or not bodies or len(set(bodies))!=len(bodies):raise ValueError('Ambiguous articulation identities')
                if set(v['body_pos_task'])!=set(bodies) or set(v['body_mat_task'])!=set(bodies):raise ValueError('Incomplete articulation bodies')
                clean[mid]=dict(joint_names=list(names),joint_pos=_finite(v['joint_pos'],(len(names),)),joint_vel=_finite(v['joint_vel'],(len(names),)),body_names=list(bodies),body_pos_task={n:_finite(v['body_pos_task'][n],(3,)) for n in bodies},body_mat_task={n:_rotation(v['body_mat_task'][n]) for n in bodies})
            for entry in self.semantic.get('key_frames',{}).values():
                if entry['body'] not in clean[entry['mechanism']]['body_names']:raise ValueError('Missing actual xylophone key body')
            self.pending_mechanisms=clean
        except (ValueError,KeyError,TypeError,IndexError) as exc:self._invalid(exc)

    def force(self,a,b):
        pair=frozenset((a,b));return self.forces.get(pair,0.) if pair in self.contacts else 0.
    def hand_force(self,name):return sum(self.force(name,f) for f in self.fingers)
    def held(self,name):return any(self.state[name]['grasp']) if name in self.state else any(all(self.force(name,f'{side}_finger{i}')>0 for i in (1,2)) for side in ('left','right'))
    def body(self,mid,name):return self.mechanisms[mid]['body_pos_task'][name],self.mechanisms[mid]['body_mat_task'][name]
    def joint(self,entry):
        m=self.mechanisms[entry['mechanism']];return float(m['joint_pos'][m['joint_names'].index(entry['joint'])])
    def body_point(self,mid,entry):
        p,r=self.body(mid,entry['body']);return p+r@_finite(entry['point_local'],(3,))

    def _region(self,name):
        center,half=self.bounds(name)
        if any(self.state[name]['grasp']):return None
        for zid,z in self.zones.items():
            anchor=z.get('anchor_object')
            if anchor:
                body=self.state[anchor];local=body['mat'].T@(center-body['pos'])
                initial=self.initial[anchor]
                relative=local[:2]-np.asarray(z['anchor_local_center'],float)[:2]
                # Project original body bounds directly into the anchor frame.
                # Rotating a world AABB back adds empty corners; spheres retain
                # the same radius under every rotation.
                obj=self.objects[name]
                extent=(np.full(3,float(max(obj['size']))) if obj.get('kind')=='sphere'
                        else np.abs(body['mat'].T@self.state[name]['mat'])@np.asarray(obj['size'],float))
                radius=extent[:2]
                # Reviewed tray floor heights are supplied in the initial
                # level scene. Preserve that floor in anchor coordinates, so
                # subsequent tilt rotates both the support plane and normal.
                floor_local=z.get('surface_z',.8)-initial['pos'][2]
                support_gap=local[2]-extent[2]-floor_local
            else:
                relative=center[:2]-np.asarray(z['xy']);radius=half[:2];surface=z.get('surface_z',.8)
                support_gap=center[2]-half[2]-surface
            if self.force(name,z.get('support','table'))<=0 or abs(support_gap)>.012:continue
            if np.all(np.abs(relative)+radius<=np.asarray(z['half_size'])+.005):return zid
            if (self.source_tray_walls is not None and anchor==self.semantic['container']
                    and self.objects[name].get('kind')=='sphere'
                    and self.source_tray_walls.contains(local,max(self.objects[name]['size']),z)):
                return zid
        return None

    def _container(self,key,names):
        inside,resting=self.container_members(key,names)
        return inside,resting

    def _trace(self,active,best,name,sample):
        if sample is None:active[name]=[];return
        seq=active.setdefault(name,[])
        if seq and seq[-1]['step']!=sample['step']-1:seq=[];active[name]=seq
        seq.append(sample)
        def travel(trace):
            if len(trace)<2:return 0.
            field='object_pos' if 'object_pos' in trace[0] else 'pos'
            return float(np.linalg.norm(np.asarray(trace[-1][field])-trace[0][field]))
        if name not in best or best[name] is seq or travel(seq)>travel(best[name]):best[name]=seq

    def _delivery_chain(self,name,sample,active,channel,tool_bodies):
        """Keep a live causal chain, separately from the longest past trace.

        A previous legal transport cannot justify later hand delivery. Loading
        assistance before a transport is allowed; direct contact after a valid
        trace invalidates that chain until a fresh valid transport is measured.
        """
        label=self.label(name)
        record=self.progress_causal.setdefault(label,dict(channel=channel,
            transport_achieved=False,delivery_chain_valid=False,
            last_valid_transport_end_step=None,invalidated_step=None))
        hand=self.hand_force(name)>0 or any(self.state[name]['grasp'])
        # A different grasped rigid body must not serve as an unrecorded second
        # delivery tool. Passive receiving containers/table remain legitimate.
        other_tool=any(other!=name and other not in tool_bodies and self.held(other)
                       and self.force(name,other)>0 for other in self.objects)
        source_tool_held=(any(self._clip_assembly_held(c) for c in self.clips.values()) if channel=='clip'
                          else any(self.held(body) for body in tool_bodies))
        invalid_tool_contact=sample is None and source_tool_held and any(self.force(name,body)>0 for body in tool_bodies)
        if hand or other_tool or invalid_tool_contact:
            record['delivery_chain_valid']=False;record['invalidated_step']=self.steps
        if sample is not None:
            seq=active.get(name,[])
            field='object_pos' if 'object_pos' in sample else 'pos'
            qualifies=len(seq)>=2 and np.linalg.norm(np.asarray(seq[-1][field])-seq[0][field])>.02
            if qualifies:
                record.update(transport_achieved=True,delivery_chain_valid=True,
                    last_valid_transport_end_step=self.steps)

    def _causal_delivery_checks(self,obs):
        """Native final checks also reject a valid old trace + later hand carry."""
        if self.task in ('E28','E46','E42','E45','E50'):
            names=self.group({'E28':'cargo','E46':'cargo','E42':'balls','E45':'balls','E50':'cards'}[self.task])
            # E28's unselected food may be untouched and have no tool chain.
            if self.task=='E28':names=[n for n in names if self.label(n) in obs.get('in_plate',[])]
            self.extra_checks['delivery_has_continuous_tool_cause']=bool(names) and all(
                self.progress_causal.get(self.label(n),{}).get('delivery_chain_valid') is True for n in names)
        obs['progress_causal']=deepcopy(self.progress_causal)

    def _spatula_history(self,names,push=False):
        tool=self.tool['actor'];tv=self.state[tool]
        for name in names:
            center,half=self.bounds(name);local=tv['mat'].T@(center-tv['pos'])
            valid=self.held(tool) and not any(self.state[name]['grasp']) and self.hand_force(name)==0 and self.force(name,tool)>0
            if push:
                edge=np.asarray(self.tool['edge_segment'],float);radius=float(max(half))
                valid=valid and self.force(name,'table')>0 and self.on_table(name) and _segment_distance(local,*edge)<=radius+.003
                sample=dict(step=self.steps,tool='spatula_edge',pos=center.tolist(),edge_contact_force=self.force(name,tool),tool_held=True,hand_contact=False,table_supported=True) if valid else None
                self._trace(self.active_pushes,self.pushes,name,sample)
                self._delivery_chain(name,sample,self.active_pushes,'push',{tool})
            else:
                box=self.tool['support_bounds'];lo=np.asarray(box['lower']);hi=np.asarray(box['upper'])
                # The source blade is inclined relative to its handle frame;
                # use its measured plane, never an assumed local +Z surface.
                obj=self.objects[name];sphere=obj.get('kind')=='sphere'
                rad=(np.full(3,float(max(obj['size']))) if sphere else
                     np.abs(tv['mat'].T@self.state[name]['mat'])@np.asarray(obj['size'],float))
                normal=_unit(self.tool['support_normal_local']);world_normal=tv['mat']@normal
                extent=(float(max(obj['size'])) if sphere else
                        float(np.abs(self.state[name]['mat'].T@world_normal)@np.asarray(obj['size'],float)))
                valid=valid and world_normal[2]>.8 and np.all(local>=lo-rad-.003) and np.all(local<=hi+rad+.003) and abs(float(normal@local)-extent-self.tool['support_plane_offset'])<.012
                sample=dict(step=self.steps,tool='spatula',object=self.label(name),object_pos=center.tolist(),tool_held=True,direct_hand_contact=False,support_contact_force=self.force(name,tool)) if valid else None
                self._trace(self.active_transports,self.transports,name,sample)
                self._delivery_chain(name,sample,self.active_transports,'spatula',{tool})

    def _strike_history(self):
        tool=self.tool['actor']
        for key,name in self.semantic['keys'].items():
            force=self.force(tool,name)
            if force>0:
                if not self.held(tool):raise ValueError('Mallet key contact without actual tool grasp')
                if key not in self.pending_strikes:self.pending_strikes[key]=dict(tool='mallet',key=int(key),step=self.steps,contact_impulse=0.)
                self.pending_strikes[key]['contact_impulse']+=force*self.dt
            elif key in self.pending_strikes:
                self.strikes.append({**self.pending_strikes.pop(key),'release_step':self.steps})
                self.events.append(dict(event='mallet_strike_released',key=int(key),step=self.steps))

    def _guide_history(self):
        ball,=self.group('balls');launcher=self.semantic['launcher']['actor'];guide=self.tool['actor']
        current=self.state[launcher];initial=self.initial[launcher]
        self.launcher_fixed=self.launcher_fixed and np.linalg.norm(current['pos']-initial['pos'])<.002 and np.linalg.norm(current['mat']-initial['mat'])<.02
        if self.release is None and self.contact(ball,launcher) is False and frozenset((ball,launcher)) in self.initial_contacts:
            self.release=dict(source='fixed_launcher',step=self.steps,initially_held=True,released=True,release_id='native-release-'+str(self.steps))
        if self.release:
            self.trajectory.append(dict(step=self.steps,release_id=self.release['release_id'],pos=self.state[ball]['pos'].tolist(),hand_contact_force=self.hand_force(ball),guide_contact_force=self.force(ball,guide),guide_held=self.held(guide)))

    def _cup_history(self):
        names=self.group('balls');c=self.semantic['containers']['cup'];cup=c['object'];v=self.state[cup]
        lo=_finite(c['lower'],(3,));hi=_finite(c['upper'],(3,));axis=c.get('rim_axis',2);sign=1 if c.get('rim_side','upper')=='upper' else -1
        if axis not in (0,1,2) or np.any(hi<=lo):raise ValueError('Reviewed cup rim frame required')
        rim=hi[axis] if sign==1 else lo[axis];normal=v['mat'][:,axis]*sign
        tilt=math.degrees(math.acos(np.clip(normal[2],-1,1)));locals={}
        if self.initial_cup is None:self.initial_cup=self._container('cup',names)[1]
        for name in names:
            pos,_=self.bounds(name);local=v['mat'].T@(pos-v['pos']);locals[name]=local
            force=self.force(cup,name)
            if force>0:self.cup_contact[name]=(self.steps,force)
            before=self.previous_cup_local.get(name);last=self.cup_contact.get(name)
            crossed=before is not None and sign*(before[axis]-rim)<=0<sign*(local[axis]-rim)
            if crossed and name not in self.exits:
                self.exits[name]=dict(ball=self.label(name),step=self.steps,cup_tilt_deg=tilt,cup_held=self.held(cup),crossed_cup_rim=True,direct_hand_contact=self.hand_force(name)>0 or any(self.state[name]['grasp']),previous_cup_contact_force=last[1] if last and (self.steps-last[0])*self.dt<=.2 else 0.)
                event=self.exits[name]
                valid=bool(name in self.initial_cup and 30<tilt<=180 and event['cup_held']
                    and not event['direct_hand_contact'] and event['previous_cup_contact_force']>0)
                self.progress_causal[self.label(name)]=dict(channel='pour',poured_exit_valid=valid,
                    delivery_chain_valid=valid,exit_step=self.steps,invalidated_step=None)
            record=self.progress_causal.setdefault(self.label(name),dict(channel='pour',
                poured_exit_valid=False,delivery_chain_valid=False,exit_step=None,invalidated_step=None))
            intervening_tool=any(other not in (name,cup) and self.held(other) and self.force(name,other)>0 for other in self.objects)
            if record['exit_step'] is not None and (self.hand_force(name)>0 or any(self.state[name]['grasp']) or intervening_tool):
                record['delivery_chain_valid']=False;record['invalidated_step']=self.steps
        self.previous_cup_local=locals;self.event_history['exit_events']=list(deepcopy(self.exits).values())

    def _jaw_geometry(self,clip,point):
        a=self.body_point(clip['mechanism'],clip['left']);b=self.body_point(clip['mechanism'],clip['right']);gap=float(np.linalg.norm(b-a))
        if gap<1e-7:return gap,False
        t=float((point-a)@(b-a)/(gap*gap));near=float(np.linalg.norm(point-(a+np.clip(t,0,1)*(b-a))))
        return gap,bool(-.1<=t<=1.1 and near<=clip['capture_radius'])

    def _card_jaw_geometry(self,clip,name):
        """Actual SHA-bound card entity, including true edge grips away from COM."""
        a=self.body_point(clip['mechanism'],clip['left']);b=self.body_point(clip['mechanism'],clip['right']);gap=float(np.linalg.norm(b-a))
        if gap<1e-7:return gap,False
        value=self.state[name];p,r=value['pos'],value['mat'];closest=self.card_collision[name].closest_to_segment(r.T@(a-p),r.T@(b-p))
        return gap,bool(-.1<=closest['axis_parameter']<=1.1 and closest['distance_m']<=clip['capture_radius'])

    def _clip_assembly_held(self,clip):
        bodies=self.clip_contact_components[clip['mechanism']]
        return any(all(any(self.force(body,f'{side}_finger{i}')>0 for body in bodies)for i in (1,2))for side in ('left','right'))

    def _clip_history(self,targets):
        # targets maps semantic marker/card labels to (actual actor, task point).
        for cid,clip in self.clips.items():
            self.joint(clip)  # Exact finite named joint is mandatory even though gap uses measured links.
            left,right=clip['left']['contact_body'],clip['right']['contact_body'];force=sum(self.hand_force(n) for n in clip['handle_contacts'])
            for label,(actor,point) in targets.items():
                if label in self.clip_records:continue
                gap,between=(self._card_jaw_geometry(clip,actor) if self.task=='E50' else self._jaw_geometry(clip,point))
                sample=dict(step=self.steps,jaw_gap_m=gap,joint_pos=self.joint(clip),handle_contact_force=force,handles_released=force==0,left_jaw_contact_force=self.force(left,actor),right_jaw_contact_force=self.force(right,actor),edge_between_jaws=between)
                key=(cid,label);seq=self.clip_samples.setdefault(key,[]);seq.append(sample)
                from .realworld_semantic_checks import _clip_record, _clip_opening_update
                record=dict(clip_id=cid,samples=seq)
                if len(seq)>1:
                    if not hasattr(self,'clip_opening_anchors'):self.clip_opening_anchors={}
                    anchor,opened=_clip_opening_update(seq[-2],seq[-1],self.clip_opening_anchors.get(key))
                    self.clip_opening_anchors[key]=anchor
                    self.clip_driven[key]=self.clip_driven.get(key,False) or opened
                candidate=force==0 and sample['left_jaw_contact_force']>0 and sample['right_jaw_contact_force']>0 and between
                if candidate and self.clip_driven.get(key,False) and _clip_record(record):self.clip_records[label]=deepcopy(record)

    def _crease_history(self):
        c=self.crease;_,base=self.body(c['mechanism'],c['base']['body']);_,fold=self.body(c['mechanism'],c['fold']['body'])
        bn=base@_unit(c['base']['normal_local']);fn=fold@_unit(c['fold']['normal_local'])
        angle=180-math.degrees(math.acos(np.clip(float(bn@fn),-1,1)));q=self.joint(c)
        force=self.hand_force(c['fold']['contact_body']);self.fold_samples.append(dict(step=self.steps,angle_deg=angle,hand_contact_force=force,joint_pos=q))
        if len(self.fold_samples)==1:self.crease_driven_totals=None
        if len(self.fold_samples)>1:
            from .crease_motion import accumulate_driven, driven_toward_final
            a,b=self.fold_samples[-2:]
            self.crease_driven_totals=accumulate_driven(a,b,getattr(self,'crease_driven_totals',None),require_joint=True)
            self.crease_driven=driven_toward_final(self.crease_driven_totals,self.fold_samples[0]['angle_deg'],angle,require_joint=True)
        self.extra_checks['actual_crease_joint_contact_motion']=self.crease_driven
        return angle

    def _mechanism_stable(self):
        if not self.required_mechanisms:return True
        anchored=self.mechanism_anchor is not None
        if anchored:
            for mid,v in self.mechanisms.items():
                a=self.mechanism_anchor[mid]
                # Stability is the declared physical body-pose envelope. A
                # second unitless joint threshold mixes metres and radians,
                # and incorrectly rejects micrometre jaw vibration that is
                # already bounded by the unchanged body checks below.
                anchored=anchored and all(np.linalg.norm(v['body_pos_task'][n]-a['body_pos_task'][n])<=.002 and np.linalg.norm(v['body_mat_task'][n]-a['body_mat_task'][n])<=.02 for n in v['body_names'])
        if not anchored:self.mechanism_anchor=deepcopy(self.mechanisms);self.mechanism_hold=0.
        else:self.mechanism_hold+=self.dt
        return self.mechanism_hold>=.5

    def _target_stable(self,released):
        key={'E28':'cargo','E42':'balls','E43':'balls','E45':'balls','E46':'cargo','E50':'cards'}.get(self.task)
        names=self.group(key,[]) if key else []
        if self.task=='E45':names=[*names,self.semantic['containers']['cup']['object']]
        anchored=self.target_anchor is not None and all(np.linalg.norm(self.state[n]['pos']-self.target_anchor[n]['pos'])<=.002
            and (self.objects[n].get('kind')=='sphere' or np.linalg.norm(self.state[n]['mat']-self.target_anchor[n]['mat'])<=.02) for n in names)
        if released and self.history_valid:
            if not anchored:self.target_anchor={n:deepcopy(self.state[n]) for n in names};self.target_hold=0.
            else:self.target_hold+=self.dt
        else:self.target_anchor=None;self.target_hold=0.
        self.hold_seconds=self.target_hold
        return self.target_hold>=.5

    def derive(self,stable):
        articulated_released=not any(self.hand_force(n)>0 for c in self.clips.values() for n in c['handle_contacts'])
        if self.crease:articulated_released=articulated_released and self.hand_force(self.crease['fold']['contact_body'])==0
        key={'E28':'cargo','E42':'balls','E43':'balls','E45':'balls','E46':'cargo','E50':'cards'}.get(self.task)
        targets=self.group(key,[]) if key else []
        if self.task=='E45':targets=[*targets,self.semantic['containers']['cup']['object']]
        released=not any(any(self.state[n]['grasp']) or self.hand_force(n)>0 for n in targets) and articulated_released
        target_stable=self._target_stable(released);mechanism_stable=self._mechanism_stable()
        obs=dict(released=released,stable=bool(target_stable and mechanism_stable),contacts=[list(p) for p in self.contacts])
        self.extra_checks={};t=self.task;labels=lambda ns:[self.label(n) for n in ns]
        if t in ('E28','E46'):
            names=self.group('cargo');self._spatula_history(names)
            traces={self.label(n):self.transports[n] for n in names if n in self.transports}
            if t=='E28':
                inside,supported=self._container('plate',names)
                same=[n for n in names if float(self.initial[n]['mat'][:,2]@self.state[n]['mat'][:,2])>.9]
                obs.update(in_plate=labels(inside),outside_plate=labels(set(names)-set(inside)),supported_in_plate=labels(supported),transport_samples={n:v for n,v in traces.items() if n in labels(inside)},same_visible_face=labels(set(same)&set(inside)))
                obs['progress_transport_samples']=traces
            else:
                name,=names;region=self._region(name);obs.update(block_region=region,paper_supported=region is not None,transport_samples=traces.get('yellow_block'))
        elif t=='E29':
            self._strike_history();obs['strike_events']=deepcopy(self.strikes);obs['pending_strikes']=list(deepcopy(self.pending_strikes).values());self.extra_checks['no_unreleased_strikes']=not self.pending_strikes
        elif t=='E42':
            names=self.group('balls');self._spatula_history(names,True)
            obs.update(ball_ids=labels(names),ball_regions={self.label(n):self._region(n) for n in names},supported=labels([n for n in names if self.on_table(n)]),push_samples={self.label(n):v for n,v in self.pushes.items()})
        elif t=='E43':
            self._guide_history();obs.update(release=self.release,trajectory=self.trajectory,region_bounds={n:dict(min=(np.asarray(z['xy'])-z['half_size']).tolist(),max=(np.asarray(z['xy'])+z['half_size']).tolist()) for n,z in self.zones.items()})
            self.extra_checks['launcher_remained_fixed']=self.launcher_fixed
            obs.update(release_observed=self.release is not None,release_id=None if self.release is None else 'native-release-'+str(self.release['step']),launcher_moved=not self.launcher_fixed)
        elif t=='E45':
            names=self.group('balls');self._cup_history();inside,_=self._container('cup',names)
            regions={self.label(n):self._region(n) for n in names};supported=[n for n in names if regions[self.label(n)] is not None]
            obs.update(initial_in_cup=labels(self.initial_cup),in_cup=labels(inside),ball_compartments=regions,supported_in_compartment=labels(supported),exit_events=list(deepcopy(self.exits).values()))
            cup=self.semantic['containers']['cup']['object']
            obs.update(cup_on_table=bool(self.on_table(cup)),cup_released=not any(self.state[cup]['grasp']) and self.hand_force(cup)==0)
        elif t=='E40':
            targets={n:(z['support'],_finite(z['edge_point'],(3,))) for n,z in self.zones.items()};self._clip_history(targets)
            final={}
            for marker,record in self.clip_records.items():
                cid=record['clip_id'];c=self.clips[cid];actor,point=targets[marker];_,between=self._jaw_geometry(c,point)
                # Accepted records are frozen by _clip_history. Copy once at
                # result(), rather than copying the full trace every tick.
                if between and self.force(c['left']['contact_body'],actor)>0 and self.force(c['right']['contact_body'],actor)>0:final[marker]=record
            obs.update(clipped_markers=list(final),clip_records=final)
        elif t=='E44':
            angle=self._crease_history();c=self.crease;fold=c['fold']['contact_body'];allowed={c['base']['contact_body'],*self.fingers}
            external=[list(pair) for pair in self.contacts if fold in pair and next(iter(pair-{fold})) not in allowed]
            obs.update(dihedral_angle_deg=angle,base_table_contact_force=self.force(c['base']['contact_body'],'table'),external_support_contacts=external,fold_samples=self.fold_samples)
        elif t=='E50':
            name,=self.group('cards');cid,=self.clips;c=self.clips[cid];pos,_=self.bounds(name)
            initial=self.initial[name]['mat'][:,2];current=self.state[name]['mat'][:,2]
            if self.card_flip_step is None and float(initial@current)<-.9:self.card_flip_step=self.steps
            if self.card_flip_step is not None and self.steps>self.card_flip_step:
                self._clip_history({'card':(name,pos)})
            left,right=c['left']['contact_body'],c['right']['contact_body'];gap,between=self._card_jaw_geometry(c,name)
            held=self._clip_assembly_held(c)
            # The free source assembly may be carried by its Spine while its
            # squeeze handles are released. Both fingers of one actual hand
            # must contact physical components, including source contact_links.
            valid=held and between and self.force(left,name)>0 and self.force(right,name)>0 and self.hand_force(name)==0 and not any(self.state[name]['grasp']) and 'card' in self.clip_records
            sample=dict(step=self.steps,object='card',tool='binder_clip',object_pos=pos.tolist(),tool_held=held,direct_hand_contact=False,jaw_contact_forces=[self.force(left,name),self.force(right,name)],between_jaws=between) if valid else None
            self._trace(self.active_transports,self.transports,name,sample)
            self._delivery_chain(name,sample,self.active_transports,'clip',set(self.clip_contact_components[c['mechanism']]))
            causal=self.progress_causal[self.label(name)]
            causal['clip_grip_achieved']=bool(causal.get('clip_grip_achieved') or ('card' in self.clip_records and self.hand_force(name)==0 and not any(self.state[name]['grasp']) and between and self.force(left,name)>0 and self.force(right,name)>0))
            region=self._region(name);released=not any(self.state[name]['grasp']) and self.force(left,name)==0 and self.force(right,name)==0 and self.hand_force(name)==0
            if region and released and name in self.transports and self.card_release_step is None:self.card_release_step=self.steps
            on_table=any(self.force(n,'table')>0 for n in self.clip_contact_components[c['mechanism']]) and not held
            if on_table and self.card_release_step is not None and self.clip_return_step is None:self.clip_return_step=self.steps
            obs.update(card_flipped=self.card_flip_step is not None,card_tray=region,transport_samples=self.transports.get(name),clip_sequence=self.clip_records.get('card'),card_flip_step=self.card_flip_step,card_release_step=self.card_release_step,clip_return_step=self.clip_return_step,card_released=released,tray_supported=region is not None,clip_on_table=on_table)
            causal['clip_return_after_delivery']=bool(on_table and self.card_release_step is not None and self.clip_return_step is not None and self.clip_return_step>=self.card_release_step and causal['delivery_chain_valid'])
            if on_table:obs['contacts'].append(['binder_clip','table'])
        for cid,clip in self.clips.items():
            mechanism=self.mechanisms[clip['mechanism']]
            poses={n:dict(pos=mechanism['body_pos_task'][n],mat=mechanism['body_mat_task'][n]) for n in mechanism['body_names']}
            components=self.clip_contact_components[clip['mechanism']]
            released_clip=all(self.hand_force(n)==0 for n in components)
            supported_clip=any(self.force(n,'table')>0 for n in components)
            if t=='E40':supported_clip=supported_clip or any(rec['clip_id']==cid for rec in obs.get('clip_records',{}).values())
            progress_evidence.measured_group(self,cid,poses,released_clip,supported_clip,self.dt)
            if t=='E50':self.progress_extra_status['binder_clip']=deepcopy(self.progress_extra_status[cid])
        self._causal_delivery_checks(obs)
        return obs

    def _check(self,task,variant,observation):
        if task not in ('E29','E43') and not observation.get('stable'):
            return dict(success=False,checks=dict(released=observation.get('released') is True,stable=False),failed_checks=['stable'])
        result=check_task(task,variant,observation);result['checks'].update(self.extra_checks)
        result['success']=all(result['checks'].values());result['failed_checks']=[k for k,v in result['checks'].items() if not v]
        return result

    def update(self,state,contacts,dt):
        try:
            if self.pending_forces is None:raise ValueError('Fresh measured contact forces required each physics step')
            if not _number(dt) or dt<=0:raise ValueError('Invalid physics time interval')
            self.forces=self.pending_forces;self.pending_forces=None
            if any(self.forces.get(pair,0)<=0 for pair in contacts):raise ValueError('Positive contact lacks measured force')
            if any(value>.001 and pair not in contacts for pair,value in self.forces.items()):raise ValueError('Force snapshot and contact pairs disagree')
            if self.required_mechanisms:
                if self.pending_mechanisms is None:raise ValueError('Fresh measured articulation required each physics step')
                self.mechanisms=self.pending_mechanisms
                if self.previous_mechanisms and any(v['joint_names']!=self.previous_mechanisms[mid]['joint_names'] or v['body_names']!=self.previous_mechanisms[mid]['body_names'] for mid,v in self.mechanisms.items()):raise ValueError('Articulation identity changed during episode')
            self.pending_mechanisms=None;self.dt=float(dt)
            super().update(state,contacts,float(dt));self.previous_mechanisms=deepcopy(self.mechanisms)
        except (ValueError,KeyError,TypeError,IndexError) as exc:
            self.pending_forces=None;self.pending_mechanisms=None;self._invalid(exc)

    def result(self):
        result=super().result();result['protocol']='realworld50-native-tool-v1';return result


__all__=['ToolTaskEvaluator','SUPPORTED']
