#!/usr/bin/env python3
"""Independent evaluator only. Never imported by the model/MCP, never writes native scores."""
from pathlib import Path
import argparse,json,os


def grade_one(agent_dir,bindings):
    root=Path(agent_dir);manifest=json.loads((root/'manifest.json').read_text())
    field=lambda x:(x['task_id'],x['variant'],x['seed'],x.get('input_condition',x.get('source')))
    matches=[x for x in bindings['records'] if field(x)==field(manifest)]
    if len(matches)!=1:raise ValueError('QA evaluator identity is missing or ambiguous')
    record=matches[0];qa=manifest['rule_qa']
    if (qa['source_sha256']!=record['source_sha256'] or qa['question_id']!=record['question_id'] or
        qa['assignment_identity_sha256']!=record['assignment_identity_sha256']):raise ValueError('QA source/assignment identity changed')
    answer=root/'rule-qa/first-valid-answer.private.json';invalid=list((root/'rule-qa').glob('invalid-*.private.json'))
    result=dict(run_id=manifest['run_id'],task_id=manifest['task_id'],variant=manifest['variant'],
        seed=manifest['seed'],source=record['source'],inference_group=record['inference_group'],protocol='qa_then_act',
        source_sha256=record['source_sha256'],answered=answer.exists(),invalid_format_attempts=len(invalid),
        selected_option=None,qa_correct=None,native_score_modified=False,
        independent_video_semantic_review_pending=record['source']=='sim',provenance=record['provenance'])
    if answer.exists():
        saved=json.loads(answer.read_text())
        if saved['identity']!={'run_id':manifest['run_id'],'assignment_sha256':record['assignment_identity_sha256']}:
            raise ValueError('first answer belongs to another episode/assignment')
        if saved['source_sha256']!=record['source_sha256'] or saved['source']!=record['source'] or saved['question_id']!=record['question_id']:
            raise ValueError('answer source/question mismatch')
        if saved.get('format_valid') is not True or saved['selected_option'] not in 'ABCD' or len(saved['selected_option'])!=1:
            raise ValueError('invalid first-valid-answer record')
        result.update(selected_option=saved['selected_option'],qa_correct=saved['selected_option']==record['correct_option'])
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--agent-dir',type=Path,required=True);p.add_argument('--bindings',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=grade_one(a.agent_dir,json.loads(a.bindings.read_text()))
    fd=os.open(a.out,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
