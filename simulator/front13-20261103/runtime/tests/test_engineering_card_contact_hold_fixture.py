from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace as S
import json
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_practical_cards import configure_spec
from videoicl_isaaclab.engineering_checkpoint import _hash,identity,reseal
from videoicl_isaaclab.engineering_e50_contact_hold_fixture import materialize

V=Path(__file__).resolve().parents[2]/'verification/task-design-revision-20261102'
RT=Path(__file__).resolve().parents[1]


def case(task,monkeypatch):
    monkeypatch.delenv('VIC_ENGINEERING_PRACTICAL_CARD_THICKNESS',raising=False)
    spec=load(task,'A',4201,V/'e38-e50-matrix/bindings-R.private.json',verify_files=False);configure_spec(spec)
    old=json.loads((RT/'configs/thin-franka-gripper-reference-v1.json').read_text());old['physics']['render_hz']=5
    spec['embodiment_config_sha256']=_hash(old)
    cp=reseal(dict(identity=identity(S(scene=S(spec=spec))),controller=dict(grips=dict(left=.04,right=.04)),readback=dict(object_grasps={'card':[False,False]}),limitations=[]))
    new=deepcopy(old);new['control'].update(public_gripper_payload_contact_hold=True,public_gripper_payload_preload_m=.00005)
    spec['embodiment_config_sha256']=_hash(new)
    controller=S(scene=S(spec=spec,embodiment=S(config=new)))
    recipe=dict(schema='engineering-practical-card-contact-hold-migration-v1',diagnostic_only=True,checkpoint=cp,source_profile=old)
    return controller,recipe


@pytest.mark.parametrize('task',('E47','E48','E49','E50'))
def test_practical_source_sha_pinned_open_hands_allow_only_the_two_control_fields(task,monkeypatch):
    c,r=case(task,monkeypatch);cp=materialize(c,r)
    assert cp['identity']==identity(c)
    assert cp['controller']==r['checkpoint']['controller']


@pytest.mark.parametrize('fault',('no_marker','source_sha','grasped','gain'))
def test_contact_migration_rejects_source_and_physics_drift(fault,monkeypatch):
    c,r=case('E50',monkeypatch)
    if fault=='no_marker':c.scene.spec['semantic'].pop('engineering_card_approximation')
    elif fault=='source_sha':c.scene.spec['objects'][0]['source_asset']['sha256']='0'*64
    elif fault=='grasped':
        r['checkpoint']['readback']['object_grasps']['card'][0]=True;r['checkpoint']=reseal(r['checkpoint'])
    else:c.scene.embodiment.config['actuators']['gripper']['stiffness']=123
    with pytest.raises(ValueError):materialize(c,r)


@pytest.mark.parametrize('actual_q,accepted',[(.0002,True),(.004,False)])
def test_empty_fully_closed_pusher_is_allowed_but_partial_closure_rejected(actual_q,accepted,monkeypatch):
    c,r=case('E47',monkeypatch);cp=r['checkpoint'];cp['controller']['grips']['left']=0.
    cp['controller']['gripper_reference']={'left':[[0.,0.]]}
    cp['robots']={'left':dict(joint_names=r['source_profile']['gripper']['joints'],joint_pos=[actual_q,actual_q],drive_targets=dict(position=[0.,0.]))}
    r['checkpoint']=reseal(cp)
    if accepted:assert materialize(c,r)['controller']==cp['controller']
    else:
        with pytest.raises(ValueError,match='Partially closed'):materialize(c,r)
