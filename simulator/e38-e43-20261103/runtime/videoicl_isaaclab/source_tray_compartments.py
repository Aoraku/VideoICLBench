"""Whole-ball cell membership against the pinned original tray walls."""
from pathlib import Path
import hashlib
import numpy as np


class SourceTrayCompartments:
    def __init__(self,geometry,actor,root=None):
        root=Path(root or Path(__file__).resolve().parents[1]).resolve()
        path=(root/geometry['path']).resolve()
        if not path.is_relative_to(root)or hashlib.sha256(path.read_bytes()).hexdigest()!=geometry['sha256']:
            raise ValueError('Original tray geometry archive identity mismatch')
        with np.load(path,allow_pickle=False)as data:
            if str(data['source_sha256'])!=actor['source_asset']['sha256']or not np.allclose(data['descriptor_half_size'],actor['size'],atol=1e-12,rtol=0):
                raise ValueError('Original tray source identity or dimensions mismatch')
            triangles=np.asarray(data['triangles_body_m'],float)
        if triangles.ndim!=3 or triangles.shape[1:]!=(3,3)or not np.isfinite(triangles).all():
            raise ValueError('Finite original tray triangles required')
        a,b,c=triangles[:,0],triangles[:,1],triangles[:,2];u,v=b-a,c-a
        normal=np.cross(u,v);length=np.linalg.norm(normal,axis=1);self.axes=[]
        for axis in (0,1):
            other=[i for i in range(3)if i!=axis]
            det=u[:,other[0]]*v[:,other[1]]-u[:,other[1]]*v[:,other[0]]
            good=(length>1e-14)&(np.abs(det)>1e-14)
            self.axes.append((other,a[good],u[good],v[good],det[good],np.abs(normal[good,axis])/length[good]))
        # Circumscribed spherical sampling: every unit direction lies within
        # latitude_half_step + longitude_half_step of a sampled direction.
        # Scaling by sec(bound) makes the sampled convex hull contain the
        # entire analytic ball, rather than checking only a few inner points.
        theta=np.arange(32)*2*np.pi/32;phi=np.linspace(-np.pi/2,np.pi/2,13)
        self.sphere=np.array([[np.cos(p)*np.cos(t),np.cos(p)*np.sin(t),np.sin(p)]for p in phi for t in theta])
        self.sphere/=np.cos(np.pi/24+np.pi/32)

    def contains(self,center,radius,zone,tolerance=.005):
        center=np.asarray(center,float);origin=np.asarray(zone['anchor_local_center'],float)
        half=np.asarray(zone['half_size'],float)
        if center.shape!=(3,)or not np.isfinite(center).all()or not 0<radius<=.1:return False
        # The old trusted core and its original tolerance remain sufficient.
        points=center+float(radius)*self.sphere
        for axis in (0,1):
            low,high=origin[axis]-half[axis],origin[axis]+half[axis]
            other,a,u,v,det,normal_axis=self.axes[axis]
            out=points[(points[:,axis]<low-tolerance)|(points[:,axis]>high+tolerance)]
            for point in out:
                sign=1 if point[axis]>high else -1
                delta=point[other]-a[:,other]
                beta=(delta[:,0]*v[:,other[1]]-delta[:,1]*v[:,other[0]])/det
                gamma=(u[:,other[0]]*delta[:,1]-u[:,other[1]]*delta[:,0])/det
                hit=a[:,axis]+beta*u[:,axis]+gamma*v[:,axis]
                valid=(beta>=-1e-9)&(gamma>=-1e-9)&(beta+gamma<=1+1e-9)&(sign*(hit-origin[axis])>1e-9)
                ids=np.flatnonzero(valid)
                if not len(ids):return False
                first=ids[np.argmin(sign*(hit[ids]-origin[axis]))]
                bound=high if sign>0 else low
                if normal_axis[first]<.5 or sign*(hit[first]-bound)<-tolerance:return False
                if sign*(point[axis]-hit[first])*normal_axis[first]>tolerance:return False
        return True
