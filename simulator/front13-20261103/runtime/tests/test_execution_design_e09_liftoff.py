import numpy as np
from types import SimpleNamespace
import pytest
from videoicl_isaaclab.execution_design_e09_liftoff import lift_piece
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
class P:
 def __init__(self,tmp,slip=False):
  self.task='E09';self.spec={'execution_design':{'revision':'embodied50-execution-v3-20261102'},'fixtures':[{'type':'box','xy':[0,0],'size':[.1,.1,.01]}]*10};self.a=SimpleNamespace(out=tmp,control_report={'engineering_reference_only':True});self.c=SimpleNamespace(steps=0);self.z=.839;self.t=.839;self.slip=slip
 def frame(self,r):return np.array([0.,0.,self.z]),np.eye(3)
 def tip(self,s):return np.array([0,0,self.t])
 def contact(self,a,b):return b=='fixture9' and self.z<.84
 def held(self,r,s):return not(self.slip and self.c.steps>0)
 def require_held(self,r,s):
  if not self.held(r,s):raise ToolExecutionError('lost')
 def act(self,s,token,mm):
  assert token=='UP' and mm==2.;self.c.steps+=1;self.t+=.0017
  if not self.slip:self.z+=.0017

def test_small_step_requires_actual_payload_and_support_release(tmp_path):
 p=P(tmp_path);lift_piece(p,{'actor':'blue_triangle'},'right');assert p.z>=.909;assert 41<=p.c.steps<=43

def test_slip_never_returns_success(tmp_path):
 p=P(tmp_path,True)
 with pytest.raises(ToolExecutionError,match='lost'):lift_piece(p,{'actor':'blue_triangle'},'right')
 assert p.c.steps==1

def test_other_task_rejected(tmp_path):
 p=P(tmp_path);p.task='E08'
 with pytest.raises(ValueError):lift_piece(p,{'actor':'left_shoe'},'left')


def test_transport_cap_restored_after_native_grip_failure(tmp_path):
 from videoicl_isaaclab.execution_design_e09_liftoff import piece_transport_steps
 p=P(tmp_path);p.max_mm=10.;p.d={'target_members':['red_triangle']}
 with pytest.raises(ToolExecutionError):
  with piece_transport_steps(p,'red_triangle'):
   assert p.max_mm==2.
   raise ToolExecutionError('actual lost grip')
 assert p.max_mm==10.


@pytest.mark.parametrize('change',[{'task':'E20'},{'name':'group_box0'},{'formal':True}])
def test_transport_cap_only_engineering_e09_pieces(tmp_path,change):
 from videoicl_isaaclab.execution_design_e09_liftoff import piece_transport_steps
 p=P(tmp_path);p.max_mm=10.;p.d={'target_members':['red_triangle']};p.task=change.get('task','E09')
 if change.get('formal'):p.a.control_report['engineering_reference_only']=False
 with piece_transport_steps(p,change.get('name','red_triangle')):assert p.max_mm==10.
