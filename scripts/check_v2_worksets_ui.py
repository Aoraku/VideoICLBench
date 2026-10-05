"""Native browser acceptance for scoped v2 work. No video recording."""
import asyncio
import json
import os
import re
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
                        region='工作范围' if state['app'] in ('chat','im') else '专辑筛选' if task==22 else '资料筛选'
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
                            if task==16:
                                await page.locator('.ant-list-item').filter(has_text=scope['name']).click()
                                await page.get_by_title('群聊设置',exact=True).click()
                                details=page.get_by_role('dialog',name='群聊信息')
                                await expect(details.get_by_text('群成员 (7)',exact=True)).to_be_visible()
                                await details.get_by_role('button',name='Close',exact=True).click()
                                for target,action in effect['actions']:
                                    index=next(i for i,x in enumerate(state['items']) if x['id']==target)
                                    row=page.locator(f'#msg-{100+index}')
                                    bubble=row.get_by_text(state['domain']['objects'][target]['text'],exact=True)
                                    await expect(page.get_by_role('menu')).to_have_count(0)
                                    await bubble.click(button='right')
                                    menu=page.get_by_role('menuitem',name={'已读':'确认已读','星标':'星标消息','回复':'回复'}[action],exact=True)
                                    if action=='回复':
                                        await menu.click()
                                        await page.locator('textarea:not([aria-hidden="true"])').fill(state['source']['fixed_reply'])
                                        await click_save(page.get_by_role('button',name=re.compile(r'发\s*送')))
                                        quote_text=' '.join(state['domain']['objects'][target]['text'].split())
                                        await expect(page.get_by_role('button',name=re.compile('：'+re.escape(quote_text)+'$'))).to_be_visible()
                                        await expect(page.get_by_title('取消回复',exact=True)).to_have_count(0)
                                    else:
                                        await click_save(menu)
                                        await expect(row.get_by_text('✓ 已确认阅读' if action=='已读' else '★ 已星标',exact=True)).to_be_visible()
                                    await expect(page.get_by_role('menu')).to_have_count(0)
                                continue
                            if state['app']=='chat':
                                await choose(page.get_by_role('combobox',name=scope['kind'],exact=True),scope['id'])
                                if task==2:
                                    targets=worksets.members(state,scope)
                                    commands={target:value for op,target,value,ids in v2_worksets.reference_commands(state,variant,include_delivery=False)}
                                    for item in targets:
                                        await page.locator('a[title="会话"]').click()
                                        await page.locator('.list__itemWrap').filter(has=page.locator('.list__title',has_text=scope['name'])).locator('.list__item').click()
                                        await expect(page.locator('.chatBody').get_by_text(f"我是 {item['name']}，我的成员账号是 {item['record_code']}。请使用我的姓名整理通讯录备注。",exact=True)).to_be_visible()
                                        await page.get_by_role('link',name='群资料',exact=True).click()
                                        await expect(page.locator('.groupMemberList__row')).to_have_count(6)
                                        await page.locator('.groupMemberList').get_by_role('link',name=item['name'],exact=True).click()
                                        await page.get_by_placeholder('无备注则留空').fill(commands[item['id']])
                                        await click_save(page.get_by_role('button',name='保存',exact=True))
                                        await expect(page).to_have_url(re.compile('/contacts'))
                                    continue
                                if task in (6,9):
                                    await page.locator('a[title="通讯录"]').click()
                                    await page.get_by_role('button',name='联系人',exact=False).click()
                                    await expect(page.locator('.wxAccRow')).to_have_count(len(worksets.members(state,scope)))
                                    targets=[key for key,value in effect.get('labels',{}).items() if value] if task==6 else effect['selection']
                                    for target in targets:
                                        name=state['domain']['objects'][target]['name']
                                        await page.locator('.wxAccRow').filter(has_text=name).click()
                                        await expect(page.locator('.wxDetailPane')).to_contain_text(scope['name'])
                                        if task==6:
                                            await page.locator('.wxGroupPicker__trigger').click()
                                            async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')):
                                                await page.get_by_role('option',name=effect['labels'][target],exact=True).click()
                                            await expect(page.locator('.wxGroupAssign')).to_contain_text('选择后自动保存')
                                            await expect(page.locator('.wxDetailPane__dl')).to_contain_text(effect['labels'][target])
                                        else:
                                            await page.get_by_role('button',name='发消息',exact=True).click()
                                            await page.locator('textarea').fill(scope['notification'])
                                            await click_save(page.locator('.sendBtn'))
                                            await expect(page.get_by_text(scope['notification'],exact=True).last).to_be_visible()
                                else:
                                    await page.locator('a[title="会话"]').click()
                                    await expect(page.locator('.list__itemWrap')).to_have_count(len(worksets.members(state,scope)))
                                    if task in (7,8):
                                        for target,value in effect['labels'].items():
                                            if not value:continue
                                            if task==8:
                                                await page.locator(f'[data-object-id="{target}"] .list__item').click()
                                                await page.get_by_role('link',name='群资料',exact=True).click()
                                                await expect(page.get_by_text('成员数量',exact=True)).to_be_visible()
                                                await page.get_by_role('link',name='返回',exact=True).click()
                                            row=page.locator(f'[data-object-id="{target}"]')
                                            await row.get_by_role('button',name='会话操作',exact=True).click()
                                            await click_save(page.get_by_role('menuitem',name=value,exact=True))
                                            await expect(row).to_contain_text(value)
                                    elif task==12:
                                        eligible={x['id'] for x in worksets.members(state,scope)}
                                        for dest,target in enumerate(effect['order']):
                                            snap=await snapshot();current=[key for key in snap['state']['domain']['orders']['main'] if key in eligible]
                                            for _ in range(current.index(target)-dest):
                                                await click_save(page.locator(f'[data-object-id="{target}"]').get_by_role('button',name='↑ 上移',exact=True))
                                                await page.wait_for_timeout(100)
                                        await expect(page.locator('.list__itemWrap')).to_have_count(len(eligible))
                                        assert await page.locator('.list__itemWrap').evaluate_all('(rows)=>rows.map(row=>row.dataset.objectId)')==effect['order']
                                    else:
                                        for target,action in effect['actions']:
                                            await page.locator(f'[data-object-id="{target}"]').get_by_role('button',name='会话操作',exact=True).click()
                                            await click_save(page.get_by_role('menuitem',name={'归档':'归档会话','置顶':'置顶会话','静音':'消息免打扰'}[action],exact=True))
                                        target,action=effect['actions'][0]
                                        await page.locator(f'[data-object-id="{target}"]').get_by_role('button',name='会话操作',exact=True).click()
                                        await click_save(page.get_by_role('menuitem',name={'归档':'取消归档','置顶':'取消置顶','静音':'关闭免打扰'}[action],exact=True))
                                        field={'归档':'archived','置顶':'pinned','静音':'muted'}[action]
                                        assert not (await snapshot())['state']['domain']['objects'][target][field]
                                        await page.locator(f'[data-object-id="{target}"]').get_by_role('button',name='会话操作',exact=True).click()
                                        await click_save(page.get_by_role('menuitem',name={'归档':'归档会话','置顶':'置顶会话','静音':'消息免打扰'}[action],exact=True))
                                        await choose(page.get_by_role('combobox',name='会话状态',exact=True),{'A':'archived','B':'pinned','C':'muted'}[variant])
                                        await expect(page.locator('.list__itemWrap')).to_have_count(len(effect['actions']))
                                continue
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
                                    elif task==49:
                                        await classify(row,value)
                                    elif task==50:
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
                                collect_region=page if task==31 else row
                                await choose(collect_region.get_by_role('combobox',name='保存位置',exact=True),scope['id'])
                                await click_save(collect_region.get_by_role('button',name='加入课程收藏夹' if task==31 else '保存到对账单',exact=True))
                                await expect(collect_region.locator('.workset-collect')).to_contain_text('此记录已保存')
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
                        # This probe covers native app controls. Document editing
                        # has a separate browser probe; create the required final
                        # deliverable through ordinary authenticated commands here.
                        for op,target,value,ids in v2_worksets.reference_commands(state,variant):
                            if op.startswith('assignment.'):
                                response=await client.post('/api/runs/'+rid+'/commands',headers={'Authorization':'Bearer '+token},json=dict(epoch=0,action_id=secrets.token_hex(16),op=op,target=target,value=value,ids=ids))
                                response.raise_for_status()
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
                        results.append(dict(task=task,variant=variant,seed=10001,status='failed',error=str(exc),page_errors=errors))
                        print(f'{task}{variant} FAIL {exc} {errors}',flush=True)
                        await page.screenshot(path=str(out/f'{task}-{variant}-failed.png'))
                    finally:
                        with (out/'history.jsonl').open('a') as f:f.write(json.dumps(results[-1],ensure_ascii=False)+'\n')
                        await context.close();await client.delete('/internal/runs/'+rid)
            (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
        finally:
            await browser.close();server.should_exit=True;await serving
    if any(r['status']=='failed' for r in results):raise SystemExit(1)


if __name__=='__main__':asyncio.run(main())
