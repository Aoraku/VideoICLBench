from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_e19_reference import cap_transport_height, move_cap_point, retreat_empty_hand
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


class Tool:
    def __init__(self):
        self.task='E19'
        self.spec=dict(execution_design=dict(revision=REVISION_V3),objects=[
            dict(id='bottle',size=[.03,.03,.1]),dict(id='cap',size=[.017,.017,.007])])
        self.position=np.array([-.13,0.,1.08]);self.calls=[];self.blocked=False
        self.state={'bottle':dict(pos=np.array([.06,0.,.9]),mat=np.eye(3)),
                    'cap':dict(pos=self.position+[0,0,.007],mat=np.eye(3))}
        self.a=SimpleNamespace(control_report=dict(engineering_reference_only=True),
            finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=float(self.position[2]-.005)))
    def snapshot(self):return self.state,set()
    def point(self,ref):return self.position.copy()
    def act(self,side,token,mm):
        self.calls.append((side,token,mm))
        if self.blocked:return
        axis,sign={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}[token]
        # Public command limits and slight cross-axis drift, not a pose setter.
        self.position[axis]+=sign*min(10.,max(.5,mm))*.001*.8
        self.position[(axis+1)%3]+=.00005


def test_height_clears_real_bottle_and_finger_without_fixed_high_plane():
    t=Tool();r=cap_transport_height(t,'cap','left',[0,0,-.007],[.06,0,.979])
    assert r['height_m']==pytest.approx(1.03)
    assert r['height_m']-r['depth_below_working_point_m']>=1.025
    assert not r['native_reachability_verified']


def test_material_point_feedback_converges_with_grip_drift():
    t=Tool();target=np.array([.06,0.,1.03]);calls=[]
    move_cap_point(t,'left',{'actor':'cap'},target,lambda:calls.append(1))
    assert np.max(abs(t.position-target))<=.002
    assert 15<len(t.calls)<100 and len(calls)==len(t.calls)+1


def test_actual_point_stall_and_grip_loss_are_not_bypassed():
    t=Tool();t.blocked=True
    with pytest.raises(ToolExecutionError,match='stalled'):
        move_cap_point(t,'left',{'actor':'cap'},[.06,0,1.03],lambda:None)
    assert len(t.calls)==32
    t=Tool()
    def lost():raise ToolExecutionError('actual grip lost')
    with pytest.raises(ToolExecutionError,match='grip lost'):
        move_cap_point(t,'left',{'actor':'cap'},[.06,0,1.03],lost)
    assert not t.calls


@pytest.mark.parametrize('change',[
    lambda t:setattr(t,'task','E24'),
    lambda t:t.spec['execution_design'].update(revision='old'),
    lambda t:t.a.control_report.clear()])
def test_only_explicit_v3_e19_engineering(change):
    t=Tool();change(t)
    with pytest.raises(ValueError):move_cap_point(t,'left',{'actor':'cap'},[0,0,1],lambda:None)
    assert not t.calls


def test_unmeasured_finger_and_nonfinite_target_are_rejected():
    t=Tool();t.a.finger_geometry=lambda side:dict(source='authored_guess',lowest_z_task_m=.8)
    with pytest.raises(ValueError):cap_transport_height(t,'cap','left',[0,0,-.007],[0,0,1])
    with pytest.raises(ValueError):move_cap_point(t,'left',{'actor':'cap'},[0,0,float('nan')],lambda:None)


def test_released_hand_vacates_bottle_zone_at_measured_clearance():
    t=Tool();t.position=np.array([.06,-.15,1.05]);moves=[]
    t.tip=lambda side:t.position.copy()
    t.stage=lambda stage:None
    def move(side,target,guard):
        guard();moves.append(np.asarray(target).copy());t.position=np.asarray(target)
    t.move=move
    retreat_empty_hand(t,'right',[-.19,-.30],1.025)
    np.testing.assert_allclose(moves[0],[.06,-.15,1.085])
    np.testing.assert_allclose(moves[1],[-.19,-.30,1.085])


def test_empty_retreat_cannot_move_a_still_grasped_payload():
    t=Tool();t.state['cap']['grasp']=[False,True]
    t.tip=lambda side:t.position.copy()
    t.stage=lambda stage:None
    t.move=lambda *args,**kwargs:pytest.fail('Must reject before moving')
    with pytest.raises(ToolExecutionError,match='actual empty hand'):
        retreat_empty_hand(t,'right',[-.19,-.30],1.025)


@pytest.mark.parametrize('source_y,target_y,expected',[(0.,-.15,'right'),(-.13,.15,'left'),(.13,-.15,'right')])
def test_cap_hand_considers_source_and_destination_native_bases(source_y,target_y,expected):
    from videoicl_isaaclab.execution_design_e19_reference import choose_cap_hand
    t=Tool();t.position=np.array([-.13,source_y,.81]);t.ref=lambda name:{'actor':name}
    t.a.scene=SimpleNamespace(robots={side:SimpleNamespace(data=SimpleNamespace(root_pos_w=np.array([[-.65,y,.75]])))for side,y in [('left',.3),('right',-.3)]},world_to_task=lambda p:p)
    assert choose_cap_hand(t,'cap',[.06,target_y,.99])==expected
    assert not t.calls and not t.a.control_report['e19_hand_choices'][0]['native_reachability_verified']
    with pytest.raises(ValueError):choose_cap_hand(t,'cap',[float('nan'),0,1])


class GravityTool:
    """CPU action-feedback fixture; never claims physical native acceptance."""
    def __init__(self,tmp_path,fault=None):
        self.task='E19';self.calls=[];self.fault=fault;self.releases=0
        self.spec={'variant':'C','execution_design':{'revision':REVISION_V3},'objects':[
            {'id':'cap_red','source_asset':{'sha256':'a8d1a023e305cc173e0bda92a4c52f7f2f20731a32894b4fbab2a2669f840c4a'}},
            {'id':'water_bottle','source_asset':{'sha256':'a1063067fb4ff0db03ba5436820756f9149f6eb45b5c9c5973ef5d6274eff71f'}}],
            'semantic':{'caps':{'cap_red':dict(center_local=[0,0,-.007],axis_local=[0,0,1],depth=.011,inner_radius=.0145)},
                        'mouths':{'water_bottle':dict(center_local=[0,0,.095],axis_local=[0,0,1],outer_radius=.014)}}}
        self.state={'water_bottle':dict(pos=np.array([.06,.15,.90]),mat=np.eye(3),grasp=[False,False]),
                    'cap_red':dict(pos=np.array([.062,.149,1.027]),mat=np.eye(3),grasp=[True,False])}
        self.contacts={frozenset(('cap_red','left_finger1')),frozenset(('cap_red','left_finger2'))}
        self.a=SimpleNamespace(out=tmp_path,control_report={'engineering_reference_only':True},finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=float(self.opening()[2]-.0007)))
        self.finger_qd=np.zeros((1,2))
        self.a.scene=SimpleNamespace(robots={'left':SimpleNamespace(data=SimpleNamespace(joint_vel=self.finger_qd),find_joints=lambda pattern:([0,1],['panda_finger_joint1','panda_finger_joint2']))})
    def label(self,name):return 'red'if name=='cap_red'else name
    def snapshot(self):return self.state,self.contacts
    def opening(self):return self.state['cap_red']['pos']+self.state['cap_red']['mat']@np.array([0,0,-.007])
    def mouth(self):return self.state['water_bottle']['pos']+np.array([0,0,.095])
    def stage(self,name):pass
    def require_held(self,ref,side):
        if not self.state['cap_red']['grasp'][0]:raise ToolExecutionError('actual grip lost')
    def act(self,side=None,token='STILL',mm=None,degrees=None):
        self.calls.append(token)
        if token=='STILL':return
        if mm is not None:
            axis,sign={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}[token]
            assert .5<=mm<=1.;self.state['cap_red']['pos'][axis]+=sign*mm*.001*.8
        else:
            from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
            axis={'ROLL_LEFT':[1,0,0],'ROLL_RIGHT':[-1,0,0],'PITCH_UP':[0,1,0],'PITCH_DOWN':[0,-1,0],'ROTATE_CCW':[0,0,1],'ROTATE_CW':[0,0,-1]}[token]
            self.state['cap_red']['mat']=_axis_rotation(axis,np.deg2rad(degrees))@self.state['cap_red']['mat']
        if self.fault=='bottle_move':self.state['water_bottle']['pos'][0]+=.003
        elif self.fault=='finger_contact':self.contacts.add(frozenset(('water_bottle','left_finger1')))
        elif self.fault=='grip':self.state['cap_red']['grasp'][0]=False
        elif self.fault=='small_mouth_shift'and len(self.calls)==1:self.state['water_bottle']['pos'][1]+=.0005
    def release(self,ref,side):
        assert self.opening()[2]-self.mouth()[2]>.002
        assert np.max(abs((self.opening()-self.mouth())[:2]))<=.0006
        self.releases+=1;self.state['cap_red']['grasp']=[False,False]
        self.contacts={frozenset(('cap_red','water_bottle'))}if self.fault!='no_support'else set()
        # Fixture response to RELEASE; the implementation may never set poses.
        self.state['cap_red']['pos']=self.mouth()+([0,0,.03]if self.fault=='wrong_pose'else[0,0,-.003])
    def tip(self,side):return self.opening()+[0,0,.01]
    def move(self,side,target):assert self.releases==1
    def wait(self,n):pass
    def contact(self,a,b):return frozenset((a,b))in self.contacts


@pytest.mark.parametrize('fault',[None,'small_mouth_shift'])
def test_gravity_candidate_tracks_actual_mouth_and_releases_above_rim(tmp_path,fault):
    import json
    from videoicl_isaaclab.execution_design_e19_reference import gravity_seat_red_water
    t=GravityTool(tmp_path,fault);before=json.dumps(t.spec,sort_keys=True)
    gravity_seat_red_water(t,'cap_red',{'actor':'cap_red'},'left',{'actor':'cap_red','local':[0,0,-.007]},'water_bottle')
    assert t.releases==1 and json.dumps(t.spec,sort_keys=True)==before
    rows=[json.loads(x)for x in (tmp_path/'e19-c-gravity-seating.private.jsonl').read_text().splitlines()]
    before=next(r for r in rows if r['phase']=='before_real_release')
    assert before['gap_m']>.002 and before['finger_lowest_z']>before['mouth'][2]+.0015
    assert before['finger_velocity_observation_only']and before['finger_qd_m_s']==[0.,0.]
    assert rows[-1]['actual_support_contact']and rows[-1]['actual_covering']and not rows[-1]['native_accepted']


@pytest.mark.parametrize('fault',['bottle_move','finger_contact','grip','no_support','wrong_pose'])
def test_gravity_candidate_does_not_push_stale_mouth_or_forge_support(tmp_path,fault):
    from videoicl_isaaclab.execution_design_e19_reference import gravity_seat_red_water
    t=GravityTool(tmp_path,fault)
    with pytest.raises(ToolExecutionError):gravity_seat_red_water(t,'cap_red',{'actor':'cap_red'},'left',{'actor':'cap_red'},'water_bottle')
    assert t.releases==int(fault in ('no_support','wrong_pose'))


def test_gravity_candidate_keeps_legacy_other_pairs_out_and_pins_sources(tmp_path):
    from videoicl_isaaclab.execution_design_e19_reference import gravity_seat_red_water
    t=GravityTool(tmp_path);t.spec['variant']='A'
    with pytest.raises(ValueError):gravity_seat_red_water(t,'cap_red',{},'left',{},'water_bottle')
    t.spec['variant']='C';t.spec['objects'][0]['source_asset']['sha256']='unreviewed'
    with pytest.raises(ValueError):gravity_seat_red_water(t,'cap_red',{},'left',{},'water_bottle')
    assert not t.calls and t.releases==0


def test_gravity_candidate_aligns_actual_cap_axis_with_public_rotations(tmp_path):
    from videoicl_isaaclab.execution_design_e19_reference import gravity_seat_red_water
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    t=GravityTool(tmp_path);t.state['cap_red']['mat']=_axis_rotation([1,0,0],np.deg2rad(5))
    gravity_seat_red_water(t,'cap_red',{'actor':'cap_red'},'left',{'actor':'cap_red'},'water_bottle')
    assert 'ROLL_RIGHT'in t.calls and t.releases==1


def test_checkpoint_rim_tail_starts_at_actual_pre_release_gap_without_replaying_alignment(tmp_path):
    from videoicl_isaaclab.execution_design_e19_reference import gravity_seat_red_water
    t=GravityTool(tmp_path);t.state['cap_red']['pos']=t.mouth()+[0,0,.010]
    gravity_seat_red_water(t,'cap_red',{'actor':'cap_red'},'left',{'actor':'cap_red'},'water_bottle',entry_phase='rim_release')
    assert t.releases==1 and t.calls==[]


def test_checkpoint_rim_tail_rejects_unaligned_held_cap_without_low_rotation(tmp_path):
    from videoicl_isaaclab.execution_design_e19_reference import gravity_seat_red_water
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    t=GravityTool(tmp_path);t.state['cap_red']['pos']=t.mouth()+[0,0,.010]
    t.state['cap_red']['mat']=_axis_rotation([1,0,0],np.deg2rad(1))
    with pytest.raises(ToolExecutionError,match='axis drifted'):
        gravity_seat_red_water(t,'cap_red',{'actor':'cap_red'},'left',{'actor':'cap_red'},'water_bottle',entry_phase='rim_release')
    assert not t.calls and t.releases==0


@pytest.mark.parametrize('velocity',[[.002,0.],[-.0526,.0693],[0.,-.002]])
def test_actual_finger_velocity_is_observed_without_extra_settling(tmp_path,velocity):
    from videoicl_isaaclab.execution_design_e19_reference import gravity_seat_red_water
    import json
    t=GravityTool(tmp_path);t.state['cap_red']['pos']=t.mouth()+[0,0,.010];t.finger_qd[0]=velocity
    gravity_seat_red_water(t,'cap_red',{'actor':'cap_red'},'left',{'actor':'cap_red'},'water_bottle',entry_phase='rim_release')
    before=json.loads((tmp_path/'e19-c-gravity-seating.private.jsonl').read_text().splitlines()[0])
    assert before['finger_qd_m_s']==velocity and before['finger_velocity_observation_only']
    assert t.releases==1 and t.calls==[]


def test_fast_finger_observation_cannot_replace_actual_final_covering(tmp_path):
    from videoicl_isaaclab.execution_design_e19_reference import gravity_seat_red_water
    t=GravityTool(tmp_path,'wrong_pose');t.state['cap_red']['pos']=t.mouth()+[0,0,.010];t.finger_qd[0]=[-.0526,.0693]
    with pytest.raises(ToolExecutionError,match='covering/support'):
        gravity_seat_red_water(t,'cap_red',{'actor':'cap_red'},'left',{'actor':'cap_red'},'water_bottle',entry_phase='rim_release')
    assert t.releases==1 and t.calls==[]


@pytest.mark.parametrize('fault',['nonfinite','missing','wrong_joint_identity'])
def test_release_rejects_missing_or_invalid_native_finger_speed(tmp_path,fault):
    from videoicl_isaaclab.execution_design_e19_reference import gravity_seat_red_water
    t=GravityTool(tmp_path);t.state['cap_red']['pos']=t.mouth()+[0,0,.010]
    if fault=='nonfinite':t.finger_qd[0,0]=float('nan')
    elif fault=='missing':del t.a.scene.robots['left'].data.joint_vel
    else:t.a.scene.robots['left'].find_joints=lambda p:([0,1],['finger1','finger2'])
    with pytest.raises((ValueError,AttributeError)):
        gravity_seat_red_water(t,'cap_red',{'actor':'cap_red'},'left',{'actor':'cap_red'},'water_bottle',entry_phase='rim_release')
    assert t.releases==0 and not t.calls
