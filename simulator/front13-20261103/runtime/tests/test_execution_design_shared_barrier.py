"""Exercise engineering authors through the real synchronous RoomPool API."""
import json
from types import SimpleNamespace
import pytest
from test_room_pool_actions import active_pool
from videoicl_isaaclab.execution_design_probe import pooled_author_class


def author(pool,controllers,root,room):
    a=pooled_author_class(type('Base',(),{}),pool,room)()
    a.c=controllers[room];a.scene=a.c.scene;a.scene.spec={}
    a.out=root/room/'engineering-reference';a.out.mkdir(parents=True)
    a.stage='engineering-control';a.tip=lambda side:[0.,0.,1.]
    return a


def test_active_sibling_gets_real_still_receipt_and_sealed_sibling_is_omitted(tmp_path):
    pool,cs,sim,events=active_pool();a=author(pool,cs,tmp_path,'E05')
    r=a.act(left='GRASP')
    assert r['step_after']==1 and pool.physics_ticks==100
    assert cs['E32'].steps==1 and cs['E32'].grips==dict(left=.04,right=.04)
    record=json.loads((tmp_path/'shared-barrier-actions.private.jsonl').read_text())
    assert set(record['commands'])==set(cs)
    assert record['commands']['E32']['left']==record['commands']['E32']['right']=='STILL'
    assert record['receipts']['E32']['step_after']==1
    assert record['receipts']['E32']['shared_tick_after']==r['shared_tick_after']
    terminal=pool.seal('E05');b=author(pool,cs,tmp_path,'E32');b.act(right='GRASP')
    assert cs['E32'].steps==2 and cs['E05'].steps==1
    assert pool.terminal_result('E05')==terminal
    before=pool.physics_ticks
    with pytest.raises(RuntimeError,match='sealed'):a.act()
    assert pool.physics_ticks==before


def test_invalid_command_does_not_advance_any_sibling(tmp_path):
    pool,cs,sim,events=active_pool();a=author(pool,cs,tmp_path,'E05')
    with pytest.raises(ValueError):a.act(left='INVALID')
    assert pool.physics_ticks==0 and all(c.steps==0 for c in cs.values())
    assert not(tmp_path/'shared-barrier-actions.private.jsonl').exists()
