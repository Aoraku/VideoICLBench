import itertools
import numpy as np
from videoicl_isaaclab.execution_design_contact_retreat import convex_exit_certificate,expanded_contact_facets
from videoicl_isaaclab.execution_design_branch_geometry import swept_pose_clearance


def box(low,high):return np.array(list(itertools.product(*zip(low,high))))


def test_actual_initial_contact_can_exit_without_increasing_penetration():
    phone=box([-.075,-.037,-.005],[.075,.037,.005]);finger=box([.0748,-.01,-.003],[.10,.01,.003])
    c=convex_exit_certificate(finger,phone,[1,0,0])
    assert c['expanded_translation_penetration_m']>0
    assert c['monotone_for_entire_translation']
    distance=c['required_exit_distance_m'];assert 0<distance<.005
    moved=finger+[distance,0,0]
    swept_pose_clearance({'finger':moved},[0,0,0],[0,0,0],np.eye(3),{'phone':[phone]},-.1)
    values=[convex_exit_certificate(finger+[t,0,0],phone,[1,0,0])['expanded_translation_penetration_m']for t in np.linspace(0,distance,5)]
    assert np.all(np.diff(values)<=1e-8)


def test_moving_deeper_is_rejected_and_tangent_exit_keeps_depth_nonincreasing():
    phone=box([-.075,-.037,-.005],[.075,.037,.005]);finger=box([.0748,-.01,-.003],[.10,.01,.003]);facets=expanded_contact_facets(finger,phone)
    assert not convex_exit_certificate(finger,phone,[-1,0,0],facets=facets)['monotone_for_entire_translation']
    tangent=convex_exit_certificate(finger,phone,[0,0,1],facets=facets)
    assert tangent['monotone_for_entire_translation']
    assert 0<tangent['required_exit_distance_m']<.02


def test_actual_supported_phone_motion_recomputes_exit_beyond_initial_static_endpoint(monkeypatch,tmp_path):
    from types import SimpleNamespace
    import videoicl_isaaclab.execution_design_contact_retreat as retreat
    import videoicl_isaaclab.execution_design_e33_grasp as source
    import videoicl_isaaclab.execution_design_e13_release as opening
    import videoicl_isaaclab.execution_design_thin_edge as thin
    shift=np.zeros(3);phone_shift=np.zeros(3);actions=[]
    phone=box([-.01,-.01,-.01],[.01,.01,.01]);base=dict(panda_hand=box([.06,-.02,.02],[.09,.02,.04]),panda_leftfinger=box([.0098,-.004,-.004],[.025,.004,.004]),panda_rightfinger=box([.0098,.04,-.004],[.025,.05,.004]))
    def mesh(a,side,name):return base.get(name,base['panda_hand'])+shift if side=='right'else base['panda_hand']+[2,2,2]
    monkeypatch.setattr(source,'actual_mesh',mesh)
    monkeypatch.setattr(opening,'actual_opening_bodies',lambda p,s:{n:mesh(p.a,s,n)for n in base})
    monkeypatch.setattr(thin,'table_bounds_task',lambda *a:dict(top=-.2))
    p=SimpleNamespace(a=SimpleNamespace(out=tmp_path,scene=SimpleNamespace(embodiment=SimpleNamespace(fingers=['panda_leftfinger','panda_rightfinger']))),s=dict(stand='stand'),c=SimpleNamespace(steps=1559),min_mm=.5,max_mm=12.,tip=lambda s:shift.copy(),contact=lambda *a:True,snapshot=lambda:({'phone':dict(grasp=[False,False])},{frozenset(('phone','right_finger1'))}))
    def act(side,token,mm=1.,**kw):
        assert token=='FWD';shift[0]+=mm/1000
        if not actions:phone_shift[0]+=.0025
        actions.append(mm);p.c.steps+=1
    p.act=act;context=dict(branch_params=dict(phone_contact_retreat_public_axis='FWD'))
    result=retreat.retreat_phone_contact(p,context,lambda:[phone+phone_shift])
    assert result['fully_separated_by_original_guard']and len(actions)>=2
    assert shift[0]>context['phone_contact_retreat_plan']['distance_m']+.001


def test_rotating_contact_padding_does_not_become_fake_penetration_but_real_point2mm_does(monkeypatch):
    from types import SimpleNamespace
    import pytest
    import videoicl_isaaclab.execution_design_contact_retreat as retreat
    import videoicl_isaaclab.execution_design_e33_grasp as source
    import videoicl_isaaclab.execution_design_e13_release as opening
    import videoicl_isaaclab.execution_design_thin_edge as thin
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    base=dict(panda_hand=box([.06,-.02,.02],[.09,.02,.04]),panda_leftfinger=box([.01,-.006,-.006],[.025,.006,.006]),panda_rightfinger=box([.01,.04,-.006],[.025,.05,.006]));phone=box([-.01,-.01,-.01],[.01,.01,.01]);parts=[phone.copy()]
    def mesh(a,s,n):return base.get(n,base['panda_hand']) if s=='right'else base['panda_hand']+[2,2,2]
    monkeypatch.setattr(source,'actual_mesh',mesh);monkeypatch.setattr(opening,'actual_opening_bodies',lambda p,s:base)
    monkeypatch.setattr(thin,'table_bounds_task',lambda *a:dict(top=-.2))
    p=SimpleNamespace(a=SimpleNamespace(scene=SimpleNamespace(embodiment=SimpleNamespace(fingers=['panda_leftfinger','panda_rightfinger']))),s=dict(stand='stand'),tip=lambda s:np.zeros(3),contact=lambda *a:True,snapshot=lambda:({'phone':dict(grasp=[False,False])},set()))
    g=retreat.ContactRetreatGeometry(p,'right','phone',['panda_leftfinger'],lambda:parts,np.array([1.,0.,0.]),{})
    first=g()['panda_leftfinger'];angle=np.deg2rad(20);r=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
    moved=phone@r.T;moved[:,0]+=.01-moved[:,0].max();parts[:]=[moved]
    second=g()['panda_leftfinger']
    assert second['expanded_translation_penetration_m']>first['expanded_translation_penetration_m']+.00001
    assert second['physical_contact_depth_m']<1e-10
    parts[0][:,0]+=.0002
    with pytest.raises(ToolExecutionError,match='clearly increased'):g()
