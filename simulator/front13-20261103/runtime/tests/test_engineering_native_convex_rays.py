import numpy as np
from scipy.spatial import ConvexHull
from videoicl_isaaclab.engineering_native_convex_rays import convex_from_native_planes,line_entry


def test_native_plane_reconstruction_preserves_thin_side_band_and_rotated_faces():
    points=np.array([[x,y,z]for x in(-.01,.01)for y in(-.012,.012)for z in(0.,.054)])
    angle=.27;r=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
    points=points@r.T+[-.075,.1,.81];hull=ConvexHull(points)
    samples=[(points[tri].mean(0),plane[:3])for tri,plane in zip(hull.simplices,hull.equations)]
    actual,planes=convex_from_native_planes(samples)
    assert len(planes)==6 and len(actual)==8
    assert np.max(actual@hull.equations[:,:3].T+hull.equations[:,3])<1e-10
    target=np.mean(points,axis=0);origin=target+[0,0,-.1]
    assert abs(line_entry(actual,origin,[0,0,1])[2]-.81)<1e-10
    assert line_entry(actual,origin+[1,0,0],[0,0,1])is None
