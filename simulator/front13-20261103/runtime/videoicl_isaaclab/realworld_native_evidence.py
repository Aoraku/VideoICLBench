"""Native pose/contact evidence for reviewed rigid RealWorld50 recipes.

Snapshots come from Controller, once per physics tick. No commanded target,
expert waypoint, or synthetic success flag is read. Source-specific local
axes, cavity bounds and handle points must be explicitly reviewed in recipes.
"""
from copy import deepcopy
import math
import numpy as np

from .realworld_contracts import provenance
from . import realworld_progress_evidence as progress_evidence
from .realworld_stability import for_evaluator as stability_policy


SUPPORTED = ('E02','E04','E05','E07','E09','E11','E13','E14','E15','E16','E20','E21','E22','E32',
             'E25','E27','E31','E33','E34','E35','E36','E38','E39',
             'E41','E47','E48','E49')


def _sphere_in_tapered_cavity(local,radius,lower,upper,entry):
    """Contain a sphere against each measured linear inner-wall segment.

    The widest sphere cross-section need not occur at a profile sample. Each
    segment also checks the analytic minimum wall clearance, avoiding a coarse
    point-sampling test that can miss penetration between measured heights.
    Profile heights are coordinates in the actual cavity body frame.
    """
    axis=entry.get('axis',2)
    if type(axis) is not int or axis not in (0,1,2):raise ValueError('Invalid cavity axis')
    profile=np.asarray(entry['radius_profile'],float)
    center=np.asarray(entry.get('axis_center',[0.,0.]),float)
    if (profile.ndim!=2 or profile.shape[1]!=2 or len(profile)<2 or not np.isfinite(profile).all()
            or np.any(np.diff(profile[:,0])<=0) or np.any(profile[:,1]<=0)
            or center.shape!=(2,) or not np.isfinite(center).all()):
        raise ValueError('Measured monotonic inner-radius profile required')
    if profile[0,0]>lower[axis]+1e-6 or profile[-1,0]<upper[axis]-1e-6:
        raise ValueError('Inner-radius profile must cover the reviewed cavity height')
    z=float(local[axis]);bottom,top=z-radius,z+radius
    if bottom<lower[axis]-.003 or top>upper[axis]+.003:return False
    lateral=[i for i in range(3) if i!=axis];offset=float(np.linalg.norm(local[lateral]-center))
    for (a,ra),(b,rb) in zip(profile[:-1],profile[1:]):
        low,high=max(a,bottom),min(b,top)
        if low>high:continue
        slope=float((rb-ra)/(b-a));critical=z-slope*radius/math.sqrt(1+slope*slope)
        samples=[low,high]
        if low<critical<high:samples.append(critical)
        for height in samples:
            section=math.sqrt(max(0.,radius*radius-(height-z)**2))
            wall=float(ra+slope*(height-a))
            if offset+section>wall+.001:return False
    return True


class NativeTaskEvaluator:
    def __init__(self, spec):
        from .realworld_semantic_checks import check_task
        self.check = check_task
        self.spec = deepcopy(spec)
        self.task, self.variant = spec['id'], spec['variant']
        if self.task not in SUPPORTED:
            raise NotImplementedError(f'{self.task}: native evidence adapter not implemented')
        self.objects = {o['id']:o for o in spec['objects']}
        self.zones = {z['id']:z for z in spec['zones']}
        self.semantic = spec['semantic']
        self.source_cavity_walls = {}
        if self.task == 'E33':
            from .e33_source_geometry import validate_e33_geometry
            validate_e33_geometry(self.objects, self.semantic)
            from .source_cavity_walls import SourceCavityWalls
            for key, entry in self.semantic.get('containers', {}).items():
                if 'source_sidewall_triangles' in entry:
                    self.source_cavity_walls[key] = SourceCavityWalls(
                        entry['source_sidewall_triangles'], self.objects[entry['object']])
        self.reset_episode()

    def reset_episode(self):
        progress_evidence.reset(self)
        self.steps = 0
        self.elapsed = 0.
        self.hold_seconds = 0.
        self.event_enabled = False
        self.events = []
        self.event_history = {'moved_objects':[], 'flipped':[], 'placements':[]}
        self.initial = None
        self.previous = None
        self.anchor = None
        self.moved = set()
        self.changed = set()
        self.flipped = set()
        self.placed = set()
        self.release_pending = set()
        self.errors = []
        self.history_valid = True
        self.observation = {}
        self.current_conditions = []
        self.provenance = provenance(self.task,self.variant)
        self.last = {'success':False,'checks':{'native_snapshot':False}}

    def group(self, label, default=None):
        value = self.semantic.get('groups',{}).get(label, default)
        if value is None:
            value = [n for n,o in self.objects.items() if o.get('role','movable')=='movable']
        if not isinstance(value,list) or any(n not in self.objects for n in value) or len(set(value))!=len(value):
            raise ValueError('Invalid native actor group '+label)
        return value

    def label(self, name):
        return self.objects[name].get('semantic_identity',self.objects[name].get('identity',name))

    def bounds(self, name, state=None):
        value = (state or self.state)[name]
        obj = self.objects[name]
        center = value['pos'] + value['mat'] @ np.asarray(obj.get('local_bounds_center',[0,0,0]),float)
        half = np.abs(value['mat']) @ np.asarray(obj['size'],float)
        if obj.get('kind')=='sphere':
            half = np.full(3,float(max(obj['size'])))
        return center, half

    def contact(self, a,b):
        return frozenset((a,b)) in self.contacts

    def on_table(self, name):
        center, half = self.bounds(name)
        return self.contact(name,'table') and abs(center[2]-half[2]-.8)<.012

    def supports(self, base, name):
        if base=='table':
            return self.on_table(name)
        if not self.contact(base,name):
            return False
        low,lh = self.bounds(base)
        high,hh = self.bounds(name)
        return bool(high[2]>low[2]+.001 and abs(high[2]-hh[2]-low[2]-lh[2])<.015
                    and np.all(np.abs(high[:2]-low[:2])<hh[:2]+lh[:2]))

    def support_edges(self, names, base='table'):
        candidates = [base]+list(names)
        return [[base if a==base else self.label(a),self.label(b)] for a in candidates for b in names
                if a!=b and self.supports(a,b)]

    def region_members(self, names, *, state=None):
        # For initial state, use the saved native contacts from that snapshot.
        current = state or self.state
        output = {z:[] for z in self.zones}
        for name in names:
            if any(current[name]['grasp']):
                continue
            center,_ = self.bounds(name,current)
            for zid,zone in self.zones.items():
                base = zone.get('support','table')
                contacts = self.initial_contacts if state is self.initial else self.contacts
                physical = (name in self.grounded if state is not self.initial and base=='table'
                            else frozenset((name,base)) in contacts)
                anchor=zone.get('anchor_object')
                xy=(current[anchor]['pos']+current[anchor]['mat']@np.asarray(zone.get('anchor_local_center',[0,0,0]),float))[:2] if anchor else zone['xy']
                if physical and np.all(np.abs(center[:2]-xy)<=np.asarray(zone['half_size'])+.005):
                    output[zid].append(name)
        return output

    def compartment_members(self,names):
        actor=self.semantic['container'];value=self.state[actor];output={k:[] for k in self.semantic['compartment_bounds']}
        for name in names:
            center,_=self.bounds(name);local=value['mat'].T@(center-value['pos'])
            if not self.contact(name,actor) or any(self.state[name]['grasp']):continue
            for cell,bounds in self.semantic['compartment_bounds'].items():
                if np.all(local>=np.asarray(bounds['lower'])-.003) and np.all(local<=np.asarray(bounds['upper'])+.003):
                    output[cell].append(name)
        return output

    def container_members(self, container_key, names):
        entry = self.semantic.get('containers',{}).get(container_key)
        if not isinstance(entry,dict):
            raise ValueError('Reviewed cavity bounds required for '+container_key)
        actor = entry['object']
        value = self.state[actor]
        lower,upper = np.asarray(entry['lower'],float),np.asarray(entry['upper'],float)
        if lower.shape!=(3,) or upper.shape!=(3,) or not np.all(upper>lower):
            raise ValueError('Invalid cavity bounds')
        inside = []
        shape=entry.get('shape','box')
        if shape not in ('box','tapered_cylinder'):raise ValueError('Unknown reviewed cavity shape')
        for name in names:
            center,half = self.bounds(name)
            local = value['mat'].T @ (center-value['pos'])
            # Project the original body box directly into the cavity frame.
            # Reprojecting a world AABB inflates it a second time and changes
            # containment when the whole scene is rigidly rotated.
            radius = (np.full(3,float(max(self.objects[name]['size']))) if self.objects[name].get('kind')=='sphere'
                      else np.abs(value['mat'].T @ self.state[name]['mat']) @ np.asarray(self.objects[name]['size'],float))
            if shape=='tapered_cylinder':
                if self.objects[name].get('kind')!='sphere':raise ValueError('Tapered cavity requires actual spherical cargo')
                contained=_sphere_in_tapered_cavity(local,float(radius[0]),lower,upper,entry)
            elif self.task=='E33' and 'source_containment_hull' in self.objects[name]:
                geometry=self.objects[name]['source_containment_hull']
                if geometry.get('source_asset_sha256')!=self.objects[name]['source_asset']['sha256']:
                    raise ValueError('Containment hull source identity mismatch')
                points=np.asarray(geometry['vertices_local'],float)
                if points.ndim!=2 or points.shape[1]!=3 or len(points)<4 or not np.isfinite(points).all():
                    raise ValueError('Measured source containment hull required')
                body=self.state[name]
                actual=(points@body['mat'].T+body['pos']-value['pos'])@value['mat']
                contained=bool(np.all(actual.min(axis=0)>=lower-.003)
                    and np.all(actual.max(axis=0)<=upper+.003))
                if not contained and container_key in self.source_cavity_walls:
                    contained=self.source_cavity_walls[container_key].contains(actual,lower,upper)
            else:contained=bool(np.all(local-radius>=lower-.003) and np.all(local+radius<=upper+.003))
            if not any(self.state[name]['grasp']) and contained:
                inside.append(name)
        grounded = {actor}
        while True:
            more = {n for n in inside if n not in grounded and any(self.contact(n,b) for b in grounded)}
            if not more:
                break
            grounded.update(more)
        return inside,[n for n in inside if n in grounded]

    def e36_box_support(self, names):
        """Require a measured table-to-container load path without robot support.

        Containment alone is invariant when a hand carries the entire box. A
        physically resting ball therefore needs the box's support path as well
        as its own contact with the cavity. Edges require real contact AND the
        same directional support geometry used for native stack evidence.
        """
        actor=self.semantic['containers']['box']['object']
        edges=[['table',n] for n in self.objects if self.supports('table',n)]
        edges.extend([a,b] for a in self.objects for b in self.objects
                     if a!=b and self.supports(a,b))
        paths={'table':['table']}
        while True:
            additions={b:paths[a]+[b] for a,b in edges if a in paths and b not in paths}
            if not additions:break
            paths.update(additions)
        # Include every measured supporting ancestor, so an alternate path to
        # the table cannot hide a robot finger still carrying part of the box.
        ancestors={actor}
        while True:
            additions={a for a,b in edges if b in ancestors and a not in ancestors}
            if not additions:break
            ancestors.update(additions)
        support_actors=sorted((ancestors|set(names))&set(self.objects))
        fingers=[f'{side}_finger{i}' for side in ('left','right') for i in (1,2)]
        hand_contacts=[[n,f] for n in support_actors for f in fingers if self.contact(n,f)]
        grasped=[n for n in support_actors if any(self.state[n]['grasp'])]
        reasons=[]
        if actor not in paths:reasons.append('no_measured_table_to_box_support_path')
        if hand_contacts:reasons.append('robot_finger_contact_on_box_or_support_chain')
        if grasped:reasons.append('robot_grasp_on_box_or_support_chain')
        return dict(container_actor=actor,root='table',measured_support_edges=edges,
                    table_to_container_path=paths.get(actor),
                    supporting_actors=support_actors,hand_contacts=hand_contacts,
                    grasped_actors=grasped,accepted=not reasons,rejected_because=reasons)

    def order(self, names, axis=0, reverse=True, state=None):
        values = state or self.state
        return sorted(names,key=lambda n:float(values[n]['pos'][axis]),reverse=reverse)

    def grid(self, names, state):
        if len(names)!=4:
            raise ValueError('A four-cell layout requires four actors')
        order = self.order(names,axis=0,reverse=True,state=state)
        return [[self.label(n) for n in self.order(row,axis=1,reverse=True,state=state)]
                for row in (order[:2],order[2:])]

    def upright(self, name):
        axis = self.objects[name].get('up_axis',[0,0,1])
        return float((self.state[name]['mat'] @ np.asarray(axis,float))[2])>.85

    def upside_down(self, name):
        axis = self.objects[name].get('up_axis',[0,0,1])
        return float((self.state[name]['mat'] @ np.asarray(axis,float))[2])<-.85

    def point(self, name, field):
        local = self.semantic.get(field,{}).get(name)
        if local is None:
            raise ValueError('Reviewed '+field+' required for '+name)
        return self.state[name]['pos']+self.state[name]['mat']@np.asarray(local,float)

    def cutlery(self, names):
        plate = self.semantic['plate']
        p,ph = self.bounds(plate)
        regions,handles = {},{}
        outside=[]
        for n in names:
            center,half = self.bounds(n)
            if center[0]>p[0]+ph[0]:
                region='far'
            elif center[1]>p[1]+ph[1]:
                region='left'
            elif center[1]<p[1]-ph[1]:
                region='right'
            else:
                region='over_plate'
            regions[self.label(n)]=region
            if abs(center[0]-p[0])>ph[0]+half[0] or abs(center[1]-p[1])>ph[1]+half[1]:
                outside.append(self.label(n))
            direction=self.point(n,'handle_points')-center
            direction/=max(np.linalg.norm(direction),1e-9)
            toward=p-center;toward/=max(np.linalg.norm(toward),1e-9)
            handles[self.label(n)] = ('operator' if direction[0]<-.7 else
                                     'plate' if np.dot(direction,toward)>.7 else
                                     'away_from_plate' if np.dot(direction,toward)<-.7 else 'other')
        # A/B E25's handle relation is plate-relative even if a diagonal
        # placement also happens to point toward the operator.
        if self.task=='E25' and self.variant in ('A','B'):
            for n in names:
                center,_=self.bounds(n);direction=self.point(n,'handle_points')-center
                toward=p-center
                cosine=float(np.dot(direction,toward)/max(np.linalg.norm(direction)*np.linalg.norm(toward),1e-9))
                handles[self.label(n)]='plate' if cosine>.7 else 'away_from_plate' if cosine<-.7 else 'other'
        return regions,handles,outside

    def derive(self, stable):
        t=self.task;active=self.group('active')
        labels=lambda ns:[self.label(n) for n in ns]
        supported=labels([n for n in active if n in self.grounded])
        fingers={f'{side}_finger{i}' for side in ('left','right') for i in (1,2)}
        released=not any(any(self.state[n]['grasp']) for n in active) and not any(self.contact(n,f) for n in active for f in fingers)
        obs=dict(released=released,stable=stable)
        if t in ('E02','E35','E14'):
            names=self.group('blocks')
            key='bottom_to_top' if t!='E14' else 'final_top_to_bottom'
            obs[key]=labels(self.order(names,axis=2,reverse=t=='E14'))
            obs['support_edges']=self.support_edges(names)
            if t=='E14':obs['initial_top_to_bottom']=labels(self.order(names,axis=2,state=self.initial))
        elif t in ('E04','E05'):
            names=self.group('cups' if t=='E04' else 'pieces');regions=self.region_members(names)
            obs.update(placements={self.label(n):z for z,ns in regions.items() for n in ns},supported=labels([n for n in names if self.on_table(n)]))
        elif t=='E07':
            names=self.group('blocks');obs['far_to_near']=[self.objects[n]['rank'] for n in self.order(names)]
            obs['supported_ranks']=[self.objects[n]['rank'] for n in names if self.on_table(n)]
            obs['nonoverlap_pairs']={str(self.objects[a]['rank'])+'|'+str(self.objects[b]['rank']):bool(np.any(np.minimum(self.bounds(a)[0]+self.bounds(a)[1],self.bounds(b)[0]+self.bounds(b)[1])-np.maximum(self.bounds(a)[0]-self.bounds(a)[1],self.bounds(b)[0]-self.bounds(b)[1])<.001)) for i,a in enumerate(names) for b in names[i+1:]}
            obs['nonoverlapping']=all(np.any(np.minimum(self.bounds(a)[0]+self.bounds(a)[1],self.bounds(b)[0]+self.bounds(b)[1])-
                                                    np.maximum(self.bounds(a)[0]-self.bounds(a)[1],self.bounds(b)[0]-self.bounds(b)[1])<.001)
                                      for i,a in enumerate(names) for b in names[i+1:])
        elif t=='E11':
            names=self.group('blocks');regions=self.compartment_members(names)
            cells=self.semantic['grid_cells'];assignment=[[regions[c] for c in row] for row in cells]
            final=[[self.label(cell[0]) for cell in row] for row in assignment] if all(len(cell)==1 for row in assignment for cell in row) else None
            obs.update(initial_grid=self.grid(names,self.initial),final_grid=final,supported=supported,
                       object_cells={self.label(n):[r,c] for r,row in enumerate(cells) for c,cell in enumerate(row) for n in regions[cell] if len(regions[cell])==1})
        elif t=='E13':
            phone=self.semantic['phone'];stand=self.semantic['stand'];pos=self.state[phone]['pos']
            direction=self.point(phone,'camera_end_points')-pos;direction/=max(np.linalg.norm(direction),1e-9)
            back=self.state[phone]['mat']@np.asarray(self.semantic['back_normals'][phone],float)
            obs.update(camera_end='up' if direction[2]>.7 else 'left' if direction[1]>.7 else 'right' if direction[1]<-.7 else 'other',
                       back_faces_operator=bool(back[0]<-.7),stand_supported=self.contact(phone,stand) and not any(self.state[phone]['grasp']))
        elif t=='E15':
            names=self.group('blocks')
            poses=lambda state:{self.label(n):dict(xy=state[n]['pos'][:2].tolist(),yaw_deg=math.degrees(math.atan2(state[n]['mat'][1,0],state[n]['mat'][0,0]))) for n in names}
            obs.update(initial=poses(self.initial),final=poses(self.state),supported=supported)
        elif t=='E09':
            names=self.group('pieces');members=self.region_members(names)
            obs.update(groups=[labels(members[z]) for z in self.semantic['group_region_ids']],
                       supported=labels([n for n in names if n in self.grounded]))
        elif t=='E16':
            names=self.group('pieces')
            poses=lambda state:{self.label(n):dict(xy=state[n]['pos'][:2].tolist(),yaw_deg=math.degrees(math.atan2(state[n]['mat'][1,0],state[n]['mat'][0,0]))) for n in names}
            inside,resting=self.container_members('tray',names)
            obs.update(initial=poses(self.initial),final=poses(self.state),reference_frame='operator_far_left',in_tray=labels(inside),supported_in_tray=labels(resting))
        elif t=='E20':
            names=self.group('chips');all_regions=self.region_members(names)
            members={z:all_regions[z] for z in ('circle','square','triangle')};selected={n for ns in members.values() for n in ns}
            obs.update(chip_colors={self.label(n):self.objects[n]['color'] for n in names},
                       initial_zone_members={z:labels(self.region_members(names,state=self.initial)[z]) for z in ('circle','square','triangle')},
                       zone_members={z:labels(ns) for z,ns in members.items()},
                       unmoved_unused=labels([n for n in names if n not in selected and n not in self.changed]),supported=labels([n for n in selected if n in self.grounded]))
        elif t=='E21':
            names=self.group('blocks');members=self.compartment_members(names);cells={}
            for cell,zone in self.semantic['cell_regions'].items():
                for n in members[zone]:cells[self.label(n)]=cell
            fingers={f'{side}_finger{i}' for side in ('left','right') for i in (1,2)}
            for n in sorted(self.release_pending):
                if self.label(n) in cells and not any(self.contact(n,f) for f in fingers):
                    self.event_history['placements'].append(dict(object=self.label(n),target=cells[self.label(n)],step=self.steps,
                        released=not any(self.state[n]['grasp']) and not any(self.contact(n,f) for f in fingers),
                        support_contact=self.contact(n,self.semantic['container'])))
                    self.release_pending.remove(n)
            obs.update(cells=cells,placement_events=deepcopy(self.event_history['placements']),supported=labels([n for n in names if n in self.grounded]))
        elif t=='E22':
            car=self.semantic['car'];cp=self.state[car]['pos'];rotation=self.state[car]['mat']
            axes=np.asarray(self.semantic['car_frame'],float);sides={};object_sides={}
            for n in self.group('blocks'):
                local=axes.T@rotation.T@(self.state[n]['pos']-cp)
                side='front' if local[0]>abs(local[1]) else 'left' if local[1]>abs(local[0]) else 'right' if -local[1]>abs(local[0]) else 'other'
                sides[side]=self.label(n);object_sides[self.label(n)]=side
            obs.update(object_sides=object_sides,car_sides=sides,reference_frame='car',supported=labels([n for n in self.group('blocks') if self.on_table(n)]))
        elif t in ('E25','E27'):
            names=self.group('cutlery');regions,handles,outside=self.cutlery(names)
            obs.update(regions=regions,handle_toward=handles,supported=supported,outside_plate=outside)
            obs['far_left_to_right']=labels(self.order([n for n in names if regions[self.label(n)]=='far'],axis=1))
            for side in ('left','right'):
                chosen=[n for n in names if regions[self.label(n)]==side]
                obs[side+'_inner_to_outer']=labels(sorted(chosen,key=lambda n:abs(self.state[n]['pos'][1]-self.state[self.semantic['plate']]['pos'][1])))
        elif t=='E31':
            bowl,plate=self.semantic['bowl'],self.semantic['plate'];bp,bh=self.bounds(bowl);pp,ph=self.bounds(plate)
            bowl_in=bp[2]>pp[2] and np.all(np.abs(bp[:2]-pp[:2])+bh[:2]<=ph[:2]+.005)
            cover=pp[2]>bp[2] and np.all(np.abs(bp[:2]-pp[:2])+bh[:2]<=ph[:2]+.005)
            obs.update(bowl_up=self.upright(bowl),plate_up=self.upright(plate),relation='bowl_in_plate' if bowl_in else 'plate_on_bowl' if cover else 'other',
                       contacts=[['bowl','plate']] if self.contact(bowl,plate) else [],contained_or_covering=bool(bowl_in or cover))
        elif t=='E32':
            members=self.region_members(list(self.objects))
            obs.update(delivered=labels(members['target']),moved_objects=labels(sorted(self.moved)))
        elif t in ('E33','E36'):
            key='bin' if t=='E33' else 'box';names=self.group('bottles' if t=='E33' else 'balls')
            inside,resting=self.container_members(key,names)
            if t=='E36':
                obs['box_support_graph']=self.e36_box_support(names)
                if not obs['box_support_graph']['accepted']:resting=[]
            obs['in_'+key]=labels(inside);obs['supported_in_'+key]=labels(resting)
            if t=='E33':obs.update(all_bottles=labels(names),on_table=labels([n for n in names if self.on_table(n)]))
        elif t=='E34':
            result={}
            for n in self.group('cutlery'):
                handle=self.point(n,'handle_points')
                container=self.semantic['container'];v=self.state[container]
                local=v['mat'].T@(handle-v['pos']);bounds=self.semantic['compartment_bounds_local']
                if self.contact(n,container) and np.all(local>=np.asarray(bounds['lower'])-.003) and np.all(local<=np.asarray(bounds['upper'])+.003):
                    result[self.label(n)]='top_left'
            selected=('knife','spoon','fork')['ABC'.index(self.variant)]
            # E34 asks whether the selected utensil has real support. The
            # other two utensils remain supported at their original places;
            # including them in the task's exact selected-object set makes
            # every otherwise valid episode fail the unchanged source rule.
            obs.update(handle_in_cell=result,
                       supported=[name for name in supported if name==selected],
                       all_supported=supported)
        elif t=='E38':
            names=self.group('rings');post=self.semantic['post'];tip=np.asarray(self.semantic['post_tip'],float)
            shaft=self.state[post]['pos']+self.state[post]['mat']@tip
            threaded=[]
            for n in names:
                center,half=self.bounds(n);radius=float(self.objects[n]['hole_radius'])
                if (np.linalg.norm(center[:2]-shaft[:2])+float(self.semantic['post_radius'])<radius
                        and shaft[2]>center[2]+half[2] and abs(self.state[n]['mat'][2,2])>.95 and n in self.grounded):
                    threaded.append(self.label(n))
            obs.update(bottom_to_top=labels(self.order(names,axis=2,reverse=False)),threaded=threaded,
                       post_for_ring={n:'rightmost' for n in threaded},support_edges=self.support_edges(names,base=post))
            obs['support_edges']=[['rightmost' if a==post else a,b] for a,b in obs['support_edges']]
            plane_local=float(self.semantic['post_support_z_local'])
            plane=float((self.state[post]['pos']+self.state[post]['mat']@np.array([0.,0.,plane_local]))[2])
            for name in names:
                center,half=self.bounds(name)
                if self.contact(post,name) and abs(center[2]-half[2]-plane)<.012:
                    obs['support_edges'].append(['rightmost',self.label(name)])
        elif t=='E39':
            names=self.group('blocks');refs=self.group('reference')
            yaws=lambda ns,state:{self.label(n):math.degrees(math.atan2(state[n]['mat'][1,0],state[n]['mat'][0,0])) for n in ns}
            obs.update(reference_order=labels(self.order(refs,axis=1,state=self.initial)),reference_yaws=yaws(refs,self.initial),
                       initial_order=labels(self.order(names,axis=1,state=self.initial)),initial_yaws=yaws(names,self.initial),
                       final_order=labels(self.order(names,axis=1)),final_yaws=yaws(names,self.state),supported=labels([n for n in names if n in self.grounded]),
                       reference_unchanged=all(n not in self.changed for n in refs),reference_changed=any(n in self.changed for n in refs))
        elif t=='E41':
            pairs=self.semantic['segments'];extensions={};gaps={};alignment={};extension_actors={};row_supported=[]
            for rank,front in pairs.items():
                end=self.point(front,'end_points');axis=self.state[front]['mat']@np.asarray(self.semantic['axes'][front],float)
                candidates=[]
                for n in self.group('extensions'):
                    start=self.point(n,'start_points');candidates.append((float(np.linalg.norm(start-end)),n))
                distance,n=min(candidates);extension_actors[rank]=self.label(n)
                if n in self.grounded:row_supported.append(rank)
                extensions[rank]=self.objects[n]['length_rank'];gaps[rank]=distance
                other=self.state[n]['mat']@np.asarray(self.semantic['axes'][n],float)
                alignment[rank]=abs(float(np.dot(axis,other)/(np.linalg.norm(axis)*np.linalg.norm(other))))
            obs.update(extension_object_for_row=extension_actors,extension_object_ids=extension_actors,progress_supported_rows=row_supported,extensions=extensions,end_gaps_m=gaps,axis_alignment_cos=alignment,supported=list(pairs) if all(n in self.grounded for n in self.group('extensions')) else [])
        elif t in ('E47','E48','E49'):
            names=self.group('cards');obs['flipped']=labels([n for n in names if n in self.flipped])
            obs['face_down']=labels([n for n in names if self.upside_down(n)])
            if t=='E47':
                inside,resting=self.container_members('box',names)
                obs.update(initial_face_colors={self.label(n):self.objects[n]['face_color'] for n in names},in_box=labels(inside),supported_in_box=labels(resting))
            elif t=='E48':
                entry=self.semantic['containers']['slot'];holder=entry['object'];hv=self.state[holder]
                lower,upper=np.asarray(entry['lower']),np.asarray(entry['upper']);inside=[]
                for name in names:
                    v=self.state[name];half=np.asarray(self.objects[name]['size'])
                    corners=np.array([[a*half[0],b*half[1],0.] for a in (-1,1) for b in (-1,1)])
                    task_corners=corners@v['mat'].T+v['pos']
                    local=(task_corners-hv['pos'])@hv['mat'];edge=local[np.argsort(local[:,2])[:2]]
                    if (not any(v['grasp']) and abs(v['mat'][2,0])>.7 and self.contact(name,holder)
                            and np.all(edge>=lower-.0015) and np.all(edge<=upper+.0015)):
                        inside.append(name)
                resting=inside
                obs.update(in_slot=labels(inside),slot_for_card={self.label(n):'slot' for n in inside},physically_inserted=labels(resting))
            else:
                members={z:ns for z,ns in self.region_members(names).items() if z in ('green','blue','red')}
                obs.update(tray_for_card={self.label(n):z for z,ns in members.items() for n in ns},
                           untouched=labels([n for n in names if n not in self.changed]),supported=supported)
        return obs

    def update(self,state,contacts,dt):
        try:
            if type(dt) not in (int,float) or not math.isfinite(dt) or dt<=0:
                raise ValueError('Invalid native physics interval')
            if set(state)!=set(self.objects) or not isinstance(contacts,(set,frozenset)):
                raise ValueError('Incomplete native snapshot')
            clean={}
            for n,v in state.items():
                p=np.asarray(v['pos'],float);r=np.asarray(v['mat'],float);g=v['grasp']
                if (p.shape!=(3,) or r.shape!=(3,3) or not np.isfinite(p).all() or not np.isfinite(r).all()
                        or not np.allclose(r.T@r,np.eye(3),atol=1e-4) or not np.isclose(np.linalg.det(r),1.,atol=1e-4)
                        or len(g)!=2 or any(not isinstance(x,(bool,np.bool_)) for x in g)):
                    raise ValueError('Malformed native actor state '+n)
                clean[n]=dict(pos=p,mat=r,grasp=tuple(g))
            if any(not isinstance(c,frozenset) or len(c)!=2 for c in contacts):
                raise ValueError('Invalid native contact pairs')
            self.state,self.contacts=clean,contacts
            if self.initial is None:
                self.initial=deepcopy(clean);self.initial_contacts=set(contacts)
            self.steps+=1;self.elapsed+=dt
            for n,v in clean.items():
                moved=np.linalg.norm(v['pos']-self.initial[n]['pos'])>.015
                turned=self.objects[n].get('kind')!='sphere' and np.linalg.norm(v['mat']-self.initial[n]['mat'])>.25
                if (moved or turned) and n not in self.moved:
                    self.moved.add(n);self.events.append(dict(event='object_moved',object_id=n,step=self.steps))
                if moved or turned:self.changed.add(n)
                if self.task in ('E47','E48','E49') and n in self.group('cards') and self.upright(n):self.flipped.add(n)
                if self.previous is not None and any(self.previous[n]['grasp']) and not any(v['grasp']):self.release_pending.add(n)
            self.grounded={n for n in clean if self.on_table(n)}
            self.grounded.update(n for n,o in self.objects.items() if o.get('role')=='fixture' and o.get('mechanical_asset',{}).get('kind')=='static_mesh'
                                 and np.linalg.norm(clean[n]['pos']-self.initial[n]['pos'])<.002
                                 and np.linalg.norm(clean[n]['mat']-self.initial[n]['mat'])<.02)
            declared_fixed=set(self.semantic.get('world_fixed_objects',[]))
            joint_fixed={j['child'] for j in self.spec.get('joints',[]) if j.get('type')=='fixed' and not j.get('parent')}
            if not declared_fixed<=joint_fixed:
                raise ValueError('World-fixed support requires an actual fixed joint')
            self.grounded.update(n for n in declared_fixed if np.linalg.norm(clean[n]['pos']-self.initial[n]['pos'])<.002)
            while True:
                more={n for n in clean if n not in self.grounded and any(self.contact(base,n) for base in self.grounded)}
                if not more:break
                self.grounded.update(more)
            settling=stability_policy(self)
            anchored=self.anchor is not None and all(np.linalg.norm(v['pos']-self.anchor[n]['pos'])<=settling.translation_m
                         and (self.objects[n].get('kind')=='sphere' or np.linalg.norm(v['mat']-self.anchor[n]['mat'])<=settling.rotation_matrix) for n,v in clean.items())
            # A continuous bounded-pose window rejects drift and motion while
            # tolerating PhysX contact jitter. Differencing two 4ms samples
            # spuriously reset stable stacks despite a sub-millimetre envelope.
            fingers={f'{side}_finger{i}' for side in ('left','right') for i in (1,2)}
            no_finger_support=not any(self.contact(n,f) for n in self.group('active') for f in fingers)
            if self.history_valid and no_finger_support and not any(any(clean[n]['grasp']) for n in self.group('active')):
                if not anchored:self.anchor=deepcopy(clean);self.hold_seconds=0.
                self.hold_seconds+=dt
            else:self.anchor=None;self.hold_seconds=0.
            progress_evidence.update_physical(self, dt)
            self.observation=progress_evidence.finish_observation(self, self.derive(self.hold_seconds>=settling.seconds))
            self.last=self.check(self.task,self.variant,self.observation)
            if self.semantic.get('preserve_reference'):
                fixed=all(n not in self.changed for n in self.group('reference',[]))
                self.last['checks']['reference_actors_unchanged']=fixed
                self.last['success']=self.last['success'] and fixed
            self.current_conditions=[dict(index=i,type=k,passed=bool(v)) for i,(k,v) in enumerate(self.last['checks'].items())]
            self.previous=deepcopy(clean)
            self.event_history.update(moved_objects=[self.label(n) for n in sorted(self.moved)],flipped=[self.label(n) for n in sorted(self.flipped)])
        except (ValueError,KeyError,TypeError,IndexError) as exc:
            self.history_valid=False;self.hold_seconds=0.;self.anchor=None
            if str(exc) not in self.errors:self.errors.append(str(exc))
            self.last={'success':False,'checks':{'native_snapshot':False}}
            self.current_conditions=[dict(index=0,type='native_snapshot',passed=False)]

    def result(self):
        result=deepcopy(dict(success=bool(self.last['success'] and self.history_valid),hold_seconds=self.hold_seconds,
                             conditions=self.current_conditions,failed_checks=[x['type'] for x in self.current_conditions if not x['passed']],
                             progress_evidence=progress_evidence.envelope(self),
                             observation=self.observation,events=self.events,event_history=self.event_history,errors=self.errors,
                             history_valid=self.history_valid,stability_definition=stability_policy(self).description,
                             stability_policy=stability_policy(self).record(),
                             backend='isaaclab_physx',protocol='realworld50-native-rigid-v2',provenance=self.provenance))
        return progress_evidence.attach_score(result)
