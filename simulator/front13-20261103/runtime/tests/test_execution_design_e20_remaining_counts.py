from copy import deepcopy
import pytest
from test_execution_design_segments_e17_e20 import context
from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor as P
from videoicl_isaaclab import execution_design_e20_slots as slots


@pytest.mark.parametrize('completed_count',[2,3])
def test_remaining_selection_uses_actual_supported_count_after_distance_ranking_changes(monkeypatch,completed_count):
    a,state,contacts=context('E20','B');p=P(a);p.d=deepcopy(p.d)
    r=next(r for r in p.d['local_regions']if r['id']=='triangle');p.d['local_regions']=[r]
    completed={'blue_supply_3','blue_supply_4'}
    if completed_count==3:completed.add('blue_supply_1')
    contacts.update(frozenset((n,r['actor']))for n in completed)
    monkeypatch.setattr(slots,'_inside',lambda p,r,n:n in completed)
    # Simulate the exact native case: already placed blue1 is far from bases,
    # causing an unused source blue2 to rank before it when the suffix resumes.
    monkeypatch.setattr('videoicl_isaaclab.execution_design_e20_reference.replenishment_candidates',lambda *args:['blue_supply_2','blue_supply_3','blue_supply_1'])
    monkeypatch.setattr('videoicl_isaaclab.execution_design_e20_reference.ordered_replenishment_regions',lambda p:p.d['local_regions'])
    p._engineering_skip_actual_completed_regions=True;a.c._engineering_diagnostic_only=True;a.c._engineering_checkpoint_readback_passed=True
    p.free_chip_slot=lambda *args:[0,0,0];calls=[];p.place=lambda n,*args:calls.append(n)
    original=deepcopy(a.scene.spec);p.local_stage()
    assert len(calls)==3-completed_count
    if calls:assert calls==['blue_supply_2']
    assert a.scene.spec==original
