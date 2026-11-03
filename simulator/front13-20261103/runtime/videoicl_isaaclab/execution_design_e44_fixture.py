"""Source-required passive E44 folding rails; fresh construction only."""
from copy import deepcopy
import hashlib,json
import numpy as np

SCHEMA='e44-passive-folding-rails-v4'
SOURCE_LINES=(65,82)

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def rails():
    vertices=[[0,-.006,0],[.014,-.006,0],[.014,-.006,.145],[0,.006,0],[.014,.006,0],[.014,.006,.145]]
    faces=[0,2,1,3,4,5,0,1,4,0,4,3,1,2,5,1,5,4,2,0,3,2,3,5]
    rails_list=[dict(type='mesh',mesh_data=dict(vertices=np.asarray(vertices).ravel().tolist(),faces=faces),
        xy=[.12,y],z=.8,rgba=[.46,.49,.52,1.],literal_rgba=True,
        source_fixture=SCHEMA,passive=True)for y in(-.075,.075)]
    # Overhead guide strips constrain only lift by ordinary collision. Their
    # 0.8mm initial gap leaves the1.2mm base free to slide in X and either Y.
    # Both Y ends remain open; there are no posts in the exit corridor.
    for y in(-.075,.075):
        lower=np.array([-.12,y-.006,.802]);upper=np.array([-.005,y+.006,.806])
        corners=np.array([[x,yy,z]for x in(lower[0],upper[0])for yy in(lower[1],upper[1])for z in(lower[2],upper[2])])
        from scipy.spatial import ConvexHull
        triangles=ConvexHull(corners).simplices
        rails_list.append(dict(type='mesh',mesh_data=dict(vertices=corners.ravel().tolist(),faces=triangles.ravel().tolist()),xy=[0.,0.],z=0.,rgba=[.35,.38,.41,1.],literal_rgba=True,source_fixture=SCHEMA,passive=True))
    for row in rails_list:row['engineering_guide_material']=dict(static_friction=.03,dynamic_friction=.03,restitution=0.,friction_combine_mode='min')
    return rails_list


def add_passive_folding_fixture(spec):
    if spec['id']!='E44':raise ValueError('E44-only passive fixture')
    if spec.get('fixtures'):raise ValueError('Unexpected existing E44 fixture; require explicit review')
    before=deepcopy({k:spec.get(k)for k in('objects','fixtures','mechanisms','semantic','goals')})
    fixed=rails();spec['fixtures']=fixed
    spec['semantic']['execution_design_fold_fixture']=dict(schema=SCHEMA,source_lines=list(SOURCE_LINES),
        source_requirement='纸板、折叠夹具、初始展开状态及目标夹角',
        fixed_geometry_sha256=digest(fixed),old_physical_geometry_sha256=digest(before),
        fixture_contact_ids=['fixture0','fixture1','fixture2','fixture3'],rail_contact_ids=['fixture0','fixture1'],base_guide_contact_ids=['fixture2','fixture3'],single_pusher=True,native_initial_verified=False,
        no_cardboard_constraint=True,no_actuation=True,no_target_angle_stop=True,
        geometry_revision='steep145mm-guide-with-open-sliding-base-clearance',native_clearance_pending=True,
        guide_material_approximation='low_friction_passive_or_roller_guide_mu003_min_v1')
    assert spec['mechanisms']==before['mechanisms']and spec['goals']==before['goals']and spec['objects']==before['objects']
    return dict(old_physical_geometry_sha256=digest(before),new_fixture_geometry_sha256=digest(fixed))

def nominal_final_clearance(interior_deg,hinge_x=.075):
    """Analytic design screen only; actual native motion remains mandatory."""
    angle=np.deg2rad(180-float(interior_deg));u=np.linspace(0,.1105,2001)
    x=hinge_x+u*np.cos(angle);z=.8006+u*np.sin(angle)
    over=(x>=.12)&(x<=.134)
    clearance=float(np.min(z[over]-(.8+(x[over]-.12)*(.145/.014)))-.0012)if over.any()else None
    return dict(interior_deg=float(interior_deg),over_rail_x=bool(over.any()),
        minimum_vertical_gap_m=clearance,base_to_rail_x_gap_m=.12-hinge_x,
        center_gripper_channel_width_m=.138,native_verified=False)

def verify_native_initial(p):
    """Read actual settled USD/PhysX evidence, never advance or change state."""
    from pxr import UsdGeom,UsdPhysics,Gf
    import omni.usd
    from .execution_design_thin_edge import mechanism_collision_points_task
    s=p.s['crease'];base=dict(mechanism=s['mechanism'],**s['expert']['base_press']);fold=dict(mechanism=s['mechanism'],**s['expert']['fold_grasp'])
    marker=p.s.get('execution_design_fold_fixture',{})
    if marker.get('schema')!=SCHEMA or p.c.steps!=0:raise ValueError('Fresh zero-action folding-fixture validation required')
    stage=omni.usd.get_context().get_stage();cache=UsdGeom.XformCache();actual=[]
    for i in range(len(marker['fixture_contact_ids'])):
        prim=stage.GetPrimAtPath(f'{p.a.scene.root_path}/Task/fixture{i}')
        if not prim or not prim.HasAPI(UsdPhysics.CollisionAPI)or prim.HasAPI(UsdPhysics.RigidBodyAPI):
            raise ValueError('Folding rail must be a passive static collision mesh')
        from pxr import UsdShade,PhysxSchema
        bound,_=UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial('physics')
        material_api=UsdPhysics.MaterialAPI(bound.GetPrim());combine=PhysxSchema.PhysxMaterialAPI(bound.GetPrim()).GetFrictionCombineModeAttr().Get()
        if abs(float(material_api.GetStaticFrictionAttr().Get())-.03)>1e-7 or abs(float(material_api.GetDynamicFrictionAttr().Get())-.03)>1e-7 or combine!='min':raise ValueError('Native guide material readback failed')
        points=UsdGeom.Mesh(prim).GetPointsAttr().Get();matrix=cache.GetLocalToWorldTransform(prim)
        actual.append(np.asarray([p.a.scene.world_to_task(np.asarray(matrix.Transform(Gf.Vec3d(*map(float,v))),float))for v in points]))
    paper=np.concatenate([mechanism_collision_points_task(p,ref)for ref in(base,fold)])
    _,contacts=p.snapshot();forbidden=[sorted(pair)for pair in contacts if any(n in pair for n in marker['fixture_contact_ids'])and any(n in pair for n in(base['contact_body'],fold['contact_body']))]
    rail_min=min(float(m[:,0].min())for m in actual[:2]);gap=rail_min-float(paper[:,0].max());guide_gap=min(float(m[:,2].min())for m in actual[2:])-float(paper[:,2].max())
    bmat=p.frame(base)[1];fmat=p.frame(fold)[1];angle=float(np.rad2deg(np.arccos(np.clip((bmat@np.array(s['base']['normal_local']))@(fmat@np.array(s['fold']['normal_local'])),-1,1))))
    row=dict(schema=SCHEMA,steps=p.c.steps,physics_ticks=p.c.physics_ticks,fixture_vertices_task=[m.tolist()for m in actual],
        actual_paper_vertices_sha256=digest(paper.tolist()),actual_initial_x_gap_m=gap,
        actual_initial_fold_deg=angle,actual_cardboard_fixture_contacts=forbidden,
        actual_base_table_support=p.contact(base['contact_body'],'table'),source_lines=list(SOURCE_LINES),
        passive_static_rails=True,body_or_joint_write_performed=False,actual_base_guide_initial_gap_m=guide_gap,open_y_exit=True)
    row['passed']=gap>.008 and guide_gap>.0005 and angle<.1 and not forbidden and row['actual_base_table_support']
    (p.a.out/'e44-fixture-initial.private.json').write_text(json.dumps(row,indent=2))
    if not row['passed']:raise RuntimeError('Native passive fixture initial separation/stability failed')
    return row


def apply_native_material(stage,path,fixture):
    """Explicit new guide material; paper, robots and all other fixtures unchanged."""
    from pxr import UsdPhysics,UsdShade,PhysxSchema
    expected=dict(static_friction=.03,dynamic_friction=.03,restitution=0.,friction_combine_mode='min')
    if fixture.get('source_fixture')!=SCHEMA or fixture.get('engineering_guide_material')!=expected:raise ValueError('Reviewed E44 guide material required')
    prim=stage.GetPrimAtPath(path);mat=UsdShade.Material.Define(stage,path+'/PassiveGuideMaterial');api=UsdPhysics.MaterialAPI.Apply(mat.GetPrim())
    api.CreateStaticFrictionAttr(.03);api.CreateDynamicFrictionAttr(.03);api.CreateRestitutionAttr(0.)
    PhysxSchema.PhysxMaterialAPI.Apply(mat.GetPrim()).CreateFrictionCombineModeAttr('min')
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(mat,UsdShade.Tokens.strongerThanDescendants,'physics')
    return mat
