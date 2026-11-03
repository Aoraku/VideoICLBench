import gzip,hashlib,json
from pathlib import Path
from types import SimpleNamespace as N
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_e19_capture import capture_for
from videoicl_isaaclab.execution_design_native_capture import NativeCapture


def controller():
    robots={}
    for side in ('left','right'):
        data=N(joint_pos=np.zeros((1,9)),joint_vel=np.zeros((1,9)),
            body_pos_w=np.array([[[0.,0.,1.],[.01,0.,1.]]]),body_quat_w=np.array([[[1.,0,0,0],[1.,0,0,0]]]))
        def joints(pattern):
            return (list(range(7)),[f'panda_joint{i}'for i in range(1,8)])if pattern=='panda_joint[1-7]'else([7,8],['panda_finger_joint1','panda_finger_joint2'])
        robots[side]=N(data=data,find_joints=joints,find_bodies=lambda name:([int(name=='finger2')],[name]))
    state={name:dict(pos=[0.,0.,1.],mat=np.eye(3),grasp=[False,False])for name in ('cap_red','water_bottle')}
    contacts={frozenset(('cap_red','left_finger1'))};calls=[]
    e=N(update=lambda *args:calls.append(args),result=lambda:dict(task_score_100=None))
    c=N(evaluator=e,steps=475,physics_ticks=40000,contact_forces={frozenset(('cap_red','left_finger1')):1.2},
        scene=N(spec=dict(id='E19',variant='C',seed=4201,execution_design=dict(revision=REVISION_V3)),
                robots=robots,embodiment=N(fingers=['finger1','finger2'])),snapshot=lambda:(state,contacts))
    return c,state,contacts,calls


def test_e19c_per_tick_native_joint_force_and_body_samples_have_complete_sha(tmp_path,monkeypatch):
    original=Path.read_text
    monkeypatch.setattr(Path,'read_text',lambda p,*a,**k:
        '1 (engineering) '+' '.join(['S']+['0']*18+['12345'])if str(p)=='/proc/self/stat'else original(p,*a,**k))
    c,state,contacts,calls=controller();cap=NativeCapture(c,tmp_path/'capture')
    for i in range(4):
        c.scene.robots['left'].data.joint_pos[0,7:]=i*.01
        c.scene.robots['left'].data.joint_vel[0,7:]=i*.02
        c.contact_forces[frozenset(('cap_red','left_finger1'))]=i*.3
        c.physics_ticks=40000+i;c.evaluator.update(state,contacts,.004)
        assert c.physics_ticks==40000+i and c.steps==475
    cap.close();f=tmp_path/'capture/e19-cap-release-dynamics.private.jsonl.gz'
    with gzip.open(f,'rt')as stream:rows=[json.loads(x)for x in stream]
    assert len(rows)==4 and len(calls)==4
    assert [r['native_physics_tick']for r in rows]==[40000,40001,40002,40003]
    assert [r['robots']['left']['finger_q_m'][0]for r in rows]==[0.,.01,.02,.03]
    assert rows[-1]['robots']['left']['finger_qd_m_s']==[.06,.06]
    assert rows[-1]['contact_forces_n'][0]['force_n']==pytest.approx(.9)
    assert rows[-1]['robots']['left']['actual_finger_bodies']['finger2']['position_world_m']==[.01,0.,1.]
    assert all(x[0]is state for x in calls)
    receipt=json.loads((tmp_path/'capture/capture.private.json').read_text());a=receipt['artifacts']['e19_cap_release_dynamics']
    assert a['sha256']==hashlib.sha256(f.read_bytes()).hexdigest()and a['bytes']==f.stat().st_size


@pytest.mark.parametrize('change',[dict(id='E18'),dict(variant='B'),dict(execution_design={'revision':'old'})])
def test_other_tasks_variants_and_revisions_keep_existing_capture_streams(change):
    c,*_=controller();c.scene.spec.update(change)
    assert capture_for(c)is None
