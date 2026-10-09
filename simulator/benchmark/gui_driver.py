"""GUI-only CDP driver. Reads visible controls/status and takes screenshots.
No fetch, simulator state, hidden DOM data, task catalog or evaluator access.
One JSON request on stdin: observe | act(left,right) | submit.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
import urllib.request
import websockets
from .protocol import TOKENS

async def main():
    p=argparse.ArgumentParser();p.add_argument('--cdp-port',type=int,required=True)
    p.add_argument('--page-url',required=True);p.add_argument('--audit-log',type=Path,required=True);a=p.parse_args()
    req=json.load(sys.stdin)
    tabs=json.load(urllib.request.urlopen(f'http://127.0.0.1:{a.cdp_port}/json'))
    tab=next(t for t in tabs if t.get('type')=='page' and t.get('url','').rstrip('/')==a.page_url.rstrip('/'))
    async with websockets.connect(tab['webSocketDebuggerUrl'],max_size=16*1024*1024) as ws:
        ident=0
        async def call(method,params):
            nonlocal ident
            ident+=1;await ws.send(json.dumps(dict(id=ident,method=method,params=params)))
            while True:
                r=json.loads(await ws.recv())
                if r.get('id')==ident:
                    if 'error' in r: raise RuntimeError(r['error'])
                    return r['result']
        async def visible_js(expr):
            r=await call('Runtime.evaluate',dict(expression=expr,returnByValue=True))
            if 'exceptionDetails' in r: raise RuntimeError('Visible GUI query failed')
            return r['result'].get('value')
        async def click(selector):
            rect=await visible_js('(()=>{const e=document.querySelector('+json.dumps(selector)+');if(!e||e.disabled)return null;e.scrollIntoView({block:"center"});const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()')
            if not rect: raise RuntimeError('GUI control unavailable')
            for kind in ('mouseMoved','mousePressed','mouseReleased'):
                await call('Input.dispatchMouseEvent',dict(type=kind,**rect,button='left',clickCount=1))
        async def ready():
            return await visible_js('({status:document.getElementById("status").innerText,ready:document.querySelectorAll("#views img").length===3 && [...document.querySelectorAll("#views img")].every(i=>i.naturalWidth>0),enabled:!document.getElementById("both").disabled})')
        for _ in range(600):
            state=await ready()
            if state['ready'] and state['enabled']: break
            await asyncio.sleep(.2)
        else: raise RuntimeError('GUI not ready')
        before=state['status']; op=req['op']
        if op=='act':
            for key in ('left','right'):
                if req.get(key,'STILL') not in TOKENS: raise ValueError('Invalid token')
            # Select normal visible options using browser keyboard events.
            for selector,token in [('#ls',req.get('left','STILL')),('#rs',req.get('right','STILL'))]:
                await click(selector)
                for key in ['Home']+['ArrowDown']*TOKENS.index(token)+['Enter']:
                    for typ in ('keyDown','keyUp'): await call('Input.dispatchKeyEvent',dict(type=typ,key=key,code=key,windowsVirtualKeyCode={'Home':36,'ArrowDown':40,'Enter':13}[key]))
            await click('#both')
        elif op=='submit': await click('#submit')
        elif op!='observe': raise ValueError('Unknown GUI operation')
        if op!='observe':
            for _ in range(600):
                state=await ready()
                if state['status']!=before and (state['enabled'] or op=='submit'): break
                await asyncio.sleep(.2)
            else: raise RuntimeError('GUI action timed out; observe before retrying')
        # Capture scene and visible controls after scrolling to the top.
        await visible_js('window.scrollTo(0,0)')
        shot=await call('Page.captureScreenshot',dict(format='jpeg',quality=85))
        a.audit_log.parent.mkdir(parents=True,exist_ok=True)
        with a.audit_log.open('a') as f: f.write(json.dumps(dict(time=time.time(),request=req,visible=state))+'\n')
        print(json.dumps(dict(status=state['status'],image=shot['data'])))
if __name__=='__main__': asyncio.run(main())
