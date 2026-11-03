"""Fixed recovery allows existing shallow overlap only while moving away."""
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_e17_palm_escape as escape
from videoicl_isaaclab import execution_design_segments_e17_upper as geometry
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def box(lo,hi):return np.array([[x,y,z]for x in(lo[0],hi[0])for y in(lo[1],hi[1])for z in(lo[2],hi[2])])


def test_signed_convex_margin_distinguishes_gap_touch_and_overlap():
    a=box([0,0,0],[1,1,1])
    assert escape.signed_sat_margin(a,a+[2,0,0])==pytest.approx(1)
    assert escape.signed_sat_margin(a,a+[1,0,0])==pytest.approx(0)
    assert escape.signed_sat_margin(a,a+[.75,0,0])==pytest.approx(-.25)


@pytest.mark.parametrize('mode',['good','deep','new_contact','deepen'])
def test_fixed_recovery_never_ignores_unreviewed_contact(monkeypatch,mode):
    p=SimpleNamespace(operations=[],calls=[]);initial=-.0003 if mode!='deep'else-.003
    if mode=='new_contact':initial=.003
    cloud=box([0,0,0],[.001,.001,.001]);cap=box([.01,.01,.01],[.02,.02,.02])
    monkeypatch.setattr(escape,'_state',lambda *args:({'position':np.zeros(3),'rotation':np.eye(3)},[{'name':'panda_hand','points':cloud}],cap))
    values=iter([initial]+([-0.0004]if mode in('deepen','new_contact')else[initial+.001*i for i in range(1,8)]))
    if mode=='good':
        # All predicted and actual pair checks monotonically separate.
        counter=iter(np.linspace(-.0003,.01,100))
        monkeypatch.setattr(escape,'signed_sat_margin',lambda *args:next(counter))
    else:monkeypatch.setattr(escape,'signed_sat_margin',lambda *args:next(values))
    monkeypatch.setattr(geometry,'_check',lambda *args,**kwargs:p.calls.append(('check',kwargs)))
    p.act=lambda *args,**kwargs:p.calls.append(('act',args,kwargs))
    if mode=='good':
        escape.escape_to_default_tilt(p,'blue_triangle',lambda:None)
        actions=[c for c in p.calls if c[0]=='act'];assert len(actions)==5
        assert all(c[1]==('right','ROLL_LEFT')and c[2]=={'degrees':1.5}for c in actions)
        assert p.calls[-1]==('check',{'payload':'blue_triangle','wrist_only':True})
    else:
        with pytest.raises(ToolExecutionError):escape.escape_to_default_tilt(p,'blue_triangle',lambda:None)
        assert not any(c[0]=='act'for c in p.calls)
