"""Private native-frontend QA. Rules stay in this harness, never in the browser.

Inputs use rendered controls and keyboard/mouse events. No select_option, injected
app state, or direct command requests are used to complete tasks. Eval reads the
same persisted domain records as the production evaluator.
"""
import asyncio, json, os, secrets, sys, time, re
from pathlib import Path
import httpx, uvicorn
from playwright.async_api import async_playwright
from vic.config import ROOT
from vic.business import generate, expected_effect
from vic_apps.domain import initialize
from vic_apps.server import create_app
from vic.application_eval import evaluate

async def main():
    subset=[int(x) for x in sys.argv[1].split(',')] if len(sys.argv)>1 else list(range(1,76))
    variants=sys.argv[2] if len(sys.argv)>2 else 'A'
    secret=secrets.token_hex(32); directory=ROOT/'.local/native-acceptance'
    directory.mkdir(parents=True,exist_ok=True)
    os.environ.update(VIC_APP_DATA=str(directory/'data'),VIC_APP_RUNTIME_TOKEN=secret,VIC_NATIVE_SELF_BASE='http://127.0.0.1:8782')
    server=uvicorn.Server(uvicorn.Config(create_app(),host='127.0.0.1',port=8782,log_level='error'))
    serving=asyncio.create_task(server.serve())
    while not server.started:await asyncio.sleep(.05)
    results=[]
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8782',headers={'Authorization':'Bearer '+secret},trust_env=False,timeout=60) as client, async_playwright() as pw:
      browser=await pw.chromium.launch()
      try:
       for task in subset:
        for variant in variants:
         rid=secrets.token_hex(16);token=secrets.token_hex(32);initial=initialize(generate(task,10001));module=initial['app']
         response=await client.post('/internal/prepare',json=dict(run_id=rid,token=token,app=module,epoch=0,state=initial));response.raise_for_status()
         context=await browser.new_context(viewport={'width':1280,'height':960},permissions=['clipboard-read','clipboard-write']);page=await context.new_page();page.set_default_timeout(12000)
         errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
         async def click(locator):
          await locator.scroll_into_view_if_needed();box=await locator.bounding_box();assert box,'Control not rendered'
          await page.mouse.click(box['x']+box['width']/2,box['y']+box['height']/2);await page.wait_for_timeout(150)
         async def button(name,exact=True):await click(page.get_by_role('button',name=name,exact=exact))
         async def text(locator,value):
          await click(locator);await page.keyboard.press('ControlOrMeta+A');await page.keyboard.insert_text(value)
         async def persisted():
          r=await client.get(f'/internal/runs/{rid}');r.raise_for_status();return r.json()
         async def label(row,value):
          await click(row.locator('.label-menu>button'));await click(page.get_by_role('option',name=value,exact=False))
         t=task;s=initial;effect=expected_effect(t,variant,s) if t<66 else None
         try:
          await page.goto(f'http://127.0.0.1:8782/apps/{module}/{rid}#{token}')
          await click(page.get_by_role('link',name='打开应用'))
          if module=='code':await page.get_by_role('heading',name='题目列表',exact=True).wait_for(timeout=60000)
          else:await page.wait_for_timeout(500)
          await page.screenshot(path=str(directory/f'{task}-{variant}-home.png'))
          if module in ('media','blog','studio','travel','shop','bank'):
           nav=page.locator('.product-nav')
           async def go(name):await click(nav.get_by_role('button',name=name,exact=False))
           if t in (21,36,37,44,45,46):
            if t==21:await go('收藏夹');control=page.locator('.media-folder input');save='保存名称'
            elif t==36:await button('继续编辑 →');control=page.locator('.blog-title-input');save='保存草稿'
            elif t==37:await go('提示词库');control=page.locator('textarea');save='保存模板'
            elif t==44:await go('常用旅客');control=page.get_by_label('旅客显示姓名');save='保存旅客'
            elif t==45:await click(page.locator('.shop-image-link').first);control=page.get_by_label('备注内容');save='保存备注'
            else:await go('转账汇款');control=page.get_by_label('备注',exact=True);save='保存转账备注'
            await text(control,effect['outputs']['target']);await button(save)
           elif t in (25,26,38,39,47,48,49,50):
            await go({25:'视频资料库',26:'视频资料库',38:'我的草稿',39:'内容项目',47:'车次查询',48:'所有商品',49:'交易明细',50:'我的账户'}[t])
            for target,value in effect['labels'].items():
             if value:await label(page.locator(f'[data-object-id="{target}"]'),value)
           elif t==35:
            await go('播放队列')
            for dest,target in enumerate(effect['order']):
             current=(await persisted())['state']['domain']['orders']['main'];name=initial['domain']['objects'][target]['name']
             for _ in range(current.index(target)-dest):await button('上移 '+name)
           elif t in (31,40,41,51,52,53):
            target=effect['selection'][0];name=initial['domain']['objects'][target]['name']
            await go({31:'视频资料库',40:'我的草稿',41:'模型库',51:'车次查询',52:'所有商品',53:'交易明细'}[t])
            row=page.locator(f'[data-object-id="{target}"]')
            if t==31:await click(row.locator('.media-thumbnail'))
            elif t==40:await click(row.get_by_role('button',name=name,exact=True));await button('发布文章')
            elif t==41:await click(row.get_by_role('button',name='使用此模型'))
            elif t==51:await click(row.get_by_role('button',name='查看行程'));await button('选择此行程')
            elif t==52:await click(row.get_by_role('button',name='选择此商品'))
            else:await click(row.get_by_role('button',name='查看明细 →'))
           elif t in (34,42,43,54,55,56,57):
            await go({34:'稍后观看',42:'我的草稿',43:'内容项目',54:'车次查询',55:'所有商品',56:'转账汇款',57:'余额提醒'}[t])
            for target,action in effect['actions']:
             name=initial['domain']['objects'][target]['name'];row=page.locator(f'[data-object-id="{target}"]')
             if t==42:
              await click(row.get_by_role('button',name=name,exact=True));await button('发布文章');await go('我的草稿')
             elif t==43:
              await click(page.locator('.studio-project-layout aside').get_by_role('button',name=name));await button('检查');await button(action)
             elif t==54:
              await click(row.get_by_role('button',name='查看行程'));await button('确认预订');await go('车次查询')
             elif t==55:
              await click(row.get_by_role('button',name='♡ 收藏' if action=='收藏' else action,exact=True))
             elif t==56:
              await click(row.get_by_role('button',name='核对并转账'));await button('确认转账');await go('转账汇款')
             else:await click(row.get_by_role('button',name=action,exact=True))
           else:raise AssertionError(f'No workflow for {t}')
          elif module=='music':
           if t==17:
            await click(page.locator('a[href*="/songs/target/"]').first);await button('编辑显示名称');await text(page.locator('#nameForm input'),effect['outputs']['target']);await click(page.locator('#nameForm button'))
           elif t==18:
            await click(page.get_by_role('link',name='播放列表',exact=True));await button('新建播放列表');await text(page.locator('#playlistForm input'),effect['outputs']['target']);await click(page.locator('#playlistForm button'))
           else:
            await click(page.get_by_role('link',name='我的音乐',exact=True))
            if t==22:
             for target,value in effect['labels'].items():
              if value:await click(page.locator(f'[data-label-open="{target}"]'));await click(page.locator(f'[data-label="{value}"][data-target="{target}"]'))
            elif t==28:
             for dest,target in enumerate(effect['order']):
              current=(await persisted())['state']['domain']['orders']['main']
              for _ in range(current.index(target)-dest):await click(page.locator(f'[data-move="-1"][data-target="{target}"]'))
            elif t==27:
             await click(page.locator(f'[data-song="{effect["selection"][0]}"] a').first);await click(page.locator('[data-play]'))
            elif t==32:
             for target,_ in effect['actions']:await click(page.locator(f'[data-add="{target}"]'))
          elif module=='news':
           if t in (19,20):
            await click(page.locator('nav [data-page="editor"]'));await text(page.locator('#editorForm textarea'),effect['outputs']['target']);await click(page.locator('#editorForm button[type="submit"]'))
           else:
            await click(page.locator('nav [data-page="articles"]'))
            if t in (23,24):
             for target,value in effect['labels'].items():
              if value:await click(page.locator(f'[data-menu="{target}"]'));await click(page.get_by_role('option',name=value,exact=True))
            elif t==29:await click(page.locator(f'[data-open="{effect["selection"][0]}"]'))
            elif t==30:
             for target in effect['selection']:await click(page.locator(f'[data-reading="{target}"]'))
             await button('保存阅读清单')
            elif t==33:
             for target,value in effect['actions']:await click(page.locator(f'[data-action="{value}"][data-target="{target}"]'))
          elif module=='chat':
           async def conversation(target):
            return page.locator('.list__itemWrap').filter(has=page.locator('.list__title',has_text=initial['domain']['objects'][target]['name']))
           async def message_menu(target):
            index=next(i for i,x in enumerate(initial['items']) if x['id']==target);bubble=page.locator(f'#msg-{100+index} .bubbleWrap');await bubble.scroll_into_view_if_needed();box=await bubble.bounding_box();await page.mouse.click(box['x']+20,box['y']+20,button='right');await page.wait_for_timeout(100)
           if t in (1,3,4,5,13):await click(page.locator('.list__item').filter(has_text=s['source']['recipient']).first)
           if t in (1,3,4):
            await text(page.locator('.chatInput textarea'),effect['outputs']['target']);await click(page.locator('.sendBtn'))
           elif t in (2,6,9):
            await click(page.locator('a[title="通讯录"]'));await button('联系人',False);await page.wait_for_timeout(250)
            if t==2:
             await click(page.locator('.wxAccRow').filter(has_text=s['source']['text']).first);await click(page.get_by_role('link',name='查看完整资料'));await text(page.get_by_placeholder('无备注则留空'),effect['outputs']['target']);await button('保存')
            elif t==6:
             for target,value in effect['labels'].items():
              if value:
               name=initial['domain']['objects'][target]['name'];await click(page.locator('.wxAccRow').filter(has_text=name));await click(page.locator('.wxGroupPicker__trigger'));await click(page.get_by_role('option',name=value,exact=True));await click(page.locator('.wxGroupAssign__btn'))
            else:
             name=initial['domain']['objects'][effect['selection'][0]]['name'];await click(page.locator('.wxAccRow').filter(has_text=name));await button('发消息')
           elif t==5:
            for target,value in effect['labels'].items():
             if value:await message_menu(target);await click(page.get_by_role('menuitem',name=value,exact=False))
           elif t in (7,8):
            for target,value in effect['labels'].items():
             if value:await click((await conversation(target)).get_by_role('button',name='会话操作'));await click(page.get_by_role('menuitem',name=value,exact=True))
           elif t==10:await click((await conversation(effect['selection'][0])).locator('.list__item'))
           elif t==11:
            await button('聊天文件');name=initial['domain']['objects'][effect['selection'][0]]['name'];await click(page.get_by_role('button',name=name,exact=False).last);await button('发送给林若宁')
           elif t==12:
            for dest,target in enumerate(effect['order']):
             current=(await persisted())['state']['domain']['orders']['main']
             for _ in range(current.index(target)-dest):await click((await conversation(target)).get_by_role('button',name='会话操作'));await click(page.get_by_role('menuitem',name='上移会话'))
           elif t==13:
            for target,value in effect['actions']:
             await message_menu(target);await click(page.get_by_role('menuitem',name=value,exact=False))
             if value=='转发':await click(page.get_by_role('dialog',name='转发消息').get_by_role('button',name=s['source']['recipient'],exact=False))
             if value=='收藏':await click(page.get_by_role('dialog').get_by_role('button',name='保存',exact=True))
           elif t==14:
            for target,value in effect['actions']:
             await click((await conversation(target)).get_by_role('button',name='会话操作'));await click(page.get_by_role('menuitem',name={'归档':'归档会话','置顶':'置顶会话','静音':'消息免打扰'}[value],exact=True))
          elif module=='im':
           if t==15:
            await click(page.get_by_title('新建',exact=True));await click(page.get_by_text('发起群聊',exact=True));await page.wait_for_timeout(400)
            for target in effect['members']:await button(initial['domain']['objects'][target]['name'],False)
            await click(page.get_by_role('button',name=re.compile(r'完\s*成')))
           else:
            await click(page.get_by_text('林若宁',exact=True).first);await page.wait_for_timeout(300)
            for target,value in effect['actions']:
             bubble=page.get_by_text(initial['domain']['objects'][target]['text'],exact=True);await bubble.scroll_into_view_if_needed();box=await bubble.bounding_box();await page.mouse.click(box['x']+15,box['y']+15,button='right');await click(page.get_by_role('menuitem',name={'已读':'确认已读','星标':'星标消息','回复':'回复'}[value],exact=True))
             if value=='回复':await text(page.locator('textarea:not([aria-hidden="true"])'),s['source']['fixed_reply']);await click(page.get_by_role('button',name=re.compile(r'发\s*送')))
          elif module=='code':
           if t in (59,60,65):
            await click(page.get_by_text('我的代码与笔记',exact=True))
            if t in (59,60):await text(page.locator('textarea'),effect['outputs']['target']);await button('保存文件')
            else:
             for target,value in effect['actions']:
              name=initial['domain']['objects'][target]['name'];panel=page.locator('[data-testid="stExpander"]').filter(has_text=name+' · solution.py');await click(panel.locator('summary'));await click(panel.get_by_role('button',name='本地检查',exact=True));await click(panel.get_by_role('button',name='提交',exact=True))
           elif t==58:
            await click(page.get_by_role('button',name='进入题目').first);await button('提交代码');await text(page.locator('textarea'),effect['outputs']['target']);await button('提交')
           elif t in (62,63):
            if t==62:
             for target,value in effect['labels'].items():
              if value:
               idx=next(i for i,x in enumerate(s['items']) if x['id']==target);await click(page.get_by_role('radio',name=value,exact=True).nth(idx));await click(page.get_by_role('button',name='保存标签',exact=True).nth(idx))
            else:
             idx=next(i for i,x in enumerate(s['items']) if x['id']==effect['selection'][0]);await click(page.get_by_role('button',name='选择这道题').nth(idx))
           else:
            await click(page.get_by_text('查看提交',exact=True))
            if t==61:
             for target,value in effect['labels'].items():
              if value:
               idx=next(i for i,x in enumerate(s['items']) if x['id']==target);await click(page.get_by_role('radio',name=value,exact=True).nth(idx));await click(page.get_by_role('button',name='保存结果标签').nth(idx))
            else:
             idx=next(i for i,x in enumerate(s['items']) if x['id']==effect['selection'][0]);await click(page.get_by_role('button',name='查看代码').nth(idx))
          elif module=='gomoku':
           from vic.games import expected
           canvas=page.locator('canvas');await canvas.wait_for(timeout=60000)
           await page.wait_for_timeout(1200)
           await page.screenshot(path=str(directory/f'{task}-{variant}-home.png'))
           box=await canvas.bounding_box();assert box,'SDL canvas not rendered'
           async def board_click(x,y):
            await page.mouse.click(box['x']+x*box['width']/1280,box['y']+y*box['height']/960)
            await page.wait_for_timeout(300)
           await board_click(1000,210)
           wanted=expected(t,variant,s)
           for row,col in (wanted if t==66 else [wanted]):await board_click(col*50+100,row*50+50)
           await page.wait_for_timeout(500)
          elif module=='games':
           from vic.games import expected, stopping_paths
           await button('打开练习棋盘 →')
           wanted=expected(t,variant,s)
           if t==68:await button(wanted)
           elif t==69:
            for direction in stopping_paths(s)[variant]:await button(direction)
            await button('结束练习')
           elif t in (70,73):
            for r,c in wanted:await button(f'第{r+1}行第{c+1}列')
           elif t==71:
            r,c=s['candidates'][0];await button(f'第{r+1}行第{c+1}列');await click(page.locator('.games-numbers').get_by_role('button',name=str(wanted),exact=True))
           else:
            r,c=wanted;await button(f'第{r+1}行第{c+1}列')
          else:raise AssertionError('Native workflow not implemented in QA harness: '+module)
          await page.wait_for_timeout(300)
          snap=await persisted();clipboard=await page.evaluate('navigator.clipboard.readText()') if t==43 and variant=='B' else None;outcome=evaluate(initial,snap['state'],variant,snap['events'],clipboard)
          assert outcome['success'],outcome
          assert not errors,errors
          await page.screenshot(path=str(directory/f'{task}-{variant}-done.png'))
          await page.reload();await page.wait_for_timeout(400)
          again=await persisted();assert evaluate(initial,again['state'],variant,again['events'],clipboard)['success']
          results.append(dict(task=task,variant=variant,status='passed',surface='native',persisted=True))
          print(f'{task}{variant} PASS',flush=True)
         except Exception as exc:
          results.append(dict(task=task,variant=variant,status='failed',error=str(exc)))
          print(f'{task}{variant} FAIL {str(exc)[:400]}',flush=True)
          await page.screenshot(path=str(directory/f'{task}-{variant}-failed.png'))
         finally:
          with (directory/'history.jsonl').open('a') as history:history.write(json.dumps(results[-1],ensure_ascii=False)+'\n')
          await context.close();await client.delete(f'/internal/runs/{rid}')
       (directory/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
      finally:
       await browser.close();server.should_exit=True;await serving
    if any(x['status']=='failed' for x in results):raise SystemExit(1)
if __name__=='__main__':asyncio.run(main())
