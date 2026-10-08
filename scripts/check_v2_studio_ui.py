"""Exercise real Studio controls, workspace clipboard and downloads; never record video."""
import asyncio,ast,base64,json,os,secrets,sys
from pathlib import Path
import httpx,uvicorn
from playwright.async_api import async_playwright,expect
from vic import v2
from vic.config import ROOT
from vic_apps.server import create_app


async def main():
    tasks=list(map(int,sys.argv[1].split(','))) if len(sys.argv)>1 else [41,43]
    variants=sys.argv[2] if len(sys.argv)>2 else 'ABC'
    out=ROOT/'.local/v2-studio-ui';out.mkdir(parents=True,exist_ok=True)
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
                    async def action(locator):
                        async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')) as pending:
                            await locator.click()
                        r=await pending.value;assert r.status==200,await r.text()
                    async def nav(name):await page.locator('.product-nav').get_by_role('button',name=name,exact=True).click()
                    async def project(id):
                        await nav('内容项目');await page.locator(f'[data-project="{id}"]').click()
                    async def download(button,expected):
                        async with page.expect_download() as pending:await button.click()
                        downloaded=await pending.value
                        assert await downloaded.failure() is None
                        assert Path(await downloaded.path()).read_bytes()==expected
                    try:
                        await page.goto(f'http://127.0.0.1:8782/native/product/studio/{rid}#{token}')
                        await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                        await page.screenshot(path=str(out/f'{task}-{variant}-home.png'))
                        if task==41:
                            await nav('模型库');await expect(page.locator('.studio-models article')).to_have_count(11)
                            await nav('提示词库');await expect(page.locator('.studio-panel')).to_have_count(6)
                            await nav('资料库');await expect(page.locator('.studio-panel')).to_have_count(6)
                            for i,pr in enumerate(state['world']['projects']):
                                await project(pr['id'])
                                candidates=[x for x in state['items'] if x['id'] in pr['available_models'] and x['context']>=pr['min_context']]
                                metric={'A':lambda x:-x['context'],'B':lambda x:x['price'],'C':lambda x:len(x['name'])}[variant]
                                model=min(candidates,key=lambda x:(metric(x),x['model_code']))
                                await page.get_by_label('生成模型',exact=True).select_option(model['id'])
                                await page.get_by_label('提示词模板',exact=True).select_option(pr['template'])
                                await page.get_by_label('输入资料',exact=True).select_option(pr['document'])
                                await action(page.get_by_role('button',name='保存项目配置',exact=True))
                                await expect(page.get_by_role('button',name='运行生成',exact=True)).to_be_enabled()
                                if i==0:
                                    await page.get_by_label('输入资料',exact=True).select_option('document-1-v1')
                                    await expect(page.get_by_role('button',name='运行生成',exact=True)).to_be_disabled()
                                    await page.get_by_label('输入资料',exact=True).select_option(pr['document'])
                                await action(page.get_by_role('button',name='运行生成',exact=True))
                                gen=page.locator('[data-generation]').first
                                await expect(gen).to_contain_text(model['name'])
                                doc=next(d for d in state['world']['documents'] if d['id']==pr['document'])
                                for line in doc['records']:await expect(gen).to_contain_text(line)
                                await gen.get_by_label('归档项目',exact=True).select_option(pr['id'])
                                await action(gen.get_by_role('button',name='归档生成结果',exact=True))
                                if i==0:await page.screenshot(path=str(out/f'{task}-{variant}-project.png'),full_page=True)
                                await nav('归档文件')
                                archive=page.locator('[data-archive]').filter(has=page.get_by_role('heading',name=pr['name'],exact=True))
                                if i==0:
                                    await action(archive.get_by_role('button',name='移除归档',exact=True))
                                    await expect(archive).to_have_count(0)
                                    await project(pr['id']);await action(page.locator('[data-generation]').first.get_by_role('button',name='归档生成结果',exact=True));await nav('归档文件')
                                snap=await snapshot();record=next(a for a in snap['state']['world']['archives'].values() if a['project']==pr['id']);file=snap['state']['domain']['files'][record['file']]
                                await download(archive.get_by_role('button',name='下载文件',exact=True),base64.b64decode(file['content']))
                                await archive.get_by_role('link',name=file['name'],exact=True).click()
                                await expect(page.get_by_role('heading',name=file['name'],exact=True)).to_be_visible()
                                await expect(page.locator('.studio-content-text')).to_have_text(base64.b64decode(file['content']).decode())
                            await nav('归档文件');await expect(page.locator('[data-archive]')).to_have_count(3)
                        else:
                            first_delivery=True
                            for pr in state['world']['projects']:
                                for target in pr['outputs']:
                                    item=state['domain']['objects'][target]
                                    await project(pr['id']);await page.locator(f'[data-output-link="{target}"]').click()
                                    await expect(page.locator('.studio-code-text')).to_have_text(item['code'])
                                    await expect(page.get_by_role('button',name='保存文件',exact=True)).to_be_disabled()
                                    await action(page.get_by_role('button',name='运行语法检查',exact=True))
                                    try:ast.parse(item['code']);passed=True
                                    except SyntaxError:passed=False
                                    if not passed:
                                        await expect(page.locator('.studio-fail')).to_contain_text('语法检查未通过')
                                        await expect(page.get_by_role('button',name='发送结果',exact=True)).to_be_disabled()
                                        continue
                                    if variant=='A':
                                        await action(page.get_by_role('button',name='保存文件',exact=True))
                                        await action(page.get_by_role('button',name='将保存文件加入清单',exact=True))
                                        if first_delivery:
                                            await action(page.get_by_role('button',name='撤销本项交付',exact=True))
                                            await expect(page.get_by_role('button',name='将保存文件加入清单',exact=True)).to_have_count(0)
                                            await action(page.get_by_role('button',name='保存文件',exact=True));await action(page.get_by_role('button',name='将保存文件加入清单',exact=True))
                                        await page.get_by_role('link',name=item['record_code']+'-'+item['name'],exact=True).click()
                                        await expect(page.locator('.studio-content-text')).to_have_text(item['code'])
                                        await download(page.get_by_role('button',name='下载文件',exact=True),item['code'].encode())
                                    elif variant=='B':
                                        await action(page.get_by_role('button',name='复制代码',exact=True))
                                        await action(page.get_by_role('button',name='粘贴到交付清单',exact=True))
                                        await expect(page.get_by_label('复制交付内容',exact=True)).to_have_value(item['code'])
                                        if first_delivery:await page.screenshot(path=str(out/f'{task}-{variant}-pasted.png'),full_page=True)
                                    else:
                                        await page.get_by_label('交付联系人',exact=True).select_option(str(pr['recipient']))
                                        await action(page.get_by_role('button',name='发送结果',exact=True))
                                        await action(page.get_by_role('button',name='将发送回执加入清单',exact=True))
                                        snap=await snapshot();receipt=next(r for r in snap['state']['world']['receipts'] if r['target']==target)
                                        await page.get_by_role('link',name='打开团队消息 →',exact=True).click()
                                        await expect(page.get_by_role('region',name='工作范围')).to_contain_text('项目结果交付')
                                        person=next(p for p in state['world']['people'] if p['id']==pr['recipient'])
                                        await page.locator('.ant-list-item').filter(has_text=person['name']).click()
                                        card=page.locator(f'[data-studio-receipt="{receipt["id"]}"]')
                                        await expect(card.locator('pre')).to_have_text(item['code'])
                                        if first_delivery:
                                            await expect(page.locator('.ant-spin-blur')).to_have_count(0);await page.wait_for_timeout(300)
                                            await page.screenshot(path=str(out/f'{task}-{variant}-message.png'),full_page=True)
                                        await card.get_by_role('link',name='查看源结果 →',exact=True).click()
                                        await expect(page.locator('.studio-code-text')).to_have_text(item['code'])
                                    first_delivery=False
                            await nav('交付清单');await expect(page.locator('[data-delivery]')).to_have_count(6)
                            await action(page.get_by_role('button',name='保存交付清单',exact=True))
                            snap=await snapshot();manifest=snap['state']['domain']['files']['delivery-manifest']
                            await download(page.get_by_role('button',name='下载交付清单',exact=True),base64.b64decode(manifest['content']))
                            await page.get_by_role('link',name='打开清单文件',exact=True).click()
                            await expect(page.locator('.studio-content-text')).to_have_text(base64.b64decode(manifest['content']).decode())
                        snap=await snapshot();result=v2.evaluate(state,snap['state'],variant,snap['events']);assert result['success'],result
                        await page.screenshot(path=str(out/f'{task}-{variant}-final.png'),full_page=True)
                        await page.reload();await expect(page.locator('.studio-workflows')).to_be_visible()
                        snap=await snapshot();assert v2.evaluate(state,snap['state'],variant,snap['events'])['success']
                        assert not errors,errors
                        results.append(dict(task=task,variant=variant,seed=10001,suite='v2',mode='eval',surface='native',status='passed',persisted=True,projects=3,delivered_outputs=3 if task==41 else 6,workspace_clipboard=task==43 and variant=='B',actual_downloads=task==41 or variant=='A',im_source_links=task==43 and variant=='C'))
                        print(f'{task}{variant} PASS',flush=True)
                    except Exception as exc:
                        results.append(dict(task=task,variant=variant,seed=10001,status='failed',error=str(exc),page_errors=errors));print(f'{task}{variant} FAIL {exc} {errors}',flush=True)
                        await page.screenshot(path=str(out/f'{task}-{variant}-failed.png'))
                    finally:
                        with (out/'history.jsonl').open('a') as f:f.write(json.dumps(results[-1],ensure_ascii=False)+'\n')
                        await context.close();await client.delete('/internal/runs/'+rid)
        finally:
            await browser.close();server.should_exit=True;await serving
    (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    if any(r['status']=='failed' for r in results):raise SystemExit(1)


if __name__=='__main__':asyncio.run(main())
