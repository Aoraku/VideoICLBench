"""Archived same-cadence hydration preserves both raw and derived hashes."""
from copy import deepcopy
import hashlib,json
import pytest
from videoicl_isaaclab import engineering_front25_server_source as source


def archive(tmp_path,hz=5):
    profile={'physics':{'render_hz':20,'dt':.004,'action_seconds':.4},'author_recording':{'initial_gripper_commands_m':{'left':.013}}}
    raw=json.dumps(profile,indent=2).encode();path=tmp_path/'runtime/configs/embodiments/franka.json';path.parent.mkdir(parents=True);path.write_bytes(raw)
    derived=deepcopy(profile);derived['physics']['render_hz']=hz
    spec={'embodiment':'franka','execution_design':{'source_sha256':'a'*64},'embodiment_config_sha256':hashlib.sha256(json.dumps(derived,sort_keys=True,separators=(',',':')).encode()).hexdigest()}
    spec['engineering_render_cadence']={'enabled':True,'engineering_only':True,'original_render_hz':20,'render_hz':hz,'changed_config_fields':['physics.render_hz'],'original_profile_sha256':hashlib.sha256(raw).hexdigest(),'derived_profile_sha256':spec['embodiment_config_sha256'],'source_sha256':'a'*64}
    return spec,path,raw


@pytest.mark.parametrize('hz',[1,5])
def test_archived_rgb_derivation_verifies_exact_profile_without_rewriting_original(tmp_path,hz):
    spec,path,raw=archive(tmp_path,hz);before=deepcopy(spec)
    grips,evidence,problem=source._initial_profile(tmp_path,spec)
    assert grips=={'left':.013,'right':.04}and problem is None
    assert evidence['sha256']==hashlib.sha256(raw).hexdigest()
    assert path.read_bytes()==raw and spec==before


@pytest.mark.parametrize('fault',['raw','derived','cadence','fields','source','missing'])
def test_cadence_hydration_never_accepts_unverified_profile_or_other_changes(tmp_path,fault):
    spec,path,raw=archive(tmp_path)
    if fault=='raw':path.write_bytes(raw+b' ')
    elif fault=='derived':spec['embodiment_config_sha256']='b'*64
    elif fault=='cadence':spec['engineering_render_cadence']['render_hz']=1
    elif fault=='fields':spec['engineering_render_cadence']['changed_config_fields'].append('physics.dt')
    elif fault=='source':spec['engineering_render_cadence']['source_sha256']='b'*64
    else:spec.pop('engineering_render_cadence')
    with pytest.raises(ValueError,match='profile SHA mismatch'):source._initial_profile(tmp_path,spec)
