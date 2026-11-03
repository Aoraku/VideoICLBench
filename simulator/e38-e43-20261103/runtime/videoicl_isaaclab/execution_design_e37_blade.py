"""Read native cooked blade geometry against the unchanged source slot."""
import json
import numpy as np


def section_edges(parts):
    from scipy.spatial import ConvexHull
    result=[]
    for part in parts:
        points=np.asarray(part,float)
        if points.ndim!=2 or points.shape[1]!=3 or len(points)<4 or not np.isfinite(points).all():
            raise ValueError('Complete native cooked convex blade parts required')
        triangles=ConvexHull(points).simplices
        edges=np.unique(np.sort(np.concatenate([triangles[:,[0,1]],triangles[:,[1,2]],triangles[:,[2,0]]]),axis=1),axis=0)
        result.append((points,edges))
    return result


def predicted_section(parts,position,rotation,tip_local,head,frame,depth):
    """Rigid prediction only; the source physical/evaluator state is untouched."""
    position,rotation,tip_local,head,frame=map(lambda x:np.asarray(x,float),(position,rotation,tip_local,head,frame))
    tip=position+rotation@tip_local;axis=frame[:,2]
    shift=axis*(-float(depth)-float((tip-head)@axis))
    sections=[];lowest=float('inf')
    for points,edges in parts:
        local=((points@rotation.T+position+shift)-head)@frame
        lowest=min(lowest,float(local[:,2].min()))
        a,b=local[edges[:,0]],local[edges[:,1]];dz=b[:,2]-a[:,2]
        mask=(a[:,2]*b[:,2]<=0)&(abs(dz)>1e-15)
        if mask.any():sections.append(a[mask]+(-a[mask,2]/dz[mask])[:,None]*(b[mask]-a[mask]))
    if not sections:raise ValueError('Actual cooked blade has no material at the source head plane')
    section=np.concatenate(sections);low=section.min(0);high=section.max(0)
    return dict(lower=low.tolist(),upper=high.tolist(),center=((low+high)/2).tolist(),
        narrow_width_m=float(high[1]-low[1]),broad_width_m=float(high[0]-low[0]),
        minimum_material_z_below_head_m=lowest,semantic_tip_offset_head=(frame.T@(tip-head)).tolist(),
        predicted_insertion_depth_m=float(depth))


class Blade:
    def __init__(self,policy,entry,axis,head,depth):
        from .execution_design_branch_geometry import collision_parts_task
        self.p=policy;self.entry=entry;self.axis=np.asarray(axis,float)
        self.head=head;self.depth=float(depth);self.actor=entry['driver']['actor']
        collision_parts_task(policy,self.actor)
        self.local=[np.asarray(x,float)for x in policy.a._branch_collision_parts[self.actor]]
        self.parts=section_edges(self.local)
        source=next(o for o in policy.spec['objects']if o['id']==self.actor)
        self.source_sha=source['source_asset']['sha256']
        import omni.usd
        from pxr import Usd,UsdPhysics
        stage=omni.usd.get_context().get_stage();properties=[]
        for actor in(self.actor,entry['screw']):
            body=stage.GetPrimAtPath(policy.a.scene.root_path+'/Props/'+actor)
            for prim in Usd.PrimRange(body,Usd.TraverseInstanceProxies()):
                if prim.HasAPI(UsdPhysics.CollisionAPI):
                    values={name:(prim.GetAttribute(name).Get()if prim.GetAttribute(name)else None)for name in(
                        'physxCollision:contactOffset','physxCollision:restOffset',
                        'physxSDFMeshCollision:sdfResolution','physics:approximation')}
                    properties.append(dict(actor=actor,path=str(prim.GetPath()),attributes=values))
        audit=dict(read_only=True,actor=self.actor,source_sha256=self.source_sha,
            native_cooked_parts=[p.tolist()for p in self.local],
            actual_collision_representation=policy.a._branch_collision_parts_evidence[self.actor],
            original_socket_width_m=2*entry['socket_radius'],original_slot_depth_m=entry['socket_depth'],
            native_collision_attributes=properties)
        (policy.a.out/'E37-actual-cooked-blade.private.json').write_text(json.dumps(audit,indent=2)+'\n')
    def frame(self):
        state=self.p.snapshot()[0];screw=state[self.entry['screw']]
        z=np.asarray(screw['mat'])@np.asarray(self.entry['axis_local'],float);z/=np.linalg.norm(z)
        u=np.asarray(screw['mat'])@np.asarray(self.entry['radial_local'],float)
        u-=z*float(u@z);u/=np.linalg.norm(u)
        return np.column_stack((u,np.cross(z,u),z))
    def measurement(self):
        body=self.p.snapshot()[0][self.actor];frame=self.frame()
        value=predicted_section(self.parts,body['pos'],body['mat'],self.entry['driver']['tip_local'],
            self.head(),frame,self.depth)
        radius=float(self.entry['socket_radius']);depth=float(self.entry['socket_depth'])
        value.update(original_socket_radius_m=radius,
            narrow_fits=value['lower'][1]>=-radius and value['upper'][1]<=radius,
            floor_fits=value['minimum_material_z_below_head_m']>=-depth,
            narrow_total_clearance_m=2*radius-value['narrow_width_m'])
        return value
    def centering_translation(self):
        value=self.measurement();tip=np.asarray(self.p.point(dict(actor=self.actor,local=self.entry['driver']['tip_local'])))
        frame=self.frame();tip_local=frame.T@(tip-np.asarray(self.head()))
        # Centre only the actual narrow blade section; keep the declared tip
        # centred along the long slot direction and preserve its clear height.
        return -frame[:,1]*value['center'][1]-frame[:,0]*tip_local[0]

    def physical_groove_measurement(self):
        """Actual original rectangular groove, separate from native tip-circle grade."""
        tip=np.asarray(self.p.point(dict(actor=self.actor,local=self.entry['driver']['tip_local'])))
        offset=self.frame().T@(tip-np.asarray(self.head()))
        screw=self.p.objects[self.entry['screw']]
        cosine=float(self.p.c.evaluator.screw_measure(self.entry)['cos'])
        body=self.p.snapshot()[0][self.actor];rotation=np.asarray(body['mat'])
        material=np.concatenate(self.local)@rotation.T+np.asarray(body['pos'])
        minimum=float(((material-np.asarray(self.head()))@self.frame())[:,2].min())
        engaged=bool(-self.entry['socket_depth']<=minimum<0
            and abs(offset[0])<=screw['size'][0]
            and abs(offset[1])<=self.entry['socket_radius']and cosine>=.9)
        return dict(tip_in_actual_screw_slot_frame=offset.tolist(),
            actual_source_blade_minimum_z_m=minimum,semantic_tip_below_head=bool(offset[2]<0),
            original_slot_half_width_m=float(self.entry['socket_radius']),
            original_head_half_length_m=float(screw['size'][0]),
            original_slot_depth_m=float(self.entry['socket_depth']),axis_cos=cosine,
            physical_tip_inside_original_groove=engaged,physical_source_blade_engaged=engaged,
            native_circular_tip_grade_unchanged=True)
