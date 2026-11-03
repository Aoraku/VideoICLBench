import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e18_ball_roll import plan_upper_back_push
from videoicl_isaaclab.realworld_mechanism_expert import MechanismExecutionError


def parts():
    from itertools import product
    finger = np.array(list(product([-.01,.01],[-.006,.006],[-.021,.035])))
    palm = np.array(list(product([-.04,.04],[-.04,.04],[.065,.11])))
    return [finger.copy(), finger.copy()], palm


def test_actual_closed_pusher_stays_outside_roof_and_roll_target_clears_open_jaw():
    fingers, palm = parts()
    source = np.array([-.106, .111, .861])
    target, goal = plan_upper_back_push(source, .015, fingers, palm, -.085, .924, .05, .094)
    rear_material=np.max((np.concatenate(fingers)+target)[:,0])
    assert rear_material>=source[0]+.002
    assert rear_material<=-.097
    assert np.min((palm+target)[:, 2]) >= .927
    assert goal+.05 <= -.089
    assert goal-.015 >= -.085-.094+.006
    assert target[2]+np.min(np.concatenate(fingers)[:, 2]) == pytest.approx(.869)
    assert source.tolist() == [-.106, .111, .861]


def test_ball_without_rear_material_corridor_is_rejected_before_entering_roof():
    fingers, palm = parts()
    for cloud in fingers:cloud[:, 0] *= 4
    with pytest.raises(MechanismExecutionError, match='roof-clear'):
        plan_upper_back_push([-.087, .111, .861], .015, fingers, palm, -.085, .924, .05, .094)


def test_nominal_tcp_may_lead_sphere_while_real_material_covers_its_upper_cap():
    fingers,palm=parts()
    for cloud in fingers:
        cloud[:,0]*=2.6
        cloud[:,2]=np.where(cloud[:,2]<0,-.009,.045)
    target,goal=plan_upper_back_push([-.106, .111, .861], .015,
        fingers,palm,-.085,.924,.066,.094)
    assert -.025<target[0]-(-.106)<0
    assert -.104<=target[0]+.026<=-.097
    assert target[2]-.009<.876


def test_roof_screen_uses_actual_sloping_palm_not_a_nonexistent_low_rear_corner():
    from itertools import product
    from videoicl_isaaclab.execution_design_e18_ball_roll import palm_roof_minimum_z
    # Palm low points are outside the cabinet; its inward portion is higher.
    palm=np.array([[x,y,z]for x,y in product([-.04,.1],[-.03,.03])
                   for z in ([.036,.09]if x<0 else[.10,.13])])
    low=palm_roof_minimum_z(palm,.026)
    assert low>.065
    assert palm[:,2].min()==pytest.approx(.036)


def test_palm_below_roof_or_front_wall_roll_are_rejected():
    fingers, palm = parts()
    palm[:, 2] -= .1
    with pytest.raises(MechanismExecutionError, match='palm'):
        plan_upper_back_push([-.106, .111, .861], .015, fingers, palm, -.085, .924, .05, .094)
    fingers, palm = parts()
    with pytest.raises(MechanismExecutionError, match='drawer floor'):
        plan_upper_back_push([-.106, .111, .861], .015, fingers, palm, -.085, .924, .05, .02)


def test_actual_native_palm_can_clear_roof_after_small_tilt():
    import json
    from pathlib import Path
    from scipy.spatial.transform import Rotation
    from itertools import product
    from videoicl_isaaclab.execution_design_e18_ball_roll import choose_push_orientation
    q=[.0055666517,.7099739891,-.7040544643,.0146190493]
    rotation=Rotation.from_quat([*q[1:],q[0]]).as_matrix()
    raw=json.loads((Path(__file__).parent/'data/e18-panda-native-palm-hull.json').read_text())
    palm=np.asarray(raw['vertices_tcp'])@rotation.T
    finger=np.array(list(product([-.0271585,.0259921],[-.0098738,.0118604],[-.0091793,.0454449])))
    opened=[finger+np.array([sign*.04,0,0])for sign in (-1,1)]
    turn,degrees,target,goal=choose_push_orientation([-.1068106,.1114837,.8611477],.015,
        [finger,finger],palm,-.0854082,.9241827,opened,.0940831)
    assert degrees==-10.
    transformed=finger@turn.T
    assert (transformed+target)[:,0].max()<=-.0884082+1e-9
    assert (transformed+target)[:,2].min()<.8751477
    assert goal<-.15


def test_stuck_public_waypoint_stops_after_three_actions():
    from videoicl_isaaclab.execution_design_e18_ball_roll import move_checked
    class Worker:
        min_mm=1.
        actions=0
        def tip(self,side):return np.zeros(3)
        def act(self,*a,**kw):self.actions+=1
    w=Worker()
    with pytest.raises(MechanismExecutionError,match='three attempts'):
        move_checked(w,'left',[.05,0,0])
    assert w.actions==3


def test_long_descent_corrects_transverse_controller_drift_before_roof_contact():
    from videoicl_isaaclab.execution_design_e18_ball_roll import move_checked
    class Worker:
        min_mm=1.
        position=np.array([0.,0.,.1])
        maximum_x=0.
        def tip(self,side):return self.position.copy()
        def act(self,side,token,mm):
            if token=='DOWN':self.position+=np.array([.002,0.,-mm/1000])
            elif token=='BACK':self.position[0]-=mm/1000
            elif token=='FWD':self.position[0]+=mm/1000
            self.maximum_x=max(self.maximum_x,self.position[0])
    w=Worker();move_checked(w,'left',[0.,0.,0.],tolerance=.005)
    assert w.position[2]<=.005
    assert w.maximum_x<.008
