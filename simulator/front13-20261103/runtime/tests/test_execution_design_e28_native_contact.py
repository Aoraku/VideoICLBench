from contextlib import contextmanager
from types import SimpleNamespace
import json
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_e28_native_contact as native
from videoicl_isaaclab import engineering_checkpoint
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


class Value:
    def __init__(self,label):self.label=label
    def clone(self):return Value(self.label)


def setup(tmp_path,monkeypatch,recover_after=2):
    scene=SimpleNamespace(robots={'left':None,'right':None},embodiment=SimpleNamespace(config={'physics':{'render_hz':5}}))
    pool=SimpleNamespace(physics_ticks=400);c=SimpleNamespace(steps=4,physics_ticks=400,sim=SimpleNamespace(current_time=1.6),dt=.004,
        _room_pool=pool,scene=scene,_public_action={'left':'STILL','right':'UP'},targets={'right':'old endpoint'},contact_forces={},object_position=np.array([1.,2.,3.]))
    a=SimpleNamespace(c=c,scene=scene,out=tmp_path,stage='carry',_engineering_e28_contact_hold=True,control_report={'engineering_reference_only':True})
    p=SimpleNamespace(a=a,c=c,start=0,limit=30,spec={'id':'E28','seed':4201,'execution_design':{'revision':'embodied50-execution-v3-20261102','condition':'I'}})
    (tmp_path/'demo-actions.private.jsonl').write_text(json.dumps(dict(step_before=3,step_after=4,shared_tick_after=400))+'\n')
    c.pose=lambda side:(Value('actual-position-'+side),Value('actual-rotation-'+side))
    ticks=[]
    def tick(render=False):
        assert c._public_action is None
        assert all(c.targets[s][0].label=='actual-position-'+s and c.targets[s][1].label=='actual-rotation-'+s for s in scene.robots)
        c.physics_ticks+=1;pool.physics_ticks+=1;c.sim.current_time+=c.dt;ticks.append(render)
        c.contact_forces[frozenset(('food','blade'))]=.2 if len(ticks)>=recover_after else 0.
    c.tick=tick
    def measure():return dict(supported=True,plane_gap_m=.0002,hand_contact=False,table_contact=False,
        actual_blade_contact=len(ticks)>=recover_after,local=np.array([.131,0.,0.]))
    @contextmanager
    def bridge(author,*,reference_authorization):
        assert author is a and reference_authorization
        yield
    monkeypatch.setattr(native,'diagnostic_tick_scope',bridge)
    monkeypatch.setattr(engineering_checkpoint,'capture',lambda controller,stage:dict(diagnostic_only=True,stage=stage,steps=controller.steps))
    return p,c,measure,ticks


def test_hold_stops_on_real_contact_and_never_continues_the_old_up_command(tmp_path,monkeypatch):
    p,c,measure,ticks=setup(tmp_path,monkeypatch)
    result=native.hold(p,'food',{'actor':'blade'},lambda:None,measure)
    assert result['physics_ticks']==2 and result['private_actions']==1 and c.steps==5
    assert c._public_action is None and np.array_equal(c.object_position,[1.,2.,3.])
    rows=[json.loads(x)for x in(tmp_path/'demo-actions.private.jsonl').read_text().splitlines()]
    assert rows[-1]['is_gui_action']is False and rows[-1]['actual_contact_recovered']is True
    assert rows[-1]['shared_tick_after']==402 and len(rows[-1]['tick_samples'])==2
    with pytest.raises(ValueError,match='At most one contact hold'):
        native.hold(p,'food',{'actor':'blade'},lambda:None,measure)
    assert len(ticks)==2


def test_uncompleted_receipt_clock_cannot_advance_or_change_motor_targets(tmp_path,monkeypatch):
    p,c,measure,ticks=setup(tmp_path,monkeypatch)
    (tmp_path/'demo-actions.private.jsonl').write_text(json.dumps(dict(step_after=4,shared_tick_after=399))+'\n')
    with pytest.raises(ValueError,match='completed receipt physics clock'):
        native.hold(p,'food',{'actor':'blade'},lambda:None,measure)
    assert ticks==[]and c.steps==4 and c._public_action['right']=='UP'and c.targets['right']=='old endpoint'


def test_hold_never_manufactures_contact_after_its_ten_tick_bound(tmp_path,monkeypatch):
    p,c,measure,ticks=setup(tmp_path,monkeypatch,recover_after=100)
    with pytest.raises(ToolExecutionError,match='within ten real hold ticks'):
        native.hold(p,'food',{'actor':'blade'},lambda:None,measure)
    assert len(ticks)==10 and c.steps==5
    row=json.loads((tmp_path/'E28-native-contact-holds.private.jsonl').read_text().splitlines()[-1])
    assert row['actual_contact_recovered']is False and row['physics_ticks']==10


def test_lost_physical_geometry_stops_the_hold_at_its_first_tick(tmp_path,monkeypatch):
    p,c,measure,ticks=setup(tmp_path,monkeypatch,recover_after=100)
    def invalid():return dict(measure(),supported=False)
    with pytest.raises(ToolExecutionError,match='lost original physical support geometry'):
        native.hold(p,'food',{'actor':'blade'},lambda:None,invalid)
    assert len(ticks)==1 and c.steps==5
