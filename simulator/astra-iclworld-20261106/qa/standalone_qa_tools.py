"""Video-only native MCP candidate: no simulator/controller/action or answer key."""
from copy import deepcopy
import argparse
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def public_question(packet):
    allowed={'question_id','prompt','options','response_instruction'}
    if not isinstance(packet,dict)or set(packet)!=allowed:raise ValueError('Only the public question packet is accepted')
    if any(not isinstance(packet[k],str)or not packet[k].strip()for k in ('question_id','prompt','response_instruction')):raise ValueError('Missing question text')
    if not isinstance(packet['options'],dict)or set(packet['options'])!=set('ABCD')or any(not isinstance(x,str)or not x.strip()for x in packet['options'].values()):raise ValueError('Exactly four public options are required')
    return deepcopy(packet)


def write_once(path,value):
    # O_EXCL makes the first valid answer immutable even across process exits.
    raw=(json.dumps(value,ensure_ascii=False,sort_keys=True)+'\n').encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb')as f:f.write(raw);f.flush();os.fsync(f.fileno())


class VideoReader:
    """Reuse the source harness' ffmpeg decoder without constructing Computer/HTTP."""
    def __init__(self,path):self.config={'demo_video':str(path)}
    def log(self,_):pass
    def info(self):
        from vic_sdk.computer_mcp import Computer
        return Computer.demo_info(self)
    def frame(self,seconds):
        from vic_sdk.computer_mcp import Computer
        return Computer.demo_frame(self,seconds)


class StandaloneQA:
    def __init__(self,config,*,reader=None):
        allowed={'schema','identity','video_path','video_sha256','question','output_dir','api_timing_log'}
        if set(config)!=allowed or config['schema']!='standalone-video-qa-v1':raise ValueError('Strict public-only QA config required')
        ident=config['identity']
        if not isinstance(ident,dict)or set(ident)!={'qa_id','task','variant','seed'}or ident['variant']not in ('A','B','C')or type(ident['seed'])is not int:raise ValueError('Fixed QA identity required')
        self.identity=deepcopy(ident);self.question=public_question(config['question'])
        self.video=Path(config['video_path']).resolve(strict=True);self.sha=config['video_sha256']
        if digest(self.video)!=self.sha:raise ValueError('QA video SHA mismatch')
        self.directory=Path(config['output_dir']).resolve();self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.timing=Path(config['api_timing_log']).resolve()
        if self.timing!=self.directory/'api-timing.private.jsonl':raise ValueError('QA requires its own fixed API ledger')
        self.state_path=self.directory/'qa-state.private.json';self.lock=threading.RLock()
        self.state=json.loads(self.state_path.read_text())if self.state_path.exists()else dict(schema='standalone-video-qa-state-v1',identity=self.identity,video_sha256=self.sha,delivered=[],question_issued=False)
        if self.state.get('identity')!=self.identity or self.state.get('video_sha256')!=self.sha:raise ValueError('QA checkpoint identity mismatch')
        self.reader=reader or VideoReader(self.video)
        self.answer_path=self.directory/'first-valid-answer.private.json'
        if self.answer_path.exists():self._answer()

    def _save(self):
        p=self.state_path.with_suffix('.tmp');p.write_text(json.dumps(self.state,ensure_ascii=False)+'\n');p.chmod(0o600);p.replace(self.state_path)
    def _answer(self):
        v=json.loads(self.answer_path.read_text())
        if v.get('identity')!=self.identity or v.get('source_sha256')!=self.sha or v.get('question_id')!=self.question['question_id']:raise ValueError('First-answer identity mismatch')
        return v
    def _active(self):
        if self.answer_path.exists():raise ValueError('QA already answered; do not request more material')
        if digest(self.video)!=self.sha:raise ValueError('Assigned QA video changed')
    def info(self):
        with self.lock:
            self._active();v=self.reader.info()
            duration=v.get('duration_seconds')
            if not v.get('available')or type(duration)not in (int,float)or not math.isfinite(duration)or duration<=0:raise ValueError('Assigned QA video metadata unavailable')
            self.state['duration_seconds']=duration;self._save()
            return {**v,'source_sha256':self.sha,'simulation_started':False}
    def frames(self,seconds):
        with self.lock:
            self._active();info=self.info();duration=info['duration_seconds']
            if not isinstance(seconds,list)or not 1<=len(seconds)<=12 or any(type(x)not in(int,float)or not math.isfinite(x)or not 0<=x<duration for x in seconds):raise ValueError('Choose 1..12 timestamps inside assigned QA video')
            content=[]
            for t in sorted(seconds):
                r=self.reader.frame(t)
                if r.isError or not any(b.type=='image'for b in r.content):raise ValueError('QA frame decode did not return an image')
                content.extend(r.content);self.state['delivered'].append(t)
            self._active();self._save()
            return CallToolResult(content=content)
    def issue(self):
        with self.lock:
            if self.answer_path.exists():self._answer();return {'status':'submitted','correctness_returned':False}
            self._active()
            if not self.state['delivered']:raise ValueError('Inspect at least one assigned video frame before requesting QA')
            self.state['question_issued']=True;self._save()
            return {'status':'awaiting_answer','question':deepcopy(self.question),'complete_video_viewing_proven':False}
    def submit(self,answer):
        with self.lock:
            if self.answer_path.exists():self._answer();return {'status':'submitted','reused_first_answer':True,'correctness_returned':False}
            self._active()
            if not self.state['question_issued']or not self.state['delivered']:raise ValueError('Inspect assigned frames and call qa_question first')
            if not isinstance(answer,str)or answer.strip()not in 'ABCD'or len(answer.strip())!=1:
                return {'status':'invalid_format','instruction':'Submit exactly one uppercase letter A, B, C or D.'}
            result=dict(identity=self.identity,question_id=self.question['question_id'],source_sha256=self.sha,
                selected_option=answer.strip(),raw_answer=answer,first_valid=True,delivered_seconds=list(self.state['delivered']),
                complete_video_viewing_proven=False,simulation_started=False)
            from vic_sdk.api_timing import ApiTimingLedger
            from vic_sdk.episode_api_admission import EpisodeApiAdmission
            ledger=ApiTimingLedger(self.timing)
            admission=EpisodeApiAdmission(self.timing)
            # Hold admission while the already-accepted generating request
            # finishes its relay log. No in-flight API is cancelled. A request
            # arriving after the first valid answer will receive local410.
            with admission.guard():
                while True:
                    proof=ledger.snapshot()
                    if proof['active'] or proof['pending_log_write']:
                        time.sleep(.02);continue
                    if proof['uncertain'] or proof['ledger_integrity_valid']is not True or proof['transport_quiescent_confirmed']is not True:
                        raise ValueError('QA API ledger is not reconciled; answer admission remains held for review')
                    break
                write_once(self.answer_path,result)
                admission.close_locked(reason='standalone_qa_first_valid_answer')
            return {'status':'submitted','correctness_returned':False}


def make_server(backend):
    server=FastMCP('vic-standalone-video-qa')
    @server.tool()
    async def demo_info()->dict:
        """Read only assigned video metadata; no physical environment exists."""
        return await asyncio.to_thread(backend.info)
    @server.tool()
    async def demo_frames(seconds:list[float])->CallToolResult:
        """Inspect 1..12 timestamps from the original assigned video."""
        return await asyncio.to_thread(backend.frames,seconds)
    @server.tool()
    async def qa_question()->dict:
        """Request the public four-option rule question after inspecting the video."""
        return await asyncio.to_thread(backend.issue)
    @server.tool()
    async def qa_answer(answer:str)->dict:
        """Record one uppercase A/B/C/D answer. First valid answer is immutable; no correctness feedback."""
        return await asyncio.to_thread(backend.submit,answer)
    return server


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--sdk-root',type=Path,required=True);args=p.parse_args()
    # Absolute source binding also works when an ambient older SDK was preloaded.
    import sys
    for name in list(sys.modules):
        if name=='vic_sdk'or name.startswith('vic_sdk.'):del sys.modules[name]
    sys.path.insert(0,str(args.sdk_root.resolve()))
    backend=StandaloneQA(json.loads(args.config.read_text()))
    make_server(backend).run(transport='stdio')


if __name__=='__main__':main()
