"""Screening acceptance through native controls, playback and real CSV download."""
import asyncio,base64,json,os,secrets,sys
from pathlib import Path
import httpx,uvicorn
from playwright.async_api import async_playwright,expect
from vic import v2,v2_screening
from vic.config import ROOT
from vic_apps.server import create_app


async def main():
    variants=sys.argv[1] if len(sys.argv)>1 else 'ABC'
    out=ROOT/'.local/v2-screening-ui';out.mkdir(parents=True,exist_ok=True)
    secret=secrets.token_hex(32)
    os.environ.update(VIC_APP_DATA=str(out/'data'),VIC_APP_RUNTIME_TOKEN=secret,VIC_NATIVE_SELF_BASE='http://127.0.0.1:8782')
    server=uvicorn.Server(uvicorn.Config(create_app(),host='127.0.0.1',port=8782,log_level='error'));serving=asyncio.create_task(server.serve())
    while not server.started:await asyncio.sleep(.05)
    results=[]
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8782',headers={'Authorization':'Bearer '+secret},trust_env=False,timeout=120) as client,async_playwright() as p:
        browser=await p.chromium.launch()
        try:
            for variant in variants:
                state=v2.generate(35,10001,'eval');rid=secrets.token_hex(16);token=secrets.token_hex(32)
                r=await client.post('/internal/prepare',json=dict(run_id=rid,token=token,app='media',epoch=0,state=state));r.raise_for_status()
                context=await browser.new_context(viewport={'width':1440,'height':1050});page=await context.new_page();page.set_default_timeout(15000)
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                async def snapshot():
                    r=await client.get('/internal/runs/'+rid);r.raise_for_status();return r.json()
                async def action(locator):
                    async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')) as pending:await locator.click()
                    r=await pending.value;assert r.status==200,await r.text()
                async def nav(name):await page.locator('.product-nav').get_by_role('button',name=name,exact=True).click()
                try:
                    await page.goto(f'http://127.0.0.1:8782/native/product/media/{rid}#{token}')
                    await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                    await page.screenshot(path=str(out/f'35-{variant}-home.png'))
                    await page.get_by_role('button',name='查看活动计划 →',exact=True).click()
                    await expect(page.locator('[data-replacement]')).to_have_count(2)
                    await page.get_by_role('button',name='打开来源收藏夹',exact=True).click()
                    if variant=='A':
                        await nav('视频资料库')
                        await page.get_by_label('搜索影片',exact=True).fill('FILM-014')
                        await expect(page.locator('[data-video]')).to_have_count(1)
                        await action(page.get_by_role('button',name='加入队列',exact=True))
                        await nav('播放队列');await expect(page.locator('[data-queue-video]')).to_have_count(1)
                        await action(page.get_by_role('button',name='移出队列',exact=True))
                        await nav('收藏夹')
                    for f in state['world']['folders']:
                        card=page.locator(f'[data-folder="{f["id"]}"]')
                        await card.get_by_role('button',name='查看片单',exact=True).click()
                        await expect(page.locator('[data-video]')).to_have_count(len(f['members']))
                        await action(page.get_by_role('button',name='汇入播放队列',exact=True))
                        await nav('收藏夹')
                    # Re-import must not duplicate queue members.
                    await action(page.locator('[data-folder="folder-1"]').get_by_role('button',name='汇入播放队列',exact=True))
                    await nav('播放队列');await expect(page.locator('[data-queue-video]')).to_have_count(11)
                    event=state['world']['event']
                    for entry in event['exclude']:
                        await action(page.locator(f'[data-queue-video="{entry["video"]}"]').get_by_role('button',name='移出队列',exact=True))
                    for entry in event['replacements']:
                        row=page.locator(f'[data-queue-video="{entry["old"]}"]')
                        await row.locator('select').select_option(entry['new'])
                        await action(row.get_by_role('button',name='替换影片',exact=True))
                        await expect(page.locator(f'[data-queue-video="{entry["new"]}"]')).to_be_visible()
                        await expect(row).to_have_count(0)
                    expected=v2_screening.final_queue(state,variant)
                    for i,id in enumerate(expected):
                        row=page.locator(f'[data-queue-video="{id}"]')
                        await row.locator('input[type=number]').fill(str(i+1))
                        await action(row.get_by_role('button',name='移动',exact=True))
                    await page.get_by_label('队列名称',exact=True).fill(event['title'])
                    await action(page.get_by_role('button',name='保存名称',exact=True))
                    await action(page.get_by_role('button',name='保存播放队列',exact=True))
                    assert await page.locator('[data-queue-video]').evaluate_all('(rows)=>rows.map(r=>r.dataset.queueVideo)')==expected
                    await page.get_by_role('button',name='从头播放队列',exact=True).click()
                    video=page.locator('video')
                    await page.wait_for_function('document.querySelector("video")?.readyState >= 2',timeout=120000)
                    assert abs(await video.evaluate('(v)=>v.duration')-state['domain']['objects'][expected[0]]['duration'])<1
                    if await video.evaluate('(v)=>v.paused'):await video.press('Space')
                    await page.wait_for_function('document.querySelector("video")?.currentTime > 0',timeout=10000)
                    await page.screenshot(path=str(out/f'35-{variant}-player.png'))
                    await page.get_by_role('button',name='下一部',exact=True).click()
                    await expect(page.get_by_role('heading',name=state['domain']['objects'][expected[1]]['name'],exact=True)).to_be_visible()
                    await page.wait_for_function('document.querySelector("video")?.readyState >= 2',timeout=120000)
                    assert abs(await video.evaluate('(v)=>v.duration')-state['domain']['objects'][expected[1]]['duration'])<1
                    await page.get_by_role('button',name='上一部',exact=True).click()
                    await expect(page.get_by_role('heading',name=state['domain']['objects'][expected[0]]['name'],exact=True)).to_be_visible()
                    await page.get_by_role('button',name='← 返回播放队列',exact=True).click()
                    await page.get_by_role('button',name='编排放映时间',exact=True).click()
                    await page.get_by_label('开场时间',exact=True).fill(event['starts_at'][:16])
                    await page.get_by_label('换片秒数',exact=True).fill(str(event['turnaround_seconds']))
                    for entry in event['breaks']:
                        await page.get_by_label('休息位置',exact=True).select_option(entry['after'])
                        await page.get_by_label('休息秒数',exact=True).fill(str(entry['seconds']))
                        await page.get_by_role('button',name='添加休息',exact=True).click()
                    await expect(page.locator('[data-break]')).to_have_count(2)
                    if variant=='A':
                        entry=event['breaks'][0]
                        await page.locator(f'[data-break="{entry["after"]}"]').get_by_role('button',name='移除休息',exact=True).click()
                        await expect(page.locator('[data-break]')).to_have_count(1)
                        await page.get_by_label('休息位置',exact=True).select_option(entry['after'])
                        await page.get_by_label('休息秒数',exact=True).fill(str(entry['seconds']))
                        await page.get_by_role('button',name='添加休息',exact=True).click()
                    await action(page.get_by_role('button',name='保存时间设置',exact=True))
                    await page.get_by_label('换片秒数',exact=True).fill('31')
                    await expect(page.get_by_role('button',name='生成并保存时间表',exact=True)).to_be_disabled()
                    await page.get_by_label('换片秒数',exact=True).fill(str(event['turnaround_seconds']))
                    await action(page.get_by_role('button',name='生成并保存时间表',exact=True))
                    await expect(page.locator('[data-schedule-video]')).to_have_count(9)
                    if variant=='A':
                        await nav('播放队列')
                        await action(page.locator(f'[data-queue-video="{expected[0]}"]').get_by_role('button',name='下移 '+state['domain']['objects'][expected[0]]['name'],exact=True))
                        await action(page.get_by_role('button',name='保存播放队列',exact=True));await nav('放映时间表')
                        await expect(page.locator('.screening-stale')).to_be_visible()
                        await nav('播放队列')
                        await action(page.locator(f'[data-queue-video="{expected[0]}"]').get_by_role('button',name='上移 '+state['domain']['objects'][expected[0]]['name'],exact=True))
                        await action(page.get_by_role('button',name='保存播放队列',exact=True));await nav('放映时间表')
                        await action(page.get_by_role('button',name='生成并保存时间表',exact=True))
                    await expect(page.locator('.screening-stale')).to_have_count(0)
                    snap=await snapshot();result=v2.evaluate(state,snap['state'],variant,snap['events']);assert result['success'],result
                    schedule=snap['state']['world']['schedule']
                    for row in schedule['rows']:
                        ui=page.locator(f'[data-schedule-video="{row["video"]}"]')
                        await expect(ui).to_contain_text(row['starts_at'][11:19]);await expect(ui).to_contain_text(row['ends_at'][11:19])
                    await page.screenshot(path=str(out/f'35-{variant}-schedule.png'),full_page=True)
                    file=snap['state']['domain']['files']['screening-timetable']
                    async with page.expect_download() as pending:await page.get_by_role('button',name='下载 CSV 时间表',exact=True).click()
                    downloaded=await pending.value;assert await downloaded.failure() is None
                    assert Path(await downloaded.path()).read_bytes()==base64.b64decode(file['content'])
                    await page.get_by_role('link',name='打开时间表文件',exact=True).click()
                    await expect(page.locator('.screening-file')).to_have_text(base64.b64decode(file['content']).decode())
                    await page.reload();await expect(page.locator('.screening-file')).to_be_visible()
                    snap=await snapshot();assert v2.evaluate(state,snap['state'],variant,snap['events'])['success']
                    assert not errors,errors
                    results.append(dict(task=35,variant=variant,seed=10001,suite='v2',mode='eval',status='passed',surface='native',persisted=True,queue_members=9,replacements=2,breaks=2,real_csv_download=True,playback_verified=True))
                    print(f'35{variant} PASS',flush=True)
                except Exception as exc:
                    results.append(dict(task=35,variant=variant,seed=10001,status='failed',error=str(exc),page_errors=errors));print(f'35{variant} FAIL {exc} {errors}',flush=True)
                    await page.screenshot(path=str(out/f'35-{variant}-failed.png'))
                finally:
                    with (out/'history.jsonl').open('a') as f:f.write(json.dumps(results[-1],ensure_ascii=False)+'\n')
                    await context.close();await client.delete('/internal/runs/'+rid)
        finally:
            await browser.close();server.should_exit=True;await serving
    (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    if any(r['status']=='failed' for r in results):raise SystemExit(1)


if __name__=='__main__':asyncio.run(main())
