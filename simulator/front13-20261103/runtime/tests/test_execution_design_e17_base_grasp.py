"""A single separating-plane adjustment preserves the original2.5mm guard."""
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e17_base_grasp import clear_rails_once
from videoicl_isaaclab.execution_design_e24_collision import separation_certificate
from videoicl_isaaclab.execution_design_segments_e17_regrasp import CORNERS
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def fixture():
    a=np.array([[x,y,z]for x in(-.020,-.00467)for y in(.03,.05)for z in(-.01,0)])
    b=a+[.08,0,0]
    rails=[{'pos':[0,y,-.006],'size':[.003,.014,.006]}for y in(-.12,-.04,.04,.12)]
    return [a,b],rails


def test_one_finite_plane_translation_restores_clearance_without_looser_threshold():
    clouds,rails=fixture();target=np.zeros(3);new,shift=clear_rails_once(clouds,rails,target)
    assert np.array_equal(target,np.zeros(3))and 0<shift<=.003
    assert new[0]==pytest.approx(-.00093)and not new[1]and not new[2]
    assert all(separation_certificate(c+new,CORNERS*np.asarray(r['size'])+r['pos'])>=.0025 for c in clouds for r in rails)


def test_multiple_contact_pattern_is_not_searched_or_silently_accepted():
    clouds,rails=fixture()
    with pytest.raises(ToolExecutionError,match='Unreviewed'):clear_rails_once([clouds[0],clouds[0]],rails,np.zeros(3))
