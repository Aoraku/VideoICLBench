"""Authoring-only oracle. This module is never imported by the GUI server."""
import json
import shutil
import sys
from pathlib import Path
import numpy as np
import mujoco
import imageio.v2 as imageio

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'simulation_b01'))
from run_b01 import Demo

ORDERS={'A':('red','green','blue'),'B':('green','blue','red'),'C':('blue','red','green')}

def generate(variant,order):
    out=ROOT/'demos'/variant;out.mkdir(parents=True,exist_ok=True)
    path=out/'demo.mp4'
    if not path.exists():
        sim=Demo(False)
        sim.renderer=mujoco.Renderer(sim.m,height=720,width=1280)
        sim.cam=mujoco.MjvCamera();sim.cam.lookat[:]=[.01,0,.27]
        sim.cam.distance=1.85;sim.cam.azimuth=125;sim.cam.elevation=-33
        sim.detail_renderer=mujoco.Renderer(sim.m,height=288,width=384)
        sim.detail_cam=mujoco.MjvCamera();sim.detail_cam.lookat[:]=[.13,0,.055]
        sim.detail_cam.distance=.95;sim.detail_cam.azimuth=100;sim.detail_cam.elevation=-48
        sim.writer=imageio.get_writer(path,fps=25,codec='libx264',quality=8,macro_block_size=16)
        sim.video=True
        try:
            sim.step(500)
            for level,color in enumerate(order):
                sim.pick_place('right' if color=='green' else 'left',color,level)
            sim.step(1500)
            p=np.array([sim.d.body(c).xpos for c in order])
            if np.max(np.abs(p[:,2]-[.02,.06,.10]))>.006:
                raise RuntimeError('Demo authoring failed')
        finally:
            sim.writer.close();sim.renderer.close();sim.detail_renderer.close()
        (out/'authoring_events.json').write_text(json.dumps(sim.records,indent=2))
    reader=imageio.get_reader(path);meta=reader.get_meta_data();n=reader.count_frames()
    indices=np.linspace(0,n-1,12).astype(int)
    for i,j in enumerate(indices):imageio.imwrite(out/f'{i:02}.jpg',reader.get_data(int(j)))
    reader.close()
    (out/'metadata.json').write_text(json.dumps({'source':'scripted simulation demonstration',
        'human_hand_demo':False,'order':order,'fps':meta['fps'],'frames':n,
        'sample_indices':indices.tolist(),'sample_seconds':(indices/meta['fps']).tolist()},indent=2))
    print('READY_DEMO',variant,flush=True)

if __name__=='__main__':
    for v,o in ORDERS.items():generate(v,o)
