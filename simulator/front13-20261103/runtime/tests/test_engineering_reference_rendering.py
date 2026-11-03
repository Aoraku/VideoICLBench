"""CPU stepping regression: rendering optimization cannot omit native ticks."""
import pytest
from test_room_pool_actions import active_pool


def isolated_pool():
    pool,controllers,sim,events=active_pool();pool.render_isolation=True
    rendered=[]
    def render_room(room,passes=1,capture=None):
        rendered.append(room)
        if capture is not None:return capture()
    pool.render_room=render_room
    return pool,controllers,sim,events,rendered


def test_reference_renders_active_rgb_but_records_every_room_each_physics_tick():
    pool,controllers,sim,events,rendered=isolated_pool()
    with pool.engineering_reference_rendering('E05'):
        receipts=pool.action_batch({'E05':dict(left='GRASP'),'E32':dict(left='STILL')})
    assert rendered==['E05']*10
    assert pool.physics_ticks==100 and sim.current_time==pytest.approx(.4)
    for room,c in controllers.items():
        assert c.steps==1 and c.physics_ticks==100
        assert sum(e[0]=='hook' for e in c.events)==100
        assert sum(e[0]=='evidence' for e in c.events)==100
        assert receipts[room]['physics_ticks']==100
    assert sum(e==('hook',True)for e in controllers['E05'].events)==10
    assert sum(e==('hook',True)for e in controllers['E32'].events)==0
    assert controllers['E05'].grips['left']==0
    assert controllers['E32'].grips['left']==.04


def test_formal_default_and_after_scope_restore_all_room_rendering():
    pool,controllers,sim,events,rendered=isolated_pool()
    pool.action_batch({r:{}for r in controllers})
    assert rendered==['E05','E32']*10
    rendered.clear()
    with pytest.raises(RuntimeError,match='test failure'):
        with pool.engineering_reference_rendering('E05'):
            raise RuntimeError('test failure')
    pool.action_batch({r:{}for r in controllers})
    assert rendered==['E05','E32']*10


def test_sealed_unknown_and_conflicting_reference_cannot_change_state():
    pool,controllers,sim,events,rendered=isolated_pool()
    with pytest.raises(ValueError):
        with pool.engineering_reference_rendering('missing'):pass
    with pool.engineering_reference_rendering('E05'):
        with pytest.raises(RuntimeError):
            with pool.engineering_reference_rendering('E32'):pass
    assert getattr(pool,'_engineering_reference_render_room',None) is None
    assert not events


def test_real_native_capture_update_and_three_video_streams_keep_physics_cadence():
    """Production capture/recorder methods with CPU cameras and byte sinks."""
    import ast
    import io
    import json
    from pathlib import Path
    from types import SimpleNamespace
    import numpy as np
    from PIL import Image
    from videoicl_isaaclab.execution_design_native_capture import NativeCapture
    tree=ast.parse((Path(__file__).parents[1]/'videoicl_isaaclab/demonstration.py').read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='Demonstration')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef)and n.name=='record')
    ns={'Image':Image}
    exec(compile(ast.Module(body=[method],type_ignores=[]),'demonstration.record','exec'),ns)
    pool,controllers,sim,events,rendered=isolated_pool();captures={}
    for room,c in controllers.items():
        cap=NativeCapture.__new__(NativeCapture);cap.c=c;cap.e=c.evaluator;cap.count=0
        cap.original_update=c.evaluator.update
        cap.streams={k:io.StringIO()for k in ('trajectory','contacts')}
        c.evaluator.update=cap.update;captures[room]=cap
    active=controllers['E05']
    class RGB:
        def __getitem__(self,key):return self
        def cpu(self):return self
        def numpy(self):return np.zeros((2,2,3),dtype=np.uint8)
    active.scene.cameras={name:SimpleNamespace(data=SimpleNamespace(output={'rgb':RGB()}))
                          for name in ('head','left_wrist','right_wrist')}
    sink=lambda:SimpleNamespace(stdin=io.BytesIO())
    author=SimpleNamespace(scene=active.scene,physics_ticks_recorded=0,frames=0,
        camera_frame_counts={name:0 for name in active.scene.cameras},frame_physics_ticks=[],
        encoder=sink(),wrist_encoders={side:sink()for side in ('left','right')},review_encoder=sink(),
        camera_streams={name:dict(width=2,height=2)for name in active.scene.cameras})
    active.tick_hooks.append(lambda c,render:ns['record'](author,c,render))
    with pool.engineering_reference_rendering('E05'):
        for _ in range(2):pool.action_batch({room:{}for room in controllers})
    assert author.physics_ticks_recorded==200
    assert author.frame_physics_ticks==list(range(10,201,10))
    assert author.frames==20 and set(author.camera_frame_counts.values())=={20}
    assert len(author.encoder.stdin.getvalue())==20*2*2*3
    assert all(len(encoder.stdin.getvalue())==20*2*2*3 for encoder in author.wrist_encoders.values())
    for cap in captures.values():
        trajectory=[json.loads(line)for line in cap.streams['trajectory'].getvalue().splitlines()]
        contacts=[json.loads(line)for line in cap.streams['contacts'].getvalue().splitlines()]
        assert cap.count==len(trajectory)==len(contacts)==200
        # Controller increments its counter immediately after evaluator.update.
        assert [r['native_physics_tick']for r in trajectory]==list(range(200))
        assert [r['tick']for r in contacts]==list(range(1,201))


def test_nonisolated_formal_pool_keeps_all_frames_even_inside_engineering_scope():
    pool,controllers,sim,events=active_pool()
    with pool.engineering_reference_rendering('E05'):
        pool.action_batch({room:{}for room in controllers})
    assert all(sum(e==('hook',True)for e in c.events)==10 for c in controllers.values())


def test_terminal_reference_rejected_before_scope_or_tick():
    pool,controllers,sim,events,rendered=isolated_pool();pool.seal('E05')
    before=pool.physics_ticks
    with pytest.raises(ValueError,match='live engineering'):
        with pool.engineering_reference_rendering('E05'):pass
    assert pool.physics_ticks==before and not rendered


def test_extra_engineering_renders_preserve_native_ticks_and_frame_cadence(monkeypatch):
    """Exercise real render_room, action barrier and hooks, not a pass-count mock."""
    import sys
    from contextlib import nullcontext
    from types import SimpleNamespace
    pool,controllers,sim,events=active_pool();pool.render_isolation=True
    renders=[]
    monkeypatch.setitem(sys.modules,'videoicl_isaaclab.rig',
        SimpleNamespace(isolated_room_render=lambda *args:nullcontext()))
    sim.stage=object();sim.render=lambda:renders.append(sim.current_time)
    with pool.engineering_recording_render_passes(12):
        receipts=pool.action_batch({room:{}for room in controllers})
    assert len(renders)==2*10*12
    assert pool.physics_ticks==100 and sim.current_time==pytest.approx(.4)
    for room,c in controllers.items():
        assert receipts[room]['physics_ticks']==100
        assert sum(e[0]=='hook'for e in c.events)==100
        assert sum(e==('hook',True)for e in c.events)==10
        assert sum(e[0]=='evidence'for e in c.events)==100
    # Restoring the scope returns ordinary pooled actions to one render/sample.
    renders.clear();pool.action_batch({room:{}for room in controllers})
    assert len(renders)==20 and pool.physics_ticks==200


def test_engineering_render_pass_scope_restores_after_failure_and_rejects_bad_values():
    pool,controllers,sim,events,rendered=isolated_pool()
    for value in (True,0,-1,65,1.5,'12'):
        with pytest.raises(ValueError):
            with pool.engineering_recording_render_passes(value):pass
    with pytest.raises(RuntimeError):
        with pool.engineering_recording_render_passes(12):
            with pool.engineering_recording_render_passes(8):
                raise RuntimeError('interrupted engineering recording')
    assert pool._engineering_recording_render_passes==1
    assert pool.physics_ticks==0 and not events
