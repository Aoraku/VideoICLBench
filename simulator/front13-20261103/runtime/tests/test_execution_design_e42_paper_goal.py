from types import SimpleNamespace
import numpy as np
from videoicl_isaaclab.execution_design_e42_paper_goal import reached


def policy(x,y):
    ball=dict(pos=np.array([x,y,.812]),mat=np.eye(3),grasp=[False,False]);contacts={frozenset(('ball','table'))}
    p=SimpleNamespace(task='E42',index=0,a=SimpleNamespace(control_report={'engineering_reference_only':True}),
        spec=dict(id='E42',execution_design=dict(revision='embodied50-execution-v3-20261102'),
            zones=[dict(id='circle',marker=0,shape='circle',xy=[.14,.13],half_size=[.042,.042])],
            objects=[dict(id='ball',kind='sphere',size=[.01316]*3)]),snapshot=lambda:({'ball':ball},contacts))
    return p,ball,contacts


def test_native_measured_a_paper_projection_does_not_require_an_extra12mm_centre():
    p,_,_=policy(.1285982728,.1031855494)
    assert reached(p,'ball')


def test_full_sphere_and_real_support_and_release_remain_required():
    p,ball,contacts=policy(.14,.103)
    assert not reached(p,'ball')  # breaches the explicit2mm paper inset
    ball['pos'][:2]=[.14,.13];assert reached(p,'ball')
    contacts.clear();assert not reached(p,'ball')
    contacts.add(frozenset(('ball','table')));ball['grasp']=[False,True]
    assert not reached(p,'ball')
    ball['grasp']=[False,False];contacts.add(frozenset(('ball','left_finger1')))
    assert not reached(p,'ball')
