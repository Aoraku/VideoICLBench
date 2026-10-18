"""Exercise all OS local demos and two held-out query seeds, without recording."""
import argparse,copy,json,sys
from pathlib import Path


def main(source):
    sys.path.insert(0,str(source.resolve()))
    import tasks36,workflows
    release=json.loads((source/'videoicl-catalog.json').read_text());count=0;counterfactuals=0
    for case in release['cases']:
        for scope,seeds in [('module-demo',case['demo_seeds']),('standard',[4201,5317])]:
            for seed in seeds:
                initial=[];completed=[]
                for c in range(3):
                    ep=tasks36.generate(case['id'],c,seed,scope);initial.append(ep['initial'])
                    for action in ep['reference']:workflows.transition(ep,copy.deepcopy(action))
                    result=workflows.evaluate(ep)
                    assert result['success'],(case['id'],scope,seed,c,result.get('failed_checks'))
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
