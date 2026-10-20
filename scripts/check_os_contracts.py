"""Exercise all OS local demos and two held-out query seeds, without recording."""
import argparse,copy,json,sys
from pathlib import Path


def check_teaching_evidence(ep):
    """Check competing explanations from inputs, independently of the oracle actions."""
    cid=ep['case']['id'];files=[f for f in ep['initial']['files'] if f['kind']!='folder']
    if cid=='OS-E-02':
        assets=[f for f in files if f['name'].startswith('asset-')]
        assert len(assets)==6
        parents={f['parent'] for f in assets}
        assert len(parents)==2
        assert all({f['resource_key'] for f in assets if f['parent']==p}=={'resource-0','resource-1'} for p in parents)
        # Same project, different keys AND same key, different projects.
        assert any(a['parent']==b['parent'] and a['resource_key']!=b['resource_key'] for a in assets for b in assets)
        assert any(a['parent']!=b['parent'] and a['resource_key']==b['resource_key'] for a in assets for b in assets)
    elif cid=='OS-E-03':
        candidates=[f for f in files if f['name'].startswith('edition-')]
        for parent in {f['parent'] for f in candidates}:
            group=[f for f in candidates if f['parent']==parent]
            approved=[f for f in group if f['approved']]
            assert len(approved)==3 and len(group)==4
            assert all(f['name']==f"edition-r{f['revision']}.txt" for f in group)
            assert not max(group,key=lambda f:f['revision'])['approved']
            winners=[max(approved,key=lambda f:f['revision']),min(approved,key=lambda f:len(f['content'].encode())),max(approved,key=lambda f:len(f['content'].encode()))]
            assert len({f['id'] for f in winners})==3
            assert any(a['op']=='copy' and a['target']==winners[ep['convention']]['id'] for a in ep['reference'])
    elif cid=='OS-E-06':
        records=[json.loads(line) for f in files if f['name'].startswith('copy-') for line in f['content'].splitlines()]
        assert all(r['operator_id'].isdigit() for r in records)
        assert len({r['operator_id'] for r in records})==len(records)
    elif cid=='OS-E-08':
        logs=[f for f in files if f.get('log_channel')]
        for f in logs:
            records=[json.loads(line) for line in f['content'].splitlines()]
            anchors=[r for r in records if r['message']=='Incident anchor']
            assert len(anchors)==1
            a=next(a for a in ep['reference'] if a['target']==f['id'])
            inside=[r for r in records if a['start']<=r['time']<=a['end']]
            assert any(r['time']==a['start'] for r in inside)
            assert any(r['time']==a['end'] for r in inside)
            assert len(inside)<len(records)


def main(source):
    sys.path.insert(0,str(source.resolve()))
    import tasks36,workflows
    release=json.loads((source/'videoicl-catalog.json').read_text());count=0;counterfactuals=0
    for case in release['cases']:
        for scope,seeds in [('module-demo',case['demo_seeds']),('standard',[4201,5317])]:
            for seed in seeds:
                initial=[];completed=[]
                for c in range(3):
                    ep=tasks36.generate(case['id'],c,seed,scope);check_teaching_evidence(ep);initial.append(ep['initial'])
                    for action in ep['reference']:workflows.transition(ep,copy.deepcopy(action))
                    result=workflows.evaluate(ep)
                    assert result['success'],(case['id'],scope,seed,c,result.get('failed_checks'))
                    if case['id']=='OS-E-03':
                        copies=[f for f in ep['state']['files'] if f.get('source')]
                        for f in copies:
                            original=workflows.get_file(ep['initial'],f['source'])
                            assert all(f[k]==original[k] for k in ('revision','approved','resource_key'))
                    completed.append(ep);count+=1
                assert initial[0]==initial[1]==initial[2],(case['id'],scope,'ABC initial state differs')
                if scope=='standard':
                    for expected in range(3):
                        for actual in range(3):
                            if expected==actual:continue
                            mismatched=copy.deepcopy(completed[expected]);mismatched['state']=copy.deepcopy(completed[actual]['state']);mismatched['events']=copy.deepcopy(completed[actual]['events'])
                            assert not workflows.evaluate(mismatched)['success'],(case['id'],seed,expected,actual,'wrong condition accepted')
                            counterfactuals+=1
        print(case['id'],'OK',flush=True)
    print(json.dumps({'successful_reference_episodes':count,'rejected_wrong_conditions':counterfactuals,'video_recorded':False}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);main(p.parse_args().source)
