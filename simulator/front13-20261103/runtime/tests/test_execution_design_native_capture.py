import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from videoicl_isaaclab.execution_design_native_capture import NativeCapture


def test_capture_preserves_native_inputs_and_unscored_failure(tmp_path,monkeypatch):
    original=Path.read_text
    def read(path,*args,**kwargs):
        if str(path)=='/proc/self/stat':return '1 (engineering) '+' '.join(['S']+['0']*18+['12345'])
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',read)
    calls=[]
    state={'object':dict(pos=np.array([1.,2.,3.]),mat=np.eye(3),grasp=(False,False))}
    contacts={frozenset(('object','table'))}
    def update(s,c,dt):calls.append((s,c,dt))
    e=SimpleNamespace(update=update,result=lambda:dict(success=False,task_score_100=None,scored=False))
    mass=SimpleNamespace(cpu=lambda:np.array([.25]))
    controller=SimpleNamespace(evaluator=e,steps=0,physics_ticks=1,
        scene=SimpleNamespace(spec=dict(id='E01',variant='A',seed=1,execution_design={},source_files_verified=False),
            objects={'object':SimpleNamespace(root_physx_view=SimpleNamespace(get_masses=lambda:mass))}),
        snapshot=lambda:(state,contacts))
    cap=NativeCapture(controller,tmp_path/'capture')
    identity=json.loads((tmp_path/'capture/identity.private.json').read_text())
    assert identity['actual_physx_masses']['object']==dict(measured=True,kg=[.25])
    e.update(state,contacts,.004)
    assert calls==[(state,contacts,.004)] and calls[0][0] is state
    cap.close(error='reference control failed')
    assert e.update is update
    cap.close()
    with gzip.open(tmp_path/'capture/trajectory.private.jsonl.gz','rt') as stream:
        rows=[json.loads(line) for line in stream]
    assert len(rows)==1 and rows[0]['state']['object']['pos']==[1.,2.,3.]
    receipt=json.loads((tmp_path/'capture/capture.private.json').read_text())
    assert receipt['result']['task_score_100'] is None
    assert receipt['acceptance']=='pending_independent_review'
    assert receipt['native_action_count']==0
    assert receipt['error']=='reference control failed'


def test_mechanism_capture_is_same_tick_input_before_consumption(tmp_path,monkeypatch):
    original=Path.read_text
    monkeypatch.setattr(Path,'read_text',lambda p,*a,**k:
        '1 (engineering) '+' '.join(['S']+['0']*18+['12345'])
        if str(p)=='/proc/self/stat'else original(p,*a,**k))
    actual={'cabinet':dict(joint_names=['joint_1'],joint_pos=[.009],joint_vel=[.001],
                          body_pos_task={'drawer':[.1,.2,.3]})}
    e=SimpleNamespace(pending_mechanisms=actual,result=lambda:dict(task_score_100=None))
    def consume(*args):
        e.pending_mechanisms['cabinet']['joint_pos'][0]=.012
        e.pending_mechanisms=None
    e.update=consume
    c=SimpleNamespace(evaluator=e,steps=0,physics_ticks=123,
        scene=SimpleNamespace(spec=dict(id='E30',variant='A',seed=4201,
            execution_design={},mechanisms=[dict(initial_joint_positions={'joint_1':999})])),
        snapshot=lambda:({},set()),snapshot_mechanisms=lambda:actual)
    cap=NativeCapture(c,tmp_path/'capture');e.update({},set(),.004)
    # No fresh mechanism input on next tick must not reuse the previous one.
    e.update=lambda *args:None
    cap.original_update=e.update;c.physics_ticks=124;cap.update({},set(),.004)
    cap.close()
    with gzip.open(tmp_path/'capture/trajectory.private.jsonl.gz','rt')as f:rows=[json.loads(x)for x in f]
    assert rows[0]['mechanisms']['cabinet']['joint_pos']==[.009]
    assert rows[0]['native_physics_tick']==123
    assert rows[0]['mechanisms']['cabinet']['body_pos_task']['drawer']==[.1,.2,.3]
    assert 'mechanisms'not in rows[1]
    final=json.loads((tmp_path/'capture/final-snapshot.private.json').read_text())
    assert final['mechanisms']['cabinet']['joint_pos']==[.012]
    assert final['result']['task_score_100']is None


def test_e43_startup_force_samples_are_read_only_and_stop_after_first_action(tmp_path,monkeypatch):
    original=Path.read_text
    monkeypatch.setattr(Path,'read_text',lambda p,*a,**k:
        '1 (engineering) '+' '.join(['S']+['0']*18+['12345'])
        if str(p)=='/proc/self/stat'else original(p,*a,**k))
    state={name:dict(pos=[0,0,.85],mat=np.eye(3),grasp=[False,False])for name in ('gate','launcher','ball')}
    calls=[];e=SimpleNamespace(update=lambda *args:calls.append(args),result=lambda:dict(task_score_100=None))
    c=SimpleNamespace(evaluator=e,steps=0,physics_ticks=0,
        scene=SimpleNamespace(spec=dict(id='E43',variant='A',seed=4201,execution_design={})),
        contact_forces={frozenset(('gate','launcher')):401.1},snapshot=lambda:(state,set()))
    cap=NativeCapture(c,tmp_path/'capture')
    for n in range(120):
        c.physics_ticks+=1;e.update(state,set(),.004)
    c.steps=1
    for n in range(120):
        c.physics_ticks+=1;e.update(state,set(),.004)
    cap.close()
    with gzip.open(tmp_path/'capture/e43-assembly-startup.private.jsonl.gz','rt')as f:rows=[json.loads(line)for line in f]
    assert [r['tick']for r in rows]==[1,120]
    assert rows[-1]['contact_forces_n']==[dict(bodies=['gate','launcher'],force_n=401.1)]
    assert len(calls)==240 and all(call[0]is state for call in calls)
    receipt=json.loads((tmp_path/'capture/capture.private.json').read_text())
    assert 'e43_assembly_startup'in receipt['artifacts']
