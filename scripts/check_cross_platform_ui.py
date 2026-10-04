"""Smoke-test native IM artifact delivery controls; no video or agent task trial.

The ordinary application API prepares real business artifacts. The browser then
reads the source request, selects attachments, sends, downloads and opens them.
Run after building native frontends; this script never builds or changes assets.
"""
import argparse
import asyncio
import base64
import json
import os
from pathlib import Path
import secrets
import sys
import time

import httpx
import uvicorn
from playwright.async_api import async_playwright, expect
from vic import v2
from vic.config import ROOT
from vic_apps.cross_platform import resources
from vic_apps.server import create_app

sys.path.insert(0, str(ROOT/'tests'))
from test_v2_screening import operations as screening_plan
from test_v2_shop_projects import plan as shop_plan
from test_v2_studio_projects import plan as studio_plan


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tasks',default='35,52,43')
    parser.add_argument('--variants',default='A')
    parser.add_argument('--port',type=int,default=8786)
    parser.add_argument('--output',default='.local/cross-inbox-ui')
    args=parser.parse_args()
    tasks=[int(x) for x in args.tasks.split(',')]
    if not set(tasks)<={35,43,52}:raise ValueError('This UI smoke supports representative tasks 035, 043 and 052')
    if not args.variants or set(args.variants)-set('ABC'):raise ValueError('Variants must use A/B/C')
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    base=f'http://127.0.0.1:{args.port}';secret=secrets.token_hex(32)
    os.environ.update(VIC_APP_DATA=str(out/'data'),VIC_APP_RUNTIME_TOKEN=secret,VIC_NATIVE_SELF_BASE=base)
    server=uvicorn.Server(uvicorn.Config(create_app(),host='127.0.0.1',port=args.port,log_level='error'))
    serving=asyncio.create_task(server.serve())
    while not server.started:
        if serving.done():await serving
        await asyncio.sleep(.05)
    results=[]
    try:
        async with httpx.AsyncClient(base_url=base,headers={'Authorization':'Bearer '+secret},trust_env=False,timeout=60) as client,async_playwright() as p:
            browser=await p.chromium.launch()
            try:
                for task in tasks:
                    for variant in args.variants:
                        run=secrets.token_hex(16);token=secrets.token_hex(32)
                        initial=v2.generate(task,10001,'eval')
                        prepared=await client.post('/internal/prepare',json=dict(run_id=run,token=token,app=initial['app'],epoch=0,state=initial))
                        prepared.raise_for_status()
                        path='/api/runs/'+run;actor={'Authorization':'Bearer '+token}
                        context=await browser.new_context(viewport={'width':1440,'height':1050},accept_downloads=True)
                        await context.add_init_script("navigator.mediaDevices.getDisplayMedia=()=>{throw Error('This smoke test must never record video')}")
                        page=await context.new_page();page.set_default_timeout(20000)
                        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                        record=dict(task=task,variant=variant,scope='native IM request and actual artifact delivery controls',video_recorded=False,checkbox_transitions=[])
                        async def snapshot():
                            r=await client.get('/internal/runs/'+run);r.raise_for_status();return r.json()
                        try:
                            # All preparation uses normal business mutations. No final-state injection.
                            plan={35:screening_plan,52:shop_plan,43:studio_plan}[task]
                            for index,command in enumerate(plan.__wrapped__(initial,variant)):
                                op,target,data=command[:3]
                                response=await client.post(path+'/commands',headers=actor,json=dict(epoch=0,action_id=f'prepare-{index}',op=op,target=target,value=json.dumps(data),ids=command[3] if len(command)==4 else []))
                                response.raise_for_status()
                            prepared=(await snapshot())['state']
                            assert not v2.evaluate(initial,prepared,variant,(await snapshot())['events'])['success'],'Business completion must not bypass cross-platform delivery'
                            options=resources(prepared)
                            await page.goto(base+f'/native-assets/im/?run={run}#'+token)
                            await expect(page.get_by_role('region',name='工作范围')).to_contain_text('业务委托与成果交付')
                            current=[r for r in initial['cross_platform']['requests'] if r['revision']==2]
                            seen_message_ids=set()
                            downloaded=[];links=[]
                            for request in current:
                                person=next(x for x in initial['cross_platform']['people'] if x['id']==request['requester'])
                                await page.locator('.ant-list-item').filter(has=page.get_by_text(person['name'],exact=True)).click()
                                card=page.locator(f'[data-handoff-request="{request["id"]}"]')
                                await expect(card).to_contain_text(request['body'])
                                source_messages=await page.locator('[id^=msg-]').filter(has=page.locator('[data-handoff-request]')).evaluate_all('(nodes)=>nodes.map(n=>n.id)')
                                assert not seen_message_ids.intersection(source_messages),'Different conversations reused message IDs'
                                seen_message_ids.update(source_messages)
                                await expect(card.get_by_role('link',name='打开业务应用 ↗')).to_be_visible()
                                if request==current[0]:
                                    await card.get_by_text('查看附件正文',exact=True).click()
                                    await expect(card.locator('pre')).to_have_text(base64.b64decode(request['attachment']['content']).decode())
                                    async with page.expect_download() as pending:
                                        await card.get_by_role('button',name='下载 '+request['attachment']['name'],exact=True).click()
                                    download=await pending.value;local=out/f'{task}-{variant}-request.md';await download.save_as(local)
                                    assert local.read_bytes()==base64.b64decode(request['attachment']['content'])
                                await card.get_by_role('button',name='回复成果附件',exact=True).click()
                                modal=page.get_by_role('dialog',name='回复需求 '+request['id'],exact=True)
                                await expect(modal.get_by_text(person['name']+' · '+person['role'],exact=True)).to_be_visible()
                                wanted=[r for r in options if r['scope']==request['scope']]
                                for resource in wanted:
                                    checkbox=modal.get_by_role('checkbox',name=resource['title']+' · '+resource['scope'],exact=True)
                                    started=time.monotonic()
                                    await checkbox.click()
                                    immediate=await checkbox.is_checked()
                                    await expect(checkbox).to_be_checked()
                                    record['checkbox_transitions'].append(dict(resource=resource['id'],checked_after_click=immediate,settled_after_ms=round((time.monotonic()-started)*1000)))
                                # The native conversation list polls every 5 seconds. User choices must survive it.
                                await page.wait_for_timeout(5500)
                                for resource in wanted:
                                    await expect(modal.get_by_role('checkbox',name=resource['title']+' · '+resource['scope'],exact=True)).to_be_checked()
                                await expect(modal.get_by_role('button',name='发送成果附件',exact=True)).to_be_enabled()
                                async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands') and r.request.post_data_json.get('op')=='handoff.send') as pending:
                                    await modal.get_by_role('button',name='发送成果附件',exact=True).click()
                                response=await pending.value;assert response.status==200,await response.text()
                                await page.wait_for_load_state('domcontentloaded')
                                snap=await snapshot();receipt=next(r for r in snap['state']['cross_platform']['receipts'] if r['request']==request['id'])
                                assert receipt['recipient']==request['recipient']
                                await page.locator('.ant-list-item').filter(has=page.get_by_text(person['name'],exact=True)).click()
                                delivered=page.locator(f'[data-handoff-delivery="{receipt["id"]}"]')
                                await expect(delivered).to_be_visible()
                                for resource in wanted:
                                    section=delivered.locator('section').filter(has=page.get_by_text(resource['title'],exact=True))
                                    async with page.expect_download() as pending:
                                        await section.get_by_role('button',name='下载 '+resource['file']['name'],exact=True).click()
                                    download=await pending.value;local=out/f'{task}-{variant}-{resource["id"]}.bin';await download.save_as(local)
                                    assert local.read_bytes()==base64.b64decode(resource['file']['content'])
                                    downloaded.append(resource['id'])
                                    if not resource['file']['name'].endswith('.zip'):
                                        await section.get_by_text('查看附件正文',exact=True).click()
                                        await expect(section.locator('pre')).to_have_text(base64.b64decode(resource['file']['content']).decode())
                                    async with context.expect_page() as opened:
                                        await section.get_by_role('link',name='在业务应用查看当前成果 ↗',exact=True).click()
                                    business=await opened.value
                                    await business.wait_for_load_state('domcontentloaded')
                                    await expect(business.locator('.product-main')).to_be_visible()
                                    if task==35:await expect(business.locator('pre')).to_contain_text('活动结束')
                                    elif task==52:await expect(business.locator('.purchase-document')).to_contain_text(resource['record']['confirmation'])
                                    else:await expect(business.get_by_role('heading',name='生成结果交付清单.md',exact=True)).to_be_visible()
                                    links.append(resource['id']);await business.close()
                                await page.reload()
                                await page.locator('.ant-list-item').filter(has=page.get_by_text(person['name'],exact=True)).click()
                                await expect(page.locator(f'[data-handoff-delivery="{receipt["id"]}"]')).to_be_visible()
                            final=await snapshot();evaluation=v2.evaluate(initial,final['state'],variant,final['events'])
                            assert evaluation['success'],evaluation['violations']
                            assert not errors,errors
                            await page.screenshot(path=str(out/f'{task}-{variant}-delivered.png'),full_page=True)
                            record.update(status='passed',requests=len(current),downloaded_resources=downloaded,opened_resources=links,evaluation=evaluation)
                            print(f'PASS {task:03d}{variant}: {len(current)} native IM deliveries, {len(downloaded)} byte-matched downloads and business links; refresh retained',flush=True)
                        except Exception as exc:
                            record.update(status='failed',error=str(exc),page_errors=errors)
                            await page.screenshot(path=str(out/f'{task}-{variant}-failure.png'),full_page=True)
                            raise
                        finally:
                            results.append(record)
                            (out/'results.json').write_text(json.dumps(dict(video_recorded=False,scope='new cross-platform inbox UI only; business setup via ordinary API',cases=results),ensure_ascii=False,indent=2)+'\n')
                            await context.close()
                            destroyed=await client.delete('/internal/runs/'+run);destroyed.raise_for_status()
            finally:await browser.close()
    finally:
        server.should_exit=True
        await serving


if __name__=='__main__':asyncio.run(main())
