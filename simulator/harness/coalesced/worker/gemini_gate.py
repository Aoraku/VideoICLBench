"""MyAPI-primary-only account admission; existing requests always drain normally."""
from contextlib import contextmanager
import json,os,time,uuid
from pathlib import Path
if __package__:
 from .gemini_gate_core import FileConcurrencyGate,GateOwnershipError,_claim_directory,_release_directory,validated_config
else:
 from gemini_gate_core import FileConcurrencyGate,GateOwnershipError,_claim_directory,_release_directory,validated_config
CAMPAIGN='five-cli-iclworld-20261107'
SUCCESS_THRESHOLD=32
INCREASE_INTERVAL=60

def config_for(out):
 # All production rooms in this fixed campaign must share the same account gate.
 # Unrelated test fixtures/campaigns retain their existing routing behavior.
 parents=[p for p in Path(out).resolve().parents if p.name==CAMPAIGN]
 return parents[0]/'api-admission/myapi/config.json' if parents else None

def atomic(path,value):
 temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
 with temp.open('x') as f:json.dump(value,f,separators=(',',':'))
 os.chmod(temp,0o600);temp.replace(path)

@contextmanager
def primary_admission(out,receipt):
 config=config_for(out)
 if config is None:yield None;return
 gate=FileConcurrencyGate(config,poll_seconds=.5)
 started=time.time();receipt['primary_gate']={'scope':gate.scope,'queued_at':started,'phase':'waiting'}
 try:lease=gate.acquire()
 except Exception as exc:
  receipt['primary_gate'].update(phase='admission_failed',error_type=type(exc).__name__,io_phase=getattr(exc,'gate_io_phase',None),upstream_started=False)
  raise
 receipt['primary_gate'].update(slot=lease.slot,queue_wait_seconds=lease.queue_wait_seconds,admitted_at=time.time(),phase='upstream_reserved',limit_at_admission=validated_config(config)['limit'])
 try:yield config
 finally:
  try:
   lease.release();receipt['primary_gate'].update(released_at=time.time(),phase='released')
  except (OSError,GateOwnershipError) as exc:
   # Preserve the reservation for explicit reconciliation. A completed paid
   # response must not become a retry merely because lease cleanup is uncertain.
   receipt['primary_gate'].update(phase='release_uncertain',release_uncertain=True,error_type=type(exc).__name__,needs_reconciliation=True)

def account_concurrency_error(status,evidence):
 if status!=429:return False
 error=evidence.get('upstream_error') or {}
 return 'concurrency limit exceeded for account' in str(error.get('message','')).lower()

def record_result(config,status,evidence,*,completed,count_only=False,now=None):
 if config is None or count_only:return
 now=time.time() if now is None else now
 cfg=validated_config(config);directory=Path(cfg['lock_directory']);guard=directory/'adaptive.guard'
 token=None;deadline=time.monotonic()+2.0
 while token is None:
  token=_claim_directory(guard,cfg['scope'])
  if token is None:
   if time.monotonic()>=deadline:return {'state':'deferred','reason':'adaptive_guard_busy','limit_unchanged':cfg['limit']}
   time.sleep(.05)
 try:
  cfg=validated_config(config);statepath=Path(config).with_name('adaptive-state.json')
  state=json.loads(statepath.read_text()) if statepath.exists() else {'consecutive_successes':0,'last_change':now,'last_concurrency_error':None}
  old=cfg['limit'];reason=None
  if account_concurrency_error(status,evidence):
   cfg['limit']=max(1,old//2);state['consecutive_successes']=0;state['last_concurrency_error']=now;reason='provider_account_concurrency_exceeded'
  elif completed and status==200:
   state['consecutive_successes']+=1
   if state['consecutive_successes']>=SUCCESS_THRESHOLD and now-state.get('last_change',now)>=INCREASE_INTERVAL and now-(state.get('last_concurrency_error') or 0)>=INCREASE_INTERVAL:
    cfg['limit']=min(50,old+1);state['consecutive_successes']=0;reason='sustained_success_probe_increase'
  else:state['consecutive_successes']=0
  if cfg['limit']!=old:
   state['last_change']=now;atomic(Path(config),cfg)
  atomic(statepath,state)
  if reason:
   with Path(config).with_name('adaptive-events.jsonl').open('a') as f:f.write(json.dumps({'time':now,'previous_limit':old,'next_limit':cfg['limit'],'reason':reason,'existing_requests_cancelled':False})+'\n')
  return {'state':'updated','previous_limit':old,'next_limit':cfg['limit'],'reason':reason}
 finally:_release_directory(guard,token,cfg['scope'])
