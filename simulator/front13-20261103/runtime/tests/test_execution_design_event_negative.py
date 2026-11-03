from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from videoicl_isaaclab import execution_design_event_negative as mod
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_reference import reference_capability

@pytest.mark.parametrize('task,control', [('E29','wrong_rule'),('E43','wrong_destination')])
@pytest.mark.parametrize('variant','ABC')
@pytest.mark.parametrize('seed',(4201,4202,4203))
def test_private_sequence_target_and_original_event_evaluator_isolation(monkeypatch,task,control,variant,seed):
    original=apply_execution_inputs(load(task,variant,0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False),condition='E',seed=seed,revision=REVISION_V3)
    before=deepcopy(original);scene=SimpleNamespace(spec=original,embodiment=SimpleNamespace(config={'author_recording':{'mallet_single_contact_stroke':True,'guide_stop_on_physical_release':True}}))
    a=SimpleNamespace(scene=scene,c=SimpleNamespace(scene=scene,steps=0),smooth=False)
    calls=[]
    class Policy:
        def __init__(self,author):
            assert author.c.scene is scene
            assert author.scene.spec is original
            assert not author.scene.embodiment.config['author_recording']['mallet_single_contact_stroke']
            self.s=original['semantic'];self.index='ABC'.index(variant);self.start=0;self.operations=[]
        def mallet(self):
            assert self.s is not original['semantic']
            assert self.s['keys']['1']==original['semantic']['keys']['2']
            assert self.s['key_frames']['1']==original['semantic']['key_frames']['2']
            assert self.s['key_points']['1']==original['semantic']['key_points']['2']
            calls.append('actual_mallet_route')
        def guide(self):
            assert self.index==('ABC'.index(variant)+1)%3
            assert self.s is original['semantic']
            calls.append('actual_gravity_launcher_route')
        def wait(self,n):pass
    monkeypatch.setattr(mod,'ToolAuthor',Policy)
    policy=mod.EventNegativeAuthor(a,control);out=policy.solve_negative()
    assert calls and a.scene is scene and original==before
    assert scene.embodiment.config['author_recording']['mallet_single_contact_stroke']
    assert out['negative_condition_observed'] is None
    if task=='E29':
        p=policy.perturbation;assert p['expected_sequence']!=p['attempted_sequence']
        assert sorted(p['expected_sequence'])==sorted(p['attempted_sequence'])
        assert 'not_released' in p['not_applicable']
    else:assert policy.perturbation['expected_region']!=policy.perturbation['attempted_region']
    Policy.mallet=lambda self:(_ for _ in ()).throw(RuntimeError('contact missing'))
    Policy.guide=Policy.mallet
    with pytest.raises(RuntimeError,match='contact missing'):mod.EventNegativeAuthor(a,control).solve_negative()
    assert a.scene is scene and original==before


def test_events_do_not_invent_delivery_or_release_rules():
    for control in ('wrong_members','wrong_destination','not_released'):
        assert not reference_capability('E29',control)['implemented']
    assert not reference_capability('E43','wrong_members')['implemented']
    assert not reference_capability('E43','wrong_rule')['implemented']
    assert 'duplicate' in reference_capability('E43','wrong_rule')['reason']


@pytest.mark.parametrize('task',('E28','E40','E42','E44','E45','E46','E50'))
@pytest.mark.parametrize('variant','ABC')
def test_specific_tool_variants_keep_original_world_and_use_real_method(monkeypatch,task,variant):
    s=apply_execution_inputs(load(task,variant,0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False),condition='E',seed=4201,revision=REVISION_V3)
    scene=SimpleNamespace(spec=s,embodiment=SimpleNamespace(config={}))
    a=SimpleNamespace(scene=scene,c=SimpleNamespace(scene=scene,steps=0),smooth=False)
    before=deepcopy(s);calls=[]
    class Policy:
        def __init__(self,author):
            self.index='ABC'.index(variant);self.start=0;self.operations=[];self.s=s['semantic']
        def wait(self,n):pass
    def action(self):
        assert self.index==('ABC'.index(variant)+1)%3
        assert self.s is s['semantic']
        calls.append(mod.METHODS[task])
    setattr(Policy,mod.METHODS[task],action);monkeypatch.setattr(mod,'ToolAuthor',Policy)
    control='wrong_members'if task=='E28'else'wrong_rule'if task in ('E40','E44')else'wrong_destination'
    out=mod.EventNegativeAuthor(a,control).solve_negative()
    assert calls==[mod.METHODS[task]] and s==before and a.scene is scene
    assert out['negative_condition_observed'] is None
    if task=='E44':assert out['perturbation']['attempted_angle_deg']!=out['perturbation']['expected_angle_deg']


@pytest.mark.parametrize('task',('E28','E45','E46'))
@pytest.mark.parametrize('contact_ok',(True,False))
def test_retained_tool_negative_requires_actual_contact_and_restores_author(monkeypatch,task,contact_ok):
    s=apply_execution_inputs(load(task,'A',0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False),condition='E',seed=4201,revision=REVISION_V3)
    scene=SimpleNamespace(spec=s,embodiment=SimpleNamespace(config={}))
    a=SimpleNamespace(scene=scene,c=SimpleNamespace(scene=scene,steps=0),smooth=False,stage='initial')
    class Policy:
        def __init__(self,author):self.index=0;self.start=0;self.operations=[];self.s=s['semantic']
        def wait(self,n):a.c.steps+=n
        def require_held(self,*args):
            if not contact_ok:raise RuntimeError('actual grip missing')
        def contact(self,*args):return contact_ok
        def move_point(self,*args,**kwargs):a.c.steps+=1
        def park(self,*args):raise AssertionError('Original park releases cup')
        def pour(self):assert self.index==0;self.park({'actor':'cup'},'left')
        def spatula(self):
            assert self.index==0
            a.stage='transport-spatula-'+self.s['groups']['cargo'][0]
            for _ in range(4):self.move_point('right',{},[0,0,0])
            raise AssertionError('Must stop before actual withdrawal')
    monkeypatch.setattr(mod,'ToolAuthor',Policy)
    if contact_ok:
        out=mod.EventNegativeAuthor(a,'not_released').solve_negative()
        assert out['negative_condition_observed'] is None
    else:
        with pytest.raises(RuntimeError):mod.EventNegativeAuthor(a,'not_released').solve_negative()
    assert a.scene is scene and scene.spec is s


def test_e28_wrong_destination_preserves_rule_and_actual_tool_route(monkeypatch):
    import numpy as np
    s=apply_execution_inputs(load('E28','A',0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False),condition='E',seed=4201,revision=REVISION_V3)
    scene=SimpleNamespace(spec=s,embodiment=SimpleNamespace(config={}))
    a=SimpleNamespace(scene=scene,c=SimpleNamespace(scene=scene,steps=0),smooth=False)
    class Policy:
        def __init__(self,author):self.index=0;self.start=0;self.operations=[];self.s=s['semantic']
        def wait(self,n):pass
        def snapshot(self):return {n:dict(pos=np.array([.11,-.22,.85]))for n in self.s['groups']['cargo']},[]
        def spatula(self):
            assert self.index==0
            dest=self.destination(self.s['groups']['cargo'][0])
            assert dest[:2].tolist()==[.11,-.22]
    monkeypatch.setattr(mod,'ToolAuthor',Policy)
    out=mod.EventNegativeAuthor(a,'wrong_destination').solve_negative()
    assert out['negative_condition_observed'] is None and a.scene is scene


def test_e42_omission_uses_real_push_with_original_two_ball_evaluator(monkeypatch):
    s=apply_execution_inputs(load('E42','B',0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False),condition='I',seed=4201,revision=REVISION_V3)
    before=deepcopy(s);scene=SimpleNamespace(spec=s,embodiment=SimpleNamespace(config={}))
    a=SimpleNamespace(scene=scene,c=SimpleNamespace(scene=scene,steps=0),smooth=False)
    class Policy:
        def __init__(self,author):self.index=1;self.start=0;self.operations=[];self.s=s['semantic']
        def wait(self,n):pass
        def push(self):
            assert self.index==1
            assert self.s['groups']['balls']==s['semantic']['groups']['balls'][:1]
            assert len(a.c.scene.spec['semantic']['groups']['balls'])==2
    monkeypatch.setattr(mod,'ToolAuthor',Policy)
    out=mod.EventNegativeAuthor(a,'wrong_members').solve_negative()
    assert out['perturbation']['omitted_member']==s['semantic']['groups']['balls'][1]
    assert s==before and a.scene is scene


@pytest.mark.parametrize('task',('E44','E50'))
@pytest.mark.parametrize('contact_ok',(True,False))
def test_fold_or_card_real_retention_before_release(monkeypatch,task,contact_ok):
    s=apply_execution_inputs(load(task,'A',0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False),condition='E',seed=4201,revision=REVISION_V3)
    before=deepcopy(s);scene=SimpleNamespace(spec=s,embodiment=SimpleNamespace(config={}))
    a=SimpleNamespace(scene=scene,c=SimpleNamespace(scene=scene,steps=0),smooth=False)
    class Policy:
        def __init__(self,author):self.index=0;self.start=0;self.operations=[];self.s=s['semantic']
        def wait(self,n):a.c.steps+=n
        def require_held(self,*args):
            if not contact_ok:raise RuntimeError('actual grip missing')
        def clip_ref(self,*args):return dict(mechanism='clip',body='frame')
        def clip_contact(self,*args):return contact_ok
        def squeeze(self,*args):a.c.steps+=1
        def fold(self):
            assert self.index==0
            self.release(dict(mechanism='paper',body='fold'),'right')
            raise AssertionError('Fold release must be withheld')
        def clip_card(self):
            assert self.index==0
            clip=next(iter(self.s['clips'].values()))
            self.squeeze(clip,{},'right')
            self.squeeze(clip,{},'left')
            raise AssertionError('Card unclamping must be withheld')
    monkeypatch.setattr(mod,'ToolAuthor',Policy)
    if contact_ok:
        out=mod.EventNegativeAuthor(a,'not_released').solve_negative()
        assert out['negative_condition_observed']is None
    else:
        with pytest.raises(RuntimeError,match='actual grip'):mod.EventNegativeAuthor(a,'not_released').solve_negative()
    assert a.scene is scene and s==before


def test_event_applicability_does_not_mark_implemented_members_na():
    for task in ('E28','E42'):
        s=apply_execution_inputs(load(task,'A',0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False),condition='I',seed=4201,revision=REVISION_V3)
        a=SimpleNamespace(scene=SimpleNamespace(spec=s),smooth=False)
        assert 'wrong_members'not in mod.EventNegativeAuthor(a,'wrong_members').perturbation['not_applicable']
