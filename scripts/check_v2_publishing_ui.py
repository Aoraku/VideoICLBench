"""Native publishing acceptance via visible controls; no video recordings."""
import asyncio,json,os,secrets,sys
import httpx,uvicorn
from playwright.async_api import async_playwright,expect
from vic import v2,v2_publishing
from vic.config import ROOT
from vic_apps.server import create_app


async def main():
    tasks=list(map(int,sys.argv[1].split(','))) if len(sys.argv)>1 else [40,42]
    variants=sys.argv[2] if len(sys.argv)>2 else 'ABC'
    out=ROOT/'.local/v2-publishing-ui';out.mkdir(parents=True,exist_ok=True)
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
                    async def nav(name):await page.locator('.product-nav').get_by_role('button',name=name,exact=True).click()
                    async def open_published(draft):
                        snap=await snapshot()
                        post=next(p for p in snap['state']['world']['publications'].values() if p['draft']==draft)
                        await page.get_by_role('link',name='打开已发布文章 →',exact=True).click()
                        await expect(page.locator('.publication-body h1')).to_have_text(state['domain']['objects'][draft]['name'])
                        await expect(page.locator('.publication-text')).to_have_text(state['domain']['objects'][draft]['text'])
                        return post
                    try:
                        await page.goto(f'http://127.0.0.1:8782/native/product/blog/{rid}#{token}')
                        await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                        await page.screenshot(path=str(out/f'{task}-{variant}-home.png'))
                        expected=v2_publishing.desired(state,variant);w=state['world']
                        for index,(draft,meta) in enumerate(expected.items()):
                            item=state['domain']['objects'][draft]
                            await nav('编辑排期')
                            project=page.locator(f'[data-project="{item["project"]}"]')
                            if task==40:
                                await expect(project).to_contain_text(meta['summary'])
                                await project.get_by_role('button',name='查看本期草稿',exact=True).click()
                                await expect(page.locator('[data-draft]')).to_have_count(6)
                                await page.locator(f'[data-draft="{draft}"]').get_by_role('button',name='编辑发布',exact=True).click()
                            else:
                                await project.locator(f'[data-plan-draft="{draft}"]').get_by_role('button',name='打开稿件',exact=True).click()
                            await expect(page.locator('.blog-editor-body')).to_have_text(item['text'])
                            await page.get_by_label('发布栏目',exact=True).select_option(meta['column'])
                            await page.get_by_label('发布封面',exact=True).select_option(meta['cover'])
                            await page.get_by_label('发布时间',exact=True).fill(meta['publish_at'])
                            await page.get_by_label('发布摘要',exact=True).fill(meta['summary'])
                            await save(page.get_by_role('button',name='保存发布资料',exact=True))
                            if index==0:
                                await page.get_by_label('发布摘要',exact=True).fill(meta['summary']+'补充')
                                await expect(page.get_by_role('button',name='发布文章',exact=True)).to_be_disabled()
                                await page.get_by_label('发布摘要',exact=True).fill(meta['summary'])
                            await save(page.get_by_role('button',name='发布文章',exact=True))
                            post=await open_published(draft)
                            if index==0:
                                await save(page.get_by_role('button',name='撤下文章',exact=True))
                                await expect(page.locator('[data-publication]')).to_have_count(0)
                                await nav('我的草稿')
                                await page.locator(f'[data-draft="{draft}"]').get_by_role('button',name='编辑发布',exact=True).click()
                                await expect(page.get_by_label('发布摘要',exact=True)).to_have_value(meta['summary'])
                                await save(page.get_by_role('button',name='发布文章',exact=True))
                                post=await open_published(draft)
                            await expect(page.locator('.publication-summary')).to_have_text(meta['summary'])
                            await expect(page.locator('.publication-meta')).to_contain_text(meta['publish_at'].replace('T',' '))
                            cover=next(c for c in w['covers'] if c['id']==meta['cover'])
                            await expect(page.locator('.publication-body>img')).to_have_attribute('src',cover['url'])
                            await page.wait_for_function("document.querySelector('.publication-body>img')?.naturalWidth > 0")
                            if index==0:await page.screenshot(path=str(out/f'{task}-{variant}-article.png'),full_page=True)
                            if task==42:
                                await page.get_by_label('通知收件人',exact=True).select_option(str(item['author']))
                                await save(page.get_by_role('button',name='发送发布通知',exact=True))
                                if index==0:
                                    await save(page.get_by_role('button',name='撤回通知',exact=True))
                                    await expect(page.locator('[data-notice]')).to_have_count(0)
                                    await save(page.get_by_role('button',name='发送发布通知',exact=True))
                                await page.get_by_role('link',name='打开团队消息 →',exact=True).click()
                                await expect(page.get_by_role('region',name='工作范围')).to_contain_text('作者发布通知')
                                person=next(a for a in w['authors'] if a['id']==item['author'])
                                await page.locator('.ant-list-item').filter(has_text=person['name']).click()
                                notice=page.locator(f'article[data-publication="{post["id"]}"]')
                                await expect(notice).to_contain_text(item['name'])
                                await expect(notice).to_contain_text(meta['summary'])
                                if index==0:
                                    await expect(page.locator('.ant-spin-blur')).to_have_count(0)
                                    await page.wait_for_timeout(300)
                                    await page.screenshot(path=str(out/f'{task}-{variant}-notification.png'),full_page=True)
                                await notice.get_by_role('link',name='阅读已发布文章 →',exact=True).click()
                                await expect(page.locator('.publication-body h1')).to_have_text(item['name'])
                                await expect(page.locator('.publication-text')).to_have_text(item['text'])
                            await page.get_by_role('button',name='管理栏目索引',exact=True).click()
                            await page.get_by_label('索引栏目',exact=True).select_option(meta['column'])
                            await page.get_by_label('索引文章',exact=True).select_option(post['id'])
                            await save(page.get_by_role('button',name='加入栏目索引',exact=True))
                            entry=page.locator(f'[data-index="{meta["column"]}"] [data-index-post="{post["id"]}"]')
                            if index==0:
                                await save(entry.get_by_role('button',name='移出索引',exact=True))
                                await expect(entry).to_have_count(0)
                                await save(page.get_by_role('button',name='加入栏目索引',exact=True))
                            await entry.get_by_role('link',name=post['title'],exact=True).click()
                            await expect(page.locator('.publication-body h1')).to_have_text(item['name'])
                        snap=await snapshot();result=v2.evaluate(state,snap['state'],variant,snap['events']);assert result['success'],result
                        await nav('栏目索引');await expect(page.locator('[data-index-post]')).to_have_count(len(expected))
                        await page.screenshot(path=str(out/f'{task}-{variant}-index.png'),full_page=True)
                        await page.reload();await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                        snap=await snapshot();assert v2.evaluate(state,snap['state'],variant,snap['events'])['success']
                        assert not errors,errors
                        results.append(dict(task=task,variant=variant,seed=10001,suite='v2',mode='eval',surface='native',status='passed',persisted=True,published_articles=len(expected),author_links=task==42))
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
