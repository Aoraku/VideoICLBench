"""Check deployed OS catalogue, direct UI, isolation and a real click without recording."""
import argparse
import asyncio
import json
from pathlib import Path

import httpx
from playwright.async_api import async_playwright


async def main(args):
    token=args.token_file.read_text().strip()
    output=args.output;output.mkdir(parents=True,exist_ok=True)
    async with httpx.AsyncClient(base_url=args.base_url,headers={'Authorization':'Bearer '+token},timeout=60) as api:
        response=await api.get('/os-api/cases');response.raise_for_status();cases=response.json()['cases']
        assert len(cases)==36
        if args.cases:
            cases=[case for case in cases if case["id"] in args.cases]
            assert len(cases)==len(set(args.cases))
        checks=[]
        async with async_playwright() as p:
            browser=await p.chromium.launch(headless=True)
            context=await browser.new_context(viewport={'width':1280,'height':720})
            page=await context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            await page.goto(args.base_url)
            await page.evaluate('(token)=>sessionStorage.setItem("vic-manager",token)',token)
            await page.reload();await page.get_by_role('button',name='OS · 36 题').click()
            await page.get_by_text('OS-SEL-01',exact=True).wait_for()
            await page.get_by_text('OS-SEL-01',exact=True).click()
            await page.locator('video').wait_for()
            await page.screenshot(path=str(output/'portal.png'),full_page=True)
            for case in cases:
                response=await api.post('/os-api/runs',json={'case_id':case['id'],'interaction':'human','seed':20261006})
                response.raise_for_status();run=response.json()
                await page.goto(args.base_url+run['application_url'])
                await page.locator('#capture-area').wait_for()
                await page.get_by_role('button',name='Finish and evaluate').wait_for()
                assert await page.locator('.rule-card,.control-panel,.studio-header').count()==0
                if case['family']=='recovery':
                    await page.get_by_text('Index',exact=True).wait_for()
                    assert 'ascending Index' in await page.locator('.task-banner').inner_text()
                if case['id']=='OS-SEL-01':
                    # A coordinate input verifies the browser-to-simulator route, not model accuracy.
                    box=await page.locator('[data-item]').first.bounding_box()
                    await page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2)
                    await page.wait_for_timeout(300)
                if case['id'] in ('OS-SEL-01','OS-REC-01','OS-XAPP-01'):
                    await page.screenshot(path=str(output/(case['id']+'.png')))
                response=await api.post('/os-api/runs/'+run['id']+'/eval');response.raise_for_status()
                result=response.json()
                if case['id']=='OS-SEL-01':assert result['agent_steps']==1
                checks.append({'case_id':case['id'],'ui_loaded':True,'evaluation_returned_boolean':isinstance(result['success'],bool)})
                print(case['id'],'UI + eval OK',flush=True)
            assert not errors,errors
            await browser.close()
        (output/'ui-check.json').write_text(json.dumps({'cases':checks,'page_errors':errors,'records_video':False,'benchmark_inference':False},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',default='http://127.0.0.1:18765')
    parser.add_argument('--token-file',type=Path,required=True)
    parser.add_argument('--cases',nargs='*')
    parser.add_argument('--output',type=Path,default=Path('.local/os-integration/ui'))
    asyncio.run(main(parser.parse_args()))
