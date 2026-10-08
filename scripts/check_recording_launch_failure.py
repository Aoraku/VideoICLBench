"""Check recording launch error/retry in a browser without capturing any screen."""
import argparse, asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright, expect

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://127.0.0.1:18965');args=parser.parse_args()
    async with async_playwright() as p:
        browser=await p.chromium.launch();context=await browser.new_context()
        await context.add_init_script("sessionStorage.setItem('vic-manager','test-only')")
        tasks=json.loads(Path('tasks/v2/catalog.json').read_text());task=tasks['tasks'][0];task['status']='application-ready'
        attempts=0
        async def route(r):
            nonlocal attempts
            path=r.request.url.split(args.base)[-1]
            if path in ('/v1/tasks','/v2/tasks'):return await r.fulfill(json={'tasks':[task]})
            if path=='/v1/capabilities':return await r.fulfill(json={'direct_application_modules':['chat']})
            if path=='/v1/recordings':return await r.fulfill(json=[])
            if path=='/v1/runs' and r.request.method=='POST':
                attempts+=1
                if attempts==1:return await r.fulfill(status=507,json={'detail':'服务器可用存储空间不足，请联系管理员。'})
                if attempts==2:return await r.fulfill(status=502,content_type='text/html',body='<h1>Bad Gateway</h1>')
                return await r.fulfill(status=201,json=dict(id='a'*32,task_id=1,variant='A',epoch=0,status='ready',mode='demo',lesson=dict(index=0,total=6,finished=False),application_url=args.base+'/apps/chat/'+'a'*32+'#test'))
            if '/native/' in path:return await r.fulfill(content_type='text/html',body='<h1>Application homepage</h1>')
            return await r.continue_()
        await context.route('**/*',route)
        page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(args.base)
        await page.get_by_role('button',name=f"001 {task['title']}",exact=True).click()
        for message in ('存储空间不足','HTTP 502'):
            async with context.expect_page() as popup:
                await page.get_by_role('button',name='开始录制',exact=True).click()
            opened=await popup.value
            await expect(page.locator('.v2-workspace').get_by_role('alert')).to_contain_text(message)
            assert not opened.is_closed()
            await expect(opened.locator('body')).to_contain_text(message)
            await expect(page.get_by_role('button',name='开始录制',exact=True)).to_be_enabled()
            await opened.close()
        async with context.expect_page() as popup:
            await page.get_by_role('button',name='开始录制',exact=True).click()
        opened=await popup.value
        await expect(opened.get_by_role('heading',name='Application homepage')).to_be_visible()
        await expect(page.get_by_role('button',name='选择应用画面并开始录制',exact=True)).to_be_visible()
        assert not errors,errors
        print('507/502 keep error page open; retry reaches application and screen selector; no capture performed: PASS')
        await browser.close()

if __name__=='__main__':asyncio.run(main())
