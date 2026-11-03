"""Offline route/guard contracts; no test fixture counts as native acceptance."""
import ast,copy,json,math
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3,REVISION_V2
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.realworld_semantic_checks import check_task
from videoicl_isaaclab.execution_design_pose_negative import (CAPABILITIES,PoseNegativeAuthor,negative_plan,intervention_observations,allow_original_terminal_failure,_side)

BOUNDS=(np.array([-.5,-.7,.75]),np.array([.6,.7,.8]))

def rotation(yaw):return np.array([[math.cos(yaw),-math.sin(yaw),0],[math.sin(yaw),math.cos(yaw),0],[0,0,1.]])


def spec(task,variant='A',seed=4201,condition='I'):
    s=load(task,variant,0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False)
    return apply_execution_inputs(s,condition=condition,seed=seed,revision=REVISION_V3)


def initial(s):return {o['id']:dict(pos=np.array([*o['xy'],o['bottom']+o['size'][2]]),mat=rotation(o.get('yaw',0)),grasp=[False,False])for o in s['objects']}


def planned_state(s,p,i):
    state=copy.deepcopy(i);zones={z['id']:z for z in p['zones']}
    for g in p['goals']:
        state[g['object']]['pos'][:2]=zones[g['target']]['xy']
        if 'yaw'in g:state[g['object']]['mat']=rotation(g['yaw'])
    return state


def semantic_result(s,i,state,released=True):
    names=s['semantic']['groups']['active'];obs=dict(released=released,stable=True)
    if s['id']=='E15':
        def poses(rows):return {n:dict(xy=rows[n]['pos'][:2].tolist(),yaw_deg=math.degrees(math.atan2(rows[n]['mat'][1,0],rows[n]['mat'][0,0])))for n in names}
        obs.update(initial=poses(i),final=poses(state),supported=names)
    else:
        car=state[s['semantic']['car']];frame=car['mat']@np.asarray(s['semantic']['car_frame']);mapping={}
        for n in names:mapping[_side(frame.T@(state[n]['pos']-car['pos']))]=n.removesuffix('_block')
        obs.update(car_sides=mapping,reference_frame='car',supported=['red','green','blue'])
    return check_task(s['id'],s['variant'],obs)


@pytest.mark.parametrize('task',['E15','E22'])
@pytest.mark.parametrize('variant','ABC')
@pytest.mark.parametrize('seed',[4201,4202,4203])
@pytest.mark.parametrize('condition','RIE')
def test_all_legal_cells_have_distinct_physical_negative_plans(task,variant,seed,condition):
    s=spec(task,variant,seed,condition);before=copy.deepcopy(s);i=initial(s)
    for control in CAPABILITIES[task]:
        p,d=negative_plan(s,control,i,BOUNDS);assert s==before and p['objects']==s['objects'] and p['semantic']==s['semantic']
        assert set(g['object']for g in p['goals'])==set(g['object']for g in s['goals'])
        assert d['negative_condition_observed']is None
        if control!='not_released':assert not semantic_result(s,i,planned_state(s,p,i))['success']
        else:assert p['goals']==s['goals']
    with pytest.raises(NotImplementedError,match='omission/duplication'):negative_plan(s,'wrong_members',i,BOUNDS)


def test_e15_wrong_rule_changes_only_the_intended_transform_component():
    for variant in 'ABC':
        s=spec('E15',variant);i=initial(s);p,_=negative_plan(s,'wrong_rule',i,BOUNDS);r=semantic_result(s,i,planned_state(s,p,i))
        checks=r['checks']
        assert checks['two_original_objects']and checks['physical_support']
        assert checks['position_swap_or_preservation']==(variant!='B')
        assert checks['orientation_swap_or_preservation']==(variant=='B')


def test_car_world_frame_equivalence_never_makes_false_negative():
    s=spec('E22',condition='R');i=initial(s);p,d=negative_plan(s,'wrong_destination',i,BOUNDS)
    assert d['destination_strategy']=='actual_car_rear_outside_all_three_destinations'
    assert not semantic_result(s,i,planned_state(s,p,i))['success']


class FakeAuthor:
    def __init__(self,s,fail=False):
        self.smooth=False;self.control_report={'engineering_reference_only':True};self.fail=fail;self.original=copy.deepcopy(s)
        self.scene=SimpleNamespace(spec=s,origin=np.zeros(3),world_to_task=lambda p:p,layout=SimpleNamespace(config={'table':{'position':[.05,0,.775],'size':[1.1,1.4,.05]}}),embodiment=SimpleNamespace(config={}))
        self.state=initial(s);self.contacts={frozenset((n,'table'))for n in self.state};self.actions=[]
        self.score={'success':False,'progress_evidence':{'object_status':{n:{'stable':True,'supported':True}for n in self.state}}}
        self.c=SimpleNamespace(scene=self.scene,steps=0,evaluator=SimpleNamespace(initial=copy.deepcopy(self.state),result=lambda:self.score),snapshot=lambda:(self.state,self.contacts))
    def act(self,*args,**kwargs):self.c.steps+=1;self.actions.append(args)
    def release_generated(self,side):
        self.act('RELEASE','STILL')
        for n in self.state:
            self.state[n]['grasp']=[False,False]
            self.contacts.discard(frozenset((n,'left_finger1')));self.contacts.discard(frozenset((n,'left_finger2')))
    def solve_generated(self):
        assert self.c.scene.spec==self.original and self.scene is not self.c.scene
        assert allow_original_terminal_failure(self)
        if self.fail:raise RuntimeError('actual transfer obstruction')
        zones={z['id']:z for z in self.scene.spec['zones']}
        for g in self.scene.spec['goals']:
            self.act('GRASP','STILL');n=g['object'];body=self.state[n];body['pos'][:2]=zones[g['target']]['xy']
            if 'yaw'in g:body['mat']=rotation(g['yaw'])
            body['grasp']=[True,False];self.contacts.update({frozenset((n,'left_finger1')),frozenset((n,'left_finger2'))})
            self.release_generated('left')
        return self.c.evaluator.result()


@pytest.mark.parametrize('task',['E15','E22'])
@pytest.mark.parametrize('control',['wrong_rule','wrong_destination','not_released'])
def test_runner_preserves_native_world_and_score_and_cleans_private_tokens(task,control):
    a=FakeAuthor(spec(task));scene=a.scene;score=a.score
    report=PoseNegativeAuthor(a,control).solve_negative()
    assert a.scene is scene and a.c.scene is scene and scene.spec==a.original
    assert a.score is score and report['original_native_result']is score and not score['success']
    assert report['negative_condition_observed']is None and report['native_validation_required']
    assert '_pose_negative_terminal_token'not in a.__dict__ and 'release_generated'not in a.__dict__ and 'act'not in a.__dict__
    assert not allow_original_terminal_failure(a)
    broken=FakeAuthor(spec(task),fail=True)
    with pytest.raises(RuntimeError,match='actual transfer obstruction'):PoseNegativeAuthor(broken,control).solve_negative()
    assert broken.scene is broken.c.scene and '_pose_negative_terminal_token'not in broken.__dict__


def test_intervention_must_be_real_not_just_native_zero():
    s=spec('E22');i=initial(s);p,_=negative_plan(s,'wrong_rule',i,BOUNDS);state=planned_state(s,p,i);contacts={frozenset((n,'table'))for n in state};score={'success':False,'progress_evidence':{'object_status':{n:{'stable':True}for n in state}}}
    intervention_observations(s,p,'wrong_rule',i,state,contacts,score)
    state['car']['pos'][0]+=.01
    with pytest.raises(RuntimeError,match='moved actual car'):intervention_observations(s,p,'wrong_rule',i,state,contacts,score)
    state=copy.deepcopy(i)
    with pytest.raises(RuntimeError,match='intended pose'):intervention_observations(s,p,'wrong_rule',i,state,contacts,score)


def test_absent_hold_contact_and_unstable_drop_rejected():
    s=spec('E15');i=initial(s);p,_=negative_plan(s,'not_released',i,BOUNDS);state=planned_state(s,p,i);name=p['goals'][-1]['object'];state[name]['grasp']=[True,False]
    score={'success':False,'progress_evidence':{'object_status':{n:{'stable':True}for n in state}}};contacts={frozenset((n,'table'))for n in state}
    with pytest.raises(RuntimeError,match='bilateral'):intervention_observations(s,p,'not_released',i,state,contacts,score,'left')
    contacts.update({frozenset((name,'left_finger1')),frozenset((name,'left_finger2'))});intervention_observations(s,p,'not_released',i,state,contacts,score,'left')
    for n in score['progress_evidence']['object_status']:score['progress_evidence']['object_status'][n]['stable']=False
    with pytest.raises(RuntimeError,match='stable table'):intervention_observations(s,p,'not_released',i,state,contacts,score,'left')


def test_actual_generated_terminal_hook_keeps_positive_failure_behavior():
    tree=ast.parse((Path(__file__).parents[1]/'videoicl_isaaclab/demonstration.py').read_text())
    f=next(x for x in ast.walk(tree)if isinstance(x,ast.FunctionDef)and x.name=='solve_generated')
    terminal=next(x for x in f.body if isinstance(x,ast.If)and ast.unparse(x.test)=="not score['success']")
    ns={'score':{'success':False},'self':FakeAuthor(spec('E15')),'__package__':'videoicl_isaaclab'}
    exec_ast=ast.Module(body=[terminal],type_ignores=[])
    with pytest.raises(RuntimeError,match='actual server evaluator'):exec(compile(ast.fix_missing_locations(exec_ast),'<actual terminal>','exec'),ns)
    ns['self']._pose_negative_terminal_token=object()
    with pytest.raises(RuntimeError):exec(compile(ast.fix_missing_locations(exec_ast),'<actual terminal>','exec'),ns)


@pytest.mark.parametrize('task',['E15','E22'])
def test_probe_capability_is_explicit_and_legacy_blocked(tmp_path,task):
    from videoicl_isaaclab.execution_design_reference import reference_capability
    from videoicl_isaaclab.execution_design_probe import validate_execution_cases
    b=json.loads((Path(__file__).parents[1]/'configs/realworld_full50_bindings.json').read_text());b['execution_design']={'revision':REVISION_V3,'condition':'I'};p=tmp_path/'b.json';p.write_text(json.dumps(b))
    case={'episode_id':'negative-test','task':task,'variant':'B','seed':4202,'robot':'franka','bindings':str(p)}
    for control in CAPABILITIES[task]:
        assert reference_capability(task,control)['implemented']
        assert validate_execution_cases([case],control)[0]['native_acceptance']=='not_run'
    assert not reference_capability(task,'wrong_members')['implemented']
    b['execution_design']={'revision':REVISION_V2,'condition':'R'};p.write_text(json.dumps(b))
    with pytest.raises(ValueError,match='explicit v3'):validate_execution_cases([case],'wrong_rule')
    a=FakeAuthor(spec(task));a.control_report={}
    with pytest.raises(ValueError,match='authorization'):PoseNegativeAuthor(a,'wrong_rule')


@pytest.mark.parametrize('with_actor_status',[False,True])
def test_e22_actual_native_semantic_labels_are_not_mistaken_for_missing_actor_evidence(with_actor_status):
    s=spec('E22');i=initial(s);p,_=negative_plan(s,'wrong_rule',i,BOUNDS);state=planned_state(s,p,i)
    objects={o['id']:o for o in s['objects']}
    label=lambda n:objects[n].get('semantic_identity',objects[n].get('identity',n))
    physical={label(n):dict(stable=True,released=True,supported=True)for n in state}
    assert 'green'in physical and 'green_block'not in physical
    evidence={'object_status':physical}
    if with_actor_status:evidence['actor_status']={n:physical[label(n)]for n in state}
    score={'success':False,'progress_evidence':evidence};contacts={frozenset((n,'table'))for n in state}
    assert set(intervention_observations(s,p,'wrong_rule',i,state,contacts,score))=={'red_block','green_block','blue_block','reference_car'}
    physical['green']['stable']=False
    with pytest.raises(RuntimeError,match='stable table'):intervention_observations(s,p,'wrong_rule',i,state,contacts,score)
