"""Measured material slicing cannot invent missing above-rail material."""
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e17_rail_top_grasp import horizontal_slice,TRIANGLE
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def test_exact_prism_slice_is_horizontal_and_inside_actual_edges():
    points=TRIANGLE.copy();points[:,2]=TRIANGLE[:,0]+.02
    section=horizontal_slice(points,.025)
    assert len(section)>=3 and np.allclose(section[:,2],.025)
    assert np.all(section>=points.min(0)-1e-12)and np.all(section<=points.max(0)+1e-12)


def test_slice_outside_actual_material_is_rejected():
    with pytest.raises(ToolExecutionError):horizontal_slice(TRIANGLE,.1)
