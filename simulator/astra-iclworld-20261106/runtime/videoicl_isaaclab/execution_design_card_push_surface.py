"""Read-only actual Panda leading-face filter for a thin card push."""
import numpy as np
from scipy.spatial import ConvexHull
from .execution_design_cutlery_grasp import plane_section


def leading_surface(meshes,material_height,outward,band=.00002):
    axis=np.asarray(outward,float);axis/=np.linalg.norm(axis)
    if axis.shape!=(3,)or abs(axis[2])>.001:raise ValueError('Horizontal push direction required')
    sections=[]
    for mesh in meshes:
        try:sections.append(plane_section(np.asarray(mesh,float),material_height))
        except ValueError:pass
    if not sections:raise ValueError('No actual toe cross-section at card contact height')
    leading=max(float(np.max(section@axis))for section in sections);faces=[]
    for mesh in meshes:
        mesh=np.asarray(mesh,float);hull=ConvexHull(mesh)
        for plane,ids in zip(hull.equations,hull.simplices):
            triangle=mesh[ids]
            if triangle[:,2].min()>material_height or triangle[:,2].max()<material_height or plane[:3]@axis<.85:continue
            points=[]
            for a,b in zip(triangle,np.roll(triangle,1,axis=0)):
                if(a[2]-material_height)*(b[2]-material_height)<=0 and abs(a[2]-b[2])>1e-12:
                    points.append(a+(b-a)*((material_height-a[2])/(b[2]-a[2])))
            if points and max(float(p@axis)for p in points)>=leading-band:
                faces.append(dict(normal=plane[:3].tolist(),normal_along_push=float(plane[:3]@axis),vertical_normal=float(plane[2]),vertices=triangle.tolist()))
    acceptable=[f for f in faces if abs(f['vertical_normal'])<.15]
    if not acceptable:raise ValueError('Actual leading toe would press card down instead of a horizontal push')
    return max(acceptable,key=lambda f:f['normal_along_push']-abs(f['vertical_normal']))
