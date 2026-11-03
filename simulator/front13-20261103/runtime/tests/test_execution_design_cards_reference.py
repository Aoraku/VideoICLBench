import numpy as np
import pytest
from videoicl_isaaclab.execution_design_cards_reference import slot_placement


def test_three_true_lower_edges_fit_the_same_rotated_source_slot():
    holder=np.array([-.13,0.,.837]);rotation=np.array([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
    lo=np.array([-.045,-.0041,-.019]);hi=np.array([.045,.00065,-.011])
    half=np.array([.04415271966527,.0315,.000175]);layers=[]
    for rank in range(3):
        card_rotation,center=slot_placement(holder,rotation,lo,hi,half,rank)
        edge=np.array([[-half[0],sign*half[1],0.]for sign in(-1,1)])@card_rotation.T+center
        local=(edge-holder)@rotation
        assert np.all(local>=lo)and np.all(local<=hi)
        assert np.allclose(card_rotation.T@card_rotation,np.eye(3))
        assert np.linalg.det(card_rotation)==pytest.approx(1.)
        assert center[2]-edge[:,2].mean()==pytest.approx(half[0])
        layers.append(local[:,1].mean())
    assert np.diff(layers)==pytest.approx(np.repeat(2*half[2],2))


def test_slot_cannot_fit_arbitrarily_many_cards():
    with pytest.raises(ValueError,match='thickness'):
        slot_placement([0,0,0],np.eye(3),[-.045,-.0002,-.019],[.045,.0002,-.011],[.044,.0315,.000175],10)
