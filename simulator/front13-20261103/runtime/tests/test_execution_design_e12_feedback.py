import numpy as np
import pytest
from test_execution_design_e12_reference import aperture_author
from videoicl_isaaclab.execution_design_e12_feedback import PinResponse
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def predictor(shift=(-.00018,0,0)):
    a=aperture_author(shift=shift);p=PinResponse(a,'charger_1',1,'right')
    p.samples={'DOWN':[np.array([-.000148,-.000027,-.000783,0,0,0])]*2,
               'FWD':[np.array([.000318,-.000028,-.000337,0,0,0])]*2}
    return a,p


def test_native_sized_down_drift_precompensated_before_actual_margin_is_lost():
    a,p=predictor();before=tuple(v.copy()for v in a.frame({'actor':'charger_1'}))
    assert p.path_margin(['DOWN'])is None
    assert p.path_margin(['FWD','DOWN'])>.00005
    assert p.choose()=='FWD'
    after=a.frame({'actor':'charger_1'})
    for x,y in zip(before,after):np.testing.assert_array_equal(x,y)


def test_no_unknown_or_inconsistent_response_used_near_hole():
    a,p=predictor();p.samples['FWD']=p.samples['FWD'][:1]
    with pytest.raises(ToolExecutionError,match='no measured safe'):
        p.choose()
    p.samples['FWD']=[np.zeros(6),np.array([.001,0,0,0,0,0])]
    assert p.response('FWD')is None


def test_second_pin_and_rotation_sweep_reject_false_translation_only_fit():
    a,p=predictor();p.samples['FWD']=[np.array([.000318,0,0,0,.06,0])]*2
    assert p.path_margin(['FWD','DOWN'])is None


def test_centered_pair_can_advance_without_unnecessary_side_action():
    a,p=predictor((0,0,0));assert p.choose()=='DOWN'


def test_corner_requires_two_measured_lateral_steps_before_down():
    # A slightly centered corner retains room for measured response uncertainty.
    a,p=predictor((-.000182,-.000200,0))
    p.samples['FWD']=[np.array([.000303,-.000029,-.000336,0,0,0])]*2
    p.samples['DOWN']=[np.array([-.000136,-.000027,-.000780,0,0,0])]*2
    p.samples['LEFT']=[np.array([-.000135,.000412,-.000339,0,0,0])]*2
    assert all(p.path_margin([token,'DOWN'])is None for token in ('FWD','BACK','LEFT','RIGHT'))
    assert p.path_margin(['FWD','LEFT','DOWN'])>.00005
    assert p.choose()=='FWD'


def test_corner_recenter_allowed_only_in_clear_air(monkeypatch):
    from test_execution_design_e12_reference import insertion_mock
    from videoicl_isaaclab import execution_design_e12_feedback as feedback
    from videoicl_isaaclab.execution_design_e12_reference import insert_charger_precisely
    a,events=insertion_mock(monkeypatch);original=a.point;calls=[0]
    # Represent a small lateral corner error when the lookahead first rejects.
    a.point=lambda ref:original(ref)+np.array([.0002,0,0])
    def choose(self):
        calls[0]+=1
        if calls[0]==1:raise ToolExecutionError('E12 no measured safe public action through both apertures')
        return 'DOWN'
    monkeypatch.setattr(feedback.PinResponse,'choose',choose)
    insert_charger_precisely(a,'charger_1',{'actor':'charger_1'},'right',1,a.frame({'actor':'charger_1'})[1],.0119)
    start=events.index('precision-insert-both-pins-slot-1')
    assert events[start+1]=='BACK';assert 'RELEASE'in events


@pytest.mark.parametrize('gap,contact',[(.002,False),(.023,True)])
def test_lookahead_failure_near_socket_does_not_trigger_free_air_recovery(monkeypatch,gap,contact):
    from test_execution_design_e12_reference import insertion_mock
    from videoicl_isaaclab import execution_design_e12_feedback as feedback
    from videoicl_isaaclab import execution_design_e12_reference as reference
    a,events=insertion_mock(monkeypatch)
    active=lambda:'precision-insert-both-pins-slot-1'in events
    a.contact=lambda *args:contact and active()
    monkeypatch.setattr(reference,'pin_aperture_diagnostics',lambda *args:[dict(fits=True,axial_m=gap if active()else .025,margin_m=[.0003,.0003])]*2)
    def reject(self):raise ToolExecutionError('E12 no measured safe public action through both apertures')
    monkeypatch.setattr(feedback.PinResponse,'choose',reject)
    with pytest.raises(ToolExecutionError,match='no measured safe'):
        reference.insert_charger_precisely(a,'charger_1',{'actor':'charger_1'},'right',1,a.frame({'actor':'charger_1'})[1],.0119)
    assert events[-1]=='precision-insert-both-pins-slot-1'


def test_multistep_search_never_uses_unknown_second_lateral_response():
    a,p=predictor((-.000182,-.000216,0))
    p.samples['FWD']=[np.array([.000303,-.000029,-.000336,0,0,0])]*2
    p.samples['DOWN']=[np.array([-.000136,-.000027,-.000780,0,0,0])]*2
    # LEFT would make the route possible, but a single response is insufficient.
    p.samples['LEFT']=[np.array([-.000135,.000412,-.000339,0,0,0])]
    with pytest.raises(ToolExecutionError,match='no measured safe'):p.choose()


def test_public_hold_requires_same_measured_context_and_does_not_create_target():
    a,p=predictor();p.samples['STILL']=[np.array([.00004,0,0,0,0,0])]*2
    assert p.path_margin(['STILL','DOWN'])is None
    p.last_token='DOWN'
    # This example only verifies context; no hidden setter exists on author.
    assert p.path_margin(['FWD','STILL','DOWN'])is None
    assert p.path_margin(['STILL','STILL','DOWN'])is None
    p.last_token='GRASP'
    with pytest.raises(ToolExecutionError,match='preceding calibrated'):p.act('STILL')


def test_still_executes_only_public_token_and_records_actual_response():
    a,p=predictor((0,0,0));calls=[]
    a.act=lambda side,token,mm:calls.append((side,token,mm))
    p.last_token='DOWN';p.act('STILL')
    assert calls==[('right','STILL',.5)]
    assert p.last_token=='STILL' and len(p.samples['STILL'])==1
    np.testing.assert_array_equal(p.samples['STILL'][0],np.zeros(6))


def test_prediction_reserve_rejects_old_barely_fitting_corner_before_real_guard():
    a,p=predictor((-.000182,-.000216,0))
    p.samples['FWD']=[np.array([.000303,-.000029,-.000336,0,0,0])]*2
    p.samples['DOWN']=[np.array([-.000136,-.000027,-.000780,0,0,0])]*2
    p.samples['LEFT']=[np.array([-.000135,.000412,-.000339,0,0,0])]*2
    assert p.path_margin(['FWD','LEFT','DOWN'])is None


def test_measured_repeatability_is_reserved_in_addition_to_nominal_geometry():
    a,p=predictor((0,0,0));assert p.path_margin(['DOWN'])is not None
    p.samples['DOWN']=[np.array([-.000148+x,-.000027,-.000783,0,0,0])for x in(-.0001,.0001)]
    assert p.response('DOWN')is not None
    assert p.path_margin(['DOWN'])is None


def test_public_hold_samples_remain_separate_for_each_prior_translation():
    a,p=predictor((0,0,0));calls=[]
    a.act=lambda side,token,mm:calls.append((side,token,mm))
    for direction in ('FWD','BACK','LEFT','RIGHT','DOWN'):
        p.last_token=direction;p.act('STILL')
        key='STILL'if direction=='DOWN'else'STILL_AFTER_'+direction
        assert len(p.samples[key])==1
    assert calls==[('right','STILL',.5)]*5
    with pytest.raises(ToolExecutionError,match='preceding calibrated'):p.act('STILL')


def test_hold_from_other_context_cannot_be_used_as_unknown_forward_hold():
    a,p=predictor((0,0,0));p.last_token='FWD'
    p.samples['STILL']=[np.array([0,0,-.0001,0,0,0])]*2
    assert p.path_margin(['STILL','DOWN'])is None
    p.samples['STILL_AFTER_FWD']=[np.zeros(6)]*2
    assert p.path_margin(['STILL','DOWN'])is not None
