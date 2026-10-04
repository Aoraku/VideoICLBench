"""Browser regression for v2 portal controls with mocked API; never records video.

Start portal Vite first, then run with --base pointing at that development server.
This checks portal behavior only; native workflows are checked separately.
"""
import argparse,asyncio,json
from urllib.parse import urlsplit
from pathlib import Path
from playwright.async_api import async_playwright,expect
async def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--base',default='http://127.0.0.1:18991')
 parser.add_argument('--output',default='.local/v2-portal-refresh')
 args=parser.parse_args()
 base=args.base.rstrip('/');out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True)
  context=await browser.new_context(viewport={'width':1440,'height':1050})
  await context.add_init_script("sessionStorage.setItem('vic-manager','test-only');window.captureCalls=0;Object.defineProperty(navigator.mediaDevices,'getDisplayMedia',{value:()=>{window.captureCalls++;throw Error('Capture forbidden in preview test')}})")
  tasks=json.loads(Path('tasks/v2/catalog.json').read_text())['tasks']
  for t in tasks:t['status']='application-ready'
  runs={};calls=[]
  async def route(r):
   path=urlsplit(r.request.url).path;method=r.request.method
   if path.startswith('/native/'):
    return await r.fulfill(content_type='text/html',body='<h1>Native application test fixture</h1>')
   if not path.startswith(('/v1/','/v2/')):return await r.continue_()
   body=r.request.post_data_json if method=='POST' else None
   calls.append((path,body))
   if path in ['/v1/tasks','/v2/tasks']:data={'tasks':tasks}
   elif path=='/v1/capabilities':data={'direct_application_modules':['chat']}
   elif path=='/v1/runs':
    rid=f'{len(runs)+1:032x}';data={**body,'id':rid,'epoch':0,'status':'ready','application_url':f'{base}/apps/chat/{rid}#test','lesson':{'total':2,'finished':False} if body['mode']=='demo' else None};runs[rid]=data
   elif path.endswith('/reset'):
    rid=path.split('/')[3];data={**runs[rid],'epoch':runs[rid]['epoch']+1,'status':'ready','result':None};runs[rid]=data
   elif path.endswith('/eval'):data={'success':True,'completion':1,'violations':[]}
   elif path.startswith('/v1/runs/'):data=runs[path.split('/')[3]]
   else:data={}
   await r.fulfill(json=data)
  await context.route('**/*',route)
  page=await context.new_page();await page.goto(base)
  await page.get_by_role('button',name='v2 list',exact=True).click()
  await expect(page.locator('.v2-list tbody tr')).to_have_count(75)
  await page.get_by_role('button',name='任务序号').click()
  await expect(page.locator('.v2-list tbody tr').first).to_contain_text('075')
  await page.get_by_role('button',name='任务序号').click()
  await expect(page.locator('.v2-list tbody tr').first).to_contain_text('001')
  await page.get_by_role('button',name='难度',exact=False).first.click()
  first=await page.locator('.v2-list tbody tr').first.inner_text();assert '低' in first
  await page.get_by_role('button',name='难度',exact=False).first.click()
  first=await page.locator('.v2-list tbody tr').first.inner_text();assert '高' in first
  await page.get_by_role('button',name='平台',exact=False).first.click()
  await expect(page.locator('th[aria-sort="ascending"]')).to_contain_text('平台')
  await page.get_by_role('button',name='平台',exact=False).first.click()
  await expect(page.locator('th[aria-sort="descending"]')).to_contain_text('平台')
  await page.get_by_label('筛选平台').select_option('Chat')
  assert await page.locator('.v2-list tbody tr').count()<75
  await page.get_by_label('筛选平台').select_option('all')
  await page.get_by_label('搜索 v2 任务').fill('001')
  await page.locator('.v2-list tbody tr button').click()
  await expect(page.get_by_text('录制时依次完成')).to_be_visible()
  async with context.expect_page() as popup:
   await page.get_by_role('button',name='预览示范环境').click()
  demo=await popup.value;await demo.wait_for_url('**/native/chat/**')
  assert await page.evaluate('window.captureCalls')==0
  assert next(iter(runs.values()))['mode']=='demo'
  await page.get_by_role('button',name='检查示范结果').click()
  await expect(page.get_by_role('alert')).to_contain_text('完成全部示范练习')
  assert not any(path.endswith('/eval') for path,_ in calls)
  await page.get_by_role('button',name='重置示范',exact=True).click()
  await expect(page.get_by_role('status')).to_contain_text('恢复初态')
  await demo.wait_for_url('**/*vic_reset=1*')
  await page.get_by_role('tab',name='执行 · inference').click()
  await expect(page.get_by_text('最终交付',exact=True)).to_be_visible()
  async with context.expect_page() as popup:
   await page.get_by_role('button',name='打开执行环境').click()
  inference=await popup.value;await inference.wait_for_url('**/native/chat/**')
  assert list(runs.values())[-1]['mode']=='eval'
  assert len(runs)==2 and await page.evaluate('window.captureCalls')==0
  await page.get_by_role('button',name='检查最终交付',exact=True).click()
  await expect(page.get_by_text('检查通过',exact=True)).to_be_visible()
  await expect(page.get_by_role('button',name='检查最终交付',exact=True)).to_be_disabled()
  await page.get_by_role('button',name='重置执行环境',exact=True).click()
  await expect(page.get_by_role('button',name='检查最终交付',exact=True)).to_be_enabled()
  await inference.wait_for_url('**/*vic_reset=1*')
  await page.get_by_label('搜索 v2 任务').fill('')
  await page.screenshot(path=str(out/'inference.png'),full_page=True)
  await page.get_by_role('tab',name='示范 · demo').click()
  await page.screenshot(path=str(out/'demo.png'),full_page=True)
  await page.set_viewport_size({'width':720,'height':1000})
  assert await page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
  await page.screenshot(path=str(out/'mobile.png'),full_page=True)
  await browser.close()
  print('PASS:75 cards, all six sort directions, platform filter, demo no-capture preview, independent inference, both resets, final check, unfinished-demo guard, responsive width')
if __name__=='__main__':
 asyncio.run(main())
