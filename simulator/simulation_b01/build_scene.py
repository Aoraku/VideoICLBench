from pathlib import Path
import xml.etree.ElementTree as E
import copy
P=Path(__file__).resolve().parent
src=E.parse(P/'assets/franka_emika_panda/panda.xml').getroot()
r=E.Element('mujoco',model='VideoICL_B01_dual_Panda')
E.SubElement(r,'compiler',angle='radian',meshdir=str(P/'assets/franka_emika_panda/assets'),autolimits='true')
E.SubElement(r,'option',timestep='0.002',integrator='implicitfast',iterations='100',noslip_iterations='10',gravity='0 0 -9.81')
E.SubElement(r,'size',njmax='5000',nconmax='1000')
v=E.SubElement(r,'visual');E.SubElement(v,'global',offwidth='1600',offheight='1000');E.SubElement(v,'quality',shadowsize='2048');E.SubElement(v,'headlight',diffuse='0.65 0.65 0.65',ambient='0.3 0.3 0.3',specular='0.2 0.2 0.2')
r.append(copy.deepcopy(src.find('default')))
a=copy.deepcopy(src.find('asset'));r.append(a)
E.SubElement(a,'texture',name='floor_tex',type='2d',builtin='checker',rgb1='.15 .19 .23',rgb2='.18 .22 .26',width='512',height='512')
E.SubElement(a,'material',name='floor_mat',texture='floor_tex',texrepeat='4 4',reflectance='.1')
w=E.SubElement(r,'worldbody')
E.SubElement(w,'light',pos='0 -1 2.5',dir='0 0 -1',diffuse='.8 .8 .8',castshadow='true')
E.SubElement(w,'geom',name='floor',type='plane',size='3 3 .1',pos='0 0 -.78',material='floor_mat')
E.SubElement(w,'geom',name='table',type='box',size='.67 .72 .04',pos='.08 0 -.04',rgba='.66 .56 .42 1',friction='1 .01 .001')
for x in [-.42,.58]:
 for y in [-.62,.62]:E.SubElement(w,'geom',type='box',size='.035 .035 .35',pos=f'{x} {y} -.43',rgba='.15 .18 .2 1')
# Flat, neutral target patch: visual only, not an attachment or invisible support.
E.SubElement(w,'geom',name='target_patch',type='cylinder',size='.073 .0002',pos='.16 0 .0003',rgba='.8 .83 .8 1',contype='0',conaffinity='0')
refs={'joint','joint1','joint2','body1','body2','tendon','site','target'}
containers={k:E.SubElement(r,k) for k in ['tendon','equality','actuator','contact']}
for prefix,y in [('left',.43),('right',-.43)]:
 def rename(el):
  for item in el.iter():
   for key in ['name']+list(refs):
    if key in item.attrib:item.set(key,prefix+'_'+item.get(key))
   if item.tag=='body':item.set('gravcomp','1')
  return el
 body=rename(copy.deepcopy(src.find('worldbody/body')));body.set('pos',f'-.43 {y} 0');w.append(body)
 hand=next(b for b in body.iter('body') if b.get('name')==prefix+'_hand')
 E.SubElement(hand,'site',name=prefix+'_tcp',pos='0 0 .1034',size='.003',rgba='0 0 0 0',group='5')
 for geom in body.iter('geom'):
  if geom.get('class','').startswith('fingertip'):geom.set('friction','1.8 .02 .001')
 for key in containers:
  for child in src.find(key):containers[key].append(rename(copy.deepcopy(child)))
for name,pos,color in [('red','-.02 .23 .021','.85 .08 .07 1'),('green','.08 -.24 .021','.05 .65 .3 1'),('blue','.28 .22 .021','.055 .24 .9 1')]:
 b=E.SubElement(w,'body',name=name,pos=pos);E.SubElement(b,'freejoint',name=name+'_free')
 E.SubElement(b,'geom',name=name+'_cube',type='box',size='.02 .02 .02',mass='.055',rgba=color,friction='1 .015 .002',condim='4',solref='.005 1',solimp='.95 .99 .001')
E.indent(r);E.ElementTree(r).write(P/'scene.xml',encoding='unicode')
print(P/'scene.xml')
