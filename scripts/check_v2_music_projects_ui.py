"""Native Music → IM acceptance via real controls. No video recordings."""
import asyncio,json,os,secrets,sys
import httpx,uvicorn
from playwright.async_api import async_playwright,expect
from vic import v2,v2_music_projects
from vic.config import ROOT
from vic_apps.server import create_app


async def main():
    tasks=list(map(int,sys.argv[1].split(','))) if len(sys.argv)>1 else [18,28,32]
    variants=sys.argv[2] if len(sys.argv)>2 else 'ABC'
    out=ROOT/'.local/v2-music-projects-ui';out.mkdir(parents=True,exist_ok=True)
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
                    async def save(locator,navigate=True):
                        if navigate:
                            async with page.expect_navigation(wait_until='domcontentloaded'):
                                async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')) as pending:await locator.click()
                        else:
                            async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')) as pending:await locator.click()
                        r=await pending.value;assert r.status==200,await r.text()
                    async def nav(name):await page.locator('.sidebar').get_by_role('link',name=name,exact=True).click()
                    try:
                        await page.goto(f'http://127.0.0.1:8782/native/music/{rid}/#{token}')
                        await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                        await page.screenshot(path=str(out/f'{task}-{variant}-home.png'))
                        w=state['world'];objects=state['domain']['objects']
                        for index,activity in enumerate(w['activities'],1):
                            expected=v2_music_projects.desired(state,activity,variant)
                            key=f'list-{index:03d}'
                            await nav('活动筹备')
                            card=page.locator(f'[data-activity="{activity["id"]}"]')
                            await expect(card.get_by_role('heading',name=activity['name'],exact=True)).to_be_visible()
                            if task!=32:
                                await card.get_by_role('link',name='创建活动歌单',exact=True).click()
                                await page.get_by_text('新建播放列表',exact=True).click()
                                await page.get_by_label('所属活动',exact=True).select_option(activity['id'])
                                await page.get_by_label('歌单名称',exact=True).fill(activity['playlist_name'])
                                await save(page.get_by_role('button',name='创建歌单',exact=True))
                            else:
                                await card.get_by_role('link',name='打开 '+activity['playlist_name'],exact=True).click()
                            if task in (18,28):
                                for source in activity['sources']:
                                    await page.get_by_label('导入来源',exact=True).select_option(source)
                                    await save(page.get_by_role('button',name='导入歌曲',exact=True))
                                # Exercise physical ordering controls before the final sort.
                                if task==28:
                                    current=(await snapshot())['state']['world']['playlists'][key]['members']
                                    code=objects[current[0]]['record_code']
                                    await save(page.get_by_role('button',name='下移 '+code,exact=True))
                                    await save(page.get_by_role('button',name='上移 '+code,exact=True))
                                remove=activity['exclusions'] if task==18 else [x['id'] for x in state['items'] if not x['available']]
                                for target in remove:await page.get_by_role('checkbox',name='选择 '+objects[target]['record_code'],exact=True).check()
                                await save(page.get_by_role('button',name='移除所选歌曲',exact=True))
                                if task==18:
                                    await page.get_by_role('link',name='从资料库添加',exact=True).click()
                                    await page.get_by_label('目标歌单',exact=True).select_option(key)
                                    for target in activity['additions']:await page.get_by_role('checkbox',name='选择 '+objects[target]['record_code'],exact=True).check()
                                    await save(page.get_by_role('button',name='将所选歌曲加入歌单',exact=True),False)
                                    await expect(page.get_by_role('status')).to_contain_text('已加入目标歌单')
                                    await page.get_by_role('link',name='打开目标歌单',exact=True).click()
                                    await page.get_by_label('歌单名称',exact=True).fill(expected['name'])
                                    await save(page.get_by_role('button',name='更新名称',exact=True))
                                else:
                                    await page.get_by_label('排序',exact=True).select_option({'A':'year-asc','B':'duration-desc','C':'artist-desc'}[variant])
                                    await save(page.get_by_role('button',name='应用排序',exact=True))
                            else:
                                for source_id in activity['sources']:
                                    source=next(s for s in w['sources'] if s['id']==source_id)
                                    await nav('活动筹备')
                                    await page.locator(f'[data-activity="{activity["id"]}"]').get_by_role('link',name=source['name'],exact=True).click()
                                    await page.get_by_label('目标歌单',exact=True).select_option(key)
                                    current=(await snapshot())['state']['world']['playlists'][key]['members']
                                    eligible=[x for x in source['members'] if x in expected['members'] and x not in current]
                                    for target in eligible:await page.get_by_role('checkbox',name='选择 '+objects[target]['record_code'],exact=True).check()
                                    if eligible:
                                        await save(page.get_by_role('button',name='将所选歌曲加入歌单',exact=True),False)
                                        await expect(page.get_by_role('status')).to_contain_text('已加入目标歌单')
                                await page.get_by_role('link',name='打开目标歌单',exact=True).click()
                            await expect(page.locator('[data-song]')).to_have_count(len(expected['members']))
                            await save(page.get_by_role('button',name='保存歌单',exact=True))
                            await expect(page.locator('[data-saved="true"]')).to_be_visible()
                            await page.get_by_label('活动群',exact=True).select_option(str(activity['group_id']))
                            await save(page.get_by_role('button',name='发送到群聊',exact=True))
                            if index==1:
                                # Withdrawal and resend are real reversible actions.
                                await save(page.get_by_role('button',name='撤回分享',exact=True))
                                await expect(page.locator('[data-share]')).to_have_count(0)
                                await page.get_by_label('活动群',exact=True).select_option(str(activity['group_id']))
                                await save(page.get_by_role('button',name='发送到群聊',exact=True))
                            await page.screenshot(path=str(out/f'{task}-{variant}-playlist-{index}.png'),full_page=True)
                            await page.get_by_role('link',name='打开团队消息',exact=True).click()
                            await expect(page.get_by_role('region',name='工作范围')).to_contain_text('活动音乐协作')
                            await page.locator('.ant-list-item').filter(has_text=activity['group_name']).click()
                            share=page.get_by_role('article',name='分享的歌单')
                            await expect(share).to_contain_text(expected['name'])
                            await share.get_by_text('查看歌曲清单',exact=True).click()
                            await expect(share.locator('ol li')).to_have_count(len(expected['members']))
                            await share.get_by_text('查看本次新增',exact=True).click()
                            await expect(share.locator('ul li')).to_have_count(len(expected['added']))
                            await page.screenshot(path=str(out/f'{task}-{variant}-share-{index}.png'),full_page=True)
                            await share.get_by_role('link',name='打开歌单',exact=True).click()
                            await expect(page.get_by_role('heading',name=expected['name'],exact=True)).to_be_visible()
                            await expect(page.locator('[data-song]')).to_have_count(len(expected['members']))
                        snap=await snapshot();result=v2.evaluate(state,snap['state'],variant,snap['events']);assert result['success'],result
                        await page.reload();await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                        snap=await snapshot();assert v2.evaluate(state,snap['state'],variant,snap['events'])['success']
                        assert not errors,errors
                        results.append(dict(task=task,variant=variant,seed=10001,suite='v2',mode='eval',surface='native',status='passed',persisted=True,cross_app_links=True))
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
