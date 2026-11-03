"""Containment is invariant under a common rigid world transform."""
from copy import deepcopy
import itertools
import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from videoicl_isaaclab.realworld_native_evidence import NativeTaskEvaluator


def evaluator(task,container_rotation,cargo_rotation,offset,kind='box'):
    ev=object.__new__(NativeTaskEvaluator)
    ev.task=task;ev.source_cavity_walls={}
    ev.semantic={'containers':{'box':{'object':'container','lower':[-.05,-.025,-.03],'upper':[.05,.025,.03]}}}
    ev.objects={'container':{'size':[.06,.035,.04]},'cargo':{'size':[.04,.012,.015],
        'kind':kind,'local_bounds_center':[.003,-.002,.001]}}
    origin=np.array([.4,-.3,1.2])
    ev.state={'container':{'pos':origin,'mat':container_rotation,'grasp':[False,False]},
              'cargo':{'pos':origin+container_rotation@np.asarray(offset)-cargo_rotation@np.asarray(ev.objects['cargo']['local_bounds_center']),
                       'mat':cargo_rotation,'grasp':[False,False]}}
    ev.contacts={frozenset(('container','cargo'))}
    return ev

@pytest.mark.parametrize('task',['E16','E33','E47'])
@pytest.mark.parametrize('angles',[(0,0,45),(32,-17,64),(-43,51,-29)])
def test_common_rotation_preserves_box_containment_and_bounds_center(task,angles):
    r=Rotation.from_euler('xyz',angles,degrees=True).as_matrix()
    aligned=evaluator(task,np.eye(3),np.eye(3),[0,0,0])
    rotated=evaluator(task,r,r,[0,0,0])
    assert aligned.container_members('box',['cargo'])==rotated.container_members('box',['cargo'])==(['cargo'],['cargo'])

@pytest.mark.parametrize('offset',[[.02,0,0],[-.02,0,0],[0,.025,0],[0,0,.025]])
def test_true_boundary_crossing_remains_rejected_under_rotation(offset):
    for angles in [(0,0,0),(30,45,70)]:
        r=Rotation.from_euler('xyz',angles,degrees=True).as_matrix()
        assert evaluator('E47',r,r,offset).container_members('box',['cargo'])==([],[])


def test_relative_rotation_agrees_with_all_eight_transformed_corners():
    c=Rotation.from_euler('xyz',[17,28,43],degrees=True).as_matrix()
    relative=Rotation.from_euler('z',25,degrees=True).as_matrix();r=c@relative
    ev=evaluator('E16',c,r,[0,0,0]);half=np.array(ev.objects['cargo']['size'])
    corners=np.asarray(list(itertools.product((-1,1),repeat=3)))*half
    expected=bool(np.all((corners@relative.T).min(0)>=np.array([-.05,-.025,-.03])-.003)
                  and np.all((corners@relative.T).max(0)<=np.array([.05,.025,.03])+.003))
    assert bool(ev.container_members('box',['cargo'])[0])==expected


def test_e36_sphere_radius_does_not_change_with_orientation():
    for angles in [(0,0,0),(30,45,70)]:
        c=Rotation.from_euler('xyz',angles,degrees=True).as_matrix()
        r=Rotation.from_euler('xyz',[67,-12,40],degrees=True).as_matrix()
        ev=evaluator('E36',c,r,[0,0,0],kind='sphere');ev.objects['cargo']['size']=[.02,.02,.02]
        assert ev.container_members('box',['cargo'])==(['cargo'],['cargo'])
        ev.state['cargo']['pos']+=c@np.array([0,.02,0])
        assert ev.container_members('box',['cargo'])==([],[])
