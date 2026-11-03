from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e28_plane_feed import plane_height,run
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def tool():
    return dict(actor='blade',support_normal_local=[.31,0.,np.sqrt(1-.31**2)],support_plane_offset=.03,
        support_bounds={'lower':[.07,-.038,0.],'upper':[.125,.038,.03]})


def test_actual_plane_height_invariant_along_its_true_slope():
    t=tool();state={'pos':np.array([0.,0.,.8]),'mat':np.eye(3)};anchor=[.15,0.]
    initial=plane_height(t,state,anchor);normal=np.asarray(t['support_normal_local'])
    translated=dict(state,pos=state['pos']+np.array([.003,0.,-.003*normal[0]/normal[2]]))
    assert abs(plane_height(t,translated,anchor)-initial)<1e-12
    # A blocked stroke only achieves0.5mm forward. Descending as if3mm were
    # achieved really lowers the plane; the feedback must see that discrepancy.
    partial=dict(state,pos=state['pos']+np.array([.0005,0.,-.003*normal[0]/normal[2]]))
    assert plane_height(t,partial,anchor)<initial-.0008


def test_plane_feed_stops_when_public_requests_have_no_real_relative_motion(tmp_path):
    t=tool();state={'blade':{'pos':np.zeros(3),'mat':np.eye(3)},'food':{'pos':np.array([.15,0.,.01]),'mat':np.eye(3),'grasp':[False,False]}}
    actions=[];controller=SimpleNamespace(steps=0)
    def act(side,token,mm):actions.append((token,mm));controller.steps+=1
    p=SimpleNamespace(snapshot=lambda:(state,set()),require_held=lambda *args:None,
        contact=lambda *args:True,stage=lambda *args:None,point=lambda *args:np.array([.133,0.,0.]),
        a=SimpleNamespace(out=tmp_path),c=controller,act=act)
    with pytest.raises(ToolExecutionError,match='no1mm relative progress'):
        run(p,t,{},'right','food',{},np.array([1.,0.,0.]))
    assert len(actions)<=12 and all(x[0]=='FWD'for x in actions)
