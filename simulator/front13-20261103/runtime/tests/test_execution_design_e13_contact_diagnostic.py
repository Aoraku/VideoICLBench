from types import SimpleNamespace
import pytest
from videoicl_isaaclab.execution_design_e13_contact_diagnostic import enabled,install,FLAG

@pytest.mark.parametrize('task,revision,control,flag,expected',[('E13','embodied50-execution-v3-20261102','positive','1',True),('E13','old','positive','1',False),('E13','embodied50-execution-v3-20261102',None,'1',False),('E13','embodied50-execution-v3-20261102','positive','0',False),('E14','embodied50-execution-v3-20261102','positive','1',False)])
def test_explicit_diagnostic_scope(task,revision,control,flag,expected):
    assert enabled({'id':task,'execution_design':{'revision':revision}},control,{FLAG:flag})is expected

def test_ordinary_controller_gets_no_diagnostic_hooks(tmp_path):
    c=SimpleNamespace(scene=SimpleNamespace(),tick_hooks=[])
    install(c,tmp_path);assert c.tick_hooks==[]

def test_observer_error_is_recorded_without_interrupting_accepted_action(tmp_path):
    class Broken:
        def update(self,*args,**kwargs):raise RuntimeError('sensor unavailable')
    c=SimpleNamespace(scene=SimpleNamespace(spec={'id':'E13'},_diagnostic_target='phone',_e13_contact_diagnostic={'left/panda_hand':Broken()}),tick_hooks=[],steps=302,physics_ticks=31001,dt=.004,public_feedback=lambda:{'actual':True})
    install(c,tmp_path);c.tick_hooks[0](c,False)
    assert 'sensor unavailable'in(tmp_path/'e13-robot-contact-ticks.private.jsonl').read_text()
    assert c.steps==302 and c.physics_ticks==31001


def test_e08_requires_separate_explicit_flag():
    from videoicl_isaaclab.execution_design_e13_contact_diagnostic import enabled
    spec={'id':'E08','execution_design':{'revision':'embodied50-execution-v3-20261102'}}
    assert not enabled(spec,'positive',{'VIC_E13_CONTACT_DIAGNOSTIC':'1'})
    assert enabled(spec,'positive',{'VIC_E08_CONTACT_DIAGNOSTIC':'1'})
    assert not enabled(spec,'negative',{'VIC_E08_CONTACT_DIAGNOSTIC':'1'})
