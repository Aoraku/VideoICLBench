"""Focused native UI regressions from recorder feedback; never captures video."""
import asyncio,json,os,secrets
from pathlib import Path
import httpx,uvicorn
from playwright.async_api import async_playwright,expect
from vic import v2,business,games
from vic.lessons import native_path
from vic_apps.server import create_app

async def main():
    out=Path('.local/feedback-native-ui');out.mkdir(parents=True,exist_ok=True)
    base='http://127.0.0.1:8784';secret=secrets.token_hex(32)
    os.environ.update(VIC_APP_DATA=str(out/'data'),VIC_APP_RUNTIME_TOKEN=secret,VIC_NATIVE_SELF_BASE=base)
    server=uvicorn.Server(uvicorn.Config(create_app(),host='127.0.0.1',port=8784,log_level='error'))
    serving=asyncio.create_task(server.serve())
    while not server.started:await asyncio.sleep(.05)
    results=[]
    try:
      async with httpx.AsyncClient(base_url=base,headers={'Authorization':'Bearer '+secret},trust_env=False,timeout=60) as admin,async_playwright() as p:
        browser=await p.chromium.launch()
        try:
          for task,mode in [(19,'eval'),(20,'eval'),(17,'demo'),(39,'eval'),(34,'demo'),(74,'eval')]:
            state=v2.generate(task,0 if mode=='demo' else 10001,mode);rid=secrets.token_hex(16);token=secrets.token_hex(32)
            (await admin.post('/internal/prepare',json=dict(run_id=rid,token=token,app=state['app'],epoch=0,state=state))).raise_for_status()
            context=await browser.new_context(viewport={'width':1440,'height':1050})
            await context.add_init_script("navigator.mediaDevices.getDisplayMedia=()=>{throw Error('No capture in QA')}")
            page=await context.new_page();page.set_default_timeout(15000);errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            async def command(op,target='',value='',ids=[]):
                response=await admin.post('/api/runs/'+rid+'/commands',headers={'Authorization':'Bearer '+token},json=dict(epoch=0,action_id=secrets.token_hex(16),op=op,target=target,value=value,ids=ids));response.raise_for_status();return response.json()['state']
            try:
              await page.goto(base+native_path(state['app'],rid)+'#'+token)
              if task in (19,20):
                for index in range(3):
                  item=state['work_batch']['units'][index]['state']
                  await page.get_by_role('button',name='内容管理',exact=True).click()
                  await page.locator('textarea[name=text]').fill(business.transform(task,0,item))
                  async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')):
                    await page.get_by_role('button',name='保存草稿',exact=True).click()
                  await expect(page.get_by_text('✓ 草稿已保存',exact=True)).to_be_visible()
                  if index<2:
                    await page.locator('#vic-work-batch button').nth(index+1).click()
                    await expect(page.locator('.news-hero')).to_be_visible()
                    assert 'Application mismatch' not in await page.locator('body').inner_text()
              elif task==17:
                await expect(page.get_by_text('本组待整理',exact=True)).to_have_count(1)
                await page.locator('a[href$="songs/target/"]').first.click()
                await page.get_by_role('button',name='编辑显示名称',exact=True).click()
                await page.locator('input[name=name]').fill(business.transform(17,0,state))
                await page.get_by_role('button',name='保存名称',exact=True).click()
                await expect(page.get_by_text('✓ 名称已保存',exact=True)).to_be_visible()
              elif task==39:
                await expect(page.locator('#vic-work-batch button')).to_have_count(3)
                await page.locator('#vic-work-batch button').nth(2).click()
                await expect(page.locator('#vic-work-batch button').nth(2)).to_have_attribute('aria-pressed','true')
              elif task==34:
                await page.locator('.product-nav').get_by_role('button',name='稍后观看',exact=False).click()
                target=next(x for x in state['items'] if x['completed'])
                row=page.locator(f'[data-object-id="{target["id"]}"]')
                await expect(row).to_be_visible()
                await row.get_by_role('button',name='删除',exact=True).click()
                await expect(row).to_have_count(0)
                await page.locator('.product-nav').get_by_role('button',name='视频资料库',exact=False).click()
                await expect(row).to_have_count(0)
              else:
                await page.locator('.product-nav').get_by_role('button',name='继续练习',exact=False).click()
                point=games.expected(74,'A',state)
                await page.get_by_role('button',name=f'第{point[0]+1}行第{point[1]+1}列',exact=True).click()
                await expect(page.get_by_text('你的落子与翻转结果 · 即将显示对手落子',exact=True)).to_be_visible()
                await expect(page.get_by_role('button',name='回看我的落子后',exact=True)).to_be_visible(timeout=5000)
                await page.get_by_role('button',name='回看我的落子后',exact=True).click()
                await expect(page.get_by_role('button',name='查看对手落子后',exact=True)).to_be_visible()
              assert not errors,errors
              await page.screenshot(path=str(out/f'{task:03d}-{mode}.png'))
              results.append(dict(task=task,mode=mode,status='passed'));print(f'{task:03d} {mode} PASS',flush=True)
            finally:
              await context.close();await admin.delete('/internal/runs/'+rid)
        finally:await browser.close()
    finally:
      server.should_exit=True;await serving
      (out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
if __name__=='__main__':asyncio.run(main())
