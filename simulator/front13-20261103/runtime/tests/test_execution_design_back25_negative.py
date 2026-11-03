from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_back25_negative import negative_plan,Back25NegativeAuthor,CAPABILITIES
from videoicl_isaaclab.execution_design_reference import reference_capability


def spec(task,variant='A',seed=4201):
    return apply_execution_inputs(load(task,variant,0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False),condition='E' if task in ('E47','E48','E49') else 'I',seed=seed,revision=REVISION_V3)

@pytest.mark.parametrize('task,control',[(t,c)for t,cs in CAPABILITIES.items()if t in ('E33','E35','E41')for c in cs])
@pytest.mark.parametrize('variant','ABC')
@pytest.mark.parametrize('seed',(4201,4202,4203))
def test_semantic_plan_changes_only_author_waypoints(task,control,variant,seed):
    s=spec(task,variant,seed);before=deepcopy(s);p,delta=negative_plan(s,control)
    assert s==before and p is not s
    assert p['objects']==s['objects'] and p['semantic']==s['semantic']
    assert delta['negative_condition_observed'] is None
    old=[g['object']for g in s['goals']];new=[g['object']for g in p['goals']]
    if control=='wrong_members':
        if task=='E33':assert new[0]!=s['semantic']['selected']
        else:assert len(new)==len(old)-1 and delta['omitted_member']not in new
    elif control=='wrong_rule':
        if task=='E35':
            assert new!=old and set(new)==set(old)
            objects={o['id']:o for o in p['objects']};z={z['id']:z for z in p['zones']};height=.8
            for g in p['goals']:
                assert z[g['target']]['surface_z']==pytest.approx(height)
                height+=2*objects[g['object']]['size'][2]
        else:
            assert delta['attempted_mapping']!=s['semantic']['mapping']
            assert set(new)==set(old)
            objects={o['id']:o for o in p['objects']};z={z['id']:z for z in p['zones']}
            for ref,piece in delta['attempted_mapping'].items():
                goal=next(g for g in p['goals']if g['object']==piece)
                assert objects[ref]['xy'][0]-objects[ref]['size'][0]-(z[goal['target']]['xy'][0]+objects[piece]['size'][0])==pytest.approx(.001)
    elif control=='wrong_destination':
        assert new==old and p['goals'][0]['target']!=s['goals'][0]['target']
    else:assert new==old and delta['held_member']==old[-1]

class FakeAuthor:
    def __init__(self,s,fail=False,grasp=True):
        self.scene=SimpleNamespace(spec=s,embodiment=SimpleNamespace(config={}))
        self.c=SimpleNamespace(scene=self.scene,steps=0);self.smooth=False;self.fail=fail;self.grasp=grasp
        self.c.snapshot=lambda:({o['id']:dict(grasp=[self.grasp,self.grasp])for o in s['objects']},[])
    def act(self):self.c.steps+=1
    def release_generated(self,side):self.act()
    def solve_generated(self):
        assert self.scene is not self.c.scene
        assert self.scene.spec is not self.c.scene.spec
        if self.fail:raise RuntimeError('physical failure')
        for goal in self.scene.spec['goals']:self.release_generated('left')

@pytest.mark.parametrize('task',[t for t,cs in CAPABILITIES.items() if {'wrong_members','not_released'}<=cs])
@pytest.mark.parametrize('control',('wrong_members','not_released'))
def test_proxy_is_restored_and_evaluator_contract_never_changed(task,control):
    s=spec(task);a=FakeAuthor(s);scene=a.scene;before=deepcopy(s)
    out=Back25NegativeAuthor(a,control).solve_negative()
    assert a.scene is scene and a.c.scene is scene and s==before
    assert 'release_generated'not in a.__dict__
    assert not a._execution_design_reference_authorized
    assert out['negative_condition_observed'] is None
    a=FakeAuthor(s,fail=True)
    with pytest.raises(RuntimeError,match='physical failure'):Back25NegativeAuthor(a,control).solve_negative()
    assert a.scene is a.c.scene and 'release_generated'not in a.__dict__


def test_missing_actual_grasp_rejects_not_released_control():
    a=FakeAuthor(spec('E33'),grasp=False)
    with pytest.raises(RuntimeError,match='physically held'):Back25NegativeAuthor(a,'not_released').solve_negative()
    assert a.scene is a.c.scene


def test_no_duplicate_or_invented_controls():
    assert not reference_capability('E35','wrong_destination')['implemented']
    assert not reference_capability('E33','wrong_rule')['implemented']
    assert 'duplicate' in reference_capability('E33','wrong_rule')['reason']


@pytest.mark.parametrize('task',('E27','E31','E32','E34','E36','E38'))
@pytest.mark.parametrize('variant','ABC')
@pytest.mark.parametrize('seed',(4201,4202,4203))
def test_additional_specific_negatives(task,variant,seed):
    import math
    s=spec(task,variant,seed);before=deepcopy(s)
    for control in CAPABILITIES[task]:
        p,delta=negative_plan(s,control)
        assert s==before and p['objects']==s['objects'] and p['semantic']==s['semantic']
        assert p['goals'] and delta['negative_condition_observed'] is None
        assert all(g['object']in {o['id']for o in s['objects']}for g in p['goals'])
        if control=='wrong_rule':
            if task=='E31':
                assert p['goals'][0]['pitch']-s['goals'][0].get('pitch',0)==pytest.approx(math.pi)
                assert p['goals'][0]['target']==s['goals'][0]['target']
                assert 'local-up' in delta['required_native_review']
            elif task=='E38':
                assert [g['object']for g in p['goals']]!=[g['object']for g in s['goals']]
                assert [g['stack_rank']for g in p['goals']]==[0,1,2]
                assert all(g['target']=='rightmost'for g in p['goals'])
                assert 'hole' in delta['required_native_review']
            elif task=='E27':assert delta['attempted_placements']!=s['semantic']['placements']
        if control=='not_released':assert delta['held_member']==s['goals'][-1]['object']
        if task=='E36' and control=='wrong_destination'and len(s['goals'])==1:
            assert 'do not count twice' in delta['overlap_note']
    if task=='E31':assert not reference_capability(task,'wrong_destination')['implemented']
    if task in ('E32','E34','E36'):assert not reference_capability(task,'wrong_rule')['implemented']


@pytest.mark.parametrize('task',('E47','E48','E49'))
@pytest.mark.parametrize('variant','ABC')
def test_card_negative_preserves_real_flip_and_slot_requirements(task,variant):
    s=spec(task,variant);before=deepcopy(s)
    for control in CAPABILITIES[task]:
        p,d=negative_plan(s,control)
        assert s==before and p['objects']==s['objects'] and p['semantic']==s['semantic']
        assert p['goals'] and d['negative_condition_observed'] is None
        if control=='wrong_members':
            assert p['goals']!=s['goals']
        elif control=='wrong_rule':assert d['attempted_plate_mapping']!=s['semantic']['mapping']
        elif control=='not_released':assert d['held_member']==s['goals'][-1]['object']
        if task=='E48':assert 'insertion-axis' in d['slot_review']
        assert 'flip history' in d['required_native_review']


@pytest.mark.parametrize('task',('E28','E42','E46'))
@pytest.mark.parametrize('variant','ABC')
def test_no_tool_counterexample_uses_original_goals_but_actual_hand_actions(task,variant):
    s=spec(task,variant);p,d=negative_plan(s,'wrong_rule')
    assert p['goals']==s['goals'] and p['semantic']==s['semantic'] and p['objects']==s['objects']
    assert d['attempted_mechanism']=='direct_hand_pick_and_place_without_tool_use'
    a=FakeAuthor(s);original=a.scene
    out=Back25NegativeAuthor(a,'wrong_rule').solve_negative()
    assert a.scene is original and a.c.scene is original
    assert out['negative_condition_observed'] is None and a.c.steps>0


@pytest.mark.parametrize('task,control', [('E34','unselected_cutlery_moved'),('E47','unrevealed_cards_disturbed'),('E49','unrevealed_cards_disturbed')])
@pytest.mark.parametrize('variant','ABC')
def test_preservation_counterexample_keeps_selected_plan_then_moves_real_other(task,control,variant):
    from videoicl_isaaclab.realworld_scenes import load
    from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
    from videoicl_isaaclab.execution_design import REVISION_V3
    from pathlib import Path
    original=apply_execution_inputs(load(task,variant,0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False),condition='E',seed=4201,revision=REVISION_V3)
    before=deepcopy(original);plan,p=negative_plan(original,control)
    assert plan['goals'][:-1]==original['goals']
    name=plan['goals'][-1]['object']
    if task!='E34':
        assert name not in original['semantic']['groups']['active']
        assert plan['goals'][-1]['roll']==pytest.approx(3.141592653589793)
    else:assert name!=original['semantic']['selected']
    zone=next(z for z in plan['zones']if z['id']==plan['goals'][-1]['target'])
    obj=next(o for o in original['objects']if o['id']==name)
    assert zone['xy'][0]==pytest.approx(obj['xy'][0]+.04)
    assert original==before and p['negative_condition_observed']is None
