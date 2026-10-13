"""Press real Tab keys in the native OJ and verify the saved source bytes."""
import asyncio,json,os,secrets
from pathlib import Path
import httpx,uvicorn
from playwright.async_api import async_playwright,expect
from vic import business,v2
from vic.lessons import native_path
from vic_apps.server import create_app

async def main():
    out=Path('.local/code-tab-ui');out.mkdir(parents=True,exist_ok=True)
    base='http://127.0.0.1:8796';secret=secrets.token_hex(32)
    os.environ.update(VIC_APP_DATA=str(out/'data'),VIC_APP_RUNTIME_TOKEN=secret,VIC_NATIVE_SELF_BASE=base)
    server=uvicorn.Server(uvicorn.Config(create_app(),host='127.0.0.1',port=8796,log_level='error'))
    serving=asyncio.create_task(server.serve())
    while not server.started:await asyncio.sleep(.05)
    try:
      async with httpx.AsyncClient(base_url=base,headers={'Authorization':'Bearer '+secret},trust_env=False,timeout=90) as client,async_playwright() as p:
        browser=await p.chromium.launch(channel=os.environ.get('VIC_BROWSER_CHANNEL') or None)
        try:
          for mode in ('demo','eval'):
            state=v2.generate(58,0 if mode=='demo' else 10001,mode);rid=secrets.token_hex(16);token=secrets.token_hex(32)
            (await client.post('/internal/prepare',json=dict(run_id=rid,token=token,app='code',epoch=0,state=state))).raise_for_status()
            context=await browser.new_context(viewport={'width':1440,'height':1000});page=await context.new_page();page.set_default_timeout(30000)
            await context.add_init_script("navigator.mediaDevices.getDisplayMedia=()=>{throw Error('No recording in QA')}")
            try:
              await page.goto(base+native_path('code',rid)+'#'+token)
              await expect(page.get_by_role('heading',name='题目列表',exact=True)).to_be_visible(timeout=90000)
              if mode=='demo':
                await page.get_by_role('button',name='我的代码与笔记',exact=True).click()
                editor=page.get_by_role('textbox',name='编辑源代码',exact=True)
                wanted=business.transform(58,2,state);save='提交代码'
              else:
                from vic.v2_code_projects import target_files
                entry=state['world']['entries'][0]
                await page.get_by_role('button',name='查看本课程清单',exact=True).click()
                await page.get_by_role('button',name='打开 '+entry['id'],exact=True).click()
                editor=page.get_by_role('textbox',name='编辑 solution.py',exact=True)
                wanted=target_files(state,entry,'C')['solution.py'];save='保存全部文件'
              await expect(editor).to_be_visible()
              # Ordinary form fields retain normal focus navigation. Code Tab is
              # literal, supports block outdent, and Esc+Tab releases focus.
              await editor.fill('one\ntwo');await editor.press('ControlOrMeta+A');await editor.press('Tab')
              await expect(editor).to_have_value('\tone\n\ttwo');await expect(editor).to_be_focused()
              await editor.press('Shift+Tab');await expect(editor).to_have_value('one\ntwo')
              await editor.press('Escape');await editor.press('Tab');await expect(editor).not_to_be_focused()
              await editor.fill('')
              for i,line in enumerate(wanted.split('\n')):
                if i:await editor.press('Enter')
                prefix=len(line)-len(line.lstrip('\t'))
                for _ in range(prefix):await editor.press('Tab');await expect(editor).to_be_focused()
                if line[prefix:]:await page.keyboard.insert_text(line[prefix:])
              await expect(editor).to_have_value(wanted)
              await page.get_by_role('button',name=save,exact=True).click()
              for _ in range(100):
                envelope=(await client.get('/internal/runs/'+rid)).json();final=envelope['state']
                actual=final['outputs'].get('target') if mode=='demo' else final['world']['drafts'].get(entry['id'],{}).get('solution.py')
                if actual==wanted:break
                await asyncio.sleep(.1)
              assert actual==wanted and '\t' in actual,(mode,actual,wanted)
              if mode=='demo':assert business.evaluate(state,final,'C',envelope['events'])['success']
              else:
                await page.get_by_role('button',name='运行本地检查与测试',exact=True).click()
                await expect(page.get_by_role('heading',name='CHK-0001',exact=True)).to_be_visible(timeout=60000)
              await page.screenshot(path=str(out/(mode+'.png')))
              print('PASS 058 C',mode,'Tab focus, multi-line indent/outdent, saved literal tabs',flush=True)
            finally:await context.close();await client.delete('/internal/runs/'+rid)
        finally:await browser.close()
    finally:server.should_exit=True;await serving
if __name__=='__main__':asyncio.run(main())
