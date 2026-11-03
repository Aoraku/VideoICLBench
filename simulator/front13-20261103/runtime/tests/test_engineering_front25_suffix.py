from types import SimpleNamespace
import pytest
from videoicl_isaaclab import engineering_front25_suffix as suffix
from videoicl_isaaclab.execution_design_probe import classify_debug_segment


def author():
    return SimpleNamespace(scene=SimpleNamespace(spec={'id':'E24'}),
                           _execution_design_reference_authorized=False)


def test_segment_reuses_original_entry_with_temporary_authorization(monkeypatch):
    a=author();seen=[]
    def run(current,entry,parameters):
        assert current._execution_design_reference_authorized
        seen.append((entry,parameters));return dict(local_completed=True,operations=['actual push'])
    monkeypatch.setattr(suffix.importlib,'import_module',lambda *x:SimpleNamespace(run_segment=run))
    r=suffix.solve(a,{},dict(entry='e24_pickup_lid_overhang',parameters={'expected_left_tip_task_m':[0,0,1]}))
    assert seen and r['segment_passed'] and not r['full_task_acceptance']
    assert not a._execution_design_reference_authorized
    status=classify_debug_segment(r,[],True)
    assert status['debug_segment_passed'] and status['native_positive_passed']is False


def test_failure_propagates_and_permission_is_restored(monkeypatch):
    a=author()
    def fail(*x):raise RuntimeError('actual wrist collision')
    monkeypatch.setattr(suffix.importlib,'import_module',lambda *x:SimpleNamespace(run_segment=fail))
    with pytest.raises(RuntimeError,match='collision'):
        suffix.solve(a,{},dict(entry='e24_pickup_lid_overhang',parameters={}))
    assert not a._execution_design_reference_authorized


def test_wrong_task_entry_and_full_grade_injection_are_rejected(monkeypatch):
    with pytest.raises(ValueError,match='registered'):
        suffix.solve(author(),{},dict(entry='e25_source_spoon_b',parameters={}))
    monkeypatch.setattr(suffix.importlib,'import_module',lambda *x:SimpleNamespace(run_segment=lambda *x:dict(local_completed=True,task_score_100=100)))
    with pytest.raises(ValueError,match='grade'):
        suffix.solve(author(),{},dict(entry='e24_pickup_lid_overhang',parameters={}))


def restored_blue_author():
    return SimpleNamespace(scene=SimpleNamespace(spec={'id':'E20','variant':'C','seed':4201}),
        c=SimpleNamespace(_engineering_diagnostic_only=True,_engineering_checkpoint_readback_passed=True),
        control_report={'engineering_reference_only':True},_execution_design_reference_authorized=False)


@pytest.mark.parametrize('entry',['e20_grasp_and_lift_blue','e20_b_grasp_and_lift_blue1'])
def test_new_blue_lift_uses_registered_module_and_shared_restore_readback_gate(monkeypatch,entry):
    a=restored_blue_author();seen=[]
    def load(name,package):
        seen.append(name)
        def run(current,actual_entry,parameters):
            assert current._execution_design_reference_authorized and actual_entry==entry and parameters=={}
            return {'local_completed':True,'operations':['actual short lift']}
        return SimpleNamespace(run_segment=run)
    monkeypatch.setattr(suffix.importlib,'import_module',load)
    r=suffix.solve(a,{'diagnostic_only':True},{'entry':entry,'parameters':{}})
    assert seen==['.execution_design_segments_e17_e20']and r['segment_passed']and not r['full_task_acceptance']
    assert a._execution_design_reference_authorized is False


@pytest.mark.parametrize('fault',['checkpoint','engineering','restore','readback'])
@pytest.mark.parametrize('entry',['e20_grasp_and_lift_blue','e20_b_grasp_and_lift_blue1'])
def test_blue_lift_cannot_dispatch_before_common_native_admission(monkeypatch,fault,entry):
    a=restored_blue_author();checkpoint={'diagnostic_only':True}
    if fault=='checkpoint':checkpoint['diagnostic_only']=False
    elif fault=='engineering':a.control_report.clear()
    elif fault=='restore':a.c._engineering_diagnostic_only=False
    else:a.c._engineering_checkpoint_readback_passed=False
    monkeypatch.setattr(suffix.importlib,'import_module',lambda *x:pytest.fail('must refuse before handler import'))
    with pytest.raises(ValueError,match='admitted'):
        suffix.solve(a,checkpoint,{'entry':entry,'parameters':{}})
    assert a._execution_design_reference_authorized is False


@pytest.mark.parametrize('entry',['e17_b_resume_held_upper_triangle_848','e17_b_place_held_upper_from_hover_722'])
def test_E17_native848_short_entry_uses_same_admission_gate_and_held_module(monkeypatch,entry):
    a=restored_blue_author();a.scene.spec={'id':'E17','variant':'B','seed':4201};seen=[]
    def load(name,package):
        seen.append(name);return SimpleNamespace(run_segment=lambda *args:{'local_completed':True,'operations':[]})
    monkeypatch.setattr(suffix.importlib,'import_module',load)
    r=suffix.solve(a,{'diagnostic_only':True},{'entry':entry,'parameters':{}})
    assert seen==['.execution_design_segments_e17_held_upper']and r['segment_passed']and not r['full_task_acceptance']
    a.c._engineering_checkpoint_readback_passed=False
    with pytest.raises(ValueError,match='admitted'):
        suffix.solve(a,{'diagnostic_only':True},{'entry':entry,'parameters':{}})


def test_E17_native223_wrong_box_regrasp_is_registered_but_still_readback_gated(monkeypatch):
    a=restored_blue_author();a.scene.spec={'id':'E17','variant':'A','seed':4201};seen=[]
    def load(name,package):
        seen.append(name);return SimpleNamespace(run_segment=lambda *args:{'local_completed':True,'operations':[]})
    monkeypatch.setattr(suffix.importlib,'import_module',load)
    r=suffix.solve(a,{'diagnostic_only':True},{'entry':'e17_a_release_box_nudge_regrasp_223','parameters':{}})
    assert r['segment_passed']and seen==['.execution_design_segments_e17_regrasp']
    a.c._engineering_checkpoint_readback_passed=False
    with pytest.raises(ValueError,match='admitted'):
        suffix.solve(a,{'diagnostic_only':True},{'entry':'e17_a_release_box_nudge_regrasp_223','parameters':{}})


@pytest.mark.parametrize('entry,module_name',[('e17_c_confirm_released_upper_blue_222','execution_design_segments_e17_completion'),('e17_c_resume_remaining_after_blue_release_1','execution_design_segments_e17_remaining')])
def test_E17_native222_release_completion_uses_same_native_readback_gate(monkeypatch,entry,module_name):
    a=restored_blue_author();a.scene.spec={'id':'E17','variant':'C','seed':4201};seen=[]
    def load(name,package):
        seen.append(name);return SimpleNamespace(run_segment=lambda *args:{'local_completed':True,'operations':[]})
    monkeypatch.setattr(suffix.importlib,'import_module',load)
    request={'entry':entry,'parameters':{}}
    r=suffix.solve(a,{'diagnostic_only':True},request)
    assert seen==['.'+module_name]and r['segment_passed']and not r['full_task_acceptance']
    a.c._engineering_checkpoint_readback_passed=False
    with pytest.raises(ValueError,match='admitted'):suffix.solve(a,{'diagnostic_only':True},request)


@pytest.mark.parametrize('entry',['e17_a_grasp_green_floor_edge_57','e17_a_grasp_green_base_18'])
def test_E17_native57_floor_edge_is_registered_and_native_readback_gated(monkeypatch,entry):
    a=restored_blue_author();a.scene.spec={'id':'E17','variant':'A','seed':4201};seen=[]
    def load(name,package):
        seen.append(name);return SimpleNamespace(run_segment=lambda *args:{'local_completed':True,'operations':[]})
    monkeypatch.setattr(suffix.importlib,'import_module',load)
    request={'entry':entry,'parameters':{}}
    r=suffix.solve(a,{'diagnostic_only':True},request)
    assert seen==['.execution_design_segments_e17_regrasp_edge']and r['segment_passed']and not r['full_task_acceptance']
    a.c._engineering_checkpoint_readback_passed=False
    with pytest.raises(ValueError,match='admitted'):suffix.solve(a,{'diagnostic_only':True},request)
