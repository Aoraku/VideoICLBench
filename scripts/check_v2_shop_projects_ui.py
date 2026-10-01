"""Native shopping acceptance with actual orders, files and IM handovers; no video."""
import asyncio,base64,json,os,secrets,sys
from pathlib import Path
import httpx,uvicorn
from playwright.async_api import async_playwright,expect
from vic import v2,v2_shop_projects
from vic.config import ROOT
from vic_apps.server import create_app


async def main():
    tasks=list(map(int,sys.argv[1].split(','))) if len(sys.argv)>1 else [52,55]
    variants=sys.argv[2] if len(sys.argv)>2 else 'ABC'
    out=ROOT/'.local/v2-shop-projects-ui';out.mkdir(parents=True,exist_ok=True)
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
                    r=await client.post('/internal/prepare',json=dict(run_id=rid,token=token,app='shop',epoch=0,state=initial));r.raise_for_status()
                    context=await browser.new_context(viewport={'width':1440,'height':1050});page=await context.new_page();page.set_default_timeout(15000)
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    async def snapshot():
                        r=await client.get('/internal/runs/'+rid);r.raise_for_status();return r.json()
                    async def action(name):
                        async with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')) as pending:await page.get_by_role('button',name=name,exact=True).click()
                        response=await pending.value;assert response.status==200,await response.text()
                    async def nav(name):await page.locator('.product-nav').get_by_role('button',name=name,exact=True).click()
                    async def download(button,id):
                        data=await snapshot();expected=base64.b64decode(data['state']['domain']['files'][id]['content'])
                        async with page.expect_download() as pending:await page.get_by_role('button',name=button,exact=True).click()
                        file=await pending.value;assert await file.failure() is None
                        assert Path(await file.path()).read_bytes()==expected
                    async def request_list(request):
                        await nav('采购整理通知');await page.locator(f'[data-request="{request["id"]}"]').get_by_role('button',name='打开整理清单',exact=True).click()
                    async def handover(request):
                        await nav('采购交接');await page.locator(f'[data-handover="{request["id"]}"]').get_by_role('button',name='编辑交接单',exact=True).click()
                    async def checkout(dep,ids):
                        await nav('购物车')
                        for id in ids:await page.get_by_label('结算商品 '+initial['domain']['objects'][id]['record_code'],exact=True).check()
                        await page.get_by_role('button',name='按部门结算',exact=True).click()
                        await page.get_by_label('采购部门',exact=True).select_option(dep['id'])
                        await page.get_by_role('button',name='填入部门地址',exact=True).click()
                        await expect(page.get_by_label('收货地址',exact=True)).to_have_value(dep['address'])
                        await action('确认模拟下单')
                    try:
                        await page.goto(f'http://127.0.0.1:8782/native/product/shop/{rid}#{token}')
                        await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                        await page.screenshot(path=str(out/f'{task}-{variant}-home.png'))
                        if task==52:
                            chosen=v2_shop_projects.selected(initial,variant)
                            for index,need in enumerate(w['needs']):
                                await nav('部门采购需求')
                                await page.locator(f'[data-need="{need["id"]}"]').get_by_role('button',name='查看候选商品',exact=True).click()
                                await expect(page.locator('[data-product]')).to_have_count(sum(p['category']==need['category'] for p in initial['items']))
                                id=chosen[need['id']]
                                await page.locator(f'[data-product="{id}"]').get_by_role('button',name='查看商品',exact=True).click()
                                await page.get_by_label('购买数量',exact=True).fill(str(need['quantity']))
                                await action('加入购物车')
                                if index==0:
                                    await page.get_by_label('购买数量',exact=True).fill(str(need['quantity']+1));await action('更新购物车数量')
                                    await page.get_by_label('购买数量',exact=True).fill(str(need['quantity']));await action('更新购物车数量')
                                    await action('收藏商品');await action('取消收藏')
                                    await action('移出购物车');await action('加入购物车')
                                    await page.screenshot(path=str(out/f'{task}-{variant}-product.png'))
                            for index,dep in enumerate(w['departments']):
                                ids=[chosen[n['id']] for n in w['needs'] if n['department']==dep['id']]
                                await checkout(dep,ids)
                                snap=await snapshot();order=next(o for o in snap['state']['world']['orders'].values() if o['department']==dep['id'])
                                await page.locator(f'[data-order="{order["id"]}"]').get_by_role('button',name='查看订单回执',exact=True).click()
                                if index==0 and variant=='A':
                                    await action('取消模拟订单');await checkout(dep,ids)
                                    snap=await snapshot();order=next(o for o in snap['state']['world']['orders'].values() if o['department']==dep['id'])
                                    await page.locator(f'[data-order="{order["id"]}"]').get_by_role('button',name='查看订单回执',exact=True).click()
                                await download('下载订单回执','order-'+order['id'])
                                await page.get_by_role('link',name='打开订单文件',exact=True).click()
                                await expect(page.locator('.purchase-document')).to_contain_text(order['confirmation'])
                                if index==0:await page.screenshot(path=str(out/f'{task}-{variant}-receipt.png'),full_page=True)
                            await nav('购物车');await expect(page.locator('[data-product]')).to_have_count(1)
                            await expect(page.locator('[data-product]')).to_contain_text('U-001')
                        else:
                            for index,request in enumerate(w['requests']):
                                await page.get_by_role('link',name='团队采购消息 →',exact=True).click()
                                await expect(page.get_by_role('region',name='工作范围')).to_contain_text('采购申请与交接')
                                person=next(p for p in w['people'] if p['id']==request['recipient'])
                                await page.locator('.ant-list-item').filter(has=page.get_by_text(person['name'],exact=True)).click()
                                card=page.locator(f'[data-shopping-request="{request["id"]}"]');await expect(card).to_contain_text(request['label'])
                                for id in request['products']:await expect(card).to_contain_text(initial['domain']['objects'][id]['record_code'])
                                await card.get_by_role('link',name='打开采购整理清单 →',exact=True).click()
                                await expect(page.locator('[data-product]')).to_have_count(4)
                                for id in request['products']:
                                    if request['label'] not in initial['domain']['objects'][id]['tags']:continue
                                    await page.locator(f'[data-product="{id}"]').get_by_role('button',name='查看商品',exact=True).click()
                                    if variant=='A' and id not in w['cart']:
                                        await page.get_by_label('购买数量',exact=True).fill(str(request['quantities'][id]));await action('加入购物车')
                                    elif variant=='B' and id in w['cart']:await action('移出购物车')
                                    elif variant=='C' and id not in w['favorites']:await action('收藏商品')
                                    await request_list(request)
                                await handover(request)
                                await page.get_by_role('button',name='读取当前商品状态',exact=True).click();await action('保存交接单')
                                if index==0:
                                    await action('删除交接单');await expect(page.get_by_role('button',name='下载采购交接单',exact=True)).to_have_count(0)
                                    await action('保存交接单')
                                await download('下载采购交接单','handover-'+request['id'])
                                await page.get_by_label('交接收件人',exact=True).select_option(str(request['recipient']))
                                id=request['products'][0];code=initial['domain']['objects'][id]['record_code']
                                field=page.get_by_label('交接数量 '+code,exact=True);current=await field.input_value()
                                await field.fill(str(int(current)+1));await expect(page.get_by_role('button',name='发送采购交接单',exact=True)).to_be_disabled()
                                await field.fill(current)
                                favorite=page.get_by_label('交接收藏 '+code,exact=True);checked=await favorite.is_checked()
                                await favorite.set_checked(not checked);await expect(page.get_by_role('button',name='发送采购交接单',exact=True)).to_be_disabled()
                                await favorite.set_checked(checked);await action('发送采购交接单')
                                if index==0:
                                    await action('撤回交接通知');await action('发送采购交接单')
                                snap=await snapshot();receipt=next(r for r in snap['state']['world']['receipts'] if r['request']==request['id'])
                                await page.get_by_role('link',name='打开团队采购消息 →',exact=True).click()
                                await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                                await page.locator('.ant-list-item').filter(has=page.get_by_text(person['name'],exact=True)).click()
                                share=page.locator(f'[data-shopping-share="{receipt["id"]}"]');await expect(share.locator('pre')).to_have_text(receipt['body'])
                                if index==0:
                                    await expect(page.locator('.ant-spin-blur')).to_have_count(0)
                                    await page.wait_for_timeout(300)
                                    await page.screenshot(path=str(out/f'{task}-{variant}-notification.png'))
                                await share.get_by_role('link',name='查看采购交接单 →',exact=True).click()
                                await expect(page.locator('.purchase-document')).to_have_text(receipt['body'])
                                await page.get_by_role('link',name='查看商品 '+code,exact=True).click()
                                await expect(page.locator('.shop-detail')).to_contain_text(code)
                            await nav('采购交接')
                        await nav('我的收藏')
                        expected_favorites=w['favorites'] if task==52 else v2_shop_projects.inventory(initial,variant)[1]
                        await expect(page.locator('[data-product]')).to_have_count(len(expected_favorites))
                        await page.get_by_label('搜索商品',exact=True).fill('U-001')
                        await expect(page.locator('[data-product]')).to_have_count(1)
                        await expect(page.locator('[data-product]')).to_contain_text('U-001')
                        await page.reload()
                        snap=await snapshot();result=v2.evaluate(initial,snap['state'],variant,snap['events']);assert result['success'],result
                        assert not errors,errors
                        results.append(dict(task=task,variant=variant,seed=10001,suite='v2',mode='eval',status='passed',surface='native',persisted=True,real_downloads=True,orders=3 if task==52 else 0,handovers=2 if task==55 else 0,im_source_and_delivery=task==55))
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
