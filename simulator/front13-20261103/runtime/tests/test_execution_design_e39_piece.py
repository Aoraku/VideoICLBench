from itertools import product
from types import SimpleNamespace

import numpy as np
import pytest

from videoicl_isaaclab.execution_design_e39_piece import release_lift,cradle_mass_offset
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def box(lo,hi):return np.asarray(list(product(*zip(lo,hi))))


def test_measured_c_wall_wedge_requires_release_above_tab_not_empty_up():
    # C1093: both fingers still pressed on tray walls after RELEASE; the first
    # UP lifted the tray 8.37mm. A hover clears even the near raised tab.
    finger=box([-.065,-.009,.995],[.065,.009,1.035])
    tab=box([-.065,-.028,.818],[-.045,.028,.865])
    wall=box([.057,-.185,.800],[.065,.185,.836])
    lift=release_lift([finger],[tab,wall],[0,0,1.],[0,0,.825])
    assert lift==pytest.approx(.049)
    assert finger[:,2].min()+.825-1.+lift>=tab[:,2].max()+.004-1e-12


def test_only_parts_in_the_actual_hand_projection_set_release_height():
    finger=box([-.02,-.02,.995],[.02,.02,1.035])
    floor=box([-.065,-.185,.800],[.065,.185,.806])
    remote_tab=box([-.065,.12,.818],[-.045,.16,.865])
    assert release_lift([finger],[floor,remote_tab],[0,0,1.],[0,0,.825])==0


def test_larger_opening_prediction_is_included_even_if_closed_mesh_fits():
    closed=box([-.02,-.01,.995],[.02,.01,1.035])
    opened=box([-.065,-.01,.993],[.065,.01,1.035])
    wall=box([.057,-.185,.8],[.065,.185,.836])
    assert release_lift([closed],[wall],[0,0,1.],[0,0,.825])==0
    assert release_lift([closed,opened],[wall],[0,0,1.],[0,0,.825])==pytest.approx(.022)


def test_unreviewed_large_fall_is_rejected():
    finger=box([-.065,-.01,.9],[.065,.01,1.035])
    wall=box([.057,-.185,.8],[.065,.185,.836])
    with pytest.raises(ToolExecutionError,match='unreviewed fall'):
        release_lift([finger],[wall],[0,0,1.],[0,0,.825])


def test_native_T_com_is_centred_on_narrow_cradle_without_asset_changes():
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    com=[-.0065,0,0]
    assert cradle_mass_offset(com,np.eye(3))==pytest.approx(.0065)
    assert abs(cradle_mass_offset(com,_axis_rotation([0,0,1],np.pi/2)))<1e-10
    assert abs(cradle_mass_offset(com,np.eye(3)))<.015
    with pytest.raises(ToolExecutionError,match='preserved-position'):
        cradle_mass_offset([-.03,0,0],np.eye(3))


def test_blue_checkpoint_continues_black_package_delivery_without_blue_pickup(monkeypatch):
    from videoicl_isaaclab import execution_design_e39_piece as module
    calls=[]
    class Policy:
        variant='C';clearance=1.15;d={'target_members':['red_active','blue_active','black_active']}
        def ref(self,n):return {'actor':n}
        def require_held(self,r,s):calls.append(('held',r['actor'],s))
        def frame(self,r):return np.zeros(3),np.eye(3)
        def measured_transport_clearance(self,*a):return 1.
        def bottom_local(self,n):return np.array([0,0,-.004])
        def place(self,n,*a):calls.append(('place',n))
        def package_stage(self):calls.append('package')
        def deliver(self):calls.append('deliver')
    monkeypatch.setattr(module,'place_held_piece',lambda *a,**k:calls.append('released-held-blue'))
    monkeypatch.setattr(module,'require_local_piece_poses',lambda p:None)
    options={'local_targets':{n:[0,0,.007]for n in Policy.d['target_members']},
             'expected_yaws':{n:0 for n in Policy.d['target_members']},
             'home_tips':{'left':[-.19,.30,.90],'right':[-.19,-.30,.90]}}
    p=Policy();module.complete_blue_suffix(p,options)
    assert calls==[('held','blue_active','right'),'released-held-blue',('place','black_active'),'package','deliver']
    assert p.clearance==1.15


def test_immediate_native_pose_guard_rejects_real_tip_without_waiting():
    from types import SimpleNamespace
    from videoicl_isaaclab.execution_design_e39_piece import require_local_piece_poses
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    state={'work_tray':dict(mat=np.eye(3)),'blue':dict(mat=_axis_rotation([0,1,0],np.deg2rad(39.373)),grasp=[False,False])}
    contacts={frozenset(('blue','work_tray'))}
    p=SimpleNamespace(d={'local_order':{'actor':'work_tray','expected_yaws':{'blue':0.}}},snapshot=lambda:(state,contacts))
    with pytest.raises(ToolExecutionError,match='unchanged native orientation'):
        require_local_piece_poses(p)
    state['blue']['mat']=_axis_rotation([0,1,0],np.deg2rad(3.))
    require_local_piece_poses(p)
    contacts.clear()
    with pytest.raises(ToolExecutionError,match='actual released tray support'):
        require_local_piece_poses(p)


def test_measured_a_181_functional_release_does_not_chase_extra_xy_precision():
    from pathlib import Path
    import json
    from types import SimpleNamespace
    from videoicl_isaaclab.execution_design_e39_piece import actual_release_ready
    from videoicl_isaaclab.layout import rotation_matrix
    f=json.loads((Path(__file__).parent/'fixtures/e39_a_measured_release_181.json').read_text())
    state={n:dict(pos=np.array(q[:3]),mat=rotation_matrix(q[3:7]))for n,q in f['roots'].items()}
    point=lambda:state['black_active']['pos']+state['black_active']['mat']@np.array([0,0,-.004875])
    view=SimpleNamespace(get_coms=lambda:np.array([[-.0065,0,0,1,0,0,0]]))
    p=SimpleNamespace(objects=f['objects'],d={'geometry_tolerance_m':.003},point=lambda control:point(),
        snapshot=lambda:(state,set()),frame=lambda ref:(state[ref['actor']]['pos'],state[ref['actor']]['mat']),
        a=SimpleNamespace(scene=SimpleNamespace(objects={'black_active':SimpleNamespace(root_physx_view=view)})))
    meshes=[np.array([[-.16,-.13,.90],[-.13,-.10,.92]])]
    assert actual_release_ready(p,'black_active',{},f['target'],f['release'],meshes,'work_tray')
    state['black_active']['pos'][0]+=.006
    assert not actual_release_ready(p,'black_active',{},f['target'],f['release'],meshes,'work_tray')
    state['black_active']['pos'][0]-=.006
    state['black_active']['pos'][2]+=.010
    assert not actual_release_ready(p,'black_active',{},f['target'],f['release'],meshes,'work_tray')
