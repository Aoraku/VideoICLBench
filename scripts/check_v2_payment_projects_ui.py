"""Native invoice payments and reconciliation acceptance, with no video recording."""
import asyncio,base64,json,os,secrets,sys
from pathlib import Path
import httpx,uvicorn
from playwright.async_api import async_playwright,expect
from vic import v2,v2_payment_projects
from vic.config import ROOT
from vic_apps.server import create_app


async def main():
    tasks=list(map(int,sys.argv[1].split(','))) if len(sys.argv)>1 else [46,56]
    variants=sys.argv[2] if len(sys.argv)>2 else 'ABC'
    out=ROOT/'.local/v2-payment-projects-ui';out.mkdir(parents=True,exist_ok=True)
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
                    r=await client.post('/internal/prepare',json=dict(run_id=rid,token=token,app='bank',epoch=0,state=initial));r.raise_for_status()
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
                    async def billpage(id):
                        await nav('账单中心');await page.locator(f'[data-bill="{id}"]').get_by_role('button',name='查看账单',exact=True).click()
                    try:
                        await page.goto(f'http://127.0.0.1:8782/native/product/bank/{rid}#{token}')
                        await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                        await page.screenshot(path=str(out/f'{task}-{variant}-home.png'))
                        chosen=v2_payment_projects.selected(initial,variant);links={}
                        for index,bill in enumerate(chosen):
                            person=next(p for p in w['people'] if p['id']==bill['coordinator'])
                            await page.get_by_role('link',name='团队付款通知 →',exact=True).click()
                            await expect(page.get_by_role('region',name='工作范围')).to_contain_text('账单通知与付款核对')
                            await page.locator('.ant-list-item').filter(has=page.get_by_text(person['name'],exact=True)).click()
                            card=page.locator(f'[data-payment-request="{bill["id"]}"]')
                            payee=initial['domain']['objects'][bill['payee']]
                            await expect(card).to_contain_text(payee['record_code']);await expect(card).to_contain_text(f'{bill["cents"]/100:.2f}')
                            await card.get_by_role('link',name='打开对应账单 →',exact=True).click()
                            await expect(page.get_by_role('heading',name=bill['id']+' · '+bill['purpose'],exact=True)).to_be_visible()
                            await page.get_by_role('link',name='查看收款资料 →',exact=True).click()
                            await expect(page.locator('.payment-facts')).to_contain_text(payee['account'])
                            await page.get_by_role('link',name=bill['id']+' · '+bill['purpose'],exact=False).click()
                            await page.get_by_role('button',name='准备付款',exact=True).click()
                            await expect(page.get_by_role('button',name='核对付款资料',exact=True)).to_be_disabled()
                            await page.get_by_label('付款账户',exact=True).select_option(bill['payer'])
                            await page.get_by_label('收款人',exact=True).select_option(bill['payee'])
                            await page.get_by_label('付款金额',exact=True).fill('12.345')
                            await expect(page.get_by_role('button',name='核对付款资料',exact=True)).to_be_disabled()
                            await page.get_by_role('button',name='填入账单金额',exact=True).click()
                            if task==46:await page.get_by_label('转账备注',exact=True).fill(v2_payment_projects.memo(initial,bill,variant))
                            else:await page.get_by_role('button',name='填入账单附言',exact=True).click()
                            await page.get_by_role('button',name='核对付款资料',exact=True).click()
                            await expect(page.locator('.payment-facts')).to_contain_text(payee['account'])
                            if index==0:
                                await page.get_by_role('button',name='返回修改',exact=True).click()
                                await expect(page.get_by_label('付款金额',exact=True)).to_have_value(f'{bill["cents"]/100:.2f}')
                                await page.get_by_role('button',name='核对付款资料',exact=True).click()
                                await page.screenshot(path=str(out/f'{task}-{variant}-confirmation.png'),full_page=True)
                            await action('确认模拟付款')
                            snap=await snapshot();transfer=next(t for t in snap['state']['world']['transfers'].values() if t['bill']==bill['id']);links[bill['id']]=transfer['id']
                            await expect(page.locator('.payment-document')).to_contain_text(payee['account'])
                            await download('下载付款回执','transfer-'+transfer['id'])
                            await page.get_by_role('link',name='打开付款文件',exact=True).click()
                            await expect(page.locator('.payment-document')).to_contain_text(transfer['id'])
                            await billpage(bill['id'])
                            await expect(page.get_by_role('button',name='准备付款',exact=True)).to_be_disabled()
                            if index==0:
                                await page.get_by_label('付款回执',exact=True).select_option('PAY-H001');await action('保存付款关联')
                                await action('清除付款关联');await expect(page.get_by_label('付款回执',exact=True)).to_have_value('')
                            await page.get_by_label('付款回执',exact=True).select_option(transfer['id']);await action('保存付款关联')
                            await download('下载关联回执','transfer-'+transfer['id'])
                        await nav('账单中心');await expect(page.locator('[data-bill]')).to_have_count(len(w['batch_bills']))
                        await page.get_by_label('账单批次',exact=True).select_option('all');await expect(page.locator('[data-bill]')).to_have_count(len(w['bills']))
                        await expect(page.locator('[data-bill="INV-HISTORY"]')).to_contain_text('PAY-H001')
                        await expect(page.locator('[data-bill="INV-NEXT"]')).to_contain_text('未付款')
                        if task==56:
                            for id in set(w['batch_bills'])-set(links):await expect(page.locator(f'[data-bill="{id}"]')).to_contain_text('未付款')
                            await nav('对账清单');await page.get_by_role('button',name='读取账单回填结果',exact=True).click();await action('保存对账清单')
                            await action('删除对账清单');await expect(page.get_by_role('button',name='下载对账清单',exact=True)).to_have_count(0);await action('保存对账清单')
                            await download('下载对账清单','payment-report')
                            await page.get_by_label('财务收件人',exact=True).select_option('10')
                            unpaid=next(id for id in w['batch_bills'] if id not in links)
                            await page.get_by_label('未付原因 '+unpaid,exact=True).fill('待核对');await expect(page.get_by_role('button',name='发送对账清单',exact=True)).to_be_disabled()
                            await page.get_by_label('未付原因 '+unpaid,exact=True).fill(w['unpaid_reason'])
                            await action('发送对账清单');await action('撤回对账通知');await action('发送对账清单')
                            snap=await snapshot();receipt=snap['state']['world']['receipts'][0]
                            await page.get_by_role('link',name='打开团队付款消息 →',exact=True).click()
                            await expect(page.get_by_role('region',name='工作范围')).to_be_visible()
                            await page.locator('.ant-list-item').filter(has=page.get_by_text(initial['world']['people'][0]['name'],exact=True)).click()
                            share=page.locator(f'[data-payment-share="{receipt["id"]}"]');await expect(share.locator('pre')).to_have_text(receipt['body'])
                            await page.screenshot(path=str(out/f'{task}-{variant}-notification.png'),full_page=True)
                            await share.get_by_role('link',name='查看付款对账清单 →',exact=True).click()
                            await expect(page.locator('.payment-document')).to_have_text(receipt['body'])
                            await page.get_by_role('link',name='回执 '+links[chosen[0]['id']],exact=True).click()
                            await expect(page.locator('.payment-document')).to_contain_text(chosen[0]['id'])
                        await nav('付款账户');snap=await snapshot()
                        for a in w['accounts']:
                            balance=snap['state']['domain']['balances'][a['id']]
                            await expect(page.locator(f'[data-account="{a["id"]}"]')).to_contain_text(f'{balance/100:,.2f}')
                        await nav('收款人名册');await page.get_by_label('搜索收款人',exact=True).fill('Avery Lin');await expect(page.locator('[data-payee]')).to_have_count(2)
                        await page.reload();snap=await snapshot();result=v2.evaluate(initial,snap['state'],variant,snap['events']);assert result['success'],result
                        assert not errors,errors
                        results.append(dict(task=task,variant=variant,seed=10001,suite='v2',mode='eval',status='passed',surface='native',persisted=True,real_downloads=True,payments=len(chosen),im_source_and_delivery=True,reconciliation=task==56))
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
