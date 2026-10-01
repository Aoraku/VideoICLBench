"""Native project workflow acceptance using visible controls; no recordings."""
import asyncio
import json
import os
import re
import secrets
import sys
import httpx
import uvicorn
from playwright.async_api import async_playwright,expect
from vic import v2,v2_communications
from vic.config import ROOT
from vic.lessons import native_path
from vic_apps.server import create_app


async def main():
    tasks=list(map(int,sys.argv[1].split(','))) if len(sys.argv)>1 else [11,13,15]
    variants=sys.argv[2] if len(sys.argv)>2 else 'ABC'
    out=ROOT/'.local/v2-communications-ui';out.mkdir(parents=True,exist_ok=True)
    secret=secrets.token_hex(32)
    os.environ.update(VIC_APP_DATA=str(out/'data'),VIC_APP_RUNTIME_TOKEN=secret,VIC_NATIVE_SELF_BASE='http://127.0.0.1:8782')
    server=uvicorn.Server(uvicorn.Config(create_app(),host='127.0.0.1',port=8782,log_level='error'))
    serving=asyncio.create_task(server.serve())
    while not server.started:await asyncio.sleep(.05)
    results=[]
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8782',headers={'Authorization':'Bearer '+secret},trust_env=False,timeout=60) as client,async_playwright() as p:
        browser=await p.chromium.launch()
        try:
            for task in tasks:
                for variant in variants:
                    state=v2.generate(task,10001,'eval');rid=secrets.token_hex(16);token=secrets.token_hex(32)
                    response=await client.post('/internal/prepare',json=dict(run_id=rid,token=token,app=state['app'],epoch=0,state=state));response.raise_for_status()
                    context=await browser.new_context(viewport={'width':1440,'height':1050});page=await context.new_page();page.set_default_timeout(15000)
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    async def snapshot():
                        r=await client.get('/internal/runs/'+rid);r.raise_for_status();return r.json()
                    async def save(locator):
                        async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')) as pending:await locator.click()
                        r=await pending.value;assert r.status==200,await r.text()
                    async def chat(name):
                        await page.locator('.list__itemWrap').filter(has=page.locator('.list__title').get_by_text(name,exact=True)).locator('.list__item').click()
                    try:
                        await page.goto('http://127.0.0.1:8782'+native_path(state['app'],rid)+'#'+token)
                        await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                        await page.screenshot(path=str(out/f'{task}-{variant}-home.png'))
                        w=state['world']
                        if task==11:
                            for request in w['requests']:
                                target=v2_communications.selected_file(state,request,variant)
                                item=next(x for x in state['items'] if x['id']==target)
                                name=next(c['name'] for c in w['conversations'] if c['id']==request['conversation'])
                                await chat(name)
                                await expect(page.locator('.chatBody').get_by_text(request['body'],exact=True)).to_be_visible()
                                project=next(p for p in w['projects'] if p['id']==request['project'])
                                await chat(project['name']+' · 项目资料')
                                await page.get_by_role('button',name='聊天文件',exact=True).click()
                                dialog=page.get_by_role('dialog',name='项目聊天文件')
                                await expect(dialog.get_by_role('combobox',name='来源会话')).to_have_value(str(project['conversation']))
                                await expect(dialog.locator('[data-file-id]')).to_have_count(6)
                                await dialog.locator(f'[data-file-id="{target}"]').click()
                                await dialog.get_by_text('预览所选文件',exact=True).click()
                                await expect(dialog.locator('pre')).to_have_text(item['file_text'])
                                await dialog.get_by_role('combobox',name='附件收件人').select_option(str(request['requester']))
                                await dialog.get_by_role('combobox',name='关联原请求').select_option(request['id'])
                                await save(dialog.get_by_role('button',name='发送附件',exact=True))
                                await expect(dialog.get_by_role('button',name='发送附件',exact=True)).to_be_disabled()
                                await dialog.get_by_role('button',name='关闭文件窗口').click()
                                await chat(name)
                                await expect(page.locator(f'#msg-{10000+w["requests"].index(request)}').get_by_text(item['name'],exact=True)).to_be_visible()
                        elif task==13:
                            targets=[]
                            for project in w['projects']:
                                await chat(project['name']+' · 项目资料')
                                rows=[x for x in state['items'] if x['project']==project['id'] and x['batch']=='晚班-0115' and '紧急' in x['text']]
                                targets+=rows
                                for item in rows:await page.get_by_role('checkbox',name='选择消息：'+item['text'],exact=True).check()
                                action={'A':'转发','B':'收藏','C':'归档'}[variant]
                                await page.get_by_role('button',name='转发给程知夏' if variant=='A' else '批量'+action,exact=True).click()
                                await expect(page.get_by_text(f'已{action} {len(rows)} 条消息',exact=True)).to_be_visible()
                            await page.get_by_role('link',name='交接单',exact=True).click()
                            await expect(page.get_by_role('heading',name='晚班消息交接单',exact=True)).to_be_visible()
                            await page.get_by_role('combobox',name='消息批次').select_option('晚班-0115')
                            for item in targets:
                                await save(page.locator(f'[data-message-id="{item["id"]}"]').get_by_role('button',name='加入交接单',exact=True))
                                select=page.get_by_role('combobox',name='处理结果 '+item['record_code'],exact=True)
                                async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')) as pending:
                                    await select.select_option({'A':'已转发','B':'已收藏','C':'已归档'}[variant])
                                assert (await pending.value).status==200
                            # Remove and re-add a draft line, then follow its
                            # real source link back to the original message.
                            first=targets[0]
                            await save(page.get_by_role('button',name='移除 '+first['record_code'],exact=True))
                            await save(page.locator(f'[data-message-id="{first["id"]}"]').get_by_role('button',name='加入交接单',exact=True))
                            async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')) as pending:
                                await page.get_by_role('combobox',name='处理结果 '+first['record_code']).select_option({'A':'已转发','B':'已收藏','C':'已归档'}[variant])
                            assert (await pending.value).status==200
                            await page.locator(f'[data-delivery-id="{first["id"]}"]').get_by_role('link').click()
                            original=page.locator(f'#msg-{first["message_id"]}')
                            await expect(original).to_be_visible()
                            for line in first['text'].splitlines():await expect(original).to_contain_text(line)
                            await page.get_by_role('link',name='交接单',exact=True).click()
                            await expect(page.locator('[data-delivery-id]')).to_have_count(len(targets))
                            await page.get_by_role('combobox',name='交接单收件人').select_option('2')
                            await save(page.get_by_role('button',name='发送交接单',exact=True))
                            await page.get_by_role('link',name='查看已发送文件',exact=True).click()
                            await expect(page.locator('.chatBody').get_by_text('晚班消息交接单.md',exact=True)).to_be_visible()
                        else:
                            await page.get_by_role('button',name='项目通知与资料',exact=True).click()
                            await expect(page.get_by_role('heading',name='项目通知与资料',exact=True)).to_be_visible()
                            await expect(page.locator('tbody tr')).to_have_count(18)
                            await page.get_by_role('link',name='返回消息',exact=True).click()
                            await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                            for project in w['projects']:
                                members=v2_communications.selected_members(state,project,variant)
                                await page.get_by_title('新建',exact=True).click()
                                await page.get_by_text('发起群聊',exact=True).click()
                                for target in members:
                                    item=next(x for x in state['items'] if x['id']==target)
                                    await page.get_by_role('button',name=re.compile(re.escape(item['account']))).click()
                                await save(page.get_by_role('button',name=re.compile(r'完\s*成')))
                                await page.get_by_title('群聊设置',exact=True).click()
                                details=page.get_by_role('dialog',name='群聊信息')
                                await expect(details.get_by_text('群成员 (4)',exact=True)).to_be_visible()
                                await details.get_by_role('button',name=re.compile('群聊名称')).click()
                                modal=page.get_by_role('dialog',name='修改群聊名称')
                                await modal.get_by_placeholder('输入群聊名称').fill(project['group_name'])
                                await save(modal.get_by_role('button',name=re.compile(r'保\s*存')))
                                await expect(details.get_by_role('heading',name=project['group_name'],exact=True)).to_be_visible()
                                await details.get_by_role('button',name='发布公告',exact=True).click()
                                modal=page.get_by_role('dialog',name='发布群公告')
                                await modal.get_by_placeholder('请输入公告内容，所有人可见...').fill(project['announcement'])
                                await save(modal.get_by_role('button',name=re.compile(r'发\s*布')))
                                await expect(details.get_by_text(project['announcement'],exact=True)).to_be_visible()
                                await details.get_by_role('button',name='Close',exact=True).click()
                                await page.locator('textarea:not([aria-hidden="true"])').fill(project['material_link'])
                                await save(page.get_by_role('button',name=re.compile(r'发\s*送')))
                                await page.get_by_role('link',name='打开项目资料 · '+project['id'],exact=True).click()
                                await expect(page.get_by_text(project['material_text'],exact=True)).to_be_visible()
                                await expect(page.locator('tbody tr')).to_have_count(6)
                                await page.get_by_role('link',name='返回消息',exact=True).click()
                                await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                        snap=await snapshot();result=v2.evaluate(state,snap['state'],variant,snap['events'])
                        assert result['success'],result
                        await page.screenshot(path=str(out/f'{task}-{variant}-done.png'),full_page=True)
                        await page.reload()
                        await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                        snap=await snapshot();assert v2.evaluate(state,snap['state'],variant,snap['events'])['success']
                        assert not errors,errors
                        results.append(dict(task=task,variant=variant,seed=10001,suite='v2',mode='eval',surface='native',status='passed',persisted=True))
                        print(f'{task}{variant} PASS',flush=True)
                    except Exception as exc:
                        results.append(dict(task=task,variant=variant,seed=10001,status='failed',error=str(exc),page_errors=errors))
                        print(f'{task}{variant} FAIL {exc} {errors}',flush=True)
                        await page.screenshot(path=str(out/f'{task}-{variant}-failed.png'))
                    finally:
                        with (out/'history.jsonl').open('a') as f:f.write(json.dumps(results[-1],ensure_ascii=False)+'\n')
                        await context.close();await client.delete('/internal/runs/'+rid)
        finally:
            await browser.close();server.should_exit=True;await serving
    (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    if any(r['status']=='failed' for r in results):raise SystemExit(1)


if __name__=='__main__':asyncio.run(main())
