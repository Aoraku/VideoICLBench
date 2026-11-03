"""New instance geometry must travel with grasp/semantic metrics and I/E pairing."""
from copy import deepcopy
from pathlib import Path
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_inputs_v3 import apply_execution_inputs_v3,physical_input_signature
from videoicl_isaaclab.execution_design_instances_v3 import GROUPS
P=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json'

@pytest.mark.parametrize('task',sorted(GROUPS))
@pytest.mark.parametrize('variant',list('ABC'))
def test_actual_dimensions_and_metric_points_change_together(task,variant):
    base=load(task,variant,0,P,verify_files=False);saved=deepcopy(base)
    for seed in (4201,4202,4203):
        primary=apply_execution_inputs_v3(base,condition='I',seed=seed)
        paired=apply_execution_inputs_v3(base,condition='E',seed=seed)
        old={o['id']:o for o in base['objects']};new={o['id']:o for o in primary['objects']}
        assert physical_input_signature(primary)==physical_input_signature(paired)
        assert primary['semantic'].get('selected')==base['semantic'].get('selected')
        for name in GROUPS[task]:
            a,b=old[name],new[name];scale=b['execution_instance']['scale']
            assert scale!=1 and b['size']==pytest.approx([x*scale for x in a['size']])
            assert a['source_asset']==b['source_asset']
            assert b['mass']==pytest.approx(a['mass']*scale**3)
            for key in ('grasp_point_local','grasp_point','working_point','local_bounds_center'):
                if key in a:assert b[key]==pytest.approx([x*scale for x in a[key]])
            if name in base['semantic'].get('handle_points',{}):
                assert primary['semantic']['handle_points'][name]==pytest.approx([x*scale for x in base['semantic']['handle_points'][name]])
            if task=='E38':assert b['hole_radius']>primary['semantic']['post_radius']
        if task=='E31':
            support=new[primary['semantic']['support']]
            zone=next(z for z in primary['zones']if z['id']=='support_center')
            assert zone['surface_z']==pytest.approx(support['bottom']+2*support['size'][2])
        fixed=apply_execution_inputs_v3(base,condition='R',seed=seed)
        assert physical_input_signature(fixed)==physical_input_signature(base)
    assert base==saved

@pytest.mark.parametrize('task',['E26','E29','E30','E35','E37','E41','E44','E47','E48','E49','E50'])
def test_explicit_other_task_contracts_are_not_silently_scaled(task):
    base=load(task,'A',0,P,verify_files=False)
    condition='R'if task in ('E29','E37','E44','E47','E48','E49','E50')else'I'
    spec=apply_execution_inputs_v3(base,condition=condition,seed=4201)
    assert all('execution_instance'not in o for o in spec['objects'])

@pytest.mark.parametrize('variant',list('ABC'))
@pytest.mark.parametrize('seed',(4201,4202,4203))
def test_e33_measured_hulls_follow_actual_instance_scale(tmp_path,variant,seed):
    import json,numpy as np
    from videoicl_isaaclab.e33_source_geometry import validate_e33_geometry
    from videoicl_isaaclab.execution_design import REVISION_V3
    raw=json.loads(P.read_text());raw['execution_design']={'revision':REVISION_V3,'condition':'I'}
    binding=tmp_path/'binding.json';binding.write_text(json.dumps(raw))
    changed=load('E33',variant,seed,binding,verify_files=False)
    objects={o['id']:o for o in changed['objects']};validate_e33_geometry(objects,changed['semantic'])
    manifest=json.loads((P.parents[1]/'configs/source_geometry/e33/e33-acceptance-geometry.json').read_text())
    for name in changed['semantic']['groups']['bottles']:
        obj=objects[name];hull=obj['source_containment_hull'];scale=obj['execution_instance']['scale']
        assert np.asarray(hull['vertices_local'])==pytest.approx(np.asarray(manifest['objects'][name]['vertices_local'])*scale)
        assert hull['descriptor_half_size']==obj['size']
        assert hull['instance_derivation']['scaled_hull_sha256']
    raw['execution_design']['condition']='E';binding.write_text(json.dumps(raw))
    paired=load('E33',variant,seed,binding,verify_files=False)
    assert physical_input_signature(changed)==physical_input_signature(paired)


def test_nonzero_cargo_grasp_metric_scales_but_jaw_direction_does_not():
    from copy import deepcopy
    from pathlib import Path
    from videoicl_isaaclab.realworld_scenes import load
    from videoicl_isaaclab.execution_design_instances_v3 import apply_instance_variation
    for task in ('E28','E46'):
        spec=load(task,'A',0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False)
        grasps=spec['semantic']['cargo_grasps']
        for grasp in grasps.values():grasp['local']=[.01,-.02,.03]
        before=deepcopy(grasps);change=apply_instance_variation(spec,4201)
        factors={r['object']:r['scale']for r in change['objects']}
        for name,grasp in grasps.items():
            assert grasp['local']==[x*factors[name]for x in before[name]['local']]
            assert grasp['jaw_axis_local']==before[name]['jaw_axis_local']
