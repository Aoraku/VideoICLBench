import numpy as np
import pytest
from types import SimpleNamespace
from videoicl_isaaclab.execution_design_e13_shortwidth import downward_shortwidth_rotation,camera_band_tcp


def test_shortwidth_jaws_cross_original_local_y_with_downward_toes_and_actual_table_band():
    a=np.deg2rad(-56.2);r=np.array([[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1]])
    target=downward_shortwidth_rotation(r);np.testing.assert_allclose(target[:,1],r[:,1]);np.testing.assert_allclose(target[:,2],[0,0,-1]);assert np.linalg.det(target)==pytest.approx(1.)
    pos=np.array([-.02,-.227,.80474]);tip=np.array([-.25,-.3,.98]);bodies={'finger':np.array([[0,0,.971],[0,0,1.04]])}
    point=camera_band_tcp(pos,r,tip,bodies,.8)
    assert (r.T@(point-pos))[0]==pytest.approx(.065)
    assert (r.T@(point-pos))[1]==pytest.approx(0.)
    assert (bodies['finger']-tip+point)[:,2].min()==pytest.approx(.8015)
    with pytest.raises(ValueError):downward_shortwidth_rotation(np.array([[1,0,0],[0,0,-1],[0,1,0]]))


def test_shortwidth_held_resume_skips_empty_route_and_native_grasp(monkeypatch):
    import videoicl_isaaclab.execution_design_e13_branch as base
    import videoicl_isaaclab.execution_design_e13_camera as camera
    import videoicl_isaaclab.execution_design_e13_camera_place as place
    import videoicl_isaaclab.execution_design_branch_geometry as geometry
    import videoicl_isaaclab.execution_design_e13_shortwidth as short
    calls=[];p=SimpleNamespace(c=SimpleNamespace(steps=1700),variant='A',snapshot=lambda:({'phone':dict(grasp=[False,True])},set()),require_held=lambda *a:calls.append('held'))
    monkeypatch.setattr(base,'_policy',lambda *a:p)
    monkeypatch.setattr(camera,'AcquisitionGeometry',lambda *a,**kw:SimpleNamespace())
    monkeypatch.setattr(geometry,'install_public_guard',lambda *a:None)
    monkeypatch.setattr(camera,'_grasp_lift',lambda *a:pytest.fail('Repeated grasp'))
    monkeypatch.setattr(camera,'_turn_empty',lambda *a:pytest.fail('Repeated empty path'))
    monkeypatch.setattr(camera,'_finish_lift',lambda *a:calls.append('lift'))
    monkeypatch.setattr(place,'run_branch',lambda *a:dict(local_completed=True,whole_task_score=None))
    c=dict(camera_end_strategy='actual_supported1337_right_camera_end_v1',shortwidth_phase='lift',shortwidth_source_table_min_z=.8,shortwidth_strategy='native1604_camera65_center_shortwidth_v1',camera_end_first_actual_hold_action=1699)
    result=short.run_branch(None,c,'shortwidth_complete_supported')
    assert calls==['held','lift']and result['local_completed']and result['whole_task_score']is None


def test_final_descent_centers_before_lowering_and_rechecks_drift(monkeypatch):
    import itertools
    import videoicl_isaaclab.execution_design_e13_camera as camera
    import videoicl_isaaclab.execution_design_e33_grasp as source
    import videoicl_isaaclab.execution_design_thin_edge as thin
    import videoicl_isaaclab.execution_design_e13_shortwidth as short
    pos=np.array([.0665,.0009,.823]);phone=np.array(list(itertools.product([-.075,.075],[-.037776,.036986],[.8,.81014])));actions=[]
    monkeypatch.setattr(camera,'closed_phone_obstacle',lambda p:[phone])
    monkeypatch.setattr(thin,'table_bounds_task',lambda *a:dict(top=.8))
    monkeypatch.setattr(source,'actual_mesh',lambda *a:np.array([[pos[0],pos[1],pos[2]-.009],[pos[0],pos[1],pos[2]+.04]]))
    def act(side,token,mm):
        assert len(actions)<40
        if token=='DOWN':
            assert max(abs(pos[:2]-[.065,-.000395]))<=.0003
            pos[2]-=mm/1000;pos[:2]+=[.00005,-.00002]
        else:
            k,sign={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1)}[token];pos[k]+=sign*mm/1000
        actions.append(token)
    p=SimpleNamespace(a=SimpleNamespace(scene=SimpleNamespace(embodiment=SimpleNamespace(fingers=['a','b']))),snapshot=lambda:({'phone':dict(pos=np.array([0.,0.,.8047]),mat=np.eye(3))},set()),tip=lambda s:pos.copy(),min_mm=.5,act=act)
    context={};short.descend_centered_shortwidth(p,context,lambda:None)
    assert actions[:2]==['BACK','RIGHT']
    assert .8003<pos[2]-.009<=.8023
    assert context['shortwidth_actual_centered_material_local'][1]==pytest.approx(-.000395)


def test_shortwidth_closure_does_not_lift_on_first_transient_bilateral_contact(monkeypatch):
    import videoicl_isaaclab.execution_design_e13_shortwidth as short
    import videoicl_isaaclab.execution_design_e13_camera as camera
    readings=iter([True,False,True,True,True]);actions=[];lift=[]
    p=SimpleNamespace(c=SimpleNamespace(steps=100),act=lambda *a:actions.append(a),held=lambda *a:next(readings),snapshot=lambda:({'phone':dict(mat=np.eye(3),pos=np.zeros(3))},set()),tip=lambda s:np.array([.065,0,.005]))
    right=SimpleNamespace(check=lambda **kw:None,mode='empty')
    monkeypatch.setattr(camera,'_finish_lift',lambda *a:lift.append('after_closure'))
    c={};short.establish_shortwidth_hold(p,c,right,'shortwidth_complete_supported',100)
    assert len(actions)==5 and all(a==('right','GRASP')for a in actions)
    assert lift==['after_closure']and c['shortwidth_consecutive_native_grasp_receipts']==3
