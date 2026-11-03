"""Real generated-reference methods must park in their own translated room."""
import ast
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
P=Path(__file__).parents[1]/'videoicl_isaaclab/demonstration.py'

def method(name):
    cls=next(n for n in ast.parse(P.read_text()).body if isinstance(n,ast.ClassDef)and n.name=='Demonstration')
    node=next(n for n in cls.body if isinstance(n,ast.FunctionDef)and n.name==name)
    ns={'np':np};exec(compile(ast.Module(body=[node],type_ignores=[]),str(P),'exec'),ns)
    return ns[name]

def subject(origin):
    cfg={'robots':{'left':{'position':[-.65,.08,0]},'right':{'position':[-.65,-.08,0]}}}
    scene=SimpleNamespace(origin=np.array(origin),world_to_task=lambda p:np.array(p)-np.array(origin),
        embodiment=SimpleNamespace(config=cfg),spec={'task_adapter':'realworld','expert_arm':'right','goals':[{'type':'place'}]})
    return SimpleNamespace(scene=scene,smooth=False,carried_payload=None,tip=lambda side:np.array([-.1,.2 if side=='left'else-.2,.9]),
        calibrate_generated_axes=lambda:None,note=lambda *a:None,act=lambda *a:None)

@pytest.mark.parametrize('origin',[(0,0,0),(8,0,0),(0,8,0),(8,8,0)])
def test_initial_idle_parking_is_room_translation_invariant(origin):
    a=subject(origin);moves=[]
    class Captured(Exception):pass
    def move(targets,**kw):
        moves.append(targets)
        if len(moves)==2:raise Captured
    a.move_generated=move
    with pytest.raises(Captured):method('solve_generated')(a)
    assert moves[-1]['left']==pytest.approx([-.5,.3,1.25])

@pytest.mark.parametrize('origin',[(0,0,0),(8,0,0),(0,8,0),(8,8,0)])
def test_switched_hand_parking_is_room_translation_invariant(origin):
    a=subject(origin);moves=[];a.move_generated=lambda targets,**kw:moves.append(targets)
    assert method('activate_generated_hand')(a,'right','left',{'right':[0,-.2]},.95)=='right'
    assert moves[1]['left']==pytest.approx([-.5,.3,1.25])

@pytest.mark.parametrize('origin',[(0,0,0),(8,0,0),(0,8,0),(8,8,0)])
def test_tool_single_hand_parking_is_room_translation_invariant(origin):
    from videoicl_isaaclab.author_clearance import _park
    a=subject(origin);moves=[];a.move_smooth=lambda targets,**kw:moves.append(targets)
    a.c=SimpleNamespace(snapshot=lambda:({},set()))
    _park(a,'left',1.10)
    assert moves[1]['left']==pytest.approx([-.5,.3,1.10])
