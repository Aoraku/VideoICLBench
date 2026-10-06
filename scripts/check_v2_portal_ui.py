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
   body=r.request.post_data_json if method=='POST' and 'application/json' in r.request.headers.get('content-type','') else None
   calls.append((path,body))
   if path in ['/v1/tasks','/v2/tasks']:data={'tasks':tasks}
   elif path=='/v1/capabilities':data={'direct_application_modules':['chat']}
   elif path=='/v1/recordings':data=[r for r in runs.values() if r.get('recording')]
   elif path=='/v1/runs':
    rid=f'{len(runs)+1:032x}';data={**body,'id':rid,'epoch':0,'status':'ready','application_url':f'{base}/apps/chat/{rid}#test','manifest':{'suite':'v2'},'created_at':'2026-10-06T12:00:00Z','lesson':{'total':2,'finished':False} if body['mode']=='demo' else None};runs[rid]=data
   elif path.endswith('/reset'):
    rid=path.split('/')[3];data={**runs[rid],'epoch':runs[rid]['epoch']+1,'status':'ready','result':None};runs[rid]=data
   elif path.endswith(('/eval','/evaluate')):
    data={'success':True,'completion':1,'violations':[]}
    if path.endswith('/evaluate'):runs[path.split('/')[3]].update(result=data,status='completed')
   elif path.endswith('/recordings/upload'):
    data={'status':'pending_review','available':True,'contract_current':True};runs[path.split('/')[3]]['recording']=data
   elif path.endswith('/recordings/metadata'):data=runs[path.split('/')[3]].get('recording',{})
   elif path.endswith('/recordings/video'):return await r.fulfill(content_type='video/mp4',body=b'UI-test-placeholder')
   elif path.endswith('/recordings/review'):
    data={**body,'status':'approved','available':True,'contract_current':True};runs[path.split('/')[3]]['recording']=data
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
  # A demo card must never inherit the long inference assignment in its header.
  for task_id in [2,43,74]:
   await page.get_by_label('搜索 v2 任务').fill(f'{task_id:03d}')
   await page.locator('.v2-list tbody tr button').click()
   await page.get_by_role('tab',name='示范 · demo').click()
   task=next(t for t in tasks if t['id']==task_id)
   await expect(page.locator('.v2-card-header h2')).to_have_text(task['demo']['title'])
   await expect(page.locator('.v2-card-header>p')).to_have_text(task['demo']['objective'])
   await expect(page.get_by_label('示范完成标准',exact=True)).to_be_visible()
   assert task['assignment'] not in await page.locator('.v2-detail').inner_text()
   if task_id==74:await expect(page.get_by_role('tabpanel')).to_contain_text('本组只选择一个合法位置落子')
   await page.screenshot(path=str(out/f'{task_id:03d}-demo.png'),full_page=True)
   await page.get_by_role('tab',name='执行 · inference').click()
   await expect(page.locator('.v2-card-header>p')).to_have_text(task['assignment'])
   await expect(page.get_by_label('执行完成标准',exact=True)).to_be_visible()
   if task_id==2:
    await expect(page.get_by_role('tabpanel')).to_contain_text('左下角“参会人员名册”')
    await expect(page.get_by_role('tabpanel')).to_contain_text('关联业务资料')
   await page.screenshot(path=str(out/f'{task_id:03d}-inference.png'),full_page=True)
  # Capture permission requires its own deliberate click after an actual app
  # tab exists. Upload/evaluation/review APIs are mocked; no video is recorded.
  await page.get_by_label('搜索 v2 任务').fill('059')
  await page.locator('.v2-list tbody tr button').click()
  await page.get_by_role('tab',name='示范 · demo').click()
  async with context.expect_page() as pending:
   await page.get_by_role('button',name='开始录制',exact=True).click()
  target=await pending.value;await target.wait_for_url('**/native/**')
  assert await page.evaluate('window.captureCalls')==0
  await expect(page.get_by_role('button',name='选择应用画面并开始录制',exact=True)).to_be_visible()
  assert not await page.locator('.v2-rule').count()
  await page.locator('input[type=file]').set_input_files({'name':'mock.webm','mimeType':'video/webm','buffer':b'UI test only; not a recording'})
  await expect(page.get_by_label('自动检查结果')).to_contain_text('完成度 100%')
  await page.get_by_label('审核人',exact=True).fill('测试审核人')
  await page.get_by_label('录制检查备注').fill('模拟上传与审核接口，未录制视频。')
  await expect(page.get_by_role('button',name='确认录像完整并审核通过')).to_be_enabled()
  await page.get_by_role('button',name='确认录像完整并审核通过').click()
  await expect(page.get_by_role('button',name='已审核通过')).to_be_visible()
  assert any(path.endswith('/evaluate') for path,_ in calls)
  assert any(path.endswith('/recordings/review') for path,_ in calls)
  await page.screenshot(path=str(out/'recording-review.png'),full_page=True)
  await page.get_by_role('button',name='返回任务说明',exact=True).click()
  # Leaving the card and reloading the entire portal both restore server state.
  await page.get_by_label('搜索 v2 任务').fill('002')
  await page.locator('.v2-list tbody tr button').click()
  await page.get_by_label('搜索 v2 任务').fill('059')
  await page.locator('.v2-list tbody tr button').click()
  await expect(page.get_by_role('button',name='已审核通过',exact=True)).to_be_visible()
  await expect(page.get_by_role('link',name='下载服务器录像（MP4）')).to_be_visible()
  await page.reload()
  await page.get_by_role('button',name='v2 list',exact=True).click()
  await page.get_by_label('搜索 v2 任务').fill('059')
  await expect(page.locator('.recording-badge')).to_contain_text('A：已完成录制')
  await page.locator('.v2-list tbody tr button').click()
  await expect(page.get_by_role('button',name='已审核通过',exact=True)).to_be_visible()
  await expect(page.get_by_label('审核人',exact=True)).to_have_value('测试审核人')
  await page.get_by_role('button',name='版本 B',exact=True).click()
  assert await page.get_by_role('button',name='已审核通过',exact=True).count()==0
  await page.get_by_role('button',name='版本 A',exact=True).click()
  await expect(page.get_by_role('button',name='已审核通过',exact=True)).to_be_visible()
  count=len(runs)
  async with context.expect_page():
   await page.get_by_role('button',name='重新录制（保留已有录像）',exact=True).click()
  assert len(runs)==count+1
  assert len([r for r in runs.values() if r.get('recording',{}).get('approved')])==1
  await page.get_by_role('button',name='返回任务说明',exact=True).click()
  await page.get_by_role('button',name='录制记录',exact=True).click()
  await expect(page.get_by_label('全部录制记录')).to_contain_text('已完成录制 · 审核通过')
  await page.get_by_role('button',name='查看',exact=True).click()
  await expect(page.get_by_role('button',name='已审核通过',exact=True)).to_be_visible()
  await expect(page.get_by_role('link',name='下载服务器录像（MP4）')).to_be_visible()
  await page.get_by_role('button',name='返回任务列表',exact=True).click()
  legacy=next(r for r in runs.values() if r.get('recording',{}).get('approved'))
  runs['legacy-take']={**legacy,'id':'legacy-take','manifest':{'suite':'v1'}}
  await page.get_by_role('button',name='v1 list',exact=True).click()
  await page.get_by_label('搜索任务',exact=True).fill('59')
  await page.locator('.task-list tbody tr').click()
  await expect(page.get_by_role('button',name='已审核通过',exact=True)).to_be_visible()
  await page.reload()
  await page.get_by_role('button',name='v1 list',exact=True).click()
  await page.get_by_label('搜索任务',exact=True).fill('59')
  await page.locator('.task-list tbody tr').click()
  await expect(page.get_by_role('button',name='已审核通过',exact=True)).to_be_visible()
  await page.get_by_role('button',name='v2 list',exact=True).click()
  await page.set_viewport_size({'width':720,'height':1000})
  assert await page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
  await page.screenshot(path=str(out/'mobile.png'),full_page=True)
  await browser.close()
  print('PASS:75 cards, all six sort directions, platform filter, demo no-capture preview, independent inference, both resets, final check, unfinished-demo guard, persisted review after card switch/reload, variant isolation, retained takes on re-record, MP4 download, responsive width')
if __name__=='__main__':
 asyncio.run(main())
