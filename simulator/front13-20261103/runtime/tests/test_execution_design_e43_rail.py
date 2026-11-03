from copy import deepcopy
import pytest
from videoicl_isaaclab.execution_design_e43_rail import configure_spec,validated_settings,apply_usd,SETTINGS


def scene():
    return dict(id='E43',execution_design=dict(revision='embodied50-execution-v3-20261102'),
        joints=[dict(type='prismatic',child='gate',axis='Y',limits=[-.09,0])])


def test_only_passive_resistance_added_to_original_gate():
    spec=scene();before=deepcopy(spec);configure_spec(spec)
    joint=spec['joints'][0];assert joint.pop('passive_rail')==SETTINGS
    assert spec==before


def test_drive_has_no_position_lock_and_only_dissipative_parameters():
    spec=scene();configure_spec(spec);values={}
    class Drive:
        def __getattr__(self,name):
            if name=='CreateTargetPositionAttr':pytest.fail('No closed-position target may be authored')
            return lambda x:values.__setitem__(name,x)
    class API:
        @staticmethod
        def Apply(prim,axis):assert axis=='linear';return Drive()
    from types import SimpleNamespace
    apply_usd(SimpleNamespace(GetPrim=lambda:object()),spec,spec['joints'][0],SimpleNamespace(DriveAPI=API))
    assert values['CreateStiffnessAttr']==values['CreateTargetVelocityAttr']==0
    assert values['CreateDampingAttr']==1000 and values['CreateMaxForceAttr']==.08


def test_other_tasks_or_existing_position_drive_fail_closed():
    spec=scene();configure_spec(spec)
    for mutation in ('task','parent','spring','damping'):
        changed=deepcopy(spec);j=changed['joints'][0]
        if mutation=='task':changed['id']='E46'
        elif mutation=='parent':j['parent']='launcher'
        elif mutation=='spring':j['spring']={'stiffness':1}
        else:j['passive_rail']['damping_n_s_per_m']=2000
        with pytest.raises(ValueError):validated_settings(changed,j)


def test_source_loader_applies_only_after_v3_contract_identity_exists(monkeypatch):
    from pathlib import Path
    from videoicl_isaaclab.realworld_scenes import load
    from videoicl_isaaclab.execution_design_inputs_v3 import physical_input_signature,apply_execution_inputs_v3
    monkeypatch.setenv('VIC_ENGINEERING_E43_PASSIVE_RAIL','1')
    binding=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json'
    base=load('E43','A',0,binding,verify_files=False)
    spec=apply_execution_inputs_v3(base,condition='I',seed=4201)
    gate=next(j for j in spec['joints']if j.get('child')=='gate')
    assert gate['passive_rail']==SETTINGS
    assert spec['execution_design']['paired_physical_input_sha256']==physical_input_signature(spec)


def test_float32_usd_readback_keeps_strict_passive_semantics():
    import struct
    from videoicl_isaaclab.execution_design_e43_rail import native_readback_matches
    values=dict(stiffness_n_per_m=0.,target_velocity_m_s=0.,damping_n_s_per_m=1000.,
        maximum_resistance_n=struct.unpack('f',struct.pack('f',.08))[0],position_target_authored=False)
    assert native_readback_matches(values)
    for field,value in [('position_target_authored',True),('stiffness_n_per_m',.001),
                        ('target_velocity_m_s',.0001),('maximum_resistance_n',.081)]:
        assert not native_readback_matches(dict(values,**{field:value}))
