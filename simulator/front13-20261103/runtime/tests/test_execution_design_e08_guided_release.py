import itertools
from types import SimpleNamespace
import numpy as np
import pytest
import videoicl_isaaclab.execution_design_e08_branch as branch
import videoicl_isaaclab.execution_design_branch_geometry as geometry
import videoicl_isaaclab.execution_design_thin_edge as material
import videoicl_isaaclab.execution_design_e13_release as release
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def setup(monkeypatch,outside=False,landed=True):
    actions=[];state={'box':dict(pos=np.zeros(3),mat=np.eye(3)),'left_shoe':dict(pos=np.zeros(3),mat=np.eye(3),grasp=[True,False])}
    def act(side,token):actions.append(token);state['left_shoe']['grasp']=[False,False];p.c.steps+=1
    p=SimpleNamespace(a=SimpleNamespace(scene=None),c=SimpleNamespace(steps=712),index=0,s=dict(containers={'box':dict(lower=[-.171,-.096,-.05264],upper=[.171,.096,.055])},shoe_axes={'left_shoe':dict(toe_local=[1,0,0],heel_local=[0,0,0])},label_end=dict(point_local=[1,0,0])),snapshot=lambda:(state,[]),require_held=lambda *a:None,tip=lambda side:np.array([0,0,.2]),act=act)
    class Guard:
        def __init__(self,*a,**k):pass
        def move(self,target):actions.append('retreat')
    monkeypatch.setattr(branch,'_policy',lambda *a:p);monkeypatch.setattr(geometry,'HeldGeometry',Guard);monkeypatch.setattr(geometry,'install_public_guard',lambda *a:None);monkeypatch.setattr(branch,'HeldGeometry',Guard);monkeypatch.setattr(branch,'install_public_guard',lambda *a:None)
    points=np.array(list(itertools.product([-.10,.10],[-.04,.04],[.08,.12])))+[.2 if outside else 0,0,0]
    monkeypatch.setattr(material,'material_collision_points_task',lambda *a:points)
    monkeypatch.setattr(material,'table_bounds_task',lambda *a:dict(top=0))
    monkeypatch.setattr(release,'actual_opening_bodies',lambda *a:{'palm':np.array(list(itertools.product([-.02,.02],[-.02,.02],[.19,.23])))})
    monkeypatch.setattr(geometry,'collision_parts_task',lambda *a:[np.array(list(itertools.product([-.18,.18],[-.1,.1],[-.055,.055])))])
    monkeypatch.setattr(branch,'_source_release_envelope',lambda *a:pytest.fail('Free-flight promise must not gate a real guided drop'))
    monkeypatch.setattr(branch,'_native_landing_conditions',lambda *a:dict(correct_label_direction=True,inside_original_cavity=landed,actual_supported_in_box=True,native_evaluator_bbox_inside=False))
    context=dict(actor='left_shoe',side='left',support='box',new_reference_strategy=True,historical_166_parameters_available=False)
    return actions,context


def test_guided_drop_uses_actual_landing_and_reports_bbox_fidelity_separately(monkeypatch):
    actions,context=setup(monkeypatch);result=branch.release_source_left_here(None,context)
    assert actions==['RELEASE','retreat'] and result['local_completed']
    assert not result['native_landing_conditions']['native_evaluator_bbox_inside']
    assert result['whole_task_score']is None


def test_guided_drop_still_rejects_real_pre_release_vertex_outside(monkeypatch):
    actions,context=setup(monkeypatch,outside=True)
    with pytest.raises(ToolExecutionError,match='footprint'):branch.release_source_left_here(None,context)
    assert actions==[]


def test_guided_drop_never_accepts_failed_actual_landing(monkeypatch):
    actions,context=setup(monkeypatch,landed=False)
    with pytest.raises(ToolExecutionError,match='failed original native'):branch.release_source_left_here(None,context)
    assert actions==['RELEASE','retreat']


def test_right_shoe_uses_same_guided_release_and_actual_native_landing(monkeypatch):
    actions,context=setup(monkeypatch);p=branch._policy(None,context);state,_=p.snapshot();state['right_shoe']=state.pop('left_shoe');state['right_shoe']['grasp']=[False,True];p.s['shoe_axes']['right_shoe']=p.s['shoe_axes'].pop('left_shoe')
    def act(side,token):
        assert side=='right';actions.append(token);state['right_shoe']['grasp']=[False,False];p.c.steps+=1
    p.act=act;context.update(actor='right_shoe',side='right',midfoot_grasp_strategy='native721_right_upper_near_actual_com_v1')
    result=branch.release_source_left_here(None,context,_source_actor='right_shoe')
    assert actions==['RELEASE','retreat']and result['local_completed']
    assert result['whole_task_score']is None
