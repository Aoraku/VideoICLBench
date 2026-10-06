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
 out=Path('.local/residual-native-ui');out.mkdir(parents=True,exist_ok=True)
 base='http://127.0.0.1:8786';secret=secrets.token_hex(32)
 os.environ.update(VIC_APP_DATA=str(out/'data'),VIC_APP_RUNTIME_TOKEN=secret,VIC_NATIVE_SELF_BASE=base)
 server=uvicorn.Server(uvicorn.Config(create_app(),host='127.0.0.1',port=8786,log_level='error'))
 serving=asyncio.create_task(server.serve())
 while not server.started:await asyncio.sleep(.05)
 try:
  async with httpx.AsyncClient(base_url=base,headers={'Authorization':'Bearer '+secret},timeout=60) as admin,async_playwright() as p:
   browser=await p.chromium.launch()
   try:
    for task,suite,mode in [(14,'v2','demo'),(22,'v2','demo'),(38,'v2','demo'),(49,'v2','demo'),(57,'v2','demo'),(39,'v2','eval'),(68,'v2','eval'),(72,'v2','demo')]:
     state=v2.generate(task,0 if mode=='demo' else 10001,mode) if suite=='v2' else initialize(business.generate(task,0))
     rid=secrets.token_hex(16);token=secrets.token_hex(32)
     (await admin.post('/internal/prepare',json=dict(run_id=rid,token=token,app=state['app'],epoch=0,state=state))).raise_for_status()
     context=await browser.new_context(viewport={'width':1440,'height':1050},timezone_id='Asia/Shanghai')
     page=await context.new_page();page.set_default_timeout(20000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     try:
      await page.goto(base+native_path(state['app'],rid)+'#'+token)
      if task==14:
       rows=page.locator('.list__itemWrap[data-object-id]')
       await expect(rows).to_have_count(len(state['items']))
       assert await rows.evaluate_all('(rows)=>rows.map(r=>r.dataset.objectId)')==[x['id'] for x in state['items']]
       await page.reload()
       await expect(rows).to_have_count(len(state['items']))
       assert await rows.evaluate_all('(rows)=>rows.map(r=>r.dataset.objectId)')==[x['id'] for x in state['items']]
      elif task in (22,38,49,57):
       await expect(page.get_by_label('任务参数',exact=True)).to_contain_text({22:'50 次',38:'50 个字符',49:'15 个字符',57:'50 元'}[task])
      elif task==39:
       for index in range(3):
        if index:
         await page.locator('#vic-work-batch button').nth(index).click()
        await page.locator('.product-nav').get_by_role('button',name='内容项目',exact=True).click()
        for item in state['work_batch']['units'][index]['state']['items']:
         await expect(page.get_by_text(item['text'],exact=True)).to_be_visible()
      elif task==68:
       await expect(page.get_by_text('按合并次数或得分比较时，多个有效方向并列最优可任选一个；每组只移动一次。',exact=True)).to_be_visible()
      else:
       await expect(page.get_by_text('候选格并列时先选行号最小者，同一行再选列号最小者。行从上到下、列从左到右编号。',exact=True)).to_be_visible()
      assert not errors,errors
      await page.screenshot(path=str(out/f'{task}-{suite}-{mode}.png'))
      print(f'{task:03d} {suite} {mode} PASS',flush=True)
     finally:
      await context.close();await admin.delete('/internal/runs/'+rid)
   finally:await browser.close()
 finally:
  server.should_exit=True;await serving
if __name__=='__main__':asyncio.run(main())
