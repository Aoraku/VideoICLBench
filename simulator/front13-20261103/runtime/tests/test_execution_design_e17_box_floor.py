import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from test_execution_design_segments_e17_e20 import context
from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
from videoicl_isaaclab import execution_design_e17_box_floor as grasp
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def setup(monkeypatch):
 a,state,contacts=context('E17','A');tip=np.array([0.,.080,.868]);a.tip=lambda side:tip.copy()
 state['packing_box']['pos']=np.array([0,0,.826]);state['packing_box']['mat']=np.eye(3)
 state['green_triangle']['pos']=np.array([.010,.097,.817]);state['green_triangle']['mat']=Rotation.from_euler('z',-56.5,degrees=True).as_matrix()
 clouds=[np.array([tip+[x,y,z]for x in xs for y in(-.0106,.0106)for z in(-.01145,.045)])for xs in[(-.066,-.040),(.040,.066)]]
 monkeypatch.setattr(grasp,'_finger_clouds',lambda p:clouds);a.finger_geometry=lambda side:dict(fingers=[dict(body_origin_task_m=[-.05,0,0]),dict(body_origin_task_m=[.05,0,0])])
 return ExecutionDesignAuthor(a),state


def test_box_axis_pinch_clips_only_planned_y_to_the_actual_free_bay(monkeypatch):
 p,state=setup(monkeypatch);before=state['green_triangle']['pos'].copy();target,evidence=grasp.planned_target(p)
 assert evidence['source_floor_bay_y_m']==pytest.approx([.054,.106])
 assert target[1]+.0106<=.106-.0025 and evidence['minimum_actual_closing_rail_clearance_m']>=.0025
 assert target[2]-.01145==pytest.approx(.814+.0026)
 assert np.array_equal(before,state['green_triangle']['pos'])


def test_real_divider_overlap_is_still_rejected(monkeypatch):
 p,state=setup(monkeypatch);state['green_triangle']['pos'][1]=.124
 with pytest.raises(ToolExecutionError):grasp.planned_target(p)
