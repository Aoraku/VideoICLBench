import pytest
from test_execution_design_segments_e17_e20 import context
from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor as P
from videoicl_isaaclab import execution_design_e20_reference as reference


@pytest.mark.parametrize('seed,expected',[(4201,'left'),(4202,'right')])
def test_only_reviewed_B_blue1_full_route_uses_real_destination_hand(monkeypatch,seed,expected):
    a,state,contacts=context('E20','B');a.scene.spec['seed']=seed;p=P(a);p._e20_freed_source_rail={'actor':'fixture2','xy':[-.29,-.12],'surface_z':.836}
    calls=[]
    monkeypatch.setattr(reference,'nearest_target_hand',lambda p,target:'left'if target[1]>0 else'right')
    class StopAfterActualPickup(Exception):pass
    def pickup(name,*,side_override):
        calls.append((name,side_override));raise StopAfterActualPickup()
    p.pickup=pickup
    with pytest.raises(StopAfterActualPickup):reference.pickup_via_transfer_support(p,'blue_supply_1',[.149,.08,.82])
    assert calls==[('blue_supply_1',expected)]
