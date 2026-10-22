"""Recorder-only schemas; never place condition-specific formats in actor files."""
JSON_NOTE='JSON 使用英文双引号；true/false 为布尔值，不加引号。缩进可为 0、2、4 个空格或 Tab，对象字段顺序不影响判分；数组按输入对象顺序填写。不要加 Markdown 代码围栏。'
TEXT_NOTE='这是纯文本，不加 JSON 外壳或 Markdown 代码围栏；一条结果一行，顺序对应输入。允许 CRLF/LF、行首尾空白和末尾换行不同；字段名、值、单位、精度及有意义的标点必须正确。'
FORMATS={
 'OS-M-10':[
  '输出一个 JSON 数组。每项只含 request_id（复制输入 ID）和 decision（字符串 Approved 或 Rejected）；approved=true 对应 Approved，false 对应 Rejected。',
  '输出一个 JSON 数组。每项只含 request_id（复制输入 ID）和 accepted（布尔值 true 或 false）；复制输入 approved 的真假值。',
  '输出一个 JSON 数组。每项只含 request_id（复制输入 ID）和 status（字符串 ok 或 error）；approved=true 对应 ok，false 对应 error。'],
 'OS-M-11':[
  '逐条读取输入 quantity；每行写 N pcs，其中 N 是 quantity 的整数值。例如数量 19 写 19 pcs。',
  '逐条用输入 quantity 除以该项 box，商为 C、余数为 R；每行写 C box + R pcs。余数为 0 也必须写 + 0 pcs。',
  '逐条用输入 quantity 除以该项 pack，商为 P、余数为 R；每行写 P pack + R pcs。余数为 0 也必须写 + 0 pcs。'],
 'OS-M-12':[
  '输出一个 JSON 对象，字段为 x、y、z、main_only、review_only；x/y/z 取 main，两个独有字段分别从所属分支保留。不要把 baseline、main、review、times 这些输入容器写进结果。',
  '输出一个 JSON 对象，字段为 x、y、z、main_only、review_only；x/y/z 取 review，两个独有字段分别从所属分支保留。不要把 baseline、main、review、times 这些输入容器写进结果。',
  '输出一个 JSON 对象，字段为 x、y、z、main_only、review_only；每个冲突字段比较 times.main 与 times.review，取时间较大分支的值，相同取 main。两个独有字段分别保留；不输出 times 容器。'],
 'OS-H-01':[
  '每项一行：key: before -> after。key、before、after 均复制本项输入，不加引号。例如 media.preview: compact -> review。',
  'CSV 第一行固定 key,before,after；后续每个输入对象占一行，三列依次复制 key、before、after。含逗号或双引号的单元格按标准 CSV 引号转义。',
  '输出 JSON 数组，每项包含 key、before、after 三个字符串字段，值均复制本项输入。'],
 'OS-H-02':[
  '每条变更一行：change_id: summary；替换为输入中的 ID 和正文，不写字段名字面量。Demo 不写 Version 头。',
  '每条变更一行：summary [change_id]；使用英文方括号。Demo 不写 Version 头。',
  '每条变更一行：[change_id] summary；使用英文方括号。Demo 不写 Version 头。'],
 'OS-H-06':[
  '保留四份资源的原名；只编辑缓存目录里的指南副本。保留 Field resources 标题，Map: 后写缓存地图的完整绝对路径，Contacts: 后写缓存通讯录的完整绝对路径，各占一行。',
  '四份资源命名为 project_id-原名；只编辑缓存指南副本。保留 Field resources 标题，Map: 后写更名后的缓存地图绝对路径，Contacts: 后写更名后的缓存通讯录绝对路径，各占一行。',
  '按四份公开资源的顺序，将其命名为 R0/R1/R2/R3 并保留扩展名；只编辑缓存指南副本。保留 Field resources 标题，Map: 后写缓存地图的绝对路径，Contacts: 后写缓存通讯录的绝对路径，各占一行。'],
 'OS-H-08':[
  '三行依次为 build_artifact: 值、passed: 值、assertions: 值。冒号后的每个值都使用 JSON：build_artifact 是带双引号的字符串，passed 是不带引号的 true/false，assertions 是 JSON 数组；每个断言保留 name、expected、actual、passed 及其类型。assertions 数组必须放在同一物理行。',
  '输出 JSON 对象，含 build_artifact（字符串）、passed（布尔值）、assertions（数组）。每个断言保留 name、expected、actual、passed，全部值及类型与输入一致。',
  'CSV 两行：表头 build_artifact,passed,assertions；数据行三列为构建 ID、true/false、完整断言 JSON 数组。第三列用双引号包裹，JSON 内每个双引号写成两个双引号（标准 CSV 转义）；每个断言保留 name、expected、actual、passed。'],
 'OS-H-11':[
  'Demo 只写一行 N B，N 为输入 released_bytes 的整数值；不写 released_bytes: 或 released_display: 字段名。',
  'Demo 只写一行 X.XXX KiB：released_bytes ÷ 1024，HALF_UP 四舍五入保留三位小数，精确值也补足三位。',
  'Demo 只写一行 X.XXXXXX MiB：released_bytes ÷ 1048576，HALF_UP 四舍五入保留六位小数，精确值也补足六位。'],
 'OS-H-12':[
  '每个输入标题一行：[rN] Title。N 取本条 revision，Title 取本条 title。例如 [r5] Review packet。Demo 不附加正文。',
  '每个输入标题一行：Title [rN]。N 取本条 revision，Title 取本条 title。例如 Review packet [r5]。Demo 不附加正文。',
  '每个输入标题一行：rN — Title。N 取本条 revision，Title 取本条 title；中间为长横线 —（不是减号 -）。Demo 不附加正文。'],
}

def demo_format(cid, variant):
    if cid not in FORMATS:return ''
    i='ABC'.index(variant)
    json_format=cid in {'OS-M-10','OS-M-12'} or cid=='OS-H-01' and i==2 or cid=='OS-H-08' and i==1
    note=JSON_NOTE if json_format else TEXT_NOTE
    if cid=='OS-H-01' and i==1 or cid=='OS-H-08' and i==2:
        note='使用标准 CSV，不加 Markdown 围栏；允许 CRLF/LF、末尾换行、可选的单元格双引号，以及单元格内 JSON 的等价空白和对象字段顺序。列顺序和数据类型必须正确，不要在单元格值外添加空格。'
    if cid=='OS-H-06':note+=' 这里只修改路径文字；不编辑下载原件，不用写 JSON。'
    return FORMATS[cid][i]+'\n'+note
