from types import SimpleNamespace
from itertools import product
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e43_trigger import select_gate_hand_frame
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def test_gate_continuous_path_checks_final_travel_before_acquisition(tmp_path,monkeypatch):
    from videoicl_isaaclab import execution_design_drawer_ik_probe as ik
    from videoicl_isaaclab import execution_design_cutlery_grasp as grasp
    from videoicl_isaaclab import execution_design_jacobian_reference as jac
    from videoicl_isaaclab import execution_design_local_pose_path as local
    from videoicl_isaaclab import execution_design_e33_grasp as mesh
    from videoicl_isaaclab import execution_design_thin_edge as thin
    seen=[];oriented=[]
    monkeypatch.setattr(ik,'physical_grasp_targets',lambda *args,**kwargs:[np.eye(3)])
    measured=dict(position=[-.19,.3,.9445],rotation_task=np.eye(3).tolist(),jacobian=np.zeros((6,7)).tolist(),q=[0]*7,limits=[[-2,2]]*7)
    monkeypatch.setattr(jac,'capture',lambda *args:measured)
    def screen(*args,**kwargs):
        seen.extend(args[5]);return dict(feasible=False,rows=[dict(reason='joint_margin')])
    monkeypatch.setattr(local,'solve_local_pose_path',screen)
    monkeypatch.setattr(mesh,'actual_mesh',lambda a,side,name:np.array(list(product((-.01,.01),repeat=3)))+([-.19,.3,.95]if side=='left'else[.2,-.3,.95]))
    monkeypatch.setattr(thin,'table_bounds_task',lambda *args:dict(top=.8))
    monkeypatch.setattr(grasp,'orient',lambda *args:oriented.append(args))
    gate=dict(pos=np.array([.1,.035,.8545]),mat=np.eye(3),grasp=(False,False))
    tool=SimpleNamespace(a=SimpleNamespace(out=tmp_path,scene=SimpleNamespace(embodiment=SimpleNamespace(fingers=('f1','f2')))),c=object(),clearance=.94,max_mm=12.,spec=dict(objects=[dict(id='ball',size=[.01]*3)]),
        snapshot=lambda:({'gate':gate,'ball':dict(pos=np.array([.7,.7,.81]),mat=np.eye(3),grasp=(False,False))},set()),stage=lambda stage:None,
        move=lambda *args:None,tip=lambda side:np.array([-.19,.3,.9445]),point=lambda ref:np.array([.1,.035,.8745]))
    with pytest.raises(ToolExecutionError,match='complete measured travel'):
        select_gate_hand_frame(tool,{'actor':'gate'},'left',np.array([0.,-1.,0.]))
    assert len(seen)>40 and np.allclose(seen[-1]['position'],[.1,-.03,.8745],atol=.002)
    assert not oriented
def test_reviewed_native_sphere_does_not_gain_height_when_it_rolls():
    import numpy as np
    from videoicl_isaaclab import execution_design_e43_ball as source
    from videoicl_isaaclab.execution_design_e43_trigger import ball_extent
    obj=dict(id='ball',kind='sphere',source_asset=dict(root_env='VIC_FULL50_RIGID_ASSETS',relative_path='sphere_white.usda',sha256=source.SOURCE_SHA),
        size=[.013652941818490449,.014,.013857428965220098],mass=.008,static_friction=.8,dynamic_friction=.6,restitution=0)
    obj['reviewed_collision_settings']=source.settings_for(obj)
    # Recorded v19 ball matrix: rotating its empty bounding cube previously
    # rejected a real16.7mm gap before any gate action was issued.
    rotation=np.array([[.2186990380,-.4304413795,-.8757231832],[.4157503843,-.7708115578,.4827020764],[-.8827924132,-.4696486592,.0103803277]])
    assert np.allclose(ball_extent(obj,rotation),[.014]*3)
    old=np.abs(rotation)@obj['size'];assert old[2]>.018
    assert .8744921255-(.8437815881+ball_extent(obj,rotation)[2])>.012
