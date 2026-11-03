import numpy as np
import pytest
from videoicl_isaaclab.author_mplib_planner import ARM_NAMES,filter_goal_joint_margin


def test_optional_goal_margin_rejects_near_limit_but_not_native_finger_aperture():
    names=ARM_NAMES+['panda_finger_joint1','panda_finger_joint2']
    limits=np.array([[-3.,3.]]*7+[[0.,.04]]*2)
    near=np.array([0.,0.,0.,0.,-2.988,0.,0.,0.,0.])
    clear=near.copy();clear[4]=-2.7
    kept,margins=filter_goal_joint_margin([near,clear],names,limits,.12)
    assert kept==[clear]
    assert margins==pytest.approx([.012,.3])
    assert near[4]==-2.988 and np.array_equal(limits,np.array([[-3.,3.]]*7+[[0.,.04]]*2))


@pytest.mark.parametrize('margin',[-.01,.51,float('nan')])
def test_private_goal_filter_never_accepts_invalid_margin(margin):
    with pytest.raises(ValueError):
        filter_goal_joint_margin([],ARM_NAMES,np.array([[-3.,3.]]*7),margin)
