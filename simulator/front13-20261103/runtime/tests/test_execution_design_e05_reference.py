import ast,hashlib,json,re
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_e05_reference import grasp_spec,triangle_pinch_geometry,TRIANGLE_SHA,TRIANGLE_HALF_SIZE
from videoicl_isaaclab.execution_design_e05_reference import placement_xy
R=Path(__file__).parents[2]


def actual_vertices():
 p=R/'deployment/real-text300-20261030/asset_roots/VIC_FULL50_RIGID_ASSETS/e05_solid/ravens_triangle_02.usda'
 assert hashlib.sha256(p.read_bytes()).hexdigest()==TRIANGLE_SHA
 vertices=np.array(ast.literal_eval(re.search(r'point3f\[\] points = (\[.*\])',p.read_text())[1]))
 rotation=np.array([[0,-1,0],[1,0,0],[0,0,1]])
 vertices=vertices@rotation.T;vertices-=(vertices.min(axis=0)+vertices.max(axis=0))/2
 return vertices*(TRIANGLE_HALF_SIZE/np.max(abs(vertices),axis=0))


def author(variant='C',condition='I'):
 s=apply_execution_inputs(load('E05',variant,0,R/'runtime/configs/realworld_full50_bindings.json',verify_files=False),condition=condition,seed=4201,revision=REVISION_V3)
 return SimpleNamespace(scene=SimpleNamespace(spec=s),_execution_design_reference_authorized=True)


def test_source_mesh_base_apex_normals_balance_without_geometry_change():
 proof=triangle_pinch_geometry(actual_vertices())
 assert proof['jaw_width_m']==pytest.approx(.031176914536239788)
 assert proof['contact_points_local'][0][1:]==[0.,0.]
 assert np.allclose(np.sum(proof['apex_face_normals_local'],axis=0)[1:],0)
 assert proof['resultant_normal_sum']==[0.,0.,0.]
 assert not proof['native_stability_verified']

@pytest.mark.parametrize('variant','ABC')
@pytest.mark.parametrize('condition','RIE')
def test_private_triangle_grasp_preserves_original_objects_goals_score(variant,condition):
 a=author(variant,condition);before=deepcopy(a.scene.spec)
 for obj in a.scene.spec['objects']:
  new=grasp_spec(a,obj)
  if obj['id']=='triangle':
   assert new is not obj and new['grasp_axis_local']==[1,0,0] and new['grasp_point_local']==[0,0,0]
   assert {k:v for k,v in new.items()if k not in ('grasp_axis_local','grasp_point_local')}=={k:v for k,v in obj.items()if k not in ('grasp_axis_local','grasp_point_local')}
  else:assert new is obj
 assert a.scene.spec==before


def test_formal_and_other_tasks_unchanged():
 a=author();o=next(o for o in a.scene.spec['objects']if o['id']=='triangle');a._execution_design_reference_authorized=False
 assert grasp_spec(a,o)is o
 a._execution_design_reference_authorized=True;a.scene.spec['id']='E14';assert grasp_spec(a,o)is o


def test_changed_geometry_rejected():
 a=author();o=next(o for o in a.scene.spec['objects']if o['id']=='triangle');o['source_asset']['sha256']='changed'
 with pytest.raises(ValueError,match='exact original'):grasp_spec(a,o)
 vertices=actual_vertices();vertices[0,0]+=.001
 with pytest.raises(ValueError,match='Exact original'):triangle_pinch_geometry(vertices)


@pytest.mark.parametrize('variant','ABC')
@pytest.mark.parametrize('condition','RIE')
def test_circle_waypoint_fits_full_source_mesh_without_changing_goal(variant,condition):
 a=author(variant,condition);before=deepcopy(a.scene.spec)
 # This test uses actual source vertices independently of the waypoint helper.
 angle=np.deg2rad(4);r=np.array([[np.cos(angle),-np.sin(angle),0],
                              [np.sin(angle),np.cos(angle),0],[0,0,1]])
 a.c=SimpleNamespace(snapshot=lambda:({'triangle':{'mat':r}},[]))
 target=next(z for z in a.scene.spec['zones']if z['id']=='circle')
 xy=placement_xy(a,'triangle',target)
 footprint=(actual_vertices()@r.T)[:,:2]+xy
 assert np.max(np.linalg.norm(footprint-target['xy'],axis=1))<=target['half_size'][0]-.002
 assert xy[0]==pytest.approx(target['xy'][0]-.015)
 assert a.scene.spec==before


def test_circle_waypoint_refuses_insufficient_clearance_and_tilt():
 a=author();a.c=SimpleNamespace(snapshot=lambda:({'triangle':{'mat':np.eye(3)}},[]))
 target=deepcopy(next(z for z in a.scene.spec['zones']if z['id']=='circle'))
 target['half_size']=[.02,.02]
 with pytest.raises(ValueError,match='does not fit'):placement_xy(a,'triangle',target)
 target['half_size']=[.045,.045]
 r=np.diag([1,-1,-1]);a.c=SimpleNamespace(snapshot=lambda:({'triangle':{'mat':r}},[]))
 with pytest.raises(ValueError,match='upright'):placement_xy(a,'triangle',target)


def test_circle_waypoint_only_private_triangle_circle():
 a=author();target=next(z for z in a.scene.spec['zones']if z['id']=='circle')
 a._execution_design_reference_authorized=False
 np.testing.assert_array_equal(placement_xy(a,'triangle',target),target['xy'])
 a._execution_design_reference_authorized=True
 np.testing.assert_array_equal(placement_xy(a,'cube',target),target['xy'])
 square=next(z for z in a.scene.spec['zones']if z['id']=='square')
 np.testing.assert_array_equal(placement_xy(a,'triangle',square),square['xy'])
