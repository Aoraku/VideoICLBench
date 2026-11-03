import numpy as np
import pytest
from videoicl_isaaclab.execution_design_drawer_ik_probe import forward_at_delta,solve_candidates
from videoicl_isaaclab.author_orientation import _axis_angle

def fixture():
 p=np.array([.3,.2,.5]);rng=np.random.default_rng(1);axes=rng.normal(size=(3,7));axes/=np.linalg.norm(axes,axis=0);pivots=rng.normal(size=(3,7))*.2
 jac=np.vstack((np.stack([np.cross(axes[:,i],p-pivots[:,i])for i in range(7)],axis=1),axes))
 return p,np.eye(3),jac

def test_native_screw_axis_forward_reproduces_jacobian():
 p,r,j=fixture()
 for index in range(7):
  delta=np.zeros(7);delta[index]=1e-6;position,rotation=forward_at_delta(p,r,j,delta);axis,angle=_axis_angle(rotation@r.T)
  np.testing.assert_allclose((position-p)/1e-6,j[:3,index],atol=1e-6)
  np.testing.assert_allclose(axis*angle/1e-6,j[3:,index],atol=.001)

def test_candidate_solver_keeps_true_limits_and_does_not_mutate_inputs():
 p,r,j=fixture();q=np.zeros(7);limits=np.array([[-2.,2.]]*7);saved=[x.copy()for x in(p,r,j,q,limits)]
 result=solve_candidates(p,r,j,q,limits,[r])
 assert result[0]['kinematically_reachable'] and result[0]['position_error_m']<.001
 assert np.all(np.abs(result[0]['candidate_joints_rad'])<=2.)
 for a,b in zip((p,r,j,q,limits),saved):np.testing.assert_array_equal(a,b)

def test_invalid_actual_axes_are_rejected():
 p,r,j=fixture();j[3:,0]=0
 with pytest.raises(AssertionError):solve_candidates(p,r,j,np.zeros(7),np.array([[-2.,2.]]*7),[r])


def test_physical_grasp_target_uses_measured_finger_axes_not_nominal_euler():
    from types import SimpleNamespace
    from videoicl_isaaclab.execution_design_drawer_ik_probe import physical_grasp_targets
    class Tensor:
        def __init__(self,x):self.x=np.asarray(x)
        def __getitem__(self,key):return Tensor(self.x[key])
        def detach(self):return self
        def cpu(self):return self
        def numpy(self):return self.x
    pos=Tensor([[[0.,0.,0.],[-.02,0.,.05],[.02,0.,.05]]])
    robot=SimpleNamespace(data=SimpleNamespace(body_pos_w=pos),find_bodies=lambda name:([{'one':1,'two':2}[name]],None))
    author=SimpleNamespace(scene=SimpleNamespace(robots={'right':robot},embodiment=SimpleNamespace(fingers=['one','two']),layout=SimpleNamespace(task_rotation=np.eye(3))),tcp_rotation_task=lambda side:np.eye(3))
    controller=SimpleNamespace(ids={'right':([],[],0)})
    targets=physical_grasp_targets(author,controller,'right',[-1.,0.,0.],pinch_axis=[0.,0.,1.])
    for target in targets:
        np.testing.assert_allclose(target@[0.,0.,1.],[1.,0.,0.],atol=1e-7)
        assert abs(float(np.dot(target@[-1.,0.,0.],[0.,0.,1.])))==pytest.approx(1.)
    np.testing.assert_allclose(targets[0]@[-1.,0.,0.],-targets[1]@[-1.,0.,0.])

def test_action_dynamics_records_tracking_error_without_state_write(tmp_path):
    from types import SimpleNamespace
    import json
    from videoicl_isaaclab.execution_design_drawer_ik_probe import record_action_dynamics
    class Tensor:
        def __init__(self,x):self.x=np.asarray(x)
        def __getitem__(self,key):return Tensor(self.x[key])
        def detach(self):return self
        def cpu(self):return self
        def numpy(self):return self.x
    data=SimpleNamespace(joint_pos=Tensor([[.1,.2]]),joint_pos_target=Tensor([[.12,.18]]),body_pos_w=Tensor([[[1.,2.,3.]]]))
    robot=SimpleNamespace(data=data,body_names=['palm'])
    author=SimpleNamespace(scene=SimpleNamespace(robots={'left':robot},world_to_task=lambda x:x-[1,1,1]),out=tmp_path,stage='approach')
    controller=SimpleNamespace(ids={'left':([0,1],[],0)},steps=3,action_feedback=lambda:{'status':'partial'})
    record_action_dynamics(author,controller,'left','DOWN')
    row=json.loads((tmp_path/'drawer-action-dynamics.private.jsonl').read_text())
    np.testing.assert_allclose(row['joint_tracking_error_rad'],[.02,-.02])
    np.testing.assert_allclose(row['body_origins_task']['palm'],[0.,1.,2.])
    np.testing.assert_array_equal(data.joint_pos.x,[[.1,.2]])

def test_drawer_hand_prefers_actual_joint_margin_over_nearest_solution(monkeypatch):
    from types import SimpleNamespace
    from videoicl_isaaclab.realworld_mechanism_expert import _Author
    from videoicl_isaaclab import execution_design_drawers as drawers
    from videoicl_isaaclab import execution_design_drawer_ik_probe as probe
    monkeypatch.setenv('VIC_ENGINEERING_DRAWER_IK_PROBE','1')
    monkeypatch.setattr(drawers,'initial_displacements',lambda spec:{'lower':.009,'upper':.011})
    monkeypatch.setattr(probe,'physical_grasp_targets',lambda *args:[np.eye(3)])
    def measured(author,controller,side,targets):
        return [dict(kinematically_reachable=True,minimum_joint_margin_rad=.3 if side=='left' else .1,joint_distance_rad=2. if side=='left' else 1.)]
    monkeypatch.setattr(probe,'inspect',measured)
    a=_Author.__new__(_Author);a.spec={};a.a=SimpleNamespace();a.c=SimpleNamespace()
    a.axis=lambda role:np.array([-1.,0,0]);a.drawer_jaw_axis=lambda role:np.array([0.,0,1.]);a.point=lambda role:np.zeros(3)
    assert a.choose_drawer_hand('lower')=='left'

def test_lower_oblique_grasp_has_source_handle_opening_margin(monkeypatch):
    from videoicl_isaaclab.realworld_mechanism_expert import _Author
    from videoicl_isaaclab import execution_design_drawers as drawers
    monkeypatch.setenv('VIC_ENGINEERING_DRAWER_IK_PROBE','1')
    monkeypatch.setattr(drawers,'initial_displacements',lambda spec:{'lower':.009,'upper':.011})
    a=_Author.__new__(_Author);a.spec={};a.axis=lambda role:np.array([-1.,0.,0.]);a.drawer_jaw_axis=lambda role:np.array([0.,0.,1.])
    outward,jaw=a.engineering_drawer_grasp_axes('lower')
    assert np.dot(outward,jaw)==pytest.approx(0.,abs=1e-10)
    # Exact source USD handle extents in task X/Y/Z. Oblique jaws must still
    # admit the complete 97.938mm bar within the unmodified 80mm opening.
    assert abs(jaw)@np.array([.002608,.097938,.002742])<.074
    np.testing.assert_allclose(a.engineering_drawer_grasp_axes('upper')[1],[0,0,1])
    monkeypatch.delenv('VIC_ENGINEERING_DRAWER_IK_PROBE')
    np.testing.assert_allclose(a.engineering_drawer_grasp_axes('lower')[1],[0,0,1])

def test_public_approach_finishes_at_the_checked_capture_target(monkeypatch):
    from types import SimpleNamespace
    from videoicl_isaaclab.realworld_mechanism_expert import _Author
    from videoicl_isaaclab import execution_design_drawers as drawers
    from videoicl_isaaclab import execution_design_drawer_ik_probe as probe
    monkeypatch.setenv('VIC_ENGINEERING_DRAWER_IK_PROBE','1')
    monkeypatch.setattr(drawers,'initial_displacements',lambda spec:{'lower':.009,'upper':.011})
    checked=[]
    def inspect(author,controller,side,targets):
        checked.extend(np.asarray(x['position']).copy()for x in targets)
        return [dict(kinematically_reachable=True)for x in targets]
    monkeypatch.setattr(probe,'inspect',inspect)
    a=_Author.__new__(_Author);a.task='E30';a.spec={};a.points={'lower':{}};a.c=SimpleNamespace()
    a.a=SimpleNamespace(scene=SimpleNamespace(embodiment=SimpleNamespace(config={})),tcp_rotation_task=lambda side:np.eye(3))
    a.point=lambda role:np.array([0.,0.,.88]);a.axis=lambda role:np.array([-1.,0,0]);a.tip=lambda side:np.array([-.2,0.,1.1]);a.front_corridor=lambda:True
    executed=[];a.move=lambda side,target,**kwargs:executed.append(np.asarray(target).copy())
    a.approach('lower','left')
    np.testing.assert_allclose(executed[-1],[-.007,0.,.88])
    np.testing.assert_allclose(executed[-1],checked[-1])
    np.testing.assert_allclose(a.point('lower'),[0.,0.,.88])


def test_inspect_records_current_rotation_separately_from_candidate(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import json
    from videoicl_isaaclab import execution_design_drawer_ik_probe as probe
    class Tensor:
        def __init__(self,x):self.x=np.asarray(x)
        def __getitem__(self,key):return Tensor(self.x[key])
        def detach(self):return self
        def cpu(self):return self
        def numpy(self):return self.x
    p,_,j=fixture();actual=np.array([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
    robot=SimpleNamespace(is_fixed_base=True,
        root_physx_view=SimpleNamespace(get_jacobians=lambda:Tensor(j[None,None]),get_coms=lambda:Tensor(np.zeros((1,2,7)))),
        data=SimpleNamespace(body_quat_w=Tensor([[[1.,0.,0.,0.],[1.,0.,0.,0.]]]),
          body_pos_w=Tensor(np.zeros((1,2,3))),
          joint_pos=Tensor([np.zeros(7)]),joint_pos_limits=Tensor([[[-2.,2.]]*7])))
    a=SimpleNamespace(scene=SimpleNamespace(robots={'left':robot},embodiment=SimpleNamespace(tcp=[0.,0.,0.]),
        layout=SimpleNamespace(task_rotation=np.eye(3))),tip=lambda side:p,tcp_rotation_task=lambda side:actual,out=tmp_path)
    c=SimpleNamespace(ids={'left':(list(range(7)),[],1)},steps=7)
    seen=[]
    def solve(position,rotation,jacobian,q,limits,targets):
        seen.append(rotation.copy());return [{'target_rotation':np.eye(3).tolist(),'kinematically_reachable':False}]
    monkeypatch.setattr(probe,'solve_candidates',solve)
    result=probe.inspect(a,c,'left',[np.eye(3)])
    row=json.loads((tmp_path/'drawer-ik-candidates.private.jsonl').read_text())
    np.testing.assert_array_equal(row['rotation_task'],actual)
    np.testing.assert_array_equal(seen[0],actual)
    assert row['rotation_task']!=row['candidates'][0]['target_rotation']
    assert row['candidates']==result and not row['actuation_performed'] and not row['collision_verified']
