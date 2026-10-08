#!/usr/bin/env python3
"""Author-only, metric A-layout sheets for the six human pilot recordings."""
import html
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
CAT=json.loads((ROOT/'simulator/benchmark/tasks.json').read_text())
OUT=ROOT/'simulator/benchmark/filming'
OUT.mkdir(exist_ok=True)
for task in CAT['tasks']:
    if task['id'] not in ('rt12','rt07','rt02','rc10','rc22','rc11'):continue
    def xy(item):return 450+1000*item['xy'][1],450+1000*item['xy'][0]
    lines=['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="1030" viewBox="0 0 900 1030">',
        '<rect width="900" height="1030" fill="#f6f8fa"/>',
        '<g font-family="Arial, sans-serif" fill="#172334">',
        f'<text x="50" y="28" font-size="20">{task["id"]} A · {html.escape(task["title"])}</text>',
        '<rect x="50" y="50" width="800" height="800" fill="white" stroke="#203044" stroke-width="2"/>']
    for mm in range(-300,301,100):
        v=450+mm
        lines += [f'<path d="M {v} 50 V 850 M 50 {v} H 850" stroke="#e4e9ee" stroke-width="1"/>']
    lines += ['<path d="M 450 50 V 850 M 50 450 H 850" stroke="#abb8c4" stroke-dasharray="5 5"/>',
              '<text x="55" y="73" font-size="14">Far edge: X = −400 mm · hands enter from this side</text>',
              '<text x="55" y="838" font-size="14">Near edge: X = +400 mm · camera on this side</text>']
    for zone in task['zones']:
        x,y=xy(zone);hx,hy=zone['half_size']
        lines += [f'<rect x="{x-hy*1000}" y="{y-hx*1000}" width="{hy*2000}" height="{hx*2000}" fill="#8298ab" opacity=".45"/>',
                  f'<text x="{x}" y="{y}" text-anchor="middle" font-size="14">mat</text>']
    objects=sorted(task['objects'],key=lambda o:o['kind'] not in ('cup','bowl','tray'))
    for o in objects:
        x,y=xy(o);sx,sy,sz=o['size'];color='#'+''.join(f'{round(c*255):02x}' for c in o['rgba'][:3])
        if o['kind']=='bottle':
            lines.append(f'<circle cx="{x}" cy="{y}" r="{sx*1000}" fill="{color}" stroke="#172334"/>')
        else:
            lines.append(f'<rect x="{x-sy*1000}" y="{y-sx*1000}" width="{sy*2000}" height="{sx*2000}" fill="{color}" stroke="#172334"/>')
        if o['kind'] in ('cup','bowl','tray'):
            lines.append(f'<rect x="{x-(sy-.008)*1000}" y="{y-(sx-.008)*1000}" width="{(sy-.008)*2000}" height="{(sx-.008)*2000}" fill="white"/>')
        lines.append(f'<text x="{x}" y="{y-sx*1000-8}" text-anchor="middle" font-size="14">{o["id"]}</text>')
    lines += ['<text x="50" y="880" font-size="16">Top view · 1 px = 1 mm · origin at table center · +Y right, +X down</text>',
              '<text x="50" y="905" font-size="15">Nominal A layout; omit the ±4 mm simulator seed jitter for physical filming.</text>']
    for i,o in enumerate(task['objects']):
        dims=' × '.join(str(round(v*2000)) for v in o['size'])
        lines.append(f'<text x="50" y="{932+i*21}" font-size="14">{o["id"]}: center (X,Y)=({round(o["xy"][0]*1000)},{round(o["xy"][1]*1000)}) mm; full size X×Y×Z = {dims} mm</text>')
    lines += ['<text x="50" y="1012" font-size="13">AUTHOR ONLY · Never show this sheet, labels or coordinates in agent demonstration media.</text>','</g></svg>']
    (OUT/f'{task["id"]}-A.svg').write_text('\n'.join(lines)+'\n')
