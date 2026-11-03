from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_bell_negative import BellNegativeAuthor, _Author
from videoicl_isaaclab.execution_design_reference import reference_capability

@pytest.mark.parametrize('variant', 'ABC')
@pytest.mark.parametrize('seed', (4201,4202,4203,4218))
@pytest.mark.parametrize('control', ('wrong_rule','not_released'))
def test_counterexample_plan_and_public_action_boundary(monkeypatch,variant,seed,control):
    spec=apply_execution_inputs(load('E26',variant,0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False),condition='I',seed=seed,revision=REVISION_V3)
    original=deepcopy(spec)
    def init(self,a):
        self.spec=spec;self.task='E26';self.variant=variant;self.c=SimpleNamespace(steps=0)
        self.start_steps=0;self.operations=[]
        self.roles={r:dict(closed_tolerance=.001,open_threshold=.005) for r in ('left','right')}
    monkeypatch.setattr(_Author,'__init__',init)
    p=BellNegativeAuthor(SimpleNamespace(scene=SimpleNamespace(spec=spec)),control)
    calls=[];pressed=set()
    p.press=lambda role,index:calls.append((role,index))
    p.act=lambda *a,**k:None
    p.hand=lambda role:role
    p.stage=lambda s:None
    p.approach=lambda *a,**k:None
    p.displacement=lambda role:.01 if role in pressed else 0
    p.no_touch=lambda role:role not in pressed
    p.touching=lambda role,side:role in pressed
    p.tip=lambda side:[0,0,0]
    p.press_steps=lambda role,side,start:pressed.add(role)
    out=p.solve_negative()
    counts={r:sum(c[0]==r for c in calls)for r in ('left','right')}
    expected=p.perturbation['expected']
    if control=='wrong_rule':
        assert counts==dict(left=expected['left']+1,right=expected['right'])
        assert not pressed
    else:
        held=p.perturbation['held_role'];assert pressed=={held}
        assert counts[held]==expected[held]-1
        assert out['operations'][-1]['operation']=='press_hold'
        p.touching=lambda *a:False
        pressed.clear()
        with pytest.raises(RuntimeError,match='physically held'):p.solve_negative()
    assert out['negative_condition_observed'] is None
    assert spec==original

@pytest.mark.parametrize('control', ('wrong_members','wrong_destination'))
def test_bell_has_no_invented_members_or_delivery(control):
    assert reference_capability('E26',control)['implemented'] is False
    with pytest.raises(ValueError):BellNegativeAuthor(SimpleNamespace(scene=SimpleNamespace(spec={'id':'E26'})),control)

@pytest.mark.parametrize('control', ('wrong_rule','not_released'))
def test_capability_available_but_not_native_validated(control):
    cap=reference_capability('E26',control)
    assert cap['implemented'] is True and cap['native_validated'] is False
