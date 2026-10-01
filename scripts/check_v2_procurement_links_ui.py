"""Native Shop/IM request links and actual purchase orders, without recording."""
import asyncio,json,os,secrets
import httpx,uvicorn
from playwright.async_api import async_playwright,expect
from vic import v2
from vic.config import ROOT
from vic_apps.server import create_app


async def main():
    out=ROOT/'.local/v2-procurement-links-ui';out.mkdir(parents=True,exist_ok=True)
    secret=secrets.token_hex(32)
    os.environ.update(VIC_APP_DATA=str(out/'data'),VIC_APP_RUNTIME_TOKEN=secret,VIC_NATIVE_SELF_BASE='http://127.0.0.1:8782')
    server=uvicorn.Server(uvicorn.Config(create_app(),host='127.0.0.1',port=8782,log_level='error'))
    serving=asyncio.create_task(server.serve())
    while not server.started:await asyncio.sleep(.05)
    results=[]
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8782',headers={'Authorization':'Bearer '+secret},trust_env=False,timeout=60) as client,async_playwright() as p:
        browser=await p.chromium.launch()
        try:
            for variant in 'ABC':
                initial=v2.generate(45,10001,'eval');w=initial['world'];rid=secrets.token_hex(16);token=secrets.token_hex(32)
                response=await client.post('/internal/prepare',json=dict(run_id=rid,token=token,app='shop',epoch=0,state=initial));response.raise_for_status()
                context=await browser.new_context(viewport={'width':1440,'height':1050});page=await context.new_page();page.set_default_timeout(15000)
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                async def action(name):
                    async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')) as pending:
                        await page.get_by_role('button',name=name,exact=name!='发送').click()
                    response=await pending.value;assert response.status==200,await response.text()
                async def snapshot():
                    response=await client.get('/internal/runs/'+rid);response.raise_for_status();return response.json()
                try:
                    await page.goto(f'http://127.0.0.1:8782/native/product/shop/{rid}#{token}')
                    await expect(page.get_by_role('heading',name='把同事需要的用品准备好')).to_be_visible()
                    await page.screenshot(path=str(out/f'45-{variant}-home.png'))
                    for index,department in enumerate(w['departments']):
                        await page.get_by_role('link',name='团队采购消息 →',exact=True).click()
                        await expect(page.get_by_role('region',name='工作范围')).to_contain_text('采购申请与交接')
                        await page.locator('.ant-list-item').filter(has=page.get_by_text(department['contact'],exact=True)).click()
                        await expect(page.locator('[data-procurement-request]')).to_have_count(3)
                        sources=[r for r in w['requests'] if r['department']==department['id']]
                        for request in sources:
                            card=page.locator(f'[data-procurement-request="{request["id"]}"]')
                            await expect(card).to_contain_text(request['id'])
                            for line in request['lines']:
                                product=next(p for p in w['products'] if p['id']==line['sku'])
                                await expect(card).to_contain_text(product['spec'])
                                await expect(card).to_contain_text(line['sku']+' × '+str(line['quantity']))
                        if index==0:
                            await page.get_by_placeholder('输入消息...',exact=True).fill('采购资料已收到，将核对最新版本与追加申请。')
                            await action('发送')
                            await expect(page.get_by_text('采购资料已收到，将核对最新版本与追加申请。',exact=True)).to_be_visible()
                            await expect(page.locator('.ant-spin-blur')).to_have_count(0)
                            await page.screenshot(path=str(out/f'45-{variant}-source-messages.png'))
                        latest=next(r for r in sources if r['revision']==2)
                        await page.locator(f'[data-procurement-request="{latest["id"]}"]').get_by_role('link',name='查看采购申请 →',exact=True).click()
                        await expect(page.locator('[data-purchase-request]')).to_have_count(1)
                        await expect(page.locator('[data-purchase-request]')).to_have_attribute('data-purchase-request',latest['id'])
                        await page.get_by_role('button',name='查看全部采购申请',exact=True).click()
                        await expect(page.locator('[data-purchase-request]')).to_have_count(9)
                    await page.get_by_label('筛选部门').select_option('design')
                    await expect(page.locator('[data-purchase-request]')).to_have_count(3)
                    await page.get_by_role('button',name='商品目录',exact=True).click()
                    await expect(page.get_by_role('cell',name='黑色 / 350ml',exact=True)).to_be_visible()
                    await page.get_by_role('button',name='部门通讯录',exact=True).click()
                    await expect(page.get_by_role('cell',name=w['departments'][0]['contact'],exact=True)).to_be_visible()
                    latest={}
                    for request in sorted(w['requests'],key=lambda r:r['revision']):latest[request['number']]=request
                    quantities={}
                    for request in latest.values():
                        for line in request['lines']:
                            key=request['department'],line['sku'];quantities[key]=quantities.get(key,0)+line['quantity']
                    for index,department in enumerate(w['departments'],1):
                        await page.get_by_role('button',name='订单草稿',exact=True).click()
                        await page.get_by_label('采购部门').select_option(department['id']);await action('新建订单')
                        await page.get_by_role('button',name=f'编辑订单 PO-{index:03d}',exact=True).click()
                        await page.get_by_label('收货地址',exact=True).fill(department['address']);await action('保存地址')
                        for (dep,sku),quantity in quantities.items():
                            if dep!=department['id']:continue
                            name=next(p['name'] for p in w['products'] if p['id']==sku)
                            note={'A':f'{quantity}{name}','B':f'{name}{quantity}','C':'零一二三四五六七八九'[quantity]+name}[variant]
                            await page.get_by_label('商品与规格').select_option(sku)
                            await page.get_by_label('数量',exact=True).fill(str(quantity));await page.get_by_label('商品备注',exact=True).fill(note)
                            await action('保存商品行')
                            await page.get_by_role('button',name='编辑商品 '+sku,exact=True).click();await expect(page.get_by_label('商品备注',exact=True)).to_have_value(note)
                        await action('保存订单草稿');await expect(page.get_by_text('此订单已保存',exact=True)).to_be_visible()
                    await page.get_by_role('button',name='返回订单列表',exact=True).click()
                    await action('新建订单');await action('删除订单 PO-004')
                    await page.reload();await page.get_by_role('button',name='订单草稿',exact=True).click()
                    await expect(page.get_by_role('cell',name='已保存',exact=True)).to_have_count(3)
                    await page.screenshot(path=str(out/f'45-{variant}-orders.png'))
                    final=await snapshot();result=v2.evaluate(initial,final['state'],variant,final['events']);assert result['success'],result
                    assert len(final['state']['world']['discussion'])==1
                    assert not errors,errors
                    results.append(dict(task=45,variant=variant,seed=10001,suite='v2',mode='eval',status='passed',surface='native',source_messages=9,source_links=3,orders=3,im_send=True,persisted=True))
                    print('45'+variant+' PASS',flush=True)
                except Exception as exc:
                    results.append(dict(task=45,variant=variant,status='failed',error=str(exc),page_errors=errors));print('45'+variant+' FAIL '+str(exc)+' '+str(errors),flush=True)
                    await page.screenshot(path=str(out/f'45-{variant}-failed.png'))
                finally:
                    (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
                    await context.close();await client.delete('/internal/runs/'+rid)
        finally:
            await browser.close();server.should_exit=True;await serving
    if any(r['status']=='failed' for r in results):raise SystemExit(1)


if __name__=='__main__':asyncio.run(main())
