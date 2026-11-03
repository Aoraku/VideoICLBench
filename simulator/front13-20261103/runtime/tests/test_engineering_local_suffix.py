from types import SimpleNamespace
import pytest
from videoicl_isaaclab.engineering_local_suffix import solve
from videoicl_isaaclab.execution_design_probe import classify_debug_segment


def test_local_stage_can_never_be_classified_as_source_initial_positive():
    for raw in ({'segment_passed':True,'task_score_100':100,'strict_success':True},{'segment_passed':False},None):
        result=classify_debug_segment(raw,[],True)
        assert result['native_positive_passed'] is False
        assert result['checkpoint_resume_diagnostic_only']
    assert classify_debug_segment({'segment_passed':True},[],True)['debug_segment_passed']
    assert not classify_debug_segment({'segment_passed':True},['actual grip lost'],True)['debug_segment_passed']
    assert not classify_debug_segment({'segment_passed':True},[],False)['debug_segment_passed']


def test_local_dispatch_rejects_unrestored_or_unrecovered_axes():
    author=SimpleNamespace(scene=SimpleNamespace(spec={'id':'E31'},robots={'left':None,'right':None}),c=SimpleNamespace(),control_report={'engineering_reference_only':True})
    with pytest.raises(ValueError,match='admitted'):solve(author,{'diagnostic_only':True},{'entry':'e31_release'})
    author.c._engineering_diagnostic_only=True
    with pytest.raises(ValueError,match='axis signs'):solve(author,{'diagnostic_only':True},{'entry':'e31_release'})
    with pytest.raises(ValueError,match='supported'):solve(author,{'diagnostic_only':True},{'entry':'arbitrary_module'})
