from types import SimpleNamespace
import pytest
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def test_held_x_suffix_does_not_repeat_pickup_or_certify_full_positive(monkeypatch):
    from videoicl_isaaclab import engineering_e39_suffix as route
    from videoicl_isaaclab import execution_design_e39_reference as tray
    calls=[]
    class Policy:
        task='E39';start=0
        def __init__(self,a):self.d={'packages':[dict(container='protective_box',lower=[0,0,-.03])]};self.c=a.c
        def ref(self,n):return dict(actor=n)
        def require_held(self,ref,side):calls.append(('held',side))
        def pickup(self,*args):pytest.fail('Suffix replayed acquisition')
        def wait(self,n):pass
    monkeypatch.setattr(route,'ExecutionDesignAuthor',Policy)
    monkeypatch.setattr(route,'verify_released_boxed_tray',lambda *args:True)
    monkeypatch.setattr(tray,'carry_held_work_tray',lambda p,container,point,ref,side,entry:calls.append((entry,side)))
    a=SimpleNamespace(c=SimpleNamespace(steps=0),control_report={'engineering_reference_only':True})
    result=route.solve(a,{'schema':'engineering-native-checkpoint-v1'},{'entry':'e39-tray-x-and-seat','context':{'hand':'left'}})
    assert calls==[('held','left'),('x','left')]
    assert result['diagnostic_only']and not result['native_acceptance']and not result['source_initial_state_full_positive']
    assert a._execution_design_reference_authorized is False


def test_restored_contact_loss_stops_before_any_suffix_motion(monkeypatch):
    from videoicl_isaaclab import engineering_e39_suffix as route
    from videoicl_isaaclab import execution_design_e39_reference as tray
    class Policy:
        task='E39';start=0
        def __init__(self,a):self.d={'packages':[dict(container='protective_box',lower=[0,0,-.03])]};self.c=a.c
        def ref(self,n):return dict(actor=n)
        def require_held(self,*args):raise ToolExecutionError('actual grip absent after reset')
    monkeypatch.setattr(route,'ExecutionDesignAuthor',Policy)
    monkeypatch.setattr(tray,'carry_held_work_tray',lambda *a,**kw:pytest.fail('Lost grip progressed'))
    a=SimpleNamespace(c=SimpleNamespace(steps=0),control_report={'engineering_reference_only':True})
    with pytest.raises(ToolExecutionError,match='actual grip absent'):
        route.solve(a,{'schema':'engineering-native-checkpoint-v1'},{'entry':'e39-tray-x-and-seat'})
    assert a._execution_design_reference_authorized is False


def test_suffix_needs_physical_containment_even_with_support_contacts():
    import numpy as np
    from videoicl_isaaclab.engineering_e39_suffix import verify_released_boxed_tray
    state={n:dict(pos=np.zeros(3),mat=np.eye(3),grasp=[False,False])for n in ('work_tray','protective_box','red')}
    contacts={frozenset(('work_tray','protective_box')),frozenset(('red','work_tray'))}
    policy=SimpleNamespace(snapshot=lambda:(state,contacts),d={'target_members':['red']},objects={'work_tray':{'size':[.03]*3},'red':{'size':[.02]*3}})
    package={'container':'protective_box','lower':[-.1]*3,'upper':[.1]*3}
    assert verify_released_boxed_tray(policy,package)
    state['red']['pos'][0]=.095
    assert not verify_released_boxed_tray(policy,package)
    state['red']['pos'][0]=0;state['work_tray']['grasp'][0]=True
    assert not verify_released_boxed_tray(policy,package)


def test_second_small_correction_uses_existing_tilt_margin():
    import numpy as np
    from videoicl_isaaclab.engineering_e39_suffix import bounded_down_rotation
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    from videoicl_isaaclab.author_orientation import _axis_angle
    current=np.eye(3);full=_axis_rotation([1,0,0],np.deg2rad(7))
    tray=_axis_rotation([1,0,0],np.deg2rad(4))
    result=bounded_down_rotation(current,full,tray)
    assert np.rad2deg(_axis_angle(result)[1])<=1.25
    assert (result@tray)[2,2]>=.996


def test_pregrip_suffix_uses_only_authorized_new_grip_phase(monkeypatch):
    from videoicl_isaaclab import engineering_e39_suffix as route
    from videoicl_isaaclab import execution_design_e39_reference as tray
    calls=[]
    class Policy:
        task='E39';start=0
        def __init__(self,a):self.d={'packages':[dict(container='protective_box',lower=[0,0,-.03])]};self.c=a.c
        def snapshot(self):return ({'work_tray':dict(grasp=[False,False])},set())
        def wait(self,n):pass
    monkeypatch.setattr(route,'ExecutionDesignAuthor',Policy)
    monkeypatch.setattr(tray,'place_work_tray',lambda *args:calls.append('corrected-physical-acquisition'))
    monkeypatch.setattr(route,'verify_released_boxed_tray',lambda *args:True)
    a=SimpleNamespace(c=SimpleNamespace(steps=0),control_report={'engineering_reference_only':True})
    result=route.solve(a,{'schema':'engineering-native-checkpoint-v1'},{'entry':'e39-pregrip-down-and-seat'})
    assert calls==['corrected-physical-acquisition']
    assert result['segment_passed']and not result['source_initial_state_full_positive']
    monkeypatch.setattr(Policy,'snapshot',lambda self:({'work_tray':dict(grasp=[True,False])},set()))
    with pytest.raises(ToolExecutionError,match='unexpectedly holds'):
        route.solve(a,{'schema':'engineering-native-checkpoint-v1'},{'entry':'e39-pregrip-down-and-seat'})
    assert len(calls)==1
