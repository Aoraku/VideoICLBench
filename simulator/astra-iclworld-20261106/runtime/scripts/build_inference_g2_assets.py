#!/usr/bin/env python3
"""Build deterministic, self-contained G2 replacement meshes; never touch demos.

Photo inputs are pinned upstream scikit-image sample photographs. All other
meshes/materials are authored here. Outputs preserve native object identities.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'configs/initial-admission-e13-e25-20261030/e13-hframe-v2-bindings.candidate.json'
OUT = ROOT / 'inference-generalization-v1'
TASKS = ('E04','E05','E06','E07','E09','E11','E20','E36','E41','E49')
PHOTOS = ('astronaut.png','camera.png','coins.png','moon.png','hubble_deep_field.jpg')
COLORS = {'red':(.77,.035,.025),'green':(.2,.55,.055),'blue':(.025,.18,.75),'yellow':(.95,.7,.035)}

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def tup(v): return '('+', '.join(format(float(x),'.10g') for x in v)+')'

class Model:
    def __init__(self): self.parts=[]
    def mesh(self,name,points,faces,color,collision=False,texture=None):
        self.parts.append(dict(name=name,points=[list(p) for p in points],faces=faces,color=color,collision=collision,texture=texture,invisible=False))
    def box(self,name,half,color,center=(0,0,0),collision=False):
        a,b,c=half; x,y,z=center
        pts=[(x+i*a,y+j*b,z+k*c) for k in (-1,1) for j in (-1,1) for i in (-1,1)]
        self.mesh(name,pts,[[0,2,3,1],[4,5,7,6],[0,1,5,4],[2,6,7,3],[0,4,6,2],[1,3,7,5]],color,collision)
    def lathe(self,name,profile,color,collision=False,n=40,lobes=0,center=(0,0,0)):
        # Closed rings with explicit end caps; no degenerate pole vertices.
        pts=[]
        for z,r in profile:
            for i in range(n):
                t=2*math.pi*i/n; rr=r*(1+lobes*math.cos(5*t))
                pts.append((center[0]+rr*math.cos(t),center[1]+rr*math.sin(t),center[2]+z))
        faces=[list(reversed(range(n)))]
        for k in range(len(profile)-1):
            for i in range(n):
                j=(i+1)%n;faces.append([k*n+i,k*n+j,(k+1)*n+j,(k+1)*n+i])
        faces.append(list(range((len(profile)-1)*n,len(profile)*n)))
        self.mesh(name,pts,faces,color,collision)
    def prism(self,name,n,lo,hi,color,collision=False,radius=1):
        if n==4: xy=[(-1,-1),(1,-1),(1,1),(-1,1)]
        else: xy=[(radius*math.cos(2*math.pi*i/n+math.pi/2),radius*math.sin(2*math.pi*i/n+math.pi/2)) for i in range(n)]
        pts=[(x,y,z) for z in (lo,hi) for x,y in xy]; count=len(xy)
        faces=[list(reversed(range(count))),list(range(count,2*count))]
        faces += [[i,(i+1)%count,(i+1)%count+count,i+count] for i in range(count)]
        self.mesh(name,pts,faces,color,collision)
    def write(self,path,half):
        # Author exact requested bounds, avoiding accidental uniform-scale rejection.
        low=[min(p[j] for v in self.parts for p in v['points']) for j in range(3)]
        high=[max(p[j] for v in self.parts for p in v['points']) for j in range(3)]
        for v in self.parts:
            v['points']=[[(p[j]-(low[j]+high[j])/2)*2*half[j]/(high[j]-low[j]) for j in range(3)] for p in v['points']]
        out=['#usda 1.0','(defaultPrim = "Asset"\n metersPerUnit = 1\n upAxis = "Z")','def Xform "Asset" {']
        for i,v in enumerate(self.parts):
            name=v['name'];mat=f'Mat{i}'
            api='prepend apiSchemas = ["PhysicsCollisionAPI", "PhysicsMeshCollisionAPI", "MaterialBindingAPI"]' if v['collision'] else 'prepend apiSchemas = ["MaterialBindingAPI"]'
            out += [f' def Mesh "{name}" ({api}) {{', '  point3f[] points = ['+', '.join(tup(p) for p in v['points'])+']',
                '  int[] faceVertexCounts = '+str([len(f) for f in v['faces']]), '  int[] faceVertexIndices = '+str([k for f in v['faces'] for k in f]),
                '  uniform token subdivisionScheme = "none"', '  bool doubleSided = true',f'  rel material:binding = </Asset/{mat}>']
            if v['collision']:out += ['  bool physics:collisionEnabled = true','  uniform token physics:approximation = "convexHull"']
            if v['invisible']:out += ['  token visibility = "invisible"']
            if v['texture']:out += ['  texCoord2f[] primvars:st = [(0,0),(1,0),(1,1),(0,1)] (interpolation = "vertex")']
            out += [' }',f' def Material "{mat}" {{',f'  token outputs:surface.connect = </Asset/{mat}/Surface.outputs:surface>', '  def Shader "Surface" {', '   uniform token info:id = "UsdPreviewSurface"',f'   color3f inputs:diffuseColor = {tup(v["color"])}','   float inputs:roughness = 0.65','   token outputs:surface']
            if v['texture']:out += [f'   color3f inputs:diffuseColor.connect = </Asset/{mat}/Texture.outputs:rgb>']
            out += ['  }']
            if v['texture']:out += ['  def Shader "UV" {','   uniform token info:id = "UsdPrimvarReader_float2"','   token inputs:varname = "st"','   float2 outputs:result','  }','  def Shader "Texture" {','   uniform token info:id = "UsdUVTexture"',f'   asset inputs:file = @{v["texture"]}@',f'   float2 inputs:st.connect = </Asset/{mat}/UV.outputs:result>','   token inputs:sourceColorSpace = "sRGB"','   float3 outputs:rgb','  }']
            out += [' }']
        out += ['}'];path.write_text('\n'.join(out)+'\n')

def fruit(kind,color):
    m=Model()
    if kind=='pear': profile=[(-1,.3),(-.85,.68),(-.5,1),(-.1,.88),(.3,.54),(.7,.32),(.86,.21)];lobes=.018
    elif kind=='lemon': profile=[(-1,.09),(-.85,.4),(-.5,.78),(0,1),(.5,.78),(.85,.4),(1,.09)];lobes=0
    else: profile=[(-1,.32),(-.87,.64),(-.6,.91),(-.2,1),(.25,.99),(.65,.85),(.83,.56),(.88,.24)];lobes=.045 if kind=='apple' else .012
    m.lathe('FruitCollision',profile,color,True,lobes=lobes)
    if kind!='lemon':
        m.lathe('Stem',[(.83,.065),(1,.045)],(.19,.085,.025),n=12)
        m.mesh('Leaf',[(.03,0,.94),(.28,-.1,.93),(.42,.03,.88),(.19,.12,.93)],[[0,1,2,3]],(.12,.3,.035))
    # Citrus pores are shallow, visible dimples in the surface, not new handles.
    if kind in ('orange','tangerine'):
        for i in range(14):
            t=2*math.pi*i/14;z=.35*math.sin(i*2.3);r=.995
            m.lathe('Pore'+str(i),[(-.015,.018),(.015,.018)],(.79,.32,.01),n=6,center=(r*math.cos(t),r*math.sin(t),z))
    return m

def prop(kind,color,photo=None):
    if kind in ('apple','pear','orange','tangerine','lemon'):return fruit(kind,color)
    m=Model()
    if kind=='jar':
        m.lathe('JarCollision',[(-1,.87),(-.9,1),(.64,1),(.77,.88),(.94,.88)],color,True)
        m.lathe('Lid',[(.77,.94),(1,.94)],(.035,.13,.43));m.lathe('LidRim',[(.78,.99),(.85,.99)],(.1,.28,.78))
    elif kind=='gift':
        m.box('GiftCollision',(1,1,1),(.62,.36,.13),collision=True)
        m.box('RibbonX',(1.001,.13,.006),(.93,.78,.15),center=(0,0,1))
        m.box('RibbonY',(.13,1.001,.007),(.93,.78,.15),center=(0,0,1))
        m.box('RibbonFront',(.13,.006,1),(.93,.78,.15),center=(0,-1,0))
    elif kind=='pastry':
        m.prism('PastryCollision',3,-1,1,(.7,.37,.13),True)
        m.prism('Cream',3,.65,1.001,(.95,.84,.57),radius=.96)
    elif kind.startswith('cookie_'):
        n={'circle':48,'square':4,'triangle':3}[kind[7:]]
        m.prism('BiscuitCollision',n,-1,.55,(.69,.39,.14),True)
        m.prism('Icing',n,.54,1,color,radius=.94)
        # Square icing inset is manually applied (prism square ignores radius).
        if n==4:
            for p in m.parts[-1]['points']:p[0]*=.94;p[1]*=.94
    elif kind=='matryoshka':
        m.lathe('DollCollision',[(-1,.62),(-.88,.86),(-.5,1),(-.1,.84),(.23,.58),(.4,.54),(.68,.5),(.9,.34),(1,.1)],(.65,.065,.07),True)
        # Identical closed shell, painted head and apron; all sizes share this mesh.
        m.mesh('Face',[(-.31,-.47,.45),(.31,-.47,.45),(.29,-.34,.84),(-.29,-.34,.84)],[[0,1,2,3]],(.97,.76,.51))
        m.mesh('Apron',[(-.55,-.78,-.73),(.55,-.78,-.73),(.42,-.79,-.14),(-.42,-.79,-.14)],[[0,1,2,3]],(.92,.68,.2))
        for x in (-.14,.14):m.box('Eye'+('L' if x<0 else 'R'),(.035,.008,.035),(.07,.035,.025),(x,-.445,.65))
    elif kind=='button':
        # Four genuine visual through-holes; convex contact disk retained because
        # E20 uses stacking/placement and never threads the holes.
        n=48;grid=40;pts=[];faces=[];holes=[(x,y) for x in (-.27,.27) for y in (-.27,.27)]
        for iy in range(grid):
            for ix in range(grid):
                x=-1+2*(ix+.5)/grid;y=-1+2*(iy+.5)/grid
                if x*x+y*y>.97**2 or any((x-a)**2+(y-b)**2<.13**2 for a,b in holes):continue
                k=len(pts);r=1/grid
                pts += [(x-r,y-r,-1),(x+r,y-r,-1),(x+r,y+r,-1),(x-r,y+r,-1),(x-r,y-r,1),(x+r,y-r,1),(x+r,y+r,1),(x-r,y+r,1)]
                faces += [[k+i for i in f] for f in ([0,3,2,1],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7])]
        m.mesh('ButtonCollision',pts,faces,color,True)
    elif kind=='eraser':
        m.box('RubberCollision',(1,1,1),(.86,.57,.5),collision=True)
        m.box('PaperBand',(.42,1.001,1.001),(.79,.84,.72))
        m.box('BandStripe',(.07,1.002,.006),(.13,.35,.25),center=(0,0,1.002))
    elif kind=='photo':
        # Original .35mm contact body. Render surfaces never overlap: an
        # invisible closed collider, side/back shell, and exact +Z photograph.
        m.box('CardCollision',(1,1,1),(.08,.13,.19),collision=True)
        m.parts[-1]['invisible']=True
        m.box('CardBackAndEdges',(1,1,1),(.08,.13,.19))
        m.parts[-1]['faces'].pop(1) # Remove +Z face; photograph owns this plane.
        m.mesh('PhotoFront',[(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)],[[0,1,2,3]],(1,1,1),texture=photo)
    else:raise ValueError(kind)
    return m

def replacements(task,objects):
    for name,obj in objects.items():
        kind=None;color=tuple(obj.get('rgba',(0.8,0.5,0.2,1))[:3]);photo=None
        if task=='E04' and name.endswith('_cup'):
            c=name.split('_')[0];kind={'red':'apple','green':'pear','blue':'jar'}[c];color=COLORS[c]
        elif task=='E05' and name in ('cube','sphere','triangle'):
            kind={'cube':'gift','sphere':'orange','triangle':'pastry'}[name];color=(.95,.37,.025)
        elif task=='E06' and name in ('purple','pink','lightpink'):kind='tangerine';color=(.96,.39,.02)
        elif task=='E07' and name.startswith('block'):kind='matryoshka'
        elif task=='E09' and '_' in name:
            c,shape=name.split('_',1)
            if c in COLORS and shape in ('circle','square','triangle'):kind='cookie_'+shape;color=COLORS[c]
        elif task=='E11' and name.endswith('_block'):
            kind={'red_block':'apple','blue_block':'orange','yellow_block':'lemon','green_block':'pear'}[name]
            color={'apple':COLORS['red'],'orange':(.95,.37,.02),'lemon':(.93,.79,.015),'pear':COLORS['green']}[kind]
        elif task=='E20' and ('_supply_' in name or name in ('yellow_initial','blue_initial')):kind='button';color=COLORS[name.split('_')[0]]
        elif task=='E36' and name in ('red','pink','lightpink','blue'):kind='apple';color=COLORS['red']
        elif task=='E41' and (name.endswith('_ref') or name.endswith('_piece')):kind='eraser'
        elif task=='E49' and name.startswith('card'):kind='photo';photo=PHOTOS[int(name[4:])-1]
        if kind:yield name,obj,kind,color,photo

def build(base=BASE,out=OUT):
    tasks=json.loads(base.read_text())['tasks'];assets=out/'assets/g2';assets.mkdir(parents=True,exist_ok=True)
    patch={'schema':'videoicl.inference-object-patch.v1','group':'G2','tasks':{}}
    provenance={'schema':'videoicl.g2-assets.v1','base_sha256':sha(base),'authorship':'Procedural rigid meshes from build_inference_g2_assets.py; no demo modifications.','tasks':{},'photos':[]}
    for photo in PHOTOS:
        p=assets/'photo_sources'/photo
        if not p.is_file():raise FileNotFoundError('Pinned upstream photo missing: '+str(p))
        provenance['photos'].append({'path':'g2/photo_sources/'+photo,'sha256':sha(p),'upstream_url':'https://raw.githubusercontent.com/scikit-image/scikit-image/v0.19.3/skimage/data/'+photo})
    for task in TASKS:
        binding=copy.deepcopy(tasks[task]);changed=[]
        for name,obj,kind,color,photo in replacements(task,binding['objects']):
            old=copy.deepcopy(obj);half=list(obj['size'])
            if task=='E11':
                half[2]=.02
                if 'center_z' in obj:obj['center_z']+=half[2]-obj['size'][2]
                obj['size']=half
            filename=f'{task}_{name}.usda';path=assets/filename
            model=prop(kind,color,'photo_sources/'+photo if photo else None);model.write(path,half)
            obj.pop('mechanical_asset',None);obj.pop('reviewed_collision_settings',None)
            obj['source_asset']={'root_env':'VIC_INFERENCE_ASSETS','relative_path':'g2/'+filename,'sha256':sha(path),'source_rotation':[1,0,0,0]}
            if photo:obj['source_asset']['dependencies']=[{'relative_path':'g2/photo_sources/'+photo,'sha256':sha(assets/'photo_sources'/photo)}]
            obj['recolor']=False
            obj['inference_object']={'group':'G2','category':kind,'legacy_identity':name}
            if task=='E49':
                obj['identity_attributes']['source_face']='photograph_'+photo
                obj['identity_attributes']['photograph']=photo
            changed.append({'id':name,'category':kind,'original_source':old.get('source_asset',old.get('mechanical_asset')),'asset':obj['source_asset'],'original_half_extents':old['size'],'half_extents':half,'collision':'closed convex rigid hull','native_validation':'pending'})
        binding['fidelity_status']='inference_G2_authored_category_replacements_native_validation_pending'
        patch['tasks'][task]=binding;provenance['tasks'][task]=changed
    (out/'g2-bindings-patch.json').write_text(json.dumps(patch,ensure_ascii=False,indent=2)+'\n')
    (assets/'provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n')
    return patch,provenance

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base',type=Path,default=BASE);parser.add_argument('--out',type=Path,default=OUT)
    args=parser.parse_args();p,v=build(args.base,args.out)
    print(json.dumps({'tasks':len(p['tasks']),'replaced_objects':sum(map(len,v['tasks'].values())),'output':str(args.out)}))
