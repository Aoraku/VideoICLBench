#!/usr/bin/env python3
"""Download the complete handoff using HF access from HF_TOKEN or local login."""
from pathlib import Path
import argparse,json
from huggingface_hub import snapshot_download
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--g2-only',action='store_true',help='Only the original ten UR5 tasks')
p.add_argument('--workers',type=int,default=16)
a=p.parse_args()
config=json.loads((ROOT/'embodied/ARTIFACTS.json').read_text())
path=snapshot_download(repo_id=config['repo_id'],repo_type='dataset',revision=config.get('revision','main'),
 local_dir=ROOT/'embodied',max_workers=a.workers,allow_patterns=['g2-ur5-v1/**']if a.g2_only else None)
print('Assets downloaded into '+str(path))
