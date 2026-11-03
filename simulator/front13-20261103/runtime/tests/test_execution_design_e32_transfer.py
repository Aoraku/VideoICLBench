import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e32_transfer import planar_route,intersects_segment

def test_clear_segment_keeps_direct_path():
 result=planar_route([0,0],[1,0],[],[-2,-2],[2,2])
 assert len(result)==1 and np.allclose(result[0],[1,0])

def test_plastic_box_corridor_detours_without_crossing_inflated_obstacle():
 start=np.array([-.22,.10]);end=np.array([.02,-.34]);rectangles=[(np.array([-.35,-.305]),np.array([-.08,-.135]))]
 result=planar_route(start,end,rectangles,[-.5,-.5],[.5,.5])
 assert len(result)>1
 for point in result:
  assert not any(intersects_segment(start,point,lo,hi)for lo,hi in rectangles)
  start=point
 assert np.allclose(result[-1],end)

def test_no_corridor_and_inside_target_fail_closed():
 with pytest.raises(RuntimeError):planar_route([-.8,0],[.8,0],[([-.1,-2],[.1,2])],[-1,-1],[1,1])
 with pytest.raises(RuntimeError):planar_route([-.8,0],[0,0],[([-.1,-.1],[.1,.1])],[-1,-1],[1,1])

@pytest.mark.parametrize('a,b,expected',[([0,0],[1,0],True),([0,2],[1,2],False),([0,1],[1,1],True),([0,-2],[1,-2],False)])
def test_segment_boundary_and_parallel_cases(a,b,expected):
 assert intersects_segment(a,b,[.4,-1],[.6,1])==expected

def test_reject_nonfinite_inputs():
 with pytest.raises(ValueError):planar_route([float('nan'),0],[1,0],[],[-2,-2],[2,2])


def test_near_base_climb_staging_preserves_current_obstacle_envelope():
    from videoicl_isaaclab.execution_design_e32_transfer import climb_candidates
    obstacles=[(np.array([-.242,.016]),np.array([-.073,.182]))]
    points=climb_candidates([.088,.054],obstacles,[-.5,-.5],[.5,.5])
    assert any(np.allclose(p,[-.032,.054])for p in points)
    assert all(not intersects_segment([.088,.054],p,*obstacles[0])for p in points)
    assert all(p[0]>=-.073 for p in points)


@pytest.mark.parametrize('reachable',[False,True])
def test_raised_route_uses_public_moves_only_after_all_ik_endpoints_pass(tmp_path,monkeypatch,reachable):
    from types import SimpleNamespace
    from videoicl_isaaclab.execution_design_e32_transfer import raised_transfer
    from videoicl_isaaclab import execution_design_drawer_ik_probe as probe
    requested=[];moves=[]
    def inspect(a,c,side,targets):
        requested.extend(targets)
        return [dict(kinematically_reachable=reachable,joint_distance_rad=i)for i,_ in enumerate(targets)]
    monkeypatch.setattr(probe,'inspect',inspect)
    a=SimpleNamespace(tip=lambda side:np.array([0.,0.,1.12]),tcp_rotation_task=lambda side:np.eye(3),
        out=tmp_path,c=SimpleNamespace(steps=3),scene=SimpleNamespace(spec={'expert_loaded_step_mm':12.}),
        move_generated=lambda targets,**kwargs:moves.append(targets))
    result=raised_transfer(a,'bottle','right',[.02,-.3],1.1,[],{'lower':[-.5,-.5],'upper':[.5,.5]},1.04,.21)
    assert result==reachable
    assert a.scene.spec['expert_loaded_step_mm']==12.
    assert requested[0]['position'][2]==pytest.approx(1.275)
    if reachable:
        assert len(moves)==3
        assert moves[0]['right'][2]==pytest.approx(1.12)  # never lower at source after loaded drift
        assert moves[1]['right'][2]==pytest.approx(1.275)
        assert moves[2]['right']==pytest.approx([.02,-.3,1.275])
    else:assert not moves
