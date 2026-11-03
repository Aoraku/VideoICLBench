from types import SimpleNamespace
import pytest
from videoicl_isaaclab.execution_design_e29_strikes import SeparatedStrikes,enabled
from videoicl_isaaclab.execution_design import REVISION_V3,source_sha256


def collector():
    return SimpleNamespace(tool={'actor':'mallet'},semantic={'keys':{'1':'key1','2':'key2'}},
        pending_strikes={},strikes=[],events=[],dt=.004,held=lambda _:True,steps=0)


def feed(t,e,contacts):
    e.steps+=1;e.force=lambda tool,key:contacts.get(key,0.);t.update(e)


def test_real_one_tick_microbounce_stays_one_impulse():
    t=SeparatedStrikes();e=collector()
    for _ in range(28):feed(t,e,{'key1':.01477605141699314/(28*.004)})
    feed(t,e,{});feed(t,e,{'key1':5.836845375597477e-6/.004})
    feed(t,e,{});feed(t,e,{})
    assert len(e.pending_strikes)==1 and not e.strikes
    feed(t,e,{})
    assert len(e.strikes)==1 and not e.pending_strikes
    assert e.strikes[0]['step']==1 and e.strikes[0]['release_step']==31
    assert e.strikes[0]['contact_impulse']==pytest.approx(.014781888262368737)
    assert e.strikes[0]['separation_confirmation_step']==33


def test_true_repeat_after_confirmed_separation_is_still_second_note():
    t=SeparatedStrikes();e=collector()
    for _ in range(2):
        feed(t,e,{'key1':1.})
        for _ in range(3):feed(t,e,{})
    assert [x['key']for x in e.strikes]==[1,1]
    assert e.strikes[1]['step']>e.strikes[0]['release_step']


def test_hold_and_two_tick_flicker_never_claims_release():
    t=SeparatedStrikes();e=collector()
    for _ in range(50):
        feed(t,e,{'key1':1.});feed(t,e,{});feed(t,e,{})
    assert not e.strikes and len(e.pending_strikes)==1


def test_two_keys_never_merged_or_force_filtered():
    t=SeparatedStrikes();e=collector()
    feed(t,e,{'key1':1e-10,'key2':2.})
    for _ in range(3):feed(t,e,{})
    assert sorted(x['key']for x in e.strikes)==[1,2]
    assert e.strikes[0]['contact_impulse']>0


def test_unheld_mallet_and_missing_ticks_rejected():
    t=SeparatedStrikes();e=collector();e.held=lambda _:False
    with pytest.raises(ValueError,match='grasp'):feed(t,e,{'key1':1.})
    t=SeparatedStrikes();e=collector();feed(t,e,{'key1':1.});feed(t,e,{})
    e.steps+=1
    with pytest.raises(ValueError,match='consecutive'):feed(t,e,{})


def test_scope_is_exact_pinned_v3_e29():
    d={'id':'E29','execution_design':{'revision':REVISION_V3,'source_sha256':source_sha256(REVISION_V3)}}
    assert enabled(d)
    assert not enabled({**d,'id':'E30'})
    assert not enabled({'id':'E29'})
    assert not enabled({'id':'E29','execution_design':{**d['execution_design'],'source_sha256':'wrong'}})
