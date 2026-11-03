import itertools
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e08_supported import table_release_footprint
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def test_empty_table_reset_requires_real_full_source_footprint_inside_table():
    points=np.array(list(itertools.product((-.30,-.10),(-.04,.09),(.812,.98))))
    bounds={'lower':[-.35,-.6,.8],'upper':[.35,.6,.8],'top':.8}
    result=table_release_footprint(points,bounds)
    assert min(result['actual_footprint_margin_xy_m'])>=.049
    with pytest.raises(ToolExecutionError,match='finite table'):
        table_release_footprint(points+[-.06,0,0],bounds)
