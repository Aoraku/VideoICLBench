from copy import deepcopy
import math
from types import SimpleNamespace
import pytest
from videoicl_isaaclab import engineering_checkpoint as core
from videoicl_isaaclab.engineering_checkpoint_reference import validate_after_settle

def scene(monkeypatch,focus):
    root=[0.,0.,1.,1.,0.,0.,0.,0.,0.,0.,0.,0.,0.]
    saved=dict(objects={n:dict(root_state_task=root.copy())for n in ('blue_square','stand','blue_triangle')},mechanisms={})
    actual=deepcopy(saved);actual['objects']['blue_triangle']['root_state_task'][3:7]=[math.cos(math.pi/8),math.sin(math.pi/8),0,0]
    monkeypatch.setattr(core,'capture',lambda *a:actual)
    contacts={frozenset(('blue_square','right_finger1')),frozenset(('blue_square','right_finger2')),frozenset(('stand','table'))}
    c=SimpleNamespace(snapshot=lambda:({n:dict(grasp=[False,n=='blue_square'])for n in saved['objects']},contacts))
    request=dict(required_contacts=[['stand','table']],required_grasps=[['blue_square','right']])
    if focus is not None:request['focus_objects']=focus
    return c,dict(checkpoint=saved,request=request,restore_receipt={})

def test_unselected_settling_is_disclosed_without_blocking_actual_held_segment(monkeypatch):
    c,r=scene(monkeypatch,['blue_square','stand']);out=validate_after_settle(c,r)
    assert out['passed'] and not out['all_objects_within_tolerances']
    assert out['all_objects_maximum_rotation_drift_rad']==pytest.approx(math.pi/4)
    assert not out['per_object_drift']['blue_triangle']['required_for_segment']

def test_default_keeps_full_readback_guard(monkeypatch):
    c,r=scene(monkeypatch,None)
    with pytest.raises(ValueError,match='physical readback rejected'):validate_after_settle(c,r)

@pytest.mark.parametrize('focus',[[],['stand'],['blue_square','missing'],['stand','stand']])
def test_focus_cannot_omit_required_body_or_inject_unknown_names(monkeypatch,focus):
    c,r=scene(monkeypatch,focus)
    with pytest.raises(ValueError):validate_after_settle(c,r)
