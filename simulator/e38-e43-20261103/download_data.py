"""Download the pinned HF delivery and install assets without replacing GitHub code."""
from pathlib import Path
import json,os,shutil,tarfile,hashlib
from huggingface_hub import snapshot_download
ROOT=Path(__file__).resolve().parent
cfg=json.loads((ROOT/'DATA.json').read_bytes())
cache=ROOT/'.data-cache';cache.mkdir(exist_ok=True)
snapshot=Path(snapshot_download(cfg['repo_id'],repo_type=cfg['repo_type'],revision=cfg['revision'],
    allow_patterns=[cfg['prefix']+'/*'],local_dir=str(cache/'download'),max_workers=8,
    token=os.environ.get('HF_TOKEN')or None))
folder=snapshot/cfg['prefix'];parts=json.loads((folder/'PARTS.json').read_bytes())
archive=cache/parts['archive'];digest=hashlib.sha256()
with archive.open('wb')as out:
 for row in parts['parts']:
  with(folder/row['path']).open('rb')as f:
   for block in iter(lambda:f.read(1024*1024),b''):
    out.write(block);digest.update(block)
if digest.hexdigest()!=cfg['archive_sha256']:raise ValueError('Incomplete/corrupt delivery download')
unpacked=cache/'unpacked';unpacked.mkdir(exist_ok=True)
with tarfile.open(archive,'r:gz')as t:t.extractall(unpacked,filter='data')
bundle=unpacked/parts['archive'].removesuffix('.tar.gz')
for rel in('asset_roots','robot','runtime/execution-design-v3/assets',
           'runtime/configs/source_geometry','runtime/engineering-vendor'):
 if(bundle/rel).is_dir():shutil.copytree(bundle/rel,ROOT/rel,dirs_exist_ok=True)
for rel in('evaluator','evidence'):
 if(bundle/rel).is_dir():shutil.copytree(bundle/rel,ROOT/'private_data'/rel,dirs_exist_ok=True)
print('Assets ready. Task instructions: docs/TASKS.md; run: python run.py --help')
