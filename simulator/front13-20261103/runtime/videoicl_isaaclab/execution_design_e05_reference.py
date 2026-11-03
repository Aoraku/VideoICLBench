"""Private engineering grasp for the unchanged E05 solid triangular prism."""
from copy import deepcopy
import json
import numpy as np
from .execution_design import REVISION_V3

TRIANGLE_SHA='8c86d186418e868214adf16b5c3d7ae5c82971103d3543eeaa3cd505cc08fa6b'
TRIANGLE_HALF_SIZE=np.array([.015588457268119894,.018,.011])


def triangle_pinch_geometry(vertices):
    """Check the original base/vertex pair has balanced horizontal support.

    The apex supports +X in the cone between its two original sloping faces;
    the flat base supports -X. This is an analytic candidate, not native proof.
    """
    p=np.asarray(vertices,float)
    if p.ndim!=2 or p.shape[1]!=3 or len(p)<6 or not np.isfinite(p).all():
        raise ValueError('Full triangular prism vertices required')
    a,b,h=TRIANGLE_HALF_SIZE
    expected=np.array([[x,y,z]for x,y in [(-a,-b),(-a,b),(a,0)]for z in [-h,h]])
    if len(p)!=6 or any(np.min(np.linalg.norm(p-v,axis=1))>1e-8 for v in expected):
        raise ValueError('Exact original triangular prism footprint required')
    # Two sloping side normals at the apex: their Y components cancel.
    normals=np.array([[b,2*a,0.],[b,-2*a,0.]])
    normals/=np.linalg.norm(normals,axis=1)[:,None]
    apex_support=normals.sum(axis=0);apex_support/=np.linalg.norm(apex_support)
    if not np.allclose(apex_support,[1,0,0],atol=1e-12):
        raise ValueError('Apex normal cone cannot oppose base')
    return dict(axis_local=[1.,0.,0.],point_local=[0.,0.,0.],jaw_width_m=2*a,
                contact_points_local=[[-a,0.,0.],[a,0.,0.]],
                base_normal_local=[-1.,0.,0.],apex_face_normals_local=normals.tolist(),
                resultant_normal_sum=[0.,0.,0.],native_stability_verified=False)


def grasp_spec(author,obj):
    spec=author.scene.spec;design=spec.get('execution_design',{})
    if not(getattr(author,'_execution_design_reference_authorized',False)
           and spec.get('id')=='E05' and design.get('revision')==REVISION_V3
           and obj.get('id')=='triangle'):
        return obj
    source=obj.get('source_asset',{})
    if (source.get('sha256')!=TRIANGLE_SHA
        or not np.allclose(obj.get('size',[]),TRIANGLE_HALF_SIZE,atol=1e-10,rtol=0)
        or not np.allclose(source.get('source_rotation',[]),[2**-.5,0,0,2**-.5],atol=1e-10,rtol=0)):
        raise ValueError('E05 pinch requires exact original triangular prism')
    # Y closes against two oblique faces, with a same-sign X resultant; the
    # observed C trial squeezed the body 21mm before lift and then rolled it.
    # X closes against the original flat base and apex; no shape/force changes.
    result=deepcopy(obj);result['grasp_axis_local']=[1,0,0];result['grasp_point_local']=[0.,0.,0.]
    return result


def placement_xy(author,name,target):
    """Choose a nearer point *inside* the unchanged circular paper marker.

    The original six source collision vertices, measured body rotation and
    original marker radius must all fit with 2mm spare room. This only changes
    a private reference waypoint; the region, mesh and native score stay intact.
    """
    center=np.asarray(target['xy'],float)
    spec=author.scene.spec
    if not (getattr(author,'_execution_design_reference_authorized',False)
            and spec.get('id')=='E05' and name=='triangle'
            and spec.get('execution_design',{}).get('revision')==REVISION_V3
            and target.get('shape')=='circle'):
        return center.copy()
    obj=next(o for o in spec['objects']if o['id']==name)
    grasp_spec(author,obj)  # Exact original source hash, size and source rotation.
    a,b,h=TRIANGLE_HALF_SIZE
    vertices=np.array([[x,y,z]for x,y in [(-a,-b),(-a,b),(a,0)]for z in [-h,h]])
    triangle_pinch_geometry(vertices)
    state,_=author.c.snapshot();rotation=np.asarray(state[name]['mat'],float)
    radius=np.asarray(target['half_size'],float)
    if (radius.shape!=(2,) or not np.isfinite(radius).all() or np.min(radius)<=.002
            or not np.allclose(radius[0],radius[1],atol=1e-9,rtol=0)
            or rotation.shape!=(3,3) or not np.isfinite(rotation).all()
            or not np.allclose(rotation.T@rotation,np.eye(3),atol=1e-5)
            or rotation[2,2]<np.cos(np.deg2rad(5))):
        raise ValueError('E05 placement requires original circular marker and upright measured body')
    chosen=center+np.array([-.015,0.])
    footprint=(vertices@rotation.T)[:,:2]+chosen
    clearance=float(radius[0]-np.linalg.norm(footprint-center,axis=1).max())
    if clearance<.002:
        raise ValueError('Full original triangle does not fit nearer circular marker waypoint')
    if getattr(author,'out',None) is not None:
        with (author.out/'e05-placement-goals.private.jsonl').open('a')as stream:
            stream.write(json.dumps(dict(object=name,original_marker_center=center.tolist(),
                reference_xy=chosen.tolist(),source_sha256=TRIANGLE_SHA,
                actual_rotated_collision_footprint=footprint.tolist(),
                minimum_marker_clearance_m=clearance,world_and_score_unchanged=True))+'\n')
    return chosen
