"""Reference counterexample boundary tests; these are not physics acceptance."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3,source_sha256
from videoicl_isaaclab.execution_design_drawer_negative import DrawerNegativeAuthor,_Author,SELECTED
from videoicl_isaaclab.execution_design_reference import reference_capability

@pytest.mark.parametrize('variant','ABC')
@pytest.mark.parametrize('control',('wrong_rule','not_released'))
def test_drawer_counterexample_never_mutates_native_spec(monkeypatch,variant,control):
    spec=dict(id='E30',variant=variant,execution_design=dict(revision=REVISION_V3,source_sha256=source_sha256(REVISION_V3)),goals=[{'native_rule':variant}]);original=deepcopy(spec)
    def init(self,author):
        self.spec=spec;self.task='E30';self.variant=variant;self.c=SimpleNamespace(steps=0);self.start_steps=0;self.operations=[]
    attempts=[]
    monkeypatch.setattr(_Author,'__init__',init)
    monkeypatch.setattr(_Author,'solve',lambda self:attempts.append(self.variant))
    p=DrawerNegativeAuthor(SimpleNamespace(scene=SimpleNamespace(spec=spec)),control)
    held=[];p.acquire=lambda role:held.append(role)or'left';p.stage=lambda name:None;p.act=lambda:None;p.touching=lambda *a,**k:True;p.displacement=lambda role:.05
    result=p.solve_negative()
    assert spec==original and p.variant==variant
    assert result['negative_condition_observed'] is None and result['native_validation_required'] is True
    if control=='wrong_rule':
        assert SELECTED[attempts[0]]!=SELECTED[variant] and not held
    else:
        assert attempts==[variant] and held==[SELECTED[variant][0]]
        p.touching=lambda *a,**k:False
        with pytest.raises(RuntimeError,match='actual bilateral contact'):p.solve_negative()

@pytest.mark.parametrize('control',('wrong_members','wrong_destination'))
def test_drawer_does_not_invent_members_or_delivery(control):
    assert reference_capability('E30',control)['implemented'] is False
    with pytest.raises(ValueError):DrawerNegativeAuthor(SimpleNamespace(scene=SimpleNamespace(spec={'id':'E30'})),control)

@pytest.mark.parametrize('control',('wrong_rule','not_released'))
def test_drawer_negative_implementation_is_not_native_validation(control):
    cap=reference_capability('E30',control)
    assert cap['implemented'] is True and cap['native_validated'] is False
