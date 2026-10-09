"""Import external, author-reviewed demonstrations. Never checks videos into git."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import imageio_ffmpeg
from .catalog import TASKS

def main():
    p=argparse.ArgumentParser()
    p.add_argument('task',choices=TASKS); p.add_argument('kind',choices=['human','sim'])
    p.add_argument('video',type=Path); p.add_argument('--author-verified',action='store_true',required=True)
    p.add_argument('--data',type=Path,default=Path(os.environ.get('EMBODIED_DATA','.local/embodied50-data')))
    a=p.parse_args(); video=a.video.resolve()
    # Human verification is an explicit author attestation, not automatic agent success.
    root=a.data/'demos'/a.task/a.kind
    if root.exists(): p.error('Demo already exists; use a new data directory to preserve provenance')
    root.parent.mkdir(parents=True,exist_ok=True)
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    reader=imageio_ffmpeg.read_frames(str(video)); meta=next(reader); reader.close()
    duration=meta['duration']
    last_timestamp=max(0.,duration-1/max(float(meta['fps']),1.)-.01)
    if duration<=0: p.error('Invalid video duration')
    with tempfile.TemporaryDirectory(dir=root.parent) as tmp:
        stage=Path(tmp)
        subprocess.run([ffmpeg,'-v','error','-i',str(video),'-an','-vf','scale=trunc(iw/2)*2:trunc(ih/2)*2','-c:v','libx264','-pix_fmt','yuv420p',str(stage/'video.mp4')],check=True)
        for i in range(16):
            subprocess.run([ffmpeg,'-v','error','-ss',str(last_timestamp*i/15),'-i',str(stage/'video.mp4'),'-frames:v','1','-vf','scale=640:-1',str(stage/f'frame{i:02d}.jpg')],check=True)
            if not (stage/f'frame{i:02d}.jpg').exists(): raise ValueError('Could not extract all 16 frames')
        m=dict(task=a.task,task_revision=TASKS[a.task].get('task_revision',1),kind=a.kind,variant='A',author_verified=True,duration=duration,
               source_sha256=hashlib.sha256(video.read_bytes()).hexdigest(),
               video_sha256=hashlib.sha256((stage/'video.mp4').read_bytes()).hexdigest(),
               frame_sampling='16 uniform timestamps from zero through last decodable frame',fps=meta['fps'],
               contains_private_goal_text=False)
        (stage/'manifest.json').write_text(json.dumps(m,indent=2))
        shutil.move(str(stage),str(root))
    print(root)
if __name__=='__main__': main()
