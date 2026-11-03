import importlib.util
from pathlib import Path
import json
import numpy as np
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sensor_depth_test', ROOT/'videoicl_isaaclab/sensor_depth.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_lossless_axial_packet_invalids_and_no_dense_metadata():
    z=np.array([[[[.7],[float('inf')],[0]],[[1.2],[-1],[float('nan')]]]],dtype=np.float32)
    p=m.encode_depth_packet(z,rgb_bytes=b'actual jpeg',observation_tick=317)
    json.dumps(p,allow_nan=False)
    result=m.decode_depth_packet(p)
    assert result.shape==(2,3) and result[0,0]==np.float32(.7) and result[1,0]==np.float32(1.2)
    assert np.isnan(result[[0,0,1,1],[1,2,1,2]]).all()
    assert p['valid_pixel_count']==2 and p['observation_tick']==317
    assert 'depth_m_base64' not in m.depth_packet_metadata(p)
    assert 'objects' not in m.depth_packet_metadata(dict(p, objects=['secret']))
    assert set(p).isdisjoint({'objects','score','success','segmentation'})

def test_reject_range_depth_and_truncated_buffer():
    p=m.encode_depth_packet(np.ones((2,3)),rgb_bytes=b'frame',observation_tick=0)
    with pytest.raises(ValueError):m.decode_depth_packet(dict(p,quantity='range'))
    with pytest.raises(ValueError):m.decode_depth_packet(dict(p,width=4))
    with pytest.raises(ValueError):m.decode_depth_packet(dict(p,width=True))

def test_runtime_sdk_packet_implementations_identical():
    sdk=ROOT.parent/'VideoICLBench/packages/sdk/vic_sdk/embodied_environment/sensor_depth.py'
    assert sdk.read_bytes()==(ROOT/'videoicl_isaaclab/sensor_depth.py').read_bytes()
