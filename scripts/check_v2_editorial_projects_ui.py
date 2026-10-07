"""Research and deliver native News/Blog documents without recording video."""
import asyncio,json,os,secrets,sys
import httpx,uvicorn
from playwright.async_api import async_playwright,expect
from vic import v2,v2_editorial_projects
from vic.config import ROOT
from vic_apps.server import create_app


async def main():
    tasks=list(map(int,sys.argv[1].split(','))) if len(sys.argv)>1 else [29,30]
    variants=sys.argv[2] if len(sys.argv)>2 else 'ABC'
    out=ROOT/'.local/v2-editorial-ui';out.mkdir(parents=True,exist_ok=True)
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
                    async def blog():
                        await page.get_by_role('link',name='打开墨记 · 编写简报和资料页 →',exact=True).click()
                        await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                    async def nav(name):await page.locator('.product-nav').get_by_role('button',name=name,exact=True).click()
                    try:
                        await page.goto(f'http://127.0.0.1:8782/native/news/{rid}#{token}')
                        await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                        await page.screenshot(path=str(out/f'{task}-{variant}-home.png'))
                        w=state['world'];expected=v2_editorial_projects.desired(state,variant)
                        for scope in w['scopes']:
                            await page.get_by_role('button',name='专题与项目',exact=True).click()
                            card=page.locator(f'[data-project="{scope["id"]}"]')
                            await card.get_by_role('button',name='浏览本项目全部来源',exact=True).click()
                            await expect(page.locator('.news-card')).to_have_count(6 if task==29 else 8)
                            if task==29:
                                for item in state['items']:
                                    if item['scope_id']==scope['id']:
                                        await expect(page.locator(f'.news-card[data-id="{item["id"]}"] .news-title-length')).to_contain_text(f'{len(item["name"])} 个字符')
                            if task==30:
                                await page.get_by_label('起始日期',exact=True).fill(scope['date_from'])
                                await page.get_by_label('结束日期',exact=True).fill(scope['date_to'])
                                await page.get_by_role('button',name='筛选文章',exact=True).click()
                                await expect(page.locator('.news-card')).to_have_count(6)
                            for target in expected[scope['id']]:
                                row=page.locator(f'.news-card[data-id="{target}"]')
                                await save(row.get_by_role('button',name='选入'+scope['name'],exact=True))
                                await expect(row.get_by_role('button',name='移出选定文章',exact=True)).to_be_visible()
                            first=expected[scope['id']][0];row=page.locator(f'.news-card[data-id="{first}"]')
                            await save(row.get_by_role('button',name='移出选定文章',exact=True))
                            await save(row.get_by_role('button',name='选入'+scope['name'],exact=True))
                        await page.screenshot(path=str(out/f'{task}-{variant}-selection.png'),full_page=True)
                        await blog()
                        bundles=[('weekly',w['report_title'],[s['id'] for s in w['scopes']])] if task==29 else [(scope['id'],scope['document_title'],[scope['id']]) for scope in w['scopes']]
                        for index,(scope,title,sections) in enumerate(bundles,1):
                            key=f'doc-{index:03d}'
                            await nav('文档')
                            await page.get_by_label('文档范围',exact=True).select_option(scope)
                            await page.get_by_label('文档标题',exact=True).fill(title)
                            await save(page.get_by_role('button',name='创建文档',exact=True))
                            await page.locator(f'[data-document="{key}"]').get_by_role('button',name='编辑文档',exact=True).click()
                            for section in sections:
                                for target in expected[section]:
                                    item=state['domain']['objects'][target]
                                    await page.get_by_label('章节',exact=True).select_option(section)
                                    await page.get_by_label('引用文章',exact=True).select_option(target)
                                    await expect(page.get_by_label('引用摘要',exact=True)).to_have_value(item['summary'])
                                    await expect(page.get_by_label('原文链接',exact=True)).to_have_value('news/articles/'+target)
                                    await save(page.get_by_role('button',name='保存引用',exact=True))
                                    await expect(page.locator(f'[data-citation="{target}"]')).to_be_visible()
                            first=expected[sections[0]][0];code=state['domain']['objects'][first]['record_code']
                            await save(page.get_by_role('button',name='移除引用 '+code,exact=True))
                            await expect(page.locator(f'[data-citation="{first}"]')).to_have_count(0)
                            await page.get_by_label('章节',exact=True).select_option(sections[0])
                            await page.get_by_label('引用文章',exact=True).select_option(first)
                            await save(page.get_by_role('button',name='保存引用',exact=True))
                            await save(page.get_by_role('button',name='保存文档',exact=True))
                            await expect(page.get_by_text('全部更改已保存',exact=False)).to_be_visible()
                            await page.get_by_role('button',name='预览文档',exact=True).click()
                            await expect(page.get_by_role('heading',name=title,exact=True)).to_be_visible()
                            await page.screenshot(path=str(out/f'{task}-{variant}-document-{index}.png'),full_page=True)
                            # Citation links open the actual selected article in News.
                            await page.locator(f'[data-citation="{first}"]').get_by_role('link',name='阅读原文 →',exact=True).click()
                            await expect(page.get_by_role('heading',name=state['domain']['objects'][first]['name'],exact=True)).to_be_visible()
                            await expect(page.locator('.news-detail')).to_contain_text(state['domain']['objects'][first]['summary'])
                            await blog()
                            if task==30:
                                await nav('资料目录')
                                await page.get_by_label('目录项目',exact=True).select_option(scope)
                                await page.get_by_label('目录资料页',exact=True).select_option(key)
                                await expect(page.get_by_label('目录文章数',exact=True)).to_have_value(str(len(expected[scope])))
                                await save(page.get_by_role('button',name='保存目录条目',exact=True))
                                entry=page.locator(f'[data-directory="{scope}"]')
                                if index==1:
                                    await save(entry.get_by_role('button',name='移除目录条目',exact=True))
                                    await expect(entry).to_have_count(0)
                                    await save(page.get_by_role('button',name='保存目录条目',exact=True))
                                await entry.get_by_role('link',name='打开资料页 →',exact=True).click()
                                await expect(page.get_by_role('heading',name=title,exact=True)).to_be_visible()
                                await expect(page.locator('[data-citation]')).to_have_count(len(expected[scope]))
                        snap=await snapshot();result=v2.evaluate(state,snap['state'],variant,snap['events']);assert result['success'],result
                        await page.reload();await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                        snap=await snapshot();assert v2.evaluate(state,snap['state'],variant,snap['events'])['success']
                        assert not errors,errors
                        results.append(dict(task=task,variant=variant,seed=10001,suite='v2',mode='eval',surface='native',status='passed',persisted=True,cross_app_links=True))
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
