from itertools import product
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e37_blade import section_edges,predicted_section
from videoicl_isaaclab.execution_design_e37_blade import Blade
from types import SimpleNamespace as N


def shape(thickness=.002,tip=.108):
    return np.array(list(product((-.05,tip),(-thickness/2,thickness/2),(-.003,.003))))


def section(points):
    rotation=np.array([[0.,0.,-1.],[0.,-1.,0.],[-1.,0.,0.]])
    tip=np.array([.107,0.,0.]);actual_tip=np.array([0.,.0003,.03])
    return predicted_section(section_edges([points]),actual_tip-rotation@tip,
        rotation,tip,np.zeros(3),np.eye(3),.0018)


def test_native_convex_section_preserves_real_blade_width_and_axial_tip_extension():
    points=shape();before=points.copy();value=section(points)
    assert value['narrow_width_m']==pytest.approx(.002)
    assert value['center'][1]==pytest.approx(.0003)
    assert value['minimum_material_z_below_head_m']==pytest.approx(-.0028)
    assert np.array_equal(points,before)


def test_inflated_native_end_is_distinct_from_the_declared_semantic_tip():
    value=section(shape(tip=.112))
    assert value['minimum_material_z_below_head_m']<-.003


def test_wide_cooked_blade_cannot_be_mistaken_for_original_slot_fit():
    value=section(shape(thickness=.0032))
    assert value['narrow_width_m']>.0028


def test_actual_blade_can_remain_inserted_while_semantic_tip_is_above_head():
    blade=Blade.__new__(Blade);blade.actor='driver';blade.head=lambda:np.zeros(3)
    blade.frame=lambda:np.eye(3)
    blade.entry=dict(driver=dict(tip_local=[.1,0,0]),screw='screw',socket_radius=.0014,socket_depth=.003)
    blade.local=[np.array(list(product((.1006,.1008),(-.0008,.0008),(-.003,.003))))]
    body=dict(pos=[0,0,.1001],mat=[[0,0,1],[0,1,0],[-1,0,0]])
    blade.p=N(point=lambda ref:np.array([0,0,.0001]),snapshot=lambda:({'driver':body},set()),
        objects={'screw':{'size':[.018,.018,.026]}},c=N(evaluator=N(screw_measure=lambda entry:{'cos':1.})))
    value=blade.physical_groove_measurement()
    assert not value['semantic_tip_below_head']
    assert value['actual_source_blade_minimum_z_m']==pytest.approx(-.0007)
    assert value['physical_source_blade_engaged']
