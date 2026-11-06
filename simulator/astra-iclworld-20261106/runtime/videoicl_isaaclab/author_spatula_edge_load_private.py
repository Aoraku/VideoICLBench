"""Private source-authorized auxiliary edge loading, then genuine tool-only carry.

Only the selected source cargo spawn is near the supported table edge. All
subsequent motion uses native actuators and measured source material geometry.
"""
from __future__ import annotations
import json
from itertools import product
import numpy as np
from .author_spatula_support_private import SourceSupportAuthor
from .author_spatula_scoop_private import ScoopContacts,LINKS
from .realworld_tool_expert import _push_rotation,_unit,_axis_rotation


def edge_clearance(fingers,palm,bounds,margin=.0003):
    bounds=np.asarray(bounds,float);palm=np.asarray(palm,float)
    if bounds.shape!=(2,3)or len(fingers)!=2 or any(np.asarray(p).ndim!=2 or np.asarray(p).shape[1]!=3 for p in fingers):raise ValueError('Actual complete native meshes/table required')
    if any(float(np.asarray(p)[:,0].max())>=bounds[0,0]-margin for p in fingers):raise RuntimeError('Complete native finger mesh crosses table front during low edge acquisition')
    if float(palm[:,2].min())<bounds[1,2]+margin and float(palm[:,0].max())>=bounds[0,0]-margin:raise RuntimeError('Actual native palm is neither above nor wholly outside the real table')
    return dict(finger_max_x_task_m=[float(np.asarray(p)[:,0].max())for p in fingers],palm_min_z_task_m=float(palm[:,2].min()),palm_max_x_task_m=float(palm[:,0].max()),palm_entirely_outside_table_x=bool(palm[:,0].max()<bounds[0,0]-margin),table_bounds_task_m=bounds.tolist())


def tool_station_tcp_goal(actual_tool,actual_tcp,work_local,work_task,target_rotation):
    tool=np.eye(4);tool[:3,:3]=np.asarray(target_rotation,float);tool[:3,3]=np.asarray(work_task,float)-tool[:3,:3]@np.asarray(work_local,float)
    return tool@np.linalg.inv(np.asarray(actual_tool,float))@np.asarray(actual_tcp,float),tool


def complete_hand_vertical_clearance(fingers,palm,bounds,margin=.012):
    """Translate the actual whole hand above the table before crossing its edge."""
    bounds=np.asarray(bounds,float);clouds=[np.asarray(p,float)for p in [*fingers,palm]]
    if bounds.shape!=(2,3)or len(fingers)!=2 or any(p.ndim!=2 or p.shape[1]!=3 or not len(p)or not np.isfinite(p).all()for p in clouds):raise ValueError('Complete finite native hand meshes required')
    if not np.isfinite(margin)or margin<.002:raise ValueError('Positive physical clearance required')
    minimum=min(float(p[:,2].min())for p in clouds)
    return max(.040,float(bounds[1,2])+margin-minimum)


class NativeEdgeGeometry:
    def __init__(self,a):
        from pxr import Usd,UsdGeom,UsdPhysics
        import omni.usd
        self.a=a;self.parts={};stage=omni.usd.get_context().get_stage();cache=UsdGeom.XformCache()
        table=UsdGeom.BBoxCache(0,[UsdGeom.Tokens.default_,UsdGeom.Tokens.render]).ComputeWorldBound(stage.GetPrimAtPath('/World/Table')).ComputeAlignedRange()
        corners=np.asarray([a.scene.world_to_task(np.asarray(p,float))for p in product(*zip(table.GetMin(),table.GetMax()))]);self.bounds=np.array([corners.min(0),corners.max(0)])
        for side in('left','right'):
            a.floor_clear_tcp(side);robot=a.scene.robots[side];prim=stage.GetPrimAtPath(f'/World/{side}_robot/panda_hand');inverse=cache.GetLocalToWorldTransform(prim).GetInverse();pieces=[]
            for child in Usd.PrimRange(prim,Usd.TraverseInstanceProxies()):
                ancestor=child;collidable=False
                while ancestor and ancestor!=prim:
                    if ancestor.HasAPI(UsdPhysics.CollisionAPI):collidable=True;break
                    ancestor=ancestor.GetParent()
                if child.IsA(UsdGeom.Mesh)and collidable:
                    M=np.asarray(cache.GetLocalToWorldTransform(child)*inverse,float);p=np.asarray(UsdGeom.Mesh(child).GetPointsAttr().Get(),float);pieces.append(p@M[:3,:3]+M[3,:3])
            if not pieces:raise RuntimeError('Actual source native palm mesh unavailable')
            self.parts[side]=(robot.find_bodies('panda_hand')[0][0],np.concatenate(pieces))
    def clouds(self,side,goal=None):
        from .author_orientation import _quaternion_matrix
        a=self.a;robot=a.scene.robots[side];delta=np.zeros(3)if goal is None else np.asarray(goal)-a.tip(side)
        def project(bid,p):
            R=a.scene.layout.task_rotation.T@_quaternion_matrix(robot.data.body_quat_w[0,bid].cpu().numpy());pos=a.scene.world_to_task(robot.data.body_pos_w[0,bid].cpu().numpy());return np.asarray(p)@R.T+pos+delta
        return [project(bid,p)for bid,p in a._finger_collision_points[side]],project(*self.parts[side])
    def check(self,side,goal=None):return edge_clearance(*self.clouds(side,goal),self.bounds)
    def low(self,side):return min(float(p[:,2].min())for p in self.clouds(side)[0])<self.bounds[1,2]+.002


class SourceEdgeContacts(ScoopContacts):
    def __init__(self,scene):
        from isaaclab.sensors import ContactSensor,ContactSensorCfg
        self.cargo_actors=list(scene.spec['semantic']['groups']['cargo']);self.actors=[o['id']for o in scene.spec['objects']]+['table'];self.sensors={}
        for side in('left','right'):
            for link in LINKS:self.sensors[(side,link)]=ContactSensor(ContactSensorCfg(prim_path=f'/World/{side}_robot/{link}',filter_prim_paths_expr=['/World/Table'if n=='table'else'/World/Props/'+n for n in self.actors],history_length=0,update_period=0.))


class SourceEdgeLoadAuthor(SourceSupportAuthor):
    def validate_initial_source_world(self):
        from .author_mplib_planner import capture_scene,plan_snapshot
        from pathlib import Path
        import os
        panel=self.contacts.read(self.c.dt);unexpected={str(k):v for k,v in panel.items()if v>.001 and not(k[2]=='table'and k[1]=='panda_link0')}
        from .author_native_grip_probe import cpu_copy
        robot=self.a.scene.robots[self.other];fingers=self.c.ids[self.other][1];effort=cpu_copy(robot.root_physx_view.get_dof_max_forces())[0,fingers];velocity=cpu_copy(robot.root_physx_view.get_dof_max_velocities())[0,fingers];limits=dict(side=self.other,native_effort_limit_n=effort.tolist(),native_velocity_limit_m_s=velocity.tolist())
        requested=self.a.scene.embodiment.config['author_recording'].get('edge_loading_hand_limits')
        if requested and(not np.allclose(effort,requested['effort_limit_n'],atol=1e-6)or not np.allclose(velocity,requested['velocity_limit_m_s'],atol=1e-6)):raise RuntimeError('Private loading-hand drive limits not applied in actual native view: '+str(limits))
        snapshot=capture_scene(self.a.scene,self.c,self.other,self.tip(self.other).tolist());profile=json.loads(Path(os.path.expandvars(snapshot['profile'])).read_text());profile['seeds']=[];result=plan_snapshot(snapshot,profile);diagnostics=result.get('diagnostics',{})
        valid=not unexpected and diagnostics.get('world_coverage_verified')is True and not diagnostics.get('error')and diagnostics.get('start_collisions')==[]
        (self.a.out/'edge-source-initial-workcell-validation.private.json').write_text(json.dumps(dict(reset_only_robot_initial_configuration=True,actual_native_robot_prop_contacts=unexpected,actual_loading_hand_drive_limits=limits,initial_static_world_valid=valid,native_scene=snapshot,static_validation_diagnostics=diagnostics,no_motion_requested=True,source_task_success_claimed=False),indent=2)+'\n')
        if not valid:raise RuntimeError('Fresh native initial workcell rejected: '+str(unexpected or diagnostics.get('error')or diagnostics.get('start_collisions')))
    def pinch_witness(self):
        from .author_mplib_planner import _rotation
        from .author_native_grip_probe import cpu_copy
        sensor,labels=self.a.scene.contacts[self.cargo];matrix=cpu_copy(sensor.data.force_matrix_w)[0].sum(axis=0)
        f=[self.a.scene.layout.task_rotation.T@matrix[labels.index(self.other+'_finger'+str(i))]for i in(1,2)]
        robot=self.a.scene.robots[self.other];R=self.a.scene.layout.task_rotation.T@_rotation(robot.data.root_quat_w[0].cpu().tolist())@_rotation(self.c.pose(self.other)[1][0].cpu().tolist());axis=R[:,1];projections=[float(v@axis)for v in f];norms=[float(np.linalg.norm(v))for v in f];opposition=float(-f[0]@f[1]/max(norms[0]*norms[1],1e-15))
        valid=projections[0]<-1. and projections[1]>1. and opposition>.9
        return dict(valid=bool(valid),native_normal_force_on_cargo_task_n=[v.tolist()for v in f],measured_hand_jaw_axis_task=axis.tolist(),jaw_projections_n=projections,normal_opposition_cos=opposition,public_grasp_flag=self.held(self.cargo_ref,self.other))
    def rotate_actor(self,actor,side,target):
        try:return super().rotate_actor(actor,side,target)
        except RuntimeError as error:
            if not str(error).startswith('Continuous orientation target not reached:'):raise
            measured=self.snapshot()[0][actor]['mat'];normal=measured@_unit(self.s['tools']['main']['support_normal_local']);forward=measured@_unit(self.s['edge_outward_normal_local'])
            wanted=np.asarray(target)@_unit(self.s['edge_outward_normal_local']);wanted[2]=0.;wanted=_unit(wanted)
            horizontal=forward.copy();horizontal[2]=0.;horizontal=_unit(horizontal)
            # The exact author yaw is only a route choice. All subsequent
            # material targets use actual measured frames; source normal and
            # physical grip/contact criteria remain unchanged.
            required_normal=min(.98,float((np.asarray(target)@_unit(self.s['tools']['main']['support_normal_local']))[2])-.01)
            if normal[2]<required_normal or float(horizontal@wanted)<np.cos(np.deg2rad(3.)):raise
            self.require_held({'actor':actor},side)
            with(self.a.out/'edge-author-partial-waypoints.private.jsonl').open('a')as f:f.write(json.dumps(dict(stage=self.a.stage,author_orientation_incomplete=str(error),actual_blade_normal_task=normal.tolist(),actual_forward_task=forward.tolist(),source_rule_modified=False))+'\n')
    def destination(self,name,slot=0):
        point=super().destination(name,slot)
        if self.task=='E28':
            goal=next(g for g in self.spec['goals']if g.get('object')==name)
            zone=next(z for z in self.spec['zones']if z['id']==goal['target'])
            point[:2]=np.asarray(goal.get('placement_xy',zone['xy']),float)
        return point
    def force(self,x,y):
        value=self.c.contact_forces.get(frozenset((x,y)))
        if value is None or not np.isfinite(value)or value<0:raise RuntimeError('Missing native contact '+x+'/'+y)
        return float(value)
    def guard(self):
        state,_=self.snapshot();panel=self.contacts.read(0.)
        if self.holding:self.require_held(self.grip,self.side)
        if getattr(self,'cargo_carrying',False):
            self.require_held(self.cargo_ref,self.other)
            if not self.pinch_witness()['valid']:raise RuntimeError('Actual opposing source cargo pinch lost')
        if self.edge_phase and self.geometry.low(self.other):self.geometry.check(self.other)
        allowed_cargo={(self.other,'panda_leftfinger'),(self.other,'panda_rightfinger')}if self.loading else set()
        for(s,link,actor),value in panel.items():
            if value<=.001:continue
            if actor in self.contacts.cargo_actors and(actor!=self.cargo or(s,link)not in allowed_cargo):raise RuntimeError('Native hand-cargo contact outside source auxiliary loading phase '+str((s,link,actor,value)))
            if actor==self.tool_actor and(s,link)not in{(self.side,'panda_leftfinger'),(self.side,'panda_rightfinger')}:raise RuntimeError('Actual non-holding robot body contacts blade '+str((s,link,value)))
        if self.carrying:
            if any(state[self.cargo]['grasp']):raise RuntimeError('Cargo hand-held during claimed tool-only carry')
            if self.force(self.cargo,'table')>.001 or self.force(self.cargo,self.tool_actor)<=.001:raise RuntimeError('Tool-only carry lacks actual table-free tool support')
            normal=state[self.tool_actor]['mat']@_unit(self.tool['support_normal_local'])
            if normal[2]<=.8:raise RuntimeError('Loaded source blade is not supporting upward')
        if self.c.physics_ticks!=getattr(self,'logged_tick',None):
            with(self.a.out/'edge-load-native-guard.private.jsonl').open('a')as f:f.write(json.dumps(dict(stage=self.a.stage,physics_tick=self.c.physics_ticks,cargo=self.cargo,source_auxiliary_loading=self.loading,table_edge_phase=self.edge_phase,tool_only_carry=self.carrying,tool_held=self.holding,cargo_task_pos=state[self.cargo]['pos'].tolist(),cargo_grasp=state[self.cargo]['grasp'],native_cargo_pinch=self.pinch_witness()if self.loading and hasattr(self,'cargo_ref')else None,tool_cargo_force_n=self.force(self.cargo,self.tool_actor),cargo_table_force_n=self.force(self.cargo,'table'),native_robot_cargo_force_n={'/'.join((s,b)):v for(s,b,n),v in panel.items()if n==self.cargo},tool_normal_z=float((state[self.tool_actor]['mat']@_unit(self.tool['support_normal_local']))[2])))+'\n')
            self.logged_tick=self.c.physics_ticks
    def tick(self,controller,render):self.contacts.read(controller.dt);self.guard()
    def hold_both(self):
        self.guard();self.require_held(self.cargo_ref,self.other)
        if not self.pinch_witness()['valid']:raise RuntimeError('Missing actual opposing source cargo pinch')
    def acquire_cargo(self,name):
        from .author_native_grip_probe import cpu_copy
        self.cargo=name;state,_=self.snapshot();body=state[name];obj=self.a.scene.objects[name];com=cpu_copy(obj.root_physx_view.get_coms())[0,:3];actual_com=body['pos']+body['mat']@com
        if self.force(name,'table')<=.001 or np.any(actual_com[:2]<=self.geometry.bounds[0,:2]+.002)or np.any(actual_com[:2]>=self.geometry.bounds[1,:2]-.002):raise RuntimeError('Selected cargo lacks genuine initial supported COM inside actual table')
        self.loading=True;ref=dict(actor=name,**self.s['cargo_grasps'][name]);self.cargo_ref=ref
        self.stage('edge-source-horizontal-outside-stand');self.act(self.other,'RELEASE')
        from .author_mplib_planner import _rotation,_quat
        robot=self.a.scene.robots[self.other];hand_R=self.a.scene.layout.task_rotation.T@_rotation(robot.data.root_quat_w[0].cpu().tolist())@_rotation(self.c.pose(self.other)[1][0].cpu().tolist());goal_R=np.array([[0,0,1],[1,0,0],[0,1,0]],float);point=self.point(ref);actual=self.tip(self.other);angle=float(np.arccos(np.clip((np.trace(hand_R@goal_R.T)-1)/2,-1,1)))
        if not(np.linalg.norm(actual[1:2]-point[1:2])<=.002 and .020<=point[0]-actual[0]<=.050 and angle<np.deg2rad(1.)):
            stand=point+[-.030,0,0];self.global_empty_pregrasp(dict(position=stand.tolist(),quaternion=_quat(goal_R).tolist()))
        self.edge_phase=True;self.c.grips[self.other]=.012;self.act()
        self.move(self.other,[*self.tip(self.other)[:2],point[2]],self.guard,tolerance=.0015)
        point=self.point(ref);proof=self.geometry.check(self.other,point)
        (self.a.out/('edge-initial-support-'+name+'.private.json')).write_text(json.dumps(dict(selected=name,source_auxiliary_loading_hand_allowed=self.s['auxiliary_loading_hand_allowed'],actual_native_com_task=actual_com.tolist(),actual_initial_table_force_n=self.force(name,'table'),actual_grasp_material_local=ref['local'],actual_tcp_goal=point.tolist(),post_reset_actor_pose_written=False,**proof),indent=2)+'\n')
        self.stage('edge-source-horizontal-upper-lower-grasp');self.move(self.other,point,self.guard,tolerance=.0015)
        stable=0;half=float(self.a.scene.embodiment.config['author_recording']['edge_cargo_closing_half_height_m'][name]);closing=min(.012,half+.001)
        for index in range(24):
            self.c.grips[self.other]=closing;self.act();witness=self.pinch_witness();valid=self.held(ref,self.other)and witness['valid'];stable=stable+1 if valid else 0
            with(self.a.out/'edge-actual-adaptive-pinch.private.jsonl').open('a')as stream:stream.write(json.dumps(dict(physics_tick=self.c.physics_ticks,actor=name,iteration=index,native_per_finger_target_m=closing,measured_opposing_normal=witness,source_mesh_and_grasp_flag_unchanged=True))+'\n')
            if stable>=3:break
            if not valid:closing=max(0.,closing-.00025)
        else:raise RuntimeError('No genuine opposing native upper/lower cargo pinch')
        self.cargo_carrying=True;self.stage('edge-source-vertical-clearance-lift')
        fingers,palm=self.geometry.clouds(self.other);rise=complete_hand_vertical_clearance(fingers,palm,self.geometry.bounds)
        self.move(self.other,self.tip(self.other)+[0,0,rise],self.hold_both,tolerance=.002)
        after_fingers,after_palm=self.geometry.clouds(self.other)
        if min(float(p[:,2].min())for p in [*after_fingers,after_palm])<self.geometry.bounds[1,2]+.009:raise RuntimeError('Complete actual auxiliary hand did not clear table before horizontal loading')
        (self.a.out/('edge-whole-hand-lift-'+name+'.private.json')).write_text(json.dumps(dict(actual_vertical_lift_requested_m=rise,before_palm_min_z_task_m=float(palm[:,2].min()),after_palm_min_z_task_m=float(after_palm[:,2].min()),actual_table_top_z_task_m=float(self.geometry.bounds[1,2]),source_cargo_geometry_modified=False),indent=2)+'\n')
        self.edge_phase=False
    def begin_loading_hold(self):
        robot=self.a.scene.robots[self.side];arm=self.c.ids[self.side][0];q=robot.data.joint_pos[:,arm].clone();overrides=self.c._author_joint_override
        self._loading_hold_previous=overrides.get(self.side);self._loading_hold_active=True;overrides[self.side]=(q,q*0.)
    def restore_loading_hold(self):
        if not getattr(self,'_loading_hold_active',False):return
        overrides=self.c._author_joint_override;previous=self._loading_hold_previous
        if previous is None:overrides.pop(self.side,None)
        else:overrides[self.side]=previous
        pose=self.c.pose(self.side);self.c.targets[self.side]=(pose[0].clone(),pose[1].clone());self._loading_hold_active=False
    def global_empty_pregrasp(self,request):
        from .author_mplib_planner import capture_scene,plan_snapshot
        from pathlib import Path
        import os
        snapshot=capture_scene(self.a.scene,self.c,self.other,request);profile=json.loads(Path(os.path.expandvars(snapshot['profile'])).read_text());result=plan_snapshot(snapshot,profile)
        prefix=self.a.out/('edge-source-'+self.a.stage+'-'+self.cargo+'-'+str(self.c.physics_ticks))
        prefix.with_suffix('.scene.private.json').write_text(json.dumps(snapshot,indent=2)+'\n');prefix.with_suffix('.plan.private.json').write_text(json.dumps(result,indent=2)+'\n')
        if result.get('verified')is not True:raise RuntimeError('Fullworld auxiliary loading path refused: '+str(result.get('diagnostics',{}).get('error',result.get('status'))))
        self.a.execute_joint_path(self.other,result,guard=self.guard);self.guard()
    def transfer(self,name,index):
        self.begin_loading_hold()
        self.acquire_cargo(name)
        center=dict(actor=name,local=[0,0,0]);normal=self.frame(self.work)[1]@_unit(self.tool['support_normal_local']);obj=next(o for o in self.spec['objects']if o['id']==name);extent=float(abs(self.snapshot()[0][name]['mat'].T@normal)@np.asarray(obj['size']))
        # Real front-edge handoff: the supporting lower finger remains beyond
        # the original blade tip. Open the actual vertical pinch above
        # the face; the original blade supports the cargo without hand contact.
        # A13.5mm real release gap keeps the source curved/convex blade clear
        # during the certified approach. Gravity, without any pose write or
        # contact exemption, must then establish actual blade support.
        front=dict(actor=self.tool_actor,local=[.1255,0.,float(self.tool['support_plane_offset']-.1255*self.tool['support_normal_local'][0])]);target=self.point(front)+normal*(extent+.0135)
        from .author_mplib_planner import _rotation,_quat
        robot=self.a.scene.robots[self.other];R=self.a.scene.layout.task_rotation.T@_rotation(robot.data.root_quat_w[0].cpu().tolist())@_rotation(self.c.pose(self.other)[1][0].cpu().tolist())
        self.stage('edge-source-global-cargo-over-blade')
        self.global_empty_pregrasp(dict(position=(self.tip(self.other)+target-self.point(center)).tolist(),quaternion=_quat(R).tolist()))
        self.hold_both()
        self.stage('edge-source-actual-release-on-blade');self.cargo_carrying=False;self.release(self.cargo_ref,self.other)
        # Raising an open vertical pinch lifts its lower pad through cargo
        # overhanging the blade. Retract opposite the measured approach axis,
        # keeping both real fingers clear of the loaded material instead.
        hand_R=self.a.scene.layout.task_rotation.T@_rotation(robot.data.root_quat_w[0].cpu().tolist())@_rotation(self.c.pose(self.other)[1][0].cpu().tolist())
        self.stage('edge-source-empty-hand-outward-withdraw');self.move(self.other,self.tip(self.other)-hand_R[:,2]*.080,self.guard);self.wait(3)
        if self.force(name,self.tool_actor)<=.001 or any(self.snapshot()[0][name]['grasp']):raise RuntimeError('Actual cargo did not settle ungrasped on source blade')
        self.restore_loading_hold();self.loading=False;self.carrying=True;self.guard()
        travel=np.array([0.,1.,0.])if self.task=='E28'or self.variant in('A','B')else np.array([-1.,0.,0.]);target_rotation=_push_rotation(self.tool['support_normal_local'],self.s['edge_outward_normal_local'],travel)
        self.stage('edge-source-real-loaded-heading');self.rotate_actor(self.tool_actor,self.side,target_rotation);self.guard()
        start=self.snapshot()[0][name]['pos'].copy();dest=self.destination(name,index);height=max(dest[2]+.08,.94,float(start[2]))
        def move_cargo(target):
            # Recompute real cargo-to-tool offset at each native phase.
            state,_=self.snapshot();offset=state[name]['pos']-self.point(self.work);self.move_point(self.side,self.work,np.asarray(target)-offset,self.guard,tolerance=.002)
        self.stage('edge-source-tool-only-lift');move_cargo([*start[:2],height])
        self.stage('edge-source-tool-only-carry');move_cargo([*dest[:2],height])
        self.carrying=False;self.stage('edge-source-low-offload');actual=self.snapshot()[0][name];vertical_extent=float(abs(actual['mat'][2])@np.asarray(obj['size']))
        support='table';release_height=.008
        if self.task=='E28':
            support=self.s['containers']['plate']['object'];plate=self.snapshot()[0][support];plate_spec=next(o for o in self.spec['objects']if o['id']==support)
            rim=float(plate['pos'][2]+abs(plate['mat'][2])@np.asarray(plate_spec['size']))
            release_height=max(.015,rim-float(dest[2])+.008)
        # Keep the level blade above the actual plate rim. A flat retreat only
        # carries sticky food backwards; unload by real gravity about its edge.
        try:move_cargo([*dest[:2],dest[2]+vertical_extent+release_height])
        except RuntimeError as error:
            if self.task!='E28'or not str(error).startswith('Continuous author waypoint unreachable at edge-source-low-offload;'):raise
            state,_=self.snapshot();food=state[name];plate=state[support];container=self.s['containers']['plate'];local=plate['mat'].T@(food['pos']-plate['pos']);radius=abs(plate['mat'].T@food['mat'])@np.asarray(obj['size']);bottom=float(food['pos'][2]-abs(food['mat'][2])@np.asarray(obj['size']));rim=float(plate['pos'][2]+abs(plate['mat'][2])@np.asarray(plate_spec['size']))
            inside=bool(np.all(local[:2]-radius[:2]>=np.asarray(container['lower'])[:2])and np.all(local[:2]+radius[:2]<=np.asarray(container['upper'])[:2]))
            # This intermediate TCP waypoint is not the source goal. A real
            # still-supported load over the original finite plate, with its
            # whole footprint inside and safe rim height, may unload there.
            if not inside or not .002<=bottom-rim<=.035 or self.force(name,self.tool_actor)<=.001:raise
            self.guard()
            with(self.a.out/'edge-author-partial-waypoints.private.jsonl').open('a')as stream:stream.write(json.dumps(dict(stage=self.a.stage,author_error=str(error),actual_cargo_plate_local=local.tolist(),actual_cargo_projected_half_extent=radius.tolist(),actual_cargo_bottom_above_rim_m=bottom-rim,actual_whole_footprint_inside_original_plate=inside,source_goal_modified=False))+'\n')
        from .author_orientation import native_rotate
        edge=np.asarray(self.tool.get('edge_segment',self.s['edge_segment_local']),float)
        if edge.shape!=(2,3)or not np.isfinite(edge).all():raise RuntimeError('Original source front-edge segment required for offload')
        pivot=self.point(dict(actor=self.tool_actor,local=edge.mean(axis=0))).copy();forward=self.frame(self.work)[1]@_unit(self.s['edge_outward_normal_local']);forward[2]=0.;forward=_unit(forward)
        def unloaded():return self.force(name,support)>.001 and self.force(name,self.tool_actor)<=.001 and not any(self.snapshot()[0][name]['grasp'])
        def target_contact():
            normal=self.frame(self.work)[1]@_unit(self.tool['support_normal_local'])
            return self.force(name,support)>.01 and not any(self.snapshot()[0][name]['grasp'])and(normal[2]<np.cos(np.deg2rad(15.))or self.force(name,self.tool_actor)<=.001)
        self.stage('edge-source-front-edge-tip-offload')
        receipt=native_rotate(self.c,self.side,_axis_rotation(np.cross([0,0,1.],forward),np.deg2rad(50.)),pivot_task=pivot,guard=self.guard,done=target_contact,max_angular_speed=.25,max_angular_acceleration=.45)
        # Stop tipping as soon as the target physically takes load. Retreat
        # horizontally opposite the inclined face normal: this lowers its
        # plane away from cargo, unlike the earlier flat retreat that dragged it.
        if not unloaded()and self.force(name,support)>.001:
            normal=self.frame(self.work)[1]@_unit(self.tool['support_normal_local']);back=-normal.copy();back[2]=0.;back=_unit(back)
            self.stage('edge-source-inclined-horizontal-retreat')
            self.a.move_smooth({self.side:self.tip(self.side)+back*.045},guard=self.guard,done=unloaded,tolerance=.002,max_speed=.04,max_acceleration=.15)
        self.wait(4)
        with(self.a.out/'edge-native-gravity-offload.private.jsonl').open('a')as stream:stream.write(json.dumps(dict(cargo=name,support=support,actual_edge_pivot_task=pivot.tolist(),actual_release_height_above_support_m=release_height,native_orientation_receipt=receipt,actual_target_support_force_n=self.force(name,support),actual_tool_cargo_force_n=self.force(name,self.tool_actor),actual_unloaded=unloaded(),source_score_modified=False))+'\n')
        if not unloaded():raise RuntimeError('Gravity offload lacks real target support and complete blade separation')
        self.stage('edge-source-offload-source-checkpoint');self.wait(4)
        with(self.a.out/'edge-native-source-checkpoints.private.jsonl').open('a')as stream:stream.write(json.dumps(dict(stage=self.a.stage,source_physics_result=self.c.evaluator.result(),author_goal_or_score_modified=False))+'\n')
    def global_station(self,work_task=None):
        self.stage('edge-source-global-loading-station')
        from .author_mplib_planner import capture_scene,plan_snapshot,_rotation,_quat
        import os
        from pathlib import Path
        state,_=self.snapshot();actual_tool=np.eye(4);actual_tool[:3,:3]=state[self.tool_actor]['mat'];actual_tool[:3,3]=state[self.tool_actor]['pos'];actual_tcp=np.eye(4);robot=self.a.scene.robots[self.side]
        actual_tcp[:3,:3]=self.a.scene.layout.task_rotation.T@_rotation(robot.data.root_quat_w[0].cpu().tolist())@_rotation(self.c.pose(self.side)[1][0].cpu().tolist());actual_tcp[:3,3]=self.tip(self.side)
        target_R=_push_rotation(self.tool['support_normal_local'],self.s['edge_outward_normal_local'],[-1,0,0])
        goal,tool_goal=tool_station_tcp_goal(actual_tool,actual_tcp,self.tool['working_local'],[-.035,-.015,1.025]if work_task is None else work_task,target_R)
        request=dict(position=goal[:3,3].tolist(),quaternion=_quat(goal[:3,:3]).tolist())
        snapshot=capture_scene(self.a.scene,self.c,self.side,request);(self.a.out/'edge-source-station-scene.private.json').write_text(json.dumps(snapshot,indent=2)+'\n')
        profile=json.loads(Path(os.path.expandvars(snapshot['profile'])).read_text());result=plan_snapshot(snapshot,profile)
        (self.a.out/'edge-source-station-plan.private.json').write_text(json.dumps(dict(actual_tool=actual_tool.tolist(),actual_tcp=actual_tcp.tolist(),source_tool_working_local=self.tool['working_local'],goal_tool=tool_goal.tolist(),goal_tcp=goal.tolist(),plan=result),indent=2)+'\n')
        if result.get('verified')is not True:raise RuntimeError('Fullworld source loading station refused: '+str(result.get('diagnostics',{}).get('error',result.get('status'))))
        other_robot=self.a.scene.robots[self.other];arm=self.c.ids[self.other][0];q=other_robot.data.joint_pos[:,arm].clone();overrides=self.c._author_joint_override;previous=overrides.get(self.other);overrides[self.other]=(q,q*0.)
        try:self.a.execute_joint_path(self.side,result,guard=self.guard)
        finally:
            if previous is None:overrides.pop(self.other,None)
            else:overrides[self.other]=previous
        self.guard();actual=self.snapshot()[0][self.tool_actor]
        if (actual['mat']@_unit(self.tool['support_normal_local']))[2]<.98:raise RuntimeError('Measured source loading station blade is not upward')
    def run(self):
        if self.s.get('auxiliary_loading_hand_allowed')is not True:raise RuntimeError('Original source does not authorize auxiliary loading hand')
        self.tool_actor=self.s['tools']['main']['actor'];self.side=self.s['tools']['main'].get('hand','right');self.other='left'if self.side=='right'else'right';self.cargo=self.s['groups']['active'][0]
        self.contacts=getattr(self.a.scene,'_source_scoop_contacts',None)
        if self.contacts is None:raise RuntimeError('Native22link contact views must be initialized before reset')
        self.validate_initial_source_world()
        self.tool,self.grip,_=self.tool();self.holding=True;self.loading=False;self.carrying=False;self.cargo_carrying=False;self.edge_phase=False
        self.geometry=NativeEdgeGeometry(self.a);self.work=dict(actor=self.tool_actor,local=self.tool['working_local']);self.c.tick_hooks.append(self.tick)
        try:
            for i,name in enumerate(self.s['groups']['active']):
                self.global_station();self.transfer(name,i)
        finally:self.restore_loading_hold();self.c.tick_hooks.remove(self.tick)


def solve_source_edge_load(author):
    if author.scene.spec['id']not in('E28','E46'):raise ValueError('Source auxiliary spatula loading accepts E28/E46 only')
    policy=SourceEdgeLoadAuthor(author);policy.run();(author.out/'source-edge-load-operations.private.json').write_text(json.dumps(policy.operations,indent=2)+'\n')
