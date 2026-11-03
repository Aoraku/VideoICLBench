import json
from itertools import product
from pathlib import Path
import numpy as np
from videoicl_isaaclab.execution_design_tool_route_clearance import swept_route_clear


def box(half):
    return np.asarray(list(product((-1.,1.),repeat=3)))*np.asarray(half)


def test_clear_turn_does_not_authorize_descent_through_actual_table():
    # C/v16: last accepted pose placed the low finger at z=.79999919m;
    # a further20.96mm DOWN request physically made only1.4um of progress.
    finger=box([.015,.02,.025])+[0,0,-.025]
    start=np.array([0.,0.,.90]);rotation=np.eye(3)
    poses=[dict(position=[0,0,.84999919],rotation=rotation),
           dict(position=[0,0,.82903883],rotation=rotation)]
    assert not swept_route_clear([finger],start,rotation,poses,[],.8)
    assert swept_route_clear([finger],start,rotation,poses[:1],[],.79)


def test_real_carried_front_cannot_sweep_through_the_other_ball():
    from videoicl_isaaclab.execution_design_spatula_clearance import SUPPORT_VERTICES
    # Actual C/v16 final body and red-ball position. Native contact was .734N;
    # a turn-only test at an elevated station had missed this low collision.
    rotation=np.asarray([[-.4086574018,-.9123178720,.0259829741],
                         [.9071255922,-.4091404974,-.0986256823],
                         [.1006086692,-.0167342909,.9947853088]])
    end=np.array([.0467338115,-.1665415317,.8319604373])
    red=box([.01316]*3)+[.0339572914,-.0849477947,.8133000708]
    start=end+[0,0,.10]
    assert swept_route_clear([SUPPORT_VERTICES],start,rotation,
        [dict(position=start,rotation=rotation)],[red],.8)
    assert not swept_route_clear([SUPPORT_VERTICES],start,rotation,
        [dict(position=end,rotation=rotation)],[red],.8)


def test_straight_sweep_rejects_an_intermediate_obstacle_with_clear_endpoints():
    mesh=box([.01]*3);rotation=np.eye(3)
    obstacle=box([.01]*3)+[.05,0,.9]
    assert not swept_route_clear([mesh],[0,0,.9],rotation,
        [dict(position=[.1,0,.9],rotation=rotation)],[obstacle],.8)
    assert swept_route_clear([mesh],[0,0,.95],rotation,
        [dict(position=[.1,0,.95],rotation=rotation)],[obstacle],.8)


def test_private_collision_budget_never_returns_a_false_clearance():
    import pytest
    with pytest.raises(TimeoutError,match='proposal budget'):
        swept_route_clear([box([.01]*3)],[0,0,.9],np.eye(3),
            [dict(position=[.1,0,.9],rotation=np.eye(3))],[],.8,deadline_monotonic=0.)
