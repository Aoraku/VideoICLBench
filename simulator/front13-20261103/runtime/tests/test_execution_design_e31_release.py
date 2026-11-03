import pytest
from videoicl_isaaclab.execution_design_e31_release import release_ready


def ready(**changes):
    # Native E31B v8: 24.837mm conservative AABB gap, held above a covered
    # upright bowl. Ready is only an author stop; native result stayed0.
    values=dict(gap_m=.02483698049346842,covered=True,plate_face_ok=True,
        bowl_up=True,held=True,hand_on_bowl=False,plate_bowl_contact=False)
    values.update(changes)
    return release_ready(**values)


def test_real_v8_gap_allows_ordinary_gravity_release_without_claiming_contact():
    assert ready()
    assert not ready(gap_m=.031)
    assert not ready(gap_m=-.001)
    assert ready(gap_m=-.001,plate_bowl_contact=True)


@pytest.mark.parametrize('changes',[dict(covered=False),dict(plate_face_ok=False),
    dict(bowl_up=False),dict(held=False),dict(hand_on_bowl=True)])
def test_drop_stop_retains_real_geometry_grip_and_hand_clearance(changes):
    assert not ready(**changes)
    assert not ready(plate_bowl_contact=True,**changes)


def test_nonfinite_gap_never_permits_release():
    with pytest.raises(ValueError):ready(gap_m=float('nan'))


def test_ordinary_inverted_gravity_drop_keeps_all_physical_preconditions():
    assert ready(gap_m=.0669,maximum_gap_m=.080)
    assert not ready(gap_m=.0801,maximum_gap_m=.080)
    assert not ready(gap_m=.0669,maximum_gap_m=.080,plate_face_ok=False)
    assert not ready(gap_m=.0669,maximum_gap_m=.080,hand_on_bowl=True)


def test_local_suffix_uses_real_conditions_but_preserves_unsealed_history(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from videoicl_isaaclab import execution_design_e31_debug
    required=['released','stable','container_relation','bowl_up','plate_face_orientation','containment_or_rim_coverage','real_bowl_plate_contact']
    native=dict(strict_success=False,success=False,conditions=[dict(type=n,passed=True)for n in required],errors=['source_initial_not_sealed'])
    state={'plate':{'grasp':[False,False]},'bowl':{'grasp':[False,False]}}
    contacts={frozenset(('plate','bowl'))};c=SimpleNamespace(_engineering_diagnostic_only=True,steps=0,evaluator=SimpleNamespace(result=lambda:native),snapshot=lambda:(state,contacts))
    spec=dict(id='E31',semantic=dict(plate='plate',bowl='bowl'),goals=[dict(object='plate')])
    def act():c.steps+=1
    a=SimpleNamespace(scene=SimpleNamespace(spec=spec),c=c,out=tmp_path,release_generated=lambda s:act(),act=act)
    monkeypatch.setattr(execution_design_e31_debug,'lower_for_release',lambda *args:dict(release_ready=True))
    result=execution_design_e31_debug.run(a,{'side':'right'})
    assert result['segment_passed'] and result['diagnostic_only']
    assert not result['actual_native_result']['strict_success']
    assert result['actual_native_result']['errors']==['source_initial_not_sealed']
    contacts.clear()
    with pytest.raises(RuntimeError,match='local real release'):execution_design_e31_debug.run(a,{'side':'right'})


def test_fresh_restoration_limit_guard_does_not_read_uninitialized_public_feedback():
    from types import SimpleNamespace
    import numpy as np
    from videoicl_isaaclab.execution_design_e31_release import check_actual_limits
    def unavailable():raise AssertionError('No public action has initialized feedback yet')
    q=np.array([[0.,-.5]])
    limits=np.array([[[-1.,1.],[-1.,1.]]])
    a=SimpleNamespace(scene=SimpleNamespace(robots={'right':SimpleNamespace(data=SimpleNamespace(joint_pos=q,joint_pos_limits=limits))}),c=SimpleNamespace(ids={'right':([0,1],None,None)},_public_action=None,action_feedback=unavailable))
    check_actual_limits(a,'right')
    q[0,1]=-.9999
    with pytest.raises(RuntimeError,match='at an actual joint limit'):check_actual_limits(a,'right')


def test_flip_diagnostic_retains_B_identity_and_failure_while_checking_C(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from videoicl_isaaclab import execution_design_e31_debug as debug,execution_design_e31_orientation as orientation
    observation=dict(released=True,stable=True,relation='plate_on_bowl',bowl_up=True,
                     plate_up=False,contained_or_covering=True,contacts=[['bowl','plate']])
    native=dict(success=False,failed_checks=['plate_face_orientation'],observation=observation)
    state={'plate':{'grasp':[False,False],'mat':[[1,0,0],[0,-1,0],[0,0,-1]]},'bowl':{'grasp':[False,False]}}
    c=SimpleNamespace(_engineering_diagnostic_only=True,steps=0,evaluator=SimpleNamespace(result=lambda:native),snapshot=lambda:(state,{frozenset(('plate','bowl'))}))
    spec=dict(id='E31',variant='B',semantic=dict(plate='plate',bowl='bowl'),goals=[dict(object='plate',pitch=0.)])
    def act():c.steps+=1
    a=SimpleNamespace(scene=SimpleNamespace(spec=spec),c=c,out=tmp_path,release_generated=lambda s:act(),act=act)
    seen=[]
    monkeypatch.setattr(orientation,'align_face',lambda a,n,s,g:seen.append(g.copy()))
    monkeypatch.setattr(debug,'lower_for_release',lambda *args:dict(release_ready=True))
    result=debug.run_flip(a,{'side':'right'})
    assert result['segment_passed'] and result['actual_C_rule_observation_check']['success']
    assert result['actual_native_B_result']['failed_checks']==['plate_face_orientation']
    assert spec['variant']=='B' and spec['goals'][0]['pitch']==0.
    assert seen[0]['pitch']==pytest.approx(3.141592653589793)
    observation['stable']=False
    with pytest.raises(RuntimeError,match='original C physical conditions'):debug.run_flip(a,{'side':'right'})


def test_real_inverted_rim_uses_outward_back_withdrawal():
    from videoicl_isaaclab.execution_design_e31_narrow_release import outward_route
    assert outward_route([-.06536,.09405,1.0095],[.00977,.12792,.97865],{0:1,1:1})==(0,-1,'BACK')
    assert outward_route([-.06536,.09405,1.0095],[.00977,.12792,.97865],{0:-1,1:1})==(0,-1,'FWD')
    with pytest.raises(ValueError):outward_route([0,0,1],[.01,0,1],{0:1,1:1})
