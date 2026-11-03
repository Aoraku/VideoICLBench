import numpy as np
from videoicl_isaaclab.execution_design_e08_source_pair import nearest_down_jaw


def test_symmetric_jaw_uses_current_assignment_without_unneeded180_turn():
    a=np.diag([1.,-1.,-1.]);b=np.diag([-1.,1.,-1.])
    assert np.allclose(nearest_down_jaw(a,np.eye(3)),a)
    assert np.allclose(nearest_down_jaw(b,np.eye(3)),b)


def test_first_actual_cooked_contact_includes_beveled_floor_and_other_shoe():
    import itertools
    from videoicl_isaaclab.execution_design_e08_source_pair import first_cooked_contact_height
    def b(lo,hi):return np.array(list(itertools.product(*zip(lo,hi))))
    shoe=[b([-.1,-.03,-.05],[.1,.03,.05])];floor=b([-.2,-.1,-.06],[.2,.1,-.05]);other=b([-.1,.04,-.05],[.1,.09,.02])
    assert np.isclose(first_cooked_contact_height(shoe,[0,0],[floor,other]),0.)
    assert np.isclose(first_cooked_contact_height(shoe,[0,.05],[floor,other]),.07)
