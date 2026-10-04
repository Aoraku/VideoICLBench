"""Browser verification of the new business-document module, without recording.

Only rule operations are prepared through ordinary public commands. The new
source lookup, draft editing, association, publication and download are performed
through actual native-page browser controls. This is not a full rule-UI test.
"""
import argparse
import asyncio
import hashlib
import json
import os
import secrets
from pathlib import Path

import httpx
import uvicorn
from playwright.async_api import async_playwright, expect
from vic import v2, v2_worksets, games
from vic.config import ROOT
from vic.lessons import native_path
from vic_apps.server import create_app
from vic_apps.store import ApplicationStore


async def check(args):
    out=ROOT/args.output;out.mkdir(parents=True,exist_ok=True)
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
                for task_id in args.tasks:
                    for variant in args.variants:
                        initial=v2.generate(task_id,args.seed,'eval');rid=secrets.token_hex(16);token=secrets.token_hex(32)
                        response=await client.post('/internal/prepare',json=dict(run_id=rid,token=token,app=initial['app'],epoch=0,state=initial));response.raise_for_status()
                        actor={'Authorization':'Bearer '+token};url='/api/runs/'+rid
                        context=await browser.new_context(viewport={'width':1440,'height':1100},accept_downloads=True)
                        await context.add_init_script("navigator.mediaDevices.getDisplayMedia=()=>{throw Error('QA must not record video')}")
                        page=await context.new_page();page.set_default_timeout(20000);errors=[]
                        page.on('pageerror',lambda error:errors.append(str(error)))
                        async def state():
                            result=await client.get(url,headers=actor);result.raise_for_status();return result.json()['state']
                        async def command(op,target='',value='',ids=None):
                            result=await client.post(url+'/commands',headers=actor,json=dict(epoch=0,action_id=secrets.token_hex(16),op=op,target=target,value=value,ids=ids or []));result.raise_for_status();return result.json()['state']
                        async def evaluate():
                            snapshot=await state();store=ApplicationStore(out/'data')
                            return v2.evaluate(initial,snapshot,variant,store.events(rid))
                        async def click_saved(locator):
                            async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')) as pending:
                                await locator.click()
                            response=await pending.value
                            assert response.status==200,await response.text()
                            # The module fetches fresh state and renders after the write.
                            await page.wait_for_function("!document.querySelector('#vic-business-documents')?.shadowRoot?.textContent.includes('正在保存…')")
                        try:
                            if task_id==74:
                                current=initial
                                for _ in range(6):
                                    point=games.expected(74,variant,current)
                                    current=await command('choose',','.join(map(str,point)))
                                targets=['practice-result']
                            else:
                                for op,target,value,ids in v2_worksets.reference_commands(initial,variant,include_delivery=False):
                                    await command(op,target,value,ids)
                                targets=v2_worksets.delivery_objects(initial,variant)
                            assert not (await evaluate())['success'],'Rule execution alone must not satisfy document delivery'
                            await page.goto(base+native_path(initial['app'],rid)+'#'+token)
                            module=page.locator('#vic-business-documents')
                            w=initial['workset_delivery'];request=max(w['requests'],key=lambda r:r['revision'])
                            directory=next(row for row in w['directory'] if row['id']==request['recipient'])
                            await module.get_by_role('button',name=w['title'],exact=True).click()
                            dialog=module.get_by_role('dialog',name=w['title'],exact=True)
                            await expect(dialog.get_by_role('heading',name=request['title'],exact=True)).to_be_visible()
                            await dialog.get_by_role('button',name=w['source_title'],exact=True).click()
                            await expect(dialog.get_by_role('table')).to_be_visible()
                            for target in targets:
                                ref=next(r for r in w['references'] if r['object']==target)
                                await expect(dialog.get_by_role('cell',name=ref['id'],exact=True)).to_be_visible()
                            await dialog.get_by_role('button',name='责任团队目录',exact=True).click()
                            await expect(dialog.get_by_text('团队编号：'+directory['id']+'\n交付邮箱：'+directory['address'],exact=True)).to_be_visible()
                            await dialog.get_by_role('button',name='编制'+w['title'],exact=True).click()
                            await dialog.get_by_label('业务请求',exact=True).select_option(request['id'])
                            await expect(dialog.get_by_label('交付截止时间',exact=True)).to_have_value(request['deadline'])
                            title=w['title']+' · 十月业务交付'
                            await dialog.get_by_label('文档标题',exact=True).fill(title)
                            summary='已依据业务资料整理本次处理结果，请责任团队按各条目的资料和保存状态开展后续工作。'
                            await dialog.get_by_label('交付说明',exact=True).fill(summary)
                            await dialog.get_by_label('接收团队',exact=True).select_option(directory['address'])
                            # Looking up another source must retain unsubmitted edits.
                            await dialog.get_by_role('button',name=w['source_title'],exact=True).click()
                            await dialog.get_by_role('button',name='编制'+w['title'],exact=True).click()
                            await expect(dialog.get_by_label('文档标题',exact=True)).to_have_value(title)
                            await expect(dialog.get_by_label('交付说明',exact=True)).to_have_value(summary)
                            save=dialog.get_by_role('button',name='保存文档信息',exact=True)
                            await save.hover()
                            assert await save.evaluate("el=>getComputedStyle(el).backgroundColor")=="rgb(23, 72, 61)"
                            await click_saved(save)
                            for index,target in enumerate(targets):
                                ref=next(r for r in w['references'] if r['object']==target)
                                await dialog.get_by_label(w['row_title'],exact=True).select_option(target)
                                await dialog.get_by_label('关联业务资料',exact=True).select_option(ref['id'])
                                await expect(dialog.get_by_label(w['detail_label'],exact=True)).to_have_value(ref['detail'])
                                await click_saved(dialog.get_by_role('button',name='保存文档条目',exact=True))
                            assert len((await state())['workset_delivery']['draft']['rows'])==len(targets)
                            # Real correction and deletion/re-addition of one row.
                            first=targets[0];ref=next(r for r in w['references'] if r['object']==first)
                            article=dialog.locator('article').filter(has=page.get_by_role('heading',name='1. '+ref['object_code']+' · '+ref['name'],exact=True))
                            await article.get_by_role('button',name='编辑',exact=True).click()
                            await dialog.get_by_label(w['detail_label'],exact=True).fill('待核对业务资料')
                            await click_saved(dialog.get_by_role('button',name='保存文档条目',exact=True))
                            await click_saved(dialog.get_by_role('button',name='交付'+w['title'],exact=True))
                            assert not (await evaluate())['success'],'Wrong business detail must fail evaluation'
                            await article.get_by_role('button',name='编辑',exact=True).click()
                            await dialog.get_by_label(w['detail_label'],exact=True).fill(ref['detail'])
                            await click_saved(dialog.get_by_role('button',name='保存文档条目',exact=True))
                            await click_saved(article.get_by_role('button',name='刷新保存结果',exact=True))
                            await click_saved(article.get_by_role('button',name='移除',exact=True))
                            assert len((await state())['workset_delivery']['draft']['rows'])==len(targets)-1
                            await dialog.get_by_label(w['row_title'],exact=True).select_option(first)
                            await dialog.get_by_label('关联业务资料',exact=True).select_option(ref['id'])
                            await click_saved(dialog.get_by_role('button',name='保存文档条目',exact=True))
                            if len(targets)>1:
                                moved=dialog.locator('article').filter(has=page.get_by_role('heading',name=str(len(targets))+'. '+ref['object_code']+' · '+ref['name'],exact=True))
                                await click_saved(moved.get_by_role('button',name='上移',exact=True))
                            await click_saved(dialog.get_by_role('button',name='交付'+w['title'],exact=True))
                            final=await state();result=await evaluate();assert result['success'],result
                            # Persistence is checked through a new store object, not the response body.
                            reloaded=ApplicationStore(out/'data').snapshot(rid)
                            assert reloaded==final
                            await dialog.get_by_role('button',name='已交付文件',exact=True).click()
                            await expect(dialog.locator('pre').first).to_have_text(final['workset_delivery']['publications'][-1]['body'])
                            await page.screenshot(path=str(out/f'{task_id:03d}-{variant}-delivery.png'),full_page=True)
                            async with page.expect_download() as downloaded:
                                await dialog.get_by_role('button',name='下载文件',exact=True).first.click()
                            download=await downloaded.value;path=out/f'{task_id:03d}-{variant}-delivery.md';await download.save_as(path)
                            raw=path.read_bytes();publication=final['workset_delivery']['publications'][-1]
                            assert raw==publication['body'].encode('utf-8')
                            assert title.encode() in raw and directory['address'].encode() in raw
                            assert not errors,errors
                            results.append(dict(task=task_id,variant=variant,status='passed',scope='new business document module only; rule actions prepared via ordinary API',rows=len(targets),sha256=hashlib.sha256(raw).hexdigest(),evaluation=result,screenshot=str(out/f'{task_id:03d}-{variant}-delivery.png')))
                            print(f'PASS {task_id:03d}{variant}: source lookup, draft retention, associations, corrections, publication, download, persistence',flush=True)
                        except Exception as error:
                            await page.screenshot(path=str(out/f'{task_id:03d}-{variant}-failure.png'),full_page=True)
                            results.append(dict(task=task_id,variant=variant,status='failed',error=str(error),page_errors=errors))
                            raise
                        finally:
                            (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
                            await context.close()
            finally:await browser.close()
    finally:
        server.should_exit=True
        await serving


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8784)
    parser.add_argument('--output',default='.local/medium-workspace-ui')
    parser.add_argument('--tasks',default='23,74')
    parser.add_argument('--variants',default='A')
    parser.add_argument('--seed',type=int,default=10007)
    args=parser.parse_args();args.tasks=list(map(int,args.tasks.split(',')))
    asyncio.run(check(args))


if __name__=='__main__':main()
