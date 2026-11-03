from copy import deepcopy
import pytest
from test_execution_design_e25_a_receiver import fixture
from videoicl_isaaclab import engineering_checkpoint as core
from videoicl_isaaclab.execution_design_e25_remaining import validate_initial_identity


@pytest.mark.parametrize('fault',[None,'source','profile','geometry','history','fields','cp_receipt','missing'])
def test_initial_policy_accepts_only_verified_exact_source_identity_render_chain(tmp_path,monkeypatch,fault):
    a,state,contacts=fixture(tmp_path);old={'task':'E25','variant':'A','seed':4201,'assignment_identity_sha256':'a'*64,'source_sha256':'b'*64,'embodiment_config_sha256':'c'*64,'physical_geometry_sha256':'d'*64}
    current=dict(old,embodiment_config_sha256='e'*64);monkeypatch.setattr(core,'identity',lambda c:current)
    receipt=dict(from_render_hz=5,to_render_hz=1,source_identity=deepcopy(old),source_profile_sha256='c'*64,target_profile_sha256='e'*64,source_native_checkpoint_integrity_sha256='f'*64,changed_config_fields=['physics.render_hz'],physics_parameters_unchanged=True,all_native_state_fields_preserved=True,history_reconstructed=False)
    a.scene.spec['engineering_render_checkpoint_migration']=receipt;a._engineering_resume_checkpoint={'render_cadence_migration_receipt':deepcopy(receipt)}
    if fault=='source':receipt['source_identity']['source_sha256']='0'*64
    elif fault=='profile':receipt['source_profile_sha256']='0'*64
    elif fault=='geometry':current['physical_geometry_sha256']='0'*64
    elif fault=='history':receipt['history_reconstructed']=True
    elif fault=='fields':receipt['changed_config_fields'].append('physics.dt')
    elif fault=='cp_receipt':a._engineering_resume_checkpoint['render_cadence_migration_receipt']['source_native_checkpoint_integrity_sha256']='0'*64
    elif fault=='missing':a.scene.spec.pop('engineering_render_checkpoint_migration')
    if fault is None:validate_initial_identity(a,old)
    else:
        with pytest.raises(ValueError):validate_initial_identity(a,old)
