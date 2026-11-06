"""First-valid-answer QA gate; contains no evaluator answer key or correctness feedback."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

INSTRUCTIONS = '''
This episode uses qa_then_act. Before acting or ending the episode, read the supplied
text rule (text condition) or inspect the assigned demonstration with demo tools
(video condition), then call qa_question() and submit one option with qa_answer(answer).
Select exactly one uppercase letter A, B, C or D. The first valid answer is final;
correctness is not returned and does not affect permission to continue. Once the
answer is recorded, continue the original physical task. After reconnect, the saved
answer is reused; do not change it. This rule-comprehension answer and the final
physical task score are separate measurements.
'''


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def publish(path, value):
    fd,tmp=tempfile.mkstemp(prefix='.qa-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(value,f,ensure_ascii=False,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
        os.link(tmp,path)
        dfd=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(dfd)
        finally:os.close(dfd)
    finally:os.unlink(tmp)


EXECUTION_REVISION='embodied50-execution-v2-20261102'


def load_execution_assignment(value,spec,condition,material):
    fields={'schema','protocol','task_id','variant','source','source_sha256','packet','provenance',
            'revision','generalization_condition','assignment_identity_sha256','seed'}
    if set(value)!=fields or value.get('schema')!='rule-qa-execution-assignment-v2' or value.get('protocol')!='qa_then_act':
        raise ValueError('Invalid execution QA assignment fields')
    if value['revision']!=EXECUTION_REVISION or spec.get('task_revision')!=EXECUTION_REVISION:
        raise ValueError('Explicit execution revision required')
    identities=spec.get('qa_assignment_identities',{})
    if not isinstance(identities,dict):raise ValueError('Invalid per-input QA identities')
    expected_identity=identities.get(condition,spec.get('assignment_identity_sha256'))
    expected=(spec['task_id'],spec['variant'],spec['seed'],spec.get('generalization_condition'),expected_identity)
    actual=(value['task_id'],value['variant'],value['seed'],value['generalization_condition'],value['assignment_identity_sha256'])
    if actual!=expected or value['generalization_condition'] not in ('I','E') or type(value['seed']) is not int:
        raise ValueError('Execution QA assignment identity mismatch')
    if not re.fullmatch('[0-9a-f]{64}',value['assignment_identity_sha256']):raise ValueError('Execution assignment digest required')
    # Reuse the unchanged public four-option/material checks below through an
    # exact v1-shaped view. No G0/G1/G2 alias or rule-answer field is introduced.
    return {k:value[k] for k in fields-{'revision','generalization_condition','assignment_identity_sha256','seed'}}


def load_assignment(task_dir, spec, condition, material):
    path=Path(task_dir)/'environment'/'rule-qa'/f'{condition}.json'
    value=json.loads(path.read_text())
    original=value
    execution=value.get('schema')=='rule-qa-execution-assignment-v2'
    if execution:
        value=load_execution_assignment(value,spec,condition,material)
        value=dict(value,schema='rule-qa-assignment-v1')
    elif spec.get('task_revision')==EXECUTION_REVISION:
        raise ValueError('New execution revision cannot reuse a legacy QA assignment')
    allowed={'schema','protocol','task_id','variant','source','source_sha256','packet','provenance'}
    if set(value)!=allowed or value['schema']!='rule-qa-assignment-v1' or value['protocol']!='qa_then_act':
        raise ValueError('Missing or invalid required QA assignment')
    if value['task_id']!=spec['task_id'] or value['variant']!=spec['variant'] or value['source']!=condition:
        raise ValueError('QA assignment/task/source mismatch')
    packet=value['packet']
    if (set(packet)!={'question_id','prompt','options','response_instruction'} or
        not isinstance(packet['question_id'],str) or not isinstance(packet['prompt'],str) or
        not isinstance(packet['options'],dict) or set(packet['options'])!=set('ABCD') or
        any(not isinstance(x,str) or not x.strip() for x in packet['options'].values())):
        raise ValueError('QA must contain only one public four-option question')
    if not re.fullmatch('[0-9a-f]{64}',value['source_sha256']):
        raise ValueError('QA source SHA256 missing')
    if material and value['source_sha256']!=material['sha256']:
        raise ValueError('QA video differs from assigned material')
    return original if execution else value


class RuleQAGate:
    def __init__(self, config):
        self.assignment=config['rule_qa']
        self.identity={'run_id':config['run_id'],'assignment_sha256':digest(self.assignment)}
        self.directory=Path(config['output_dir'])/'rule-qa'
        self.directory.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.answer=self.directory/'first-valid-answer.private.json'
        self.delivery=self.directory/'material-delivered.private.json'
        self.question_receipt=self.directory/'question-issued.private.json'
        for p in (self.answer,self.delivery,self.question_receipt):
            if p.exists():self._read(p)

    def _read(self,path):
        obj=json.loads(path.read_text())
        if obj.get('identity')!=self.identity:raise ValueError('QA state identity mismatch')
        return obj

    def _once(self,path,record):
        try:publish(path,dict(identity=self.identity,**record))
        except FileExistsError:self._read(path)

    def delivered(self, *, source_sha256, seconds=None):
        if source_sha256!=self.assignment['source_sha256']:raise ValueError('QA material hash mismatch')
        source=self.assignment['source']
        if source!='text_rule' and (not isinstance(seconds,(int,float)) or seconds<0):
            raise ValueError('Video frame delivery required')
        self._once(self.delivery,{'source':source,'source_sha256':source_sha256,
                                  'first_delivered_frame_seconds':seconds,
                                  'evidence':'prompt_text_rule' if source=='text_rule' else 'successful_demo_frame_decode',
                                  'complete_video_viewing_proven':False})

    def question(self):
        if self.answer.exists():
            self._read(self.answer)
            return {'status':'submitted','action_allowed':True}
        if not self.delivery.exists():raise ValueError('Inspect the assigned demo before requesting the question')
        self._read(self.delivery)
        self._once(self.question_receipt,{'question_id':self.assignment['packet']['question_id']})
        return {'status':'awaiting_answer','action_allowed':False,'question':self.assignment['packet']}

    def submit(self, answer):
        if self.answer.exists():
            self._read(self.answer)
            return {'status':'submitted','action_allowed':True,'reused_first_answer':True}
        if not self.question_receipt.exists():raise ValueError('Call qa_question after inspecting assigned material')
        self._read(self.question_receipt);self._read(self.delivery)
        if not isinstance(answer,str) or not re.fullmatch('[ABCD]',answer.strip()):
            # Persist malformed attempts without ever returning correctness.
            raw={'identity':self.identity,'raw_answer':answer,'format_valid':False}
            p=self.directory/('invalid-'+digest(raw)+'.private.json')
            self._once(p,{'raw_answer':answer,'format_valid':False})
            return {'status':'invalid_format','action_allowed':False,'instruction':'Submit one uppercase letter A, B, C or D.'}
        self._once(self.answer,{'raw_answer':answer,'selected_option':answer.strip(),
                               'format_valid':True,'question_id':self.assignment['packet']['question_id'],
                               'source':self.assignment['source'],'source_sha256':self.assignment['source_sha256']})
        return {'status':'submitted','action_allowed':True}

    def require_answer(self):
        if not self.answer.exists():raise ValueError('Answer the assigned question with qa_question and qa_answer before acting or ending')
        self._read(self.answer)


def needs_qa_continuation(config, *, completed, returncode, environment_error):
    """A normal CLI turn without the required answer is not episode completion."""
    if not completed or returncode != 0 or environment_error is not None:
        return False
    gate = RuleQAGate(config)
    if gate.answer.exists():
        gate._read(gate.answer)
        return False
    return True
