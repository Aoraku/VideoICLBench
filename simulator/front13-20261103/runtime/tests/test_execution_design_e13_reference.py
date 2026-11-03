from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e13_reference import align_phone_side_band,side_band

class Reference:
    def __init__(self):
        self._execution_design_reference_authorized=True
        self.obj=dict(id='phone',size=[.075,.03698669,.00473954],grasp_point_local=[0,0,0])
        self.scene=SimpleNamespace(spec=dict(id='E13',execution_design=dict(revision='embodied50-execution-v3-20261102'),objects=[self.obj]))
        self.tcp=np.array([.06475,.12909,.81834]);self.low=.80868
        self.state=dict(pos=[.06606,.13176,.80474],mat=np.eye(3))
        self.c=SimpleNamespace(snapshot=lambda:({'phone':self.state},None))
        self.moves=[];self.blocked=False
    def tip(self,side):return self.tcp.copy()
    def finger_geometry(self,side):return dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=self.low)
    def move_generated(self,goals,tolerance):
        target=np.array(next(iter(goals.values())));self.moves.append(target)
        if not self.blocked:
            # A changing wrist angle makes a stale TCP-to-toe offset inaccurate.
            self.low+=(target[2]-self.tcp[2])*.85
            self.tcp=target

def test_native_failure_geometry_converges_without_touching_table():
    a=Reference();align_phone_side_band(a,'left','phone')
    assert 1<len(a.moves)<=6
    assert .8005<a.low<.8011
    assert np.max(abs(a.tcp[:2]-np.array(a.state['pos'])[:2]))<.001
    assert all(p[2]>.8 for p in a.moves)

def test_blocked_actual_fingers_fail_instead_of_assuming_target_reached():
    a=Reference();a.blocked=True
    with pytest.raises(RuntimeError,match='did not converge'):align_phone_side_band(a,'left','phone')
    assert len(a.moves)==6

@pytest.mark.parametrize('change',[lambda a:setattr(a,'_execution_design_reference_authorized',False),lambda a:a.scene.spec.update(id='E14'),lambda a:a.scene.spec['execution_design'].update(revision='old')])
def test_no_legacy_or_other_task_mutation(change):
    a=Reference();change(a)
    with pytest.raises(ValueError):align_phone_side_band(a,'left','phone')
    assert not a.moves

@pytest.mark.parametrize('z',[.79,.82,float('nan')])
def test_wrong_support_and_nonfinite_pose_are_rejected(z):
    a=Reference();a.state['pos'][2]=z
    with pytest.raises(ValueError):side_band(a.state,a.obj)


def test_measured_closure_rise_retains_phone_side_band():
    a=Reference();_,target,top=side_band(a.state,a.obj)
    # Observed first closure raised the TCP by 6.7122 mm. This is a
    # conservative geometric candidate check, not simulated grasp success.
    assert target-.0003>=.8003
    assert top-(target+.0003+.0067122)>.001
