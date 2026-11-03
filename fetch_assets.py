#!/usr/bin/env python3
"""Restore the complete HF data bundle; authentication uses HF_TOKEN/local login."""
from pathlib import Path,PurePosixPath
from concurrent.futures import ThreadPoolExecutor
import argparse,json,shutil,tarfile,os
from huggingface_hub import hf_hub_download
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--g2-only',action='store_true',help='Restore only original ten UR5 tasks from the complete bundle')
p.add_argument('--workers',type=int,default=16)
a=p.parse_args()
config=json.loads((ROOT/'embodied/ARTIFACTS.json').read_text());repo=config['repo_id'];revision=config.get('revision','main')
manifest_path=hf_hub_download(repo,filename='BUNDLE_MANIFEST.json',repo_type='dataset',revision=revision)
manifest=json.loads(Path(manifest_path).read_text());parts=manifest['parts']
def download(row):
 return Path(hf_hub_download(repo,filename=row['path'],repo_type='dataset',revision=revision))
with ThreadPoolExecutor(max_workers=a.workers)as pool:paths=list(pool.map(download,parts))
work=ROOT/'.local/handoff-download';work.mkdir(parents=True,exist_ok=True)
archive=work/'data.tar.gz'
with archive.open('wb')as dst:
 for path in paths:
  with path.open('rb')as src:shutil.copyfileobj(src,dst,1024*1024)
destination=(ROOT/'embodied').resolve();count=0
with tarfile.open(archive,'r|gz')as tf:
 for member in tf:
  name=PurePosixPath(member.name)
  if name.is_absolute()or '..'in name.parts:raise ValueError('Unsafe archive member')
  if a.g2_only and name.parts[0]!='g2-ur5-v1':continue
  if not member.isfile():continue
  target=destination/str(name);target.parent.mkdir(parents=True,exist_ok=True)
  # Keep the GitHub entrypoint/docs version while restoring all missing data.
  if target.exists()and target.suffix in ('.py','.md','.sh','.toml','.html','.js','.css'):continue
  temporary=target.with_name(target.name+'.download-partial')
  with tf.extractfile(member)as src,temporary.open('wb')as dst:shutil.copyfileobj(src,dst,1024*1024)
  os.replace(temporary,target);count+=1
archive.unlink()
print('Restored '+str(count)+' data files into '+str(destination))
