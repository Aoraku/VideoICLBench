import json
from pathlib import Path

import numpy as np
import pytest

from videoicl_isaaclab.execution_design_cutlery_grasp import plane_section, sectional_target,choose_staging


def test_recorded_thin_handle_is_between_real_finger_sections_above_table():
    d = json.loads((Path(__file__).parent / 'fixtures/cutlery_native_finger_section.json').read_text())
    tcp, current = np.array(d['tcp']), np.array(d['rotation'])
    for candidate in d['targets']:
        rotation = np.array(candidate['rotation'])
        target = sectional_target(d['point'], tcp, current, rotation, d['palm'], d['fingers'], d['floor'])
        meshes = [(np.array(m)-tcp) @ current @ rotation.T + target for m in [d['palm'], *d['fingers']]]
        assert min(m[:, 2].min() for m in meshes) >= d['floor'] + .000299
        sections = [plane_section(m, d['point'][2]) for m in meshes[1:]]
        point = np.array(d['point'])
        # The material lies between opposing jaw sections, within each pad's
        # fore-aft extent; this is geometry evidence, not a simulated grip.
        assert all(s[:, 0].min() < point[0] < s[:, 0].max() for s in sections)
        centres = [(s.min(0)+s.max(0))/2 for s in sections]
        assert min(c[1] for c in centres) < point[1] < max(c[1] for c in centres)
        assert np.linalg.norm(np.mean(centres, axis=0)[:2]-point[:2]) < 1e-8


def test_section_rejects_material_outside_real_finger_height():
    box = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (0, 1)])
    with pytest.raises(ValueError, match='does not intersect'):
        plane_section(box, 1.001)
    section = plane_section(box, .5)
    assert np.allclose(section[:, 2], .5)
    assert np.allclose(section[:, :2].min(0), [-1, -1])
    assert np.allclose(section[:, :2].max(0), [1, 1])


def test_nonfinite_geometry_is_rejected():
    with pytest.raises(ValueError, match='finite'):
        plane_section([[0, 0, float('nan')]], 0)


def test_actual_native_candidates_avoid_long_equivalent_jaw_branch():
    d=json.loads((Path(__file__).parent/'fixtures/cutlery_native_staging_candidates.json').read_text())
    site,grasp,margin=choose_staging(d['final'],d['entries'],d['staging'])
    assert (site,grasp)==(0,1) and margin>.20
    # The earlier higher-margin choice needs joint7 to move +2.64 -> -1.51
    # radians, while the chosen equivalent pinch stays on the nearby branch.
    old=np.array(d['final'][0]['candidate_joints_rad'])-d['staging'][0]['candidate_joints_rad']
    assert np.max(abs(old))>np.pi
    d['staging'][1]['minimum_joint_margin_rad']=.01
    assert choose_staging(d['final'],d['entries'],d['staging'])[0]!=0
