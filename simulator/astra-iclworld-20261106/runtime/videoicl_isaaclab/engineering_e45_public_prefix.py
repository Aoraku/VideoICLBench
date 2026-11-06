"""Reviewed goal-independent held-cup public prefix for E45 engineering ABC."""
import copy,numpy as np
from .engineering_checkpoint import _hash,PHYSICAL_KEYS,identity,reseal

def materialize(controller,recipe):
    from .execution_design_e45_balls import configure_spec,BALLS,NATIVE_SOURCE_MASS_PROPERTIES
    from .execution_design_e45_acceptance_geometry import bind
    if recipe.get('schema')!='engineering-e45-public-prefix-variant-v1':raise ValueError('Explicit E45 public prefix only')
    cp=copy.deepcopy(recipe['checkpoint']);digest=cp.pop('checkpoint_sha256')
    if _hash(cp)!=digest:raise ValueError('Prefix integrity')
    cp['checkpoint_sha256']=digest;old=recipe['source_scene'];new=controller.scene.spec
    if old['id']!='E45'or old['variant']!='A'or new['id']!='E45'or new['variant']not in('B','C')or new['seed']!=4201:raise ValueError('E45 A public prefix to B/C4201 only')
    if cp['source']['steps']!=216 or cp['stage']!='e45-before-first-tilt'or cp['readback']['object_grasps']['cup']!=[False,True]:raise ValueError('Pinned true held-cup216 prefix required')
    if _hash({k:old.get(k)for k in PHYSICAL_KEYS})!=cp['identity']['physical_geometry_sha256']:raise ValueError('Original prefix physical inputs')
    expected=copy.deepcopy(old);configure_spec(expected);bind(expected);expected['semantic']['target']=new['semantic']['target']
    if any(expected.get(k)!=new.get(k)for k in PHYSICAL_KEYS):raise ValueError('Public prefix altered physical inputs beyond reviewed balls/acceptance metadata and goal branch')
    current=identity(controller);profile_migration=None
    if any(cp['identity'][k]!=current[k]for k in ('task','seed','source_sha256')):raise ValueError('Public prefix changed task/seed/source')
    if old['execution_design']['condition']!='I'or new['execution_design']['condition']!='I':raise ValueError('Only the same I input prefix is shared')
    if cp['identity']['embodiment_config_sha256']!=current['embodiment_config_sha256']:
        old_profile=recipe['source_profile_config'];new_profile=copy.deepcopy(old_profile);new_profile['physics']['render_hz']=1
        if (recipe.get('allow_render_only_from5_to1')is not True or old_profile['physics']['render_hz']!=5
                or _hash(old_profile)!=cp['identity']['embodiment_config_sha256']or new_profile!=controller.scene.embodiment.config):raise ValueError('Only explicit render5Hz to1Hz may change prefix profile')
        profile_migration=dict(changed_fields=['physics.render_hz'],old=5,new=1,physics_dt_unchanged=True,controls_cameras_other_parameters_unchanged=True)
    native={}
    for name,asset in controller.scene.objects.items():
        view=asset.root_physx_view;native[name]={k:v.cpu().tolist()for k,v in [('masses_kg',view.get_masses()),('inertias_kg_m2',view.get_inertias()),('centres_of_mass',view.get_coms())]}
        if name in NATIVE_SOURCE_MASS_PROPERTIES:
            for key,value in native[name].items():
                if not np.allclose(value,NATIVE_SOURCE_MASS_PROPERTIES[name][key],rtol=1e-5,atol=1e-11):raise ValueError('Public prefix changed native dynamics '+name+'/'+key)
    old_identity=cp['identity'];cp['identity']=current;cp['context']['e45_public_prefix_variant']=dict(origin_variant='A',target_variant=new['variant'],prefix_actions=216,goal_branch_only=True,objects_physical_equal_before_reviewed_ball_fidelity=True,old_identity=old_identity,new_identity=current,render_only_profile_migration=profile_migration,native_mass_properties=native)
    cp['context']['e45_ball_migration']=dict(changed_objects=list(BALLS),post_settle_ball_motion_is_new_geometry=True,old_ball_state_preserved=False)
    cp['limitations'].append('Engineering-only shared public held-cup prefix from A; new B/C goal branch; no prior evaluator/history/score is restored. Explicit render-only profile migration recorded.')
    return reseal(cp)
