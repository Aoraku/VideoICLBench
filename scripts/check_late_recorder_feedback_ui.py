"""Native interaction regression; does not record video or modify user runs."""
import asyncio,json,os,secrets
from pathlib import Path
import httpx,uvicorn
from playwright.async_api import async_playwright,expect
from vic import v2,business
from vic.lessons import native_path
from vic_apps.domain import initialize
from vic_apps.server import create_app

async def main():
 out=Path('.local/late-recorder-ui');out.mkdir(parents=True,exist_ok=True)
 base='http://127.0.0.1:8785';secret=secrets.token_hex(32)
 os.environ.update(VIC_APP_DATA=str(out/'data'),VIC_APP_RUNTIME_TOKEN=secret,VIC_NATIVE_SELF_BASE=base)
 server=uvicorn.Server(uvicorn.Config(create_app(),host='127.0.0.1',port=8785,log_level='error'))
 serving=asyncio.create_task(server.serve())
 while not server.started:await asyncio.sleep(.05)
 try:
  async with httpx.AsyncClient(base_url=base,headers={'Authorization':'Bearer '+secret},timeout=60) as admin,async_playwright() as p:
   browser=await p.chromium.launch(channel=os.environ.get('VIC_BROWSER_CHANNEL'))
   try:
    for task,suite,mode in [(14,'v1','demo'),(14,'v2','eval'),(16,'v2','demo'),(56,'v2','demo'),(22,'v2','eval')]:
     state=v2.generate(task,0 if mode=='demo' else 10001,mode) if suite=='v2' else initialize(business.generate(task,0))
     rid=secrets.token_hex(16);token=secrets.token_hex(32)
     (await admin.post('/internal/prepare',json=dict(run_id=rid,token=token,app=state['app'],epoch=0,state=state))).raise_for_status()
     context=await browser.new_context(viewport={'width':1440,'height':1050},timezone_id='Asia/Shanghai')
     page=await context.new_page();page.set_default_timeout(20000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     try:
      await page.goto(base+native_path(state['app'],rid)+'#'+token)
      if task==14:
       row=page.locator('.list__itemWrap[data-object-id]').first
       await expect(row).to_be_visible();target=await row.get_attribute('data-object-id');row=page.locator(f'[data-object-id="{target}"]')
       for label,field,expected in [('归档会话','archived',True),('取消归档','archived',False),('置顶会话','pinned',True),('取消置顶','pinned',False),('消息免打扰','muted',True),('关闭免打扰','muted',False)]:
        await row.click(button='right')
        async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')):
         await page.get_by_role('menuitem',name=label,exact=True).click()
        current=(await admin.get('/api/runs/'+rid,headers={'Authorization':'Bearer '+token})).json()['state']
        assert current['domain']['objects'][target][field] is expected
       await row.locator('button.list__item').click()
       source=next(x for x in state['items'] if x['id']==target)['created_at'][:16].replace('T',' ')+' UTC'
       await expect(page.locator('.bubble__time').first).to_have_text(source)
       await expect(row).to_contain_text(source)
      elif task==16:
       await expect(page.get_by_role('listitem').first).to_be_visible()
       await expect(page.get_by_label('工作范围',exact=True)).to_have_count(0)
       assert '固定回复正文' not in await page.locator('body').inner_text()
      elif task==56:
       await expect(page.locator('.product')).to_be_visible()
       assert '指定字母' not in await page.locator('body').inner_text()
       assert '金额阈值' not in await page.locator('body').inner_text()
      else:
       await page.get_by_role('link',name='2',exact=True).click();await page.wait_for_url('**/?page=2')
       await page.locator('a.song-title').first.click();await page.wait_for_url('**/songs/**')
       await page.locator('[data-label-open]').click()
       async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')):
        await page.locator('[data-label="长"]').click()
       await page.locator('[data-song-list]').click();await page.wait_for_url('**/?page=2')
       await expect(page.locator('.page-item.active')).to_have_text('2')
      assert not errors,errors
      await page.screenshot(path=str(out/f'{task}-{suite}-{mode}.png'))
      print(f'{task:03d} {suite} {mode} PASS',flush=True)
     finally:
      await context.close();await admin.delete('/internal/runs/'+rid)
   finally:await browser.close()
 finally:
  server.should_exit=True;await serving
if __name__=='__main__':asyncio.run(main())
