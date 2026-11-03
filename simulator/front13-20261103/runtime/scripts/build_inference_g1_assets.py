#!/usr/bin/env python3
"""Deterministic G1 inference-only meshes. Does not modify base assets or demos.

Replacement bodies retain mass, contact
coefficients and start pose; only E02/E35 use documented proportional resizing.
Authored meshes are new rigid visual/collision
instances, not label substitutions. Concave silhouettes use convex components;
the spool is a compound annulus, never a solid convex hull.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, math, re, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'configs/initial-admission-e13-e25-20261030/e13-hframe-v2-bindings.candidate.json'
OUT=ROOT/'inference-generalization-v1'
G1=['E01','E02','E08','E13','E14','E15','E16','E17','E18','E21','E22','E24','E25','E27','E30','E34','E35','E38','E39','E47']
COLORS={'red':(.8,.055,.035),'blue':(.035,.2,.8),'green':(.08,.55,.14),'yellow':(.95,.72,.035),'black':(.07,.07,.09)}
SILVER=(.64,.68,.72); PAPER=(.88,.85,.72); DARK=(.07,.08,.1)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def vec(v):return '('+', '.join(f'{x:.12g}' for x in v)+')'
def color_for(name):return next((c for k,c in COLORS.items() if k in name),(.4,.24,.12))
class Meshes:
 def __init__(self):self.parts=[]
 def mesh(self,name,pts,faces,color,collision=True):self.parts.append(dict(name=name,points=pts,faces=faces,color=color,collision=collision))
 def prism(self,name,poly,z0,z1,color,collision=True):
  n=len(poly);pts=[(x,y,z) for z in [z0,z1] for x,y in poly]
  faces=[list(reversed(range(n))),list(range(n,2*n))]+[[i,(i+1)%n,(i+1)%n+n,i+n] for i in range(n)]
  self.mesh(name,pts,faces,color,collision)
 def box(self,name,lo,hi,color,collision=True):self.prism(name,[(lo[0],lo[1]),(hi[0],lo[1]),(hi[0],hi[1]),(lo[0],hi[1])],lo[2],hi[2],color,collision)
 def disk(self,name,rx,ry,z0,z1,color,cx=0,cy=0,n=32,collision=True):
  self.prism(name,[(cx+rx*math.cos(2*math.pi*i/n),cy+ry*math.sin(2*math.pi*i/n)) for i in range(n)],z0,z1,color,collision)
 def lathe(self,name,rings,color,n=32,collision=True):
  pts=[(r*math.cos(2*math.pi*i/n),r*math.sin(2*math.pi*i/n),z) for z,r in rings for i in range(n)]
  faces=[list(reversed(range(n))),list(range((len(rings)-1)*n,len(rings)*n))]
  faces += [[j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i] for j in range(len(rings)-1) for i in range(n)]
  self.mesh(name,pts,faces,color,collision)
 def ring(self,name,inner,outer,z0,z1,color,n=48):
  for i in range(n):
   a,b=2*math.pi*i/n,2*math.pi*(i+1)/n
   self.prism(f'{name}_{i}',[(inner*math.cos(a),inner*math.sin(a)),(outer*math.cos(a),outer*math.sin(a)),(outer*math.cos(b),outer*math.sin(b)),(inner*math.cos(b),inner*math.sin(b))],z0,z1,color)
 def normalize(self,size):
  lows=[min(p['points'][i][a] for p in self.parts for i in range(len(p['points']))) for a in range(3)]
  highs=[max(p['points'][i][a] for p in self.parts for i in range(len(p['points']))) for a in range(3)]
  for p in self.parts:p['points']=[tuple((v[a]-(lows[a]+highs[a])/2)*2*size[a]/(highs[a]-lows[a]) for a in range(3)) for v in p['points']]
 def text(self):
  out=['#usda 1.0','(defaultPrim = "Asset"\n metersPerUnit = 1\n upAxis = "Z")','def Xform "Asset" {']
  for i,p in enumerate(self.parts):
   name=p['name'];mat=f'/Asset/Material_{i}'
   schemas='["MaterialBindingAPI", "PhysicsCollisionAPI", "PhysicsMeshCollisionAPI"]' if p['collision'] else '["MaterialBindingAPI"]'
   out += [f'def Mesh "{name}" (apiSchemas = {schemas}) {{','uniform token subdivisionScheme = "none"','bool doubleSided = true',f'point3f[] points = [{", ".join(vec(x) for x in p["points"])}]',f'int[] faceVertexCounts = {[len(f) for f in p["faces"]]}',f'int[] faceVertexIndices = {[i for f in p["faces"] for i in f]}',f'color3f[] primvars:displayColor = [{vec(p["color"])}]',f'rel material:binding = <{mat}>']
   if p.get('hidden'):out+=['token visibility = "invisible"']
   if p['collision']:out+=['bool physics:collisionEnabled = true','uniform token physics:approximation = "convexHull"']
   out+=['}',f'def Material "Material_{i}" {{',f'token outputs:surface.connect = <{mat}/Shader.outputs:surface>','def Shader "Shader" {','uniform token info:id = "UsdPreviewSurface"',f'color3f inputs:diffuseColor = {vec(p["color"])}','float inputs:roughness = 0.62','token outputs:surface','}','}']
  return '\n'.join(out+['}'])+'\n'

def shape(kind,color):
 m=Meshes()
 if kind=='burger':
  for name,r,z0,z1,c in [('heel',.9,-1,-.62,(.65,.32,.1)),('patty',1,-.62,-.27,(.2,.07,.025)),('cheese',1,-.27,-.18,(.98,.66,.06)),('lettuce',1.04,-.18,0,(.2,.55,.06))]:m.disk(name,r,r,z0,z1,c)
  m.lathe('wholegrain_bun',[(0,.98),(.35,.95),(.68,.8),(1,.28)],(.7,.4,.16))
  for i in range(8):
   a=2*math.pi*i/8;m.disk(f'seed_{i}',.055,.025,.7,.735,(.93,.82,.6),.45*math.cos(a),.45*math.sin(a),8,False)
 elif kind=='fries':
  m.prism('striped_carton',[(-.8,-.65),(.8,-.65),(1,.7),(-1,.7)],-1,.3,(.15,.3,.65))
  for i in range(7):
   x=-.78+i*.26;m.box(f'fry_{i}',(x,-.25,.2),(x+.14,.02,.8+(i%3)*.1),(.95,.66,.12))
  for i in range(3):m.box(f'carton_stripe_{i}',(-.62+i*.48,-.657,-.8),(-.42+i*.48,-.65,.1),(.95,.94,.82),False)
 elif kind=='drink':
  m.lathe('aluminum_can',[(-1,.78),(-.93,.91),(-.8,1),(.8,1),(.93,.91),(1,.78)],(.12,.64,.58))
  m.disk('top_lid',.78,.78,1,1.025,SILVER);m.ring('pull_tab',.1,.22,1.025,1.04,SILVER,16)
  m.box('cream_label',(-.48,-1.005,-.4),(.48,-1,.4),(.93,.87,.64),False)
 elif kind=='soap':
  m.prism('chamfered_soap',[(-.85,-1),(.85,-1),(1,-.85),(1,.85),(.85,1),(-.85,1),(-1,.85),(-1,-.85)],-1,1,color)
  m.disk('embossed_oval',.45,.25,1,1.003,tuple(min(1,c+.15) for c in color),collision=False)
  for i in range(3):m.box(f'soap_engraving_{i}',(-.23+i*.2,-.13,1.003),(-.16+i*.2,.13,1.004),tuple(c*.72 for c in color),False)
 elif kind=='book':
  m.box('pages',(-.94,-.92,-.78),(.94,.92,.78),PAPER)
  m.box('bottom_cover',(-1,-1,-1),(1,1,-.78),color);m.box('top_cover',(-1,-1,.78),(1,1,1),color)
  m.box('spine',(-1,-1,-.78),(-.91,1,.78),color)
  m.box('cover_inset',(-.65,-.72,1),(.64,.7,1.001),tuple(min(1,c+.2) for c in color),False)
  for i in range(5):m.box(f'page_line_{i}',(.94,-.91,-.6+i*.3),(.941,.91,-.585+i*.3),(.63,.6,.52),False)
 elif kind in ('left_shoe','right_shoe'):
  sign=1 if kind=='left_shoe' else -1
  poly=[(-1,-.58),(-.78,-.88),(.45,-.95),(.92,-.62),(1,0),(.8,.75),(.3,1),(-.8,.7)]
  poly=[(x,y*sign) for x,y in poly]
  if sign<0:poly.reverse()
  m.prism('rubber_sole',poly,-1,-.65,(.91,.9,.83));m.prism('sneaker_upper',[(x*.95,y*.86) for x,y in poly],-.65,.45,(.1,.25,.49))
  m.box('heel_collar',(-.88,-.45,.45),(-.45,.45,1),(.2,.35,.57))
  for i in range(4):m.box(f'lace_{i}',(-.15+i*.14,-.42,.46),(-.11+i*.14,.42,.51),(.96,.95,.86),False)
  m.box('toe_cap',(.55,-.4,.46),(.88,.4,.5),(.87,.86,.79),False)
 elif kind=='tablet':
  m.box('tablet_body',(-1,-1,-1),(1,1,1),(.28,.3,.33))
  m.box('front_screen',(-.91,-.91,-1.001),(.91,.91,-1),(.025,.035,.05),False)
  m.box('rear_camera_island',(.65,-.86,1),(.91,-.5,1.07),DARK)
  m.disk('rear_lens',.08,.08,1.07,1.09,(.05,.14,.2),.78,-.69,16,False)
 elif kind=='airplane':
  m.prism('fuselage',[(-1,-.12),(.55,-.15),(1,0),(.55,.15),(-1,.12)],-1,.4,color)
  m.prism('left_wing',[(-.45,0),(-.6,1),(.15,1),(.4,0)],-1,-.3,color)
  m.prism('right_wing',[(-.45,0),(.4,0),(.15,-1),(-.6,-1)],-1,-.3,color)
  m.box('tailplane',(-.92,-.5,-1),(-.7,.5,-.4),color)
  m.box('cockpit',(.22,-.1,.4),(.55,.1,1),(.15,.2,.25))
 elif kind=='car':
  m.box('stable_chassis',(-1,-.85,-1),(1,.85,-.5),DARK)
  m.prism('car_body',[(-1,-1),(.85,-1),(1,-.75),(1,.75),(.85,1),(-1,1)],-.5,.3,color)
  m.box('cabin',(-.55,-.75,.3),(.35,.75,1),color)
  m.box('front_windshield',(.35,-.68,.4),(.355,.68,.9),(.06,.17,.25),False)
  for y in [-.8,.5]:m.box('headlight_'+str(y).replace('-','m').replace('.','p'),(.996,y,-.1),(1,y+.3,.15),(.95,.91,.48),False)
 elif kind in ('square_pastry','triangle_pastry'):
  poly=[(-1,-1),(1,-1),(1,1),(-1,1)] if kind.startswith('square') else [(-1,-1),(1,-1),(0,1)]
  m.prism('biscuit_base',poly,-1,.4,(.67,.37,.12));m.prism('frosting',[(x*.94,y*.94) for x,y in poly],.4,1,color)
 elif kind in ('apple','pear'):
  rings=[(-1,.5),(-.8,.85),(-.3,1),(.3,.95),(.7,.7),(.85,.35)] if kind=='apple' else [(-1,.5),(-.75,.9),(-.3,1),(.2,.7),(.65,.35),(.87,.24)]
  m.lathe(kind,rings,color);m.box('stem',(-.055,-.055,.85),(.055,.055,1),(.27,.12,.035))
 elif kind=='jar':
  m.lathe('blue_jar',[(-1,.8),(-.9,1),(.7,1),(.85,.8)],color);m.disk('lid',.9,.9,.85,1,(.03,.08,.25))
  m.box('jar_label',(-.45,-1.001,-.45),(.45,-1,.35),(.79,.88,.96),False)
 elif kind=='candle':
  m.disk('flat_candle',1,1,-1,.9,color);m.disk('wick',.035,.035,.9,1,DARK,n=12)
 elif kind=='yarn':
  m.lathe('rigid_yarn_ball',[(-1,.22),(-.8,.62),(-.35,.93),(0,1),(.35,.93),(.8,.62),(1,.22)],color)
  # Concentric visible wound strands; these are rigid geometry, not soft yarn.
  for i in range(9):
   z=-.72+i*.18;r=math.sqrt(max(.05,1-z*z));m.ring(f'winding_{i}',r*.985,r*1.01,z-.018,z+.018,tuple(min(1,c+.15) for c in color),32)
 elif kind in ('spoon','fork','knife'):
  m.prism('scalloped_wood_handle',[(-1,-.35),(-.84,-.48),(-.28,-.35),(-.15,-.2),(-.15,.2),(-.28,.35),(-.84,.48),(-1,.35)],-1,.5,(.36,.16,.06))
  for x in [-.8,-.55]:m.disk('rivet_'+str(x).replace('-','m').replace('.','p'),.045,.09,.5,.52,SILVER,cx=x,n=12,collision=False)
  m.box('neck',(-.2,-.13,-.4),(.4,.13,.25),SILVER)
  if kind=='knife':m.prism('blade',[(.1,-.1),(1,-.3),(.95,.6),(.2,1)],-.2,1,SILVER)
  elif kind=='fork':
   m.box('fork_base',(.2,-1,-.1),(.55,1,.5),SILVER)
   for i in range(4):m.box(f'tine_{i}',(.55,-1+i*.58,-.1),(1,-.75+i*.58,1),SILVER)
  else:
   m.disk('spoon_bowl_outer',.4,1,-.1,.4,SILVER,cx=.6)
   m.disk('spoon_bowl_inset',.31,.79,.401,.402,(.36,.4,.44),cx=.6,collision=False)
   # Slight upturned rim gives the bowl an identifiable working end.
   m.box('bowl_tip',(.95,-.25,.4),(1,.25,1),SILVER)
 elif kind=='spool':
  # Units use outer radius1; hole ratio .24 -> 4.8 mm at20mmouter.
  m.ring('lower_flange',.24,1,-1,-.55,color)
  m.ring('thread_core',.24,.76,-.55,.55,tuple(min(1,c+.1) for c in color))
  m.ring('upper_flange',.24,1,.55,1,color)
 elif kind=='arrow':
  m.box('arrow_shaft',(-1,-.38,-1),(.25,.38,1),color)
  m.prism('arrow_head',[(.1,-1),(1,0),(.1,1)],-1,1,color)
 elif kind in ('ticket_red','ticket_black'):
  m.box('thin_ticket',(-1,-1,-1),(1,1,1),(.86,.82,.69))
  m.parts[-1]['hidden']=True # Exact full-thickness collider, no rendered coplanar shell.
  shell=Meshes();shell.box('ticket_edges',(-1,-1,-1),(1,1,1),PAPER,False)
  shell.parts[0]['faces']=shell.parts[0]['faces'][2:] # Render only four edge faces.
  m.parts.extend(shell.parts)
  # Partition the front into nonoverlapping cells; no depth bias or thicker card.
  xs=[-1,-.56,.56,1];ys=[-1,-.6,.6,1]
  motif=COLORS['red'] if kind.endswith('red') else DARK
  for i in range(3):
   for j in range(3):
    name='front_motif' if (i,j)==(1,1) else f'front_border_{i}_{j}'
    m.mesh(name,[(xs[i],ys[j],1),(xs[i+1],ys[j],1),(xs[i+1],ys[j+1],1),(xs[i],ys[j+1],1)],[[0,1,2,3]],motif if (i,j)==(1,1) else PAPER,False)
  m.mesh('uniform_back',[(-1,-1,-1),(-1,1,-1),(1,1,-1),(1,-1,-1)],[[0,1,2,3]],(.17,.28,.38),False)
 else:raise ValueError(kind)
 return m

TASK_KINDS={
'E01':{'burger':'burger','fries':'fries','drink':'drink'},
'E08':{'left_shoe':'left_shoe','right_shoe':'right_shoe'},'E13':{'phone':'tablet'},
'E25':{'spoon':'spoon','knife':'knife','fork':'fork'},'E27':{'spoon':'spoon','fork':'fork'},'E34':{'spoon':'spoon','knife':'knife','fork':'fork'}}
def replacements(task,objects):
 if task in TASK_KINDS:return TASK_KINDS[task]
 if task=='E02':return {k:'soap' for k in objects}
 if task in ('E14','E35'):return {k:'book' for k in objects}
 if task=='E15':return {k:'airplane' for k in objects}
 if task=='E16':return {k:'car' for k in objects if k!='tray'}
 if task=='E17':return {k:'triangle_pastry' if 'triangle' in k else 'square_pastry' for k in objects if k!='stand'}
 if task in ('E18','E22'):return {k:('apple' if 'red' in k else 'pear' if 'green' in k else 'jar') for k in objects if k in ('red','green','blue','red_block','green_block','blue_block')}
 if task=='E21':return {k:'candle' for k in objects if k!='tray'}
 if task=='E24':return {k:'yarn' for k in ('red','green','blue')}
 if task=='E38':return {k:'spool' for k in ('red','green','blue')}
 if task=='E39':return {k:'arrow' for k in objects}
 if task=='E47':return {f'card{i}':'ticket_red' if i in (1,3,5) else 'ticket_black' for i in range(1,6)}
 if task=='E30':return {}
 raise ValueError(task)

def cabinet(base,out,assets_root):
 old=base['mechanisms'][0]['mechanical_asset'];source=assets_root/old['relative_path']
 if sha(source)!=old['sha256']:raise ValueError('Cabinet source SHA mismatch')
 text=source.read_text(); dependencies=[]
 targetdir=out/'assets/g1/E30';targetdir.mkdir(parents=True,exist_ok=True)
 # Flat source USD retains all original joint/rigid/collision content verbatim.
 # Add an inset raised frame to the stationary cabinet's visual layer only;
 # interior, drawer pull, contact shapes, joint friction and travel stay exact.
 # Source body frame maps (x,y,z)->(-z,-x,y)+[0,0,.1301279656].
 decorations=Meshes()
 for y in [-.063,.063]:
  decorations.box('side_frame_'+str(y).replace('-','m').replace('.','p'),(-.066,y-.002,.006),(.061,y+.002,.168),(.23,.29,.31),False)
 decorations.box('top_frame',(-.066,-.065,.165),(.061,.065,.169),(.23,.29,.31),False)
 # Fixed body link0 uses inherited rotation. Convert asset coordinates to body.
 for p in decorations.parts:p['points']=[(-y,z-.13012796561431736,-x) for x,y,z in p['points']]
 meshtext=decorations.text();body=meshtext[meshtext.index('def Xform "Asset" {')+len('def Xform "Asset" {'):].rsplit('}',1)[0]
 body=body.replace('/Asset/','/Asset/Links/link_0/')
 # Insert directly into link0; no rigid root or new collision is introduced.
 start=text.index('def Xform "link_0"');start=text.index('{',start)+1
 text=text[:start]+body+text[start:]
 # Refinish base white/plastic tones, preserving top-red/bottom-blue authoredpanels.
 text=text.replace('color3f inputs:diffuseColor = (1, 1, 1)','color3f inputs:diffuseColor = (0.76, 0.81, 0.78)')
 # Resolve every source dependency with a pinned copy. References remain relative.
 for dep in old.get('dependencies',[]):
  src=assets_root/dep['relative_path']
  if sha(src)!=dep['sha256']:raise ValueError(f'Cabinet dependency mismatch {src}')
  dest=targetdir/dep['relative_path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
  dependencies.append({'relative_path':'g1/E30/'+dep['relative_path'],'sha256':sha(dest)})
 dest=targetdir/'cabinet_g1_frame.usda';dest.write_text(text)
 new=copy.deepcopy(old);new.update(root_env='VIC_INFERENCE_ASSETS',relative_path='g1/E30/'+dest.name,sha256=sha(dest),dependencies=dependencies)
 new.pop('path',None);new['id']='cabinet_g1_frame';new['source_modified']=True
 new['inference_adaptation']='New framed cabinet visual instance; original collision, joints, handles, friction and travel retained byte-for-byte.'
 base['mechanisms'][0]['mechanical_asset']=new
 return {'task':'E30','asset':new['relative_path'],'sha256':new['sha256'],'original_sha256':old['sha256'],'kind':'framed_two_tier_cabinet','physics':'retained_source_joint_and_collision_definitions','native_verified':False}

def bind_shoe_containment(obj, mesh):
 """Use every authored mesh vertex, including trim, in the loaded local frame.

 Each collision component is convexHull: its extrema are attained at these
 vertices. The box cavity is convex too, so vertex inclusion is sufficient;
 unlike a bounding-box test it does not invent empty shoe corners.
 """
 if obj['source_asset']['source_rotation'] != [1,0,0,0]:
  raise ValueError('Generated shoe containment requires identity source rotation')
 # Match the 12-significant-digit USD serialization exactly.
 points=sorted({tuple(float(f'{v:.12g}') for v in point)
                for part in mesh.parts for point in part['points']})
 obj['containment_points_local']=[list(p) for p in points]
 obj['containment_points_source_sha256']=obj['source_asset']['sha256']
 obj['containment_points_method']='all_authored_mesh_vertices_loaded_body_local_v1'

def build(basepath=BASE,out=OUT):
 original=json.loads(Path(basepath).read_text());tasks={};provenance=[]
 for task in G1:
  b=copy.deepcopy(original['tasks'][task]);tasks[task]=b
  for oid,kind in replacements(task,b['objects']).items():
   obj=b['objects'][oid];old=copy.deepcopy(obj.get('source_asset',obj.get('mechanical_asset')))
   # Only envelope changes approved for required rectangular soap/book shapes.
   # Base XY/bottom/pose and goal semantics stay untouched.
   if task=='E02':obj['size']=[obj['size'][0],obj['size'][1]*.8,obj['size'][2]]
   if task=='E35':obj['size']=[obj['size'][0],obj['size'][1]*.75,obj['size'][2]*.3]
   col=color_for(oid)
   if task=='E35':col=(.2,.32,.58) # same design and colour at all three scales
   m=shape(kind,col);m.normalize(obj['size'])
   p=out/'assets/g1'/task/f'{oid}.usda';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(m.text())
   obj.pop('mechanical_asset',None)
   for k in ['recolor','rgba','reviewed_collision_settings','adaptation_note']:obj.pop(k,None)
   obj['source_asset']={'root_env':'VIC_INFERENCE_ASSETS','relative_path':f'g1/{task}/{oid}.usda','sha256':sha(p),'dependencies':[],'source_rotation':[1,0,0,0]}
   if task=='E08':bind_shoe_containment(obj,m)
   provenance.append({'task':task,'object':oid,'kind':kind,'original_source':old,'asset':f'g1/{task}/{oid}.usda','sha256':sha(p),'half_extents':obj['size'],'parts':len(m.parts),'collision_parts':sum(x['collision'] for x in m.parts),'physics':'new_compound_convex_geometry_base_mass_friction_pose_retained','size_adaptation':('rectangular_soap_y_0.8' if task=='E02' else 'uniform_book_y_0.75_z_0.3' if task=='E35' else 'base_envelope_retained'),'native_verified':False})
  if task=='E08':
   for variant in b['variants'].values():variant['semantic']['source_acceptance_geometry']='E08-source-geometry-v1'
  if task=='E30':provenance.append(cabinet(b,out,ROOT.parent/'deployment/real-text300-20261030/asset_roots/VIC_MECHANISM_ASSETS'))
 patch={'schema':'videoicl-inference-g1-patch-v1','base_sha256':sha(basepath),'tasks':tasks}
 (out/'g1-bindings-patch.json').write_text(json.dumps(patch,indent=2,ensure_ascii=False)+'\n')
 (out/'g1-asset-provenance.json').write_text(json.dumps({'schema':'videoicl-g1-asset-provenance-v1','generator':str(Path(__file__).relative_to(ROOT)),'generator_sha256':sha(__file__),'policy':'Inference-only assets; G0, environment, demo and ABC goal semantics unchanged. Native physics acceptance is separate, never inferred from mesh generation.','assets':provenance},indent=2)+'\n')
 return patch,provenance
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,default=BASE);p.add_argument('--out',type=Path,default=OUT);a=p.parse_args();patch,prov=build(a.base,a.out);print(json.dumps({'tasks':len(patch['tasks']),'replacement_assets':len(prov),'out':str(a.out)}))
