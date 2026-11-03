"""Engineering-only scalar/segmentation boundary and actual generated route."""
import ast,json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_probe import engineering_action_plan,pooled_author_class
CONTROL={'step_mm':[.5,50.],'rotation_deg':[.5,20.]}


def test_numpy_real_scalar_keeps_value_and_records_original_type():
    original=np.float64(7.38191)
    req,plan=engineering_action_plan('FWD','STILL',original,np.float32(10),CONTROL,10)
    assert type(plan[0]['step_mm'])is float and plan[0]['step_mm']==original
    assert req['step_mm_type']=='float64' and req['rotation_deg_type']=='float32'

@pytest.mark.parametrize('bad',[0,-1,float('nan'),float('inf'),True,'20',np.bool_(True),.49])
def test_invalid_values_are_rejected_without_direction_changes(bad):
    with pytest.raises(ValueError):engineering_action_plan('BACK','STILL',bad,10.,CONTROL,100)


def test_only_roundoff_near_positive_minimum_can_be_rounded():
    req,plan=engineering_action_plan('UP','STILL',np.nextafter(.5,0.),10.,CONTROL,10)
    assert req['step_mm']<.5 and plan[0]['step_mm']==.5
    with pytest.raises(ValueError):engineering_action_plan('UP','STILL',.499999,10.,CONTROL,10)


def test_large_motion_decomposes_without_replaying_grasp():
    req,plan=engineering_action_plan('BACK','GRASP',125.,10.,CONTROL,3)
    assert len(plan)==3 and sum(p['step_mm']for p in plan)==pytest.approx(125.)
    assert [p['left']for p in plan]==['BACK']*3
    assert [p['right']for p in plan]==['GRASP','STILL','STILL']
    assert all(.5<=p['step_mm']<=50. for p in plan)
    with pytest.raises(RuntimeError):engineering_action_plan('BACK','GRASP',125.,10.,CONTROL,2)


def test_unrepresentable_mixed_motion_rejected_before_any_subaction():
    with pytest.raises(ValueError,match='Simultaneous'):
        engineering_action_plan('FWD','ROTATE_CCW',125.,.5,CONTROL,100)
    with pytest.raises(ValueError,match='Unused'):
        engineering_action_plan('STILL','STILL',100.,10.,CONTROL,100)


def test_actual_move_generated_near_waypoint_uses_public_scalar_types(tmp_path):
    path=Path(__file__).parents[1]/'videoicl_isaaclab/demonstration.py';tree=ast.parse(path.read_text())
    cls=next(x for x in tree.body if isinstance(x,ast.ClassDef)and x.name=='Demonstration')
    method=next(x for x in cls.body if isinstance(x,ast.FunctionDef)and x.name=='move_generated')
    scope={'np':np,'json':json,'__package__':'videoicl_isaaclab'};exec(compile(ast.Module(body=[method],type_ignores=[]),str(path),'exec'),scope)
    c=SimpleNamespace(steps=0);positions={'left':np.array([0.,0.,1.]),'right':np.array([0.,0.,1.])};accepted=[]
    def action_batch(commands):
        command=commands['room'];assert type(command['step_mm'])in(int,float)
        assert .5<=command['step_mm']<=50. and type(command['rotation_deg'])in(int,float)
        accepted.append(command.copy());before=c.steps;c.steps+=1
        for side in ('left','right'):
            if command[side]=='FWD':positions[side][0]+=command['step_mm']/1000*.7
        return {'room':dict(step_before=before,step_after=c.steps,physics_ticks=1)}
    base=type('Base',(),{'move_generated':scope['move_generated']})
    a=pooled_author_class(base,SimpleNamespace(action_batch=action_batch),'room')();a.c=c;a.smooth=False;a.out=tmp_path;a.stage='park-idle-left'
    a.scene=SimpleNamespace(spec={},embodiment=SimpleNamespace(name='franka',config={'control':CONTROL}));a.tip=lambda side:positions[side].copy()
    a.move_generated({'left':[.047311,0,1.]},tolerance=.004)
    assert abs(a.tip('left')[0]-.047311)<=.004
    rows=[json.loads(x)for x in(tmp_path/'demo-actions.private.jsonl').read_text().splitlines()]
    assert any(r['requested_action']['step_mm_type']=='float64'for r in rows)
    assert len(rows)==c.steps==len(accepted)
    assert all(r['step_after']==i+1 for i,r in enumerate(rows))
