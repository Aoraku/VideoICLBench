import hashlib,json
from pathlib import Path
from types import SimpleNamespace as N
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_e25_c_return as tail
from videoicl_isaaclab import engineering_checkpoint as core


def test_pinned_initial_policy_home_is_read_without_restoring_world_or_history(monkeypatch):
    identity={'task':'E25','variant':'C'}
    cp={'schema':'engineering-native-checkpoint-v1','identity':identity,'source':{'steps':0,'physics_ticks':840},
        'robots':{s:{'root_state_task':[.1,.2,.3,1.,0.,0.,0.,0.,0.,0.,0.,0.,0.]}for s in('left','right')},
        'controller':{'tcp_targets_base':{s:{'position':[.2,.3,.4],'quaternion':[1.,0.,0.,0.]}for s in('left','right')}}}
    raw=json.dumps(cp).encode();monkeypatch.setattr(Path,'read_bytes',lambda p:raw)
    monkeypatch.setattr(core,'identity',lambda c:identity)
    ref={'path':'/mnt/pfs/robot-agent-public/home/jiemingli/RoboDojo-Audit/engineering/execution-design-v3-20261102-e25c-full-positive-slot10-v5-s4201/result/room-00-E25-C-s4201/engineering-reference/checkpoints/stage-0001-initial.private.json','sha256':hashlib.sha256(raw).hexdigest()}
    home,rot=tail.source_home_context(N(c=N()),ref)
    np.testing.assert_allclose(home['left'],[.3,.5]);np.testing.assert_allclose(rot['left'],np.eye(3))
    ref['sha256']='0'*64
    with pytest.raises(ValueError,match='SHA'):tail.source_home_context(N(c=N()),ref)


def test_other_C_boundary_rejects_before_any_native_action(monkeypatch):
    monkeypatch.setattr(tail,'_scope',lambda *a:None)
    a=N(scene=N(spec={'seed':4201}),_engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':592,'physics_ticks':60040}},
        c=N(_engineering_diagnostic_only=True,_engineering_checkpoint_readback_passed=True))
    monkeypatch.setattr(tail,'source_home_context',lambda *a:pytest.fail('must reject before home read'))
    with pytest.raises(ValueError,match='C591'):tail.run_segment(a,'e25_c_empty_return_from591',{'initial_checkpoint':{}})
