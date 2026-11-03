"""Geometry/identity guards; native contact execution remains a separate gate."""
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('g1_builder',ROOT/'scripts/build_inference_g1_assets.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
PATCH=json.loads((ROOT/'inference-generalization-v1/g1-bindings-patch.json').read_text())
BASE=json.loads(b.BASE.read_text())

def test_exact_scope_and_unchanged_relations():
 assert set(PATCH['tasks'])==set(b.G1)
 for task,t in PATCH['tasks'].items():
  orig=BASE['tasks'][task]
  assert t['variants']==orig['variants']
  assert t.keys()==orig.keys()
  assert set(t['objects'])==set(orig['objects'])
  for k in t:
   if k not in ('objects','mechanisms'):assert t[k]==orig[k]

def test_sha_and_complete_dependencies():
 root=ROOT/'inference-generalization-v1/assets'
 for task,t in PATCH['tasks'].items():
  records=[o.get('source_asset',o.get('mechanical_asset',{})) for o in t['objects'].values()]
  records += [m['mechanical_asset'] for m in t.get('mechanisms',[])]
  for r in records:
   if r.get('root_env')!='VIC_INFERENCE_ASSETS':continue
   assert r['relative_path'].startswith('g1/'+task+'/')
   for d in [r]+r.get('dependencies',[]):assert b.sha(root/d['relative_path'])==d['sha256']

def test_target_and_fixture_objects_unchanged():
 for task,t in PATCH['tasks'].items():
  replacements=b.replacements(task,t['objects'])
  for oid,o in t['objects'].items():
   original=BASE['tasks'][task]['objects'][oid]
   if oid not in replacements:assert o==original
   else:
    for key in ['size','xy','bottom','yaw','pitch','roll','quaternion','mass','static_friction','dynamic_friction','restitution']:
     expected=original.get(key)
     if key=='size' and task=='E02':expected=[expected[0],expected[1]*.8,expected[2]]
     if key=='size' and task=='E35':expected=[expected[0],expected[1]*.75,expected[2]*.3]
     assert o.get(key)==expected,(task,oid,key)

def test_generated_mesh_closed_collision_components_and_bounds():
 for task,t in PATCH['tasks'].items():
  for oid,kind in b.replacements(task,t['objects']).items():
   size=t['objects'][oid]['size'];mesh=b.shape(kind,b.color_for(oid));mesh.normalize(size)
   for axis in range(3):
    values=[p[axis] for c in mesh.parts for p in c['points']]
    assert max(values)==pytest.approx(size[axis]);assert min(values)==pytest.approx(-size[axis])
   for component in mesh.parts:
    if not component['collision']:continue
    edges={}
    for face in component['faces']:
     for i in range(len(face)):
      edge=tuple(sorted((face[i],face[(i+1)%len(face)])));edges[edge]=edges.get(edge,0)+1
    assert set(edges.values())=={2},(task,oid,component['name'])

def test_spool_hole_is_through_all_collision_shapes():
 m=b.shape('spool',b.COLORS['red']);m.normalize([.02,.02,.003])
 assert len(m.parts)==144
 # Minimum distance of every convex sector's inner chord from center.
 clear_radius=.02*.24*math.cos(math.pi/48)
 assert clear_radius>.0047
 for p in m.parts:
  assert p['collision']
  assert min(math.hypot(x,y) for x,y,z in p['points'])>=.0047999
 # No filled cylinder, no single torus convex hull: 48 sectors x3heightbands.
 for band in ['lower_flange','thread_core','upper_flange']:
  assert sum(p['name'].startswith(band) for p in m.parts)==48

def test_ticket_thickness_and_hidden_initial_face():
 for oid,kind in b.replacements('E47',PATCH['tasks']['E47']['objects']).items():
  o=PATCH['tasks']['E47']['objects'][oid];assert o['size'][2]==.000175
  m=b.shape(kind,b.COLORS['red']);m.normalize(o['size'])
  assert len([p for p in m.parts if p['collision']])==1
  base=next(p for p in m.parts if p['name']=='thin_ticket')
  front=next(p for p in m.parts if p['name']=='front_motif')
  back=next(p for p in m.parts if p['name']=='uniform_back')
  assert base['hidden']
  assert min(v[2] for v in front['points'])==max(v[2] for v in base['points'])
  assert max(v[2] for v in back['points'])==min(v[2] for v in base['points'])
  assert len(next(p for p in m.parts if p['name']=='ticket_edges')['faces'])==4
  assert max(v[2] for p in m.parts for v in p['points'])-min(v[2] for p in m.parts for v in p['points'])==pytest.approx(.00035,abs=1e-14)
  assert o.get('roll',0)==BASE['tasks']['E47']['objects'][oid].get('roll',0)
  assert o['source_asset']['source_rotation']==[1,0,0,0]
 assert PATCH['tasks']['E47']['variants']['A']['semantic']['card_face_axis_local']==[0,0,1]

def test_books_are_uniform_design_across_sizes():
 t=PATCH['tasks']['E35'];sizes=[o['size'] for o in t['objects'].values()]
 assert sorted(s[0] for s in sizes)==[.012,.02,.03]
 assert all(s[1]/s[0]==pytest.approx(.75) and s[2]/s[0]==pytest.approx(.3) for s in sizes)
 # A flat supporting cover exists for every layer, including large-on-small.
 for size in sizes:
  m=b.shape('book',(.2,.32,.58));m.normalize(size)
  top=next(p for p in m.parts if p['name']=='top_cover')
  assert top['collision']

def test_cabinet_joints_and_colliders_unchanged():
 original=BASE['tasks']['E30']['mechanisms'][0]['mechanical_asset']
 new=PATCH['tasks']['E30']['mechanisms'][0]['mechanical_asset']
 for k in ['joint_roles','joint_count','joint_friction','linear_limits_m','contact_links']:
  assert new[k]==original[k]
 old=(ROOT.parent/'deployment/real-text300-20261030/asset_roots/VIC_MECHANISM_ASSETS'/original['relative_path']).read_text()
 newtext=(ROOT/'inference-generalization-v1/assets'/new['relative_path']).read_text()
 # Joint subtree (last part of flattened USDA) unchanged exactly.
 marker='def Scope "Joints"'
 if marker not in old:marker='def "Joints"'
 assert marker in old
 assert old[old.index(marker):]==newtext[newtext.index(marker):]
 assert old.count('PhysicsCollisionAPI')==newtext.count('PhysicsCollisionAPI')


def test_usd_parse_when_available():
 pxr=pytest.importorskip('pxr')
 from pxr import Usd,UsdGeom,UsdPhysics
 root=ROOT/'inference-generalization-v1/assets'
 for task,t in PATCH['tasks'].items():
  for oid in b.replacements(task,t['objects']):
   record=t['objects'][oid]['source_asset'];s=Usd.Stage.Open(str(root/record['relative_path']))
   assert s and s.GetDefaultPrim()
   assert any(p.HasAPI(UsdPhysics.CollisionAPI) for p in s.Traverse())
