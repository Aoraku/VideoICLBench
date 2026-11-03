"""Opt-in engineering RGB cadence; full physics/evidence timing is unchanged.

Call after constructing all scenes, before constructing Controller/RoomPool or
Demonstration. This derives per-scene profiles; global profile objects, assets,
source demonstrations, formal evaluation and initial/final render passes stay
untouched. Native acceptance and video-duration checks are still required.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib,json
from .execution_design import REVISION_V3,source_sha256

FLAG='VIC_ENGINEERING_RENDER_HZ'


def _hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def configure(scenes,*,execution_control,environ):
    value=environ.get(FLAG,'0')
    if value in ('','0'):
        return dict(enabled=False,physics_changed=False,formal_evaluation_unchanged=True)
    if value not in('1','5'):raise ValueError('Only explicit1Hz or5Hz engineering RGB cadence is reviewed')
    render_hz=int(value)
    if not execution_control:raise ValueError('Engineering execution control is required')
    from .execution_design_probe import CONTROLS
    if execution_control not in CONTROLS:raise ValueError('Unknown engineering control')
    if not scenes:raise ValueError('Nonempty engineering scene cohort required')
    pending=[]
    # Validate the complete cohort before changing any scene reference.
    for room,scene in scenes.items():
        spec=scene.spec;design=spec.get('execution_design',{})
        if spec.get('id')not in {f'E{i:02d}'for i in range(14,51)}:
            raise ValueError('Engineering RGB cadence scope is E14 through E50 only')
        if design.get('revision')!=REVISION_V3 or design.get('source_sha256')!=source_sha256(REVISION_V3):
            raise ValueError('Source-verified v3 scene required')
        if spec.get('author_smooth_recording')or 'engineering_render_cadence'in spec:
            raise ValueError('Cannot alter a source recording or reconfigure a running scene')
        original=scene.embodiment;config=deepcopy(original.config);before=deepcopy(config['physics'])
        old_hz=before['render_hz']
        if type(old_hz)not in (int,float)or old_hz<5:raise ValueError('Unexpected original camera cadence')
        config['physics']['render_hz']=render_hz
        restored=deepcopy(config);restored['physics']['render_hz']=old_hz
        assert restored==original.config,'Unexpected change outside RGB render cadence'
        for key,entry in before.items():
            if key!='render_hz':assert config['physics'][key]==entry,key
        derived_hash=_hash(config)
        receipt=dict(enabled=True,engineering_only=True,task=spec['id'],room=room,
            source_sha256=design['source_sha256'],original_render_hz=old_hz,render_hz=render_hz,
            encoder_fps=render_hz,original_profile_sha256=original.config_hash,
            derived_profile_sha256=derived_hash,changed_config_fields=['physics.render_hz'],
            physics_parameters_unchanged=True,physics_dt=before['dt'],
            action_seconds=before['action_seconds'],per_physics_tick_capture_unchanged=True,
            initial_final_resolution_unchanged=True,initial_final_capture_passes_unchanged=True,
            formal_evaluation_unchanged=True,native_video_validation_pending=True)
        pending.append((scene,replace(original,config=config,config_hash=derived_hash),receipt))
    for scene,profile,receipt in pending:
        scene.embodiment=profile
        scene.spec['embodiment_config_sha256']=profile.config_hash
        scene.spec['engineering_render_cadence']=receipt
    return dict(enabled=True,render_hz=render_hz,encoder_fps=render_hz,physics_changed=False,
                full_tick_capture_unchanged=True,rooms=[x[2]for x in pending])
