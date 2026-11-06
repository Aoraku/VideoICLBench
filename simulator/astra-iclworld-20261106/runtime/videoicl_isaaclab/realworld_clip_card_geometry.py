"""SHA-bound source-card entity distance to an actual clip-mouth segment.

Uses the closed original collision mesh, not its empty AABB corners or COM.
Declared primitive boxes are supported for CPU evidence fixtures only; an
unregistered source asset never falls back to a box.
"""
from functools import lru_cache
import hashlib
import itertools
import numpy as np
from . import realworld_source_card_geometry as source


class CollisionEntity:
    def __init__(self,vertices,triangles):
        self.vertices=np.asarray(vertices,float);self.triangles=np.asarray(triangles,int)
        if self.vertices.ndim!=2 or self.vertices.shape[1]!=3 or not np.isfinite(self.vertices).all():raise ValueError('Finite source collision vertices required')
        if self.triangles.ndim!=2 or self.triangles.shape[1]!=3 or self.triangles.min()<0 or self.triangles.max()>=len(self.vertices):raise ValueError('Actual source triangles required')
        self.tri=self.vertices[self.triangles]
        normal=np.cross(self.tri[:,1]-self.tri[:,0],self.tri[:,2]-self.tri[:,0]);length=np.linalg.norm(normal,axis=1)
        if np.any(length<1e-16):raise ValueError('Degenerate source collision triangle')
        normal/=length[:,None];inward=np.einsum('ij,ij->i',normal,self.vertices.mean(0)-self.tri[:,0])>0;normal[inward]*=-1
        self.normal=normal;self.offset=np.einsum('ij,ij->i',normal,self.tri[:,0])
        if np.max(self.vertices@normal.T-self.offset)>1e-9:raise ValueError('Original source card collision must be convex')
        edge=np.concatenate((self.triangles[:,[0,1]],self.triangles[:,[1,2]],self.triangles[:,[2,0]]));edge=np.sort(edge,axis=1);self.edge_ids,counts=np.unique(edge,axis=0,return_counts=True)
        if not np.all(counts==2):raise ValueError('Original source card collision must be closed')
        self.edges=self.vertices[self.edge_ids]

    def _point_surface(self,p):
        a,b,c=self.tri[:,0],self.tri[:,1],self.tri[:,2];ab=b-a;ac=c-a
        normal=self.normal;projection=p-normal*(normal@p-self.offset)[:,None]
        v=projection-a;aa=np.einsum('ij,ij->i',ab,ab);bb=np.einsum('ij,ij->i',ab,ac);cc=np.einsum('ij,ij->i',ac,ac);d=np.einsum('ij,ij->i',v,ab);e=np.einsum('ij,ij->i',v,ac);den=aa*cc-bb*bb
        u=(d*cc-e*bb)/den;w=(e*aa-d*bb)/den;inside=(u>=-1e-12)&(w>=-1e-12)&(u+w<=1+1e-12)
        starts=self.tri[:,[0,1,2]];ends=self.tri[:,[1,2,0]];delta=ends-starts;t=np.einsum('nki,nki->nk',p-starts,delta)/np.einsum('nki,nki->nk',delta,delta);on_edges=starts+np.clip(t,0,1)[...,None]*delta;dist=np.sum((on_edges-p)**2,axis=2);q=on_edges[np.arange(len(self.tri)),np.argmin(dist,axis=1)];q[inside]=projection[inside]
        index=int(np.argmin(np.sum((q-p)**2,axis=1)));return q[index]

    def closest_to_segment(self,a,b):
        a=np.asarray(a,float);b=np.asarray(b,float);u=b-a;uu=float(u@u)
        if uu<1e-20:raise ValueError('Actual nonzero clip-mouth segment required')
        den=self.normal@u;rhs=self.offset-self.normal@a;parallel=np.abs(den)<1e-14;lo=0.;hi=1.
        if not np.any(rhs[parallel]<-1e-12):
            lo=max(lo,float(np.max(rhs[den<-1e-14]/den[den<-1e-14],initial=-np.inf)));hi=min(hi,float(np.min(rhs[den>1e-14]/den[den>1e-14],initial=np.inf)))
            if lo<=hi+1e-12:
                t=float(np.clip((lo+hi)/2,0,1));p=a+t*u;return dict(distance_m=0.,card_point_local=p,segment_point_local=p,axis_parameter=t)
        candidates=[]
        for p in (a,b):
            q=self._point_surface(p);candidates.append((float(np.sum((p-q)**2)),q,p))
        # Interior line/edge closest pairs, plus every vertex/segment boundary.
        c=self.edges[:,0];v=self.edges[:,1]-c;w=a-c;vv=np.einsum('ij,ij->i',v,v);uv=v@u;uw=w@u;vw=np.einsum('ij,ij->i',v,w);det=uu*vv-uv*uv;valid=det>1e-20
        s=np.divide(uv*vw-vv*uw,det,out=np.zeros_like(det),where=valid);t=np.divide(uu*vw-uv*uw,det,out=np.zeros_like(det),where=valid);valid&=(s>=0)&(s<=1)&(t>=0)&(t<=1)
        if valid.any():
            ps=a+s[valid,None]*u;qs=c[valid]+t[valid,None]*v[valid];d2=np.sum((ps-qs)**2,axis=1);i=int(np.argmin(d2));candidates.append((float(d2[i]),qs[i],ps[i]))
        t=np.clip((self.vertices-a)@u/uu,0,1);ps=a+t[:,None]*u;d2=np.sum((ps-self.vertices)**2,axis=1);i=int(np.argmin(d2));candidates.append((float(d2[i]),self.vertices[i],ps[i]))
        distance,q,p=min(candidates,key=lambda x:x[0]);return dict(distance_m=float(np.sqrt(max(0.,distance))),card_point_local=q,segment_point_local=p,axis_parameter=float((q-a)@u/uu))


@lru_cache(maxsize=1)
def _original_source_entity():
    v=np.asarray(source.VERTICES_BODY_LOCAL,dtype='<f8');f=np.asarray(source.TRIANGLES,dtype='<i8')
    if hashlib.sha256(v.tobytes()+f.tobytes()).hexdigest()!=source.GEOMETRY_ARRAY_SHA256:raise ValueError('SHA-bound source card collision payload was changed')
    return CollisionEntity(v,f)


def collision_entity(recipe):
    asset=recipe.get('source_asset')
    if asset is not None:
        if asset.get('sha256')!=source.SOURCE_ASSET_SHA256:raise ValueError('Unregistered source card collision SHA')
        half=np.asarray(recipe['size'],float);q=np.asarray(asset.get('source_rotation',[1,0,0,0]),float);expected=np.asarray(source.RECIPE_SOURCE_ROTATION,float)
        practical=recipe.get('engineering_practical_card',{})
        approximate=(practical.get('schema')=='engineering-practical-card-1mm-v1'
                     and practical.get('source_exact_geometry')is False
                     and practical.get('approximate_thickness_m')==.001)
        expected_half=np.asarray(source.RECIPE_HALF_SIZE,float).copy()
        if approximate:expected_half[2]=.0005
        if half.shape!=(3,)or not np.allclose(half,expected_half,rtol=1e-9,atol=1e-10):raise ValueError('Source card collision fit differs from reviewed recipe')
        if q.shape!=(4,)or not np.isfinite(q).all()or np.linalg.norm(q)<1e-12 or not np.isclose(abs((q/np.linalg.norm(q))@(expected/np.linalg.norm(expected))),1.,atol=1e-12,rtol=0):raise ValueError('Source card collision rotation differs from reviewed recipe')
        original=_original_source_entity()
        if approximate:
            vertices=original.vertices.copy();vertices[:,2]*=.0005/float(source.RECIPE_HALF_SIZE[2])
            return CollisionEntity(vertices,original.triangles)
        return original
    if recipe.get('kind')!='box':raise ValueError('No source collision geometry; primitive fallback forbidden')
    half=np.asarray(recipe['size'],float)
    if half.shape!=(3,)or not np.isfinite(half).all()or np.any(half<=0):raise ValueError('Exact primitive box dimensions required')
    vertices=np.asarray(list(itertools.product((-1.,1.),repeat=3)))*half
    faces=[]
    for axis in range(3):
        for side in (-1,1):
            ids=[i for i,p in enumerate(vertices)if np.isclose(p[axis],side*half[axis])];a,b,c,d=ids;faces.extend(((a,b,d),(a,d,c)))
    return CollisionEntity(vertices,faces)
