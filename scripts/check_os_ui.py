"""Check current OS catalogue and real desktop inputs. Never capture video."""
import argparse,json,os
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect


def check(args):
 token=args.token_file.read_text().strip();args.output.mkdir(parents=True,exist_ok=True)
 with httpx.Client(base_url=args.base_url,headers={'Authorization':'Bearer '+token},trust_env=False,timeout=60) as api,sync_playwright() as p:
  response=api.get('/os-api/cases');response.raise_for_status();cases=response.json()['cases'];assert len(cases)==36
  browser=p.chromium.launch(channel=os.getenv('VIC_BROWSER_CHANNEL') or None)
  ctx=browser.new_context(viewport={'width':1440,'height':1000});page=ctx.new_page();errors=[]
  ctx.add_init_script("navigator.mediaDevices.getDisplayMedia=()=>Promise.reject(new DOMException('QA never captures video','NotAllowedError'))")
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(args.base_url);page.evaluate('(t)=>sessionStorage.setItem("vic-manager",t)',token);page.reload()
  page.get_by_role('button',name='OS · 36 题',exact=True).click();expect(page.get_by_text('OS-E-01',exact=True)).to_be_visible();page.get_by_text('OS-H-11',exact=True).click()
  expect(page.get_by_role('button',name='预览示范环境 ↗')).to_be_enabled();expect(page.get_by_text('4096、3660、3845',exact=False)).to_be_visible()
  page.screenshot(path=str(args.output/'recorder.png'),full_page=True)
  page.goto(args.base_url+'/review?kind=os');expect(page.locator('.review-list>button')).to_have_count(36)
  expect(page.get_by_text('批量规范文件名称',exact=True).last).to_be_visible();page.screenshot(path=str(args.output/'review.png'),full_page=True)
  checked=[]
  for case in cases:
   if args.cases and case['id'] not in args.cases:continue
   r=api.post('/os-api/runs',json={'case_id':case['id'],'mode':'eval','interaction':'human','seed':4201});r.raise_for_status();run=r.json()
   page.goto(args.base_url+run['application_url']);expect(page.locator('.desktop')).to_be_visible();assert page.locator('.brief').count()==0
   page.get_by_role('button',name='Start',exact=True).click();expect(page.locator('[data-command="task-info"]')).to_have_count(0)
   page.locator('.start-grid [data-open="files"]').click();expect(page.locator('.file-list')).to_be_visible()
   # All nine apps must render on a shared desktop, without a new task/environment.
   if case['id']=='OS-H-01':
    for app in ['editor','settings','scheduler','transfers','monitor','devices','events','terminal']:
     page.locator(f'.taskbar [data-open="{app}"]').click()
    expect(page.locator('.window')).to_have_count(9)
   result=api.post(f"/os-api/runs/{run['id']}/check",json={});result.raise_for_status();assert isinstance(result.json()['success'],bool)
   api.post(f"/os-api/runs/{run['id']}/eval",json={}).raise_for_status();checked.append(case['id'])
   print(case['id'],'desktop + persisted-state judge OK',flush=True)
  # Complete three local examples through actual Notepad UI, including navigation.
  r=api.post('/os-api/runs',json={'case_id':'OS-H-11','variant':'A','mode':'demo'});r.raise_for_status();run=r.json();page.goto(args.base_url+run['application_url'])
  for n,value in enumerate([4096,3660,3845]):
   expect(page.locator('.desktop')).to_be_visible();page.locator('.desktop-icons [data-open="editor"]').click()
   page.locator('[data-command="choose-document"]').click()
   expect(page.locator('select[name="target"]')).to_be_visible();options=page.locator('select[name="target"] option');labels=options.all_text_contents();label=next(s for s in labels if s.endswith('/Example result.txt'))
   page.locator('select[name="target"]').select_option(label=label);page.locator('.dialog button[type="submit"]').click()
   page.get_by_role('textbox',name='Document content',exact=True).fill(f'{value} B')
   with page.expect_response(lambda r:'/action' in r.url and r.request.method=='POST') as saved:page.get_by_role('button',name='Save',exact=True).click()
   assert saved.value.ok
   page.get_by_role('button',name=f'示范 {n+1}/3 · '+('完成练习' if n==2 else '下一组'),exact=True).click()
   if n<2:expect(page.get_by_role('button',name=f'示范 {n+2}/3 · '+('完成练习' if n==1 else '下一组'),exact=True)).to_be_visible()
  expect(page.get_by_role('button',name='示范已完成，请返回工作台保存和审核',exact=True)).to_be_visible()
  result=api.post(f"/os-api/runs/{run['id']}/check",json={});assert result.json()['success'] and result.json()['passed']==3
  page.screenshot(path=str(args.output/'notepad.png'));assert not errors,errors
  (args.output/'results.json').write_text(json.dumps({'catalogue':36,'ui_and_judge':checked,'local_examples_saved_through_ui':3,'video_recorded':False,'errors':errors},indent=2))
  browser.close();print('PASS human lesson navigation and persisted Notepad results; no video recorded',flush=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--base-url',default='http://127.0.0.1:18765');parser.add_argument('--token-file',type=Path,required=True);parser.add_argument('--cases',nargs='*');parser.add_argument('--output',type=Path,default=Path('.local/os36-ui'));check(parser.parse_args())
