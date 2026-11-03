"""Exact extruded source triangles for E10 holes that native cooking closed.

Original source bytes, surface vertices, dimensions and scoring stay unchanged.
Each triangle of the original planar top is extruded into a six-vertex convex
prism. This partitions the existing material; it never fills or widens holes.
"""
import numpy as np

SOURCES={
 'fed57b9b0e69a5b8b98d75324ed6856c0cdb21ebc56c8f98cb372670255b61bb':202,
 'caae5e783af9afae7ee6c1933e42a1654d746635873c7a1bb221ea4554a70e7b':152,
}


def source_prisms(vertices,faces,source_sha256):
    if source_sha256 not in SOURCES:raise ValueError('Pinned E10 source identity required')
    vertices=np.asarray(vertices,float);faces=np.asarray(faces,int)
    if vertices.ndim!=2 or vertices.shape[1]!=3 or faces.ndim!=2 or faces.shape[1]!=3 or not np.isfinite(vertices).all():
        raise ValueError('Finite source triangles required')
    zmin,zmax=float(vertices[:,2].min()),float(vertices[:,2].max())
    if not np.allclose([zmin,zmax],[-.003,.003],atol=1e-9):raise ValueError('Original E10 source thickness required')
    triangles=vertices[faces];normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    top=np.all(abs(triangles[:,:,2]-zmax)<1e-9,axis=1)
    bottom=np.all(abs(triangles[:,:,2]-zmin)<1e-9,axis=1)
    if np.any(abs(normal[~(top|bottom),2])>1e-10):raise ValueError('Source side is not an exact vertical extrusion')
    if int(top.sum())!=SOURCES[source_sha256]:raise ValueError('Original E10 source top topology required')
    area=np.abs(normal[top,2]).sum()/2
    volume=abs(np.einsum('ij,ij->i',triangles[:,0],np.cross(triangles[:,1],triangles[:,2])).sum()/6)
    if not np.isclose(area*(zmax-zmin),volume,rtol=1e-5,atol=1e-12):raise ValueError('Source extrusion volume differs from closed source material')
    result=[]
    for tri in triangles[top]:
        tri=tri.copy();u,v=tri[1,:2]-tri[0,:2],tri[2,:2]-tri[0,:2]
        if u[0]*v[1]-u[1]*v[0]<0:tri=tri[[0,2,1]]
        lower=tri.copy();lower[:,2]=zmin
        result.append(np.vstack([tri,lower]))
    return result,dict(source_sha256=source_sha256,source_faces=len(faces),original_volume_m3=volume,
        prism_union_volume_m3=area*(zmax-zmin),prism_count=len(result),cook_coordinates="per_triangle_orthonormal_normalized",original_topology_and_holes_preserved=True)


def install(stage,obj,selected):
    from pxr import UsdGeom,UsdPhysics,Gf,Vt,PhysxSchema
    sha=obj['source_asset']['sha256']
    if obj.get('reviewed_e10_extruded_collision')!=sha:raise ValueError('Explicit E10 source collision review required')
    if len(selected)!=1 or not selected[0].IsA(UsdGeom.Mesh):raise ValueError('Reviewed single source collision mesh required')
    original=selected[0];mesh=UsdGeom.Mesh(original)
    if UsdGeom.Xformable(original).GetOrderedXformOps():raise ValueError('Unexpected source mesh local transform')
    counts=list(mesh.GetFaceVertexCountsAttr().Get())
    if any(n!=3 for n in counts):raise ValueError('Original source triangulation required')
    prisms,audit=source_prisms(mesh.GetPointsAttr().Get(),np.asarray(mesh.GetFaceVertexIndicesAttr().Get()).reshape(-1,3),sha)
    prisms,merged=runtime_prisms(prisms,sha)
    audit.update(runtime_prism_count=len(prisms),exact_adjacent_merges=merged)
    parent=original.GetPath().GetParentPath();created=[]
    for i,points in enumerate(prisms):
        name=parent.AppendChild('E10SourcePrism%03d'%i)
        if stage.GetPrimAtPath(name):raise ValueError('Source collision adaptation already exists')
        cooked,transform=normalized_prism(points)
        part=UsdGeom.Mesh.Define(stage,name);part.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*map(float,p))for p in cooked]))
        n=len(points)//2;faces=[]
        for k in range(1,n-1):faces.extend([0,k,k+1,n,n+k+1,n+k])
        for k in range(n):
            q=(k+1)%n;faces.extend([k,n+k,n+q,k,n+q,q])
        part.CreateFaceVertexCountsAttr([3]*(len(faces)//3));part.CreateFaceVertexIndicesAttr(faces)
        # Only an orthonormal frame and positive diagonal scale: no shear.
        # Cook a well-conditioned prism then exactly recover every source
        # point through the authored local matrix. PhysX mesh scale supports
        # this rotated diagonal scale without altering original material.
        UsdGeom.Xformable(part).AddTransformOp().Set(Gf.Matrix4d(*transform.reshape(-1).tolist()))
        fidelity=PhysxSchema.PhysxConvexHullCollisionAPI.Apply(part.GetPrim())
        fidelity.CreateHullVertexLimitAttr(64);fidelity.CreateMinThicknessAttr(0.)
        part.CreateVisibilityAttr('invisible')
        prim=part.GetPrim();UsdPhysics.CollisionAPI.Apply(prim).CreateCollisionEnabledAttr(True)
        UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr('convexHull');created.append(prim)
    UsdPhysics.CollisionAPI(original).CreateCollisionEnabledAttr(False)
    original.SetCustomDataByKey('videoicl:e10_exact_source_partition',__import__('json').dumps(audit))
    return created


def configure_spec(spec):
    if spec['id']!='E10':raise ValueError('E10 only')
    count=0
    for obj in spec['objects']:
        sha=obj.get('source_asset',{}).get('sha256')
        if sha in SOURCES:
            obj['reviewed_e10_extruded_collision']=sha;count+=1
    if count!=6:raise ValueError('Expected all three colors of original E10 plates')


def normalized_prism(points):
    points=np.asarray(points,float)
    if points.ndim!=2 or points.shape[1]!=3 or len(points)<6 or len(points)%2:
        raise ValueError('Original extruded convex polygon required')
    tri=points[:len(points)//2];pairs=[(i,j)for i in range(len(tri))for j in range(i+1,len(tri))]
    i,j=max(pairs,key=lambda pair:np.linalg.norm(tri[pair[1],:2]-tri[pair[0],:2]))
    u=tri[j]-tri[i];u[2]=0.;u/=np.linalg.norm(u)
    v=np.cross([0.,0.,1.],u);basis=np.column_stack([u,v,[0.,0.,1.]])
    coordinates=points@basis;low=coordinates.min(0);extent=np.ptp(coordinates,axis=0)
    if np.min(extent)<=1e-10:raise ValueError('Degenerate source prism')
    center=(low+extent/2)@basis.T
    normalized=(points-center)@basis/extent
    transform=np.eye(4);transform[:3,:3]=np.diag(extent)@basis.T;transform[3,:3]=center
    if not np.allclose(np.c_[normalized,np.ones(len(points))]@transform,np.c_[points,np.ones(len(points))],atol=1e-12,rtol=0):raise ValueError('Collision coordinate map changed source')
    return normalized,transform


def runtime_prisms(prisms,source_sha256):
    """Join only two proved convex material unions rejected by native scaling."""
    from scipy.spatial import ConvexHull
    if source_sha256 not in SOURCES:raise ValueError('Pinned E10 source identity required')
    if source_sha256!='caae5e783af9afae7ee6c1933e42a1654d746635873c7a1bb221ea4554a70e7b':
        return prisms,[]
    if len(prisms)!=152:raise ValueError('Original triangle partition required')
    replacements={};removed=set();audit=[]
    for i,j in ((109,132),(111,144)):
        a,b=np.asarray(prisms[i]),np.asarray(prisms[j]);a,b=a[:len(a)//2],b[:len(b)//2]
        if np.count_nonzero(np.linalg.norm(a[:,None]-b[None],axis=2)<1e-12)!=2:
            raise ValueError('Exact E10 merge needs original common edge')
        points=np.unique(np.vstack([a,b]),axis=0);hull=ConvexHull(points[:,:2]);area=ConvexHull(a[:,:2]).volume+ConvexHull(b[:,:2]).volume
        if not np.isclose(hull.volume,area,rtol=1e-12,atol=1e-16):
            raise ValueError('E10 material union is not exactly convex')
        top=points[hull.vertices];bottom=top.copy();bottom[:,2]=-.003
        replacements[i]=np.vstack([top,bottom]);removed.add(j)
        audit.append(dict(original_prisms=[i,j],material_union_area_m2=area,
            convex_union_area_m2=float(hull.volume),no_material_added_or_removed=True))
    return [replacements.get(i,points)for i,points in enumerate(prisms)if i not in removed],audit
