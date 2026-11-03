"""Native USD collision compounds, PhysX bodies, robot pairs, and RTX cameras."""
from copy import deepcopy
import math, os
from pathlib import Path
from dataclasses import MISSING
import torch
import numpy as np
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade, PhysxSchema
import omni.usd
import isaaclab.sim as sim
from isaaclab.assets import Articulation, ArticulationCfg, RigidObject, RigidObjectCfg
from isaaclab.sensors import Camera, CameraCfg, ContactSensor, ContactSensorCfg
from isaaclab.utils import configclass
from isaaclab.utils.math import combine_frame_transforms
from . import style
from .embodiments import select, articulation
from .layout import Layout
from .rig import spawn_reference_rig, link_room_lights


def material(stage,path,rgb,roughness=.38,metallic=0):
    mat=UsdShade.Material.Define(stage,path)
    shader=UsdShade.Shader.Define(stage,path+'/Surface');shader.CreateIdAttr('UsdPreviewSurface')
    shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb[:3]))
    shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(roughness)
    shader.CreateInput('metallic',Sdf.ValueTypeNames.Float).Set(metallic)
    if len(rgb)>3:shader.CreateInput('opacity',Sdf.ValueTypeNames.Float).Set(float(rgb[3]))
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),'surface')
    return mat


def transparent_material(stage,path,rgb,opacity):
    """Explicit clear-plastic material; legacy PreviewSurface stays unchanged."""
    mat=UsdShade.Material.Define(stage,path)
    shader=UsdShade.Shader.Define(stage,path+'/Surface')
    shader.CreateImplementationSourceAttr(UsdShade.Tokens.sourceAsset)
    shader.SetSourceAsset('OmniPBR.mdl','mdl')
    shader.SetSourceAssetSubIdentifier('OmniPBR','mdl')
    shader.CreateInput('diffuse_color_constant',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb[:3]))
    shader.CreateInput('reflection_roughness_constant',Sdf.ValueTypeNames.Float).Set(.12)
    shader.CreateInput('enable_opacity',Sdf.ValueTypeNames.Bool).Set(True)
    shader.CreateInput('opacity_constant',Sdf.ValueTypeNames.Float).Set(opacity)
    shader.CreateInput('opacity_threshold',Sdf.ValueTypeNames.Float).Set(0.)
    for kind in ('Surface','Displacement','Volume'):
        getattr(mat,'Create'+kind+'Output')('mdl').ConnectToSource(shader.ConnectableAPI(),'out')
    return mat


def transform(prim,position=(0,0,0),quaternion=(1,0,0,0),scale=None):
    xf=UsdGeom.Xformable(prim)
    ops={op.GetOpName():op for op in xf.GetOrderedXformOps()}
    (ops.get('xformOp:translate') or xf.AddTranslateOp()).Set(Gf.Vec3d(*map(float,position)))
    orient=ops.get('xformOp:orient') or xf.AddOrientOp()
    quat=Gf.Quatd(float(quaternion[0]),Gf.Vec3d(*map(float,quaternion[1:]))) if orient.GetPrecision()==UsdGeom.XformOp.PrecisionDouble else Gf.Quatf(float(quaternion[0]),Gf.Vec3f(*map(float,quaternion[1:])))
    orient.Set(quat)
    if scale is not None:(ops.get('xformOp:scale') or xf.AddScaleOp()).Set(Gf.Vec3f(*map(float,scale)))


def enable_continuous_prop_contacts(root):
    """Keep task bodies awake so PhysX reports settled support forces.

    This changes the sleeping optimization, not gravity, collision geometry,
    friction or contact thresholds. Call only on task props/mechanisms; robot
    articulation settings remain those of the source embodiment.
    """
    for prim in Usd.PrimRange(root):
        if prim.HasAPI(UsdPhysics.RigidBodyAPI):
            PhysxSchema.PhysxRigidBodyAPI.Apply(prim).CreateSleepThresholdAttr(0.)
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            PhysxSchema.PhysxArticulationAPI.Apply(prim).CreateSleepThresholdAttr(0.)


def geometry(stage,path,g,mat,collide=True):
    if 'rgba' in g and g.get('literal_rgba'):
        color=list(style.linear(g['rgba'][:3]))+list(g['rgba'][3:])
        mat=material(stage,path+'_Material',color)
    kind=g['type'];size=g.get('size',[]);scale=None
    if kind=='box':
        shape=UsdGeom.Cube.Define(stage,path);shape.CreateSizeAttr(2);scale=size
    elif kind=='sphere':
        shape=UsdGeom.Sphere.Define(stage,path);shape.CreateRadiusAttr(size[0])
    elif kind=='cylinder':
        shape=UsdGeom.Cylinder.Define(stage,path);shape.CreateRadiusAttr(size[0]);shape.CreateHeightAttr(2*size[1]);shape.CreateAxisAttr('Z')
    elif kind=='mesh':
        shape=UsdGeom.Mesh.Define(stage,path);m=g['mesh_data'];v=m['vertices'];f=m['faces']
        shape.CreatePointsAttr([Gf.Vec3f(*v[i:i+3]) for i in range(0,len(v),3)])
        shape.CreateFaceVertexCountsAttr([3]*(len(f)//3));shape.CreateFaceVertexIndicesAttr(f)
        shape.CreateSubdivisionSchemeAttr('none');shape.CreateDoubleSidedAttr(True)
    else:raise ValueError('Unsupported collision shape: '+kind)
    prim=shape.GetPrim();transform(prim,g.get('pos',(0,0,0)),g.get('quat',(1,0,0,0)),scale)
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(mat)
    if collide:
        UsdPhysics.CollisionAPI.Apply(prim)
        api=PhysxSchema.PhysxCollisionAPI.Apply(prim);api.CreateContactOffsetAttr(.0008);api.CreateRestOffsetAttr(0)
        if kind=='mesh':UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr('convexHull')
    return prim


def mark(stage,path,xy,index,radius,z,mat,yaw=0.):
    points=style.marker_points(xy,index,radius,z,yaw)
    curve=UsdGeom.BasisCurves.Define(stage,path)
    curve.CreateTypeAttr('linear');curve.CreateWrapAttr('nonperiodic' if index==3 else 'periodic')
    curve.CreateCurveVertexCountsAttr([2,2] if index==3 else [len(points)]);curve.CreatePointsAttr(points)
    curve.CreateWidthsAttr([.002]);curve.SetWidthsInterpolation('constant')
    UsdShade.MaterialBindingAPI.Apply(curve.GetPrim()).Bind(mat)


def spawn_prop(prim_path,cfg,translation=None,orientation=None,**kwargs):
    stage=omni.usd.get_context().get_stage();obj=cfg.recipe
    if obj.get('mechanical_asset'):
        from .mechanical_asset_adapters import spawn_mechanical_asset
        if obj['mechanical_asset'].get('kind')!='static_mesh':
            raise ValueError('Articulations must use the mechanisms section')
        record=spawn_mechanical_asset(stage,prim_path,obj['mechanical_asset'],translation or (0,0,0),orientation or (1,0,0,0))
        root=record['root']
        if 'e17_stand_geometry' in obj:
            from .execution_design_e17_stand import apply_to_usd
            apply_to_usd(root,obj)
        dynamic=obj.get('dynamic_mechanical_asset',False)
        if type(dynamic) is not bool:
            raise ValueError('dynamic_mechanical_asset must be an explicit boolean')
        if dynamic and (obj.get('role')!='movable' or obj['mechanical_asset'].get('joint_count')!=0):
            raise ValueError('Dynamic mechanical prop requires a movable joint-free rigid asset')
        UsdPhysics.RigidBodyAPI.Apply(root).CreateKinematicEnabledAttr(not dynamic)
        rigid=PhysxSchema.PhysxRigidBodyAPI.Apply(root)
        rigid.CreateDisableGravityAttr(not dynamic)
        if dynamic:
            rigid.CreateSolverPositionIterationCountAttr(16)
            rigid.CreateSolverVelocityIterationCountAttr(4)
            rigid.CreateEnableCCDAttr(True)
            rigid.CreateMaxDepenetrationVelocityAttr(1.)
            physical=UsdShade.Material.Define(stage,prim_path+'/DynamicFriction')
            friction=UsdPhysics.MaterialAPI.Apply(physical.GetPrim())
            friction.CreateStaticFrictionAttr(1.1)
            friction.CreateDynamicFrictionAttr(.9)
            friction.CreateRestitutionAttr(.02)
        UsdPhysics.MassAPI.Apply(root).CreateMassAttr(float(obj.get('mass',.5)))
        PhysxSchema.PhysxContactReportAPI.Apply(root).CreateThresholdAttr(0.)
        for part in Usd.PrimRange(root):
            if part.HasAPI(UsdPhysics.CollisionAPI):
                if dynamic and part.IsA(UsdGeom.Mesh):
                    # Preserve separate source components (two shelves and
                    # columns). A single hull would fill the access opening;
                    # dynamic triangle meshes cannot carry a movable stand.
                    UsdPhysics.MeshCollisionAPI.Apply(part).CreateApproximationAttr('convexHull')
                if dynamic:
                    UsdShade.MaterialBindingAPI.Apply(part).Bind(physical,UsdShade.Tokens.strongerThanDescendants,'physics')
                collision=PhysxSchema.PhysxCollisionAPI.Apply(part)
                collision.CreateContactOffsetAttr(float(obj.get('contact_offset',.0005)))
                collision.CreateRestOffsetAttr(float(obj.get('rest_offset',0.)))
        if obj.get('recolor'):
            mat=material(stage,prim_path+'/Recolor',obj['rgba'],float(obj.get('roughness',.8)))
            for part in Usd.PrimRange(root):
                if part.IsA(UsdGeom.Mesh):UsdShade.MaterialBindingAPI.Apply(part).Bind(mat,UsdShade.Tokens.strongerThanDescendants)
        enable_continuous_prop_contacts(root)
        return root
    if obj.get('source_asset'):
        from .source_assets import spawn_source_asset
        return spawn_source_asset(stage,prim_path,obj,translation or (0,0,0),orientation or (1,0,0,0))
    root=UsdGeom.Xform.Define(stage,prim_path).GetPrim()
    transform(root,translation or (0,0,0),orientation or (1,0,0,0))
    color=style.linear(obj['rgba'][:3]) if obj.get('color_mode')=='literal' else style.color(obj['rgba'])
    if 'opacity' in obj:
        opacity=float(obj['opacity'])
        if not 0 <= opacity <= 1:raise ValueError('Opacity must lie in [0, 1]')
        color=list(color[:3])+[opacity]
    mat=(transparent_material(stage,prim_path+'/Material',color,opacity) if 'opacity' in obj
         else material(stage,prim_path+'/Material',color))
    physical=UsdShade.Material.Define(stage,prim_path+'/Friction')
    api=UsdPhysics.MaterialAPI.Apply(physical.GetPrim())
    api.CreateStaticFrictionAttr(1.1);api.CreateDynamicFrictionAttr(.9);api.CreateRestitutionAttr(.02)
    for i,g in enumerate(obj['collision_shapes']):
        p=geometry(stage,prim_path+f'/shape_{i}',g,mat)
        UsdShade.MaterialBindingAPI(p).Bind(physical,UsdShade.Tokens.weakerThanDescendants,'physics')
    for i,g in enumerate(obj.get('visual_shapes',[])):
        geometry(stage,prim_path+f'/visual_{i}',g,mat,False)
    UsdPhysics.RigidBodyAPI.Apply(root)
    PhysxSchema.PhysxContactReportAPI.Apply(root).CreateThresholdAttr(0.)
    UsdPhysics.MassAPI.Apply(root).CreateDensityAttr(float(obj.get('density',300)))
    if 'physical_mass_kg' in obj:
        mass=obj['physical_mass_kg']
        if type(mass) not in (int,float) or not math.isfinite(mass) or mass<=0:
            raise ValueError('physical_mass_kg must be finite and positive')
        UsdPhysics.MassAPI.Apply(root).CreateMassAttr(float(mass))
    rigid=PhysxSchema.PhysxRigidBodyAPI.Apply(root)
    rigid.CreateSolverPositionIterationCountAttr(16);rigid.CreateSolverVelocityIterationCountAttr(4)
    rigid.CreateEnableCCDAttr(True);rigid.CreateMaxDepenetrationVelocityAttr(1.)
    if obj.get('disable_gravity'):rigid.CreateDisableGravityAttr(True)
    enable_continuous_prop_contacts(root)
    if 'marker' in obj:
        z=-obj['size'][2]+.009 if obj['kind']=='post' else obj['size'][2]+.002
        mark(stage,prim_path+'/IdentityMark',(0,-obj['size'][1]+.016),obj['marker'],.012,z,
            material(stage,prim_path+'/Ink',style.MARKER))
    if obj['id'].startswith('catch'):
        mark(stage,prim_path+'/IdentityMark',(0,-obj['size'][1]+.012),int(obj['id'][-1]),.009,obj['size'][2]+.002,
            material(stage,prim_path+'/Ink',style.MARKER))
    return root


@configclass
class PropCfg(sim.SpawnerCfg):
    func=spawn_prop
    recipe:dict=MISSING


class TabletopScene:
    def __init__(self,spec,camera_resolution=None,embodiment=None,*,root_path='/World',origin=(0.,0.,0.),include_overview=None,light_isolation=False):
        """Build one room; namespacing and translation are opt-in.

        The namespace root has no transform. Dynamic PhysX assets receive
        world-space initial poses, while static rig geometry uses a translated
        child Xform. Task recipes and evaluator coordinates remain local.
        """
        root=Sdf.Path(root_path)
        if not root.IsAbsolutePath() or not root.IsPrimPath() or root_path=='/':
            raise ValueError('root_path must be an absolute USD prim path')
        self.root_path=str(root)
        if include_overview is not None and type(include_overview) is not bool:
            raise ValueError('include_overview must be an explicit boolean or None')
        if type(light_isolation) is not bool:
            raise ValueError('light_isolation must be boolean')
        self.origin=np.asarray(origin,dtype=float)
        if self.origin.shape!=(3,) or not np.isfinite(self.origin).all():
            raise ValueError('origin must contain three finite coordinates')
        self.rig_root=self.root_path if self.root_path=='/World' and not self.origin.any() else self.root_path+'/Rig'
        self.spec=deepcopy(spec);self.objects={};self.robots={};self.cameras={};self.contacts={};self.mechanisms={};self.passive_efforts={}
        self.embodiment=select(spec['id'],embodiment)
        self.spec['embodiment']=self.embodiment.name
        self.layout=Layout(self.embodiment.config['layout'])
        self.layout.task_translation=self.layout.task_translation+self.origin
        self.spec['layout_profile']=self.layout.name
        self.spec['camera_profile']=self.embodiment.config['cameras']['profile']
        if spec.get('head_view'):self.spec['camera_profile']+='+'+spec['head_view']['profile']
        self.spec['embodiment_config_sha256']=self.embodiment.config_hash
        self.task_to_world=self.layout.task_to_world;self.world_to_task=self.layout.world_to_task
        stage=omni.usd.get_context().get_stage();UsdGeom.Xform.Define(stage,self.root_path)
        if self.rig_root!=self.root_path:
            rig=UsdGeom.Xform.Define(stage,self.rig_root).GetPrim()
            transform(rig,self.origin)
        spawn_reference_rig(stage,self.embodiment,geometry,material,transform,root_path=self.rig_root)
        if 'table_visual' in spec:
            # R/E pairing changes appearance only. Do not bind a new physics
            # material: preserve the actual table's contact coefficients.
            surface=spec['table_visual'];color=np.asarray(surface['color'],float)
            roughness=float(surface['roughness'])
            if color.shape!=(3,) or not np.isfinite(color).all() or np.any(color<0) or np.any(color>1) or not math.isfinite(roughness) or not 0<=roughness<=1:
                raise ValueError('Invalid visual-only tabletop material')
            table_prim=stage.GetPrimAtPath(self.rig_root+'/Table')
            if not table_prim.IsValid():raise ValueError('Visual-only table requires native table geometry')
            table_mat=material(stage,self.rig_root+'/Materials/ExecutionTableVisual',color,roughness)
            UsdShade.MaterialBindingAPI.Apply(table_prim).Bind(table_mat,UsdShade.Tokens.strongerThanDescendants)
        if 'table_surface' in spec:
            surface=spec['table_surface']
            color=np.asarray(surface['color'],float)
            values=[surface[k] for k in ('roughness','static_friction','dynamic_friction','restitution')]
            if color.shape!=(3,) or not np.isfinite(color).all() or np.any(color<0) or np.any(color>1) or not all(math.isfinite(float(v)) and float(v)>=0 for v in values):
                raise ValueError('Invalid explicit tabletop material')
            table_prim=stage.GetPrimAtPath(self.rig_root+'/Table')
            if not table_prim.IsValid():raise ValueError('Explicit tabletop material requires native table geometry')
            table_mat=material(stage,self.rig_root+'/Materials/ExecutionTableSurface',color,float(surface['roughness']))
            UsdShade.MaterialBindingAPI.Apply(table_prim).Bind(table_mat,UsdShade.Tokens.strongerThanDescendants)
            table_physical=UsdShade.Material.Define(stage,self.rig_root+'/Materials/ExecutionTablePhysics')
            table_friction=UsdPhysics.MaterialAPI.Apply(table_physical.GetPrim())
            table_friction.CreateStaticFrictionAttr(float(surface['static_friction']))
            table_friction.CreateDynamicFrictionAttr(float(surface['dynamic_friction']))
            table_friction.CreateRestitutionAttr(float(surface['restitution']))
            UsdShade.MaterialBindingAPI.Apply(table_prim).Bind(table_physical,UsdShade.Tokens.strongerThanDescendants,'physics')
        from .execution_design_environment_v3 import apply_native_environment
        self.execution_environment_readback=apply_native_environment(stage,self.rig_root,spec,material)
        if self.execution_environment_readback is not None:
            self.spec['execution_environment_readback']=deepcopy(self.execution_environment_readback)
        self.room_light_links=link_room_lights(stage,self.root_path) if light_isolation else []
        frame=material(stage,self.root_path+'/Materials/Frame',style.FRAME,.3,.25)
        pad=material(stage,self.root_path+'/Materials/Pad',style.PAD,.7)
        ink=material(stage,self.root_path+'/Materials/Ink',style.MARKER,.5)
        # Recipes, zones, fixtures and private evaluator use one unchanged task
        # frame. Move the complete physical task into the reference rig.
        UsdGeom.Xform.Define(stage,self.root_path+'/Task')
        transform(stage.GetPrimAtPath(self.root_path+'/Task'),self.layout.task_translation,self.layout.task_quat)
        for i,z in enumerate(spec['zones']):
            if z.get('hidden'):
                continue
            zone_material=material(stage,f'{self.root_path}/Materials/Pad{i}',z['rgba'],.8) if 'rgba' in z else pad
            geometry(stage,f'{self.root_path}/Task/Pad{i}',dict(type='box',size=z['half_size']+[.0005],pos=z['xy']+[z.get('surface_z',.8)+.0005]),zone_material,False)
            if z.get('outline'):
                x,y=z['xy'];hx,hy=z['half_size'];edge=.0008;top=z.get('surface_z',.8)+.0012
                for k,(pos,size) in enumerate([([x-hx,y,top],[edge,hy,.0001]),([x+hx,y,top],[edge,hy,.0001]),
                                               ([x,y-hy,top],[hx,edge,.0001]),([x,y+hy,top],[hx,edge,.0001])]):
                    geometry(stage,f'{self.root_path}/Task/Pad{i}Edge{k}',dict(type='box',size=size,pos=pos),ink,False)
            if z.get('marker') is not None:mark(stage,f'{self.root_path}/Task/PadMark{i}',z['xy'],z['marker'],min(z['half_size'])*.7,z.get('surface_z',.8)+.002,ink,yaw=z.get('marker_yaw',0.))
            if 'digit' in z:
                digits={0:'abcdef',1:'bc',2:'abdeg',3:'abcdg',4:'bcfg',5:'acdfg',6:'acdefg',7:'abc',8:'abcdefg',9:'abcdfg'}
                if z['digit'] not in digits:raise ValueError('Paper digit must be 0 through 9')
                x,y=z['xy'];hx,hy=np.asarray(z['half_size'])*.65;top=z.get('surface_z',.8)+.0015
                segments={'a':([x+hx,y,top],[.001,hy,.0001]),'d':([x-hx,y,top],[.001,hy,.0001]),'g':([x,y,top],[.001,hy,.0001]),
                          'b':([x+hx/2,y-hy,top],[hx/2,.001,.0001]),'c':([x-hx/2,y-hy,top],[hx/2,.001,.0001]),
                          'e':([x-hx/2,y+hy,top],[hx/2,.001,.0001]),'f':([x+hx/2,y+hy,top],[hx/2,.001,.0001])}
                for segment in digits[z['digit']]:
                    pos,size=segments[segment]
                    geometry(stage,f'{self.root_path}/Task/Digit{i}{segment}',dict(type='box',size=size,pos=pos),ink,False)
        for i,f in enumerate(spec['fixtures']):
            geometry(stage,f'{self.root_path}/Task/fixture{i}',dict(f,pos=f['xy']+[f['z']]),frame)
            if f.get('source_fixture')=='e44-passive-folding-rails-v4':
                from .execution_design_e44_fixture import apply_native_material
                apply_native_material(stage,f'{self.root_path}/Task/fixture{i}',f)
        # Real robot USDs and their own joints/fingers; no proxy meshes or welds.
        profile=self.embodiment
        for side in ('left','right'):
            cfg=articulation(profile,side);cfg.prim_path=f'{self.root_path}/{side}_robot'
            cfg.init_state.pos=tuple(np.asarray(cfg.init_state.pos)+self.origin)
            self.robots[side]=Articulation(cfg)
        for obj in spec['objects']:
            bottom=obj.get('bottom',.805)
            if 'bottom' not in obj:
                bottom+=sum(.008 for other in spec['objects'] if other['id']!=obj['id'] and other['kind'] in ('bowl','tray','cup') and other['xy']==obj['xy'])
            half=obj['size'][0] if 'quaternion' in obj else obj['size'][2]
            q=obj.get('quaternion',[math.cos(obj['yaw']/2),0,0,math.sin(obj['yaw']/2)])
            cfg=RigidObjectCfg(prim_path=self.root_path+'/Props/'+obj['id'],spawn=PropCfg(recipe=obj),
                init_state=RigidObjectCfg.InitialStateCfg(pos=tuple(self.task_to_world(obj['xy']+[obj.get('center_z',bottom+half)])),rot=self.layout.world_quaternion(q)))
            self.objects[obj['id']]=RigidObject(cfg)
        if profile.config['physics'].get('engineering_thin_contact_offset_m') is not None:
            from .engineering_thin_contact_skin import apply_scene
            apply_scene(self)
        mechanism_links={}
        for mechanism in spec.get('mechanisms',[]):
            from .mechanical_asset_adapters import spawn_mechanical_asset
            name=mechanism['id'];record=mechanism['mechanical_asset']
            q=mechanism.get('quaternion',[math.cos(mechanism.get('yaw',0)/2),0,0,math.sin(mechanism.get('yaw',0)/2)])
            position=self.task_to_world(mechanism['position'])
            path=self.root_path+'/Mechanisms/'+name
            data=spawn_mechanical_asset(stage,path,record,tuple(position),self.layout.world_quaternion(q))
            if data['kind']!='articulation':
                raise ValueError('Static mesh fixtures belong to objects, not mechanisms')
            enable_continuous_prop_contacts(data['root'])
            for role,target in data['contact_prim_paths'].items():
                mechanism_links[name+'/'+role]=target
                PhysxSchema.PhysxContactReportAPI.Apply(stage.GetPrimAtPath(target)).CreateThresholdAttr(0.)
            # Some reviewed source mechanisms (for example the fixed
            # xylophone key bodies) intentionally have no movable DOF. Isaac
            # Lab's default ``.*`` joint initialization rejects an empty
            # joint list, so make the empty state explicit while retaining
            # all fixed source bodies for contact snapshots.
            moving_names=data.get('moving_joint_names', [])
            initial_positions={} if not moving_names else {'.*':0.}
            if 'initial_joint_positions' in mechanism:
                from .execution_design_inputs_v3 import initial_joint_positions
                initial_positions=initial_joint_positions(spec,mechanism,moving_names)
            init=ArticulationCfg.InitialStateCfg(pos=tuple(position),rot=self.layout.world_quaternion(q),
                joint_pos=initial_positions,
                joint_vel={} if not moving_names else {'.*': 0.})
            self.mechanisms[name]=Articulation(ArticulationCfg(prim_path=path,spawn=None,
                init_state=init,actuators={}))
            if record.get('passive_effort_model'):
                from .mechanical_asset_adapters import ElastoPlasticHinge
                model=record['passive_effort_model']
                if model.get('class')!='ElastoPlasticHinge':
                    raise ValueError('Unknown source passive material model: '+str(model.get('class')))
                parameters={k:float(model[k]) for k in ('stiffness_nm_per_rad','yield_moment_nm','damping_nm_s_per_rad')}
                self.passive_efforts[name]=dict(joint=model['joint'],model=ElastoPlasticHinge(**parameters))
        for i,j in enumerate(spec.get('joints',[])):
            path=f'{self.root_path}/Constraints/joint{i}'
            cls={'prismatic':UsdPhysics.PrismaticJoint,'revolute':UsdPhysics.RevoluteJoint,'fixed':UsdPhysics.FixedJoint}[j['type']]
            joint=cls.Define(stage,path)
            joint.CreateBody1Rel().SetTargets([Sdf.Path(self.root_path+'/Props/'+j['child'])])
            parent=j.get('parent')
            if parent:
                joint.CreateBody0Rel().SetTargets([Sdf.Path(self.root_path+'/Props/'+parent)])
                anchor=j.get('anchor0',[0,0,0]);rotation=(1,0,0,0)
            else:
                anchor=self.task_to_world(j['anchor0']);rotation=self.layout.task_quat
            joint.CreateLocalPos0Attr(Gf.Vec3f(*map(float,anchor)))
            joint.CreateLocalRot0Attr(Gf.Quatf(float(rotation[0]),Gf.Vec3f(*map(float,rotation[1:]))))
            joint.CreateLocalPos1Attr(Gf.Vec3f(*map(float,j.get('anchor1',[0,0,0]))))
            joint.CreateLocalRot1Attr(Gf.Quatf(1.))
            joint.CreateCollisionEnabledAttr(False)
            if j['type']!='fixed':
                joint.CreateAxisAttr(j.get('axis','X'))
                joint.CreateLowerLimitAttr(float(j['limits'][0]));joint.CreateUpperLimitAttr(float(j['limits'][1]))
                if 'passive_rail' in j:
                    from .execution_design_e43_rail import apply_usd
                    apply_usd(joint,spec,j,UsdPhysics)
                if 'spring' in j:
                    spring=j['spring'];drive=UsdPhysics.DriveAPI.Apply(joint.GetPrim(),'angular' if j['type']=='revolute' else 'linear')
                    drive.CreateTypeAttr('force');drive.CreateTargetPositionAttr(float(spring.get('target',0)))
                    drive.CreateStiffnessAttr(float(spring['stiffness']));drive.CreateDampingAttr(float(spring.get('damping',.1)))
                    drive.CreateMaxForceAttr(float(spring.get('max_force',10)))
        head=self.embodiment.config['cameras']['head']
        # Installed CameraCfg declares this field. configclass may move defaults
        # into dataclass factories, so hasattr(class, field) is not a capability
        # check: it can silently leave the sensor pose buffers uninitialized.
        camera_pose_kwargs={'update_latest_camera_pose':True}
        width,height=camera_resolution or (head['width'],head['height'])
        self.cameras['head']=Camera(CameraCfg(prim_path=self.root_path+'/HeadCamera',height=height,width=width,**camera_pose_kwargs,
            data_types=['rgb', 'distance_to_image_plane'] if os.environ.get('VIDEOICL_SENSOR_DEPTH') == '1' else ['rgb'],spawn=sim.PinholeCameraCfg(**dict(head['intrinsics'],clipping_range=tuple(head['intrinsics']['clipping_range'])))))
        if (self.embodiment.config.get('author_recording',{}).get('diagnostic_overview',True)
                if include_overview is None else include_overview):
            self.cameras['overview']=Camera(CameraCfg(prim_path=self.root_path+'/OverviewCamera',height=960,width=1280,**camera_pose_kwargs,
                data_types=['rgb'],spawn=sim.PinholeCameraCfg(focal_length=24,horizontal_aperture=32,clipping_range=(.02,20))))
        wrist=self.embodiment.config['cameras']['wrist']
        for side in ('left','right'):
            # Fabric does not reliably propagate a nested camera's transform
            # from this USD articulation's camera rigid body. Follow its actual
            # PhysX pose explicitly, preserving RoboDojo's exact local mount.
            self.cameras[side+'_wrist']=Camera(CameraCfg(prim_path=f'{self.root_path}/{side}_WristCamera',
                height=wrist['height'],width=wrist['width'],data_types=['rgb', 'distance_to_image_plane'] if os.environ.get('VIDEOICL_SENSOR_DEPTH') == '1' else ['rgb'],**camera_pose_kwargs,spawn=sim.PinholeCameraCfg(**dict(wrist['intrinsics'],clipping_range=tuple(wrist['intrinsics']['clipping_range']))),
                offset=CameraCfg.OffsetCfg(convention='opengl')))

        filters={'table':self.rig_root+'/Table',**{f'fixture{i}':f'{self.root_path}/Task/fixture{i}' for i in range(len(spec['fixtures']))},
            **{o['id']:self.root_path+'/Props/'+o['id'] for o in spec['objects']},
            **mechanism_links,
            **{f'{side}_finger{i}':f'{self.root_path}/{side}_robot/{name}' for side in ('left','right') for i,name in enumerate(profile.fingers,1)}}
        for name in self.objects:
            selected={k:v for k,v in filters.items() if k!=name}
            self.contacts[name]=(ContactSensor(ContactSensorCfg(prim_path=self.root_path+'/Props/'+name,
                filter_prim_paths_expr=list(selected.values()),history_length=0,update_period=0.)),list(selected))
        for name,path in mechanism_links.items():
            selected={k:v for k,v in filters.items() if k!=name}
            self.contacts[name]=(ContactSensor(ContactSensorCfg(prim_path=path,
                filter_prim_paths_expr=list(selected.values()),history_length=0,update_period=0.)),list(selected))

    def initialize_declared_mechanisms(self):
        from .execution_design_initialization import initialize_declared_mechanisms
        return initialize_declared_mechanisms(self)

    def initialize_cameras(self,device):
        head=self.embodiment.config['cameras']['head']
        if self.spec.get('head_view'):
            view=self.spec['head_view']
            self.cameras['head'].set_world_poses_from_view(
                torch.tensor([self.task_to_world(view['eye_task']).tolist()],device=device),
                torch.tensor([self.task_to_world(view['target_task']).tolist()],device=device))
        else:
            self.cameras['head'].set_world_poses(torch.tensor([(np.asarray(head['position'])+self.origin).tolist()],device=device),torch.tensor([head['rotation']],device=device),convention=head['convention'])
        # Additional maintainer-only view; the agent's fixed view is the exact
        # reference cam_head above, not this diagnostic camera.
        if 'overview' in self.cameras:
            self.cameras['overview'].set_world_poses_from_view(torch.tensor([(np.asarray([1.25,-1.18,1.95])+self.origin).tolist()],device=device),torch.tensor([(np.asarray([0,0,.85])+self.origin).tolist()],device=device))

    def rgb_camera_calibration(self, name):
        """Sensor calibration only, in the same room task frame as robot TCP.

        Called inside RGB readback after sensor update. No scene object state,
        depth buffers, segmentation or evaluator data is consulted.
        """
        from .layout import rotation_matrix
        camera = self.cameras[name]
        data = camera.data
        quaternion = np.asarray(data.quat_w_opengl[0].detach().cpu().tolist())
        position = data.pos_w[0].detach().cpu().numpy()
        intrinsics = data.intrinsic_matrices[0].detach().cpu().numpy()
        # Camera sensors may not have a populated pose on the initial render.
        # Never let an unavailable estimate poison the existing RGB response.
        # It stays explicitly unavailable until a real calibrated frame exists.
        invalid_fields = [field for field, value in
                          (('quat_w_opengl', quaternion), ('pos_w', position), ('intrinsic_matrices', intrinsics))
                          if not np.isfinite(value).all()]
        if np.isfinite(quaternion).all() and np.linalg.norm(quaternion)<1e-6:
            invalid_fields.append('zero_quaternion')
        if invalid_fields:
            return dict(available=False, reason='camera_calibration_not_ready', invalid_fields=invalid_fields)
        rotation = rotation_matrix(quaternion)
        task_from_camera = np.eye(4)
        task_from_camera[:3, :3] = self.layout.task_rotation.T @ rotation
        # layout.task_translation already includes this pool room's origin.
        task_from_camera[:3, 3] = self.world_to_task(position)
        world_from_camera = np.eye(4)
        world_from_camera[:3, :3] = rotation
        world_from_camera[:3, 3] = position
        world_from_task = np.eye(4)
        world_from_task[:3, :3] = self.layout.task_rotation
        world_from_task[:3, 3] = self.layout.task_translation
        optical_to_opengl = np.diag([1., -1., -1., 1.])
        rgb = data.output['rgb']
        return dict(available=True, K=intrinsics.tolist(),
                    T_task_from_camera=task_from_camera.tolist(),
                    T_world_from_camera=world_from_camera.tolist(),
                    T_task_from_camera_optical=(task_from_camera @ optical_to_opengl).tolist(),
                    T_world_from_camera_optical=(world_from_camera @ optical_to_opengl).tolist(),
                    T_world_from_task=world_from_task.tolist(),
                    optical_convention='opencv: +X right, +Y down, +Z forward',
                    pixel_convention='u=column, v=row, origin=top-left; K applies to native image pixels',
                    width=int(rgb.shape[2]), height=int(rgb.shape[1]),
                    convention='opengl', units='m', source='camera_calibration_and_robot_state')

    def sync_wrist_cameras(self):
        profile=self.embodiment
        for side,robot in self.robots.items():
            optical=profile.wrist_camera_pose(side)
            ids,_=robot.find_bodies(profile.camera_link);bid=ids[0]
            pos,quat=combine_frame_transforms(robot.data.body_pos_w[:,bid],robot.data.body_quat_w[:,bid],
                torch.tensor([optical['position']],device=robot.device,dtype=torch.float32),
                torch.tensor([optical['rotation']],device=robot.device))
            self.cameras[side+'_wrist'].set_world_poses(pos,quat,convention=optical['convention'])

    def apply_passive_efforts(self):
        """Apply source material torque from measured q/qd on every physics tick.

        Each scene owns fresh plastic state. No variant, requested angle, or
        evaluator state enters this constitutive material calculation.
        """
        for name,entry in self.passive_efforts.items():
            asset=self.mechanisms[name]
            if 'joint_id' not in entry:
                ids,names=asset.find_joints(entry['joint'],preserve_order=True)
                if len(ids)!=1 or names!=[entry['joint']]:
                    raise ValueError('Passive source joint must resolve exactly once: '+entry['joint'])
                entry['joint_id']=ids[0]
            index=entry['joint_id']
            q=float(asset.data.joint_pos[0,index]);qd=float(asset.data.joint_vel[0,index])
            effort=entry['model'].effort(q,qd)
            from .passive_effort_bridge import apply_native_passive_effort
            receipt=apply_native_passive_effort(asset,index,effort,array_module=torch)
            entry['native_effort_steps']=entry.get('native_effort_steps',0)+1
            entry['last_native_effort']=receipt

    def passive_material_state(self):
        return {name:dict(joint=entry['joint'],plastic_rest_angle_rad=entry['model'].plastic_rest_angle_rad,
                         native_effort_steps=entry.get('native_effort_steps',0),
                         last_native_effort=entry.get('last_native_effort'))
                for name,entry in self.passive_efforts.items()}

    def contact_diagnostics(self):
        """Native paths and force buffers for private contact-adapter audits."""
        stage=omni.usd.get_context().get_stage()
        def paths(value):
            if value is None:return None
            if isinstance(value,(list,tuple)):return [paths(item) for item in value]
            return str(value)
        def values(tensor):
            return None if tensor is None else tensor.detach().cpu().tolist()
        bodies={}
        for name,asset in {**self.objects,**self.mechanisms}.items():
            root_paths=list(getattr(asset.root_physx_view,'prim_paths',[]))
            rigid=[]
            for root_path in root_paths:
                for prim in Usd.PrimRange(stage.GetPrimAtPath(root_path)):
                    if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                        rigid.append(dict(path=str(prim.GetPath()),
                            sleep_threshold=PhysxSchema.PhysxRigidBodyAPI(prim).GetSleepThresholdAttr().Get()))
            bodies[name]=dict(root_physx_paths=paths(root_paths),rigid_bodies=rigid)
        sensors={}
        for name,(sensor,labels) in self.contacts.items():
            view=sensor.contact_physx_view
            sensors[name]=dict(configured_sensor_path=sensor.cfg.prim_path,
                filter_labels=list(labels),configured_filter_paths=list(sensor.cfg.filter_prim_paths_expr),
                body_physx_paths=paths(getattr(sensor.body_physx_view,'prim_paths',None)),
                sensor_paths=paths(getattr(view,'sensor_paths',None)),
                filter_paths=paths(getattr(view,'filter_paths',None)),
                net_forces_w=values(sensor.data.net_forces_w),
                force_matrix_w=values(sensor.data.force_matrix_w))
        return dict(bodies=bodies,sensors=sensors)

    def update_physics(self,dt):
        """Refresh every measured physical state without authoring camera USD."""
        for x in [*self.robots.values(),*self.objects.values(),*self.mechanisms.values(),*[v[0] for v in self.contacts.values()]]:x.update(dt)
        self._camera_elapsed_dt=getattr(self,'_camera_elapsed_dt',0.)+dt

    def prepare_render(self):
        """Follow the latest measured wrist poses before the renderer samples."""
        self.sync_wrist_cameras()

    def update_render_cameras(self):
        """Invalidate camera buffers using all physics time since last capture."""
        elapsed=getattr(self,'_camera_elapsed_dt',0.)
        for camera in self.cameras.values():camera.update(elapsed)
        self._camera_elapsed_dt=0.

    def update(self,dt):
        # Existing initialization, inspection and preview callers retain the
        # complete update. The controller can defer camera work until render.
        self.update_physics(dt)
        self.prepare_render()
        self.update_render_cameras()
