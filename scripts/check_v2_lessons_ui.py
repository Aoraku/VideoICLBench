"""Validate real tutorial navigation and Next buttons without video capture.

Run against an isolated controller and worker, with VIC_ADMIN_TOKEN supplied
through the environment. Task answers are computed in this private QA process.
"""
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit
import httpx
from playwright.sync_api import sync_playwright, expect
from vic.business import expected_effect
from vic.games import expected
from vic.lessons import native_path


def main():
    base=os.environ.get('VIC_CONTROL_BASE','http://127.0.0.1:18865')
    tasks=list(map(int,sys.argv[1].split(','))) if len(sys.argv)>1 else [1,10,68]
    variants=sys.argv[2] if len(sys.argv)>2 else 'ABC'
    output=Path('.local/v2-ui');output.mkdir(exist_ok=True,parents=True)
    results=[]
    with httpx.Client(base_url=base,headers={'Authorization':'Bearer '+os.environ['VIC_ADMIN_TOKEN']},trust_env=False,timeout=60) as control,sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            for task in tasks:
                for variant in variants:
                    response=control.post('/v1/runs',json=dict(suite='v2',task_id=task,variant=variant,seed=0,mode='demo',runtime='browser',interaction='human',teaching=True))
                    response.raise_for_status();run=response.json()
                    address=urlsplit(run['application_url']);origin=address.scheme+'://'+address.netloc
                    context=browser.new_context(viewport={'width':1440,'height':1050});page=context.new_page();page.set_default_timeout(20000)
                    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    app=address.path.split('/')[2]
                    page.goto(origin+native_path(app,run['id'])+'#'+address.fragment)
                    episodes=[]
                    try:
                        for index in range(run['lesson']['total']):
                            current=control.get('/v1/runs/'+run['id']);current.raise_for_status()
                            token=urlsplit(current.json()['application_url']).fragment
                            response=httpx.get(origin+'/api/runs/'+run['id'],headers={'Authorization':'Bearer '+token},trust_env=False)
                            response.raise_for_status();state=response.json()['state']
                            bar=page.get_by_role('complementary',name='连续练习')
                            expect(bar).to_contain_text(f'练习 {index+1} / {run["lesson"]["total"]}')
                            effect=expected_effect(task,variant,state) if task<66 else None
                            if task==1:
                                page.locator('.list__item').filter(has_text=state['source']['recipient']).first.click()
                                page.locator('.chatInput textarea').fill(effect['outputs']['target'])
                                with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')):
                                    page.locator('.sendBtn').click()
                            elif task==10:
                                page.get_by_role('button',name='搜索记录',exact=True).click()
                                page.get_by_label('搜索聊天记录').fill(state['source']['search_keyword'])
                                name=state['domain']['objects'][effect['selection'][0]]['name']
                                with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')):
                                    page.locator('.paneSearchResultItem').filter(has=page.locator('.paneSearchResultTitle',has_text=name)).first.click()
                            elif task==68:
                                page.get_by_role('button',name='打开练习棋盘 →',exact=True).click()
                                with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/commands')):
                                    page.get_by_role('button',name=expected(task,variant,state),exact=True).click()
                            elif task==60:
                                expect(page.get_by_role('heading',name='题目列表',exact=True)).to_be_visible(timeout=90000)
                                page.get_by_text('我的代码与笔记',exact=True).click()
                                page.locator('textarea').fill(effect['outputs']['target'])
                                page.get_by_role('button',name='保存文件',exact=True).click()
                                for _ in range(100):
                                    saved=httpx.get(origin+'/api/runs/'+run['id'],headers={'Authorization':'Bearer '+token},trust_env=False).json()['state']
                                    if saved['outputs'].get('target')==effect['outputs']['target']:break
                                    time.sleep(.1)
                                else:raise AssertionError('Code lesson did not persist the current file')
                                expect(page.locator('[data-testid="stApp"]')).to_have_attribute('data-test-script-state','notRunning',timeout=30000)
                            elif task==66:
                                canvas=page.locator('canvas');expect(canvas).to_be_visible(timeout=90000)
                                page.wait_for_timeout(1000)
                                box=canvas.bounding_box();assert box
                                def click_board(x,y):
                                    page.mouse.click(box['x']+x*box['width']/1280,box['y']+y*box['height']/960)
                                    page.wait_for_timeout(300)
                                click_board(1000,210)
                                for row,col in expected(task,variant,state):click_board(col*50+100,row*50+50)
                                page.wait_for_timeout(400)
                            else:raise ValueError('Unsupported lesson UI flow: '+str(task))
                            name='完成练习' if index==run['lesson']['total']-1 else '下一组'
                            with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/lesson/next')) as response:
                                bar.get_by_role('button',name=name,exact=True).click()
                            assert response.value.status==200
                            # The app navigates immediately after fetch resolves;
                            # Chromium may evict the previous response body.
                            updated=control.get('/v1/runs/'+run['id']);updated.raise_for_status()
                            data=updated.json();assert data['lesson']['completed']==index+1,data['lesson']
                            episodes.append(dict(index=index,seed=state.get('seed',state.get('source',{}).get('instance_seed')),next_button_passed=True))
                            if index==run['lesson']['total']-1:expect(bar).to_contain_text('已完成 6 组练习')
                        response=control.post(f'/v2/tasks/{task}/eval',json={'run_id':run['id']});response.raise_for_status()
                        assert response.json()['success'],response.text
                        assert not errors,errors
                        results.append(dict(task=task,variant=variant,status='passed',mode='demo',suite='v2',all_episodes_via_ui=True,episodes=episodes))
                        print(f'{task}{variant} PASS all {len(episodes)} episodes',flush=True)
                    finally:
                        (output/'lesson-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
                        context.close()
                        removed=control.delete('/v1/runs/'+run['id']);removed.raise_for_status()
        finally:browser.close()


if __name__=='__main__':main()
