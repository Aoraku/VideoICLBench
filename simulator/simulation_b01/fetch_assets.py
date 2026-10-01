from pathlib import Path
import subprocess, xml.etree.ElementTree as ET, concurrent.futures, hashlib,json
root=Path(__file__).resolve().parent/'assets'/'franka_emika_panda'
root.mkdir(parents=True,exist_ok=True)
base='https://cdn.jsdelivr.net/gh/google-deepmind/mujoco_menagerie@main/franka_emika_panda/'
def get(name):
 p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
 if not p.exists():
  temp=p.with_suffix(p.suffix+'.part')
  subprocess.run(['curl','-fSL','--retry','2','--connect-timeout','15','--max-time','180','-s',base+name,'-o',str(temp)],check=True)
  temp.replace(p)
 return name
get('panda.xml');get('LICENSE')
tree=ET.parse(root/'panda.xml')
names=sorted(set('assets/'+m.attrib['file'] for m in tree.findall('.//mesh') if 'file' in m.attrib))
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
 for i,n in enumerate(ex.map(get,names)):print(i+1,len(names),n,flush=True)
(root/'download_manifest.json').write_text(json.dumps({'source':base,'files':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['panda.xml','LICENSE']+names}},indent=2))
