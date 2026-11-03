"""Reviewed E46 I/4201 input:12mm yellow cargo, same footprint/mass/rule."""
import copy
import numpy as np
REVISION='e46-I4201-yellow-block-total12mm-v1'
SOURCE_SHA='fed57b9b0e69a5b8b98d75324ed6856c0cdb21ebc56c8f98cb372670255b61bb'

def apply(spec):
    if spec['id']!='E46':raise ValueError('E46 input only')
    obj=next(o for o in spec['objects']if o['id']=='yellow_block')
    if obj.get('source_asset',{}).get('sha256')!=SOURCE_SHA or not np.allclose(obj['size'],[.0188,.0188,.00282],atol=1e-12,rtol=0):raise ValueError('Pinned old E46 I4201 cargo required')
    obj['size'][2]=.006;obj['source_asset']['allow_nonuniform_scale']=True
    obj['source_asset']['instance_adaptation']='Reviewed E46 I4201 input v2: Z-only dimension variant total12mm; original XY/color/mass retained'
    obj['execution_instance'].pop('scale',None);obj['execution_instance'].update(kind='nonuniform_dimension_variant',scale_axes=[.94,.94,2.],actual_size=list(obj['size']),input_revision=REVISION)
    obj['execution_input_revision']=REVISION
    spec['e46_input_revision']=REVISION
    return dict(kind='new_yellow_cargo_thickness_instance',input_revision=REVISION,old_total_thickness_m=.00564,new_total_thickness_m=.012,footprint_color_mass_goal_unchanged=True)

def materialize(controller,recipe):
    from .engineering_checkpoint import _hash,PHYSICAL_KEYS,identity,reseal
    if recipe.get('schema')!='engineering-e46-height-input-migration-v1':raise ValueError('Explicit E46 input revision migration required')
    cp=copy.deepcopy(recipe['checkpoint']);digest=cp.pop('checkpoint_sha256')
    if _hash(cp)!=digest:raise ValueError('Old E46 checkpoint checksum')
    cp['checkpoint_sha256']=digest;old=recipe['source_scene'];new=controller.scene.spec
    if _hash({k:old.get(k)for k in PHYSICAL_KEYS})!=cp['identity']['physical_geometry_sha256']:raise ValueError('Old input physical identity')
    expected=copy.deepcopy(old);apply(expected)
    if any(expected.get(k)!=new.get(k)for k in PHYSICAL_KEYS):raise ValueError('Height migration changed other inputs')
    current=identity(controller)
    if any(current.get(k)!=val for k,val in cp['identity'].items()if k!='physical_geometry_sha256'):raise ValueError('Height migration changed assignment/profile')
    from .execution_design_e46_partition_data import NATIVE_BASELINE
    native={}
    for name,asset in controller.scene.objects.items():
        view=asset.root_physx_view;native[name]={k:v.cpu().tolist()for k,v in [('masses_kg',view.get_masses()),('inertias_kg_m2',view.get_inertias()),('centres_of_mass',view.get_coms())]}
        baseline=NATIVE_BASELINE[name]
        for key,val in native[name].items():
            if name=='yellow_block'and key!='masses_kg':continue
            if not np.allclose(val,baseline[key],rtol=1e-5,atol=1e-11):raise ValueError('Unchanged dynamics mismatch '+name+'/'+key)
    from .layout import rotation_matrix
    row=cp['objects']['yellow_block']['root_state_task'];rot=rotation_matrix(row[3:7]);old_size=np.asarray(next(o['size']for o in old['objects']if o['id']=='yellow_block'));new_size=np.asarray(next(o['size']for o in new['objects']if o['id']=='yellow_block'))
    rise=float((np.abs(rot)@(new_size-old_size))[2]);old_bottom=float(row[2]-(np.abs(rot)@old_size)[2]);row[2]+=rise
    old_identity=cp['identity'];cp['identity']=current;cp['context']['e46_input_geometry_migration']=dict(input_revision=REVISION,old_identity=old_identity,new_identity=current,old_bottom_m=old_bottom,new_bottom_m=float(row[2]-(np.abs(rot)@new_size)[2]),root_height_change_m=rise,old_total_thickness_m=.00564,new_total_thickness_m=.012,legal_new_shape_native_mass_properties=native,robot_and_other_objects_state_unchanged=True)
    cp['limitations'].append('Reviewed E46 I4201 cargo height revision5.64mm to12mm; original bottom/XY/color/mass and other states retained; native inertia legitimately recomputed for new shape.')
    return reseal(cp)
