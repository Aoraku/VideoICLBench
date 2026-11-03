import numpy as np
from videoicl_isaaclab.execution_design_card_direct import plan_open_target


def box(center,half):
    return np.asarray(center)+np.asarray([[x,y,z]for x in(-half[0],half[0])for y in(-half[1],half[1])for z in(-half[2],half[2])])


def test_adjacent_plate_blocks_central_open_finger_but_not_a_real_offcentre_card_section():
    tcp=np.array([0.,0.,1.]);fingers=[box([0.,y,1.], [.005,.005,.010])for y in(-.05,.05)]
    palm=box([0.,0.,1.08],[.025,.02,.01]);plate=box([0.,.05,.806],[.006,.012,.006])
    plan=plan_open_target([0.,0.,.800175],np.eye(3),tcp,fingers,palm,.8,{'plate':plate})
    assert plan['candidates'][0]['blocked_by']==['plate']
    assert plan['candidates'][-1]['blocked_by']==[]
    assert .010<abs(plan['position'][0])<=.03
    assert not plan['native_grasp_verified']
