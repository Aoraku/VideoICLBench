"""Pinned task design and persistent, human-reviewed OS demonstration library."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from .config import ROOT, DATA


def catalog(source):
    result=json.loads((Path(source)/'videoicl-catalog.json').read_text())
    pinned=json.loads((ROOT/'tasks/os/catalog.json').read_text())
    if result['commit']!=pinned['commit'] or result['implementation']['fingerprint']!=pinned['implementation']['fingerprint']:
        raise ValueError('OS release does not match the platform catalogue')
    return result


def demo_root(source=None, data=None):
    return (Path(data or DATA)/'os-recordings').resolve()

def recording_current(release, entry):
    if entry.get('design_version') != release['design_version']:
        return False
    fingerprint=entry.get('fingerprint')
    return (fingerprint == release['implementation']['fingerprint']
            or entry.get('case_id') in release.get('recording_compatibility',{}).get(fingerprint,[])
            or {0:'A',1:'B',2:'C'}.get(entry.get('convention')) in release.get('recording_variant_compatibility',{}).get(fingerprint,{}).get(entry.get('case_id'),[]))


def demonstrations(source, data=None, *, approved_only=False):
    release=catalog(source);root=demo_root(source,data);rows=[]
    for path in root.glob('*.json'):
        entry=json.loads(path.read_text())
        current=recording_current(release,entry)
        if approved_only and (not current or not entry.get('approved') or entry.get('recording_actor')!='human_browser'):continue
        rows.append({**entry,'historical':not current,'visual_review':'passed' if entry.get('approved') else 'pending'})
    rows.sort(key=lambda e:(e['created_at'],e['id']))
    return rows, '' if rows else '尚无人工示范录像。请在工作台录制、上传并审核；AI 参考录像不计入人工示范。'


def demo_file(source,case_id,variant,take=0,data=None):
    entries,_=demonstrations(source,data)
    choices=[e for e in entries if e['case_id']==case_id and e['convention']=='ABC'.index(variant)]
    if take<0 or take>=len(choices):raise FileNotFoundError('该版本尚无此人工录像')
    return choices[take],recording_file(source,choices[take],data)


def recording_file(source,entry,data=None):
    root=demo_root(source,data);path=(root/entry['video']).resolve()
    if not path.is_relative_to(root) or not path.is_file():raise FileNotFoundError('录像文件不可用')
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    if digest!=entry['sha256']:raise ValueError('录像文件校验失败')
    return path


def review_catalog(source,data=None):
    release=catalog(source);entries,notice=demonstrations(source,data);rows=[]
    for case in release['cases']:
        videos={}
        for index,variant in enumerate('ABC'):
            selected=[e for e in entries if e['case_id']==case['id'] and e['convention']==index]
            videos[variant]=[dict(label=f"人工录像 · {'审核通过' if e.get('approved') else '待审核'} · {e.get('reviewer') or '未署名'}", historical=e['historical'],approved=e.get('approved',False),created_at=datetime.fromtimestamp(e['created_at'],timezone.utc).isoformat(),
                url=f"/review-api/media/os/{case['id']}/{variant}?take={i}") for i,e in enumerate(selected)]
        rows.append(dict(id=case['id'],kind='os',title=case['title'],platform=case['app'],difficulty=case['difficulty'],
            rules=case['rules'],instruction=case.get('query_example',case['task']),relation=case['relation'],demo_description=case['demo_description'],
            demo_examples=case.get('demo_examples',{}),demo_apps=case.get('demo_apps',[]),
            demo_source='同事人工录制 · 审核通过后用于 inference',demo_notice=notice,
            benchmark_version=release['benchmark_version'],videos=videos))
    return rows
