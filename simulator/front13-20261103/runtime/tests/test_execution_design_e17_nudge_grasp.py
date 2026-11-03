"""Real rail-top and wall dimensions bound the closed pusher target."""
import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from test_execution_design_segments_e17_e20 import context
from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
from videoicl_isaaclab import execution_design_e17_nudge_grasp as nudge
from videoicl_isaaclab import execution_design_e17_base_grasp as base


def prepared(monkeypatch):
    a,state,contacts=context('E17','B');tip=np.array([0.,-.23,1.12]);a.tip=lambda side:tip.copy()
    state['packing_box']['pos']=np.array([0.,0.,.826]);state['packing_box']['mat']=np.eye(3)
    state['green_triangle']['pos']=np.array([.004,.1207,.8291]);state['green_triangle']['mat']=Rotation.from_euler('y',36.8,degrees=True).as_matrix();contacts.add(frozenset(('green_triangle','packing_box')))
    clouds=[]
    for low,high in[(-.026,-.0002),(.0002,.026)]:clouds.append(np.array([tip+[x,y,z]for x in(low,high)for y in(-.0106,.0106)for z in(-.009,.045)]))
    monkeypatch.setattr(base,'_finger_clouds',lambda p:clouds)
    return ExecutionDesignAuthor(a),state


def test_closed_pusher_stays_above_true_rail_and_inside_north_wall(monkeypatch):
    p,state=prepared(monkeypatch);before=state['green_triangle']['pos'].copy();target,evidence=nudge.pusher_target(p,'green_triangle')
    assert target[2]==pytest.approx(.8375) and evidence['rail_clear_pusher_toe_z_m']==pytest.approx(.0025)
    assert evidence['target_tcp_box_local_m'][1]+.0106<=.162-.0025+1e-12
    assert np.array_equal(state['green_triangle']['pos'],before)and not nudge.floor_flat(p,'green_triangle')


def test_flat_stop_depends_on_actual_floor_and_box_support(monkeypatch):
    p,state=prepared(monkeypatch);state['green_triangle']['pos']=np.array([.04,.08,.817]);state['green_triangle']['mat']=np.eye(3)
    assert nudge.floor_flat(p,'green_triangle')
    state['green_triangle']['pos'][2]+=.012
    assert not nudge.floor_flat(p,'green_triangle')


def test_measured_a99_low_north_tip_uses_real_positive_x_divider_gap(monkeypatch):
    p,state=prepared(monkeypatch)
    state['green_triangle']['pos']=np.array([.0236,.1265,.8205])
    state['green_triangle']['mat']=np.array([[.907945,.209785,.362803],[-.262473,.959530,.102030],[-.326716,-.187864,.926263]])
    target,evidence=nudge.pusher_target(p,'green_triangle',lower_north_edge=True)
    assert evidence['below_rail_north_edge']and evidence['rail_clear_pusher_toe_z_m']<0
    assert evidence['target_tcp_box_local_m'][0]-.026>=.003+.0025
    assert target[2]-.009>=.814+.0025
