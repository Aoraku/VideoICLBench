"""Source-triangle table-skim scoop for E46; no auxiliary cargo grasp."""
from __future__ import annotations
import json,os
from pathlib import Path
import numpy as np
from .author_spatula_support_private import SourceSupportAuthor
from .realworld_tool_expert import _push_rotation,_axis_rotation,_unit

LINKS=[f'panda_link{i}'for i in range(8)]+['panda_hand','panda_leftfinger','panda_rightfinger']


def scoop_rotation(normal,outward,direction,degrees=5.):
    direction=_unit([direction[0],direction[1],0.]);flat=_push_rotation(normal,outward,direction)
    return _axis_rotation(np.cross([0,0,1.],direction),np.deg2rad(degrees))@flat,flat


def skim_height(vertices,edge,rotation,table_top,clearance=.0002):
    return float(table_top+clearance-((np.asarray(vertices)-edge)@rotation.T)[:,2].min())


class ScoopContacts:
    def __init__(self,scene):
        from isaaclab.sensors import ContactSensor,ContactSensorCfg
        self.cargo_actors=list(scene.spec['semantic']['groups']['cargo']);self.actors=self.cargo_actors+[scene.spec['semantic']['tools']['main']['actor'],'table'];self.sensors={}
        for side in('left','right'):
            for link in LINKS:
                self.sensors[(side,link)]=ContactSensor(ContactSensorCfg(prim_path=f'/World/{side}_robot/{link}',filter_prim_paths_expr=['/World/Table'if n=='table'else'/World/Props/'+n for n in self.actors],history_length=0,update_period=0.))
    def read(self,dt):
        import torch
        values=[];keys=[]
        for key,sensor in self.sensors.items():
            sensor.update(dt);m=sensor.data.force_matrix_w
            if m is None or m.shape[-2]!=len(self.actors):raise RuntimeError('Missing actual22link/cargo/tool native contact matrix')
            values.append(m.norm(dim=-1).amax(dim=1)[0]);keys.append(key)
        return {(*key,actor):float(value)for key,row in zip(keys,torch.stack(values).cpu().tolist())for actor,value in zip(self.actors,row)}


class SourceScoopAuthor(SourceSupportAuthor):
    def move(self,side,target,guard=None,follower=None,tolerance=.002):
        if self.a.stage.startswith('scoop-') and follower is None:
            low=any(token in self.a.stage for token in('skim','insert','low-offload','withdraw'))
            return self.a.move_smooth({side:np.asarray(target)},tolerance=tolerance,guard=guard,max_speed=.015 if low else .04,max_acceleration=.06 if low else .12)
        return super().move(side,target,guard,follower,tolerance)
    def move_point(self,side,ref,target,guard=None,follower=None,tolerance=.002):
        if not self.a.stage.startswith('scoop-source-insert-'):
            return super().move_point(side,ref,target,guard,follower,tolerance)
        # Intermediate insertion goals are feedback commands. All native force,
        # source geometry and grip guards still run on every physical tick.
        before=self.point(ref).copy();target=np.asarray(target);tcp=self.tip(side)+target-before
        partial=False
        try:self.move(side,tcp,guard,follower,tolerance)
        except RuntimeError as error:
            if not str(error).startswith('Continuous author waypoint unreachable at '+self.a.stage+';'):raise
            partial=True
        if guard:guard()
        after=self.point(ref).copy()
        with(self.a.out/'scoop-insert-feedback.private.jsonl').open('a')as stream:
            stream.write(json.dumps(dict(stage=self.a.stage,physics_tick=self.c.physics_ticks,partial_waypoint=partial,actual_edge_before=before.tolist(),actual_edge_after=after.tolist(),requested_edge=target.tolist(),actual_edge_progress_m=float(np.linalg.norm(after-before)),source_completion_claimed=False))+'\n')
        return dict(partial=partial,actual_edge=after)
    def force(self,a,b):
        value=self.c.contact_forces.get(frozenset((a,b)))
        if value is None or not np.isfinite(value)or value<0:raise RuntimeError('Missing real contact force '+a+'/'+b)
        return float(value)
    def blade_vertices(self):
        from .author_mplib_planner import capture_scene
        proofpath=Path(os.path.expandvars(self.a.scene.embodiment.config['author_recording']['scoop_geometry_file']));proof=json.loads(proofpath.read_text())
        obj=next(o for o in self.spec['objects']if o['id']==self.tool_actor)
        if obj['source_asset']['sha256']!=proof['source_sha256']or not np.allclose(obj['size'],[.13,.0554114236,.009435933],atol=1e-10):raise RuntimeError('Source original spatula9 geometry/scale required')
        snapshot=capture_scene(self.a.scene,self.c,self.side,self.tip(self.side).tolist())
        parts=[s for s in snapshot['shapes']if s['actor']==self.tool_actor];expected=proof['actual_source_shapes'];errors=[]
        for source in expected:
            suffix=source['path'].split('/')[-1];matches=[s for s in parts if s['source_prim'].endswith(suffix)]
            if len(matches)!=1:raise RuntimeError('Original native source collision piece missing '+suffix)
            a=np.asarray(source['vertices_tool_local_m']);b=np.asarray(matches[0]['vertices']);error=float(np.linalg.norm(a[:,None]-b[None,:],axis=-1).min(axis=1).max());errors.append(dict(piece=suffix,maximum_vertex_error_m=error))
            if error>=.001:raise RuntimeError('Actual/source tool collider readback differs>=1mm')
        table=next(s for s in snapshot['shapes']if s['source_prim']=='/World/Table');T=np.asarray(table['pose_world']);v=np.asarray(table['vertices'])@T[:3,:3].T+T[:3,3];top=float(v[:,2].max());self.table_top=float(self.a.scene.world_to_task([0,0,top])[2])
        (self.a.out/'scoop-source-readback.private.json').write_text(json.dumps(dict(source_geometry_proof=str(proofpath),source_colliders=errors,actual_table_top_task=self.table_top,source_binding_sha256=self.spec['source_binding_sha256'],snapshot=snapshot),indent=2)+'\n')
        return np.concatenate([s['vertices_tool_local_m']for s in expected])
    def guard(self):
        state,_=self.snapshot();panel=self.contacts.read(0.)
        backstop=getattr(self,'backstop',False);allowed_backstop={(self.support_side,self.backstop_body)}if backstop else set()
        if any(v>.001 for(s,b,actor),v in panel.items()if actor in self.contacts.cargo_actors and (actor!=self.cargo or(s,b)not in allowed_backstop)):raise RuntimeError('Actual cargo contact outside source single-finger auxiliary backstop phase')
        if backstop and getattr(self,'backstop_tcp_z',None)is not None and self.tip(self.support_side)[2]>self.backstop_tcp_z+.001:raise RuntimeError('Auxiliary backstop hand raised while contacting source cargo')
        if backstop and self.a.scene.embodiment.config.get('author_recording',{}).get('scoop_flat_pad_backstop')is True and self.tip(self.support_side)[2]<self.a.floor_clear_tcp(self.support_side)-.0002:raise RuntimeError('Actual source auxiliary finger toe below measured table clearance')
        forbidden=[(s,b,v)for(s,b,actor),v in panel.items()if actor==self.tool_actor and v>.001 and(s,b)not in{(self.side,'panda_leftfinger'),(self.side,'panda_rightfinger')}]
        if forbidden:raise RuntimeError('Actual non-finger robot contact with scoop tool '+json.dumps(forbidden))
        if self.holding:
            self.require_held(self.grip,self.side)
            if min(self.force(self.tool_actor,self.side+'_finger1'),self.force(self.tool_actor,self.side+'_finger2'))<=.001:raise RuntimeError('Bilateral actual scoop grip lost')
        if any(any(state[n]['grasp'])for n in self.contacts.cargo_actors):raise RuntimeError('Scoop cargo must never be held by a hand')
        row=dict(stage=self.a.stage,physics_tick=self.c.physics_ticks,tool_held=self.holding,cargo_pos_task=state[self.cargo]['pos'].tolist(),tool_cargo_force_n=self.force(self.cargo,self.tool_actor),cargo_table_force_n=self.force(self.cargo,'table'),tool_table_force_n=self.force(self.tool_actor,'table'),robot_cargo_force_max_n=max(v for(s,b,actor),v in panel.items()if actor==self.cargo))
        row['source_auxiliary_backstop']=dict(active=backstop,allowed_link=None if not backstop else [self.support_side,self.backstop_body],native_robot_cargo_forces_n={'/'.join((side,body)):v for(side,body,actor),v in panel.items()if actor==self.cargo},auxiliary_hand_never_grasps=True,auxiliary_hand_transports=False)
        if self.skim_active:
            tool=state[self.tool_actor];points=self.vertices@tool['mat'].T+tool['pos'];minimum=float(points[:,2].min());row['actual_source_tool_lowest_z']=minimum
            if minimum<self.table_top-.0006:raise RuntimeError('Actual source blade penetrated table geometry beyond.6mm bound')
            if row['tool_table_force_n']>5.:raise RuntimeError('Bounded source scoop table load exceeded5N')
            if self.tip(self.side)[2]<self.a.floor_clear_tcp(self.side)-.0004:raise RuntimeError('Actual source finger toe below safe table floor')
        if self.loaded:
            if row['tool_cargo_force_n']<=.001:raise RuntimeError('Real blade lost loaded cargo contact')
            if row['cargo_table_force_n']>.001:raise RuntimeError('Cargo still table-supported during claimed tool-only transport')
        if self.c.physics_ticks!=getattr(self,'logged_tick',None):
            with(self.a.out/'scoop-native-guard.private.jsonl').open('a')as stream:stream.write(json.dumps(row)+'\n')
            self.logged_tick=self.c.physics_ticks
        return row
    def tick(self,controller,render):
        self.contacts.read(controller.dt);self.guard()
    def place_source_backstop(self,direction):
        if not self.s.get('auxiliary_loading_hand_allowed',False):raise RuntimeError('Source task does not authorize auxiliary loading contact')
        from .author_mplib_planner import _rotation
        other='left'if self.side=='right'else'right';self.support_side=other;self.backstop_tcp_z=None
        self.stage('scoop-source-open-backstop-hand');self.act(other,'RELEASE')
        height=max(self.clearance,self.tip(other)[2]);self.move(other,[*self.tip(other)[:2],height],self.guard)
        state,_=self.snapshot();center=self.actual_center(state)
        flat_backstop=self.a.scene.embodiment.config.get('author_recording',{}).get('scoop_flat_pad_backstop')is True
        if not flat_backstop:self.move(other,[*center[:2],height],self.guard)
        self.a.align_gripper_axis(other,direction)
        if flat_backstop:
            from .author_orientation import panda_downward_grasp_delta,_axis_angle
            for _ in range(3):
                robot=self.a.scene.robots[other];ids=[robot.find_bodies(n)[0][0]for n in self.a.scene.embodiment.fingers]
                axis=self.a.scene.layout.task_rotation.T@(robot.data.body_pos_w[0,ids[0]]-robot.data.body_pos_w[0,ids[1]]).cpu().numpy()
                hand_R=self.a.scene.layout.task_rotation.T@_rotation(robot.data.root_quat_w[0].cpu().tolist())@_rotation(self.c.pose(other)[1][0].cpu().tolist())
                delta=panda_downward_grasp_delta(hand_R,axis,direction)
                if _axis_angle(delta)[1]<np.deg2rad(.5):break
                self.a.rotate_tcp_smooth(other,delta,guard=self.guard)
            else:raise RuntimeError('Actual auxiliary flat-pad hand frame did not converge')
        self.a.floor_clear_tcp(other);robot=self.a.scene.robots[other];parts=[]
        for bid,points in self.a._finger_collision_points[other]:
            R=self.a.scene.layout.task_rotation.T@_rotation(robot.data.body_quat_w[0,bid].cpu().tolist());p=self.a.scene.world_to_task(robot.data.body_pos_w[0,bid].cpu().numpy());vertices=np.asarray(points)@R.T+p
            band=vertices[vertices[:,2]<=vertices[:,2].min()+.004]
            if len(band)<2:raise RuntimeError('Original finite finger toe band unavailable')
            parts.append((str(robot.body_names[bid]),vertices,band))
        body,vertices,band=min(parts,key=lambda item:float(item[2].mean(axis=0)@direction));self.backstop_body=body
        if flat_backstop:
            hand_R=self.a.scene.layout.task_rotation.T@_rotation(robot.data.root_quat_w[0].cpu().tolist())@_rotation(self.c.pose(other)[1][0].cpu().tolist());origin=self.tip(other)-hand_R@np.array([0,0,.1034]);material=(vertices-origin)@hand_R
            valid=(material[:,2]>=.09456482)&(material[:,2]<=.10856621);candidate=np.flatnonzero(valid)
            if len(candidate)<3:raise RuntimeError('Actual original flat inner-pad material region unavailable')
            values=material[candidate,1];inner=values.min()if body=='panda_leftfinger'else values.max();candidate=candidate[np.abs(values-inner)<.0003];band=vertices[candidate]
            if len(band)<2:raise RuntimeError('Actual finite flat-pad source face unavailable')
        state,_=self.snapshot();center=self.actual_center(state);obj=next(o for o in self.spec['objects']if o['id']==self.cargo);half=np.asarray(obj['size']);extent=float(abs(state[self.cargo]['mat'].T@direction)@half);top=center[2]+float(abs(state[self.cargo]['mat'][2])@half);toe_goal=self.table_top+.0004 if flat_backstop else top-.0015
        lateral=np.cross([0,0,1.],direction);shift=direction*(float(center@direction)+extent+.003-float((band@direction).min()))+lateral*float((center-band.mean(axis=0))@lateral);shift[2]=toe_goal-min(float(item[1][:,2].min())for item in parts);target=self.tip(other)+shift
        if flat_backstop and float(band[:,2].min()+shift[2])>=top-.0003:raise RuntimeError('Real source flat pad cannot overlap thin cargo while keeping both toes above table')
        if toe_goal<self.table_top+(.0003 if flat_backstop else .003):raise RuntimeError('Backstop toe must remain above thin front blade/table')
        self.backstop=True;self.stage('scoop-source-backstop-approach');self.move(other,[*target[:2],height],self.guard);self.move(other,target,self.guard,tolerance=.0003 if flat_backstop else .0008)
        contacted=False
        for _ in range(6):
            self.guard()
            if self.force(self.cargo,other+'_finger1')>.001 or self.force(self.cargo,other+'_finger2')>.001:contacted=True;break
            self.move(other,self.tip(other)-direction*.001,self.guard,tolerance=.0005)
        if not contacted:raise RuntimeError('Source backstop did not make real upper-side cargo contact')
        self.backstop_tcp_z=float(self.tip(other)[2])
        (self.a.out/'scoop-source-backstop-geometry.private.json').write_text(json.dumps(dict(source_video_evidence='source_media/evidence/136.jpg times2.0-4.4s',allowed_source_loading_hand=True,side=other,actual_finger_body=body,finite_source_toe_band_task_before_move=band.tolist(),source_cargo_top_task=top,target_toe_height_task=toe_goal,actual_contact_tcp_task=self.tip(other).tolist(),closed_gripper=False,object_pose_written=False,source_flat_pad_backstop=flat_backstop,all_native_finger_minimum_target_z=toe_goal,actual_flat_pad_after_translation_task=(band+shift).tolist()if flat_backstop else None),indent=2)+'\n')
    def withdraw_source_backstop(self,direction):
        if not getattr(self,'backstop',False):return
        side=self.support_side;self.stage('scoop-source-backstop-horizontal-release');self.move(side,self.tip(side)+direction*.025,self.guard,tolerance=.001)
        if max(self.force(self.cargo,side+'_finger1'),self.force(self.cargo,side+'_finger2'))>.001:raise RuntimeError('Auxiliary source backstop contact did not release before transport')
        self.backstop=False;self.guard();self.move(side,self.tip(side)+[0,0,.06],self.guard)

    def actual_center(self,state):
        obj=next(o for o in self.spec['objects']if o['id']==self.cargo);value=state[self.cargo]
        return value['pos']+value['mat']@np.asarray(obj.get('local_bounds_center',[0,0,0]))
    def source_scoop(self,cargo=None,reuse_tool=False):
        self.cargo=cargo or self.s['groups']['active'][0];self.tool_actor=self.s['tools']['main']['actor'];self.side=self.s['tools']['main'].get('hand','right');self.grip=dict(actor=self.tool_actor,local=self.s['tools']['main']['grasp_local'],jaw_axis_local=self.s['tools']['main']['jaw_axis_local'])
        self.contacts=getattr(self.a.scene,'_source_scoop_contacts',None)
        if self.contacts is None:raise RuntimeError('Actual scoop contact views must be initialized before native reset')
        self.holding=False;self.loaded=False;self.skim_active=False;self.backstop=False;self.c.tick_hooks.append(self.tick)
        try:
            if reuse_tool:
                tool=self.s['tools']['main'];grip=self.grip;side=self.side;self.holding=True;self.guard()
            else:tool,grip,side=self.tool()
            self.holding=True;self.guard();self.vertices=self.blade_vertices();edge=np.mean(self.s['tools']['main']['edge_segment'],axis=0);edge_ref=dict(actor=self.tool_actor,local=edge);normal=tool['support_normal_local'];outward=self.s.get('edge_outward_normal_local',[1,0,0])
            state,_=self.snapshot();cargo_start=self.actual_center(state);toolpose=state[self.tool_actor];direction=toolpose['mat']@_unit(outward);direction[2]=0;direction=_unit(direction)
            R,flat=scoop_rotation(normal,outward,direction,5.);self.stage('scoop-real-pitch5');self.rotate_actor(self.tool_actor,side,R);self.guard()
            _,actual_R=self.frame(edge_ref);z=skim_height(self.vertices,edge,actual_R,self.table_top);state,_=self.snapshot();center=self.actual_center(state);obj=next(o for o in self.spec['objects']if o['id']==self.cargo);extent=float(abs(state[self.cargo]['mat'].T@direction)@np.asarray(obj['size']));entry=center-direction*(extent+.008);entry[2]=z
            self.stage('scoop-source-preapproach');self.move_point(side,edge_ref,entry+[0,0,.06],self.guard,tolerance=.001)
            self.stage('scoop-table-skim-entry');self.skim_active=True;self.move_point(side,edge_ref,entry,self.guard,tolerance=.0006)
            if self.a.scene.embodiment.config.get('author_recording',{}).get('scoop_source_auxiliary_backstop')is True:self.place_source_backstop(direction)
            total=0.;loaded_geometry=False;insert_history=[]
            for index in range(24):
                state,_=self.snapshot();pose=state[self.tool_actor];center=self.actual_center(state);local=pose['mat'].T@(center-pose['pos']);row=self.guard()
                if row['tool_cargo_force_n']>.001 and .065<=local[0]<=.100 and abs(local[1])<.025:loaded_geometry=True;break
                actual_edge=self.point(edge_ref).copy();insert_history.append(actual_edge)
                if len(insert_history)>=9 and float((insert_history[-1]-insert_history[-9])@direction)<.00025:raise RuntimeError('Real scoop insertion has no forward edge progress across8 feedback iterations')
                if self.backstop and self.a.scene.embodiment.config.get('author_recording',{}).get('scoop_flat_pad_backstop')is True:
                    far=float((center-actual_edge)@direction)+float(abs(state[self.cargo]['mat'].T@direction)@np.asarray(obj['size']))
                    if far<.012:
                        if center[2]-cargo_start[2]<.0005 or row['tool_cargo_force_n']<=.001:raise RuntimeError('Blade reached backstop corridor before actual partial cargo lift; do not collide with hand')
                        self.withdraw_source_backstop(direction)
                point=actual_edge+direction*.004;point[2]=skim_height(self.vertices,edge,pose['mat'],self.table_top);self.stage('scoop-source-insert-'+str(index));self.move_point(side,edge_ref,point,self.guard,tolerance=.0006);total+=.004
                if total>.085:break
            if not loaded_geometry:raise RuntimeError('Bounded real scoop did not put cargo over original blade face; side pushing is not accepted')
            self.withdraw_source_backstop(direction)
            self.stage('scoop-verify-real-supported-lift');self.skim_active=False;self.move_point(side,edge_ref,self.point(edge_ref)+[0,0,.020],self.guard,tolerance=.001);self.wait(2);state,_=self.snapshot();row=self.guard()
            pose=state[self.tool_actor];center=self.actual_center(state);local=pose['mat'].T@(center-pose['pos']);n=_unit(normal);world_n=pose['mat']@n
            half=np.asarray(obj['size']);extent=float(abs(state[self.cargo]['mat'].T@world_n)@half);gap=float(n@local-extent-tool['support_plane_offset'])
            (self.a.out/'scoop-real-lift-evidence.private.json').write_text(json.dumps(dict(actual_cargo_lift_m=float(center[2]-cargo_start[2]),actual_cargo_center_tool_local=local.tolist(),actual_source_plane_bottom_gap_m=gap,normal_world=world_n.tolist(),actual_forces=row,source_face_support_required=True),indent=2)+'\n')
            if row['tool_cargo_force_n']<=.001 or row['cargo_table_force_n']>.001 or center[2]-cargo_start[2]<.01 or not -.001<=gap<=.004:raise RuntimeError('Scoop failed true table-free native source-face-supported lift')
            self.loaded=True;self.stage('scoop-real-level-loaded');self.rotate_actor(self.tool_actor,side,flat);self.guard();work=dict(actor=self.tool_actor,local=tool['working_local']);dest=self.destination(self.cargo)
            self.stage('scoop-loaded-carry');height=max(dest[2]+.08,.92);self.move_point(side,work,[*self.point(work)[:2],height],self.guard);self.move_point(side,work,[*dest[:2],height],self.guard)
            self.stage('scoop-source-low-offload');self.loaded=False;self.move_point(side,work,dest+[0,0,.003],self.guard,tolerance=.001)
            self.stage('scoop-source-withdraw');direction=self.frame(work)[1]@_unit(tool['withdraw_local']);self.move_point(side,work,self.point(work)+direction*.10,self.guard,tolerance=.001);self.wait(3);self.move(side,self.tip(side)+[0,0,.05],self.guard);self.wait(4)
        finally:self.c.tick_hooks.remove(self.tick)


def solve_source_scoop(author):
    if author.scene.spec['id']not in('E28','E46'):raise ValueError('Independent true scoop onlyE28/E46')
    policy=SourceScoopAuthor(author)
    for index,cargo in enumerate(policy.s['groups']['active']):policy.source_scoop(cargo,reuse_tool=index>0)
    (author.out/'source-scoop-operations.private.json').write_text(json.dumps(policy.operations,indent=2)+'\n')
