from types import SimpleNamespace
import pytest
from videoicl_isaaclab.engineering_native_tick import diagnostic_tick_scope


def setup():
    events=[]
    class Controller:
        _engineering_diagnostic_only=True
        def tick(self,render=False,*,phase='full'):
            if phase=='full':raise RuntimeError('Use pool')
            events.append(phase)
    c=Controller();p=SimpleNamespace(controllers={'room':c},terminal={})
    def tick(render=False):
        c.tick(phase='write');events.append('single-physics-step');c.tick(phase='read');events.append('capture-hooks')
    p.tick=tick;c._room_pool=p
    return SimpleNamespace(c=c,control_report={'engineering_reference_only':True}),p,events


def test_private_tick_uses_exact_original_shared_world_path_once():
    a,p,events=setup()
    with diagnostic_tick_scope(a):
        a.c.tick(render=True)
        assert a.c._room_pool is p
    assert events==['write','single-physics-step','read','capture-hooks']
    with pytest.raises(RuntimeError,match='Use pool'):a.c.tick()


def test_bridge_restores_on_failure_and_refuses_siblings_or_model_context():
    a,p,events=setup()
    with pytest.raises(RuntimeError,match='segment failure'):
        with diagnostic_tick_scope(a):raise RuntimeError('segment failure')
    assert 'tick'not in vars(a.c)
    p.controllers['sibling']=object()
    with pytest.raises(ValueError,match='one live'): 
        with diagnostic_tick_scope(a):pass
    p.controllers.pop('sibling');a.control_report['engineering_reference_only']=False
    with pytest.raises(ValueError,match='engineering diagnostic'):
        with diagnostic_tick_scope(a):pass


def reference():
    a,p,events=setup();a.c._engineering_diagnostic_only=False
    a.scene=SimpleNamespace(spec={'id':'E37','seed':4201,'execution_design':{
        'condition':'R','revision':'embodied50-execution-v3-20261102'}})
    a._engineering_e37_verified_path=True
    return a,p,events


def test_source_reference_needs_explicit_opt_in_and_keeps_original_pool_tick():
    a,p,events=reference()
    with pytest.raises(ValueError,match='engineering diagnostic'):
        with diagnostic_tick_scope(a):pass
    with diagnostic_tick_scope(a,reference_authorization=True):a.c.tick()
    assert events==['write','single-physics-step','read','capture-hooks']
    assert a.c._room_pool is p and 'tick'not in vars(a.c)
    p.controllers['sibling']=object()
    with pytest.raises(ValueError,match='one live'):
        with diagnostic_tick_scope(a,reference_authorization=True):pass


@pytest.mark.parametrize('wrong',['task','seed','condition','revision','flag','model'])
def test_source_exception_cannot_enable_other_tasks_or_model_execution(wrong):
    a,p,events=reference();spec=a.scene.spec
    if wrong=='task':spec['id']='E31'
    elif wrong=='seed':spec['seed']=4202
    elif wrong=='condition':spec['execution_design']['condition']='I'
    elif wrong=='revision':spec['execution_design']['revision']='older'
    elif wrong=='flag':a._engineering_e37_verified_path=False
    else:a.control_report['engineering_reference_only']=False
    with pytest.raises(ValueError):
        with diagnostic_tick_scope(a,reference_authorization=True):a.c.tick()
    assert not events and 'tick'not in vars(a.c)


def test_source_e31c_requires_its_own_marker_and_keeps_original_pool_tick():
    a,p,events=reference();a._engineering_e37_verified_path=False
    a._engineering_e31_verified_path=True
    a.scene.spec.update(id='E31',variant='C')
    a.scene.spec['execution_design']['condition']='I'
    with diagnostic_tick_scope(a,reference_authorization=True):a.c.tick()
    assert events==['write','single-physics-step','read','capture-hooks']
    assert a.c._room_pool is p and 'tick'not in vars(a.c)


@pytest.mark.parametrize('wrong',['variant','seed','condition','revision','flag','model'])
def test_e31c_source_gate_cannot_reach_old_b_or_other_authorizations(wrong):
    a,p,events=reference();a._engineering_e37_verified_path=False
    a._engineering_e31_verified_path=True
    a.scene.spec.update(id='E31',variant='C')
    a.scene.spec['execution_design']['condition']='I'
    if wrong=='variant':a.scene.spec['variant']='B'
    elif wrong=='seed':a.scene.spec['seed']=4202
    elif wrong=='condition':a.scene.spec['execution_design']['condition']='R'
    elif wrong=='revision':a.scene.spec['execution_design']['revision']='older'
    elif wrong=='flag':a._engineering_e31_verified_path=False
    else:a.control_report['engineering_reference_only']=False
    with pytest.raises(ValueError):
        with diagnostic_tick_scope(a,reference_authorization=True):a.c.tick()
    assert not events and 'tick'not in vars(a.c)


def test_e28_contact_hold_is_explicit_and_does_not_change_original_tick_path():
    a,p,events=reference();a._engineering_e37_verified_path=False
    a.scene.spec.update(id='E28',variant='A')
    a.scene.spec['execution_design']['condition']='I'
    with pytest.raises(ValueError):
        with diagnostic_tick_scope(a,reference_authorization=True):a.c.tick()
    a._engineering_e28_contact_hold=True
    with diagnostic_tick_scope(a,reference_authorization=True):a.c.tick()
    assert events==['write','single-physics-step','read','capture-hooks']
    assert a.c._room_pool is p and 'tick'not in vars(a.c)


@pytest.mark.parametrize('wrong',['task','seed','condition','revision','model'])
def test_e28_hold_gate_cannot_enable_other_contexts(wrong):
    a,p,events=reference();a._engineering_e37_verified_path=False
    a._engineering_e28_contact_hold=True
    a.scene.spec.update(id='E28',variant='A')
    a.scene.spec['execution_design']['condition']='I'
    if wrong=='task':a.scene.spec['id']='E27'
    elif wrong=='seed':a.scene.spec['seed']=4202
    elif wrong=='condition':a.scene.spec['execution_design']['condition']='R'
    elif wrong=='revision':a.scene.spec['execution_design']['revision']='older'
    else:a.control_report['engineering_reference_only']=False
    with pytest.raises(ValueError):
        with diagnostic_tick_scope(a,reference_authorization=True):a.c.tick()
    assert not events and 'tick'not in vars(a.c)
