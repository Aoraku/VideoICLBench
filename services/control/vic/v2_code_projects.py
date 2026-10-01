"""Private rule checks for concrete course files, tests, versions and submissions."""
from copy import deepcopy
import io,tokenize
from vic_apps.code_execution import syntax_check,run_checks
from vic_apps.code_projects import zip_record,submission_files,delivery_artifacts
from vic_apps.communications import file_record


def target_files(initial,entry,variant):
    files=deepcopy(entry['files']);task=initial['task_id']
    if task==58:
        unit={'A':'  ','B':'    ','C':'\t'}[variant]
        return {name:'\n'.join(unit*((len(line)-len(line.lstrip(' ')))//3)+line.lstrip(' ') for line in code.split('\n')) for name,code in files.items()}
    if task==60:
        names={n:{'A':'x_'+n,'B':n+'_v','C':n.upper()}[variant] for n in initial['world']['rename_targets']}
        for name,code in files.items():
            tokens=list(tokenize.generate_tokens(io.StringIO(code).readline))
            files[name]=tokenize.untokenize([t._replace(string=names.get(t.string,t.string)) if t.type==tokenize.NAME else t for t in tokens])
        return files
    if task==64:return chosen_version(initial,entry,variant)['files']
    return files


def chosen_version(initial,entry,variant):
    candidates=[h for h in initial['world']['history'] if h['entry']==entry['id']]
    key=(lambda h:sum(len(code.splitlines()) for code in h['files'].values())) if variant=='C' else (lambda h:h['created_at'])
    return sorted(candidates,key=key,reverse=variant!='B')[0]


def should_submit(initial,entry,variant):
    if initial['task_id']==64:return False
    if initial['task_id']!=65:return True
    code=entry['files']['solution.py']
    return {'A':syntax_check(entry['files'])['passed'],'B':initial['world']['function'] in code,'C':len(code)<initial['world']['threshold']}[variant]


def evaluate(initial,final,variant,events):
    checks=[]
    def check(id,value):checks.append(dict(id=id,passed=bool(value)))
    for k in initial.keys()-{'world','domain','next_check','next_submission'}:check('input:'+k,initial[k]==final.get(k))
    for k in initial['domain'].keys()-{'files'}:check('input:domain:'+k,initial['domain'][k]==final['domain'].get(k))
    start=initial['world'];w=final['world']
    for k in start.keys()-{'drafts','restored','checks','submissions','delivery'}:check('input:world:'+k,start[k]==w.get(k))
    reference=deepcopy(initial);rw=reference['world'];rw['checks']=deepcopy(w['checks']);rw['drafts']={};rows=[];files=deepcopy(initial['domain']['files'])
    expected_count=sum(should_submit(initial,e,variant) for e in start['entries']);check('submission_count',len(w['submissions'])==expected_count)
    for entry in start['entries']:
        id=entry['id'];source=target_files(initial,entry,variant);rw['drafts'][id]=deepcopy(source)
        check(id+':code',w['drafts'].get(id)==source)
        problem=next(p for p in start['problems'] if p['id']==entry['problem'])
        result=run_checks(source,problem['tests'],entry['entry_file']);syntax=syntax_check(source)
        history_id=chosen_version(initial,entry,variant)['id'] if initial['task_id']==64 else ''
        if history_id:rw['restored'][id]=history_id
        candidates=[c for c in w['checks'].values() if c['entry']==id and c['files']==source]
        checked=candidates[-1] if candidates else None;check(id+':checked',checked is not None)
        if checked:
            expected=dict(id=checked['id'],entry=id,files=source,syntax=syntax,tests=result)
            check(id+':actual_check',checked==expected);rw['checks'][checked['id']]=expected
        matches=[s for s in w['submissions'].values() if s['entry']==id]
        needed=should_submit(initial,entry,variant);check(id+':submission_presence',len(matches)==(1 if needed else 0))
        sub=matches[0] if len(matches)==1 and needed else None
        if sub:
            # A submitted snapshot can reference an earlier identical check.
            sub_check=w['checks'].get(sub['check'])
            check(id+':submission_check',bool(sub_check) and sub_check['entry']==id and sub_check['files']==source and sub_check['syntax']==syntax and sub_check['tests']==result)
            expected=dict(id=sub['id'],entry=id,problem=entry['problem'],files=source,check=sub['check'],tests=result)
            check(id+':actual_submission',sub==expected);rw['submissions'][sub['id']]=expected
            files['submission-'+sub['id']]=zip_record(sub['id']+'-代码提交.zip',submission_files(expected))
        if initial['task_id'] in (58,60):check(id+':tests_passed',result['passed'])
        rows.append(dict(entry=id,problem=entry['problem'],source=history_id,check=checked['id'] if checked else '',submission=sub['id'] if sub else '',reason=start['unsubmitted_reason'] if initial['task_id']==65 and not needed else ''))
    check('draft_entry_set',set(w['drafts'])==set(rw['drafts']))
    check('restored_versions',w['restored']==rw['restored'])
    body,bundle=delivery_artifacts(reference,rows)
    check('published_delivery',w['delivery']==dict(rows=rows,body=body,published=True))
    files['course-delivery']=bundle;files['course-manifest']=file_record('课程代码交付清单.md',body)
    check('real_files',final['domain']['files']==files);check('activity',bool(events))
    return dict(success=all(c['passed'] for c in checks),completion=sum(c['passed'] for c in checks)/len(checks),checks=checks,violations=[c['id'] for c in checks if not c['passed']])
