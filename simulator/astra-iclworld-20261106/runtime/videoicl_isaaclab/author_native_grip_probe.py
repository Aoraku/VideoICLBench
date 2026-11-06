"""Opt-in read-only PhysX normal/friction patch probe for the private author.

Uses the installed NVIDIA Tensor API's independent1024-element contact views.
Only referenced valid buffer rows are serialized, unchanged, with original
counts/start offsets; unused uninitialized capacity is not contact evidence.
No source material, shape, mass, joint command or collision filter is changed.
"""
from __future__ import annotations
import io,json,os,zipfile
from pathlib import Path
import numpy as np
from .author_mplib_planner import _matrix,_vertices


def cpu_copy(value):
    if hasattr(value,'detach'):value=value.detach().cpu().numpy()
    return np.array(value,copy=True)


def decode_patch(buffers,friction=False):
    expected=4 if friction else 6
    if len(buffers)!=expected:raise ValueError('Unexpected native patch tuple length')
    names=['force','point','counts','starts']if friction else['force','point','normal','separation','counts','starts']
    values={k:cpu_copy(v)for k,v in zip(names,buffers)}
    if values['counts'].shape!=(1,1)or values['starts'].shape!=(1,1):raise ValueError('Probe requires one exact sensor/filter pair')
    count=int(values['counts'][0,0]);start=int(values['starts'][0,0]);capacity=len(values['force'])
    if count<0 or(count and(start<0 or start+count>capacity)):raise ValueError('Native contact buffer range overflow')
    result=dict(counts=values['counts'],starts=values['starts'],buffer_capacity=np.array(capacity),valid_source_indices=np.arange(start,start+count,dtype=np.int64))
    for key in names[:-2]:
        result[key]=values[key][start:start+count].copy()if count else values[key][:0].copy()
        if not np.isfinite(result[key]).all():raise ValueError('Nonfinite actual contact data')
    return result


def patch_wrench(normal,friction,origin):
    # Tensor force/normal products and friction vectors act on the sensor
    # finger. The tool receives their negatives at the reported world points.
    force_n=np.asarray(normal['force']).reshape(-1,1)*normal['normal'];force_f=np.asarray(friction['force']).reshape(-1,3)
    on_tool_n=-force_n;on_tool_f=-force_f
    torque_n=np.cross(normal['point']-origin,on_tool_n).sum(0);torque_f=np.cross(friction['point']-origin,on_tool_f).sum(0)
    return dict(normal_force_on_tool=on_tool_n.sum(0),friction_force_on_tool=on_tool_f.sum(0),normal_torque_on_tool=torque_n,friction_torque_on_tool=torque_f)


def require_straight_handle_points(points,bounds):
    p=np.asarray(points,float)
    if not len(p)or not np.isfinite(p).all()or np.any(p[:,0]<bounds[0]-1e-6)or np.any(p[:,0]>bounds[1]+1e-6):
        raise RuntimeError('Actual finger contact left the reviewed original straight handle; blade/neck grasp forbidden')


class NativeGripPatchProbe:
    def __init__(self,author,sensors,side,tool,enabled):
        self.a=author;self.c=author.c;self.scene=author.scene;self.side=side;self.tool=tool;self.enabled=enabled;self.last_tick=None
        self.archive=None
        self.views={};self.body_views={}
        for body in('panda_leftfinger','panda_rightfinger'):
            sensor=sensors.sensors[(side,body)]
            self.views[body]=sensor._physics_sim_view.create_rigid_contact_view(f'/World/{side}_robot/{body}',filter_patterns=['/World/Props/'+tool],max_contact_data_count=1024)
            self.body_views[body]=sensor.body_physx_view
            if self.views[body].sensor_count!=1 or self.views[body].filter_count!=1:raise RuntimeError('Exact native finger/tool patch view not established')
        self.object=self.scene.objects[tool];view=self.object.root_physx_view
        self.mass=float(cpu_copy(view.get_masses()).reshape(-1)[0]);self.com=cpu_copy(view.get_coms())[0];self.inertia=cpu_copy(view.get_inertias())[0]
        import omni.usd
        from pxr import Usd,UsdPhysics,PhysxSchema
        stage=omni.usd.get_context().get_stage();gravity=[];collision=[]
        for prim in Usd.PrimRange(stage.GetPseudoRoot(),Usd.TraverseInstanceProxies()):
            if prim.IsA(UsdPhysics.Scene):
                cfg=UsdPhysics.Scene(prim);gravity.append(dict(path=str(prim.GetPath()),direction=list(cfg.GetGravityDirectionAttr().Get()),magnitude=float(cfg.GetGravityMagnitudeAttr().Get())))
            if f'/World/{side}_robot/panda_'in str(prim.GetPath())and'finger/'in str(prim.GetPath())and prim.HasAPI(UsdPhysics.CollisionAPI):
                api=PhysxSchema.PhysxCollisionAPI(prim);row=dict(path=str(prim.GetPath()),applied_schemas=prim.GetAppliedSchemas())
                for name,attr in [('torsional_patch_radius',api.GetTorsionalPatchRadiusAttr()),('min_torsional_patch_radius',api.GetMinTorsionalPatchRadiusAttr())]:
                    token='torsionalPatchRadius'if name=='torsional_patch_radius'else'minTorsionalPatchRadius'
                    field=attr.GetName()or next((v for v in PhysxSchema.PhysxCollisionAPI.GetSchemaAttributeNames()if v.rsplit(':',1)[-1]==token),token)
                    fallback=None;fallback_error=None
                    try:fallback=Usd.SchemaRegistry().FindAppliedAPIPrimDefinition('PhysxCollisionAPI').GetAttributeFallbackValue(field)
                    except Exception as exc:fallback_error=repr(exc)
                    row[name]=dict(runtime_get=attr.Get(),authored=attr.HasAuthoredValueOpinion(),registered_runtime_schema_fallback=fallback,fallback_read_error=fallback_error)
                collision.append(row)
        configured=getattr(self.c.sim.cfg,'physics_prim_path',None);active=[v for v in gravity if v['path']==configured]if configured else gravity
        if len(active)!=1:raise RuntimeError('One active native gravity scene required')
        if not np.isfinite(active[0]['magnitude'])or active[0]['magnitude']<=0:raise RuntimeError('Actual runtime gravity magnitude unavailable')
        direction=np.asarray(active[0]['direction']);self.gravity=direction/np.linalg.norm(direction)*active[0]['magnitude']
        materials={body:dict(material_properties=cpu_copy(v.get_material_properties()).tolist(),contact_offsets=cpu_copy(v.get_contact_offsets()).tolist(),rest_offsets=cpu_copy(v.get_rest_offsets()).tolist())for body,v in self.body_views.items()}
        metadata=dict(read_only=True,buffer_capacity_per_finger=1024,normal_force_sign='force times normal acts on sensor finger; tool receives negative',friction_force_sign='Tensor friction force acts on sensor finger; tool receives negative',
                      serialization='All referenced valid raw values unchanged plus original counts/starts/indices; unused uninitialized capacity omitted',
                      tool_mass_kg=self.mass,tool_com_body=self.com.tolist(),tool_inertia_native=self.inertia.tolist(),gravity_scene=gravity,active_gravity_scene=active[0],finger_shapes=collision,finger_actual_properties=materials,
                      tool_actual_material_properties=cpu_copy(view.get_material_properties()).tolist(),tool_contact_offsets=cpu_copy(view.get_contact_offsets()).tolist(),tool_rest_offsets=cpu_copy(view.get_rest_offsets()).tolist())
        (author.out/'E42-native-contact-properties.private.json').write_text(json.dumps(metadata,indent=2)+'\n')
        self.archive=zipfile.ZipFile(author.out/'E42-raw-patch-buffers.private.zip','w',compression=zipfile.ZIP_DEFLATED)

    def tick(self,controller,render):
        if not self.enabled()or self.last_tick==controller.physics_ticks:return
        self.last_tick=controller.physics_ticks;patches={};arrays={};centers=[];checks={};validation_errors=[]
        obj=self.object;root=_matrix(cpu_copy(obj.data.root_pos_w[0]),cpu_copy(obj.data.root_quat_w[0]));points_local={}
        for body,view in self.views.items():
            # NVIDIA reuses count/start storage between these methods. Copy
            # and decode normal data BEFORE querying friction data.
            normal=decode_patch(view.get_contact_data(controller.dt));friction=decode_patch(view.get_friction_data(controller.dt),True)
            patches[body]=(normal,friction)
            for group,data in [('normal',normal),('friction',friction)]:
                for key,value in data.items():arrays[body+'_'+group+'_'+key]=value
            weights=normal['force'].reshape(-1);total=float(weights.sum())
            if total>0:centers.append((normal['point']*weights[:,None]).sum(0)/total)
            aggregate=(normal['force'].reshape(-1,1)*normal['normal']).sum(0);matrix=cpu_copy(view.get_contact_force_matrix(controller.dt))[0,0]
            checks[body]=dict(normal_matrix_world=matrix.tolist(),normal_point_sum_world=aggregate.tolist(),normal_sign_alignment_error_n=float(np.linalg.norm(aggregate-matrix)),normal_point_count=len(weights),friction_patch_count=len(friction['force']))
            if np.linalg.norm(aggregate-matrix)>.001+.0001*np.linalg.norm(matrix):validation_errors.append('Actual patch force sign/sensor alignment failed: '+body)
            local=(np.asarray(normal['point'])-root[:3,3])@root[:3,:3]
            points_local[body]=local.tolist()
            if os.environ.get('VIC_E42_REQUIRE_SOURCE_HANDLE_CONTACTS')=='1':
                bounds=self.scene.spec['semantic']['near_com_handle_grasp_review']['straight_handle_contact_x_bounds_local']
                try:require_straight_handle_points(local,bounds)
                except RuntimeError as exc:validation_errors.append(body+': '+str(exc))
        data=io.BytesIO();np.savez(data,**arrays);entry=f'tick-{controller.physics_ticks:09d}.npz';self.archive.writestr(entry,data.getvalue())
        com_world=_vertices(root,self.com[:3][None])[0]
        robot=self.scene.robots[self.side];names=list(robot.body_names);p=cpu_copy(robot.data.body_pos_w[0]);jaw=p[names.index('panda_rightfinger')]-p[names.index('panda_leftfinger')];length=np.linalg.norm(jaw)
        jaw=jaw/length if length>1e-8 else None
        row=dict(physics_tick=controller.physics_ticks,stage=self.a.stage,raw_npz_entry=entry,probe_validation_errors=validation_errors,contact_checks=checks,actual_normal_contact_points_tool_local=points_local,tool_root_world=root.tolist(),tool_com_world=com_world.tolist(),actual_jaw_axis_world=None if jaw is None else jaw.tolist(),native_tool_velocity_world=cpu_copy(obj.data.root_vel_w[0]).tolist())
        if len(centers)==2 and jaw is not None:
            midpoint=np.mean(centers,axis=0);w=[patch_wrench(n,f,midpoint)for n,f in patches.values()];torque_g=np.cross(com_world-midpoint,self.mass*self.gravity)
            torque_n=sum((v['normal_torque_on_tool']for v in w),np.zeros(3));torque_f=sum((v['friction_torque_on_tool']for v in w),np.zeros(3))
            row.update(actual_contact_centers_world=[v.tolist()for v in centers],actual_contact_midpoint_world=midpoint.tolist(),gravity_torque_about_contact_midpoint_world_nm=torque_g.tolist(),
                       tool_com_minus_contact_midpoint_world_m=(com_world-midpoint).tolist(),
                       normal_torque_on_tool_world_nm=torque_n.tolist(),friction_torque_on_tool_world_nm=torque_f.tolist(),gravity_torque_jaw_nm=float(torque_g@jaw),normal_torque_jaw_nm=float(torque_n@jaw),friction_torque_jaw_nm=float(torque_f@jaw),
                       total_contact_force_on_tool_world_n=sum((v['normal_force_on_tool']+v['friction_force_on_tool']for v in w),np.zeros(3)).tolist())
        with(self.a.out/'E42-native-patch-wrench.private.jsonl').open('a')as stream:stream.write(json.dumps(row)+'\n')
        if validation_errors:raise RuntimeError('Native raw-contact validation failed: '+repr(validation_errors))

    def close(self):
        if self.archive is not None:self.archive.close()
