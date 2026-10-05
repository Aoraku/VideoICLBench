"""GUI-only driver: screenshots and actual Chromium mouse events.
No simulator API, state files, object identities, or geometry are read.
"""
import argparse, asyncio, json, sys, time, urllib.request
from pathlib import Path
import websockets
TOKENS=set('MV_FWD MV_BACK MV_LEFT MV_RIGHT MV_UP MV_DOWN ROTATE_CW ROTATE_CCW ROLL_POS ROLL_NEG PITCH_POS PITCH_NEG GRASP RELEASE STILL'.split())
async def main():
    req=json.load(sys.stdin)
    p=argparse.ArgumentParser();p.add_argument('--cdp-port',type=int,required=True);p.add_argument('--page-url',required=True);p.add_argument('--audit-log',type=Path,required=True);a=p.parse_args()
    cdp=a.cdp_port
    tabs=json.load(urllib.request.urlopen(f'http://127.0.0.1:{cdp}/json'))
    tab=next(t for t in tabs if t.get('type')=='page' and t.get('url','').rstrip('/')==a.page_url.rstrip('/'))
    async with websockets.connect(tab['webSocketDebuggerUrl'],max_size=8*1024*1024) as ws:
        ident=0
        async def call(method,params):
            nonlocal ident
            ident+=1; await ws.send(json.dumps({'id':ident,'method':method,'params':params}))
            while True:
                r=json.loads(await ws.recv())
                if r.get('id')==ident:
                    if 'error' in r:raise RuntimeError(r['error'])
                    return r['result']
        async def js(expression):
            r=await call('Runtime.evaluate',{'expression':expression,'returnByValue':True})
            if 'exceptionDetails' in r:raise RuntimeError('GUI query failed')
            return r['result'].get('value')
        async def click(selector):
            rect=await js('(()=>{const e=document.querySelector('+json.dumps(selector)+'); if(!e||e.disabled)return null; const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()')
            if not rect:raise RuntimeError('GUI control unavailable')
            for kind in ('mouseMoved','mousePressed','mouseReleased'):
                await call('Input.dispatchMouseEvent',{'type':kind,**rect,'button':'left','clickCount':1})
            await asyncio.sleep(.10)
        async def visible():
            return await js("({status:document.getElementById('rec-chip').innerText,message:document.getElementById('result').innerText,ready:[...document.querySelectorAll('.view img')].every(i=>i.naturalWidth>0)})")
        for _ in range(100):
            if (await visible())['ready']:break
            await asyncio.sleep(1)
        else:raise RuntimeError('Images not loaded')
        op=req['op']; before=await visible()
        if op=='start':await click('#btn-start')
        elif op=='finish':await click('#btn-stop')
        elif op=='act':
            token=req['token'];n=req.get('count',1);step=req.get('step',.02)
            assert token in TOKENS and type(n)==int and 1<=n<=9 and step in (.005,.01,.02)
            if token in ('GRASP','RELEASE','STILL'):assert n==1
            # Set a normal HTML select via focused keyboard events.
            await click('#step-size')
            await call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Home','code':'Home','windowsVirtualKeyCode':36})
            await call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Home','code':'Home','windowsVirtualKeyCode':36})
            # Read only the visible option labels/value order, never scene internals.
            vals=await js("[...document.getElementById('step-size').options].map(o=>Number(o.value))")
            for _ in range(vals.index(step)):
                await call('Input.dispatchKeyEvent',{'type':'keyDown','key':'ArrowDown','code':'ArrowDown','windowsVirtualKeyCode':40})
                await call('Input.dispatchKeyEvent',{'type':'keyUp','key':'ArrowDown','code':'ArrowDown','windowsVirtualKeyCode':40})
            await call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Enter','code':'Enter','windowsVirtualKeyCode':13})
            await call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Enter','code':'Enter','windowsVirtualKeyCode':13})
            for _ in range(n):await click(f'[data-side="right"][data-token="{token}"]')
            await click('#commit')
        elif op!='observe':raise ValueError('Invalid GUI operation')
        if op!='observe':
            for _ in range(180):
                now=await visible()
                if now['status']!=before['status'] and now['message']!='Executing…':break
                await asyncio.sleep(.5)
            else:raise RuntimeError('GUI completion timed out; inspect before retrying')
            await asyncio.sleep(2)
        for _ in range(100):
            status=await visible()
            if status['ready']:break
            await asyncio.sleep(.2)
        else:raise RuntimeError('Action completed but camera images unavailable; observe before another action')
        shot=await call('Page.captureScreenshot',{'format':'jpeg','quality':85})
        out={'status':status,'image':shot['data']}
        log=a.audit_log
        log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('a') as f:f.write(json.dumps({'time':time.time(),'request':req,'visible':status})+'\n')
        print(json.dumps(out))
asyncio.run(main())
