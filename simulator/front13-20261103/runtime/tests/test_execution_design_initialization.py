"""Startup state application only; these mocks are not native acceptance."""
from types import SimpleNamespace
from pathlib import Path
import numpy as np
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_initialization import initialize_declared_mechanisms

class Tensor(np.ndarray):
    def clone(self):return self.copy()

def scene():
    s=load('E30','A',0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False)
    s=apply_execution_inputs(s,condition='I',seed=4201,revision=REVISION_V3)
    m=s['mechanisms'][0];writes=[]
    # Deliberately reverse source order: writes must follow actual PhysX names.
    asset=SimpleNamespace(joint_names=['joint_2','joint_1'],
        data=SimpleNamespace(default_joint_pos=np.zeros((1,2)).view(Tensor),
                             default_joint_vel=np.ones((1,2)).view(Tensor)),
        write_joint_state_to_sim=lambda p,v:writes.append((p.copy(),v.copy())),
        write_data_to_sim=lambda:writes.append('flush'))
    return SimpleNamespace(spec=s,mechanisms={m['id']:asset}),asset,writes

def test_declared_positions_applied_once_in_actual_joint_order():
    s,a,w=scene();receipt=initialize_declared_mechanisms(s)
    assert len(w)==2 and w[1]=='flush'
    np.testing.assert_allclose(w[0][0],[[.011,.009]])
    np.testing.assert_equal(w[0][1],[[0.,0.]])
    np.testing.assert_equal(a.data.default_joint_pos,[[0.,0.]])
    assert receipt[0]['measurement_verified'] is False
    with pytest.raises(RuntimeError,match='live reset forbidden'):initialize_declared_mechanisms(s)
    assert len(w)==2

def test_old_scene_without_declaration_has_no_writes():
    s,a,w=scene();s.spec['mechanisms'][0].pop('initial_joint_positions')
    s.spec.pop('execution_design')
    assert initialize_declared_mechanisms(s)==[] and not w

@pytest.mark.parametrize('fault',['unknown_joint','wrong_revision','wrong_declared_state'])
def test_invalid_input_fails_before_any_write(fault):
    s,a,w=scene()
    if fault=='unknown_joint':a.joint_names=['unknown','joint_1']
    if fault=='wrong_revision':s.spec['execution_design']['revision']='legacy'
    if fault=='wrong_declared_state':s.spec['mechanisms'][0]['initial_joint_positions']['joint_1']=.04
    with pytest.raises(ValueError):initialize_declared_mechanisms(s)
    assert not w

def test_failed_write_is_not_repeated_on_live_world():
    s,a,w=scene()
    def fail(*args):raise RuntimeError('physics write failed')
    a.write_joint_state_to_sim=fail
    with pytest.raises(RuntimeError,match='physics write'):initialize_declared_mechanisms(s)
    with pytest.raises(RuntimeError,match='live reset forbidden'):initialize_declared_mechanisms(s)
