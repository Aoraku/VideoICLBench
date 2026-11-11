"""Lossless compatibility for the observed missing initial tool_use.input only.

The complete, accepted response already exists. Fill the empty stream placeholder
only if every affected tool has complete, valid object JSON in later deltas.
Never create/edit tool argument values, call an API, or execute an action.
"""
import hashlib,json,re
TOOLS=frozenset(('observe','action_batch','depth_points','demo_frames','history','done','giveup'))
def public_tool(name):
 if not isinstance(name,str):return None
 for prefix in ('mcp__vic__','mcp_vic_','vic_',''):
  if name.startswith(prefix)and name[len(prefix):]in TOOLS:return name[len(prefix):]
 return None

def normalize(raw):
 meta={'schema':'videoicl-dsh-missing-input-placeholder-v1','before_sha256':hashlib.sha256(raw).hexdigest(),'changed':False,'filled_indices':[],'argument_values_changed':False,'reasoning_or_text_changed':False}
 try:
  parts=re.split(br'(\r?\n\r?\n)',raw);parsed=[];starts={};candidates={};complete=False;error=False
  for position in range(0,len(parts),2):
   frame=parts[position];lines=frame.splitlines();data=[];event=None
   for line in lines:
    if line.startswith(b'event:'):event=line[6:].lstrip(b' ').decode()
    elif line.startswith(b'data:'):data.append(line[5:].lstrip(b' '))
   if not data:continue
   value=json.loads(b'\n'.join(data))
   if not isinstance(value,dict):raise ValueError('non_object_SSE')
   kind=value.get('type')
   if event is not None and event!=kind:raise ValueError('event_type_mismatch')
   if kind=='error':error=True
   if kind=='message_stop':complete=True
   index=value.get('index')
   if kind=='content_block_start':
    if type(index)is not int or index in starts:raise ValueError('ambiguous_index')
    block=value.get('content_block');starts[index]=kind
    if not isinstance(block,dict):raise ValueError('non_object_block')
    if block.get('type')=='tool_use':
     if 'input'not in block:
      if not public_tool(block.get('name'))or not isinstance(block.get('id'),str)or not block['id']:raise ValueError('unknown_tool_identity')
      candidates[index]={'position':position,'value':value,'chunks':[],'closed':False,'public_tool':public_tool(block['name'])}
     elif not isinstance(block['input'],dict):raise ValueError('unsupported_initial_input_type')
   elif kind=='content_block_delta'and index in candidates:
    if candidates[index]['closed']:raise ValueError('delta_after_tool_block_closed')
    delta=value.get('delta')
    if not isinstance(delta,dict)or delta.get('type')!='input_json_delta'or not isinstance(delta.get('partial_json'),str):raise ValueError('invalid_tool_delta')
    candidates[index]['chunks'].append(delta['partial_json'])
   elif kind=='content_block_stop'and index in candidates:
    if candidates[index]['closed']:raise ValueError('duplicate_block_stop')
    candidates[index]['closed']=True
  if not candidates:meta['disposition']='no_observed_missing_input';return raw,meta
  if not complete or error:raise ValueError('stream_not_complete_success')
  for index,item in candidates.items():
   if not item['closed']or not item['chunks']:raise ValueError('tool_delta_not_complete')
   arguments=json.loads(''.join(item['chunks']))
   if not isinstance(arguments,dict):raise ValueError('tool_delta_root_not_object')
  # Only the already validated tool-start frame changes. All other bytes,
  # including every argument delta and every thinking signature, stay identical.
  for index,item in candidates.items():
   value=item['value'];value['content_block']['input']={};payload=json.dumps(value,separators=(',',':'),ensure_ascii=False).encode()
   lines=parts[item['position']].splitlines(keepends=True);replaced=[];written=False
   for line in lines:
    if not line.startswith(b'data:'):replaced.append(line);continue
    if not written:
     ending=b'\r\n'if line.endswith(b'\r\n')else b'\n'if line.endswith(b'\n')else b''
     replaced.append(b'data: '+payload+ending);written=True
   parts[item['position']]=b''.join(replaced)
  result=b''.join(parts);meta.update(changed=True,filled_indices=sorted(candidates),public_tools=[candidates[i]['public_tool']for i in sorted(candidates)],after_sha256=hashlib.sha256(result).hexdigest(),disposition='filled_only_missing_empty_initial_placeholder')
  return result,meta
 except (ValueError,TypeError,KeyError,UnicodeError,RecursionError)as exc:
  meta['disposition']='preserved_unmodified_incompatible_stream';meta['rejection_class']=type(exc).__name__;return raw,meta
