"""Author engineering check through tokens; never an independent agent result."""
import argparse
import base64
import io
import json
import imageio_ffmpeg
import numpy as np
from PIL import Image
from pathlib import Path
from .environment import DesktopDual
from .catalog import task_spec

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('.local/cup-token-probe.json'));p.add_argument('--record',type=Path);a=p.parse_args()
    e=DesktopDual(task_spec('rt12'),render=bool(a.record))
    writer=None
    if a.record:
        a.record.parent.mkdir(parents=True,exist_ok=True)
        writer=imageio_ffmpeg.write_frames(str(a.record),(512,384),fps=2.5,codec='libx264',pix_fmt_in='rgb24',pix_fmt_out='yuv420p');writer.send(None)
    rows=[]
    try:
        for token,n in [('BACK',3),('LEFT',2),('DOWN',8),('GRASP',3),('UP',5),('FWD',16),('LEFT',10),('DOWN',5),('RELEASE',3),('STILL',3)]:
            for _ in range(n):
                e.action(token,'STILL')
                if writer: writer.send(np.asarray(Image.open(io.BytesIO(base64.b64decode(e.images()['agentview'])))))
            rows.append(dict(token=token,count=n,eef=e._eef0_xpos.tolist(),cup=e.snapshot()['cup']['pos'].tolist(),grasp=e.snapshot()['cup']['grasp']))
        result=dict(kind='author-fixed-token-engineering-probe',independent_agent=False,task='rt12',rows=rows,score=e.score())
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))
    finally:
        if writer: writer.close()
        e.close()
if __name__=='__main__': main()
