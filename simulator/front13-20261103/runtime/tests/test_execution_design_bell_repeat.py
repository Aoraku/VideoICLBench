from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3,source_sha256
from videoicl_isaaclab.execution_design_bell_repeat import enabled
from videoicl_isaaclab.realworld_mechanism_expert import _Author


def author():
    p=object.__new__(_Author);p.task='E26';p.spec={'id':'E26','execution_design':{'revision':REVISION_V3,'source_sha256':source_sha256(REVISION_V3)}}
    p.a=SimpleNamespace(control_report={'engineering_reference_only':True},scene=SimpleNamespace(embodiment=SimpleNamespace(config={})))
    p.points={'left':{}};p.roles={'left':{'closed_tolerance':.0005}};p.clearance=.91
    p.button_releases={'left':'left'};p.point=lambda _:np.array([0,0,.853]);p.axis=lambda _:np.array([0,0,-1.])
    p.tip=lambda _:np.array([0,0,.873]);p.displacement=lambda _:0.;p.no_touch=lambda _:True
    p.moves=[];p.move=lambda side,target,**kwargs:p.moves.append(np.asarray(target))
    return p


def test_explicit_engineering_flag_and_exact_source_required(monkeypatch):
    p=author();assert not enabled(p);monkeypatch.setenv('VIC_ENGINEERING_BELL_SHORT_REPEAT','1');assert enabled(p)
    p.a.control_report={};assert not enabled(p)
    p.a.control_report={'engineering_reference_only':True};p.spec['execution_design']['source_sha256']='wrong';assert not enabled(p)
    p.spec['execution_design']['source_sha256']=source_sha256(REVISION_V3);p.spec['id']='E30';assert not enabled(p)


def test_short_repeat_only_after_real_same_bell_release(monkeypatch):
    monkeypatch.setenv('VIC_ENGINEERING_BELL_SHORT_REPEAT','1');p=author();p.approach('left','left',button=True)
    assert len(p.moves)==1;np.testing.assert_allclose(p.moves[0],[0,0,.873])


@pytest.mark.parametrize('blocked',['contact','spring','lateral','different_bell'])
def test_physical_guard_failure_uses_original_high_clearance(monkeypatch,blocked):
    monkeypatch.setenv('VIC_ENGINEERING_BELL_SHORT_REPEAT','1');p=author()
    if blocked=='contact':p.no_touch=lambda _:False
    elif blocked=='spring':p.displacement=lambda _: .001
    elif blocked=='lateral':p.tip=lambda _:np.array([.01,0,.873])
    else:p.button_releases={'left':'other'}
    p.approach('left','left',button=True);assert len(p.moves)==3 and p.moves[0][2]>=.95


def test_retreat_still_executes_public_twelve_mm_motion(monkeypatch):
    monkeypatch.setenv('VIC_ENGINEERING_BELL_SHORT_REPEAT','1');p=author();p.retreat('left','left',button=True)
    assert len(p.moves)==1;np.testing.assert_allclose(p.moves[0],[0,0,.885])
    monkeypatch.delenv('VIC_ENGINEERING_BELL_SHORT_REPEAT');p.moves=[];p.retreat('left','left',button=True);assert len(p.moves)==2
