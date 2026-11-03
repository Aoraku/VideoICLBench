from types import SimpleNamespace
import copy
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_e04_reference import lift_from_support


class Author:
    def __init__(self, out, response=.0015, lose_at=None, stuck_table=False):
        self.out=out;self.scene=SimpleNamespace(spec={'id':'E04','execution_design':{'revision':REVISION_V3}})
        self._execution_design_reference_authorized=True
        self.generated_axis_signs={'left':{2:1},'right':{2:1}}
        self.calls=[];self.z=.84;self.response=response;self.lose_at=lose_at;self.stuck_table=stuck_table
        self.c=SimpleNamespace(snapshot=self.snapshot)

    def snapshot(self):
        held=self.lose_at is None or len(self.calls)<self.lose_at
        contacts={frozenset(('cup','table'))} if not self.calls or self.stuck_table else set()
        return {'cup':{'pos':np.array([0,0,self.z]),'grasp':[held,held]}},contacts

    def tip(self, side):return np.array([0,0,.87+len(self.calls)*.002])

    def act(self,left,right,mm):
        self.calls.append((left,right,mm));self.z+=self.response


@pytest.mark.parametrize('side',['left','right'])
def test_actual_object_motion_and_release_required(tmp_path,side):
    a=Author(tmp_path);spec=copy.deepcopy(a.scene.spec)
    lift_from_support(a,'cup',side)
    assert .012<=a.z-.84<.014
    assert all(x==('UP','STILL',2.) if side=='left' else x==('STILL','UP',2.) for x in a.calls)
    assert a.scene.spec==spec


def test_tcp_motion_alone_cannot_pass(tmp_path):
    a=Author(tmp_path,response=0.)
    with pytest.raises(RuntimeError,match='actual object'):lift_from_support(a,'cup','left')
    assert len(a.calls)==24


def test_grip_loss_stops_before_next_action(tmp_path):
    a=Author(tmp_path,lose_at=2)
    with pytest.raises(RuntimeError,match='grip lost'):lift_from_support(a,'cup','left')
    assert len(a.calls)==2


def test_contact_still_present_rejects_success(tmp_path):
    a=Author(tmp_path,stuck_table=True)
    with pytest.raises(RuntimeError,match='still contacts table'):lift_from_support(a,'cup','left')


@pytest.mark.parametrize('change',[{'id':'E05'},{'execution_design':{'revision':'old'}}])
def test_other_task_or_revision_cannot_use_hook(tmp_path,change):
    a=Author(tmp_path);a.scene.spec.update(change)
    with pytest.raises(ValueError):lift_from_support(a,'cup','left')
    assert not a.calls


def test_formal_evaluation_cannot_use_hook(tmp_path):
    a=Author(tmp_path);a._execution_design_reference_authorized=False
    with pytest.raises(ValueError):lift_from_support(a,'cup','left')
    assert not a.calls
