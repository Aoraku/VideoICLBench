"""Private E42 blade-edge/same-destination contact policy; never score logic.

Only exact native blade-part/target-shape pairs are relaxed during search. Each
returned sample recomputes FK and conditionally restores/rejects those pairs.
No tool handle, robot link, hand, table or ground collision is authorized here.
"""
from __future__ import annotations
import numpy as np


def reviewed_source(objects, semantic, binding_sha256):
    objects = {o['id']:o for o in objects} if isinstance(objects,list) else objects
    tool=semantic['tools']['main'];name=tool['actor'];balls=list(semantic['groups']['balls'])
    return dict(binding_sha256=binding_sha256,tool_actor=name,balls=balls,mapping={n:semantic['mapping'][n]for n in balls},
                edge_segment=tool['edge_segment'],outward_local=semantic['edge_outward_normal_local'],
                blade_contour=semantic['tool_geometry_measurement']['upward_blade_vertices_local_m'],
                source_asset_sha256=objects[name]['source_asset']['sha256'],tool_size=objects[name]['size'],
                radius={n:float(max(objects[n]['size']))for n in balls},
                local_bounds_center={n:objects[n].get('local_bounds_center',[0,0,0])for n in balls})


def segment_geometry(point,a,b):
    d=b-a;raw=float((point-a)@d/(d@d));t=float(np.clip(raw,0,1));closest=a+t*d
    return float(np.linalg.norm(point-closest)),raw,closest


def edge_conditions(tool_world,center_world,radius,review):
    edge=np.asarray(review['edge_segment'],float);contour=np.asarray(review['blade_contour'],float)
    local=tool_world[:3,:3].T@(np.asarray(center_world)-tool_world[:3,3]);distance,t,closest=segment_geometry(local,*edge)
    side=min(segment_geometry(local,contour[0],contour[2])[0],segment_geometry(local,contour[1],contour[3])[0]);back=segment_geometry(local,contour[0],contour[1])[0]
    outward=np.asarray(review['outward_local'],float);outward/=np.linalg.norm(outward);front=float((local-edge.mean(0))@outward);threshold=float(radius+.003)
    reasons=[]
    if distance>threshold:reasons.append('outside source edge capsule')
    if not -1e-9<=t<=1+1e-9:reasons.append('outside edge segment interior')
    if front < -1e-9:reasons.append('behind source front edge plane')
    if side<=threshold or back<=threshold:reasons.append('side or back envelope also reachable')
    return dict(eligible=not reasons,source_edge_distance_m=distance,source_radius_plus_slack_m=threshold,
                source_edge_parameter=t,source_front_signed_m=front,side_distance_m=side,back_distance_m=back,
                reasons=reasons,ball_local=local.tolist())


class E42EdgeGroupPolicy:
    def __init__(self,planner,snapshot,profile,base,hand_world,diagnostics):
        from .author_mplib_planner import _matrix,_vertices
        config=profile.get('e42_edge_group');review=snapshot.get('e42_source_review')
        if not isinstance(config,dict)or config.get('enabled')is not True:raise ValueError('Private E42 edge-group policy not enabled')
        if snapshot['task']!='E42'or not isinstance(review,dict):raise ValueError('E42 reviewed source metadata required')
        if snapshot['allowed_contact_pairs']:raise ValueError('Cannot mix source edge-group policy and legacy actor-wide exceptions')
        if review['binding_sha256']!=snapshot['source_binding_sha256']or review['binding_sha256']!=config['expected_binding_sha256']:raise ValueError('E42 source binding identity mismatch')
        if review['source_asset_sha256']!=config['expected_tool_asset_sha256']or not np.allclose(review['tool_size'],config['expected_tool_half_size'],atol=1e-10,rtol=0):raise ValueError('E42 source tool scale/asset changed')
        self.tool=review['tool_actor'];self.balls=list(review['balls'])
        if len(self.balls)!=2 or len(set(review['mapping'][n]for n in self.balls))!=1:raise ValueError('Exactly two source balls with one destination required')
        if snapshot['attached_actors']!=[self.tool]or not snapshot['native_grasp'].get(self.tool):raise ValueError('Actual bilateral native tool grasp required')
        contact_set={frozenset(c)for c in snapshot['contacts']};self.table_witness={}
        shapes=snapshot['shapes'];self.centers={};self.radius=review['radius'];self.review=review;self.planner=planner;self.base=base
        tool_shapes=[s for s in shapes if s['actor']==self.tool];blade=[s for s in tool_shapes if s['source_prim'].endswith(config['blade_native_prim_suffix'])]
        if len(blade)!=1:raise ValueError('Exact reviewed native blade collision part required')
        if not all(np.allclose(v['pose_world'],blade[0]['pose_world'],atol=1e-9,rtol=0)for v in tool_shapes):raise ValueError('Source tool collision pieces are not one measured rigid body')
        edge=np.asarray(review['edge_segment']);vertices=np.asarray(blade[0]['vertices'])
        if max(float(np.linalg.norm(vertices-v,axis=1).min())for v in edge)>.001:raise ValueError('Reviewed source edge does not match native blade collision geometry')
        self.blade=blade[0]['name'];self.relative_tool=np.linalg.inv(hand_world)@np.asarray(blade[0]['pose_world']);self.link=planner.link_name_2_idx['panda_hand']
        self.pairs=[]
        table=next((s for s in shapes if s['source_prim']=='/World/Table'),None)
        if table is None:raise ValueError('Actual native table geometry required')
        top=float(_vertices(np.asarray(table['pose_world']),table['vertices'])[:,2].max())
        for ball in self.balls:
            parts=[s for s in shapes if s['actor']==ball]
            if not parts:raise ValueError('Missing source ball collider')
            pose=np.asarray(parts[0]['pose_world']);center=_vertices(pose,np.asarray([review['local_bounds_center'][ball]]))[0];self.centers[ball]=center
            table_contact=frozenset((ball,'table'))in contact_set
            hand_contact=any(frozenset((ball,f'{side}_finger{i}'))in contact_set for side in ('left','right')for i in (1,2))
            if not table_contact or abs(float(center[2]-self.radius[ball]-top))>=.012 or hand_contact:raise ValueError('Original native ball table support/no-hand witness missing')
            self.table_witness[ball]=dict(native_table_contact=True,height_error_m=float(center[2]-self.radius[ball]-top),direct_finger_contact=False,
                actual_force_values_available=bool(snapshot.get('native_contact_forces')),witness='Captured native Controller.snapshot contact matrix threshold; never a fabricated force')
            for part in parts:self.pairs.append((self.blade,part['name'],ball))
        self.native_start_conditions=self.conditions(np.asarray(blade[0]['pose_world']))
        self.data=dict(policy='E42 source blade-edge same-zone group',source_binding_sha256=review['binding_sha256'],
            blade_native_shape=self.blade,target_balls=self.balls,target_zone=review['mapping'][self.balls[0]],baseline_table_witness=self.table_witness,
            exact_candidate_pairs=[list(p[:2])for p in self.pairs],search_goal_qualified_pairs=[],sample_audit=[],permissions_cleared_after_verification=False,
            robot_or_handle_or_world_pairs_authorized=False,native_runtime_guards_required=True,dynamic_ball_motion_simulated=False)
        diagnostics['e42_edge_group']=self.data
        self._matrix=_matrix

    def conditions(self,tool_world):
        return {n:edge_conditions(tool_world,self.centers[n],self.radius[n],self.review)for n in self.balls}

    def tool_pose(self,q):
        pin=self.planner.pinocchio_model;pin.compute_forward_kinematics(q);pose=pin.get_link_pose(self.link)
        return self.base@self._matrix(pose.p,pose.q)@self.relative_tool

    def allow_search_goal(self,hand_goal_world):
        conditions=self.conditions(hand_goal_world@self.relative_tool);qualified=[]
        for a,b,ball in self.pairs:
            allow=bool(conditions[ball]['eligible']or self.native_start_conditions[ball]['eligible']);self.planner.acm.set_entry(a,b,allow)
            if allow:qualified.append([a,b])
        self.data['search_goal_qualified_pairs']=qualified;self.data['search_goal_geometry']=conditions;self.data['search_start_geometry']=self.native_start_conditions
        return conditions

    def apply_sample(self,q,index=None,fraction=None,record=True):
        conditions=self.conditions(self.tool_pose(q));allowed=[]
        for a,b,ball in self.pairs:
            allow=bool(conditions[ball]['eligible']);self.planner.acm.set_entry(a,b,allow)
            if allow:allowed.append([a,b])
        if record:self.data['sample_audit'].append(dict(seed=getattr(self,'seed',None),index=index,fraction=fraction,ball_geometry=conditions,allowed_exact_shape_pairs=allowed))
        return conditions

    def clear(self):
        for a,b,_ in self.pairs:self.planner.acm.set_entry(a,b,False)
        self.data['permissions_cleared_after_verification']=True
