import hashlib,json
from pathlib import Path
from copy import deepcopy
import numpy as np
import pytest
from test_execution_design_e25_a_receiver import fixture
from videoicl_isaaclab import execution_design_e25_functional as functional
from videoicl_isaaclab import execution_design_e25_remaining as remaining
from videoicl_isaaclab import engineering_checkpoint as core


def test_already_clear_empty_hand_does_not_reset_home_or_orientation(tmp_path):
    a,state,contacts=fixture(tmp_path)
    a.finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',
        fingers=[dict(aabb_min_task_m=[.5,.5,1.0],aabb_max_task_m=[.52,.52,1.05])]*2)
    a.act=lambda *args,**kwargs:pytest.fail('actual clearance already sufficient')
    functional.withdraw_released(a,'left')
    assert a.control_report['e25_functional_hand_switches'][-1]['actions']==0


def test_remaining_gate_requires_real_native_readback(tmp_path):
    a,state,contacts=fixture(tmp_path);a.c._engineering_diagnostic_only=True;a.c._engineering_checkpoint_readback_passed=False
    with pytest.raises(ValueError,match='Admitted'):remaining.validate_resume(a,dict(home_xy={},active_hand='left',completed_objects=['spoon']))


def test_native_A586_relay_sizes_remaining_payloads_but_keeps_completed_spoon_obstacle(tmp_path):
    from videoicl_isaaclab.execution_design_e07_reference import staging_target
    a,state,contacts=fixture(tmp_path)
    measured={
        'fork':([.0343065858,-.144445926,.809024749],[[.993353903,.114493191,-.011799491],[-.114485145,.993423998,.001359155],[.011877513,.000000743,.999929488]]),
        'spoon':([.229975939,.177660689,.808661458],[[.998983145,.044965088,.003291671],[-.045078278,.997458816,.055170637],[-.000802554,-.055262916,.998471498]]),
        'knife':([-.000455,-.089385107,.806803164],[[.99865371,.000755966,-.051867869],[.003776193,.996181428,.087226212],[.051735755,-.087304637,.994837344]]),
        'tray':([-.000038231,.120020241,.819995282],[[.999999881,.000018477,-.000364806],[-.000018299,.999999881,.00053441],[.000364816,-.000534403,.999999762]])}
    for name,(position,rotation)in measured.items():state[name].update(pos=np.array(position),mat=np.array(rotation))
    original=deepcopy(a.scene.spec)
    with pytest.raises(RuntimeError,match='No measured empty'):staging_target(a)
    goals=[g for g in a.scene.spec['goals']if g['object']!='spoon']
    target=staging_target(a,goals)
    np.testing.assert_allclose(target['xy'],[-.2,-.03])
    assert a.scene.spec==original
    state['spoon']['pos'][:2]=target['xy']
    with pytest.raises(RuntimeError,match='No measured empty'):staging_target(a,goals)


@pytest.mark.parametrize('boundary',[(586,59440),(186,18602)])
def test_A586_remaining_reuses_original_goals_without_replaying_spoon_or_claiming_grade(tmp_path,monkeypatch,boundary):
    a,state,contacts=fixture(tmp_path);a._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':boundary[0],'physics_ticks':boundary[1]}}
    a.c._engineering_diagnostic_only=True;a.c._engineering_checkpoint_readback_passed=True
    initial={'identity':{'task':'E25','variant':'A'},'source':{'steps':0},
        'robots':{s:{'root_state_task':[0,0,0,1,0,0,0,0,0,0,0,0,0]}for s in('left','right')},
        'controller':{'tcp_targets_base':{s:{'position':[-.3,.1,1.],'quaternion':[1,0,0,0]}for s in('left','right')}}}
    raw=json.dumps(initial).encode();monkeypatch.setattr(Path,'read_bytes',lambda p:raw);monkeypatch.setattr(core,'identity',lambda c:initial['identity'])
    def place(name):
        g=next(g for g in a.scene.spec['goals']if g['object']==name);z=next(z for z in a.scene.spec['zones']if z['id']==g['target'])
        xy=np.asarray(z['xy']);support=z.get('support','table')
        if z.get('anchor_object'):
            anchor=state[z['anchor_object']];xy=(anchor['pos']+anchor['mat']@np.asarray(z.get('anchor_local_center',[0,0,0])))[:2];support=z.get('support',z['anchor_object'])
        state[name]['pos']=np.r_[xy,.809];contacts.add(frozenset((name,support)))
    place('spoon');old=deepcopy(a.scene.spec);calls=[]
    def solve():
        expected=['spoon']if boundary[0]==586 else['spoon','knife']
        assert a._engineering_e25_remaining['completed_objects']==expected
        for name in('fork','knife'):
            if name not in expected:calls.append(name);place(name)
    a.solve_generated=solve
    if boundary[0]==186:
        from videoicl_isaaclab import execution_design_e25_a_receiver as receiver
        monkeypatch.setattr(functional,'prepare_next_pickup',lambda *args:calls.append('actual_palm'))
        monkeypatch.setattr(receiver,'place_settled_knife',lambda *args:(calls.append('knife'),place('knife')))
    ref={'path':'/mnt/pfs/robot-agent-public/home/jiemingli/RoboDojo-Audit/engineering/execution-design-v3-20261102-e25a-full-positive-slot10-v8-s4201/result/room-00-E25-A-s4201/engineering-reference/checkpoints/stage-0001-initial.private.json','sha256':hashlib.sha256(raw).hexdigest()}
    entry='e25_a_finish_remaining_from586'if boundary[0]==586 else'e25_a_finish_after_knife_relay186'
    result=remaining.run_segment(a,entry,{'initial_checkpoint':ref})
    expected=['fork','knife']if boundary[0]==586 else['actual_palm','knife','fork']
    assert result['local_completed']and calls==expected and a.scene.spec==old
    assert not {'task_score_100','success','strict_success'}&result.keys()
    assert not hasattr(a,'_engineering_e25_remaining')


def test_next_pickup_levels_tilted_empty_palm_before_any_translation(tmp_path):
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    a,state,contacts=fixture(tmp_path);rotation=_axis_rotation([0,1,0],np.deg2rad(55))@np.diag([1.,-1.,-1.])
    a.tcp_rotation_task=lambda side:rotation.copy();tip=a.tip('left');before=deepcopy(a.scene.spec)
    def geometry(side):
        origins=[tip+rotation[:,1]*v+[0,0,.04]for v in(-.04,.04)]
        return dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=.90,
            fingers=[dict(body_origin_task_m=p,aabb_min_task_m=p-[.005,.005,.01],aabb_max_task_m=p+[.005,.005,.01])for p in origins])
    a.finger_geometry=geometry;a.move_generated=lambda *args,**kwargs:pytest.fail('must rotate before translation')
    a.c.action_feedback=lambda:{'control_feedback':{'left':{'status':'reached'}}};calls=[]
    axes={'ROLL_LEFT':[1,0,0],'ROLL_RIGHT':[-1,0,0],'PITCH_UP':[0,1,0],'PITCH_DOWN':[0,-1,0],'ROTATE_CCW':[0,0,1],'ROTATE_CW':[0,0,-1]}
    def act(left,right,rotation_deg):
        nonlocal rotation
        assert right=='STILL';calls.append(left);rotation=_axis_rotation(axes[left],np.deg2rad(rotation_deg))@rotation
    a.act=act;functional.prepare_next_pickup(a,'left','knife')
    assert 1<=len(calls)<=8 and rotation[2,2]<-np.cos(np.deg2rad(5))
    assert a.scene.spec==before
