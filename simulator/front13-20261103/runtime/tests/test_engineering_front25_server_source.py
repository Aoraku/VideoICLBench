"""Server-local archive scope, literal identity and command-prefix evidence."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import shutil
import pytest
from test_engineering_checkpoint import all_writes
from test_engineering_checkpoint import Asset
from test_engineering_front25_fixture import fixture
from videoicl_isaaclab import engineering_front25_server_source as source
from videoicl_isaaclab.engineering_front25_fixture import convert


def archive(tmp_path,monkeypatch):
    c,r=fixture();base=tmp_path/'engineering';base.mkdir();monkeypatch.setattr(source,'ENGINEERING_BASE',base)
    root=base/'execution-design-v3-20261102-e24-archived-source-s4201';root.mkdir()
    room='room-00-E24-A-s4201';d=root/'result'/room;d.mkdir(parents=True)
    (root/'exit.private.json').write_text('{"code":2}')
    runtime=Path(__file__).parents[1]
    profile=json.loads((runtime/'configs/embodiments/franka.json').read_text())
    profile.setdefault('author_recording',{})['initial_gripper_commands_m']={'right':.013}
    raw=json.dumps(profile).encode();c.scene.spec['embodiment_config_sha256']=hashlib.sha256(raw).hexdigest()
    profile_path=root/'runtime/configs/embodiments/franka.json';profile_path.parent.mkdir(parents=True);profile_path.write_bytes(raw)
    (d/'scene-input.private.json').write_text(json.dumps(c.scene.spec))
    actions=d/'engineering-reference/demo-actions.private.jsonl';actions.parent.mkdir()
    rows=[]
    for i in range(829):
        rows.append(dict(step_before=i,step_after=i+1,shared_tick_before=840+i*100,
            shared_tick_after=840+(i+1)*100,stage=r['source_counters']['stage'],
            left='GRASP'if i==828 else'STILL',right='STILL'))
    actions.write_text(''.join(json.dumps(row)+'\n'for row in rows))
    r.pop('scene_input');r['server_source']={'engineering_root':str(root),'room_id':room}
    return c,r,root,d,actions,profile_path,rows


def test_stripped_record_hydrates_and_converts_with_hash_count_evidence_only(tmp_path,monkeypatch,capsys):
    c,r,root,d,actions,profile,_=archive(tmp_path,monkeypatch);before=deepcopy(r)
    hydrated=source.hydrate(c,r)
    assert r==before and all_writes(c)==0
    assert hydrated['scene_input']==json.loads((d/'scene-input.private.json').read_text())
    provenance=hydrated['scene_input_provenance']
    assert provenance['literal_remote_scene_input_readback']is True
    assert provenance['server_local_source_verified']is True and provenance['accepted_prefix_verified']is True
    assert hydrated['grips']=={'left':0.,'right':.013}
    evidence=provenance['server_local_evidence']
    assert evidence['accepted_prefix']['action_count']==829
    for entry in evidence.values():
        assert set(entry)<={'sha256','byte_count','action_count'}
        assert len(entry['sha256'])==64
    p=convert(c,hydrated)
    assert p['controller']['grips']==hydrated['grips']and p['state_quality']=='measured_pose_fixture'
    assert 'scene_input'not in p and 'commands'not in p
    assert any('SERVER-LOCALLY'in text for text in p['assumptions'])
    assert not any('NOT literal remote'in text for text in p['assumptions'])
    assert capsys.readouterr().out=='' and all_writes(c)==0


def test_original_grasp_release_walk_changes_only_the_corresponding_arm(tmp_path,monkeypatch):
    c,r,_,_,actions,_,rows=archive(tmp_path,monkeypatch)
    rows[10]['right']='GRASP';rows[20]['right']='RELEASE'
    actions.write_text(''.join(json.dumps(row)+'\n'for row in rows))
    h=source.hydrate(c,r)
    assert h['grips']=={'left':0.,'right':.04}


@pytest.mark.parametrize('case',['relative','wrong_prefix','parent_traversal','wrong_room','wrong_seed','wrong_variant','extra_selector','missing_exit'])
def test_scope_and_old_exit_are_hard_requirements(tmp_path,monkeypatch,case):
    c,r,root,_,_,_,_=archive(tmp_path,monkeypatch)
    if case=='relative':r['server_source']['engineering_root']='relative/archive'
    elif case=='wrong_prefix':r['server_source']['engineering_root']=str(root.parent/'execution-design-v2-other')
    elif case=='parent_traversal':r['server_source']['engineering_root']=str(root/'..'/root.name)
    elif case=='wrong_room':r['server_source']['room_id']='../room-00-E24-A-s4201'
    elif case=='wrong_seed':r['identity']='E24-A-I-s4202'
    elif case=='wrong_variant':r['identity']='E24-B-I-s4201'
    elif case=='extra_selector':r['server_source']['scene_file']='/etc/passwd'
    else:(root/'exit.private.json').unlink()
    with pytest.raises(ValueError):source.hydrate(c,r)
    assert all_writes(c)==0


@pytest.mark.parametrize('target',['root','room','scene','actions','profile','exit'])
def test_no_symlink_escape_or_alias_is_followed(tmp_path,monkeypatch,target):
    c,r,root,d,actions,profile,_=archive(tmp_path,monkeypatch)
    if target=='root':
        alias=root.parent/'execution-design-v3-20261102-alias';alias.symlink_to(root,target_is_directory=True)
        r['server_source']['engineering_root']=str(alias)
    elif target=='room':
        moved=tmp_path/'outside-room';shutil.move(str(d),str(moved));d.symlink_to(moved,target_is_directory=True)
    else:
        path={'scene':d/'scene-input.private.json','actions':actions,'profile':profile,'exit':root/'exit.private.json'}[target]
        moved=tmp_path/('outside-'+target);path.rename(moved);path.symlink_to(moved)
    with pytest.raises(ValueError):source.hydrate(c,r)
    assert all_writes(c)==0


@pytest.mark.parametrize('case',['assignment','source','profile','geometry','catalog','native_geometry','profile_bytes'])
def test_original_source_identity_and_sha_mismatches_fail_closed(tmp_path,monkeypatch,case):
    c,r,_,d,_,profile,_=archive(tmp_path,monkeypatch);spec=json.loads((d/'scene-input.private.json').read_text())
    if case=='assignment':spec['execution_design']['assignment_identity_sha256']='d'*64
    elif case=='source':spec['execution_design']['source_sha256']='d'*64
    elif case=='profile':spec['embodiment_config_sha256']='d'*64
    elif case=='geometry':spec['objects'][0]['size'][0]+=.001
    elif case=='catalog':spec['provenance']['catalog_sha256']='d'*64
    elif case=='native_geometry':c.scene.spec['objects'][0]['size'][0]+=.001
    else:profile.write_text('{}')
    (d/'scene-input.private.json').write_text(json.dumps(spec))
    with pytest.raises(ValueError):source.hydrate(c,r)
    assert all_writes(c)==0


@pytest.mark.parametrize('case',['gap','duplicate','missing_command','wrong_tick','partial','missing_profile','missing_actions'])
def test_unreliable_command_chain_keeps_unknown_right_without_guessing(tmp_path,monkeypatch,case):
    c,r,_,_,actions,profile,rows=archive(tmp_path,monkeypatch)
    if case=='gap':rows.pop(12)
    elif case=='duplicate':rows.insert(12,deepcopy(rows[11]))
    elif case=='missing_command':rows[12].pop('right')
    elif case=='wrong_tick':rows[12]['shared_tick_before']+=1
    elif case=='partial':rows=rows[:12]
    elif case=='missing_profile':profile.unlink()
    else:actions.unlink()
    if case!='missing_actions':actions.write_text(''.join(json.dumps(row)+'\n'for row in rows))
    h=source.hydrate(c,r)
    assert h['grips']=={'left':0.,'right':None}
    assert h['scene_input_provenance']['server_local_source_verified']is True
    assert h['scene_input_provenance']['accepted_prefix_verified']is False
    assert h['grip_provenance']['right']['inference_reliable']is False
    assert convert(c,h)['controller']['grips']['right']==pytest.approx(.039998818188905716)


def test_known_command_conflict_and_unverified_literal_flag_are_rejected(tmp_path,monkeypatch):
    c,r,_,_,actions,_,rows=archive(tmp_path,monkeypatch)
    rows[-1]['left']='RELEASE';actions.write_text(''.join(json.dumps(row)+'\n'for row in rows))
    with pytest.raises(ValueError,match='conflicts'):source.hydrate(c,r)
    # A literal provenance claim without server-local verification does not
    # disable the existing fixture identity/admission checks.
    c,r=fixture();r['scene_input_provenance']['literal_remote_scene_input_readback']=True
    with pytest.raises(ValueError):convert(c,r)


def terminal_archive(tmp_path,monkeypatch):
    c,r,root,d,actions,profile,rows=archive(tmp_path,monkeypatch)
    r['server_source']['measurement']='terminal_boundary'
    final=dict(state=deepcopy(r['state_task']),robot_feedback=deepcopy(r['robot_feedback_same_tick']),
               actions=829,native_physics_tick=83740)
    r['state_task']=None;r['robot_feedback_same_tick']=None;r['mechanisms']=None
    path=d/'reference-final-state.private.json';path.write_text(json.dumps(final))
    return c,r,path,final


def test_terminal_boundary_hydrates_all_measurements_from_one_timed_file(tmp_path,monkeypatch):
    c,r,path,final=terminal_archive(tmp_path,monkeypatch)
    h=source.hydrate(c,r)
    assert h['state_task']==final['state']and h['robot_feedback_same_tick']==final['robot_feedback']
    assert h['mechanisms']=={}and h['scene_input_provenance']['terminal_measurement_hydrated']is True
    assert h['scene_input_provenance']['server_local_evidence']['terminal_boundary']['action_count']==829
    for side in ('left','right'):
        measured=final['robot_feedback']['arms'][side]
        assert h['robot_diagnostics'][side]['arm_joints']['positions_rad']==measured['joint_positions_rad']
        assert h['robot_diagnostics'][side]['finger_joints']['velocities_m_s']==measured['measured_sensors']['finger_joint_velocities_m_s']['value']
    assert convert(c,h)['source']['steps']==829
    assert all_writes(c)==0


@pytest.mark.parametrize('fault',['actions','tick','object','arm','arm_qd','finger_qd','local_q','missing_file'])
def test_terminal_measurement_never_mixes_ticks_or_fills_missing_sensors(tmp_path,monkeypatch,fault):
    c,r,path,final=terminal_archive(tmp_path,monkeypatch)
    if fault=='actions':final['actions']=828
    elif fault=='tick':final['native_physics_tick']=83739
    elif fault=='object':final['state'].pop('lid')
    elif fault=='arm':final['robot_feedback']['arms'].pop('right')
    elif fault=='arm_qd':final['robot_feedback']['arms']['left']['measured_sensors']['joint_velocities_rad_s']['available']=False
    elif fault=='finger_qd':final['robot_feedback']['arms']['right']['measured_sensors']['finger_joint_velocities_m_s']['value'][0]=float('nan')
    elif fault=='local_q':r['robot_diagnostics']['left']['arm_joints']['positions_rad'][0]+=.1
    if fault=='missing_file':path.unlink()
    else:path.write_text(json.dumps(final))
    with pytest.raises(ValueError):source.hydrate(c,r)
    assert all_writes(c)==0


@pytest.mark.parametrize('fault',[None,'different_tick','missing_qd'])
def test_mechanism_snapshot_is_read_only_at_the_same_terminal_boundary(tmp_path,monkeypatch,fault):
    c,r,path,final=terminal_archive(tmp_path,monkeypatch)
    c.scene.spec['mechanisms']=[{'id':'drawer','kind':'articulation'}]
    (path.parent/'scene-input.private.json').write_text(json.dumps(c.scene.spec))
    c.scene.mechanisms={'drawer':Asset(c.scene.robots['left'].data.root_state_w[0],['slide'])}
    measured={'joint_names':['slide'],'joint_pos':[.07],'joint_vel':[-.002]}
    snapshot={'actions':829,'native_physics_tick':83740,'mechanisms':{'drawer':measured},'result':{'task_score_100':100}}
    if fault=='different_tick':snapshot['native_physics_tick']=83739
    elif fault=='missing_qd':measured.pop('joint_vel')
    folder=path.parent/'native-capture';folder.mkdir();(folder/'final-snapshot.private.json').write_text(json.dumps(snapshot))
    if fault:
        with pytest.raises(ValueError):source.hydrate(c,r)
    else:
        h=source.hydrate(c,r)
        assert h['mechanisms']=={'drawer':measured}
        assert 'result'not in h and 'task_score_100'not in h
    assert all_writes(c)==0


def sealed_room_archive(tmp_path,monkeypatch):
    c,r,root,d,actions,profile,rows=archive(tmp_path,monkeypatch)
    (root/'exit.private.json').unlink()
    terminal=dict(room=r['server_source']['room_id'],steps=900,terminal_controller_tick=90840,
                  recorder_stopped=True,terminal_geometry={'private_source_must_not_export':'sentinel'})
    capture=dict(engineering_reference_only=True,native_action_count=900)
    final=dict(actions=900,native_physics_tick=90840,state={'private_source_must_not_export':'sentinel'})
    folder=d/'native-capture';folder.mkdir()
    files={'terminal':d/'native-terminal.private.json','capture':folder/'capture.private.json','final':d/'reference-final-state.private.json'}
    values={'terminal':terminal,'capture':capture,'final':final}
    for key,path in files.items():path.write_text(json.dumps(values[key]))
    return c,r,files,values


def test_sealed_room_can_hydrate_earlier_boundary_while_pool_has_no_exit(tmp_path,monkeypatch,capsys):
    c,r,files,values=sealed_room_archive(tmp_path,monkeypatch);before=deepcopy(r)
    h=source.hydrate(c,r);proof=h['source_evidence']['server_local_hydration']['sealed_room']
    assert proof['room_id']==r['server_source']['room_id']and proof['recorder_stopped']is True
    assert proof['action_count']==900 and proof['source_action_count']==829
    assert proof['physics_tick_count']==90840 and proof['source_physics_tick_count']==83740
    assert 'old_exit'not in h['source_evidence']['server_local_hydration']
    for key in ('terminal','capture','final_measurement'):
        assert set(proof[key])=={'sha256','byte_count'}
    assert 'sentinel'not in json.dumps(h) and 'terminal_geometry'not in json.dumps(h)
    assert h['state_task']==r['state_task']and h['grips']=={'left':0.,'right':.013}
    assert r==before and all_writes(c)==0 and capsys.readouterr().out==''


@pytest.mark.parametrize('fault',['room','not_stopped','earlier_steps','earlier_tick','nonengineering','capture_count','final_steps','final_tick','missing_terminal','missing_capture','missing_final'])
def test_unsealed_or_inconsistent_room_cannot_replace_pool_exit(tmp_path,monkeypatch,fault):
    c,r,files,values=sealed_room_archive(tmp_path,monkeypatch)
    if fault=='room':values['terminal']['room']='room-01-E24-A-s4201'
    elif fault=='not_stopped':values['terminal']['recorder_stopped']=False
    elif fault=='earlier_steps':values['terminal']['steps']=828
    elif fault=='earlier_tick':values['terminal']['terminal_controller_tick']=83739
    elif fault=='nonengineering':values['capture']['engineering_reference_only']=False
    elif fault=='capture_count':values['capture']['native_action_count']=899
    elif fault=='final_steps':values['final']['actions']=899
    elif fault=='final_tick':values['final']['native_physics_tick']=90839
    for key,path in files.items():path.write_text(json.dumps(values[key]))
    if fault.startswith('missing_'):files[fault[8:]].unlink()
    with pytest.raises(ValueError):source.hydrate(c,r)
    assert all_writes(c)==0
