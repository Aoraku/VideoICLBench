from copy import deepcopy
from types import SimpleNamespace
import pytest
from videoicl_isaaclab.engineering_checkpoint import _hash,identity,reseal
from videoicl_isaaclab.engineering_render_checkpoint_fixture import materialize,SCHEMA


def fixture(task='E44',held=True):
    cfg=dict(physics=dict(render_hz=1,dt=.004),control=dict(public_gripper_reference_speed_m_s=.01))
    spec=dict(id=task,variant='A',seed=4201,execution_design=dict(assignment_identity_sha256='assignment',source_sha256='source'),embodiment_config_sha256=_hash(cfg),objects=[dict(id='paper',mass=.08)])
    if task in('E47','E48','E49','E50'):
        spec['semantic']=dict(engineering_card_approximation=dict(schema='engineering-practical-card-1mm-v1',source_exact_geometry=False))
        from videoicl_isaaclab.execution_design_thin_cooking import SOURCES
        path=next(iter(SOURCES));spec['objects'][0].update(size=[.04415271966527,.0315,.0005],source_asset=dict(relative_path=path,sha256=SOURCES[path]))
    c=SimpleNamespace(scene=SimpleNamespace(spec=spec,embodiment=SimpleNamespace(config=cfg)))
    old=deepcopy(cfg);old['physics']['render_hz']=5
    ident=identity(c);ident['embodiment_config_sha256']=_hash(old)
    cp=reseal(dict(schema='engineering-native-checkpoint-v1',diagnostic_only=True,identity=ident,source=dict(steps=132),controller=dict(grips=dict(left=0. if held else .04,right=.04)),readback=dict(object_grasps=dict(paper=[held,False])),robots=dict(left=dict(joint_pos=[.1,.2],joint_vel=[.03,.04],drive_targets=[.5,.6])),limitations=[]))
    r=dict(schema=SCHEMA,diagnostic_only=True,from_render_hz=5,to_render_hz=1,checkpoint=cp)
    return c,r,old


def test_preserves_held_payload_drives_velocities_and_source_actions():
    c,r,_=fixture();before=deepcopy(c.scene.spec);result=materialize(c,r)
    for key in ('robots','controller','readback','source'):assert result[key]==r['checkpoint'][key]
    assert result['identity']==identity(c)
    receipt=result['render_cadence_migration_receipt']
    assert receipt['source_identity']==r['checkpoint']['identity']
    assert receipt['source_native_checkpoint_integrity_sha256']==r['checkpoint']['checkpoint_sha256']
    assert receipt['changed_config_fields']==['physics.render_hz']
    assert receipt['history_reconstructed']is False
    assert c.scene.spec==before and c.scene.embodiment.config['physics']['render_hz']==1


@pytest.mark.parametrize('task',[f'E{i:02d}'for i in range(14,26)])
def test_front25_native_cadence_migration_preserves_every_physical_field(task):
    c,r,_=fixture(task)
    cp=r['checkpoint'];cp.pop('checkpoint_sha256')
    cp['mechanisms']={'cabinet':{'joint_pos':[.094,0.],'joint_vel':[.001,0.]}}
    cp['source'].update(physics_ticks=13202,dt=.004)
    r['checkpoint']=reseal(cp)
    result=materialize(c,r)
    for key in r['checkpoint']:
        if key not in ('identity','limitations','checkpoint_sha256'):
            assert result[key]==r['checkpoint'][key]
    assert result['identity']==identity(c)


@pytest.mark.parametrize('kind',('source','physical','extra_profile','tamper','scope'))
def test_rejects_non_cadence_changes(kind):
    c,r,_=fixture()
    if kind=='source':c.scene.spec['execution_design']['source_sha256']='changed'
    elif kind=='physical':c.scene.spec['objects'][0]['mass']=.09
    elif kind=='extra_profile':
        c.scene.embodiment.config['physics']['dt']=.008;c.scene.spec['embodiment_config_sha256']=_hash(c.scene.embodiment.config)
    elif kind=='tamper':r['checkpoint']['robots']['left']['joint_pos'][0]=.9
    else:c.scene.spec['id']='E43'
    with pytest.raises(ValueError):materialize(c,r)


@pytest.mark.parametrize('task',['E47','E48','E49','E50'])
def test_nested_contact_hold_preserves_independent_admission(task):
    c,r,old=fixture(task,held=False);cp=r['checkpoint'];c.scene.embodiment.config['control'].update(public_gripper_payload_contact_hold=True,public_gripper_payload_preload_m=.00005);c.scene.spec['embodiment_config_sha256']=_hash(c.scene.embodiment.config)
    r['checkpoint']=dict(schema='engineering-practical-card-contact-hold-migration-v1',diagnostic_only=True,checkpoint=cp,source_profile=old)
    result=materialize(c,r)
    assert result['identity']==identity(c) and result['robots']==cp['robots']
    r['checkpoint']['checkpoint']['controller']['grips']['left']=0.
    r['checkpoint']['checkpoint']=reseal(r['checkpoint']['checkpoint'])
    with pytest.raises(ValueError,match='Empty open'):materialize(c,r)


def pinned_fixture(tmp_path,monkeypatch,hz=15):
    import json,hashlib
    from videoicl_isaaclab import engineering_render_checkpoint_fixture as module
    c,r,old=fixture('E17');old['physics']['render_hz']=hz
    root=tmp_path/'engineering';frozen=root/'execution-design-v3-20261102-e17-pinned-s4201'
    path=frozen/'runtime/configs/embodiments/franka.json';path.parent.mkdir(parents=True)
    raw=json.dumps(old,indent=2).encode();path.write_bytes(raw);raw_sha=hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(module,'ENGINEERING_ROOT',root)
    cp=r['checkpoint'];cp['identity']['embodiment_config_sha256']=raw_sha;r['checkpoint']=reseal(cp)
    r.update(from_render_hz=hz,source_profile_pin=dict(path=str(path),sha256=raw_sha),source_checkpoint_path=str(frozen/'result/room-00-E17-A-s4201/engineering-reference/checkpoints/failure-after-last-action.private.json'))
    return c,r,old,path


@pytest.mark.parametrize('hz',[5,15])
def test_explicit_raw_profile_pin_preserves_native_state_and_only_changes_render(tmp_path,monkeypatch,hz):
    c,r,old,path=pinned_fixture(tmp_path,monkeypatch,hz)
    result=materialize(c,r)
    for key in('robots','controller','readback','source'):assert result[key]==r['checkpoint'][key]
    receipt=result['render_cadence_migration_receipt']
    assert receipt['source_profile_pin_verified']is True and receipt['source_profile_identity_encoding']=='raw_bytes_sha256'
    assert receipt['from_render_hz']==hz and receipt['source_profile_sha256']==_hash(old)
    assert receipt['source_profile_raw_sha256']==r['checkpoint']['identity']['embodiment_config_sha256']
    assert result['identity']==identity(c)


@pytest.mark.parametrize('kind',['sha','identity','control','outside','symlink','root'])
def test_raw_profile_pin_rejects_drift_or_unbound_source(tmp_path,monkeypatch,kind):
    c,r,old,path=pinned_fixture(tmp_path,monkeypatch)
    if kind=='sha':r['source_profile_pin']['sha256']='0'*64
    elif kind=='identity':r['checkpoint']['identity']['embodiment_config_sha256']='0'*64;r['checkpoint']=reseal(r['checkpoint'])
    elif kind=='control':c.scene.embodiment.config['control']['public_gripper_reference_speed_m_s']=.02;c.scene.spec['embodiment_config_sha256']=_hash(c.scene.embodiment.config)
    elif kind=='outside':r['source_profile_pin']['path']=str(tmp_path/'elsewhere.json')
    elif kind=='root':r['source_checkpoint_path']=r['source_checkpoint_path'].replace('e17-pinned-s4201','other-s4201')
    else:
        other=tmp_path/'outside.json';other.write_bytes(path.read_bytes());path.unlink();path.symlink_to(other)
    with pytest.raises(ValueError):materialize(c,r)


def test_fifteen_hz_without_byte_pin_is_refused():
    c,r,_=fixture('E17');r['from_render_hz']=15
    with pytest.raises(ValueError,match='pinned source'):materialize(c,r)
