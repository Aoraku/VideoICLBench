from types import SimpleNamespace
import pytest
from videoicl_isaaclab.engineering_contact_warmup import settle_checkpoint


def world(contact_ticks,**request):
    counter=[0]
    controller=SimpleNamespace(snapshot=lambda:({},
        {frozenset(('lid','table'))}if counter[0]in contact_ticks else set()))
    pool=SimpleNamespace(tick=lambda:counter.__setitem__(0,counter[0]+1))
    resumed={'room':dict(request=dict(required_contacts=[['lid','table']],**request))}
    return pool,{'room':controller},resumed,counter


def test_default_retains_exact_fixed_native_tick_count():
    pool,controllers,resumed,count=world({0})
    assert settle_checkpoint(pool,controllers,resumed,10)is None
    assert count[0]==10


def test_actual_retarget_contact_does_not_advance_to_an_absent_contact_frame():
    pool,controllers,resumed,count=world({0,2,4,5},settle_until_required_contacts=True)
    result=settle_checkpoint(pool,controllers,resumed,120)
    assert count[0]==0 and result['required_contacts_observed']
    assert not result['contacts_fabricated']


def test_stop_on_first_actual_contact_instead_of_requiring_extra_stability():
    pool,controllers,resumed,count=world({2},settle_until_required_contacts=True)
    result=settle_checkpoint(pool,controllers,resumed,120)
    assert count[0]==2 and result['actual_extra_ticks']==2


def test_absent_contact_exhausts_finite_bound_and_is_never_filled():
    pool,controllers,resumed,count=world(set(),settle_until_required_contacts=True)
    result=settle_checkpoint(pool,controllers,resumed,4)
    assert count[0]==4 and not result['required_contacts_observed']


@pytest.mark.parametrize('options',[dict(settle_until_required_contacts=1),
    dict(settle_until_required_contacts='true')])
def test_nonboolean_request_rejected_without_physics(options):
    pool,controllers,resumed,count=world(set(),**options)
    with pytest.raises(ValueError,match='boolean'):settle_checkpoint(pool,controllers,resumed,4)
    assert count[0]==0


def test_missing_named_gate_is_rejected_before_physics():
    pool,controllers,resumed,count=world(set(),settle_until_required_contacts=True)
    resumed['room']['request']['required_contacts']=[]
    with pytest.raises(ValueError,match='named required'):settle_checkpoint(pool,controllers,resumed,4)
    assert count[0]==0
