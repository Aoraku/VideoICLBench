"""Recorder-only explanations of saved outputs; never change the task score."""
import json


def output_feedback(example, state):
    files = {f['id']: f for f in state.get('files', []) if not f.get('deleted')}

    def path(f):
        parts, seen = [], set()
        while f and f['id'] not in seen:
            seen.add(f['id']); parts.append(f['name']); f = files.get(f.get('parent'))
        return '/' + '/'.join(reversed(parts))

    by_path = {path(f): f for f in files.values()}
    messages = []
    for step in example.get('steps', []):
        if step.get('op') != 'write':
            continue
        target = step['target']; saved = by_path.get(target)
        if not saved:
            messages.append(f'{target}：找不到结果文件，请核对保存路径。'); continue
        actual = saved.get('content', '')
        if not actual.strip():
            messages.append(f'{target}：已保存的文件仍为空；请在正文填写后点击 Save。'); continue
        try:
            expected = json.loads(step['content'])
        except (ValueError, TypeError):
            continue  # Text/CSV outputs are diagnosed by the task's own judge.
        try:
            parsed = json.loads(actual)
        except json.JSONDecodeError as exc:
            messages.append(f'{target}：JSON 第 {exc.lineno} 行、第 {exc.colno} 列无法解析（{exc.msg}）。字符串值也必须用英文双引号，例如 "Approved"；只有 true/false/null 和数字不加引号。不要复制 Markdown 代码围栏。')
            continue
        def compare(a, b, where='$'):
            if type(a) is not type(b):
                return f'{where} 的 JSON 类型不符，请核对本组示例的字符串、布尔值、数组或对象类型。'
            if isinstance(b, dict):
                missing, extra = sorted(b.keys()-a.keys()), sorted(a.keys()-b.keys())
                if missing or extra:
                    return f'{where} 字段不符：缺少 {", ".join(missing) or "无"}；多出 {", ".join(extra) or "无"}。'
                return next((m for k in b if (m := compare(a[k], b[k], f'{where}.{k}'))), None)
            if isinstance(b, list):
                if len(a) != len(b):return f'{where} 条目数不符，请逐项处理本组输入。'
                return next((m for i,(x,y) in enumerate(zip(a,b)) if (m := compare(x,y,f'{where}[{i}]'))), None)
            if a != b:return f'{where} 的值与本组输入处理结果不符，请核对版本、组号和输入 ID。'
            return None
        mismatch = compare(parsed, expected)
        if mismatch:messages.append(f'{target}：JSON 可解析；{mismatch}')
    return messages
