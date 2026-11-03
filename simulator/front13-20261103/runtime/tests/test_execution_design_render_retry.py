from types import SimpleNamespace
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_render_retry import capture


def setup(task='E32'):
    c = SimpleNamespace(physics_ticks=5, steps=0, scene=SimpleNamespace(spec={
        'id': task, 'execution_design': {'revision': REVISION_V3}}))
    p = SimpleNamespace(physics_ticks=5)
    return p, c


@pytest.mark.parametrize('task',['E04','E08','E32']+[f'E{i:02}'for i in range(14,26)])
def test_gray_warmup_reads_same_world_without_motion(tmp_path, task):
    p,c = setup(task); seen=[]
    def render(room, passes, capture):
        seen.append(passes)
        if len(seen)<3: raise RuntimeError('All three native views are near-uniform gray')
        return capture()
    p.render_room=render
    assert capture(p,'r',c,passes=3,callback=lambda:'actual_rgb',log_path=tmp_path/'log')=='actual_rgb'
    assert seen==[3,12,24]
    assert (p.physics_ticks,c.physics_ticks,c.steps)==(5,5,0)


@pytest.mark.parametrize('task,error,count',[
    ('E32','All three native views are near-uniform gray',3),
    ('E08','All three native views are near-uniform gray',3),
    ('E15','All three native views are near-uniform gray',3),
    ('E15','Actual head camera differs from declared task view',1),
    ('E04','All three native views are near-uniform gray',3),
    ('E04','Actual head camera differs from declared task view',1),
    ('E08','Actual head camera differs from declared task view',1),
    ('E32','Actual head camera differs from declared task view',1),
    ('E01','All three native views are near-uniform gray',1)])
def test_rejects_persistent_gray_or_calibration_and_preserves_other_scope(tmp_path,task,error,count):
    p,c=setup(task);seen=[]
    def render(room,passes,capture):
        seen.append(passes);raise RuntimeError(error)
    p.render_room=render
    with pytest.raises(RuntimeError,match=error):capture(p,'r',c,passes=3,callback=lambda:None,log_path=tmp_path/'log')
    assert len(seen)==count


def test_even_successful_image_is_rejected_if_physics_advanced(tmp_path):
    p,c=setup()
    def render(room,passes,capture):
        p.physics_ticks+=1;return 'rgb'
    p.render_room=render
    with pytest.raises(RuntimeError,match='advanced physics'):
        capture(p,'r',c,passes=3,callback=lambda:None,log_path=tmp_path/'log')


@pytest.mark.parametrize('task',['E04','E08','E15'])
def test_front13_legacy_does_not_retry(tmp_path,task):
    p,c=setup(task);c.scene.spec['execution_design']['revision']='legacy'
    calls=[]
    def render(room, passes, capture):
        calls.append(passes)
        raise RuntimeError('All three native views are near-uniform gray')
    p.render_room=render
    with pytest.raises(RuntimeError, match='gray'):
        capture(p,'r',c,passes=3,callback=lambda:None,log_path=tmp_path/'log')
    assert calls==[3]


@pytest.mark.parametrize('task',[f'E{i:02}'for i in range(14,26)])
def test_each_actual_camera_audit_and_rgb_hash_is_preserved_without_faking_admission(tmp_path,task):
    import json,hashlib
    p,c=setup(task);seen=[];log=tmp_path/'reference-initial-render-attempts.private.json'
    def render(room,passes,capture):
        seen.append(passes);return capture()
    def callback():
        i=len(seen);admitted=i==3
        (tmp_path/'reference-initial-camera-audit.private.json').write_text(json.dumps({'admission_passed':admitted,'views':{'head':{'channel_std':[i,i,i]}}}))
        for view in ('head','left_wrist','right_wrist'):(tmp_path/('reference-initial-'+view+'.png')).write_bytes((view+str(i)).encode())
        if not admitted:raise RuntimeError('All three native views are near-uniform gray')
        return 'accepted_by_unchanged_audit'
    p.render_room=render
    assert capture(p,'room',c,passes=3,callback=callback,log_path=log)=='accepted_by_unchanged_audit'
    rows=json.loads(log.read_text());assert len(rows)==3
    assert [r['actual_camera_readback']['camera_audit']['admission_passed']for r in rows]==[False,False,True]
    assert all(r['actual_camera_readback']['audit_updated_this_attempt']for r in rows)
    assert [r['actual_camera_readback']['rgb_files']['head']['sha256']for r in rows]==[hashlib.sha256(('head'+str(i)).encode()).hexdigest()for i in (1,2,3)]
    assert (p.physics_ticks,c.physics_ticks,c.steps)==(5,5,0)


@pytest.mark.parametrize('task',[f'E{i:02}'for i in range(14,26)])
@pytest.mark.parametrize('error',[
    'Actual head camera differs from declared task view',
    'Invalid initial native RGB: head',
    'Initial camera evidence rejected: All three native views are near-uniform gray; Actual head camera differs from declared task view',
    'Unexpected camera schema failure'])
def test_new_tasks_do_not_retry_any_non_gray_or_mixed_error(tmp_path,task,error):
    p,c=setup(task);calls=[]
    def render(room,passes,capture):calls.append(passes);raise RuntimeError(error)
    p.render_room=render
    with pytest.raises(RuntimeError,match=error):capture(p,'r',c,passes=3,callback=lambda:None,log_path=tmp_path/'log')
    assert calls==[3]


@pytest.mark.parametrize('counter',['pool_physics','room_physics','actions'])
def test_warmup_rejects_each_independent_counter_change(tmp_path,counter):
    p,c=setup('E19');calls=[]
    def render(room,passes,capture):
        calls.append(passes)
        if counter=='pool_physics':p.physics_ticks+=1
        if counter=='room_physics':c.physics_ticks+=1
        if counter=='actions':c.steps+=1
        raise RuntimeError('All three native views are near-uniform gray')
    p.render_room=render
    with pytest.raises(RuntimeError,match='advanced physics/actions'):
        capture(p,'r',c,passes=3,callback=lambda:None,log_path=tmp_path/'log')
    assert calls==[3]


@pytest.mark.parametrize('task',[f'E{i:02}'for i in range(14,26)])
def test_new_scope_persistent_gray_rejects_after_24_passes(tmp_path,task):
    p,c=setup(task);calls=[]
    def render(room,passes,capture):calls.append(passes);raise RuntimeError('Initial camera evidence rejected: All three native views are near-uniform gray; task visibility not established')
    p.render_room=render
    with pytest.raises(RuntimeError,match='near-uniform gray'):
        capture(p,'r',c,passes=3,callback=lambda:None,log_path=tmp_path/'log')
    assert calls==[3,12,24]and(p.physics_ticks,c.physics_ticks,c.steps)==(5,5,0)
