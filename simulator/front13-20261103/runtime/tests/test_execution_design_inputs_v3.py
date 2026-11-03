"""Pair identity, real input changes, and recomputed metric-target regressions."""
from copy import deepcopy
from pathlib import Path
import math
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design import metadata,WORKFLOW_TASKS,REVISION_V3,source_sha256
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs,e26_targets
from videoicl_isaaclab.execution_design_inputs_v3 import RE_TASKS,physical_input_signature,initial_joint_positions
P=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json'

def base(task,variant='A'):return load(task,variant,0,P,verify_files=False)
def apply(s,c,seed=4201):return apply_execution_inputs(s,condition=c,seed=seed,revision=REVISION_V3)
TASKS=[f'E{n:02}'for n in range(1,51)if f'E{n:02}'not in WORKFLOW_TASKS]

@pytest.mark.parametrize('task',TASKS)
def test_paired_inputs_exact_and_source_immutable(task):
    for variant in 'ABC':
        source=base(task,variant);before=deepcopy(source)
        for seed in (4201,4202,4203):
            primary='R'if task in RE_TASKS else'I'
            paired=apply(source,primary,seed);env=apply(source,'E',seed)
            assert physical_input_signature(paired)==physical_input_signature(env)
            assert paired['execution_design']['paired_input_identity']==env['execution_design']['paired_input_identity']
            assert env['execution_design']['environment_base']==primary
            assert env['table_visual'] and 'table_visual'not in paired
            assert 'table_surface'not in env
            assert not paired['release_ready'] and not env['release_ready']
            if primary=='I':assert physical_input_signature(paired)!=physical_input_signature(source)
            elif task in ('E44','E47'):
                # These two source-described passive fixtures were missing
                # from the old canonical scene. They change real geometry,
                # while preserving all original materials/mechanisms/goals.
                assert physical_input_signature(paired)!=physical_input_signature(source)
                assert paired['fixtures']and paired['fixtures']!=source.get('fixtures')
                for key in('objects','mechanisms','goals'):
                    assert paired[key]==source[key]
            else:assert physical_input_signature(paired)==physical_input_signature(source)
        assert source==before

@pytest.mark.parametrize('task',sorted(RE_TASKS))
def test_re_input_fixed_across_seeds_and_does_not_invent_I(task):
    a,b=apply(base(task),'R',1),apply(base(task),'E',999)
    assert physical_input_signature(a)==physical_input_signature(b)
    assert a['execution_design']['paired_input_identity']==b['execution_design']['paired_input_identity']
    with pytest.raises(ValueError):apply(base(task),'I')

@pytest.mark.parametrize('task',['E07','E35'])
def test_size_rank_and_physical_mesh_scale_match(task):
    source=base(task);changed=apply(source,'I')
    old={o['id']:o for o in source['objects']};new={o['id']:o for o in changed['objects']}
    assert sorted(old,key=lambda n:old[n]['size'][0])==sorted(new,key=lambda n:new[n]['size'][0])
    assert all(new[n]['size']!=old[n]['size'] for n in old)
    for n in old:assert new[n]['source_asset']==old[n]['source_asset']
    if task=='E35':
        zones={z['id']:z for z in changed['zones']};height=.8
        for g in changed['goals']:
            assert zones[g['target']]['surface_z']==pytest.approx(height)
            height+=2*new[g['object']]['size'][2]

@pytest.mark.parametrize('variant',['A','B','C'])
def test_input_relative_targets_are_recomputed(variant):
    s=apply(base('E11',variant),'I');objects=s['objects'][1:]
    order=sorted(objects,key=lambda o:o['xy'][0],reverse=True)
    grid=[[o['id']for o in sorted(row,key=lambda o:o['xy'][1],reverse=True)]for row in(order[:2],order[2:])]
    expected={'A':grid,'B':[[grid[1][0],grid[0][0]],[grid[1][1],grid[0][1]]],'C':[r[::-1]for r in grid]}[variant]
    cells=s['semantic']['grid_cells']
    assert s['semantic']['mapping']=={expected[r][c]:cells[r][c]for r in range(2)for c in range(2)}
    tower=apply(base('E14',variant),'I');top=sorted(tower['objects'],key=lambda o:o['bottom'],reverse=True)
    names=[o['id']for o in top]
    expected={'A':[names[1],names[0],names[2],names[3]],'B':[names[0],names[2],names[1],names[3]],'C':names[::-1]}[variant]
    assert [g['object']for g in tower['goals'][4:]]==expected[::-1]


def test_plank_lengths_and_metric_endpoints_change_together():
    s=apply(base('E41'),'I');old=base('E41');objects={o['id']:o for o in s['objects']}
    assert s['semantic']['lengths']!=old['semantic']['lengths']
    for n,o in objects.items():
        field='end_points'if n.endswith('_ref')else'start_points'
        assert abs(s['semantic'][field][n][0])==o['size'][0]
        assert s['semantic']['lengths'][n]==2*o['size'][0]
    for ref,piece in s['semantic']['mapping'].items():
        zone=next(z for z in s['zones']if z['id']==piece+'_target')
        # A one-mm physical endpoint gap; no stale source-length target.
        assert objects[ref]['xy'][0]-objects[ref]['size'][0]-(zone['xy'][0]+objects[piece]['size'][0])==pytest.approx(.001)


def test_drawer_reset_is_real_bounded_and_revision_scoped():
    s=apply(base('E30'),'I');m=s['mechanisms'][0];names=['joint_1','joint_2']
    assert initial_joint_positions(s,m,names)==m['initial_joint_positions']
    for bad in(-1,100,float('nan'),True):
        b=deepcopy(m);b['initial_joint_positions']['joint_1']=bad
        with pytest.raises(ValueError):initial_joint_positions(s,b,names)
    with pytest.raises(ValueError):initial_joint_positions(base('E30'),m,names)
    with pytest.raises(ValueError):initial_joint_positions(s,m,['unknown'])


def test_v3_bell_scoring_uses_actual_rendered_new_digits():
    for variant in 'ABC':
        s=apply(base('E26',variant),'I',7)
        assert s['semantic']['digit_cards']==dict(left=3,right=2)
        assert e26_targets(s)=={'A':dict(left=3,right=2),'B':dict(left=2,right=3),'C':dict(left=5,right=0)}[variant]


def test_old_unsupported_input_stays_fail_closed_in_explicit_v2():
    with pytest.raises(NotImplementedError):
        apply_execution_inputs(base('E41'),condition='I',seed=1,revision='embodied50-execution-v2-20261102')


def test_real_loader_preserves_applied_pairing_not_empty_contract(tmp_path):
    import json
    binding=json.loads(P.read_text());binding['execution_design']=dict(revision=REVISION_V3,condition='E')
    path=tmp_path/'binding.json';path.write_text(json.dumps(binding))
    for task in ('E12','E04','E01'):
        s=load(task,'A',4201,path,verify_files=False)
        assert s['execution_design']['environment_changes']
        assert s['execution_design']['revision']==REVISION_V3
        assert s['execution_design']['source_sha256']==source_sha256(REVISION_V3)
    for task in ('E12','E04'):
        s=load(task,'A',4201,path,verify_files=False)
        assert s['execution_design']['environment_changes']==['table_visual']
        assert s['execution_design']['paired_physical_input_sha256']==physical_input_signature(s)


@pytest.mark.parametrize('variant',['A','B','C'])
def test_swap_and_transfer_goals_follow_changed_initial_pose(variant):
    s=apply(base('E15',variant),'I');objects={o['id']:o for o in s['objects']};names=list(objects)
    zones={z['id']:z for z in s['zones']};other=dict(zip(names,names[::-1]))
    for n in names:
        pos=objects[other[n] if variant in ('A','C')else n]['xy']
        yaw=objects[other[n] if variant in ('B','C')else n]['yaw']
        assert zones[n+'_target']['xy']==pos
        assert next(g for g in s['goals']if g['target']==n+'_target')['yaw']==yaw
    s=apply(base('E16',variant),'I');objects={o['id']:o for o in s['objects']};names=s['semantic']['groups']['pieces']
    center=[sum(objects[n]['xy'][i]for n in names)/3 for i in range(2)]
    for n in names:
        goal=s['semantic']['targets'][n]
        assert goal['yaw']==pytest.approx(objects[n]['yaw']+(math.pi/2 if variant=='B'else 0))
        expected=[(objects[n]['xy'][i]-center[i])*(-1 if variant=='C'and i==0 else 1) for i in range(2)]
        assert [goal['xy'][i]-objects['tray']['xy'][i]for i in range(2)]==pytest.approx(expected)


@pytest.mark.parametrize('variant',['A','B','C'])
def test_bowl_plate_changed_support_has_matching_reference_goal(variant):
    original=base('E31',variant);s=apply(original,'I')
    support=next(o for o in s['objects']if o['id']==s['semantic']['support'])
    zone=next(z for z in s['zones']if z['id']=='support_center')
    assert zone['xy']==support['xy']
    assert zone['xy']!=original['zones'][0]['xy']


def test_e32_nearer_column_keeps_input_pair_and_target_categories():
    source=base('E32','B');original=deepcopy(source)
    changed=apply(source,'I');env=apply(source,'E');ref=apply(source,'R')
    assert source==original
    assert physical_input_signature(changed)==physical_input_signature(env)
    assert physical_input_signature(ref)==physical_input_signature(source)
    ids=('sprite_bottle','cola_bottle','pink_cube')
    assert max(o['xy'][0]for o in changed['objects']if o['id']in ids)<=.16
    assert changed['semantic']['selected']=='pink_cube'
    cube=next(o for o in changed['objects']if o['id']=='pink_cube')
    zone=next(z for z in changed['zones']if z['id']==changed['goals'][0]['target'])
    assert any(abs(cube['xy'][i]-zone['xy'][i])>zone['half_size'][i]+cube['size'][i]for i in range(2))


def test_e32_new_far_source_slot_does_not_overlap_unselected_shoe():
    import numpy as np
    spec=apply(base('E32','B'),'I');objects={o['id']:o for o in spec['objects']}
    shoe=objects['shoe'];cube=objects['pink_cube'];theta=shoe['yaw']
    rotation=np.array([[np.cos(theta),-np.sin(theta)],[np.sin(theta),np.cos(theta)]])
    extent=np.abs(rotation)@np.asarray(shoe['size'][:2])
    assert np.any(abs(np.asarray(cube['xy'])-shoe['xy'])>extent+cube['size'][:2]+.015)
