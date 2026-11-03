from types import SimpleNamespace as N
import numpy as np
import pytest
from test_execution_design_segments_e17_e20 import context
from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor as P
from videoicl_isaaclab.execution_design_e20_reference import pickup_via_transfer_support
from videoicl_isaaclab import engineering_front25_suffix as dispatch
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


@pytest.mark.parametrize('fault',['step','tick','readback','parameters'])
def test_C423_direct_entry_never_replays_unadmitted_or_wrong_boundary(monkeypatch,fault):
    a,state,contacts=context('E20','C');a._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':423,'physics_ticks':43140}};a.c._engineering_diagnostic_only=True;a.c._engineering_checkpoint_readback_passed=True
    params={}
    if fault=='step':a._engineering_resume_checkpoint['source']['steps']=424
    elif fault=='tick':a._engineering_resume_checkpoint['source']['physics_ticks']=43141
    elif fault=='readback':a.c._engineering_checkpoint_readback_passed=False
    else:params={'invented_target':1}
    monkeypatch.setattr(P,'act',lambda *a,**kw:pytest.fail('invalid boundary must not issue actions'))
    with pytest.raises(ToolExecutionError):dispatch.solve(a,a._engineering_resume_checkpoint,{'entry':'e20_c_direct_remaining_from423','parameters':params})


def test_direct_destination_keeps_public_pickup_and_requires_native_admission(monkeypatch):
    a,state,contacts=context('E20','C');p=P(a);p._engineering_e20_direct_destination=True;calls=[]
    a.c._engineering_diagnostic_only=True;a.c._engineering_checkpoint_readback_passed=True
    monkeypatch.setattr('videoicl_isaaclab.execution_design_e20_reference.nearest_target_hand',lambda *args:'left')
    p.pickup=lambda n,side_override:(calls.append((n,side_override))or(p.ref(n),side_override))
    ref,side=pickup_via_transfer_support(p,'blue_supply_2',[.2,.1,.82])
    assert calls==[('blue_supply_2','left')]and side=='left'
    a.c._engineering_checkpoint_readback_passed=False
    with pytest.raises(ToolExecutionError):pickup_via_transfer_support(p,'blue_supply_2',[.2,.1,.82])
    assert len(calls)==1
