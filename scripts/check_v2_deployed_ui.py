"""Verify the deployed portal, direct native entry and Linux app controls, no video."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from playwright.sync_api import sync_playwright, expect
from vic import business, games
from vic.lessons import native_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:18765')
    parser.add_argument('--token-file', default='.local/agentlab-admin-token')
    parser.add_argument('--output', default='.local/v2-deployed-ui')
    args = parser.parse_args()
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    secret = Path(args.token_file).read_text().strip()
    results = []; created = []
    with httpx.Client(base_url=args.base, headers={'Authorization': 'Bearer ' + secret}, trust_env=False, timeout=120) as control, sync_playwright() as p:
        catalog = control.get('/v2/tasks').json()['tasks']
        browser = p.chromium.launch()
        context = browser.new_context(viewport={'width': 1440, 'height': 1050})
        # Any accidental capture request fails this check instead of recording.
        context.add_init_script("navigator.mediaDevices.getDisplayMedia = () => { throw new Error('QA must not record video'); }")
        portal = context.new_page(); portal.set_default_timeout(20000)
        try:
            portal.goto(args.base)
            portal.get_by_label('访问密钥').fill(secret)
            portal.get_by_role('button', name='进入录制台', exact=True).click()
            portal.get_by_role('button', name='v2 list', exact=True).click()
            expect(portal.locator('.v2-list tbody tr')).to_have_count(75)
            search = portal.get_by_label('搜索 v2 任务')
            for task in catalog:
                search.fill(f'{task["id"]:03d}')
                portal.get_by_role('button', name=f'{task["id"]:03d} {task["title"]}', exact=True).click()
                detail = portal.locator('.v2-detail')
                expect(detail).to_contain_text(task['assignment'])
                detail.get_by_role('tab', name='示范 · demo', exact=True).click()
                for variant in 'ABC':
                    detail.get_by_role('button', name='版本 ' + variant, exact=True).click()
                    expect(detail.locator('.v2-rule')).to_contain_text(task['variants'][variant])
                expect(detail.get_by_role('button', name='预览示范环境', exact=False)).to_be_enabled()
                detail.get_by_role('tab', name='执行 · inference', exact=True).click()
                expect(detail).to_contain_text(task['delivery'])
                expect(detail.get_by_role('button', name='打开执行环境', exact=False)).to_be_enabled()
            search.fill('')
            portal.screenshot(path=str(out / 'portal.png'), full_page=True)
            results.append(dict(check='all_75_cards_and_225_rules', status='passed'))
            print('PASS all 75 task cards and 225 rule descriptions', flush=True)

            def open_task(task):
                item = next(t for t in catalog if t['id'] == task)
                search.fill(f'{task:03d}')
                portal.get_by_role('button', name=f'{task:03d} {item["title"]}', exact=True).click()
                portal.get_by_role('button', name='版本 A', exact=True).click()
                portal.get_by_role('tab', name='执行 · inference', exact=True).click()
                with portal.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/v1/runs')) as response, context.expect_page() as opened:
                    portal.get_by_role('button', name='打开执行环境', exact=False).click()
                run = response.value.json(); created.append(run['id'])
                page = opened.value; page.set_default_timeout(30000)
                page.wait_for_url('**/native/**')
                address = urlsplit(run['application_url'])
                origin = address.scheme + '://' + address.netloc
                actor = {'Authorization': 'Bearer ' + address.fragment}
                with httpx.Client(trust_env=False) as client:
                    state = client.get(origin + '/api/runs/' + run['id'], headers=actor).json()['state']
                return run, page, state

            run, page, state = open_task(1)
            page.locator('.list__item').filter(has_text=state['source']['recipient']).first.click()
            page.locator('.chatInput textarea').fill(business.expected_effect(1, 'A', state)['outputs']['target'])
            with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/commands')) as saved:
                page.locator('.sendBtn').click()
            assert saved.value.status == 200
            page.screenshot(path=str(out / 'chat-delivery.png'))
            portal.get_by_role('button', name='检查最终交付', exact=True).click()
            expect(portal.get_by_text('检查通过', exact=True)).to_be_visible()
            with portal.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/reset')) as reset:
                portal.get_by_role('button', name='重置执行环境', exact=True).click()
            assert reset.value.status == 200 and reset.value.json()['epoch'] > run['epoch']
            results.append(dict(task=1, check='portal_direct_entry_send_eval_reset', status='passed'))
            print('PASS direct native Chat entry, delivery check and reset', flush=True)
            page.close()

            run, page, state = open_task(60)
            expect(page.get_by_role('heading', name='题目列表', exact=True)).to_be_visible(timeout=90000)
            page.get_by_role('button', name='查看本课程清单', exact=True).click()
            page.get_by_role('button', name='打开 PROJECT-01', exact=True).click()
            expect(page.get_by_role('heading', name='项目工作区', exact=True)).to_be_visible()
            page.get_by_role('button', name='运行本地检查与测试', exact=True).click()
            expect(page.get_by_role('heading', name='CHK-0001', exact=True)).to_be_visible(timeout=60000)
            expect(page.locator('[data-testid="stApp"]')).to_have_attribute('data-test-script-state', 'notRunning', timeout=60000)
            expect(page.get_by_role('textbox', name='编辑 pricing.py', exact=True)).to_have_value(state['world']['entries'][0]['files']['pricing.py'])
            expect(page.locator('[data-testid="stException"]')).to_have_count(0)
            page.screenshot(path=str(out / 'code-check.png'), full_page=True)
            results.append(dict(task=60, check='native_streamlit_navigation_real_python_check', status='passed'))
            print('PASS native Code navigation and Python check', flush=True)
            page.close()

            for task in (66, 67):
                run, page, state = open_task(task)
                canvas = page.locator('canvas'); expect(canvas).to_be_visible(timeout=90000)
                page.wait_for_timeout(1500)
                box = canvas.bounding_box(); assert box
                def click(x, y):
                    page.mouse.click(box['x'] + x * box['width'] / 1280, box['y'] + y * box['height'] / 960)
                    page.wait_for_timeout(350)
                click(1000, 210)
                wanted = games.expected(task, 'A', state)
                for row, col in wanted if task == 66 else [wanted]:
                    click(col * 50 + 100, row * 50 + 50)
                page.wait_for_timeout(700)
                page.screenshot(path=str(out / f'gomoku-{task}.png'))
                result = control.post(f'/v2/tasks/{task}/eval', json={'run_id': run['id']})
                assert result.status_code == 200 and result.json()['success'], result.text
                results.append(dict(task=task, check='linux_native_gomoku_pointer_input', status='passed'))
                print(f'PASS Gomoku {task} canvas actions and delivery evaluation', flush=True)
                page.close()
        finally:
            browser.close()
            for run_id in created:
                response = control.delete('/v1/runs/' + run_id)
                assert response.is_success
            (out / 'results.json').write_text(json.dumps(dict(video_recorded=False, cases=results), ensure_ascii=False, indent=2) + '\n')
    print('PASS deployed portal, all 75 cards, direct native entry, actual actions and reset; no video')


if __name__ == '__main__':
    main()
