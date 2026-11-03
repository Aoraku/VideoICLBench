#!/usr/bin/env python3
"""Fetch the versioned asset package from the existing private HF dataset."""
from pathlib import Path
import argparse,hashlib,json,tarfile
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,help='Use an existing archive instead of downloading');p.add_argument('--destination',type=Path,default=ROOT);a=p.parse_args()
record=json.loads((ROOT/'asset-package.json').read_text())
if a.archive:archive=a.archive
else:
 from huggingface_hub import hf_hub_download
 from concurrent.futures import ThreadPoolExecutor
 records=record.get('parts')
 if records:
  def fetch(row):
   f=Path(hf_hub_download(record['dataset'],row['path'],repo_type='dataset',revision=record.get('revision')))
   if hashlib.sha256(f.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Asset part SHA256 mismatch')
   return f
  with ThreadPoolExecutor(max_workers=8)as pool:files=list(pool.map(fetch,records))
  archive=ROOT/'front13-assets-20261103-r1.tar.gz'
  with archive.open('wb')as output:
   for f in files:
    with f.open('rb')as stream:
     import shutil
     shutil.copyfileobj(stream,output)
 else:archive=Path(hf_hub_download(record['dataset'],record['path'],repo_type='dataset',revision=record.get('revision')))
if hashlib.sha256(archive.read_bytes()).hexdigest()!=record['sha256']:raise SystemExit('Asset package SHA256 mismatch')
target=a.destination.expanduser().resolve();target.mkdir(parents=True,exist_ok=True)
if(target/'front13-assets').exists():raise SystemExit('Destination front13-assets already exists; preserve it or choose another directory')
with tarfile.open(archive,'r:gz')as tar:
 for m in tar.getmembers():
  path=Path(m.name)
  if path.is_absolute()or'..'in path.parts or m.issym()or m.islnk():raise SystemExit('Unsafe archive member')
 tar.extractall(target,filter='data')
checks=json.loads((target/'front13-assets/asset-checksums.json').read_text())['files']
for name,row in checks.items():
 f=target/'front13-assets'/name
 if not f.is_file()or hashlib.sha256(f.read_bytes()).hexdigest()!=row['sha256']:raise SystemExit('Extracted asset mismatch: '+name)
print(json.dumps(dict(extracted_to=str(target/'front13-assets'),files_verified=len(checks))))
