"""Application switchers preserve one run; goals remain outside software screens."""
import asyncio, hashlib, json, os, secrets
from pathlib import Path
import httpx, uvicorn
from playwright.async_api import async_playwright, expect
from vic import v2
from vic.lessons import native_path
from vic_apps.server import create_app

async def main():
    out=Path('.local/inference-navigation-ui');out.mkdir(parents=True,exist_ok=True)
    base='http://127.0.0.1:8787';secret=secrets.token_hex(32)
    os.environ.update(VIC_APP_DATA=str(out/'data'),VIC_APP_RUNTIME_TOKEN=secret,VIC_NATIVE_SELF_BASE=base)
    server=uvicorn.Server(uvicorn.Config(create_app(),host='127.0.0.1',port=8787,log_level='error'))
    serving=asyncio.create_task(server.serve())
    while not server.started:await asyncio.sleep(.05)
    try:
        async with httpx.AsyncClient(base_url=base,headers={'Authorization':'Bearer '+secret},trust_env=False,timeout=60) as client,async_playwright() as p:
            browser=await p.chromium.launch(channel=os.environ.get('VIC_BROWSER_CHANNEL'))
            try:
                for task in [11,13,15,18,28,29,30,32,35,40,41,42,43,44,45,46,51,52,54,55,56,58,60,64,65]:
                    state=v2.generate(task,10001,'eval');rid=secrets.token_hex(16);token=secrets.token_hex(32)
                    (await client.post('/internal/prepare',json=dict(run_id=rid,token=token,app=state['app'],epoch=0,state=state))).raise_for_status()
                    context=await browser.new_context(viewport={'width':1440,'height':1000})
                    await context.add_init_script("navigator.mediaDevices.getDisplayMedia=()=>{throw Error('No recording in QA')}")
                    page=await context.new_page();page.set_default_timeout(20000)
                    try:
                        before=(await client.get('/internal/runs/'+rid)).json()
                        await page.goto(base+native_path(state['app'],rid)+'#'+token)
                        switcher=page.get_by_role('navigation',name='应用切换')
                        expected=set([state['app'],*state.get('linked_apps',[])])
                        await expect(switcher.get_by_role('link')).to_have_count(len(expected))
                        hrefs=await switcher.get_by_role('link').evaluate_all('(links)=>links.map(a=>a.href)')
                        for href in hrefs:
                            assert rid in href
                            await page.goto(href)
                            await expect(page.get_by_role('navigation',name='应用切换')).to_be_visible()
                            await expect(page.locator('#vic-work-batch')).to_have_count(0)
                            body=await page.locator('body').inner_text()
                            assert state['execution']['assignment'] not in body
                            assert 'Application mismatch' not in body
                        after=(await client.get('/internal/runs/'+rid)).json()
                        assert before['state']==after['state']
                        if task in (11,29,52):await page.screenshot(path=str(out/f'{task}.png'))
                        print(f'{task:03d} application links and persistent state PASS',flush=True)
                    finally:await context.close();await client.delete('/internal/runs/'+rid)
            finally:await browser.close()
    finally:server.should_exit=True;await serving
if __name__=='__main__':asyncio.run(main())
