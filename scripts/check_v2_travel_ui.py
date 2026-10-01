"""Native travel acceptance: actual forms, simulated bookings, IM and file bytes."""
import asyncio,base64,json,os,secrets,sys
from pathlib import Path
import httpx,uvicorn
from playwright.async_api import async_playwright,expect
from vic import v2,v2_travel_projects
from vic.config import ROOT
from vic_apps.server import create_app


async def main():
    tasks=list(map(int,sys.argv[1].split(','))) if len(sys.argv)>1 else [44,51,54]
    variants=sys.argv[2] if len(sys.argv)>2 else 'ABC'
    out=ROOT/'.local/v2-travel-ui';out.mkdir(parents=True,exist_ok=True)
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
                    state=v2.generate(task,10001,'eval');rid=secrets.token_hex(16);token=secrets.token_hex(32)
                    r=await client.post('/internal/prepare',json=dict(run_id=rid,token=token,app='travel',epoch=0,state=state));r.raise_for_status()
                    context=await browser.new_context(viewport={'width':1440,'height':1050});page=await context.new_page();page.set_default_timeout(15000)
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    async def snapshot():
                        r=await client.get('/internal/runs/'+rid);r.raise_for_status();return r.json()
                    async def action(locator):
                        async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')) as pending:await locator.click()
                        r=await pending.value;assert r.status==200,await r.text()
                    async def nav(name):await page.locator('.product-nav').get_by_role('button',name=name,exact=True).click()
                    async def open_booking(id):
                        await nav('我的订单');await page.locator(f'[data-booking="{id}"]').get_by_role('button',name='查看预订详情',exact=True).click()
                    async def download(button,expected):
                        async with page.expect_download() as pending:await button.click()
                        file=await pending.value;assert await file.failure() is None
                        assert Path(await file.path()).read_bytes()==expected
                    async def conversation(name):await page.locator('.ant-list-item').filter(has=page.get_by_text(name,exact=True)).click()
                    try:
                        await page.goto(f'http://127.0.0.1:8782/native/product/travel/{rid}#{token}')
                        await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                        await page.screenshot(path=str(out/f'{task}-{variant}-home.png'))
                        if task!=51:
                            await nav('审批申请' if task==54 else '差旅安排')
                            await page.get_by_role('link',name='查看团队出行通知 →',exact=True).click()
                            await expect(page.get_by_role('region',name='工作范围')).to_contain_text('出差安排与审批')
                            await conversation(state['world']['people'][0]['name'])
                            notice=next(n for n in state['world']['notices'] if n['recipient']==10)
                            card=page.locator(f'[data-travel-request="{notice["id"]}"]');await expect(card).to_contain_text(notice['title'])
                            await card.get_by_role('link',name='查看出行安排 →',exact=True).click()
                            if task==54:await expect(page.locator(f'[data-slot="{notice["slot"]}"]')).to_be_visible()
                            else:await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                        if task==44:
                            await nav('常用旅客')
                            for person in state['world']['people'][:4]:
                                row=page.locator(f'[data-person="{person["id"]}"]');name=v2_travel_projects.full_name(person,variant)
                                await row.get_by_label('旅客显示姓名 '+person['id'],exact=True).fill(name)
                                await action(row.get_by_role('button',name='保存旅客资料',exact=True))
                                await expect(row.get_by_label('旅客显示姓名 '+person['id'],exact=True)).to_have_value(name)
                        plan=v2_travel_projects.route_plan(state,variant);book_ids=[]
                        for index,(slot,route) in enumerate(plan.items()):
                            await nav('审批申请' if task==54 else '差旅安排')
                            card=page.locator(f'[data-slot="{slot}"]')
                            await card.get_by_role('button',name='查看候选车次',exact=True).click()
                            row=page.locator(f'[data-route="{route}"]')
                            await expect(row).to_contain_text(state['domain']['objects'][route]['record_code'])
                            await action(row.get_by_role('button',name='填写预订资料',exact=True))
                            if task==44 and variant=='A' and index==0:
                                await action(page.get_by_role('button',name='取消并移除预订',exact=True))
                                await expect(page.locator('[data-booking]')).to_have_count(0)
                                await nav('车次查询');await action(page.locator(f'[data-route="{route}"]').get_by_role('button',name='填写预订资料',exact=True))
                            snap=await snapshot();booking=next(b for b in snap['state']['world']['bookings'].values() if b['slot']==slot);bid=booking['id'];book_ids.append(bid)
                            source=next(r for r in (state['world']['requests'] if task==54 else state['world']['legs']) if r['id']==slot)
                            people=[source['person']] if task==54 else source['passengers']
                            for pid in people:
                                await page.get_by_label('选择旅客 '+pid,exact=True).check()
                                person=next(p for p in state['world']['people'] if p['id']==pid)
                                expected_name=v2_travel_projects.full_name(person,variant) if task==44 else state['world']['profiles'][pid]['full_name']
                                await expect(page.get_by_label('预订姓名 '+pid,exact=True)).to_have_value(expected_name)
                                await expect(page.get_by_label('预订证件 '+pid,exact=True)).to_have_value(person['document'])
                            await page.get_by_role('button',name='填入申请联系方式',exact=True).click()
                            await action(page.get_by_role('button',name='更新乘客资料',exact=True))
                            if index==0:
                                await page.get_by_label('预订联系邮箱',exact=True).fill('unsaved@example.test')
                                await expect(page.get_by_role('button',name='保存预订草稿',exact=True)).to_be_disabled()
                                await page.get_by_label('预订联系邮箱',exact=True).fill(source['contact'])
                            await action(page.get_by_role('button',name='保存预订草稿',exact=True))
                            if task!=44:await action(page.get_by_role('button',name='确认模拟预订',exact=True))
                            if index==0:await page.screenshot(path=str(out/f'{task}-{variant}-booking.png'),full_page=True)
                            snap=await snapshot();file=snap['state']['domain']['files']['booking-'+bid]
                            await download(page.get_by_role('button',name='下载预订行程单',exact=True),base64.b64decode(file['content']))
                            await page.get_by_role('link',name='打开预订行程单',exact=True).click()
                            await expect(page.locator('.trip-document')).to_have_text(base64.b64decode(file['content']).decode())
                            await open_booking(bid)
                            if task==54:
                                await page.get_by_label('行程单收件人',exact=True).select_option(str(source['recipient']))
                                await action(page.get_by_role('button',name='发送行程单',exact=True))
                                if variant=='A' and index==0:
                                    await action(page.get_by_role('button',name='撤回行程通知',exact=True))
                                    await expect(page.locator('[data-travel-receipt]')).to_have_count(0)
                                    await page.get_by_label('行程单收件人',exact=True).select_option(str(source['recipient']))
                                    await action(page.get_by_role('button',name='发送行程单',exact=True))
                                snap=await snapshot();receipt=next(r for r in snap['state']['world']['receipts'] if r['booking']==bid)
                                await page.get_by_role('link',name='打开团队消息 →',exact=True).click()
                                await expect(page.get_by_role('region',name='工作范围')).to_contain_text('出差安排与审批')
                                person=next(p for p in state['world']['people'] if p['im']==source['recipient']);await conversation(person['name'])
                                share=page.locator(f'[data-travel-share="{receipt["id"]}"]');await expect(share.locator('pre')).to_have_text(receipt['body'])
                                if index==0:
                                    await expect(page.locator('.ant-spin-blur')).to_have_count(0);await page.wait_for_timeout(300)
                                    await page.screenshot(path=str(out/f'{task}-{variant}-notification.png'),full_page=True)
                                await share.get_by_role('link',name='查看确认预订 →',exact=True).click()
                                await expect(page.get_by_role('heading',name=bid,exact=True)).to_be_visible()
                                await page.get_by_role('button',name='返回审批申请',exact=True).click()
                                req=page.locator(f'[data-slot="{slot}"]')
                                await req.get_by_label('回填预订号 '+slot,exact=True).select_option(bid)
                                await action(req.get_by_role('button',name='保存申请回填',exact=True))
                                if index==0:
                                    await action(req.get_by_role('button',name='清除回填',exact=True));await expect(req.locator('.trip-status')).to_have_text('待处理')
                                    await req.get_by_label('回填预订号 '+slot,exact=True).select_option(bid);await action(req.get_by_role('button',name='保存申请回填',exact=True))
                                await expect(req.locator('.trip-status')).to_have_text('已回填：'+bid)
                        await nav('出差行程单')
                        for bid in book_ids:await page.get_by_label('行程单预订 '+bid,exact=True).check()
                        await action(page.get_by_role('button',name='保存合并行程单',exact=True))
                        snap=await snapshot();result=v2.evaluate(state,snap['state'],variant,snap['events']);assert result['success'],result
                        await page.screenshot(path=str(out/f'{task}-{variant}-itinerary.png'),full_page=True)
                        file=snap['state']['domain']['files']['travel-itinerary']
                        await download(page.get_by_role('button',name='下载完整行程单',exact=True),base64.b64decode(file['content']))
                        await page.get_by_role('link',name='打开完整行程文件',exact=True).click();await expect(page.locator('.trip-document')).to_have_text(base64.b64decode(file['content']).decode())
                        await page.reload();await expect(page.locator('.trip-document')).to_be_visible()
                        snap=await snapshot();assert v2.evaluate(state,snap['state'],variant,snap['events'])['success'];assert not errors,errors
                        results.append(dict(task=task,variant=variant,seed=10001,suite='v2',mode='eval',status='passed',surface='native',persisted=True,bookings=len(book_ids),actual_downloads=True,im_source_notices=task!=51,im_itinerary_receipts=task==54))
                        print(f'{task}{variant} PASS',flush=True)
                    except Exception as exc:
                        results.append(dict(task=task,variant=variant,seed=10001,status='failed',error=str(exc),page_errors=errors));print(f'{task}{variant} FAIL {exc} {errors}',flush=True)
                        await page.screenshot(path=str(out/f'{task}-{variant}-failed.png'))
                    finally:
                        with (out/'history.jsonl').open('a') as f:f.write(json.dumps(results[-1],ensure_ascii=False)+'\n')
                        await context.close();await client.delete('/internal/runs/'+rid)
        finally:
            await browser.close();server.should_exit=True;await serving
    (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    if any(r['status']=='failed' for r in results):raise SystemExit(1)


if __name__=='__main__':asyncio.run(main())
