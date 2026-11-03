from pathlib import Path
from copy import deepcopy
import math
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_scenes import build_execution_scene, TASKS

BINDINGS=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json'

@pytest.mark.parametrize('task',TASKS)
@pytest.mark.parametrize('variant',list('ABC'))
@pytest.mark.parametrize('seed',[1,2,3])
def test_workflow_pair_identity_and_actual_bodies(task,variant,seed):
    base=load(task,variant,seed,BINDINGS,verify_files=False)
    before=deepcopy(base)
    a=build_execution_scene(base,condition='I',seed=seed)
    b=build_execution_scene(base,condition='E',seed=seed)
    assert base==before
    assert a==build_execution_scene(base,condition='I',seed=seed)
    x,y=a['execution_design'],b['execution_design']
    assert x['paired_input_id']==y['paired_input_id']
    assert x['destination_zone']==y['destination_zone']
    assert x['local_regions']==y['local_regions']
    assert x['initial_preserved']==y['initial_preserved']
    aa={o['id']:o for o in a['objects']};bb={o['id']:o for o in b['objects']}
    assert len(aa)==len(a['objects']) and aa.keys()==bb.keys()
    assert aa[x['delivery_actor']]['role']=='movable'
    for package in x['packages']:
        assert len(aa[package['container']]['collision_shapes'])>=5
        assert all(i<j for i,j in zip(package['lower'],package['upper']))
        assert set(package['members'])<=set(aa)
        if package.get('lid'):assert package['lid'] in aa
    for joint in a['joints']:
        assert joint['parent'] in aa and joint['child'] in aa
        assert joint['type']=='revolute'
    for key in aa:
        assert bb[key]['xy'][0]-aa[key]['xy'][0]==pytest.approx(.035)
        assert bb[key]['xy'][1]-aa[key]['xy'][1]==pytest.approx(-.025)
    assert not a['release_ready']
    assert a['instruction']!=base['instruction']
    assert a['demo_scope']=='local_rule_only'
    assert {z['digit'] for z in a['zones'] if z['id'].startswith('delivery_')}=={1,2}

@pytest.mark.parametrize('task',TASKS)
def test_local_demo_does_not_fake_full_R(task):
    b=load(task,'A',0,BINDINGS,verify_files=False)
    with pytest.raises(ValueError):build_execution_scene(b,condition='R')

@pytest.mark.parametrize('task',['E01','E39'])
def test_initial_hinge_anchors_coincide(task):
    s=build_execution_scene(load(task,'A',1,BINDINGS,verify_files=False))
    objects={o['id']:o for o in s['objects']}
    for j in s['joints']:
        p,c=objects[j['parent']],objects[j['child']]
        a=j['anchor0'];b=j['anchor1']
        # Initial child rests against the real 100-degree hinge upper stop.
        parent=[p['xy'][0]+a[0],p['xy'][1]+a[1],p['bottom']+p['size'][2]+a[2]]
        angle=2*math.atan2(c['quaternion'][1],c['quaternion'][0])
        child=[c['xy'][0]+b[0],c['xy'][1]+math.cos(angle)*b[1]-math.sin(angle)*b[2],
               c['center_z']+math.sin(angle)*b[1]+math.cos(angle)*b[2]]
        assert child==pytest.approx(parent)

@pytest.mark.parametrize('task',TASKS)
@pytest.mark.parametrize('seed',[1,2,3])
def test_world_and_order_do_not_reveal_private_variant(task,seed):
    specs=[build_execution_scene(load(task,v,seed,BINDINGS,verify_files=False)) for v in 'ABC']
    for key in ('objects','zones','fixtures','joints','head_view'):
        assert specs[0][key]==specs[1][key]==specs[2][key],key
    assert len({str(s['execution_design']['public_order']) for s in specs})==1

@pytest.mark.parametrize('task',['E01','E39'])
def test_closed_hinge_lid_bottom_clears_box_rim(task):
    s=build_execution_scene(load(task,'A',1,BINDINGS,verify_files=False))
    oo={o['id']:o for o in s['objects']}
    for j in s['joints']:
        parent,child=oo[j['parent']],oo[j['child']]
        closed_z=j['anchor0'][2]-j['anchor1'][2]
        assert closed_z-child['size'][2]>=parent['size'][2]-1e-9

@pytest.mark.parametrize('task',TASKS)
def test_source_actor_origin_calibration_survives_new_storage_height(task):
    base=load(task,'A',1,BINDINGS,verify_files=False)
    revised=build_execution_scene(base)
    old={o['id']:o for o in base['objects']}
    for o in revised['objects']:
        if o['id'] in old and 'center_z' in old[o['id']]:
            b=old[o['id']]
            assert o['center_z']-o['bottom']==pytest.approx(b['center_z']-b['bottom'])

@pytest.mark.parametrize('task',TASKS)
@pytest.mark.parametrize('condition',['I','E'])
def test_delivery_footprint_supported_by_real_table(task,condition):
    s=build_execution_scene(load(task,'A',1,BINDINGS,verify_files=False),condition=condition)
    d=s['execution_design'];o=next(o for o in s['objects'] if o['id']==d['delivery_actor'])
    for z in s['zones']:
        if not z['id'].startswith('delivery_'):continue
        for axis,table_half in enumerate((.35,.60)):
            assert abs(z['xy'][axis])+o['size'][axis] <= table_half


def test_movable_stand_requires_dynamic_native_opt_in():
    s=build_execution_scene(load('E17','A',1,BINDINGS,verify_files=False))
    stand=next(o for o in s['objects'] if o['id']=='stand')
    assert stand['dynamic_mechanical_asset'] is True
    assert stand['role']=='movable'
    assert s['execution_design']['shelf_insertion']['lower']['carry_bottom_z'] > .0168

@pytest.mark.parametrize('task',TASKS)
@pytest.mark.parametrize('condition',['I','E'])
@pytest.mark.parametrize('seed',[1,2,3])
def test_initial_carrier_is_not_already_delivered(task,condition,seed):
    s=build_execution_scene(load(task,'A',seed,BINDINGS,verify_files=False),condition=condition)
    d=s['execution_design'];o=next(o for o in s['objects'] if o['id']==d['delivery_actor'])
    z=next(z for z in s['zones'] if z['id']==d['destination_zone'])
    assert not all(abs(o['xy'][i]-z['xy'][i])+o['size'][i]<=z['half_size'][i]+.003 for i in range(2))

@pytest.mark.parametrize('task',['E01','E17','E39'])
@pytest.mark.parametrize('condition',['I','E'])
def test_delivery_avoids_protected_or_cleanup_props(task,condition):
    s=build_execution_scene(load(task,'A',1,BINDINGS,verify_files=False),condition=condition)
    d=s['execution_design'];objects={o['id']:o for o in s['objects']};carrier=objects[d['delivery_actor']]
    protected={'E01':['drink'],'E17':['recycle_box'],'E39':['reference_tray']}[task]
    for z in s['zones']:
        if not z['id'].startswith('delivery_'):continue
        for name in protected:
            o=objects[name]
            assert any(abs(z['xy'][i]-o['xy'][i])>carrier['size'][i]+o['size'][i]+.002 for i in range(2)),(task,name,z['id'])


def test_e01_grasp_tab_is_physical_and_inside_declared_bounds():
    s=build_execution_scene(load('E01','A',1,BINDINGS,verify_files=False))
    o=next(o for o in s['objects'] if o['id']=='meal_box')
    g=s['execution_design']['grasps']['meal_box']
    assert g['hand']=='right'  # Seed1's receiving station is on the right-arm side.
    tab=o['collision_shapes'][-1]
    assert tab['size'][0]*2==pytest.approx(.020)
    assert tab['pos']==g['local']
    c=o['local_bounds_center']
    for shape in o['collision_shapes']:
        for i in range(3):
            assert abs(shape['pos'][i]-c[i])+shape['size'][i] <= o['size'][i]+1e-9


@pytest.mark.parametrize('condition',['I','E'])
def test_e01_lower_storage_projects_outside_upper_platform_without_food_overlap(condition):
    s=build_execution_scene(load('E01','A',4201,BINDINGS,verify_files=False),condition=condition)
    d=s['execution_design'];objects={o['id']:o for o in s['objects']}
    lower,upper=s['fixtures'][:2];tray=objects['tray']
    assert upper['xy'][0]-lower['xy'][0]==pytest.approx(.15)
    assert tray['xy']==lower['xy']
    assert tray['xy'][0]-tray['size'][0]<upper['xy'][0]-upper['size'][0]-.10
    exit_x=d['storage_extraction']['tray']['exit_offset_task'][0]
    assert exit_x==pytest.approx(-.15)
    assert tray['xy'][0]+exit_x+tray['size'][0] < upper['xy'][0]-upper['size'][0]-.015
    for name in s['semantic']['groups']['foods']:
        food=objects[name]
        assert any(abs(food['xy'][i]-tray['xy'][i])>food['size'][i]+tray['size'][i]+.005 for i in (0,1))
    for f in (lower,upper):
        assert abs(f['xy'][0])+f['size'][0]<.35 and abs(f['xy'][1])+f['size'][1]<.6

@pytest.mark.parametrize('task',TASKS)
def test_E_changes_real_table_material_without_changing_I(task):
    base=load(task,'A',1,BINDINGS,verify_files=False)
    a=build_execution_scene(base,condition='I');b=build_execution_scene(base,condition='E')
    assert 'table_surface' not in a and 'table_surface' not in base
    assert b['table_surface']['color']==[.32,.43,.48]
    assert b['table_surface']['static_friction']==.65
    assert 'table_material' in b['execution_design']['environment_changes']

@pytest.mark.parametrize('task',TASKS)
def test_packaging_mass_estimates_are_explicit_and_pair_matched(task):
    base=load(task,'A',1,BINDINGS,verify_files=False)
    a=build_execution_scene(base,condition='I');b=build_execution_scene(base,condition='E')
    estimates=a['execution_design']['packaging_mass_estimates']
    assert estimates==b['execution_design']['packaging_mass_estimates']
    assert estimates
    objects={o['id']:o for o in a['objects']}
    original={o['id']:o for o in base['objects']}
    for name,value in estimates.items():
        assert name not in original
        assert objects[name]['physical_mass_kg']==value['mass_kg']>0
        assert value['measured'] is False and value['native_load_validation']=='pending'
    if task=='E01':assert objects['meal_box']['physical_mass_kg']==.25


@pytest.mark.parametrize('condition',['I','E'])
def test_e17_lid_tab_is_real_and_preserves_original_lid_contact_plane(condition):
    s=build_execution_scene(load('E17','A',1,BINDINGS,verify_files=False),condition=condition)
    lid=next(o for o in s['objects'] if o['id']=='packing_lid')
    assert lid['center_z']-.003==pytest.approx(lid['bottom'])
    assert lid['bottom']==pytest.approx(.849)  # Real storage platform adds 8mm.
    assert lid['local_bounds_center'][2]-lid['size'][2]==pytest.approx(-.003)
    tab=lid['collision_shapes'][1]
    assert tab['pos'][2]-tab['size'][2]==pytest.approx(.003)
    assert tab['size'][0]*2==pytest.approx(.020)
    grasp=s['execution_design']['grasps']['packing_lid']
    assert grasp['local'][2]>.003
    assert grasp['jaw_axis_local']==[1,0,0]
    assert abs(grasp['local'][2]-tab['pos'][2])<tab['size'][2]


@pytest.mark.parametrize('revision',['embodied50-execution-v2-20261102','embodied50-execution-v3-20261102'])
def test_scene_contract_revision_is_explicit_and_not_schema_alias(revision):
    s=build_execution_scene(load('E01','A',1,BINDINGS,verify_files=False),revision=revision)
    assert s['task_revision']==revision
    assert s['execution_design']['revision']==revision
    assert s['execution_design']['schema']=='execution-design-v2'


@pytest.mark.parametrize('condition',['I','E'])
def test_e20_spare_rails_leave_finger_space_and_preserve_initial_tray_members(condition):
    import numpy as np
    s=build_execution_scene(load('E20','A',4201,BINDINGS,verify_files=False),condition=condition)
    d=s['execution_design'];objects={o['id']:o for o in s['objects']}
    preserved={n for ids in d['initial_preserved'].values() for n in ids}
    spare=set(d['target_members'])-preserved
    for n in spare:
        o=objects[n];support=d['initial_storage'][n]
        assert support in d['unused_supply_supports']
        f=s['fixtures'][int(support.removeprefix('fixture'))]
        assert f['size'][0]<o['size'][0]/2
        assert o['bottom']==pytest.approx(f['z']+f['size'][2])
        np.testing.assert_allclose(o['xy'],f['xy'])
    for a in spare:
        for b in spare-{a}:
            assert np.linalg.norm(np.array(objects[a]['xy'])-objects[b]['xy'])>=.0799
    for n in preserved:
        assert d['initial_storage'][n] not in d['unused_supply_supports']


@pytest.mark.parametrize('condition',['I','E'])
def test_e17_integral_cradles_support_pieces_without_touching_closed_lid(condition):
    s=build_execution_scene(load('E17','A',4201,BINDINGS,verify_files=False),condition=condition)
    d=s['execution_design'];objects={o['id']:o for o in s['objects']};box=objects['packing_box'];lid=objects['packing_lid']
    top=box['bottom']+box['size'][2]
    for n in d['target_members']:
        o=objects[n]
        assert o['bottom']==pytest.approx(top)
        assert o['bottom']+2*o['size'][2]<lid['bottom']-.010
        assert d['grasps'][n]['local']==[0,0,0]
    assert len(box['collision_shapes'])==9


@pytest.mark.parametrize('condition',['I','E'])
def test_e39_cradles_leave_active_tops_below_work_tray_rim(condition):
    s=build_execution_scene(load('E39','A',4201,BINDINGS,verify_files=False),condition=condition)
    d=s['execution_design'];objects={o['id']:o for o in s['objects']};tray=objects['work_tray']
    for n in d['target_members']:
        o=objects[n]
        assert o['bottom']==pytest.approx(tray['center_z']+.006)
        assert o['bottom']+2*o['size'][2]<tray['center_z']+.018
    assert len(tray['collision_shapes'])==11  # Walls, cradles, dividers and real grip tab.
    assert objects['reference_tray']['role']=='fixture'


@pytest.mark.parametrize('condition',['I','E'])
def test_e09_source_rails_clear_open_fingers_without_altering_source_assets(condition):
    import numpy as np
    base=load('E09','A',4201,BINDINGS,verify_files=False)
    originals={o['id']:o for o in base['objects']}
    s=build_execution_scene(base,condition=condition,seed=4201)
    d=s['execution_design'];objects={o['id']:o for o in s['objects']}
    for n in d['target_members']:
        o=objects[n];f=s['fixtures'][int(d['initial_storage'][n].removeprefix('fixture'))]
        assert o['size']==originals[n]['size']
        assert o.get('source_asset')==originals[n].get('source_asset')
        assert o['bottom']==pytest.approx(f['z']+f['size'][2])
        np.testing.assert_allclose(o['xy'],f['xy'])
        for other in set(d['target_members'])-{n}:
            assert np.linalg.norm(np.asarray(o['xy'])-objects[other]['xy'])>=.0999


@pytest.mark.parametrize('condition',['I','E'])
def test_e17_single_column_has_real_full_open_finger_space_and_packable_shell(condition):
    import numpy as np
    s=build_execution_scene(load('E17','A',4201,BINDINGS,verify_files=False),condition=condition)
    d=s['execution_design'];o={v['id']:v for v in s['objects']}
    packing=o['packing_box'];lid=o['packing_lid'];recycle=o['recycle_box']
    points=np.array([o[n]['xy']for n in d['target_members']])
    assert np.ptp(points[:,0])<1e-9
    assert np.diff(np.sort(points[:,1])).min()==pytest.approx(.08)
    # Actual prior native full-open mesh spanned 127.31mm; allow 130mm
    # during reviewed straight jaw-X entry plus 10mm on each side.
    assert packing['size'][0]-.006 > .130/2+.010
    assert packing['size'][:2]==lid['size'][:2]
    assert all(packing['size'][i]<recycle['size'][i]-.006 for i in (0,1))
    for n in ['packing_box','recycle_box']:
        assert abs(o[n]['xy'][0])+o[n]['size'][0]<.35
        assert abs(o[n]['xy'][1])+o[n]['size'][1]<.60
    xy=d['staging']['packing_lid']['xy']
    assert abs(xy[0])+lid['size'][0]<.35 and abs(xy[1])+lid['size'][1]<.6
    assert xy[0]-lid['size'][0]-(packing['xy'][0]+packing['size'][0])==pytest.approx(.035)
    assert xy[0]<.06  # Avoid the native far-forward elbow-straight limit.

@pytest.mark.parametrize('variant',list('ABC'))
@pytest.mark.parametrize('seed',[4201,4202,4203])
def test_e39_staging_cradles_are_physical_and_paired(variant,seed):
    base=load('E39',variant,seed,BINDINGS,verify_files=False)
    for condition in ('I','E'):
        scene=build_execution_scene(base,condition=condition,seed=seed,revision='embodied50-execution-v3-20261102')
        stages=scene['execution_design']['staging'];seen=set()
        for stage in stages.values():
            for side,name in stage['support_by_hand'].items():
                assert name not in seen;seen.add(name)
                fixture=scene['fixtures'][int(name.removeprefix('fixture'))]
                assert fixture['type']=='box'
                assert fixture['xy']==stage['xy_by_hand'][side]
                assert fixture['z']+fixture['size'][2]==pytest.approx(stage['surface_z'])
                assert fixture['z']-fixture['size'][2]==pytest.approx(.8)
                assert fixture['size'][:2]==[.004,.015]
        assert len(seen)==6


@pytest.mark.parametrize('condition',['I','E'])
def test_e20_cover_has_real_top_pinch_tab_without_changing_closing_plane(condition):
    s=build_execution_scene(load('E20','A',4201,BINDINGS,verify_files=False),condition=condition)
    d=s['execution_design'];lid=next(o for o in s['objects']if o['id']=='compartment_lid')
    assert lid['collision_shapes'][0]['size']==[.195,.065,.003]
    assert lid['collision_shapes'][1]['size']==[.010,.022,.018]
    assert d['grasps']['compartment_lid']==dict(local=[0,0,.025],jaw_axis_local=[1,0,0])
    assert d['packages'][0]['lid_local_center']==[0,0,.021]
    assert lid['local_bounds_center']==[0,0,.018]
    assert lid['center_z']-.003==pytest.approx(lid['bottom'])



def test_e39_grasp_tab_envelope_mass_initial_pose_and_protective_clearance():
    scene=build_execution_scene(load('E39','A',4201,BINDINGS,verify_files=False),condition='I',seed=4201,revision='embodied50-execution-v3-20261102')
    d=scene['execution_design'];o=next(o for o in scene['objects'] if o['id']=='work_tray')
    assert o['size'][:2]==[.065,.185]
    assert o['center_z']==pytest.approx(o['bottom']+.018)
    assert o['local_bounds_center'][2]-o['size'][2]==pytest.approx(-.018)
    assert o['local_bounds_center'][2]+o['size'][2]==pytest.approx(.042)
    p=next(p for p in d['packages'] if 'work_tray' in p['members'])
    assert 2*o['size'][2]<p['upper'][2]-p['lower'][2]
    assert o['physical_mass_kg']==pytest.approx(.18)
    assert d['grasps']['work_tray']['local']==[-.055,0,.030]
    assert d['grasps']['work_tray']['hand']=='left'


@pytest.mark.parametrize('condition',['I','E'])
@pytest.mark.parametrize('variant',list('ABC'))
@pytest.mark.parametrize('seed',[4201,4202,4203])
def test_e39_receiving_footprint_clears_fixed_assets(condition,variant,seed):
    import numpy as np
    s=build_execution_scene(load('E39',variant,seed,BINDINGS,verify_files=False),condition=condition,seed=seed)
    objects={o['id']:o for o in s['objects']}
    delivered=objects[s['execution_design']['delivery_actor']]
    fixed=[(f['xy'],f['size'][:2]) for f in s['fixtures']]
    fixed += [(objects[n]['xy'],objects[n]['size'][:2]) for n in s['execution_design']['reference_objects']]
    for z in s['zones']:
        if not z['id'].startswith('delivery_'):continue
        assert z['surface_z']==pytest.approx(.8)
        for xy,half in fixed:
            separation=np.abs(np.asarray(z['xy'])-xy)-np.asarray(delivered['size'][:2])-half
            assert np.max(separation)>.005, (condition,variant,seed,z['id'],xy,separation)


@pytest.mark.parametrize('variant',list('ABC'))
def test_e39_v3_layout_adaptation_only_translates_released_group_reset_x(variant):
    from videoicl_isaaclab.execution_design import REVISION_V2,REVISION_V3
    base=load('E39',variant,4201,BINDINGS,verify_files=False)
    old=build_execution_scene(base,condition='I',seed=4201,revision=REVISION_V2)
    new=build_execution_scene(base,condition='I',seed=4201,revision=REVISION_V3)
    names={'work_tray','reference_tray','protective_box','protective_box_lid',*new['execution_design']['target_members'],*new['execution_design']['reference_objects']}
    a={o['id']:o for o in old['objects']};b={o['id']:o for o in new['objects']}
    assert set(a)==set(b)
    for name in a:
        before=dict(a[name]);after=dict(b[name]);p=before.pop('xy');q=after.pop('xy')
        assert before==after
        assert q[1]==p[1]
        assert q[0]==pytest.approx(p[0]-.025 if name in names else p[0])
    assert old['fixtures']==new['fixtures']and old['zones']==new['zones']and old['joints']==new['joints']
