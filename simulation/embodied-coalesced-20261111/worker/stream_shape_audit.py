"""Nonmutating, content-free Anthropic SSE response-shape diagnostics.

Call audit(out, receipt, raw) after reply.read(); always return the ORIGINAL raw.
No network, credentials, model requests, schema repairs or native history edits.
"""
from pathlib import Path
import hashlib,json,os,re,threading,time

EVENTS=frozenset(('message_start','content_block_start','content_block_delta','content_block_stop','message_delta','message_stop','ping','error'))
BLOCKS=frozenset(('text','thinking','redacted_thinking','tool_use','tool_result','image','document'))
DELTAS=frozenset(('text_delta','thinking_delta','signature_delta','input_json_delta','citations_delta'))
TOOLS=frozenset(('observe','action_batch','depth_points','demo_frames','history','done','giveup'))
_LOCK=threading.Lock()
_MAX_PARTIAL_CHARS=16*1024*1024
_MAX_FRAMES=200000
_FIELDS=('message','delta','usage','content_block','input','error','choices')

def kind(value):
    if value is None:return 'null'
    if isinstance(value,bool):return 'boolean'
    if isinstance(value,dict):return 'object'
    if isinstance(value,list):return 'array'
    if isinstance(value,str):return 'string'
    if isinstance(value,(int,float)):return 'number'
    return 'other'

def enum(value,allowed):
    return value if isinstance(value,str)and value in allowed else ('unrecognized_string'if isinstance(value,str)else kind(value))

def public_tool(value):
    if not isinstance(value,str):return None
    for prefix in ('mcp__vic__','mcp_vic_','vic_',''):
        if value.startswith(prefix)and value[len(prefix):]in TOOLS:return value[len(prefix):]
    return 'unrecognized_tool'

def frames(raw):
    # SSE data can span several lines; every dispatch joins them with LF.
    event=None;data=[]
    for line in raw.decode('utf-8',errors='replace').splitlines():
        if not line:
            if data:yield event,'\n'.join(data)
            event=None;data=[];continue
        if line.startswith(':'):continue
        field,separator,value=line.partition(':')
        if not separator:continue
        if value.startswith(' '):value=value[1:]
        if field=='event':event=value
        elif field=='data':data.append(value)
    if data:yield event,'\n'.join(data)

def summarize(raw):
    if not isinstance(raw,(bytes,bytearray)):raise TypeError('raw_must_be_bytes')
    rows=[];partials={};ended=[]
    def finish(index,reason):
        if index not in partials:return
        state=partials.pop(index);entry={'index':index,'partial_json_chars':state['chars'],'end':reason}
        if state['too_large']:entry.update(parse='too_large',root_type='unknown')
        else:
            try:entry.update(parse='valid',root_type=kind(json.loads(''.join(state['chunks']))))
            except(ValueError,RecursionError):entry.update(parse='invalid_json',root_type='unknown')
        ended.append(entry)
    for number,(wire_event,text)in enumerate(frames(raw)):
        if number>=_MAX_FRAMES:
            rows.append({'limit_reached':True});break
        row={'frame':number,'wire_event':enum(wire_event,EVENTS)if wire_event is not None else 'absent'}
        if text=='[DONE]':row['data_type']='done_sentinel';rows.append(row);continue
        try:value=json.loads(text)
        except(ValueError,RecursionError):row.update(data_type='invalid_json');rows.append(row);continue
        row['data_type']=kind(value)
        if not isinstance(value,dict):rows.append(row);continue
        event=value.get('type');row['event_type']=enum(event,EVENTS)if 'type'in value else 'absent'
        row['field_types']={field:kind(value[field])for field in _FIELDS if field in value}
        index=value.get('index');valid_index=type(index)is int and 0<=index<=1000000
        if 'index'in value:row['index']=index if valid_index else 'invalid'
        message=value.get('message')
        if isinstance(message,dict):row['message_field_types']={field:kind(message[field])for field in ('usage','content','stop_reason')if field in message}
        delta=value.get('delta')
        if isinstance(delta,dict):
            row['delta_type']=enum(delta.get('type'),DELTAS)if 'type'in delta else 'absent'
            row['delta_field_types']={field:kind(delta[field])for field in ('partial_json','text','thinking','signature','stop_reason')if field in delta}
        block=value.get('content_block')
        if isinstance(block,dict):
            row['block_type']=enum(block.get('type'),BLOCKS)if 'type'in block else 'absent'
            row['block_field_types']={field:kind(block[field])for field in ('input','text','thinking','signature','data')if field in block}
            if block.get('type')=='tool_use':row['public_tool']=public_tool(block.get('name'))
        if event=='content_block_start'and valid_index:
            if index in partials:finish(index,'replaced_start')
        if event=='content_block_delta'and valid_index and isinstance(delta,dict)and delta.get('type')=='input_json_delta':
            part=delta.get('partial_json')
            if isinstance(part,str):
                state=partials.setdefault(index,{'chunks':[],'chars':0,'too_large':False});state['chars']+=len(part)
                if state['chars']>_MAX_PARTIAL_CHARS:state['too_large']=True;state['chunks']=[]
                elif not state['too_large']:state['chunks'].append(part)
        if event=='content_block_stop'and valid_index:finish(index,'content_block_stop')
        rows.append(row)
    for index in list(partials):finish(index,'stream_ended_without_block_stop')
    return {'schema':'videoicl-content-free-sse-shape-v1','raw_bytes':len(raw),'raw_sha256':hashlib.sha256(raw).hexdigest(),'frames':rows,'partial_json_roots':ended}

def append(out,record):
    path=Path(out)/'dsh-response-shape.jsonl'
    encoded=(json.dumps(record,separators=(',',':'),ensure_ascii=True)+'\n').encode()
    with _LOCK:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND|getattr(os,'O_NOFOLLOW',0),0o600)
        try:
            os.fchmod(fd,0o600)
            # The relay is the sole process writer to this room; lock serializes
            # its request threads. Preserve any short-write remainder as well.
            while encoded:
                count=os.write(fd,encoded)
                if count<=0:raise OSError('shape_audit_short_write')
                encoded=encoded[count:]
        finally:os.close(fd)

def audit(out,receipt,raw):
    """Best effort; audit failures never change the response or escape caller."""
    rid=receipt.get('id',receipt.get('upstream_request_id'))if isinstance(receipt,dict)else None
    meta={'request_id':rid if isinstance(rid,str)and re.fullmatch('[a-fA-F0-9-]{16,64}',rid)else None,'observed_unix':time.time()}
    body_sha=receipt.get('request_body_sha256')if isinstance(receipt,dict)else None
    if isinstance(body_sha,str)and re.fullmatch('[a-fA-F0-9]{64}',body_sha):meta['request_body_sha256']=body_sha
    try:
        record=summarize(raw);record.update(meta);append(out,record)
    except BaseException as exc:
        # No exception messages: parse errors may embed provider content.
        try:append(out,dict(meta,schema='videoicl-content-free-sse-shape-v1',audit_error=type(exc).__name__))
        except BaseException:pass
    return None
