from pathlib import Path
from types import SimpleNamespace
import itertools
import numpy as np
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_e28_source import plate_destination


def test_both_real_c_food_footprints_are_separate_inside_original_plate_core():
    runtime=Path(__file__).parents[1]
    bindings=runtime.parent/'verification/task-design-revision-20261102/half26_50-matrix/bindings-I.private.json'
    spec=load('E28','C',4201,bindings,verify_files=False)
    position=np.array([.04,.15,.816]);angle=.6
    rotation=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
    p=SimpleNamespace(spec=spec,s=spec['semantic'],a=SimpleNamespace(control_report={'engineering_reference_only':True}),snapshot=lambda:({'plate':{'pos':position,'mat':rotation}},set()))
    objects={o['id']:o for o in spec['objects']};local=[]
    for i,name in enumerate(('rectangle_food','round_food')):
        target=plate_destination(p,name,i,2)
        center=rotation.T@(target-position);half=np.asarray(objects[name]['size'])[:2]
        local.append((center,half))
        for sign in itertools.product((-1,1),repeat=2):
            corner=center[:2]+half*np.asarray(sign)
            assert np.linalg.norm(corner)<min(spec['semantic']['containers']['plate']['upper'][:2])
    assert np.linalg.norm(local[0][0][:2]-local[1][0][:2])>sum(np.linalg.norm(half)for _,half in local)
