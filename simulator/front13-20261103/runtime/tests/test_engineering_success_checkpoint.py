import hashlib
import json
from types import SimpleNamespace
import pytest
from videoicl_isaaclab import engineering_checkpoint as cp
from videoicl_isaaclab import engineering_checkpoint_reference as ref


@pytest.mark.parametrize('passed',[True,False])
@pytest.mark.parametrize('task',['E15','E17','E18','E19','E20','E23','E24','E25','E28','E31','E34','E37'])
def test_success_saves_exact_completed_action_and_drive_state_without_ticking(tmp_path,monkeypatch,passed,task):
    controller=SimpleNamespace(steps=19,physics_ticks=1900)
    author=SimpleNamespace(c=controller,out=tmp_path,scene=SimpleNamespace(spec={'id':task}),
        control_report={'engineering_reference_only':True},carried_payload=('tool','right'),
        _engineering_resume_checkpoint={},_engineering_resume_context={'entry':'e28_insert'})
    monkeypatch.setattr(ref.importlib,'import_module',lambda *a:SimpleNamespace(solve=lambda *a:{'segment_passed':passed}))
    def capture(actual,stage,context):
        assert actual is controller
        return {'schema':'engineering-native-checkpoint-v1','diagnostic_only':True,
            'source':{'steps':actual.steps,'physics_ticks':actual.physics_ticks},
            'robots':{'right':{'joint_pos':[.2],'joint_vel':[.03],'drive_targets':[.24]}},
            'context':context}
    monkeypatch.setattr(cp,'capture',capture)
    result=ref.solve_suffix(author)
    assert controller.steps==19 and controller.physics_ticks==1900
    assert result['native_task_acceptance'] is False and result['source_initial_episode'] is False
    path=tmp_path/'checkpoints/complete-after-last-action.private.json'
    if not passed:
        assert not path.exists() and 'complete_checkpoint'not in result
        return
    raw=path.read_bytes();saved=json.loads(raw)
    assert saved['source']['steps']==19
    assert saved['robots']['right']['drive_targets']==[.24]
    assert result['complete_checkpoint']['sha256']==hashlib.sha256(raw).hexdigest()
    assert result['complete_checkpoint']['no_physics_advance'] is True
