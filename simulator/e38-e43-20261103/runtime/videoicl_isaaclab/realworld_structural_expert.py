"""Source-geometry structural authoring through real robot controls.

Uses ToolAuthor's actual-pose Cartesian/rotation feedback and two-finger checks.
Its optional continuous recording path keeps the same measured contact guards.
Never reads evaluator results or writes object/joint state. Semantic geometry is
shared with StructuralTaskEvaluator; answers are private authoring choices only.

All tasks require structural_grasps:{actor:{local,jaw_axis_local}} with reviewed
loaded-body coordinates. structural_expert contains source-reviewed placement
points, never blindly inferred from a kind or bounding-box center:
 E01 plate_positions:{food:[plate-local contact plane point]};
 E08 box_positions:{shoe:[box-local bottom point]};
 E10 threading_targets:{piece:{post_indices:[...],rotation:[3x3]}};
 E17 shelf_positions:{piece:[shelf-body-local bottom point]};
 E24 box_positions:[[box-local bottom point],...] in operator left-to-right order;
 E37 driver_grasp:{local,jaw_axis_local}, removed_screw_placements:{role:
       {point_task:[actual grasp-point rest location],rotation:[3x3]}}.
E03 nesting depths are solved from measured inner/outer collision profiles.
E12 pin alignment is solved from the actual hole/pin cross axes. E19 cap seating
uses actual mouth/pocket geometry. E23 branch levels derive from actual tip Z.
These policies are bounded attempts; a return value is not a physics certificate.
"""
import itertools
import math
import numpy as np
from .realworld_tool_expert import ToolAuthor,ToolExecutionError,_axis_rotation
from .realworld_tool_evidence import _unit
from .realworld_mechanism_evidence import _finite,_rotation
from .realworld_structural_evidence import _basis,_profile,_radius

SUPPORTED=('E01','E03','E08','E10','E12','E17','E19','E23','E24','E37')


class StructuralAuthor(ToolAuthor):
    def __init__(self,author):
        self.a=author;self.c=author.c;self.spec=author.scene.spec;self.s=self.spec['semantic'];self.task=self.spec['id'];self.variant=self.spec['variant']
        if self.task not in SUPPORTED:raise NotImplementedError(self.task+': structural expert unavailable')
        if self.variant not in ('A','B','C'):raise ToolExecutionError('Unknown source variant')
        self.index='ABC'.index(self.variant);self.start=self.c.steps;self.limit=self.spec.get('expert_action_budget',1500)
        config=author.scene.embodiment.config['control'];self.min_mm=float(config['step_mm'][0]);self.max_mm=min(10.,float(config['step_mm'][1]));self.min_deg=float(config['rotation_deg'][0]);self.max_deg=min(10.,float(config['rotation_deg'][1]))
        if self.min_mm>self.max_mm:raise ToolExecutionError('Public precision translation unavailable')
        self.clearance=float(self.s.get('expert_clearance_z',1.15));self.operations=[];self.geometry=self.s.get('structural_expert',{})
        self.objects={o['id']:o for o in self.spec['objects']};self.identity={o.get('semantic_identity',o.get('identity',o['id'])):o['id'] for o in self.spec['objects']}
        self.grasps=self.s.get('structural_grasps',{})
        if (self.task=='E10' and getattr(author,'control_report',{}).get('engineering_reference_only')
                and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'):
            # Cleared transit can use ordinary public25mm requests. Thin
            # side-band approach and engaged bores keep their own small steps.
            self.max_mm=min(25.,float(config['step_mm'][1]))
        if (self.task=='E08' and getattr(author,'control_report',{}).get('engineering_reference_only')
                and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'):
            from .execution_design_reference_grasps import e08_engineering_heel_grasps
            self.grasps=e08_engineering_heel_grasps(self.spec,self.grasps)
        if (self.task=='E12' and getattr(author,'control_report',{}).get('engineering_reference_only')
                and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'):
            from .execution_design_e12_reference import horizontal_charger_grasps
            self.grasps=horizontal_charger_grasps(self.spec,self.grasps)
            self._e12_single_step_reference=self.variant=='B'
            import os
            self._e12_functional_workflow=os.environ.get('VIC_ENGINEERING_FUNCTIONAL_ACCEPTANCE')=='1'
            if self._e12_functional_workflow:
                self.a.control_report['functional_acceptance_requested']=True
                self.a.control_report['native_score_unchanged']=True

    def move_point(self,side,ref,target,guard=None,follower=None,tolerance=.002):
        if self.task=='E12'and getattr(self,'_e12_functional_workflow',False):
            from .execution_design_e12_functional import move_point
            return move_point(self,side,ref,target,guard,follower,max(tolerance,.006))
        return super().move_point(side,ref,target,guard,follower,tolerance)

    def ref(self,name):
        g=self.grasps[name];_finite(g['local'],(3,));_unit(g['jaw_axis_local']);ref=dict(actor=name,**g)
        if (self.task=='E19'and self.spec.get('variant')=='C'and name=='cap_red'
                and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                and getattr(self.a,'control_report',{}).get('engineering_reference_only')):
            from .execution_design_e19_reacquire import higher_red_cap_ref
            ref=higher_red_cap_ref(self,ref)
        return ref
    def body_point(self,ref,local):return self.point({**ref,'local':local})
    def label(self,name):return self.objects[name].get('semantic_identity',self.objects[name].get('identity',name))
    def hand_for(self,name):return self.grasps[name].get('hand','left' if self.snapshot()[0][name]['pos'][1]>=0 else 'right')
    def align_axis(self,name,side,source_axis,target_axis):
        current=self.snapshot()[0][name]['mat'];a=current@_unit(source_axis);b=_unit(target_axis);cos=float(np.clip(a@b,-1,1))
        if cos>.999:return
        if cos<-.999:
            seed=np.array([1.,0,0]) if abs(a[0])<.9 else np.array([0.,1,0]);axis=_unit(np.cross(a,seed))
        else:axis=_unit(np.cross(a,b))
        self.rotate_actor(name,side,_axis_rotation(axis,math.acos(cos))@current)
    def pickup(self,name,side=None):
        ref=self.ref(name);side=self.hand_for(name) if side is None else side
        if side not in ('left','right'):raise ToolExecutionError('Invalid physical pickup hand')
        if (self.task=='E10' and getattr(self.a,'control_report',{}).get('engineering_reference_only')
                and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'):
            from .execution_design_e10_reference import acquire_thin_piece,near_side_piece_ref
            ref=near_side_piece_ref(self,ref)
            acquire_thin_piece(self,ref,side)
        else:
            if (self.task=='E12' and getattr(self.a,'control_report',{}).get('engineering_reference_only')
                    and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'):
                from .execution_design_e12_reference import prepare_next_charger_acquisition
                prepare_next_charger_acquisition(self,ref,side)
            self.acquire(ref,side)
            if (self.task=='E12' and getattr(self.a,'control_report',{}).get('engineering_reference_only')
                    and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'):
                from .execution_design_e12_reference import remember_acquired_hand
                remember_acquired_hand(self,ref,side)
        if (self.task=='E10'and getattr(self.a,'control_report',{}).get('engineering_reference_only')
                and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'):
            from .execution_design_e10_reference import lift_thin_piece
            lift_thin_piece(self,ref,side)
        else:self.move(side,self.tip(side)+[0,0,.07],lambda:self.require_held(ref,side))
        return ref,side
    def lower_place(self,name,ref,side,local_point,target,rotation=None,support=None):
        guard=lambda:self.require_held(ref,side)
        control=dict(actor=name,local=_finite(local_point,(3,)).tolist());target=_finite(target,(3,));height=max(self.clearance,target[2]+.07)
        # Lift the actual payload above container rims before rotating it.
        # Rotating a long shoe after only the pickup lift sweeps its toe into
        # the box; use the measured working point again after rotation.
        self.move_point(side,control,[*self.point(control)[:2],height],guard)
        if rotation is not None:self.rotate_actor(name,side,_rotation(rotation))
        self.move_point(side,control,[*target[:2],height],guard)
        contact_stop=float(self.geometry.get('support_contact_stop_m',0.))
        if self.spec.get('author_smooth_recording',False) and support is not None and contact_stop>0:
            def supported_near_goal():
                return self.contact(name,support) and np.max(np.abs(self.point(control)-target))<=contact_stop
            self.a.move_smooth({side:self.tip(side)+target+[0,0,.001]-self.point(control)},
                guard=guard,done=supported_near_goal,tolerance=.002,max_speed=.04,max_acceleration=.2)
        else:
            self.move_point(side,control,target+[0,0,.001],guard)
        self.release(ref,side);self.move(side,self.tip(side)+[0,0,.06]);self.wait(3)
        if support is not None and not self.contact(name,support):raise ToolExecutionError('Placed target lacks actual source support: '+name)
    def bottom_local(self,name):
        # This is a reviewed collision-bound point, used only for public action
        # clearance. Geometry/contact evaluation remains independently derived.
        o=self.objects[name];center=np.asarray(o.get('local_bounds_center',[0,0,0]),float)
        down=self.snapshot()[0][name]['mat'].T@np.array([0.,0.,-1.])
        active=np.abs(down)>1e-8
        distance=float(np.min(np.asarray(o['size'],float)[active]/np.abs(down[active])))
        return center+down*distance

    def food(self):
        selected=(['burger','fries'],['burger','drink'],['fries','drink'])[self.index];container=self.s['containers']['plate'];support=container['ref'].get('actor',container['ref'].get('contact_body'))
        for label in selected:
            name=self.identity[label];self.stage('food-to-plate-'+label);ref,side=self.pickup(name);target=self.body_point(container['ref'],self.geometry['plate_positions'][name])
            self.lower_place(name,ref,side,self.bottom_local(name),target,support=support)

    def nest(self):
        order=(['red','green','blue'],['green','blue','red'],['blue','red','green'])[self.index];names=[self.identity[n] for n in order]
        # Preserve the selected outer cup's actual table position.
        for outer,inner in zip(names[:-1],names[1:]):
            a,b=self.s['cups'][outer],self.s['cups'][inner];ref,side=self.pickup(inner);self.align_axis(inner,side,b['axis_local'],[0,0,1]);self.stage('nest-'+self.label(inner)+'-in-'+self.label(outer))
            outer_bottom=self.body_point({'actor':outer},a['bottom_local']);outer_rim=self.body_point({'actor':outer},a['rim_local']);height=float(outer_rim[2]-outer_bottom[2]);inner_profile=_profile(b['outer_profile']);inner_cavity=_profile(a['inner_profile']);chosen=None
            for offset in np.linspace(.002,height-.008,160):
                upper=min(float(inner_profile[-1,0]),height-offset)
                if upper<=0:continue
                zs=sorted(set([0.,upper,*[float(z) for z in inner_profile[:,0] if 0<z<upper]]));valid=True
                for z in zs:
                    ri=_radius(inner_profile,z);ro=_radius(inner_cavity,z+offset);valid=valid and ri is not None and ro is not None and ri<=ro-.0002
                if valid:chosen=offset;break
            if chosen is None:raise ToolExecutionError('Measured collision profiles admit no safe cup nesting')
            self.lower_place(inner,ref,side,b['bottom_local'],outer_bottom+[0,0,chosen],support=outer)

    def shoes(self):
        c=self.s['containers']['box'];label=self.s['label_end'];p,r=self.frame(label['ref']);direction=_unit(self.body_point(label['ref'],label['point_local'])-p)
        ends=(dict(left=1,right=1),dict(left=-1,right=-1),dict(left=1,right=-1))[self.index]
        for label,sign in ends.items():
            name=self.identity[label];ref,side=self.pickup(name);g=self.s['shoe_axes'][name];state=self.snapshot()[0][name];axis=state['mat']@_unit(np.asarray(g['toe_local'])-g['heel_local']);desired=direction*sign
            angle=math.atan2(desired[1],desired[0])-math.atan2(axis[1],axis[0]);rotation=_axis_rotation([0,0,1],angle)@state['mat'];target=self.body_point(c['ref'],self.geometry['box_positions'][name])
            self.stage('shoe-label-end-'+label);self.lower_place(name,ref,side,self.bottom_local(name),target,rotation,support=c['ref'].get('actor',c['ref'].get('contact_body')))

    def post_pieces(self,skip_functional=False):
        names=self.s['groups']['pieces'];selected=[n for n in names if (self.label(n).startswith('red_') if self.index==0 else self.label(n).endswith('_square') if self.index==1 else self.label(n).startswith('red_') or self.label(n).endswith('_square'))];heights={}
        for name in selected:
            placement=self.geometry['threading_targets'][name];indices=placement['post_indices'];holes=self.s['holes'][name]
            if len(indices)!=len(holes) or len(set(indices))!=len(indices):raise ToolExecutionError('Every measured hole needs a distinct insertion post')
            posts=[self.s['posts'][i] for i in indices];post=posts[0];base=self.body_point(post['ref'],post['base_local']);tip=self.body_point(post['ref'],post['tip_local']);axis=_unit(tip-base);key=tuple(sorted(indices));thickness=2*float(holes[0]['half_depth']);level=heights.get(key,0.)+float(holes[0]['half_depth'])+.001
            if skip_functional:
                from .execution_design_e10_insertion import post_clearances,physical_post_support
                state,_=self.snapshot();measured=post_clearances(self,name,indices)
                if not any(state[name]['grasp'])and name in physical_post_support(self,state,'board')and all(r['coarse_shaft_crosses_bore']for r in measured):
                    heights[key]=max(heights.get(key,0.),max(r['height_above_base_m']for r in measured)+thickness/2)
                    self.stage('preserve-physically-placed-'+name);continue
            if level+thickness>=np.linalg.norm(tip-base):raise ToolExecutionError('Actual post has no remaining insertion height')
            state,_=self.snapshot()
            held_sides=[side for side,index in(('left',0),('right',1))if state[name]['grasp'][index]]if skip_functional else[]
            if held_sides:
                from .execution_design_e10_reference import near_side_piece_ref
                ref,side=near_side_piece_ref(self,self.ref(name)),held_sides[0]
            else:
                receiver=None
                if skip_functional and float(state[name]['pos'][0])<-.20 and abs(float(state[name]['pos'][1]))<.06:
                    receiver='left'if float(base[1])>=0. else'right'
                ref,side=self.pickup(name,side=receiver)
            self.stage('thread-real-holes-'+name)
            previous=self.clearance
            if (getattr(self.a,'control_report',{}).get('engineering_reference_only')
                    and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'):
                from .execution_design_e10_reference import post_transport_height,relay_to_destination_hand
                ref,side=relay_to_destination_hand(self,name,ref,side,base+axis*level)
                self.stage('thread-real-holes-'+name)
                self.clearance=post_transport_height(self,name,side,holes[0]['center_local'],base+axis*level,placement['rotation'])
            try:
                support=post['ref'].get('actor',post['ref'].get('contact_body'))
                if (getattr(self.a,'control_report',{}).get('engineering_reference_only')
                        and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'):
                    from .execution_design_e10_insertion import thread_piece
                    thread_piece(self,name,ref,side,base+axis*level,placement['rotation'],indices,support)
                else:self.lower_place(name,ref,side,holes[0]['center_local'],base+axis*level,placement['rotation'],support=support)
            finally:self.clearance=previous
            heights[key]=level+thickness/2

    def chargers(self):
        names=self.s['groups']['chargers'];selected=((1,2),(3,4),(1,4))[self.index]
        for name,slot_id in zip(names,selected):
            if (name==names[1] and getattr(self.a,'control_report',{}).get('engineering_reference_only')
                    and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'):
                from .execution_design_e12_branch import complete_second_from_source
                complete_second_from_source(self)
                continue
            slot=self.s['slots'][str(slot_id)];pin=self.s['pins'][name][0];hole=slot['holes'][0];ha,hu,hv=_basis(hole['axis_local'],hole['u_local']);matrix=self.frame(slot['ref'])[1];ha,hu,hv=(matrix@x for x in (ha,hu,hv));pa,pu,pv=_basis(pin['axis_local'],pin['u_local']);rotation=np.stack([hu,-hv,-ha],axis=1)@np.stack([pu,pv,pa],axis=1).T
            center=self.body_point(slot['ref'],hole['center_local']);depth=min(float(pin['length'])*.85,float(hole['depth'])-.001);ref,side=self.pickup(name);self.stage('insert-both-pins-slot-'+str(slot_id))
            if (getattr(self.a,'control_report',{}).get('engineering_reference_only')
                    and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'):
                from .execution_design_e12_reference import insert_charger_precisely
                insert_charger_precisely(self,name,ref,side,slot_id,rotation,depth)
            else:self.lower_place(name,ref,side,pin['tip_local'],center-ha*depth,rotation,support=slot['ref'].get('actor',slot['ref'].get('contact_body')))

    def shelves(self):
        for name in self.s['groups']['pieces']:
            label=self.label(name);upper=label.startswith('blue_') if self.index==0 else label.endswith('_triangle') if self.index==1 else True;layer='upper' if upper else 'lower';shelf=self.s['shelves'][layer];ref,side=self.pickup(name);self.stage('source-shelf-'+layer+'-'+name)
            target=self.body_point(shelf['ref'],self.geometry['shelf_positions'][name]);self.lower_place(name,ref,side,self.bottom_local(name),target,support=shelf['ref'].get('actor',shelf['ref'].get('contact_body')))

    def caps(self):
        home_xy={side:self.tip(side)[:2].copy() for side in ('left','right')}
        colors=(['yellow','white','red'],['red','yellow','white'],['white','red','yellow'])[self.index]
        for bottle_label,color in zip(['sprite_bottle','water_bottle','cola_bottle'],colors):
            bottle=self.identity[bottle_label];cap=next(n for n in self.s['caps'] if self.label(n).removeprefix('cap_')==color);mouth=self.s['mouths'][bottle];cover=self.s['caps'][cap]
            chosen=None
            if (getattr(self.a,'control_report',{}).get('engineering_reference_only')
                    and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'):
                from .execution_design_e19_reference import choose_cap_hand
                chosen=choose_cap_hand(self,cap,self.body_point({'actor':bottle},mouth['center_local']))
            ref,side=self.pickup(cap,side=chosen);axis=self.frame({'actor':bottle})[1]@_unit(mouth['axis_local']);self.align_axis(cap,side,cover['axis_local'],axis)
            target=self.body_point({'actor':bottle},mouth['center_local'])-axis*cover['depth'];self.stage('cap-real-mouth-'+bottle_label)
            if (getattr(self.a,'control_report',{}).get('engineering_reference_only')
                    and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'):
                from .execution_design_e19_reference import place_cap
                place_cap(self,cap,ref,side,cover['center_local'],target,bottle,home_xy[side])
            else:self.lower_place(cap,ref,side,cover['center_local'],target,support=bottle)

    def branches(self):
        branches=self.s['branches'];heights={k:self.body_point(v['ref'],v['tip_local'])[2] for k,v in branches.items()};groups=[]
        for key in sorted(heights,key=heights.get,reverse=True):
            if not groups or abs(heights[key]-heights[groups[-1][0]])>.01:groups.append([])
            groups[-1].append(key)
        if len(groups)!=3:raise ToolExecutionError('Three actual branch levels required')
        order=(['red','green','blue'],['red','blue','green'],['blue','green','red'])[self.index]
        for label,group in zip(order,groups):
            name=self.identity[label];branch=branches[group[0]];cup=self.s['cups'][name];ref,side=self.pickup(name)
            base=self.body_point(branch['ref'],branch['base_local']);tip=self.body_point(branch['ref'],branch['tip_local']);direction=_unit(tip-base)
            self.align_axis(name,side,cup['axis_local'],-direction);height=float(np.linalg.norm(np.asarray(cup['rim_local'])-cup['bottom_local']));target=tip-direction*(height-.008)
            self.stage('cup-mouth-over-real-branch-'+label);control=dict(actor=name,local=cup['rim_local']);guard=lambda:self.require_held(ref,side)
            entry=tip+direction*.03;clearance=max(self.clearance,float(entry[2])+.07)
            self.move_point(side,control,[*self.point(control)[:2],clearance],guard)
            self.move_point(side,control,[*entry[:2],clearance],guard);self.move_point(side,control,entry,guard)
            # The cup mouth enters along the actual branch axis. A vertical
            # drop would scrape a horizontal branch through the side wall.
            self.move_point(side,control,target,guard);self.release(ref,side)
            self.move(side,self.tip(side)+direction*.03+[0,0,.04]);self.wait(3)
            support=branch['ref'].get('actor',branch['ref'].get('contact_body'))
            if not self.contact(name,support):raise ToolExecutionError('Released cup lacks real branch support')

    def box_and_lid(self):
        order=(['red','green','blue'],['green','blue','red'],['blue','red','green'])[self.index];box=self.s['containers']['box']
        for label,point in zip(order,self.geometry['box_positions']):
            name=self.identity[label];cup=self.s['cups'][name];ref,side=self.pickup(name);self.align_axis(name,side,cup['axis_local'],[0,0,1]);self.stage('first-source-box-insertion-'+label);target=self.body_point(box['ref'],point);self.lower_place(name,ref,side,cup['bottom_local'],target,support=box['ref'].get('actor',box['ref'].get('contact_body')))
        lid=self.s['lid_geometry'];name=lid['ref']['actor'];ref,side=self.pickup(name);target=self.body_point(lid['box_ref'],lid['box_rim_center_local']);matrix=self.frame(lid['box_ref'])[1];target+=matrix[:,2]*lid['closed_offset_m'];self.stage('close-real-lid-after-cup-releases');self.lower_place(name,ref,side,lid['cover_center_local'],target,matrix,support=lid['box_ref'].get('actor',lid['box_ref'].get('contact_body')))

    def screws(self):
        roles=(['left'],['right'],['left','right'])[self.index]
        for role in roles:
            entry=self.s['screw_roles'][role];driver=entry['driver'];name=driver['actor'];ref=dict(actor=name,**self.geometry['driver_grasp']);side='right'
            if self.a.scene.embodiment.config.get('author_recording',{}).get('e37_axial_edge_acquire',False):
                from .author_e37_edge_private import acquire_driver_edge
                acquire_driver_edge(self,ref,side)
            else:self.acquire(ref,side)
            isolated_v3=(self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                         and getattr(self.a,'control_report',{}).get('engineering_reference_only'))
            if isolated_v3 or self.a.scene.embodiment.config.get('author_recording',{}).get('lift_tool_before_orientation',False):
                self.stage('lift-driver-clear-of-table')
                # Native v3 evidence showed 3.8--6.9 N table collision while
                # rotating the still-grasped long driver at z=0.83 m. Lift
                # the actual payload first; never force rotation through it.
                self.move(side,[*self.tip(side)[:2],max(self.clearance,self.tip(side)[2]+.10)],lambda:self.require_held(ref,side))
                if isolated_v3 and self.contact(name,'table'):
                    raise ToolExecutionError('Driver still contacts table after actual clearance lift')
            fixture=entry['fixture'];axis=self.frame(fixture['ref'])[1]@_unit(fixture['axis_local']);tip=dict(actor=name,local=driver['tip_local']);screw=entry['screw'];head=lambda:self.body_point({'actor':screw},entry['head_socket_local'])
            if self.a.scene.embodiment.config.get('author_recording',{}).get('e37_verified_head_approach',False):
                from .author_mplib_planner import plan,_quat,_rotation as quat_rotation
                from .author_orientation import _axis_angle
                current=self.snapshot()[0][name]['mat'];a=current@_unit(driver['axis_local']);b=-axis
                turn=np.cross(a,b);angle=float(np.arccos(np.clip(a@b,-1.,1.)))
                if np.linalg.norm(turn)<1e-8:turn=np.array([0.,1.,0.])
                delta=_axis_rotation(turn,angle)
                if self.a.scene.embodiment.config.get('author_recording',{}).get('e37_slot_plane_alignment',False):
                    # Original source triangle sections: the blade is broad
                    # along driver local Z and the slot along screw local X.
                    # The two signs describe the same physical slot plane.
                    slot=self.snapshot()[0][screw]['mat']@_unit(entry['radial_local'])
                    slot=_unit(slot-axis*float(slot@axis))
                    if float(slot@current[:,2])<0:slot=-slot
                    driver_x=-axis;driver_y=_unit(np.cross(slot,driver_x))
                    desired=np.column_stack((driver_x,driver_y,np.cross(driver_x,driver_y)))
                    delta=desired@current.T
                robot=self.a.scene.robots[side]
                hand=self.a.scene.layout.task_rotation.T@quat_rotation(robot.data.root_quat_w[0].cpu().tolist())@quat_rotation(self.c.pose(side)[1][0].cpu().tolist())
                tcp=head()+axis*.03+delta@(self.tip(side)-self.point(tip))
                proposal=plan(self.a.scene,self.c,side,tcp.tolist(),task_tcp_quaternion=_quat(delta@hand).tolist())
                import json
                (self.a.out/'E37-real-driver-head-plan.private.json').write_text(json.dumps(proposal,default=lambda x:x.tolist(),indent=2)+'\n')
                if proposal.get('status')!='Success' or proposal.get('verified') is not True:raise ToolExecutionError('No verified loaded driver path above actual source head')
                self.stage('source-driver-fullworld-to-head-'+role)
                self.a.execute_joint_path(side,proposal,guard=lambda:self.require_held(ref,side))
            else:
                if isolated_v3:
                    from .execution_design_e37_approach import above_head
                    above_head(self,ref,side,driver,entry,axis,head)
                else:self.align_axis(name,side,driver['axis_local'],-axis)
                self.stage('driver-working-tip-approach-'+role)
                self.move_point(side,tip,head()+axis*.03,lambda:self.require_held(ref,side))
            self.stage('source-driver-actual-slot-engagement-'+role)
            self.move_point(side,tip,head()-axis*min(.002,entry['socket_depth']*.6),lambda:self.require_held(ref,side),tolerance=.0005)
            component=int(np.argmax(abs(axis)));sign=axis[component]*entry['unscrew_direction'];token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[component][int(sign<0)];history=[];self.stage('actual-thread-unscrew-'+role)
            freeplay_degrees=0.
            for _ in range(900):
                self.require_held(ref,side);base=self.body_point({'actor':screw},entry['thread_base_local']);origin=self.body_point(fixture['ref'],fixture['origin_local']);axial=float((base-origin)@axis);low,high=fixture['interval'];overlap=max(0.,min(axial+entry['thread_length'],high)-max(axial,low))
                fixture_contact=fixture['ref'].get('actor',fixture['ref'].get('contact_body'))
                if overlap<=0 and not self.contact(screw,fixture_contact):break
                if not self.contact(name,screw):
                    if not self.a.scene.embodiment.config.get('author_recording',{}).get('e37_measured_socket_freeplay',False):
                        raise ToolExecutionError('Driver lost actual screw-head engagement')
                    offset=self.point(tip)-head();depth=-float(offset@axis)
                    radial=float(np.linalg.norm(offset-axis*float(offset@axis)))
                    limit=entry['socket_radius']-driver['tip_radius']+.0003
                    if not(0<depth<=entry['socket_depth']+.001 and radial<=limit and freeplay_degrees<30):
                        raise ToolExecutionError('Source tip left real socket geometry during bounded freeplay takeup')
                    self.act(side,token,degrees=1.)
                    self.move_point(side,tip,head()-axis*min(.002,entry['socket_depth']*.6),lambda:self.require_held(ref,side),tolerance=.0005)
                    freeplay_degrees+=1.
                    continue
                freeplay_degrees=0.
                self.act(side,token,degrees=5.);self.move_point(side,tip,head()-axis*min(.002,entry['socket_depth']*.6),lambda:self.require_held(ref,side),tolerance=.0005);history.append(axial)
                if len(history)>30 and history[-1]-history[-30]<.00005:raise ToolExecutionError('Actual thread failed to advance under driver torque')
            else:raise ToolExecutionError('Unscrewing action budget exhausted')
            self.move_point(side,tip,self.point(tip)+axis*.05,lambda:self.require_held(ref,side))
            # The removed free screw is placed by the other actual hand.
            screwref=self.ref(screw);self.acquire(screwref,'left');destination=self.geometry['removed_screw_placements'][role];self.lower_place(screw,screwref,'left',screwref['local'],destination['point_task'],destination['rotation'],support='table')
            self.release(ref,side);self.move(side,self.tip(side)+[0,0,.06])


def solve_structural(author):
    policy=StructuralAuthor(author)
    try:
        method={'E01':'food','E03':'nest','E08':'shoes','E10':'post_pieces','E12':'chargers','E17':'shelves','E19':'caps','E23':'branches','E24':'box_and_lid','E37':'screws'}[policy.task]
        getattr(policy,method)();policy.wait(4)
        from .author_clearance import finish_single_hand
        finish_single_hand(author)
    except (KeyError,ValueError,TypeError,IndexError) as exc:raise ToolExecutionError('Incomplete reviewed structural geometry: '+str(exc)) from exc
    return dict(task=policy.task,variant=policy.variant,actions=policy.c.steps-policy.start,operations=policy.operations,execution_finished=True,physics_success_not_asserted=True)


__all__=['StructuralAuthor','solve_structural','SUPPORTED']
