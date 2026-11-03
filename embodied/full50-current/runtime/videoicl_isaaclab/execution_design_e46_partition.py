"""One E46 source-hull fidelity correction, preserving measured rigid dynamics."""
import copy,json
import numpy as np
from .execution_design_e46_partition_data import SOURCE_SHA,ARTIFACT_SHA,PARTS,NATIVE_BASELINE

def configure_spec(spec):
    if spec['id']!='E46':raise ValueError('E46 partition scope')
    obj=next(o for o in spec['objects']if o['id']=='spatula')
    if obj.get('source_asset',{}).get('sha256')!=SOURCE_SHA or not np.allclose(obj['size'],[.14,.03761496517,.01481387076],atol=1e-9,rtol=0):raise ValueError('Exact source E46 required')
    old=obj.get('reviewed_collision_settings')
    if old!=dict(source_sha256=SOURCE_SHA,approximation='convexHull',hull_vertex_limit=255,coordinate_factor=100.):raise ValueError('Exact previous source coordinate adapter required')
    obj['reviewed_collision_settings']=dict(source_sha256=SOURCE_SHA,approximation='sourceConvexPartition',artifact_sha256=ARTIFACT_SHA,preserve_native_mass_properties=copy.deepcopy(NATIVE_BASELINE['spatula']),native_mass_baseline_sha256=ARTIFACT_SHA)

def install(stage,root,obj,selected):
    from pxr import UsdGeom,UsdPhysics,PhysxSchema,Gf,Vt
    from scipy.spatial import ConvexHull
    if obj.get('reviewed_collision_settings',{}).get('artifact_sha256')!=ARTIFACT_SHA:raise ValueError('Pinned exact79 source partition required')
    for prim in selected:UsdPhysics.CollisionAPI(prim).CreateCollisionEnabledAttr(False)
    result=[]
    for i,raw in enumerate(PARTS):
        points=np.asarray(raw,float);hull=ConvexHull(points)
        mesh=UsdGeom.Mesh.Define(stage,str(root.GetPath())+'/SourceHullPiece%03d'%i)
        mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*map(float,p*100))for p in points]))
        mesh.CreateFaceVertexCountsAttr([3]*len(hull.simplices));mesh.CreateFaceVertexIndicesAttr(hull.simplices.ravel().tolist())
        mesh.CreateVisibilityAttr(UsdGeom.Tokens.invisible);UsdGeom.Xformable(mesh).AddScaleOp().Set(Gf.Vec3f(.01,.01,.01))
        UsdPhysics.CollisionAPI.Apply(mesh.GetPrim());UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim()).CreateApproximationAttr('convexHull')
        PhysxSchema.PhysxConvexHullCollisionAPI.Apply(mesh.GetPrim()).CreateHullVertexLimitAttr(128)
        result.append(mesh.GetPrim())
    return result,dict(reviewed_approximation='sourceConvexPartition',pieces=len(result),source_sha256=SOURCE_SHA,artifact_sha256=ARTIFACT_SHA,approx=False,fidelity_correction=True,source_visual_unchanged=True,source_convex_union_preserved=True,mass_properties_preserved=True)

def bind_mass(root,obj):
    from pxr import UsdPhysics,Gf
    from .layout import rotation_matrix
    r=NATIVE_BASELINE['spatula'];c=np.asarray(r['centres_of_mass'][0]);q=c[3:];rot=rotation_matrix([q[3],*q[:3]]);inertia=np.asarray(r['inertias_kg_m2'][0]).reshape(3,3);principal=rot.T@inertia@rot
    if np.max(abs(principal-np.diag(np.diag(principal))))>1e-10:raise ValueError('Pinned native inertia frame')
    api=UsdPhysics.MassAPI.Apply(root);api.CreateMassAttr(float(r['masses_kg'][0][0]));api.CreateCenterOfMassAttr(Gf.Vec3f(*map(float,c[:3])));api.CreateDiagonalInertiaAttr(Gf.Vec3f(*map(float,np.diag(principal))));api.CreatePrincipalAxesAttr(Gf.Quatf(float(q[3]),Gf.Vec3f(*map(float,q[:3]))))

def materialize(controller,recipe):
    from .engineering_checkpoint import _hash,PHYSICAL_KEYS,identity,reseal
    cp=copy.deepcopy(recipe['checkpoint']);digest=cp.pop('checkpoint_sha256')
    if _hash(cp)!=digest:raise ValueError('Original E46 checkpoint checksum')
    cp['checkpoint_sha256']=digest;old=recipe['source_scene'];new=controller.scene.spec
    if _hash({k:old.get(k)for k in PHYSICAL_KEYS})!=cp['identity']['physical_geometry_sha256']:raise ValueError('Original source physical hash')
    expected=copy.deepcopy(old);configure_spec(expected)
    if any(expected.get(k)!=new.get(k)for k in PHYSICAL_KEYS):raise ValueError('Partition altered other source inputs')
    current=identity(controller)
    if any(current.get(k)!=val for k,val in cp['identity'].items()if k!='physical_geometry_sha256'):raise ValueError('Partition changed identity/profile')
    actual={}
    for name,asset in controller.scene.objects.items():
        view=asset.root_physx_view;actual[name]={k:v.cpu().tolist()for k,v in [('masses_kg',view.get_masses()),('inertias_kg_m2',view.get_inertias()),('centres_of_mass',view.get_coms())]}
        for key,value in actual[name].items():
            if not np.allclose(value,NATIVE_BASELINE[name][key],rtol=1e-5,atol=1e-11):raise ValueError('Partition changed native dynamics '+name+'/'+key)
    old_id=cp['identity'];cp['identity']=current;cp['context']['e46_partition_migration']=dict(old_identity=old_id,new_identity=current,approx=False,fidelity_correction=True,pieces=79,artifact_sha256=ARTIFACT_SHA,native_mass_properties=actual)
    cp['limitations'].append('Explicit exact source convex partition collider fidelity correction; old PhysX caches not restored.')
    return reseal(cp)
