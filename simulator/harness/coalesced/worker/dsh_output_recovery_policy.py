"""Read-only delay selection; the SDK still owns every recovery/API/action guard."""
from pathlib import Path
import json
class UnsafeRecoveryHistory(ValueError):pass

def _pairs(values):
 result={}
 for key,value in values:
  if key in result:raise UnsafeRecoveryHistory('duplicate_JSON_key')
  result[key]=value
 return result

def _constant(value):raise UnsafeRecoveryHistory('nonfinite_JSON_number')
def _json(raw):return json.loads(raw,object_pairs_hook=_pairs,parse_constant=_constant)
def _need(value,reason):
 if not value:raise UnsafeRecoveryHistory(reason)

def consecutive_for_recovery(*,engine,failure,attempt,room,identity,barrier):
 """Only DS output limits use same-action consecutive history, never CLI ordinal.

 Authoritative checked_barrier is supplied by run immediately before this call.
 A later SDK guard rechecks state and drains original accepted transactions.
 """
 _need(type(attempt)is int and attempt>0,'invalid_attempt')
 if engine!='dsh'or failure!='native_output_limit':return attempt
 room=Path(room);_need(room.name=='agent'and room.resolve(strict=True)==room,'noncanonical_agent_room')
 conn=_json((room.parent/'connection.private.json').read_bytes())
 _need(isinstance(conn,dict)and conn.get('identity')==identity,'room_identity_changed')
 _need(isinstance(identity,dict)and identity.get('epoch')==room.parents[4].name+'-'+room.parents[2].name,'campaign_pool_identity_changed')
 _need(barrier.get('status')=='running'and not barrier.get('recovery_id'),'owner_not_at_idle_recovery_boundary')
 count=barrier.get('action_count');_need(type(count)is int and 0<=count<=500,'invalid_authoritative_action_count')
 path=room/'recovery.private.jsonl'
 try:before=path.stat()
 except FileNotFoundError:before=None
 if before is None:
  _need(attempt==1,'missing_prior_recovery_journal');raw=b''
  _need(not path.exists(),'new_recovery_journal_appeared')
 else:
  raw=path.read_bytes();after=path.stat()
  stamp=lambda value:(value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
  _need(stamp(before)==stamp(after)and len(raw)==after.st_size,'recovery_journal_changed_during_read')
 _need(not raw or raw.endswith(b'\n'),'partial_recovery_journal')
 active={};ended=set();seen_attempts=set();previous_count=-1;previous_attempt=0;streak=0
 for line in raw.splitlines():
  _need(bool(line),'empty_recovery_record');event=_json(line);_need(isinstance(event,dict),'nonobject_recovery_record')
  kind=event.get('event')
  if kind=='backoff_started':
   rid=event.get('recovery_id');old_attempt=event.get('attempt');old_count=event.get('action_count');old_failure=event.get('failure')
   _need(isinstance(rid,str)and bool(rid)and rid not in active and rid not in ended,'duplicate_recovery_ID')
   _need(type(old_attempt)is int and previous_attempt<old_attempt<attempt and old_attempt not in seen_attempts,'invalid_or_duplicate_prior_attempt')
   _need(type(old_count)is int and 0<=old_count and previous_count<=old_count<=count,'action_count_regression_or_future')
   _need(isinstance(old_failure,str)and len(old_failure)<=256,'invalid_prior_failure')
   _need(not active,'overlapping_recovery_locks')
   seen_attempts.add(old_attempt);previous_attempt=old_attempt;active[rid]=old_attempt;previous_count=old_count
   streak=streak+1 if old_failure=='native_output_limit'and old_count==count else 0
  elif kind in('backoff_ended','backoff_handed_off'):
   rid=event.get('recovery_id');_need(rid in active,'orphan_or_duplicate_recovery_end')
   if event.get('attempt')is not None:_need(event['attempt']==active[rid],'recovery_attempt_changed')
   active.pop(rid);ended.add(rid)
  elif kind not in('pending_reconciled','recovery_wait_stopped'):
   raise UnsafeRecoveryHistory('unknown_recovery_event')
 _need(not active,'prior_recovery_not_durably_ended')
 return streak+1
