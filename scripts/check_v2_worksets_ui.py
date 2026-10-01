"""Native browser acceptance for scoped v2 work. No video recording."""
import asyncio
import json
import os
import secrets
import sys
from pathlib import Path
import httpx
import uvicorn
from playwright.async_api import async_playwright, expect
from vic import v2, v2_worksets
from vic.config import ROOT
from vic.lessons import native_path
from vic_apps import worksets
from vic_apps.server import create_app


async def main():
    tasks=list(map(int,sys.argv[1].split(','))) if len(sys.argv)>1 else sorted(worksets.TASKS)
    variants=sys.argv[2] if len(sys.argv)>2 else 'ABC'
    out=ROOT/'.local/v2-worksets-ui';out.mkdir(parents=True,exist_ok=True)
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
                    async def go(name):await page.locator('.product-nav').get_by_role('button',name=name,exact=True).click()
                    async def click_save(locator):
                        async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')) as pending:await locator.click()
                        response=await pending.value
                        assert response.status==200,await response.text()
                    async def choose(locator,value,save=False):
                        # HTML select uses the browser's platform popup, which
                        # headless macOS does not drive with keyboard events.
                        # Playwright's native-select API dispatches input/change
                        # through the actual application handler.
                        if save:
                            async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')) as pending:await locator.select_option(value)
                            assert (await pending.value).status==200
                        else:await locator.select_option(value)
                        await expect(locator).to_have_value(value)
                    async def classify(container,value):
                        await container.locator('.label-menu>button').click()
                        await click_save(page.get_by_role('option',name=value,exact=False))
                    async def snapshot():
                        r=await client.get('/internal/runs/'+rid);r.raise_for_status();return r.json()
                    async def code_idle():
                        await page.wait_for_timeout(200)
                        await expect(page.locator('[data-testid="stApp"]')).to_have_attribute('data-test-script-state','notRunning',timeout=30000)
                    try:
                        await page.goto('http://127.0.0.1:8782'+native_path(state['app'],rid)+'#'+token)
                        region='专辑筛选' if task==22 else '资料筛选'
                        if task in (61,63):
                            await page.get_by_role('heading',name='题目列表',exact=True).wait_for(timeout=60000)
                            await code_idle()
                        else:await expect(page.get_by_role('region',name=region)).to_be_visible()
                        await page.screenshot(path=str(out/f'{task}-{variant}-home.png'))
                        if task in (61,63):await expect(page.locator('[data-testid="stException"]')).to_have_count(0)
                        nav={26:'视频资料库',31:'视频资料库',34:'稍后观看',38:'我的草稿',47:'车次查询',48:'所有商品',49:'交易明细',50:'我的账户',53:'交易明细',57:'余额提醒'}.get(task)
                        for scope in state['scopes']:
                            if not scope['requested']:continue
                            effect=v2_worksets.scope_effect(state,variant,scope)
                            if task in (61,63):
                                sidebar=page.locator('[data-testid="stSidebar"]')
                                await sidebar.get_by_role('combobox').click()
                                await page.get_by_role('option',name=scope['name'],exact=True).click()
                                await code_idle()
                                if task==61:
                                    await sidebar.get_by_role('button',name='查看提交',exact=True).click()
                                    await code_idle()
                                    await expect(page.get_by_role('radiogroup',name='结果标签',exact=True)).to_have_count(6)
                                    objects=worksets.members(state,scope)
                                    for index,item in enumerate(objects):
                                        if not effect['labels'][item['id']]:continue
                                        panel=page.locator('[data-testid="stExpander"]').filter(has_text='测试详情 · '+str(item['submission_number']))
                                        await panel.locator('summary').click()
                                        await expect(panel.get_by_role('table')).to_be_visible()
                                        await page.get_by_role('radiogroup',name='结果标签',exact=True).nth(index).get_by_text(effect['labels'][item['id']],exact=True).click()
                                        await page.get_by_role('button',name='保存结果标签',exact=True).nth(index).click()
                                        await code_idle()
                                        await expect(page.get_by_text('标签已保存',exact=True)).to_be_visible()
                                else:
                                    await sidebar.get_by_role('button',name='题目列表',exact=True).click()
                                    await code_idle()
                                    target=state['domain']['objects'][effect['selection'][0]]
                                    index=next(i for i,x in enumerate(worksets.members(state,scope)) if x['id']==target['id'])
                                    # Open the original problem detail before adding it.
                                    await page.get_by_role('button',name='进入题目',exact=True).nth(index).click()
                                    await code_idle()
                                    await page.get_by_role('button',name='加入课程练习',exact=True).click()
                                    await code_idle()
                                    await expect(page.get_by_text('已加入课程；可在课程练习列表中排序和保存',exact=True)).to_be_visible()
                                continue
                            if task==22:
                                await page.get_by_role('link',name='我的音乐',exact=True).click()
                                await choose(page.get_by_role('combobox',name='专辑',exact=True),scope['id'])
                                await choose(page.get_by_role('combobox',name='版本',exact=True),'录音室版')
                                await page.get_by_role('button',name='筛选专辑歌曲',exact=True).click()
                                await expect(page.locator('.music-table-row')).to_have_count(3)
                                for target,value in effect['labels'].items():
                                    if not value:continue
                                    await page.locator(f'[data-song="{target}"] a').first.click()
                                    await page.locator(f'[data-label-open="{target}"]').click()
                                    await click_save(page.locator(f'[data-label="{value}"][data-target="{target}"]'))
                                    await page.get_by_role('link',name='返回所属专辑',exact=True).click()
                                    await expect(page.locator(f'[data-label-open="{target}"]')).to_contain_text(value)
                                continue
                            if task in (23,33):
                                await page.locator('nav [data-page="articles"]').click()
                                await choose(page.get_by_role('combobox',name=scope['kind'],exact=True),scope['id'])
                                await choose(page.get_by_role('combobox',name='发布月份',exact=True),'2026-01')
                                await page.get_by_role('button',name='筛选文章',exact=True).click()
                                await expect(page.locator('.news-card')).to_have_count(6)
                                if task==23:
                                    for target,value in effect['labels'].items():
                                        if not value:continue
                                        await page.locator(f'[data-open="{target}"]').click()
                                        await page.locator(f'[data-menu="{target}"]').click()
                                        await click_save(page.get_by_role('option',name=value,exact=True))
                                        await page.get_by_role('button',name='← 返回文章列表',exact=True).click()
                                else:
                                    for target,action in effect['actions']:
                                        await click_save(page.locator(f'[data-action="{action}"][data-target="{target}"]'))
                                    destination={'A':'read','B':'favorites','C':'hidden'}[variant]
                                    await page.locator(f'nav [data-page="{destination}"]').click()
                                    await expect(page.locator('.news-card')).to_have_count(len(effect['actions']))
                                continue
                            await go(nav)
                            await choose(page.get_by_role('combobox',name=scope['kind'],exact=True),scope['id'])
                            for key,value in scope['filters'].items():
                                await choose(page.get_by_role('combobox',name=scope['filter_label'],exact=True),str(value))
                            if task==31:await page.get_by_placeholder('搜索视频',exact=True).fill(scope['name'])
                            effect=v2_worksets.scope_effect(state,variant,scope)
                            if 'labels' in effect:
                                for target,value in effect['labels'].items():
                                    if not value:continue
                                    row=page.locator(f'[data-object-id="{target}"]')
                                    if task==38:
                                        await row.locator('.product-text-link').click();await classify(page.locator('.blog-editor'),value)
                                        await page.get_by_role('button',name='← 返回草稿',exact=True).click()
                                    elif task==47:
                                        await row.locator('.product-text-link').click();await classify(page.locator('.travel-ticket'),value)
                                        await page.get_by_role('button',name='← 返回车次列表',exact=True).click()
                                    elif task==48:
                                        await row.locator('.shop-image-link').click();await classify(page.locator('.shop-detail'),value)
                                        await page.get_by_role('button',name='← 所有商品',exact=True).click()
                                    elif task in (49,50):
                                        await row.locator('.product-text-link').click()
                                        if task==50:
                                            history=page.locator('.bank-form details');await history.locator('summary').click()
                                            expected_count=state['domain']['objects'][target]['transactions']
                                            await expect(history.locator('tbody tr')).to_have_count(expected_count)
                                        await classify(page.locator('.bank-form'),value)
                                        await page.get_by_role('button',name='← 交易明细' if task==49 else '← 我的账户',exact=True).click()
                                    else:await classify(row,value)
                                if task in worksets.SNAPSHOT_TASKS:
                                    await click_save(page.get_by_role('button',name='保存'+scope['collection'],exact=True))
                                    count=sum(bool(v) for v in effect['labels'].values())
                                    await expect(page.locator('.workset-summary')).to_contain_text(f'已保存 {count} 项')
                            elif 'selection' in effect:
                                target=effect['selection'][0];row=page.locator(f'[data-object-id="{target}"]')
                                if task==31:await row.locator('.media-thumbnail').click()
                                else:await row.get_by_role('button',name='查看明细 →',exact=True).click()
                                await choose(page.get_by_role('combobox',name='保存位置',exact=True),scope['id'])
                                await click_save(page.get_by_role('button',name='加入课程收藏夹' if task==31 else '保存到对账单',exact=True))
                                await expect(page.locator('.workset-collect')).to_contain_text('此记录已保存')
                            else:
                                for target,action in effect['actions']:
                                    row=page.locator(f'[data-object-id="{target}"]')
                                    if task==57:
                                        await row.locator('.product-text-link').click()
                                        item=state['domain']['objects'][target]
                                        # Persist the channel through its UI handler before
                                        # enabling the reminder on the ordinary account page.
                                        locator=page.get_by_role('combobox',name='通知渠道 '+item['record_code'],exact=True)
                                        await choose(locator,state['source']['notification_channel'],save=True)
                                        await click_save(page.get_by_role('button',name='开启余额提醒',exact=True))
                                        await go(nav)
                                    else:await click_save(row.get_by_role('button',name=action,exact=True))
                        if task==31:await go('收藏夹');await expect(page.get_by_role('region',name='已保存的集合').locator('article')).to_have_count(3)
                        if task==53:await go('对账单');await expect(page.locator('.bank-receipt')).to_have_count(2)
                        if task==63:
                            await page.locator('[data-testid="stSidebar"]').get_by_role('button',name='课程练习列表',exact=True).click()
                            await code_idle()
                            await expect(page.get_by_role('button',name='移除',exact=True)).to_have_count(3)
                            # Verify reorder controls, then restore the
                            # requested topic sequence before saving the delivery.
                            await page.get_by_role('button',name='下移',exact=True).first.click()
                            await code_idle()
                            await page.get_by_role('button',name='上移',exact=True).nth(1).click()
                            await code_idle()
                            await page.get_by_role('button',name='移除',exact=True).last.click()
                            await code_idle()
                            await expect(page.get_by_role('button',name='移除',exact=True)).to_have_count(2)
                            await page.locator('[data-testid="stSidebar"]').get_by_role('button',name='题目列表',exact=True).click()
                            await code_idle()
                            last_scope=[scope for scope in state['scopes'] if scope['requested']][-1]
                            target=v2_worksets.scope_effect(state,variant,last_scope)['selection'][0]
                            index=next(i for i,x in enumerate(worksets.members(state,last_scope)) if x['id']==target)
                            await page.get_by_role('button',name='加入课程练习',exact=True).nth(index).click()
                            await code_idle()
                            await page.locator('[data-testid="stSidebar"]').get_by_role('button',name='课程练习列表',exact=True).click()
                            await code_idle()
                            await expect(page.get_by_role('button',name='移除',exact=True)).to_have_count(3)
                            await page.get_by_role('button',name='保存课程练习列表',exact=True).click()
                            await code_idle()
                            await expect(page.get_by_text('已保存的课程练习列表',exact=True)).to_be_visible()
                        snap=await snapshot();result=v2.evaluate(state,snap['state'],variant,snap['events'])
                        assert result['success'],result
                        assert not errors,errors
                        await page.screenshot(path=str(out/f'{task}-{variant}-done.png'),full_page=True)
                        await page.reload()
                        if task in (61,63):await page.get_by_role('heading',name='题目列表',exact=True).wait_for(timeout=60000)
                        else:await page.get_by_role('region',name=region).wait_for()
                        snap=await snapshot();assert v2.evaluate(state,snap['state'],variant,snap['events'])['success']
                        results.append(dict(task=task,variant=variant,seed=10001,suite='v2',mode='eval',status='passed',surface='native',persisted=True,checks=result['checks']))
                        print(f'{task}{variant} PASS',flush=True)
                    except Exception as exc:
                        results.append(dict(task=task,variant=variant,seed=10001,status='failed',error=str(exc)))
                        print(f'{task}{variant} FAIL {exc}',flush=True)
                        await page.screenshot(path=str(out/f'{task}-{variant}-failed.png'))
                    finally:
                        with (out/'history.jsonl').open('a') as f:f.write(json.dumps(results[-1],ensure_ascii=False)+'\n')
                        await context.close();await client.delete('/internal/runs/'+rid)
            (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
        finally:
            await browser.close();server.should_exit=True;await serving
    if any(r['status']=='failed' for r in results):raise SystemExit(1)


if __name__=='__main__':asyncio.run(main())
