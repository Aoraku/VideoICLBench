"""Contact/envelope clearance checks, not a native pass certificate."""
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e09_clearance import supported_package_payload,measured_package_clearance


def scene():
    objects={'box':dict(size=[.1,.1,.05]),'cargo':dict(size=[.03,.03,.01]),
             'lid':dict(size=[.1,.1,.004]),'obstacle':dict(size=[.1,.1,.05])}
    state={n:dict(pos=np.array(p),mat=np.eye(3)) for n,p in
           [('box',[0,0,1.2]),('cargo',[0,0,1.18]),('lid',[0,0,1.254]),('obstacle',[.4,0,.86])]}
    contacts={frozenset(('box','cargo')),frozenset(('box','lid'))}
    return objects,state,contacts


def test_real_connected_carried_contents_and_lid_not_counted_as_external_obstacle():
    objects,state,contacts=scene()
    assert supported_package_payload('box',objects,state,contacts)=={'box','cargo','lid'}
    p=SimpleNamespace(objects=objects,spec={'fixtures':[]},snapshot=lambda:(state,contacts),
        point=lambda ref:np.array([0,0,1.15]),bottom_local=lambda name:[0,0,-.05],
        tip=lambda side:np.array([0,0,1.25]),operations=[],
        a=SimpleNamespace(floor_clear_tcp=lambda side,floor:floor+.06))
    assert measured_package_clearance(p,'box','right')==pytest.approx(1.0)
    assert p.operations[-1]['obstacle_top_m']==pytest.approx(.91)


def test_missing_contact_and_external_side_touch_do_not_hide_an_obstacle():
    objects,state,contacts=scene();contacts.remove(frozenset(('box','lid')))
    assert 'lid' not in supported_package_payload('box',objects,state,contacts)
    contacts.add(frozenset(('box','obstacle')));state['obstacle']['pos']=np.array([.2,0,1.3])
    assert 'obstacle' not in supported_package_payload('box',objects,state,contacts)


def test_nested_actual_contact_chain_is_included_and_rotation_preserves_membership():
    objects,state,contacts=scene();contacts.remove(frozenset(('box','cargo')))
    contacts.add(frozenset(('lid','cargo')))
    assert supported_package_payload('box',objects,state,contacts)=={'box','cargo','lid'}
    rotation=np.array([[0,-1,0],[1,0,0],[0,0,1]])
    for value in state.values():value['pos']=rotation@value['pos'];value['mat']=rotation@value['mat']
    assert supported_package_payload('box',objects,state,contacts)=={'box','cargo','lid'}
