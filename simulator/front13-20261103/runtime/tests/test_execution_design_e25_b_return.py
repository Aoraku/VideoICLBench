import numpy as np
import pytest
from test_execution_design_e25_a_receiver import fixture
from test_execution_design_e25_reference import scene
from videoicl_isaaclab import execution_design_e25_b_return as tail


def test_near_stop_empty_B_retracts_before_vertical_return(tmp_path,monkeypatch):
    a,state,contacts=fixture(tmp_path);a.scene.spec=scene(tmp_path,'B');a.tip_array[:]=[.1545,.1787,.8896]
    q=np.array([-.1578,1.609,.169,-.0699,-.165,1.787,.629]);limits=np.array([[-3.,3.]]*7);limits[3]=[-3.07,-.0698]
    monkeypatch.setattr(tail,'_joints',lambda a,s:(q,limits,[]));calls=[]
    def move(goals):
        target=np.asarray(goals['left']);assert target[0]<a.tip_array[0]and target[2]==a.tip_array[2]
        calls.append(target);a.tip_array[:]=target;q[3]=-.5
    a.move_generated=move;old=a.tip_array.copy()
    assert tail.retract_empty(a,'left',{'left':[-.29,.12]})
    assert len(calls)==1 and np.linalg.norm(a.tip_array[:2]-old[:2])==pytest.approx(.02)


def test_retraction_never_moves_a_held_payload(tmp_path,monkeypatch):
    a,state,contacts=fixture(tmp_path);a.scene.spec=scene(tmp_path,'B');state['spoon']['grasp'][0]=True
    a.move_generated=lambda *args:pytest.fail('no public movement while held')
    with pytest.raises(RuntimeError,match='empty'):tail.retract_empty(a,'left',{'left':[-.29,.12]})
