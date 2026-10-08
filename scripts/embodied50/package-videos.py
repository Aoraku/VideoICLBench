#!/usr/bin/env python3
"""Package verified successful recordings without private states or action traces."""
import argparse,hashlib,html,json,shutil,subprocess,sys
from pathlib import Path
import imageio_ffmpeg
from PIL import Image,ImageDraw
p=argparse.ArgumentParser();p.add_argument('--recordings',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
repo=Path(__file__).resolve().parents[2];sys.path.insert(0,str(repo))
from simulator.benchmark.catalog import TASKS,task_spec
from simulator.benchmark.provenance import harness_sha256
expected=harness_sha256();environment_hash=hashlib.sha256((repo/'simulator/benchmark/environment.py').read_bytes()).hexdigest()
a.output.mkdir(parents=True,exist_ok=False)
for sub in ('videos','posters','reviews'):(a.output/sub).mkdir()
rows=[];ff=imageio_ffmpeg.get_ffmpeg_exe();cards=[];review_images=[]
for tid,t in TASKS.items():
    chosen=None
    for root in a.recordings:
        folder=root/f'{tid}-A-0';proof=folder/'result.private.json'
        if not proof.exists():continue
        r=json.loads(proof.read_text())
        if (r.get('camera') or {}).get('fovy_degrees')==60 and not r['error'] and r['score']['success'] and r['video_end_success'] and r.get('environment_sha256')==environment_hash and r.get('task_spec_sha256')==hashlib.sha256(json.dumps(task_spec(tid,'A'),sort_keys=True).encode()).hexdigest() and r['task_revision']==t['task_revision']:chosen=(folder,r)
    if not chosen:raise RuntimeError(f'No current successful recording: {tid}')
    folder,r=chosen;video=a.output/'videos'/f'{tid}.mp4';shutil.copyfile(folder/'video.mp4',video)
    reader=imageio_ffmpeg.read_frames(str(video));meta=next(reader);reader.close()
    assert meta['fps']==20 and meta['duration']>0
    timestamps=[0,meta['duration']/2,max(0,meta['duration']-.06)];frames=[]
    for i,ts in enumerate(timestamps):
        dest=a.output/'reviews'/f'{tid}-{i}.jpg'
        subprocess.run([ff,'-v','error','-ss',str(ts),'-i',str(video),'-frames:v','1',str(dest)],check=True)
        frames.append(Image.open(dest).convert('RGB'))
    frames[-1].save(a.output/'posters'/f'{tid}.jpg')
    tile=Image.new('RGB',(1536,410),'white');d=ImageDraw.Draw(tile);d.text((8,5),f'{tid}  initial / midpoint / final',fill='black')
    for i,im in enumerate(frames):tile.paste(im,(i*512,26))
    review_images.append(tile)
    row=dict(task=tid,title=t['title'],task_revision=t['task_revision'],source=t['source'],variant='A',seed=0,
        scene_domain='desktop-non-kitchen',camera=r['camera'],render_backend=r.get('render_backend','osmesa'),kind='privileged-author-simulation-demo',independent_agent=False,
        success=True,actions=r['actions'],recorded_actions=r['video_recorded_actions'],fps=20,duration_seconds=meta['duration'],
        video=f'videos/{tid}.mp4',video_sha256=hashlib.sha256(video.read_bytes()).hexdigest(),
        controller_sha256=r['controller_sha256'],harness_sha256=r['harness_sha256'],task_spec_sha256=r['task_spec_sha256'],environment_sha256=r['environment_sha256'])
    rows.append(row)
    title=html.escape(t['title']);source=html.escape(t['source']['project'])
    cards.append(f'<article data-text="{tid} {title} {source}"><h2>{tid} · {title}</h2><video controls preload="none" poster="posters/{tid}.jpg" src="videos/{tid}.mp4"></video><p>{source} 设计来源 · A / seed 0 · {meta["duration"]:.1f} 秒 · {r["actions"]} 动作</p></article>')
for i in range(0,50,5):
    page=Image.new('RGB',(1536,2050),'white')
    for j,im in enumerate(review_images[i:i+5]):page.paste(im,(0,j*410))
    page.save(a.output/'reviews'/f'page-{i//5+1:02}.jpg',quality=90)
manifest=dict(benchmark='VideoICL-Embodied-50',scope='50 author demonstrations, A layout, seed 0',fps=20,
    independent_agent_trials=0,human_demonstrations_collected=0,author_visual_review='pending',harness_sha256=expected,rows=rows)
(a.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
(a.output/'index.html').write_text('''<!doctype html><html lang="zh"><meta charset="utf-8"><title>VideoICL 桌面任务视频库</title><style>body{font:16px system-ui;margin:32px;background:#f3f5f8;color:#182235}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:24px}article{padding:18px;background:white;border-radius:12px}video{width:100%}h2{font-size:18px}input{padding:12px;margin:16px 0;width:60%}p{line-height:1.6}</style><h1>50个桌面双臂任务 · 仿真示范库</h1><p>全部为作者控制器录制的成功仿真演示，20 fps，A布局、seed 0。机器人执行合法动作；未使用瞬移或状态注入。这不是独立 agent 成绩，也不是人手示范。来源表示设计借鉴，并非上游原生任务视频。演示画面不含任务文字。</p><input placeholder="搜索题号、任务或来源" oninput="for(const c of document.querySelectorAll('article'))c.hidden=!c.dataset.text.toLowerCase().includes(this.value.toLowerCase())"><main>'''+''.join(cards)+'</main></html>')
print(a.output)
