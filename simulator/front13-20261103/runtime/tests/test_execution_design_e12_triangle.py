import numpy as np
from videoicl_isaaclab.execution_design_e12_triangle import convex_intersects_triangle


def test_triangle_hole_stays_empty_while_a_solid_face_intersection_is_detected():
    # Two triangles form the material beside a slit; their combined convex
    # hull would fill the slit and reject the genuinely separated pin.
    pin=np.array([[x,y,z]for x in(-.001,.001)for y in(-.001,.001)for z in(-.003,.003)])
    left=np.array([[-.01,-.01,0],[-.002,-.01,0],[-.002,.01,0]])
    right=np.array([[.002,-.01,0],[.01,-.01,0],[.002,.01,0]])
    assert not convex_intersects_triangle(pin,left)
    assert not convex_intersects_triangle(pin,right)
    assert convex_intersects_triangle(pin,np.array([[-.01,-.01,0],[.01,-.01,0],[0,.01,0]]))
