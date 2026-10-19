"""Recorder-only GUI directions, derived from each actual demonstration fixture.

No directions, reference actions or expected answers enter the actor desktop.
"""
from pathlib import PurePosixPath

APP = {'write': 'Notepad', 'rename': 'File Explorer', 'move': 'File Explorer',
       'copy': 'File Explorer', 'process': 'Task Manager', 'device': 'Device Manager',
       'print-control': 'Device Manager', 'export-log': 'Event Viewer',
       'update-job': 'Task Scheduler', 'create-job': 'Task Scheduler',
       'run-job': 'Task Scheduler', 'setting': 'Settings', 'probe': 'Terminal', 'delete': 'File Explorer'}
SETTINGS = {
    'media.preview': ('Apps → Media previews → Preview output size', {'compact':'Compact · 640 × 360', 'review':'Review · 1280 × 720', 'detail':'Detailed · 1920 × 1080'}),
    'printer.paper': ('Bluetooth & devices → Printing → Paper size', {}),
    'printer.duplex': ('Bluetooth & devices → Printing → Duplex printing', {True:'On', False:'Off'}),
    'printer.order': ('Bluetooth & devices → Printing → Output page order', {'forward':'First page to last', 'reverse':'Last page to first'}),
    'privacy.method': ('Privacy → Evidence filtering → Personal field treatment', {'mask':'Mask values', 'remove':'Remove fields', 'pseudonym':'Stable pseudonyms'}),
}
TRIGGERS = {'manual':'Manual', 'idle':'When idle', 'plugged-in':'When plugged in'}


def explorer_path(path):
    """Explorer initially opens the current project, not the filesystem root."""
    parts=PurePosixPath(path).parts
    return 'File Explorer → 当前项目' + (' → ' + ' → '.join(parts[3:]) if len(parts)>3 else '')


def make_guide(group):
    steps=group['steps'];context=group['context'];apps=list(dict.fromkeys(APP[s['op']] for s in steps))
    inputs=[f for f in context['files'] if f['name']=='Example input.json']
    first=apps[0]
    if inputs:
        entry='桌面单击 Notepad → Open… → Document 选择 '+inputs[0]['path']+' → OK。先阅读输入，再打开结果文件。'
    elif first=='File Explorer':
        entry='桌面单击 File Explorer；窗口已在当前项目。按下面路径双击文件夹进入，文件单击选中，双击用 Notepad 查看。'
    elif first=='Notepad':
        entry='桌面单击 Notepad → Open… → Document 选择下列待编辑文件的完整路径 → OK。不要打开默认选中的 Unrelated note.txt。'
    else:
        entry=f'左下角 Start → {first}。桌面没有这个图标时，也可在 Start 的 Search applications 输入应用名。'
    items=[]
    if inputs:
        items.append({'title':'先展示输入材料','where':'Notepad → Open… → Document → '+inputs[0]['path']+' → OK',
                      'action':'展示文件里的各条输入，理解字段与对象；不要修改或保存输入文件。然后再次点击 Open… 切换到下面的结果文件。',
                      'expected':None})
    for s in steps:
        op=s['op'];target=s.get('target','');item={'title':'','where':'','action':'','expected':None}
        if op=='write':
            item.update(title='编辑并保存 '+PurePosixPath(target).name,
                where='Notepad → Open… → Document → '+target+' → OK',
                action='在正文编辑区逐项处理材料，展示输入与对应结果；点击顶部 Save。保存后重新 Open… 打开同一文件，确认内容仍在。',expected=s['content'])
            if '\f' in s['content']:
                lines=[s['content'][:i].count('\n')+1 for i,c in enumerate(s['content']) if c=='\f']
                item['action']='在顶部 Line 输入 '+', '.join(map(str,lines))+'（逐个处理）→ Go，将光标定位到标题行开头 → Insert page break → Save。底部应显示 Page breaks before lines 和页数；不要输入字面量 \\f。'
        elif op=='rename':
            item.update(title='重命名 '+PurePosixPath(target).name,where=explorer_path(str(PurePosixPath(target).parent)),
                action=f'单击 {PurePosixPath(target).name} → Rename → Name 填写 {s["name"]} → OK。检查列表里的新文件名。')
            if PurePosixPath(target).name==s['name']:item['action']=f'保留 {s["name"]} 原名，不需要重复重命名。可单击 Properties 展示属性，再点 Close。'
        elif op in {'copy','move'}:
            action='Copy' if op=='copy' else 'Cut'
            item.update(title=('复制 ' if op=='copy' else '移动 ')+PurePosixPath(target).name,
                where=explorer_path(str(PurePosixPath(target).parent)),
                action=f'单击 {PurePosixPath(target).name}，可用 Properties 查看属性（Close 返回）；点击 {action}。再进入 {explorer_path(s["parent"])}，点击 Paste。检查目标目录中的文件及内容。')
        elif op=='delete':
            item.update(title='移除已备份的目标旧件',where=explorer_path(str(PurePosixPath(target).parent)),
                action=f'先确认上一步已保留旧内容，再单击 {PurePosixPath(target).name} → Delete，为来件腾出原文件名。只处理此示范工作副本。')
        elif op=='process':
            item.update(title='处理进程 '+target,where='Start → Task Manager → Processes',
                action=f'找到 {target}，展示内存数值；点击 '+('Pause' if s['status']=='Paused' else 'Resume')+f'，确认状态为 {s["status"]}。')
        elif op=='device':
            value='Connected' if s['connected'] else 'Disconnected';button='Connect' if s['connected'] else 'Disconnect'
            item.update(title='设置设备 '+target,where='Start → Device Manager → All devices',
                action=f'找到 {target}，检查类别和连接状态。若已是 {value} 则保持；否则点击 {button}，确认状态为 {value}。')
        elif op=='print-control':
            item.update(title='处理打印作业 '+target,where='Start → Device Manager → Print queue',
                action=f'找到 {target}，展示页数；点击 '+('Pause' if s['status']=='Paused' else 'Resume')+f'，确认 {s["status"]}。不要点击 Cancel。')
        elif op=='update-job':
            item.update(title='修改触发方式 '+target,where='桌面 Task Scheduler → Task Scheduler Library',
                action=f'单击 {target} → Properties → Trigger 选择 {TRIGGERS[s["trigger"]]} → OK；确认列表 Trigger 列。其他字段保持，不点击 Run / retry。')
        elif op=='create-job':
            item.update(title='创建作业 '+s['name'],where='桌面 Task Scheduler → Create task…',
                action='依次填写：Task name = '+s['name']+'；Operation = '+s['kind']+'；Input folder = '+s['input']+'；Output folder = '+s['output']+'；Depends on = '+(s['dependency'] or 'None')+'；Trigger = '+TRIGGERS[s['trigger']]+'。点击 OK。')
        elif op=='run-job':
            item.update(title='运行并展示结果 '+target,where='桌面 Task Scheduler → Task Scheduler Library',
                action=f'单击 {target} → Run / retry，查看 Status 和 Last result；有 Open output 时点击它查看生成内容，再从底部任务栏返回 Task Scheduler。')
        elif op=='setting':
            route,values=SETTINGS[s['key']]
            item.update(title='设置 '+s['key'],where='桌面 Settings → '+route,
                action='下拉框选择 '+str(values.get(s['value'],s['value']))+'；选择后自动保存，再切回该页面确认。')
        elif op=='export-log':
            f=next(f for f in context['files'] if f['path']==target)
            item.update(title='导出 '+s['name'],where='Start → Event Viewer → '+f['log_channel']+' log → Export interval…',
                action=f'先查看事件时间。Destination folder 选择 {s["parent"]}；File name 填 {s["name"]}；Start time 填 {s["start"]}；End time 填 {s["end"]} → OK。用 Notepad → Open… 打开导出文件，展示边界内记录。')
        elif op=='probe':
            item.update(title='检查离线资源',where='Start → Terminal',
                action=f'输入 offline-test "{target}" 后回车，展示检查输出。')
        else:raise ValueError('Missing recorder GUI mapping: '+op)
        items.append(item)
    # Inputs and unchanged examples matter: omission from the mutation trace is not a rule.
    preserve='未列出需要修改的对象保持原状；展示它们与命中对象的区别。不要改动 Documents/Unrelated note.txt。'
    outputs=list(dict.fromkeys(s['target'] for s in steps if s['op']=='write'))
    return dict(apps=apps,entry=entry,inputs=[f['path'] for f in inputs],outputs=outputs,steps=items,preserve=preserve,
                finish='展示保存后的结果。试做后可回工作台点击「检查示范结果」；正式录制时在应用右下角点击「下一组」继续，最后点击「完成练习」，回工作台等待上传并审核。')
