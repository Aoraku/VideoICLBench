"""Engineering references exercise the unchanged native RoomPool barrier."""
import json
import threading
from types import SimpleNamespace
import pytest
pytest.importorskip('greenlet')
from test_room_pool_actions import active_pool
from videoicl_isaaclab.execution_design_cooperative import CooperativeReferences,enabled_for
from videoicl_isaaclab.execution_design_probe import pooled_author_class
from videoicl_isaaclab.execution_design import REVISION_V3

def test_each_reference_uses_real_commands_and_seals_independently(tmp_path):
    pool,cs,sim,events=active_pool();schedule=CooperativeReferences(pool,tmp_path)
    observed={room:[]for room in cs};seals={};thread=threading.get_ident()
    def job(room,count):
        try:
            for index in range(count):
                receipt=schedule.submit(room,dict(left='GRASP' if index==0 else 'RELEASE'))
                observed[room].append((receipt,threading.get_ident(),pool.physics_ticks))
        finally:seals[room]=pool.seal(room)
    result=schedule.run({'E05':lambda:job('E05',2),'E32':lambda:job('E32',4)})
    assert result['native_batches']==4 and pool.physics_ticks==400
    assert cs['E05'].steps==2 and cs['E32'].steps==4
    assert seals['E05']==pool.terminal_result('E05')
    assert seals['E05']['physical_world_frozen'] is False
    assert cs['E05'].physics_ticks==400
    for room,items in observed.items():
        assert all(t==thread and receipt['shared_tick_after']==tick for receipt,t,tick in items)
    log=[json.loads(x)for x in (tmp_path/'cooperative-barrier-actions.private.jsonl').read_text().splitlines()]
    assert [set(x['commands'])for x in log]==[{'E05','E32'}]*2+[{'E32'}]*2
    assert not (tmp_path/'shared-barrier-actions.private.jsonl').exists()

def test_local_reference_failure_finally_seals_without_interrupting_sibling(tmp_path):
    pool,cs,sim,events=active_pool();schedule=CooperativeReferences(pool,tmp_path);errors=[]
    def broken():
        try:
            schedule.submit('E05',dict(left='GRASP'))
            schedule.submit('E05',dict(left='INVALID'))
        except ValueError as error:errors.append(str(error))
        finally:pool.seal('E05')
    def healthy():
        try:
            for _ in range(3):schedule.submit('E32',dict(right='GRASP'))
        finally:pool.seal('E32')
    schedule.run({'E05':broken,'E32':healthy})
    assert errors and cs['E05'].steps==1 and cs['E32'].steps==3
    assert pool.physics_ticks==300

def test_partially_accepted_batch_is_not_retried_and_every_finally_runs(tmp_path):
    pool,cs,sim,events=active_pool();schedule=CooperativeReferences(pool,tmp_path);closed=[];calls=[]
    native=pool.action_batch
    def failed(actions):
        calls.append(actions);native(actions)
        raise RuntimeError('Failure after physical advancement')
    pool.action_batch=failed
    def job(room):
        try:schedule.submit(room,dict(left='GRASP'))
        finally:closed.append(room);pool.seal(room)
    with pytest.raises(RuntimeError,match='after physical'):
        schedule.run({room:lambda room=room:job(room)for room in cs})
    assert len(calls)==1 and pool.physics_ticks==100 and set(closed)==set(cs)

def test_unsealed_return_aborts_before_advancing_world(tmp_path):
    pool,cs,sim,events=active_pool();schedule=CooperativeReferences(pool,tmp_path)
    with pytest.raises(RuntimeError,match='without native terminal'):
        schedule.run({room:lambda:None for room in cs})
    assert pool.physics_ticks==0

def test_cooperative_author_keeps_split_actions_and_individual_receipts(tmp_path):
    pool,cs,sim,events=active_pool();schedule=CooperativeReferences(pool,tmp_path)
    authors={}
    for room,c in cs.items():
        a=pooled_author_class(type('Base',(),{}),pool,room,schedule)()
        a.c=c;a.scene=c.scene;a.scene.spec={};a.stage='test'
        a.out=tmp_path/room/'engineering-reference';a.out.mkdir(parents=True)
        a.tip=lambda side:None;authors[room]=a
    def job(room):
        try:authors[room].act(left='GRASP',mm=20);authors[room].act(left='RELEASE')
        finally:pool.seal(room)
    schedule.run({room:lambda room=room:job(room)for room in cs})
    assert pool.physics_ticks==200
    for room,a in authors.items():
        rows=[json.loads(x)for x in (a.out/'demo-actions.private.jsonl').read_text().splitlines()]
        assert [x['step_after']for x in rows]==[1,2]
        assert [x['left']for x in rows]==['GRASP','RELEASE']

@pytest.mark.parametrize('task,revision,accepted',[('E26',REVISION_V3,True),('E50',REVISION_V3,True),('E25',REVISION_V3,False),('E26','v2',False)])
def test_opt_in_only_applies_to_backhalf_v3(task,revision,accepted):
    cs={'room':SimpleNamespace(scene=SimpleNamespace(spec=dict(id=task,execution_design=dict(revision=revision))))}
    assert enabled_for(cs,{}) is False
    if accepted:assert enabled_for(cs,{'VIC_ENGINEERING_COOPERATIVE_REFERENCES':'1'})
    else:
        with pytest.raises(ValueError):enabled_for(cs,{'VIC_ENGINEERING_COOPERATIVE_REFERENCES':'1'})


@pytest.mark.parametrize('task',['E05','E11','E13','E14','E15','E16','E21','E22','E25'])
def test_reviewed_front_generated_routes_require_discrete_placement_opt_in(task):
    spec=dict(id=task,execution_design=dict(revision=REVISION_V3),goals=[dict(type='place')])
    controllers={'room':SimpleNamespace(scene=SimpleNamespace(spec=spec))}
    assert enabled_for(controllers,{}) is False
    assert enabled_for(controllers,{'VIC_ENGINEERING_COOPERATIVE_REFERENCES':'1'})
    spec['author_smooth_recording']=True
    with pytest.raises(ValueError,match='public discrete'):enabled_for(controllers,{'VIC_ENGINEERING_COOPERATIVE_REFERENCES':'1'})
    spec['author_smooth_recording']=False;spec['goals']=[dict(type='mechanism')]
    with pytest.raises(ValueError,match='placement goals'):enabled_for(controllers,{'VIC_ENGINEERING_COOPERATIVE_REFERENCES':'1'})


def test_three_front_workers_receive_every_real_batch_rgb_and_keep_own_terminal(tmp_path):
    from copy import deepcopy
    from videoicl_isaaclab.room_pool import RoomPool
    original,cs,sim,events=active_pool()
    third=deepcopy(cs['E05']);third.sim=sim;third._room_pool=None
    third.scene.root_path='/World/Rooms/E22'
    cs={'E13':cs['E05'],'E21':cs['E32'],'E22':third}
    for c in cs.values():c._room_pool=None
    pool=RoomPool(sim,cs,render_isolation=True);rendered=[]
    pool.render_room=lambda room,**kwargs:rendered.append(room)
    schedule=CooperativeReferences(pool,tmp_path);receipts={r:[]for r in cs}
    def job(room,count):
        try:
            for i in range(count):receipts[room].append(schedule.submit(room,dict(left='GRASP'if i%2==0 else'RELEASE')))
        finally:pool.seal(room)
    result=schedule.run({r:lambda r=r,n=n:job(r,n)for r,n in zip(cs,(2,3,4))})
    assert result['native_batches']==4 and pool.physics_ticks==400
    assert [cs[r].steps for r in cs]==[2,3,4]
    assert [rendered.count(r)for r in cs]==[20,30,40]
    for room,items in receipts.items():
        assert [x['step_after']for x in items]==list(range(1,len(items)+1))
        assert pool.terminal_result(room)['steps']==len(items)


def test_private_dependency_preflight_uses_c_extension_and_real_same_thread_roundtrip(tmp_path):
    import greenlet
    import shutil,hashlib,subprocess,sys
    from pathlib import Path
    vendor=tmp_path/'engineering-vendor'
    shutil.copytree(Path(greenlet.__file__).parent,vendor/'greenlet',ignore=shutil.ignore_patterns('__pycache__'))
    hashes={str(p.relative_to(vendor)):hashlib.sha256(p.read_bytes()).hexdigest()for p in vendor.rglob('*')if p.is_file()}
    manifest=tmp_path/'hashes.json';manifest.write_text(json.dumps(hashes))
    code='import json;from videoicl_isaaclab.execution_design_cooperative import verify_private_dependency;print(json.dumps(verify_private_dependency('+repr(str(vendor))+',json.load(open('+repr(str(manifest))+')))))'
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    receipt=json.loads(result.stdout)
    assert receipt['passed'] and receipt['same_thread_yield_resume']==['worker_yield','worker_return']
    assert receipt['simulator_imported']is False and receipt['gpu_or_simulation_started']is False
    assert str(vendor)in receipt['module_paths']['extension']
    # A hash mismatch fails before attempting to load or execute the package.
    from videoicl_isaaclab.execution_design_cooperative import verify_private_dependency
    hashes['greenlet/__init__.py']='0'*64
    with pytest.raises(ValueError,match='checksum mismatch'):verify_private_dependency(vendor,hashes)
    with pytest.raises(ValueError,match='manifest'):verify_private_dependency(vendor,{})


def test_e16_e25_reference_preparation_does_not_step_sibling_physics(tmp_path):
    # Production relay planning and pinned handle selection may do CPU work,
    # but must not advance the shared pool before both public commands exist.
    from test_execution_design_e07_reference import author as relay_author,feasible
    from test_execution_design_e25_reference import scene as cutlery_scene
    from videoicl_isaaclab.execution_design_e07_reference import plan_transfers
    from videoicl_isaaclab.execution_design_e25_reference import grasp_spec
    from videoicl_isaaclab.room_pool import RoomPool
    pool0,old,sim,events=active_pool()
    cs={'E16':old['E05'],'E25':old['E32']}
    for c in cs.values():c._room_pool=None
    pool=RoomPool(sim,cs,render_isolation=True)
    pool.render_room=lambda room,capture=None,**kwargs:capture()if capture else None
    scheduler=CooperativeReferences(pool,tmp_path)
    prepared=[]
    def relay():
        try:
            local=tmp_path/'relay';local.mkdir()
            a=relay_author(local,task='E16')
            queue=plan_transfers(a,a.scene.spec['goals'],feasible)
            assert any('_e07_relay_phase'in g for g in queue)
            assert pool.physics_ticks==0
            prepared.append('E16')
            for token in ['GRASP','RELEASE','GRASP','RELEASE']:
                scheduler.submit('E16',dict(left=token))
        finally:pool.seal('E16')
    def cutlery():
        try:
            local=tmp_path/'cutlery';local.mkdir()
            spec=cutlery_scene(local)
            a=SimpleNamespace(scene=SimpleNamespace(spec=spec),_execution_design_reference_authorized=True)
            obj=next(o for o in spec['objects']if o['id']=='knife')
            picked=grasp_spec(a,obj)
            assert picked is not obj and picked['grasp_point_local']!=obj['grasp_point_local']
            assert pool.physics_ticks==0 and prepared==['E16']
            prepared.append('E25')
            scheduler.submit('E25',dict(right='GRASP'))
            scheduler.submit('E25',dict(right='RELEASE'))
        finally:pool.seal('E25')
    result=scheduler.run({'E16':relay,'E25':cutlery})
    assert prepared==['E16','E25'] and result['native_batches']==4
    assert cs['E16'].steps==4 and cs['E25'].steps==2
    rows=[json.loads(x)for x in (tmp_path/'cooperative-barrier-actions.private.jsonl').read_text().splitlines()]
    assert [set(x['commands'])for x in rows]==[{'E16','E25'},{'E16','E25'},{'E16'},{'E16'}]
    assert pool.terminal_result('E25')['steps']==2


def test_e08_structural_route_rejects_continuous_side_paths():
    spec=dict(id='E08',execution_design=dict(revision=REVISION_V3),goals=[dict(type='place')],
              semantic={'structural_grasps':{'shoe':dict(local=[0,0,0],jaw_axis_local=[0,1,0])}})
    config={'author_recording':{}}
    c=SimpleNamespace(scene=SimpleNamespace(spec=spec,embodiment=SimpleNamespace(config=config)))
    assert enabled_for({'room':c},{})is False
    assert enabled_for({'room':c},{'VIC_ENGINEERING_COOPERATIVE_REFERENCES':'1'})
    config['author_recording']['clear_idle_arm']=True
    with pytest.raises(ValueError,match='idle-arm'):enabled_for({'room':c},{'VIC_ENGINEERING_COOPERATIVE_REFERENCES':'1'})
    config['author_recording']['clear_idle_arm']=False
    spec['semantic']['structural_grasps']['shoe']['pre_grasp_task_yaw_rad']=.2
    with pytest.raises(ValueError,match='pre-grasp'):enabled_for({'room':c},{'VIC_ENGINEERING_COOPERATIVE_REFERENCES':'1'})
    spec['semantic']['structural_grasps']['shoe']['pre_grasp_task_yaw_rad']=0
    spec['author_smooth_recording']=True
    with pytest.raises(ValueError,match='public discrete'):enabled_for({'room':c},{'VIC_ENGINEERING_COOPERATIVE_REFERENCES':'1'})


@pytest.mark.parametrize('task',['E17','E20'])
def test_workflow_cooperative_opt_in_rejects_every_nonpublic_preparation(task):
    spec=dict(id=task,execution_design=dict(revision=REVISION_V3,grasps={'piece':dict(local=[0,0,0],jaw_axis_local=[1,0,0])}))
    config={'author_recording':{}}
    c=SimpleNamespace(scene=SimpleNamespace(spec=spec,embodiment=SimpleNamespace(config=config)))
    assert enabled_for({'room':c},{})is False
    assert enabled_for({'room':c},{'VIC_ENGINEERING_COOPERATIVE_REFERENCES':'1'})
    for key,value in [('clear_idle_arm',True),('pre_grasp_opening_m',.03)]:
        config['author_recording']={key:value}
        with pytest.raises(ValueError,match='preparation'):enabled_for({'room':c},{'VIC_ENGINEERING_COOPERATIVE_REFERENCES':'1'})
    config['author_recording']={};spec['execution_design']['grasps']['piece']['pre_grasp_task_yaw_rad']=.1
    with pytest.raises(ValueError,match='pre-grasp'):enabled_for({'room':c},{'VIC_ENGINEERING_COOPERATIVE_REFERENCES':'1'})
    spec['execution_design']['grasps']['piece']['pre_grasp_task_yaw_rad']=0;spec['author_smooth_recording']=True
    with pytest.raises(ValueError,match='discrete'):enabled_for({'room':c},{'VIC_ENGINEERING_COOPERATIVE_REFERENCES':'1'})


def test_e17_e20_real_workflow_wait_and_actions_yield_and_failed_sibling_seals(tmp_path):
    from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
    from videoicl_isaaclab.room_pool import RoomPool
    _,old,sim,events=active_pool();cs={'E17':old['E05'],'E20':old['E32']}
    for c in cs.values():c._room_pool=None
    pool=RoomPool(sim,cs,render_isolation=True)
    pool.render_room=lambda room,capture=None,**kwargs:capture()if capture else None
    scheduler=CooperativeReferences(pool,tmp_path);policies={}
    for room,c in cs.items():
        author=pooled_author_class(type('Base',(),{}),pool,room,scheduler)()
        author.c=c;author.scene=c.scene;author.scene.spec={};author.stage='workflow-public'
        author.out=tmp_path/room/'engineering-reference';author.out.mkdir(parents=True);author.tip=lambda side:None
        policy=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);policy.a=author;policy.c=c;policy.start=0;policy.limit=3000
        policy.min_mm=.5;policy.max_mm=10.;policy.min_deg=.5;policy.max_deg=10.;policies[room]=policy
    failures=[]
    def run(room):
        try:
            policy=policies[room];policy.wait(2);policy.act('right','GRASP')
            if room=='E17':raise RuntimeError('measured held lost')
            policy.wait();policy.act('right','RELEASE')
        except RuntimeError as error:failures.append((room,str(error)))
        finally:pool.seal(room)
    result=scheduler.run({room:lambda room=room:run(room)for room in cs})
    assert failures==[('E17','measured held lost')]
    assert cs['E17'].steps==3 and cs['E20'].steps==6
    assert result['native_batches']==6 and pool.physics_ticks==600
    log=[json.loads(x)for x in (tmp_path/'cooperative-barrier-actions.private.jsonl').read_text().splitlines()]
    assert [set(r['commands'])for r in log]==[{'E17','E20'}]*3+[{'E20'}]*3


def test_e15_guarded_public_rotation_yields_and_sibling_finishes(tmp_path,monkeypatch):
    import numpy as np
    from videoicl_isaaclab.execution_design_e15_wrist import _guard_public_step
    pool,cs,sim,events=active_pool();schedule=CooperativeReferences(pool,tmp_path)
    # The CPU adapter has no arm kinematics. Admit the real rotation token for
    # this barrier test; measured joint changes below are explicitly simulated.
    from test_room_pool_actions import ACTUAL
    namespace=ACTUAL['validate_action'].__globals__
    monkeypatch.setitem(namespace,'TOKENS',namespace['TOKENS']|{'ROTATE_CCW'})
    q=np.zeros((1,7));limits=np.tile([-3.,3.],(1,7,1));resumed=[]
    robot=SimpleNamespace(find_joints=lambda pattern:(list(range(7)),[f'panda_joint{i}'for i in range(1,8)]),data=SimpleNamespace(joint_pos=q,soft_joint_pos_limits=limits))
    a=SimpleNamespace(scene=SimpleNamespace(robots={'left':robot}),c=SimpleNamespace(action_feedback=lambda:{'control_feedback':{'left':{'status':'ok','joint_limit_names':[]}}}),out=tmp_path,stage='e15-empty-reference')
    def act(left,right,rotation_deg):
        receipt=schedule.submit('E05',dict(left=left,right=right,rotation_deg=rotation_deg))
        resumed.append(receipt['step_after']);q[0,6]+=.01
    a.act=act
    def e15():
        try:
            for _ in range(2):_guard_public_step(a,'left','ROTATE_CCW',1.)
        finally:pool.seal('E05')
    def other():
        try:
            for _ in range(3):schedule.submit('E32',dict(left='STILL',right='GRASP'))
        finally:pool.seal('E32')
    result=schedule.run({'E05':e15,'E32':other})
    assert resumed==[1,2] and result['native_batches']==3
    assert cs['E32'].steps==3 and pool.physics_ticks==300
    rows=[json.loads(line)for line in(tmp_path/'e15-wrist-public-steps.private.jsonl').read_text().splitlines()]
    assert [row['q'][6]for row in rows]==[.01,.02]
