from copy import deepcopy
from pathlib import Path
import numpy as np
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_spatula_clearance import blade_edge_floor_height,SUPPORT_VERTICES

BINDINGS=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json'

@pytest.mark.parametrize('variant',list('ABC'))
def test_real_source_tip_floor_clearance_preserves_thin_block_entry_band(variant):
    s=load('E46',variant,0,BINDINGS,verify_files=False);tool=next(o for o in s['objects']if o['id']=='spatula');edge=np.mean(s['semantic']['tools']['main']['edge_segment'],0)
    theta=np.deg2rad(8);pitch=np.array([[np.cos(theta),0,np.sin(theta)],[0,1,0],[-np.sin(theta),0,np.cos(theta)]])
    for yaw in (0,np.pi/2,np.pi,-np.pi/2):
        c,ss=np.cos(yaw),np.sin(yaw);r=np.array([[c,-ss,0],[ss,c,0],[0,0,1]])@pitch
        z=blade_edge_floor_height(tool,r,edge,.8)
        assert z==pytest.approx(.8022875982172399)
        assert .8<z<.804
        assert np.min(((SUPPORT_VERTICES-edge)@r.T)[:,2]+z)==pytest.approx(.8002)
    changed=deepcopy(tool);changed['size'][0]*=1.1
    with pytest.raises(ValueError,match='exact reviewed source'):blade_edge_floor_height(changed,pitch,edge,.8)
