"""Build physically distinct cabinet frames; no model or simulation invocation."""
import copy, hashlib, json, shutil
from pathlib import Path
from pxr import Usd, UsdGeom, UsdPhysics, Gf
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parent/'deployment/real-text300-20261030/asset_roots/VIC_MECHANISM_ASSETS'
OUT=ROOT/'execution-design-v3/assets/E30'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def vertices(stage,root):
 cache=UsdGeom.XformCache();out=[]
 for prim in Usd.PrimRange(root):
  if prim.IsA(UsdGeom.Mesh) and prim.HasAPI(UsdPhysics.CollisionAPI):
   t=cache.GetLocalToWorldTransform(prim)
   out.extend(tuple(t.Transform(Gf.Vec3d(*p))) for p in UsdGeom.Mesh(prim).GetPointsAttr().Get())
 return out

def build():
 bindings=json.loads((ROOT/'configs/realworld_full50_bindings.json').read_text())
 # Locate one immutable source record without relying on catalog wrapper shape.
 def find(x):
  if isinstance(x,dict):
   if x.get('id')=='cabinet_2_tier_v3' and x.get('kind')=='articulation':return x
   for v in x.values():
    r=find(v)
    if r:return r
  if isinstance(x,list):
   for v in x:
    r=find(v)
    if r:return r
 old=find(bindings);source=SOURCE/old['relative_path'];assert sha(source)==old['sha256']
 OUT.mkdir(parents=True,exist_ok=True)
 for dep in old['dependencies']:
  src=SOURCE/dep['relative_path'];assert sha(src)==dep['sha256'];dst=OUT/dep['relative_path'];dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 original=Usd.Stage.Open(str(source));points=vertices(original,original.GetDefaultPrim());lo=[min(p[a]for p in points)for a in range(3)];hi=[max(p[a]for p in points)for a in range(3)]
 # The global bounds include handles in front of the fixed frame. Extending
 # a roof to that front edge obstructs the upper finger during drawer closure.
 # Match the original fixed cabinet's front, leaving the actual handle free.
 fixed_points=vertices(original,original.GetPrimAtPath('/Asset/Links/link_0'))
 fixed_front=min(p[0]for p in fixed_points)
 assert fixed_front>lo[0]
 # All source prismatic joints travel along asset X. A Y-separated outer
 # frame therefore stays clear for the entire joint travel, not just t=0.
 cache=UsdGeom.XformCache();axes=[]
 for prim in original.Traverse():
  if prim.IsA(UsdPhysics.PrismaticJoint):
   j=UsdPhysics.PrismaticJoint(prim);axis=j.GetAxisAttr().Get();local={'X':Gf.Vec3d(1,0,0),'Y':Gf.Vec3d(0,1,0),'Z':Gf.Vec3d(0,0,1)}[axis]
   body=original.GetPrimAtPath(j.GetBody0Rel().GetTargets()[0]);q=j.GetLocalRot0Attr().Get();direction=cache.GetLocalToWorldTransform(body).TransformDir(Gf.Rotation(q).TransformDir(local));assert abs(direction[1])<1e-6 and abs(direction[2])<1e-6
   axes.append(dict(joint=str(prim.GetPath()),axis_asset=list(direction),limits=[j.GetLowerLimitAttr().Get(),j.GetUpperLimitAttr().Get()]))
 records=[]
 for index,thickness in enumerate((.004,.007,.010)):
  height=(.040,.045,.050)[index]
  path=OUT/f'cabinet_outer_frame_legs_{index}.usda';shutil.copyfile(source,path);stage=Usd.Stage.Open(str(path));body=stage.GetPrimAtPath('/Asset/Links/link_0');inverse=UsdGeom.XformCache().GetLocalToWorldTransform(body).GetInverse();frames=[]
  for side in (-1,1):
   y0,y1=(lo[1]-.002-thickness,lo[1]-.002)if side<0 else(hi[1]+.002,hi[1]+.002+thickness)
   low=[lo[0],y0,lo[2]];high=[hi[0],y1,hi[2]+.012]
   frames.append((f'v3_side_{side}',low,high))
  frames.append(('v3_top',[fixed_front,lo[1]-.002-thickness,hi[2]+.006],[hi[0],hi[1]+.002+thickness,hi[2]+.012]))
  # Visible, collision-bearing supports outside the complete drawer sweep.
  # Matching root-height lift is applied only to explicit I/E task inputs.
  for side in (-1,1):
   y0,y1=(lo[1]-.002-thickness,lo[1]-.002)if side<0 else(hi[1]+.002,hi[1]+.002+thickness)
   frames.append(('v3_support_left'if side<0 else'v3_support_right',[lo[0],y0,lo[2]-height-.002],[hi[0],y1,lo[2]+.006]))
  for name,low,high in frames:
   mesh=UsdGeom.Mesh.Define(stage,str(body.GetPath())+'/'+name.replace('-','m'));pts=[(x,y,z)for z in (low[2],high[2])for y in(low[1],high[1])for x in(low[0],high[0])]
   mesh.CreatePointsAttr([inverse.Transform(Gf.Vec3d(*p))for p in pts]);mesh.CreateFaceVertexCountsAttr([4]*6);mesh.CreateFaceVertexIndicesAttr([0,2,3,1,4,5,7,6,0,1,5,4,2,6,7,3,0,4,6,2,1,3,7,5]);mesh.CreateSubdivisionSchemeAttr('none');mesh.CreateDisplayColorAttr([(.27,.20,.13)if name.startswith('v3_support')else(0.23,0.29,0.31)])
   UsdPhysics.CollisionAPI.Apply(mesh.GetPrim()).CreateCollisionEnabledAttr(True);UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim()).CreateApproximationAttr('convexHull')
  stage.GetRootLayer().Save();stage=Usd.Stage.Open(str(path));actual=vertices(stage,stage.GetDefaultPrim());bounds=[[min(p[a]for p in actual)for a in range(3)],[max(p[a]for p in actual)for a in range(3)]]
  record=copy.deepcopy(old);record.update(id=f'cabinet_outer_frame_legs_v3_{index}',root_env='VIC_EXECUTION_DESIGN_ASSETS',relative_path='E30/'+path.name,sha256=sha(path),bounds=bounds,source_modified=True);record.pop('path',None)
  record['dependencies']=[dict(relative_path='E30/'+d['relative_path'],sha256=d['sha256'])for d in old['dependencies']]
  records.append(dict(index=index,asset=record,source_sha256=sha(source),new_collision_components=5,base_lift_m=height,source_collision_and_joints_unchanged=True,side_clearance_m=.002,top_clearance_m=.006,top_front_asset_x_m=fixed_front,top_front_setback_from_handle_m=fixed_front-lo[0],side_thickness_m=thickness,native_verified=False,source_joint_axes=axes))
 metadata=dict(schema='execution-e30-physical-instances-v1',instances=records,source_collision_bounds=[lo,hi]);(OUT/'instances.private.json').write_text(json.dumps(metadata,indent=2));print(json.dumps(dict(instances=len(records),bounds=[x['asset']['bounds']for x in records],native_verified=False)))
if __name__=='__main__':build()
