"""Private same-host request timing. No request bodies, tokens, or API retries."""
from __future__ import annotations
import json
import hashlib
import math
import os
from pathlib import Path
import time

SCHEMA = 'videoicl-api-timing-v1'


def union_intervals(intervals, start=None, end=None):
    values=[]
    for left,right in intervals:
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in (left,right)) or right<left:
            raise ValueError('Invalid monotonic interval')
        if start is not None:left=max(left,start)
        if end is not None:right=min(right,end)
        if right>left:values.append((left,right))
    merged=[]
    for left,right in sorted(values):
        if merged and left<=merged[-1][1]:merged[-1][1]=max(right,merged[-1][1])
        else:merged.append([left,right])
    return merged


def interval_seconds(intervals, start=None, end=None):
    return sum(right-left for left,right in union_intervals(intervals,start,end))


def subtract_intervals(intervals, removed):
    result=[]
    for left,right in union_intervals(intervals):
        cursor=left
        for a,b in union_intervals(removed):
            if b<=cursor:continue
            if a>=right:break
            if a>cursor:result.append([cursor,min(a,right)])
            cursor=max(cursor,b)
            if cursor>=right:break
        if cursor<right:result.append([cursor,right])
    return result


def append_timing_event(path,event,*,monotonic=None,**fields):
    value=time.monotonic() if monotonic is None else monotonic
    if type(value) not in (int,float) or not math.isfinite(value) or value<0:
        raise ValueError('Invalid monotonic event time')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    data=(json.dumps(dict(schema=SCHEMA,event=event,monotonic=value,**fields),separators=(',',':'),allow_nan=False)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    try:
        # One append preserves event boundaries across relay/owner processes.
        if os.write(fd,data)!=len(data):raise OSError('Incomplete private timing append')
    finally:os.close(fd)


class ApiTimingLedger:
    def __init__(self,path,*,clock=time.monotonic):
        self.path=Path(path);self.clock=clock
        self._inode=None;self._observed_size=0;self._prefix_digest=None;self._integrity_failed=False

    def actor_activity(self,now=None):
        append_timing_event(self.path,'actor_activity',monotonic=self.clock() if now is None else now)

    activity=actor_activity

    def snapshot(self,now=None):
        now=self.clock() if now is None else now
        if type(now) not in (int,float) or not math.isfinite(now) or now<0:raise ValueError('Invalid monotonic clock')
        try:
            with self.path.open('rb') as stream:
                stat=os.fstat(stream.fileno());raw=stream.read()
            inode=(stat.st_dev,stat.st_ino)
            if self._inode is not None and (inode!=self._inode or len(raw)<self._observed_size
                    or hashlib.sha256(raw[:self._observed_size]).hexdigest()!=self._prefix_digest):
                self._integrity_failed=True
            self._inode=inode;self._observed_size=len(raw);self._prefix_digest=hashlib.sha256(raw).hexdigest()
        except FileNotFoundError:
            if self._inode is not None:self._integrity_failed=True
            raw=b''
        pending_log_write=bool(raw and not raw.endswith(b'\n'))
        uncertain=pending_log_write or self._integrity_failed;requests={};activities=[]
        complete_lines=raw.splitlines()[:-1] if pending_log_write else raw.splitlines()
        for line in complete_lines:
            try:
                event=json.loads(line);stamp=event['monotonic'];kind=event['event']
                if event.get('schema')!=SCHEMA or type(stamp) not in (int,float) or not math.isfinite(stamp) or stamp<0:
                    raise ValueError('Invalid event')
                # A concurrent append may be newer than the owner's captured
                # now. Leave it for the next snapshot; it is not corrupt data.
                if stamp>now:continue
                if kind=='actor_activity':activities.append(stamp);continue
                request_id=event['request_id']
                if not isinstance(request_id,str) or not request_id:raise ValueError('Missing request identity')
                request=requests.setdefault(request_id,{})
                if kind=='request_start':
                    if 'start' in request and request['start']!=stamp:raise ValueError('Conflicting start')
                    request['start']=stamp
                elif kind=='request_end':
                    if 'end' in request and (request['end'],request['outcome'])!=(stamp,event.get('outcome')):
                        raise ValueError('Conflicting end')
                    if event.get('outcome') not in ('success','failure','unknown'):raise ValueError('Invalid outcome')
                    if 'failure_kind' in request and request['failure_kind'] != event.get('failure_kind'):
                        raise ValueError('Conflicting failure kind')
                    request.update(end=stamp,outcome=event['outcome'],failure_kind=event.get('failure_kind'))
                elif kind in ('queue_start','queue_end'):
                    if kind in request and request[kind]!=stamp:raise ValueError('Conflicting queue event')
                    request[kind]=stamp
                else:raise ValueError('Unknown timing event')
            except (ValueError,KeyError,TypeError):uncertain=True
        structural_error=uncertain
        failed=[];active=[];queued=[];all_requests=[];fail_ends=[];starts=[];unknown_count=0
        for request in requests.values():
            if 'start' not in request:uncertain=True;structural_error=True;continue
            begin=request['start'];end=request.get('end',now);starts.append(begin)
            if end<begin:uncertain=True;structural_error=True;continue
            if 'queue_start' in request:
                queue_begin=request['queue_start'];queue_end=request.get('queue_end',now)
                if (queue_begin<begin or queue_end<queue_begin or queue_end>end
                        or ('end' in request and 'queue_end' not in request)):
                    uncertain=True;structural_error=True
                else:queued.append([queue_begin,queue_end])
            elif 'queue_end' in request:
                uncertain=True;structural_error=True
            all_requests.append([begin,end])
            if 'end' not in request:active.append([begin,now])
            elif request['outcome']=='failure':failed.append([begin,end]);fail_ends.append(end)
            elif request['outcome']=='unknown':uncertain=True;unknown_count+=1
        unknown_requests={k:r for k,r in requests.items() if r.get('outcome')=='unknown'}
        last_unknown_end=max((r['end'] for r in unknown_requests.values()),default=None)
        subsequent_success_ends=[r['end'] for r in requests.values()
            if last_unknown_end is not None and r.get('outcome')=='success'
            and r.get('start',-1)>=last_unknown_end]
        closed_unknown_recoverable=bool(unknown_requests) and not (structural_error or active) and all(
            r.get('failure_kind')=='unverified_response_completion' for r in unknown_requests.values())
        gaps=[];open_gap=False
        for end in fail_ends:
            candidates=[stamp for stamp in starts+activities if stamp>=end]
            finish=min(candidates) if candidates else now
            if not candidates:open_gap=True
            gaps.append([end,finish])
        # Failed request latency is excluded. Successful and still-pending API
        # intervals must never become retry-backoff credit due to concurrency.
        gaps=subtract_intervals(gaps,all_requests)
        return dict(active=bool(active),active_request_count=len(active),uncertain=uncertain,
            closed_unknown_recoverable=closed_unknown_recoverable,
            unknown_request_ids=sorted(unknown_requests),last_unknown_end=last_unknown_end,
            subsequent_success_end=min(subsequent_success_ends) if subsequent_success_ends else None,
            pending_log_write=pending_log_write,ledger_integrity_failed=self._integrity_failed,
            ledger_integrity_valid=not structural_error,unknown_outcome_count=unknown_count,
            transport_quiescent_confirmed=not (structural_error or active),
            failed_intervals=union_intervals(failed),active_intervals=union_intervals(active),
            retry_wait_intervals=gaps,queue_wait_intervals=union_intervals(queued),
            excluded_intervals=union_intervals(failed+gaps+queued),
            retry_gap_open=open_gap,request_count=len(requests),timebase='same_host_monotonic')
