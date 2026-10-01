"""Exercise the original Liugu OJ UI and download real code packages; no video."""
import asyncio,base64,json,os,secrets,sys
from pathlib import Path
import httpx,uvicorn
from playwright.async_api import async_playwright,expect
from vic import v2,v2_code_projects as rules
from vic.config import ROOT
from vic_apps.server import create_app


async def main():
    tasks=list(map(int,sys.argv[1].split(','))) if len(sys.argv)>1 else [58,60,64,65]
    variants=sys.argv[2] if len(sys.argv)>2 else 'ABC'
    out=ROOT/'.local/v2-code-projects-ui';out.mkdir(parents=True,exist_ok=True)
    secret=secrets.token_hex(32)
    os.environ.update(VIC_APP_DATA=str(out/'data'),VIC_APP_RUNTIME_TOKEN=secret,VIC_NATIVE_SELF_BASE='http://127.0.0.1:8782')
    server=uvicorn.Server(uvicorn.Config(create_app(),host='127.0.0.1',port=8782,log_level='error'));serving=asyncio.create_task(server.serve())
    while not server.started:await asyncio.sleep(.05)
    results=[]
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8782',headers={'Authorization':'Bearer '+secret},trust_env=False,timeout=60) as client,async_playwright() as p:
        browser=await p.chromium.launch()
        try:
            for task in tasks:
                for variant in variants:
                    initial=v2.generate(task,10001,'eval');w=initial['world'];rid=secrets.token_hex(16);token=secrets.token_hex(32)
                    r=await client.post('/internal/prepare',json=dict(run_id=rid,token=token,app='code',epoch=0,state=initial));r.raise_for_status()
                    context=await browser.new_context(viewport={'width':1440,'height':1050});page=await context.new_page();page.set_default_timeout(20000)
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    async def snapshot():
                        r=await client.get('/internal/runs/'+rid);r.raise_for_status();return r.json()
                    async def idle():
                        await page.wait_for_timeout(180)
                        await expect(page.locator('[data-testid="stApp"]')).to_have_attribute('data-test-script-state','notRunning',timeout=30000)
                        await expect(page.locator('[data-testid="stException"]')).to_have_count(0)
                    async def button(name):
                        await page.get_by_role('button',name=name,exact=True).click();await idle()
                    async def action(name):
                        before=len((await snapshot())['events']);await button(name)
                        for _ in range(100):
                            if len((await snapshot())['events'])>before:break
                            await asyncio.sleep(.1)
                        else:raise AssertionError('No persisted action after '+name)
                        await idle()
                    async def nav(name):
                        await page.locator('[data-testid="stSidebar"]').get_by_role('button',name=name,exact=True).click();await idle()
                    async def select(label,value):
                        await page.get_by_role('combobox',name=label,exact=True).click()
                        await page.get_by_role('option',name=value,exact=True).click();await idle()
                    async def download(label,id):
                        snap=await snapshot();expected=base64.b64decode(snap['state']['domain']['files'][id]['content'])
                        async with page.expect_download() as pending:await page.get_by_role('button',name=label,exact=True).click()
                        item=await pending.value;assert await item.failure() is None
                        assert Path(await item.path()).read_bytes()==expected
                        await idle()
                    async def open_entry(entry):
                        await nav('课程清单');await button('打开 '+entry['id'])
                        await expect(page.get_by_role('heading',name='项目工作区',exact=True)).to_be_visible()
                        await expect(page.get_by_role('combobox',name='课程条目',exact=True)).to_have_value(entry['id']+' · '+entry['title'])
                    try:
                        await page.goto(f'http://127.0.0.1:8782/native/code/{rid}/#{token}')
                        await expect(page.get_by_role('heading',name='题目列表',exact=True)).to_be_visible(timeout=60000);await idle()
                        await page.screenshot(path=str(out/f'{task}-{variant}-home.png'))
                        await button('查看本课程清单');await expect(page.get_by_role('heading',name='课程清单',exact=True)).to_be_visible()
                        await download('下载课程说明','course-readme')
                        for index,e in enumerate(w['entries']):
                            await nav('课程清单');await button('查看题目 '+e['id'])
                            problem=next(p for p in w['problems'] if p['id']==e['problem'])
                            await expect(page.get_by_role('heading',name='题目: '+problem['title'],exact=True)).to_be_visible()
                            await expect(page.get_by_text(problem['description'],exact=True)).to_be_visible()
                            await open_entry(e)
                            if task==64:
                                await button('选择历史版本');h=rules.chosen_version(initial,e,variant)
                                await action('恢复 '+h['id'])
                                await expect(page.get_by_role('textbox',name='编辑 solution.py',exact=True)).to_have_value(h['files']['solution.py'])
                            elif task in (58,60):
                                files=rules.target_files(initial,e,variant)
                                for name,code in files.items():
                                    await page.get_by_role('tab',name=name,exact=True).click()
                                    await page.get_by_role('textbox',name='编辑 '+name,exact=True).fill(code)
                                    await page.get_by_role('heading',name='项目工作区',exact=True).click();await idle()
                                await action('保存全部文件')
                                snap=await snapshot();assert snap['state']['world']['drafts'][e['id']]==files
                            else:
                                await expect(page.get_by_role('textbox',name='编辑 solution.py',exact=True)).to_be_disabled()
                            await action('运行本地检查与测试');snap=await snapshot()
                            checked=list(snap['state']['world']['checks'].values())[-1]
                            await expect(page.get_by_role('heading',name=checked['id'],exact=True)).to_be_visible()
                            if index==0:await page.screenshot(path=str(out/f'{task}-{variant}-editor.png'),full_page=True)
                            if rules.should_submit(initial,e,variant):
                                await action('提交当前代码');snap=await snapshot();sub=next(s for s in snap['state']['world']['submissions'].values() if s['entry']==e['id'])
                                await expect(page.get_by_text(sub['id']+' · 题目 '+e['problem']+' · '+sub['tests']['status'],exact=True)).to_be_visible()
                                await download('下载此提交代码包','submission-'+sub['id'])
                                if index==0 and variant=='A':
                                    await action('撤回此提交');await expect(page.get_by_role('button',name='提交当前代码',exact=True)).to_be_enabled()
                                    await action('提交当前代码')
                        await nav('检查记录');await expect(page.get_by_role('heading',name='检查记录',exact=True)).to_be_visible()
                        await page.locator('[data-testid="stExpander"] summary').first.click();await expect(page.get_by_role('heading',name=checked['id'],exact=True)).to_be_visible()
                        await nav('查看提交');await expect(page.get_by_role('heading',name='查看提交记录',exact=True)).to_be_visible()
                        await nav('交付中心');await button('读取当前记录');await action('保存交付清单')
                        await action('删除交付清单');await expect(page.get_by_role('button',name='下载课程代码交付包',exact=True)).to_have_count(0)
                        await action('保存交付清单');await action('发布交付包')
                        await expect(page.get_by_text('交付包已发布',exact=True)).to_be_visible()
                        await expect(page.get_by_role('button',name='保存交付清单',exact=True)).to_be_disabled()
                        await download('下载课程代码交付包','course-delivery');await download('下载交付清单','course-manifest')
                        await action('撤回交付发布');await action('发布交付包')
                        await page.screenshot(path=str(out/f'{task}-{variant}-delivery.png'),full_page=True)
                        await page.reload();await expect(page.get_by_role('heading',name='题目列表',exact=True)).to_be_visible(timeout=60000)
                        await nav('交付中心');await expect(page.get_by_text('交付包已发布',exact=True)).to_be_visible()
                        snap=await snapshot();result=v2.evaluate(initial,snap['state'],variant,snap['events']);assert result['success'],result
                        assert not errors,errors
                        results.append(dict(task=task,variant=variant,seed=10001,suite='v2',mode='eval',status='passed',surface='native-streamlit',persisted=True,real_downloads=True,entries=len(w['entries']),real_python_checks=True))
                        print(f'{task}{variant} PASS',flush=True)
                    except Exception as exc:
                        results.append(dict(task=task,variant=variant,status='failed',error=str(exc),page_errors=errors));print(f'{task}{variant} FAIL {exc} {errors}',flush=True)
                        await page.screenshot(path=str(out/f'{task}-{variant}-failed.png'))
                    finally:
                        (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
                        with (out/'history.jsonl').open('a') as file:file.write(json.dumps(results[-1],ensure_ascii=False)+'\n')
                        await context.close();await client.delete('/internal/runs/'+rid)
        finally:
            await browser.close();server.should_exit=True;await serving
    if any(r['status']=='failed' for r in results):raise SystemExit(1)


if __name__=='__main__':asyncio.run(main())
