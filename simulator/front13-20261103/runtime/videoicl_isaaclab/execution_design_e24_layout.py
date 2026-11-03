"""Declared fresh E24 initial placement; original meshes and goals retained."""
import hashlib
import json
import math

VERSION='e24-source-lid-clear-box-xy-v1'
LID_XY=[-.03,.365]
LID_SHA='180837493663657fecabc2cbfb1f3ffeedfc96c700ae4ae4a1c82eae5c412fde'
BOX_SHA='b70d3aea3eccf90089cc839ee631bd7ccbabfd26a1c2a7d2d696d0746df6de21'


def apply_layout(spec):
    if spec.get('id')!='E24'or spec.get('e24_lid_initial_layout'):
        raise ValueError('Fresh original E24 layout required')
    objects={obj['id']:obj for obj in spec['objects']};lid=objects['lid'];box=objects['box']
    if (lid.get('source_asset',{}).get('sha256')!=LID_SHA
            or box.get('mechanical_asset',{}).get('sha256')!=BOX_SHA
            or not math.isclose(lid.get('yaw',0),math.pi/2,abs_tol=1e-10)
            or box.get('xy')!=[.04,0.]):
        raise ValueError('Original sideways lid and source box required')
    # The original source surfaces intersect the positive-Y box wall. The
    # declared placement clears its complete envelope and remains on the table.
    half_x=float(lid['size'][1]);half_y=float(lid['size'][0])
    gap=LID_XY[1]-half_y-float(box['size'][0])
    if (gap<.002 or LID_XY[0]-half_x<-.35 or LID_XY[0]+half_x>.35
            or LID_XY[1]-half_y<-.6 or LID_XY[1]+half_y>.6):
        raise ValueError('Declared E24 lid needs source-box separation and full table footprint')
    old=list(lid['xy']);lid['xy']=list(LID_XY)
    spec['e24_lid_initial_layout']=dict(version=VERSION,lid_source_sha256=LID_SHA,
        box_source_sha256=BOX_SHA,original_lid_xy=old,derived_lid_xy=list(LID_XY),
        minimum_required_separation_m=.002,source_envelope_y_gap_m=gap,
        only_initial_lid_xy_changed=True,source_mesh_mass_and_native_rules_unchanged=True,
        native_verified=False)


def bind_identity(spec):
    physical=spec['e24_lid_initial_layout'];design=spec['execution_design']
    def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    for key in('environment_identity','assignment_identity_sha256','paired_input_identity'):
        design['source_'+key]=design[key]
        design[key]=digest(dict(source_identity=design[key],physical_revision=physical))
    design['physical_configuration_sha256']=digest(physical)
    design['engineering_layout_candidate']=physical


def verify_native_restore(author):
    """Read the admitted migration world; send no public or private actions."""
    import numpy as np
    spec=author.scene.spec;checkpoint=getattr(author,'_engineering_resume_checkpoint',{})
    migration=checkpoint.get('context',{}).get('e24_layout_migration',{})
    if (spec.get('variant')!='A'or spec.get('seed')!=4201
            or spec.get('e24_lid_initial_layout',{}).get('version')!=VERSION
            or migration.get('history_reconstructed')is not False
            or not getattr(author.c,'_engineering_diagnostic_only',False)
            or not getattr(author.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Admitted explicit E24 clear-layout migration required')
    state,contacts=author.c.snapshot();position=np.asarray(state['lid']['pos'],float)
    if not np.isfinite(position).all()or np.max(np.abs(position[:2]-LID_XY))>.005:
        raise ValueError('Actual restored E24 lid differs from declared startup XY')
    if any(any(row['grasp'])for row in state.values()):
        raise ValueError('E24 layout verification requires actual empty hands')
    cups={name:frozenset((name,'box'))in contacts for name in('blue','green','red')}
    if not all(cups.values()):raise ValueError('Actual original E24 three-cup box support missing')
    forces=getattr(author.c,'contact_forces',{})
    return dict(local_completed=True,operations=[],actions=0,initialization_only=True,
        manual_lid_startup_change_disclosed=True,history_reconstructed=False,
        actual_lid_position_task_m=position.tolist(),actual_cup_box_contacts=cups,
        actual_cup_box_forces_n={name:forces.get(frozenset((name,'box')))for name in cups},
        actual_lid_contacts=[sorted(pair)for pair in contacts if'lid'in pair],
        lid_picked_up_or_full_task_completed=False)
