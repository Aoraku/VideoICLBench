from types import SimpleNamespace
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_e18_support import VERSION,SOURCE_SHA,LIFT_M
from videoicl_isaaclab import execution_design_e18_reference as module


def test_full_supported_source_uses_validated_two_mm_opening_and_preserves_closing():
    worker=module.E18MeasuredAuthor.__new__(module.E18MeasuredAuthor)
    worker.task='E18';worker.spec=dict(execution_design=dict(revision=REVISION_V3),
        e18_support_layout=dict(version=VERSION,source_cabinet_sha256=SOURCE_SHA,lift_m=LIFT_M))
    worker.a=SimpleNamespace(control_report=dict(engineering_reference_only=True))
    worker._engineering_two_mm_real_reseat=True
    assert worker.drawer_public_step_m('drawer',False)==.002
    assert worker.drawer_public_step_m('drawer',True)is None


def test_full_public_preparation_reuses_exact_native95mm_executor(monkeypatch):
    from videoicl_isaaclab import execution_design_e18_opening as opening
    worker=module.E18MeasuredAuthor.__new__(module.E18MeasuredAuthor)
    worker._engineering_two_mm_real_reseat=True;seen=[]
    monkeypatch.setattr(opening,'prepare',lambda *args:seen.append(args)or dict(real_preparation=True))
    result=worker.prepare_drawer_public_pull('drawer','left')
    assert result['real_preparation']and seen==[(worker,'drawer','left')]
