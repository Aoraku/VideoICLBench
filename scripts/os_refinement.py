"""Auditable task/lesson adaptation; never import an oracle video as human media."""
import json
from pathlib import Path
from os_output_contracts import demo_format

RELATIONS = [
'file-title word formatting while preserving extensions', 'destination grouping by file metadata',
'approved-version selection criterion', 'existing-versus-incoming conflict naming convention',
'memory threshold and inclusive comparison', 'contact-field transformation', 'device-category connection policy',
'anchor-relative time window with inclusive endpoints', 'task trigger setting', 'body-paragraph formatting',
'page-count threshold and strict comparison', 'section-heading page-break boundary',
'handoff folder grouping', 'change-entry text format', 'person-name and phone display format',
'reference ordering and tie-breaking', 'chapter heading numbering', 'timestamp representation',
'preservation of replaced file contents', 'stage task-name format', 'stage output-folder organization',
'approval-result encoding', 'quantity units, quotient and remainder representation', 'conflicting-field precedence',
'configuration difference record format', 'release change-entry format', 'recovery folder layout',
'preview size profile', 'paper, duplex and page-order profile', 'cached resource naming and corresponding links',
'local file conflict preservation', 'test-result summary representation', 'sensitive-field treatment',
'final delivery trigger setting', 'byte-unit conversion and rounding', 'revision marker placement in a title']

LESSONS = [
'对三份含不同词数、连续空格和大小写的文件改名。逐个展示改前、改后名称；扩展名、内容及无关文件保持。',
'将六份材料归档；两个项目都包含 resource-0 和 resource-1，同一种扩展名也来自不同项目。逐个展示来源、resource_key 与实际目标路径。',
'完成三个独立文档组。先展示每组四份候选的 Approved、Revision 和 Size；仅在 Approved = Yes 的三份中比较。A 取 Revision 最大，B 取 Size 最小，C 取 Size 最大；展示所选文件和复制结果。',
'处理三组同名来件与现有件，双方内容、修订号不同；展示保留后的两份文件名及内容，不覆盖丢失任何一侧。',
'查看九个后台进程的内存，覆盖 127/128/129、255/256/257、383/384/385 MB；按同一阈值处理所有对象，保留范围外系统进程。',
'修改三份日志副本，每份含不同联系人记录；展示原始值、处理后字段及保存结果，原始日志不变。',
'处理六个不同类别和初始连接状态的设备，展示命中与不命中类别的结果；不动范围外打印机。',
'对三个不同时间锚点导出窗口。展示锚点、两端边界、边界外记录和实际导出内容，所有时间按同一时区比较。',
'为三项已有作业保存同一触发设置；展示保存后的值，输入、输出、依赖不变，不运行作业。',
'整理三份正文不同的文档；每份含两段多行正文、标题和代码围栏。保存后展示正文的转换与其他部分保持。',
'处理八份页数不同的 Packet 作业；展示阈值本身与阈值两侧的队列状态。保留无关作业，不取消任何作业。',
'为三份内容不同但均含 Appendix、References、Signature 的文档插入分页符；展示分页边界和保存内容。',
'将已选定的三份批准材料放入相应交接目录；展示类别、来源和资源键，以及实际保存位置。无需录版本筛选和依赖收集。',
'将两条不同 ID、不同正文的变更写成指定格式。录三组不同变更，保留输入；不录发布文档成套编制。',
'将两位不同姓名、电话的联系人转换为对应显示格式。录三组不同联系人，不录现场安排关联。',
'对三份不同的六条 references 列表排序；三组使用不同文件名、逻辑编号和输入顺序，每组 Code、Config、Data 各两条，类别、编号、路径排序互不等同。逐组展示输入和保存结果，不录完整迁移。',
'给三个不同章节标题编号并保存。展示每个标题的编号对应关系，不录选稿、组稿和打印提交。',
'将两个不同日期/时间转换并保存。录三组，只改变表示形式，不改变时刻；不录事故搜集和时间线编排。',
'替换一份同名旧文件前先按指定方法保留旧内容，展示新旧两侧均可恢复。录三组不同内容，不录整个目录同步。',
'给 inventory、validate 两个阶段建立对应名称，展示阶段顺序与命名关系。录三组小项目，不录完整六阶段修复。',
'用已准备的四份资料展示 inventory、backup、restore 的输出目录关系。录三个独立项目；不录比较、复验和完整恢复演练。',
'将一项已知通过、一项已知拒绝的结论写为对应表示。录三组不同请求 ID；不录申请核查和修改人员主档。',
'展示不同产品容量下的数量表示。三组覆盖非零余数、整箱和整包；容量来自输入，不能统一猜一个容量，不录整批对账。',
'对基线、主分支、审阅分支进行局部字段合并；含主分支较新、审阅较新和同时间冲突，以及两边独有字段。录三组不同数值。',
'将两个可见配置差异写为记录，before 与 after 均取输入。录三组不同值，不查历史作业，不回退设置和重跑验证。',
'将两条变更写成指定条目格式。录三组不同 ID 和正文，不录修工具、构建、签名或发布。',
'把已给的数据与报告放入对应恢复目录及其 Reports 子目录。录三个不同项目，只展示布局，不筛快照或恢复任务。',
'使用已配对的片段和字幕设置同一预览规格，生成并查看实际输出尺寸。录三个项目，不录连接相机、下载或字幕校正。',
'用已准备的短文档设置纸型、单双面及顺序，生成布局与校样并查看结果。录三组，不提交打印，不录组稿和故障修复。',
'对已缓存的四份资源按同一方法命名，同步指南链接并验证离线可读。录三个项目；不录下载、设备恢复或缓存重建。',
'对一份同名冲突保存本地旧内容并放入来件，展示两侧位置和可恢复内容。录三个不同项目，不录路径修订和工作区启动。',
'将已经给出的测试结果转成摘要。三组使用不同 build_artifact、断言和值，保留全部字段；不录构建、测试修复和进程恢复。',
'对已准备的事故副本应用同一种敏感字段处理，展示不同记录及重复个人值的一致结果。录三组，不录日志搜集和打包。',
'给已验证的分发载荷设置最终触发方式，展示 Scheduled 且未派发。录三个不同项目，不录选盘、权限修复或前置流水线。',
'将 4096、3660、3845 三个字节数分别转换并保存，覆盖精确值及向下/向上舍入。基数 1024，HALF_UP；不录清理、备份或服务恢复。',
'给两个不同标题加入各自修订号。录三组不同标题和修订，不录撤回旧队列和重新提交。',
]
SINGLE={'OS-E-%02d'%i for i in range(1,13)} | {'OS-M-01','OS-M-05'}

def design(row):
    s=row['spec']; index=int(s['id'][-2:])-1+{'E':0,'M':12,'H':24}[s['id'].split('-')[1]]
    seeds=[1001] if s['id'] in SINGLE else [1001,1012,1026]
    if s['id']=='OS-M-11':seeds=[1001,7,9]
    if s['id']=='OS-H-11':seeds=[509,73,258]
    rule_notes={'OS-E-03':'先排除 Approved = No；A 比较 Revision（修订号），B/C 比较 Size（字节数）。Properties 可查看这些属性，文件名中的 r 后数字与 Revision 一致。若比较值相同，先按文件名，再按完整路径的 Unicode 码点顺序取首项。',
      'OS-E-06':'operator_id 是纯数字标识，例如 1004；C 写为 Contact-1004。保留 operator_id 本身及其他字段。',
      'OS-M-04':'A 按完整目标路径升序；B 按 number 数值升序；C 先按 Code → Config → Data 分组，同类别再按完整目标路径升序。路径逐字符比较（本题均为小写 ASCII，因此同目录内就是文件名字母序），不是按原始列表顺序。',
      'OS-E-05':'示范处理所有 Background worker，范围外 Protected system service 保持。',
      'OS-E-11':'示范处理所有 Packet，范围外 Unrelated draft 保持。',
      'OS-E-08':'闭区间包含两端；同一时区，不转换时刻。','OS-H-11':'1 KiB = 1024 B；1 MiB = 1048576 B。定点四舍五入 HALF_UP；精确值也保留规定的小数位。',
      'OS-H-08':'公共字段顺序为 build_artifact、passed、assertions；所有值保留源 JSON 类型与引号。C 的数据行由三个 JSON 值用逗号连接，不做 CSV 双重转义。',
      'OS-M-12':'双方独有字段都保留；C 时间相同取 main。', 'OS-H-06':'C 使用 R0/R1/R2/R3，对应四份公开资源的顺序，保留扩展名；指南内引用须同步。'}
    return dict(id=s['id'],title=s['title'],app=s['apps'],family='task36',difficulty=s['level'],
      task=s['prompt'], query_example=row['task'], relation=RELATIONS[index],
      rules={v:(s['rules'][v]+'。'+row['methods'][v]+' '+rule_notes.get(s['id'],'')+' '+demo_format(s['id'],v)).strip() for v in 'ABC'},
      demo_description=LESSONS[index],demo_instruction=row['demo_instruction'],demo_seeds=seeds,
      demo_groups=len(seeds),demo_scope='local-method-only',demo_actor='human',
      inference_description=s['query'],evaluation=s['predicates'],dependencies=s.get('interface_edges',[]),
      difficulty_reason={'easy':'一个持续环境内对多个新对象反复应用同一方法。','medium':'一个主要应用内完成有前后依赖的业务目标，视频方法仅是其中一个局部模块。','hard':'完成业务目标，并在多个桌面应用之间传递真实文件、配置或结果；视频只教其中一个局部模块。'}[s['level']])

def refine(source):
    path=source/'tasks36.py';text=path.read_text()
    def replace(old,new):
        nonlocal text
        if old not in text:raise ValueError('Pinned OS refinement target missing: '+old[:70])
        text=text.replace(old,new)
    # Preserve JSON values in the header-and-values representation for H08 C.
    for name in ('summary','source'):
        replace("csv_text([list("+name+"),[json.dumps(v) if not isinstance(v,str) else v for v in "+name+".values()]])", "summary_values("+name+")")
    replace('Write one CSV row with headers build_artifact,passed,assertions.', 'Write headers build_artifact,passed,assertions, then one row of comma-separated JSON values; preserve string quotes and the assertions array without CSV escaping.')
    replace('CSV build_artifact,passed,assertions', 'Header build_artifact,passed,assertions then comma-separated JSON values')
    for old,new in [('r8 — Title','r8 - Title'),('r8 — Meeting packet','r8 - Meeting packet'),('rN — Title','rN - Title'),('} — {x["title"]}', '} - {x["title"]}')]:
        replace(old,new)
    spec_path=source/'docs/TASK_CATALOGUE_36.json'
    spec=json.loads(spec_path.read_text())
    for task in spec['tasks']:
        if task['id']=='OS-H-08':
            task['rules']['C']='两行：字段名表头；按原顺序用逗号连接三个 JSON 值，保留字符串双引号及数组结构，不做 CSV 转义'
            task['demo']='展示多个实际测试结果到摘要的转换。公共字段为 build_artifact、passed、assertions，保留源 JSON 类型；C 用表头和一行逗号分隔的 JSON 值表示，不示范完整诊断流程。'
        if task['id']=='OS-H-12':task['rules']['C']='r{revision} - {title}（英文短横线，左右各一空格）'
    spec_path.write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n')
    replace('range(2 if b.scope==\'demo\' else 4)', 'range(3 if b.scope==\'demo\' else 4)')
    replace("        for i in range(n):\n            ext=['csv','txt','json'][i%3];key=f'resource-{i%2}';p=i%2",
        "        attributes=[('csv',0,0),('csv',1,1),('txt',0,1),('txt',1,0),('json',0,0),('json',1,1)]\n"
        "        b.rng.shuffle(attributes)\n"
        "        for i,(ext,p,resource) in enumerate(attributes):\n            key=f'resource-{resource}'")
    replace("f'edition-{tokens[j]}.txt'", "f'edition-r{revision}.txt'")
    replace("'operator_id':f'O{b.seed%997+j}','contact':f'op{b.seed%997+j}@example.test'",
            "'operator_id':f'{1000+b.seed%997+i*2+j}','contact':f'op{1000+b.seed%997+i*2+j}@example.test'")
    replace("'message':f'Record {s}'", "'message':'Incident anchor' if s==0 else f'Event record {j}'")
    replace('page_counts=[4,5,6,7,8,9]', "page_counts=[3,4,5,6,7,8,9,10] if b.scope=='demo' else [3,4,5,6,8,9]")
    replace('memories=[127,128,255,256,383,384]', "memories=[127,128,129,255,256,257,383,384,385] if b.scope=='demo' else [127,128,255,256,383,384]")
    replace('all six Background workers', 'all Background workers in the supplied batch')
    replace('the six Packet queue states', 'the Packet queue states in the supplied batch')
    # Recorder directions belong to the workbench, not files in the desktop.
    replace("        if scope=='demo':self.file('Example work order.txt','',parent='documents',identifier='demo-context')", '')
    begin=text.index("        if self.scope=='demo':\n            # Public business scope")
    end=text.index('        case=copy.deepcopy(self.case);',begin)
    text=text[:begin]+text[end:]
    replace('Approved example cover. Use the demonstrated printing profile.', 'Approved example cover.')
    replace('Approved meeting cover. Use the demonstrated printing profile. Preserve originals.', 'Approved meeting cover.')
    # Values in repeated local examples must differ; change only demo branches.
    replace("old=b.file('source.txt','Local edits must survive.'", "old=b.file('source.txt',f'Local edit {seed} must survive.'")
    replace("new=b.file('source.txt','Approved incoming content.'", "new=b.file('source.txt',f'Approved incoming content {seed}.'")
    replace("{'request_id':'R1','approved':True},{'request_id':'R2','approved':False}", "{'request_id':f'R{seed}-1','approved':True},{'request_id':f'R{seed}-2','approved':False}")
    replace("source={'baseline':{'x':1,'y':2,'z':3}", "source={'baseline':{'x':1,'y':2,'z':3}")
    replace("source=[{'key':'archive.format','before':'zip','after':'tar'},{'key':'verification.mode','before':'checksum','after':'full'}]", "source=[[{'key':'archive.format','before':'zip','after':'tar'},{'key':'verification.mode','before':'checksum','after':'full'}],[{'key':'media.preview','before':'compact','after':'review'},{'key':'scheduler.trigger','before':'manual','after':'idle'}],[{'key':'archive.format','before':'tar','after':'zip'},{'key':'media.preview','before':'detail','after':'compact'}]][seed%3]")
    replace("source=[{'path':'/new/z.js','number':3,'category':'Code'},{'path':'/new/b.json','number':1,'category':'Config'},{'path':'/new/a.csv','number':2,'category':'Data'},{'path':'/new/m.js','number':4,'category':'Code'},{'path':'/new/c.json','number':5,'category':'Config'}]",
        "fixtures=[([('zipper.js',3,'Code'),('beta.json',6,'Config'),('atlas.csv',2,'Data'),('engine.js',5,'Code'),('orbit.json',1,'Config'),('delta.csv',4,'Data')]),\n"
        "                  [('solar.js',8,'Code'),('alpha.json',3,'Config'),('lagoon.csv',7,'Data'),('beacon.js',2,'Code'),('zephyr.json',6,'Config'),('meridian.csv',5,'Data')],\n"
        "                  [('maple.js',2,'Code'),('quartz.json',9,'Config'),('apricot.csv',4,'Data'),('willow.js',7,'Code'),('cedar.json',3,'Config'),('harbor.csv',6,'Data')]]\n"
        "        entries=fixtures[{1001:0,1012:1,1026:2}.get(seed,seed%3)]\n"
        "        source=[{'path':f'/project-{seed}/'+name,'number':number,'category':category} for name,number,category in entries]\n"
        "        b.rng.shuffle(source)")
    replace("'Order Code, Config, Data.'][c]", "'Order Code, Config, Data; within each category, order full paths alphabetically.'][c]")
    replace("resources=[{'number':3,'category':'Code','name':'z-source.js'},{'number':1,'category':'Config','name':'b-settings.json'},{'number':2,'category':'Data','name':'a-data.csv'}]",
        "resources=[{'number':3,'category':'Code','name':'z-source.js'},{'number':1,'category':'Config','name':'b-settings.json'},{'number':2,'category':'Data','name':'a-data.csv'},"
        "{'number':6,'category':'Code','name':'c-tool.js'},{'number':5,'category':'Config','name':'e-flags.json'},{'number':4,'category':'Data','name':'d-report.csv'}]")
    # Three-way conflict values vary, while comparison/tie witnesses stay clear.
    marker="value={'x':[10,11,10][c],'y':[20,21,21][c],'z':[30,31,30][c],'main_only':'retain','review_only':'retain'}"
    replace(marker, "\n        for branch in ('baseline','main','review'):\n            for key in ('x','y','z'):source[branch][key]+=seed%97\n        "+marker+"\n        for key in ('x','y','z'):value[key]+=seed%97")
    # Explicit relation in public inference prompt, never the chosen A/B/C value.
    replace("case['task']=self.request+f' Learn {self.subject} from the supplied demonstration videos.'", "case['task']=self.request+' Use the '+VIDEOICL_RELATIONS[self.cid]+' demonstrated in the video.'+(VIDEOICL_OUTPUTS.get(self.cid,'')+' For JSON outputs, use the declared field names and value types; indentation and object key order are unrestricted.' if self.scope=='query' else '')")
    text += '\nVIDEOICL_RELATIONS = '+repr({f'OS-{level}-{n:02}':RELATIONS[i*12+n-1] for i,level in enumerate('EMH') for n in range(1,13)})+'\n'
    text += '\nVIDEOICL_OUTPUTS = '+repr({
      'OS-E-08':' Save each channel i export as window-i.jsonl in Output.',
      'OS-M-02':' Deliver Output/config.json (release_version), release-notes.txt (Version: header followed by change entries), and delivery-index.json with version, notes, config and changes (change IDs).',
      'OS-M-03':' Save an array in Output/field-guide.json. Each entry retains slot_id, person_id, site, time, resources (resource IDs), active, and adds contact in the demonstrated display format.',
      'OS-M-05':' Save print-master.txt and contents.json in Output. Each contents entry has chapter_id, heading and one-based page.',
      'OS-M-06':' Save Output/timeline.json with incident, events, recovered and verification_event. Each event retains event_id, time and message and adds channels: Application and/or System, based on the corresponding exports.',
      'OS-M-10':' Save people-working.json and acknowledgements.json as JSON arrays in Output. Keep all unchanged person fields; every active request acknowledgement contains request_id, person_id and the demonstrated decision field.',
      'OS-M-11':' Save two JSON arrays in Output: stock-working.json entries contain lot_id (string) and quantity (string in the demonstrated units); differences.json entries contain lot_id (string), before_pcs, after_pcs and difference_pcs (integer counts). Preserve lot order from lot-baselines.json.',
      'OS-M-12':' Save Output/merged.json as a JSON object of merged fields and merge-diff.json as a JSON object. The conflict record contains conflict_fields (names), values (resolved conflicting fields) and preserved_unique (names of both sides unique fields).',
      'OS-H-01':' Save Output/configuration-diff.txt with one record per restored setting, using key, before and after from the actual old and restored values. Use the record representation demonstrated in the video.',
      'OS-H-02':' The staged release notes start with Version: followed by the preserved release_version, then one line per approved change in the demonstrated format; the changes request is input, not an output to overwrite.',
      'OS-H-06':' In the cached guide retain the title and the two lines Map: <absolute cached map path> and Contacts: <absolute cached contacts path>. Keep other guide text and original downloaded resources.',
      'OS-H-08':' Save test-summary.txt with build_artifact, passed and assertions, in that field order when order matters. Assertions retain name, expected, actual and passed from the actual test result.',
      'OS-H-11':' Save maintenance-report.txt as two text lines: released_bytes: <integer> and released_display: <unit representation learned from the video>. The demo itself shows only the unit representation. Use base 1024 and decimal HALF_UP rounding.',
      'OS-H-12':' Edit the working cover, not revision-request.txt: line 1 is the marked title, line 2 is the approved body. The replacement cover title is Meeting packet, revision 8; its body is Approved revision 8. Retain the same paper, duplex and order settings as the supplied valid print configuration.',
    })+'\n'
    # Declare comparators rather than requiring the oracle's serialization bytes.
    replace('    def write(self,identifier,value,mode=None):',
            '    def write(self,identifier,value,mode=None):\n        mode=output_mode(self.cid,self.c,self.scope,mode)')
    replace("b.goal('domain',name='resource_content',source='source-1',value=notes['content'])",
            "b.goal('domain',name='resource_content',source='source-1',value=notes['content'],mode='trim-lines')")
    text+='\nfrom os_content_formats import output_mode, summary_values\n'
    path.write_text(text)
    (source/'os_content_formats.py').write_text(Path(__file__).with_name('os_content_formats.py').read_text())
    judge=source/'judge36.py';js=judge.read_text();start=js.index('def _normal(');end=js.index('\n\ndef check_goal',start)
    judge.write_text(js[:start]+'from os_content_formats import normal as _normal'+js[end:])
    domain=source/'domain_checks.py';ds=domain.read_text()
    old="entries=[line.split(': ',1) for line in guide['content'].splitlines() if line.startswith(('Map: ','Contacts: '))]"
    assert old in ds
    ds=ds.replace("delivered['source-1'].startswith('Version: '+expected+'\\n')", "(delivered['source-1'].strip().splitlines() or [''])[0].strip() == 'Version: '+expected")
    domain.write_text(ds.replace(old,"entries=[(line.partition(':')[0].strip(),line.partition(':')[2].strip()) for line in guide['content'].splitlines() if line.partition(':')[0].strip() in {'Map','Contacts'}]"))
    provenance=source/'artifact_provenance.py'
    provenance.write_text(provenance.read_text().replace("SOURCES=('workflows.py'", "SOURCES=('os_content_formats.py','workflows.py'"))
    # Present task data as normal file attributes and incident metadata, not goals.
    desktop=source/'static/desktop.js'
    ui=desktop.read_text()
    ui=ui.replace("let busy=Promise.resolve();", "let copiedPath=\"\";\nlet busy=Promise.resolve();")
    ui=ui.replace('autocomplete="off"></label></form>', 'autocomplete="off"></label>${btn("paste-path","Paste path",copiedPath?"":"disabled")}</form>')
    ui=ui.replace("${btn('copy','Copy')}", "${btn('copy','Copy')}${btn('copy-path','Copy path','title=\"Copy selected item path, or current folder when nothing is selected\"')}")
    ui=ui.replace("${btn('choose-document','Open…')}", "${btn('choose-document','Open…')}${btn('copy-path','Copy path',f?'':'disabled')}")
    ui=ui.replace("['copy','cut','rename','delete','properties']", "['copy','copy-path','cut','rename','delete','properties']")
    ui=ui.replace("btn(c,c[0].toUpperCase()+c.slice(1))", "btn(c,c==='copy-path'?'Copy path':c[0].toUpperCase()+c.slice(1))")
    ui=ui.replace("  else if(c==='properties')", """  else if(c==='copy-path'){
    if(w.app==='files'&&w.selected.length>1){notice='Select one file or folder to copy its path.'}
    else {
      const id=w.app==='editor'?w.fileId:(w.selected[0]||w.route);
      if(id){const value=fullpath(id);copiedPath=value;try{await navigator.clipboard.writeText(value);notice='Path copied: '+value}catch{dialog={type:'copy-path',title:'Copy path',value}}}
    }
  }
  else if(c==='paste-path'&&copiedPath){
    const input=root.querySelector(`[data-window="${w.id}"] input[name="command"]`);
    input.setRangeText(copiedPath,input.selectionStart,input.selectionEnd,'end');input.focus();return;
  }
  else if(c==='properties')""")
    ui=ui.replace("  if(dialog.type==='open')", "  if(dialog.type==='copy-path') fields=`<label>Absolute path<input aria-label=\"Absolute path\" value=\"${esc(dialog.value)}\" readonly></label><p>Select the path and copy it with Ctrl+C or Command+C.</p>`;\n  if(dialog.type==='open')")

    old="<span>${esc(f.kind)}</span><span>${f.kind==='folder'"
    assert old in ui
    ui=ui.replace(old,"<span>${esc(f.kind)}${typeof f.approved==='boolean'?(f.approved?' · Approved':' · Not approved'):''}</span><span>${f.kind==='folder'")
    old="content:JSON.stringify(info,null,2)"
    assert old in ui
    ui=ui.replace(old,"content:formatFileProperties(info)")
    ui += """

function formatFileProperties(info) {
  const labels={path:'Location',revision:'Revision',bytes:'Size (bytes)',approved:'Approved',
    resource_key:'Resource key',snapshot_version:'Snapshot version',snapshot_status:'Snapshot status',
    regenerable:'Regenerable',owners:'Owners',sha256:'SHA-256'};
  return Object.entries(labels).filter(([key])=>info[key]!==null&&info[key]!==undefined)
    .map(([key,label])=>label+': '+(typeof info[key]==='boolean'?(info[key]?'Yes':'No'):Array.isArray(info[key])?(info[key].join(', ')||'None'):info[key])).join('\\n');
}
"""
    old="${esc(selected.name)}</h2>${btn('export-log'"
    assert old in ui
    ui=ui.replace(old,"${esc(selected.name)}</h2>${records?.find(r=>r.message==='Incident anchor')?`<p><strong>Incident anchor:</strong> ${esc(records.find(r=>r.message==='Incident anchor').time)}</p>`:''}${btn('export-log'")
    # Keep action columns aligned regardless of print job name or page count.
    start=ui.index('function printQueue()')
    end=ui.index('function monitor(',start)
    queue=ui[start:end].replace('class="setting-card"','class="setting-card print-job"')
    queue=queue.replace("${p.status==='Cancelled'?'':btn(", '<div class="print-actions">${p.status===\'Cancelled\'?\'\':btn(')
    queue=queue.replace('data-status="Cancelled"`)}</div>`','data-status="Cancelled"`)}</div></div>`')
    ui=ui[:start]+queue+ui[end:]
    ui=ui.replace('  assignTraceIds();','  installVisibleSelects();\n  assignTraceIds();')
    ui+='\n'+Path(__file__).with_name('os_desktop_controls.js').read_text()
    desktop.write_text(ui)
    css=source/'static/desktop.css'
    css.write_text(css.read_text()+'\n'+Path(__file__).with_name('os_desktop_controls.css').read_text())
    engine=source/'workflows.py'
    runtime=engine.read_text()
    runtime=runtime.replace("not notes.startswith('Version: '+version+'\\n')", "(notes.strip().splitlines() or [''])[0].strip() != 'Version: '+version")
    old='source=f.get("source", f["id"]), source_hash=digest(f["content"]))["id"]'
    assert runtime.count(old)==1
    runtime=runtime.replace(old,'source=f.get("source", f["id"]), source_hash=digest(f["content"]),\n'
        '                            **({k:f[k] for k in ("revision","approved","resource_key") if k in f} if case.get("id")=="OS-E-03" else {}))["id"]')
    engine.write_text(runtime)
