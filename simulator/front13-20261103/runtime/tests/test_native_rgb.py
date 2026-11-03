"""RGB delivery validity differs from scene-dependent pixel variance."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

spec=importlib.util.spec_from_file_location('pool_serve',Path(__file__).resolve().parents[1]/'scripts/serve_realworld_room_pool.py')
serve=importlib.util.module_from_spec(spec);spec.loader.exec_module(serve)


def test_uniform_uint8_background_is_valid_and_saved_before_return(tmp_path):
    raw=np.full((1,12,16,4),220,dtype=np.uint8)
    image,quality=serve.native_rgb(raw,diagnostic_root=tmp_path,room='room',name='left_wrist',tick=340)
    assert image.shape==(12,16,3) and quality['delivery_valid'] and quality['spatial_stddev']==0
    evidence=tmp_path/'room/tick-340-left_wrist'
    assert np.array_equal(np.load(evidence/'annotator.npy'),raw)
    assert (evidence/'rgb.png').exists()
    assert json.loads((evidence/'camera.private.json').read_text())['shared_tick']==340


@pytest.mark.parametrize('raw',[np.empty((1,0),dtype=np.uint8),np.full((1,12,16,3),np.nan)])
def test_empty_or_nonfinite_annotators_remain_invalid_with_private_evidence(tmp_path,raw):
    with pytest.raises(ValueError,match='shape/type'):
        serve.native_rgb(raw,diagnostic_root=tmp_path,room='room',name='head',tick=240)
    evidence=tmp_path/'room/tick-240-head'
    assert (evidence/'annotator.npy').exists()
    assert not json.loads((evidence/'camera.private.json').read_text())['delivery_valid']


def test_sensor_clock_uses_actual_attributes_only():
    class Camera:frame=np.array([7])
    assert serve.camera_clock(Camera())==dict(frame=[7],timestamp=None)
