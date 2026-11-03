from types import SimpleNamespace
import math
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e12_branch import make_plan,_settle,_rotate
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError,_axis_rotation


def test_toe_plan_keeps_source_and_uses_original_first_frame_without_replacing_goal():
    frames={'charger_1':(np.array([.1,.1,.86]),np.eye(3)),
            'charger_2':(np.array([-.1,-.12,.824]),_axis_rotation([1,0,0],math.pi/2))}
    policy=SimpleNamespace(task='E12',variant='A',spec={'execution_design':{'condition':'R'}},
        objects={'charger_2':{'source_asset':{'sha256':'e5843b3b6f1829b5a251030b7204eb5988b412a4f648138e7eb0a870f703b043'}}},
        a=SimpleNamespace(control_report={'e12_actual_acquired_hand_frames':[dict(actor='charger_1',side='right',relative_hand_rotation=np.eye(3))]}),
        frame=lambda ref:frames[ref['actor']])
    plan=make_plan(policy)
    assert plan['grip_local']==[0.,.012,.036]and plan['phase']=='warm'
    assert plan['source_pos']==frames['charger_2'][0].tolist()
    np.testing.assert_allclose(np.asarray(plan['toe_rotation'])[:,2],[0,1,0],atol=1e-12)
    assert 'goal'not in plan


def test_restored_pending_empty_rotation_only_holds_original_target_and_keeps_count():
    feedback={'orientation_error_rad':.08,'orientation_tolerance_rad':.05};calls=[]
    def act(side,token):calls.append((side,token));feedback['orientation_error_rad']=.001
    policy=SimpleNamespace(act=act,c=SimpleNamespace(action_feedback=lambda:{'control_feedback':{'right':feedback}}))
    state=dict(pending_rotation=True,pending_holds=2,rotation_commands={'restore':7,'side':0})
    _settle(policy,state,SimpleNamespace(check=lambda:None))
    assert calls==[('right','STILL')]and state['rotation_commands']['restore']==7
    assert state['pending_holds']==3 and not state['pending_rotation']


def test_empty_rotation_refuses_more_actions_after_original_round_bound():
    calls=[];policy=SimpleNamespace(a=SimpleNamespace(tcp_rotation_task=lambda side:_axis_rotation([1,0,0],.3)),act=lambda *a,**kw:calls.append(a))
    state=dict(pending_rotation=False,restore_rotation=np.eye(3),rotation_commands={'restore':100,'side':0})
    with pytest.raises(ToolExecutionError,match='finite round bound'):_rotate(policy,state,SimpleNamespace(check=lambda:None),'restore',5.)
    assert not calls
