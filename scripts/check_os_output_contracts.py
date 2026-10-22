"""Exercise edited output representations through persisted task evaluation, no video."""
import argparse,copy,csv,io,json,sys
from pathlib import Path
IDS=['OS-M-10','OS-M-11','OS-M-12','OS-H-01','OS-H-02','OS-H-06','OS-H-08','OS-H-11','OS-H-12']

def cosmetic(value,mode):
 if mode=='json':return json.dumps(json.loads(value),sort_keys=True,indent=4,ensure_ascii=False)+'\r\n'
 if mode=='diff-csv':
  stream=io.StringIO();writer=csv.writer(stream,quoting=csv.QUOTE_ALL,lineterminator='\r\n');writer.writerows(csv.reader(io.StringIO(value)));return stream.getvalue()
 if mode=='summary-csv':
  rows=list(csv.reader(io.StringIO(value)));rows[1][2]=json.dumps(json.loads(rows[1][2]),sort_keys=True)
  stream=io.StringIO();writer=csv.writer(stream,quoting=csv.QUOTE_ALL);writer.writerows(rows);return stream.getvalue()
 if mode=='summary-lines':
  return '\r\n'.join(k+' : '+json.dumps(json.loads(v),sort_keys=True) for line in value.splitlines() for k,_,v in [line.partition(':')])+'\r\n'
 return '\r\n'.join('  '+line+'  ' for line in value.splitlines())+'\r\n'

def main(source):
 sys.path.insert(0,str(source.resolve()));import tasks36,workflows
 from os_content_formats import output_mode
 count=0
 for cid in IDS:
  for condition in range(3):
   for scope,seed in [('module-demo',1001),('module-demo',1012),('module-demo',1026),('standard',4201)]:
    ep=tasks36.generate(cid,condition,seed,scope)
    for action in ep['reference']:
     a=copy.deepcopy(action)
     if a['op']=='write':
      goals=[g for g in ep['_judge36']['goals'] if g['type']=='content' and g['id']==a['target']]
      mode=goals[0].get('mode') if goals else 'trim-lines'
      # Only transform declared outputs, not input scripts consumed by jobs.
      if goals or cid=='OS-H-02' and 'Version:' in a['content']:
       a['content']=cosmetic(a['content'],mode)
     workflows.transition(ep,a)
    result=workflows.evaluate(ep)
    assert result['success'],(cid,condition,scope,result['failed_checks'])
    if scope=='module-demo':
     action=next(a for a in ep['reference'] if a['op']=='write');workflows.transition(ep,{**action,'content':'incorrect result'})
     assert not workflows.evaluate(ep)['success'],(cid,condition,'bad content accepted')
    count+=1
  print(cid,'cosmetic variations pass; incorrect output rejected',flush=True)
 print(json.dumps({'verified_output_episodes':count,'video_recorded':False}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=Path);main(p.parse_args().source)
