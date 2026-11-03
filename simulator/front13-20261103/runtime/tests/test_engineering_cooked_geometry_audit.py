from itertools import product
import numpy as np
import pytest
from videoicl_isaaclab.engineering_cooked_geometry_audit import vertical_source_surface

def test_thin_source_top_and_bottom_remain_distinct_in_translated_task_frame():
    vertices=np.asarray(list(product((-.044,.044),(-.031,.031),(-.000175,.000175))))+[.2,-.1,.8]
    top=vertical_source_surface(vertices,[.2,-.1],-1);bottom=vertical_source_surface(vertices,[.2,-.1],1)
    assert top['z_m']==pytest.approx(.800175)
    assert bottom['z_m']==pytest.approx(.799825)
    assert top['normal'][2]>.999 and bottom['normal'][2]<-.999
    assert vertical_source_surface(vertices,[.25,-.1],-1)is None
