"""Semantic comparison for declared output formats, preserving method distinctions."""
import csv
import io
import json
import re


def _json(value):
    # Object member order is cosmetic; arrays and JSON value types are not.
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ValueError('Duplicate JSON field: '+k)
            out[k]=v
        return out
    parsed=json.loads(value,object_pairs_hook=pairs)
    return json.dumps(parsed,sort_keys=True,separators=(',',':'),ensure_ascii=False)


def normal(value, mode):
    if mode=='summary-values':
        header,sep,body=value.strip().partition('\n')
        if not sep or header.strip()!='build_artifact,passed,assertions':raise ValueError('Expected build_artifact,passed,assertions header')
        canonical=_json('['+body+']')
        values=json.loads(canonical)
        if len(values)!=3 or not isinstance(values[0],str) or type(values[1]) is not bool or not isinstance(values[2],list):
            raise ValueError('Expected JSON string, boolean and array values')
        return canonical
    if mode=='json':return _json(value)
    if mode=='jsonl':return [json.loads(line) for line in value.splitlines() if line.strip()]
    if mode=='trim-lines':return [line.strip() for line in value.replace('\r\n','\n').strip().split('\n') if line.strip()]
    if mode=='diff-lines':
        rows=[]
        for line in value.splitlines():
            if not line.strip():continue
            match=re.fullmatch(r'\s*([^:]+?)\s*:\s*(.*?)\s*->\s*(.*?)\s*',line)
            if not match:raise ValueError('Expected key: before -> after')
            rows.append(match.groups())
        return rows
    if mode in {'diff-csv','summary-csv'}:
        try:rows=list(csv.reader(io.StringIO(value.strip()),strict=True))
        except csv.Error as exc:raise ValueError('Invalid CSV quoting') from exc
        if mode=='diff-csv':
            if not rows or rows[0]!=['key','before','after'] or any(len(row)!=3 for row in rows):raise ValueError('Invalid difference CSV')
            return rows
        if len(rows)!=2 or rows[0]!=['build_artifact','passed','assertions'] or len(rows[1])!=3:raise ValueError('Invalid summary CSV')
        return [rows[0],[rows[1][0],_json(rows[1][1]),_json(rows[1][2])]]
    if mode=='summary-lines':
        rows=[]
        for line in value.splitlines():
            if not line.strip():continue
            key,sep,val=line.partition(':')
            if not sep:raise ValueError('Expected key: JSON value')
            rows.append((key.strip(),_json(val)))
        if [k for k,v in rows]!=['build_artifact','passed','assertions']:raise ValueError('Invalid summary fields or order')
        return rows
    if mode=='units':return [' '.join(line.split()) for line in value.splitlines() if line.strip()]
    if mode=='lines':return value.replace('\r\n','\n').rstrip('\n')
    return value


def output_mode(cid,condition,scope,original):
    if original=='json':return original
    if cid=='OS-H-01':return ['diff-lines','diff-csv','json'][condition]
    if cid=='OS-H-08':return ['summary-lines','json','summary-values'][condition]
    if cid in {'OS-H-02','OS-H-06','OS-H-12'}:return 'trim-lines'
    if cid in {'OS-M-11','OS-H-11'}:return 'units'
    return original


def summary_values(record):
    """Header plus comma-separated JSON values, without CSV string escaping."""
    keys=('build_artifact','passed','assertions')
    return ','.join(keys)+'\n'+','.join(json.dumps(record[k],ensure_ascii=False) for k in keys)
