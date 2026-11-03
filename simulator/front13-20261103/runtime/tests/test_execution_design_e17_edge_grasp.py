import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from test_execution_design_segments_e17_e20 import context
from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
from videoicl_isaaclab import execution_design_e17_edge_grasp as edge
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def setup(monkeypatch):
 import json
 from pathlib import Path
 model=json.loads((Path(__file__).parent/'fixtures/e17_c90_real_finger_edge_model.json').read_text())
 a,state,contacts=context('E17','C');tip=np.asarray(model['tip']);a.tip=lambda side:tip.copy()
 for name,row in model['objects'].items():
  if name in state:state[name].update(pos=np.asarray(row['pos']),mat=np.asarray(row['mat']),grasp=row['grasp'])
 clouds=[np.asarray(c)for c in model['clouds']]
 monkeypatch.setattr(edge,'_finger_clouds',lambda p:clouds)
 a.finger_geometry=lambda side:dict(fingers=[dict(body_origin_task_m=x)for x in model['origins']])
 return ExecutionDesignAuthor(a),state


def test_tilted_square_closes_to_real_full_width_before_source_rail(monkeypatch):
 p,state=setup(monkeypatch);before=state['green_square']['pos'].copy();target,evidence=edge.planned_target(p,'green_square')
 assert evidence['minimum_nominal_edge_stroke_rail_clearance_m']>=.0025
 assert max(evidence['predicted_material_contact_strokes_m'])<.023
 assert evidence['minimum_nominal_edge_stroke_rail_clearance_m']>.004
 assert np.array_equal(before,state['green_square']['pos'])


def test_floating_material_outside_real_finger_pad_height_is_rejected(monkeypatch):
 p,state=setup(monkeypatch);state['green_square']['pos'][2]+=.20
 with pytest.raises(ToolExecutionError):edge.planned_target(p,'green_square')
