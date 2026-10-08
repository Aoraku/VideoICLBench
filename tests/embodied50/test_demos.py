from simulator.benchmark.catalog import TASKS
import json
import sys
import imageio_ffmpeg
from simulator.benchmark import demos

def test_low_fps_video_import_includes_last_decodable_frame(tmp_path,monkeypatch):
    video=tmp_path/'input.mp4'
    writer=imageio_ffmpeg.write_frames(str(video),(32,32),fps=2.5,codec='libx264')
    writer.send(None)
    for i in range(5): writer.send(bytes([i*40,80,120])*32*32)
    writer.close()
    data=tmp_path/'data'
    monkeypatch.setattr(sys,'argv',['import','rt12','sim',str(video),'--author-verified','--data',str(data)])
    demos.main()
    root=data/'demos/rt12/sim'
    manifest=json.loads((root/'manifest.json').read_text())
    assert manifest['fps']==2.5
    assert manifest['task_revision']==TASKS['rt12']['task_revision']
    assert manifest['variant']=='A' and manifest['author_verified']
    assert len(list(root.glob('frame*.jpg')))==16
    assert len(manifest['video_sha256'])==64
