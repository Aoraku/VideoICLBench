from types import SimpleNamespace
import numpy as np
import json
from videoicl_isaaclab.execution_design_e13_functional import rough_orientation


def test_rough_ABC_direction_halfspaces_remain_distinct():
    sem=dict(camera_end_points={'phone':[1,0,0]},back_normals={'phone':[0,0,1]})
    # A upright; camera to+Z/back to-X.
    r=np.array([[0,0,-1],[0,1,0],[1,0,0.]])
    for variant,expected in [('A',True),('B',False),('C',False)]:
        p=SimpleNamespace(s=sem,variant=variant,snapshot=lambda:({'phone':dict(mat=r)},{}))
        assert rough_orientation(p)['correct']==expected
        json.dumps(rough_orientation(p))
    # Landscape camera-right must fail C even under coarse functional scope.
    r=np.array([[0,0,-1],[-1,0,0],[0,1,0.]])
    for variant,expected in [('A',False),('B',True),('C',False)]:
        p=SimpleNamespace(s=sem,variant=variant,snapshot=lambda:({'phone':dict(mat=r)},{}))
        assert rough_orientation(p)['correct']==expected
        json.dumps(rough_orientation(p))
