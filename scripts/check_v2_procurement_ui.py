"""Click through procurement in Chromium; no video capture or direct state writes."""
import json
import os
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright

base=os.environ.get('VIC_CONTROL_BASE','http://127.0.0.1:18865')
secret=os.environ['VIC_ADMIN_TOKEN']
out=Path('.local/v2-ui');out.mkdir(exist_ok=True,parents=True)


def main():
    results=[]
    with httpx.Client(base_url=base,headers={'Authorization':'Bearer '+secret},timeout=30) as client, sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000})
        portal=context.new_page();portal.goto(base)
        portal.get_by_label('访问密钥').fill(secret)
        portal.get_by_role('button',name='进入录制台').click()
        portal.get_by_role('button',name='v2 list',exact=True).click()
        portal.get_by_label('搜索 v2 任务').fill('045')
        portal.get_by_role('button',name='045 汇总采购单并填写备注').click()
        assert portal.get_by_role('heading',name='最终交付').is_visible()
        for variant in 'ABC':
            created=client.post('/v1/runs',json=dict(suite='v2',task_id=45,variant=variant,seed=10001,mode='eval',runtime='browser',interaction='human'))
            created.raise_for_status();run=created.json()
            app_url=run['application_url'].replace('/apps/shop/','/native/product/shop/')
            origin=app_url.split('/native/')[0];token=app_url.split('#')[1]
            response=httpx.get(origin+'/api/runs/'+run['id'],headers={'Authorization':'Bearer '+token});response.raise_for_status()
            w=response.json()['state']['world']
            newest={}
            for request in sorted(w['requests'],key=lambda r:r['revision']):newest[request['number']]=request
            needs={}
            for request in newest.values():
                for line in request['lines']:
                    key=request['department'],line['sku'];needs[key]=needs.get(key,0)+line['quantity']
            page=context.new_page();errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
            page.goto(app_url)
            page.get_by_role('heading',name='把同事需要的用品准备好').wait_for()
            page.get_by_role('button',name='查看采购申请',exact=True).click()
            page.get_by_label('筛选部门').select_option('design')
            assert page.get_by_role('heading',name='CG-001 · 第 2 版').is_visible()
            page.get_by_role('button',name='商品目录',exact=True).click()
            assert page.get_by_role('cell',name='黑色 / 350ml',exact=True).is_visible()
            page.get_by_role('button',name='部门通讯录',exact=True).click()
            assert page.get_by_role('cell',name=w['departments'][0]['address']).is_visible()
            def click_save(name):
                with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')) as pending:
                    page.get_by_role('button',name=name,exact=True).click()
                assert pending.value.status==200,pending.value.text()
            for index,dep in enumerate(w['departments'],1):
                page.get_by_role('button',name='订单草稿',exact=True).click()
                page.get_by_label('采购部门').select_option(dep['id'])
                click_save('新建订单')
                page.get_by_role('button',name=f'编辑订单 PO-{index:03d}',exact=True).click()
                page.get_by_label('收货地址',exact=True).fill(dep['address'])
                click_save('保存地址')
                for (department,sku),quantity in needs.items():
                    if department!=dep['id']:continue
                    product=next(p for p in w['products'] if p['id']==sku)
                    note={'A':f'{quantity}{product["name"]}','B':f'{product["name"]}{quantity}','C':'零一二三四五六七八九'[quantity]+product['name']}[variant]
                    page.get_by_label('商品与规格').select_option(sku)
                    page.get_by_label('数量',exact=True).fill(str(quantity))
                    page.get_by_label('商品备注').fill(note)
                    click_save('保存商品行')
                    page.get_by_role('button',name='编辑商品 '+sku,exact=True).click()
                    assert page.get_by_label('商品备注').input_value()==note
                click_save('保存订单草稿')
                page.get_by_text('此订单已保存',exact=True).wait_for()
            page.get_by_role('button',name='订单草稿',exact=True).click()
            # Exercise reversible deletion and removal controls, not just save.
            click_save('新建订单')
            click_save('删除订单 PO-004')
            page.get_by_role('button',name='编辑订单 PO-001',exact=True).click()
            first_dep=w['departments'][0]['id']
            sku=next(sku for (dept,sku) in needs if dept==first_dep)
            q=needs[first_dep,sku];name=next(p['name'] for p in w['products'] if p['id']==sku)
            line_note={'A':f'{q}{name}','B':f'{name}{q}','C':'零一二三四五六七八九'[q]+name}[variant]
            click_save('移除商品 '+sku)
            page.get_by_label('商品与规格').select_option(sku)
            page.get_by_label('数量',exact=True).fill(str(q))
            page.get_by_label('商品备注').fill(line_note)
            click_save('保存商品行');click_save('保存订单草稿')
            page.get_by_role('button',name='返回订单列表',exact=True).click()
            page.reload()
            page.get_by_role('button',name='订单草稿',exact=True).click()
            assert page.get_by_role('cell',name='已保存',exact=True).count()==3
            page.screenshot(path=str(out/f'procurement-{variant}.png'),full_page=True)
            result=client.post('/v2/tasks/45/eval',json={'run_id':run['id']});result.raise_for_status()
            assert result.json()['success'],result.text
            assert not errors,errors
            results.append(dict(task_id=45,variant=variant,success=True,checks=result.json()['checks']))
            print('PASS procurement',variant,flush=True)
            page.close()
        browser.close()
    (out/'procurement-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
