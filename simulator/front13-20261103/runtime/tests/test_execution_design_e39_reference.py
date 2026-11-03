import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e39_reference import move_payload_point
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError

class MeasuredAuthor:
    max_mm=12
    def __init__(self, drift=0., blocked=False):
        self.position=np.zeros(3); self.actions=[]; self.drift=drift; self.blocked=blocked
    def point(self,ref):return self.position.copy()
    def act(self,side,token,mm,follower=None):
        self.actions.append((side,token,mm,follower))
        if self.blocked:return
        axis,sign={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}[token]
        self.position[axis]+=sign*mm/1000
        if axis!=2:self.position[2]-=self.drift

def test_loaded_lateral_drift_replans_actual_payload_not_fixed_tcp():
    author=MeasuredAuthor(drift=.0018)
    move_payload_point(author,'left',{},[.11,.04,.08])
    assert np.max(abs(author.position-[.11,.04,.08]))<=.002
    assert any(a[1]=='UP' for a in author.actions)
    assert all(a[2]<=12 for a in author.actions)

def test_true_grasp_checked_even_at_arrived_position():
    author=MeasuredAuthor()
    def lost():raise ToolExecutionError('actual grasp lost')
    with pytest.raises(ToolExecutionError,match='actual grasp lost'):
        move_payload_point(author,'left',{},[0,0,0],guard=lost)
    assert not author.actions

def test_fixed_residual_stops_without_exhausting_budget():
    author=MeasuredAuthor(blocked=True)
    with pytest.raises(ToolExecutionError,match='stalled'):
        move_payload_point(author,'left',{},[.1,0,0])
    assert len(author.actions)==24

def test_final_two_mm_is_not_relaxed():
    author=MeasuredAuthor()
    move_payload_point(author,'left',{},[.0021,0,0])
    assert len(author.actions)==1 and abs(author.position[0]-.0021)<1e-9

@pytest.mark.parametrize('target',[[float('nan'),0,0],[1,2],[0,float('inf'),1]])
def test_invalid_target_rejected(target):
    with pytest.raises(ToolExecutionError):move_payload_point(MeasuredAuthor(),'left',{},target)

from videoicl_isaaclab.execution_design_e39_reference import swept_height

def test_measured_open_lid_requires_y_detour_before_lateral_translation():
    # v2 native lid y upper -.144 m and 1.264 m upper; box rim .872 m.
    lid=([.153,-.218,.874],[.307,-.144,1.264])
    box=([.153,-.147,.800],[.307,.247,.872])
    lo=[-.065,-.185,0];hi=[.065,.185,.060]
    straight=swept_height([-.12,0,.9],[.23,0,.9],lo,hi,[lid,box])
    yfirst=swept_height([-.12,0,.9],[-.12,.05,.9],lo,hi,[lid,box])
    xnext=swept_height([-.12,.05,.9],[.23,.05,.9],lo,hi,[lid,box])
    assert straight==pytest.approx(1.269)
    assert yfirst==pytest.approx(.805)
    assert xnext==pytest.approx(.877)

def test_finger_below_payload_increases_actual_required_height():
    height=swept_height([0,0,1],[.2,0,1],[-.05,-.05,-.02],[.05,.05,.05],[([.1,-.1,.8],[.3,.1,.9])])
    assert height==pytest.approx(.925)

def test_bad_actual_obstacle_cannot_be_ignored():
    with pytest.raises(ToolExecutionError):
        swept_height([0,0,0],[1,0,0],[-.1]*3,[.1]*3,[([float('nan'),0,0],[1,1,1])])


def test_transport_plane_extra_margin_pays_for_intermediate_error():
    lo=[-.065,-.185,0];hi=[.065,.185,.06]
    lid=([.153,-.218,.874],[.307,-.144,1.264]);box=([.153,-.147,.8],[.307,.247,.872])
    h=swept_height([-.12,.05,.9],[.23,.05,.9],lo,hi,[lid,box],margin=.008)
    assert h==pytest.approx(.880)
    assert h-.003-.872>=.005-1e-12

def test_xy_uncertainty_is_included_in_same_eight_mm_sweep_margin():
    # Nominal moving edge at y=.185: obstacle only 6mm beyond it must be
    # included, even though it would miss an uninflated or 5mm-only sweep.
    obstacle=([.1,.191,.8],[.3,.25,1.2])
    h=swept_height([0,0,1],[.2,0,1],[-.065,-.185,0],[.065,.185,.06],[obstacle],margin=.008)
    assert h==pytest.approx(1.208)


from videoicl_isaaclab.execution_design_e39_reference import move_clearance_plane

def test_transport_corrects_loaded_sag_before_next_horizontal_step():
    a=MeasuredAuthor(drift=.0018)
    a.position[2]=.9
    snapshots=[]
    def guard():snapshots.append(a.position.copy())
    move_clearance_plane(a,'left',{},[.1,.05,.9],guard)
    assert np.max(np.abs(a.position-[.1,.05,.9]))<=.003
    for before,action in zip(snapshots,a.actions):
        if action[1] in ('FWD','BACK','LEFT','RIGHT'):
            assert abs(before[2]-.9)<=.003
            assert action[2]<=10
    assert min(p[2] for p in snapshots)>=.9-.003-.0018-1e-12


def test_loaded_up_tracking_offset_does_not_create_zero_progress_loop():
    class Loaded(MeasuredAuthor):
        def act(self,side,token,mm,follower=None):
            self.actions.append((side,token,mm,follower))
            if token=='UP':self.position[2]+=(mm-4.2)/1000;self.position[0]-=.001
            elif token=='DOWN':self.position[2]-=mm/1000
            else:
                axis,sign={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1)}[token]
                self.position[axis]+=sign*mm/1000;self.position[2]-=.0018
    a=Loaded();a.position[2]=.9
    move_clearance_plane(a,'left',{},[.1,.05,.9],lambda:None)
    assert np.max(np.abs(a.position-[.1,.05,.9]))<=.003
    assert len(a.actions)<150
    assert all(6<=r[2]<=10 for r in a.actions if r[1]=='UP')


def test_plane_corrects_cross_track_drift_before_further_main_axis_move():
    class Drift(MeasuredAuthor):
        def act(self,side,token,mm,follower=None):
            super().act(side,token,mm,follower)
            if token=='FWD':self.position[1]+=.0018
    a=Drift();a.position[2]=.9;samples=[]
    move_clearance_plane(a,'left',{},[.1,0,.9],lambda:samples.append(a.position.copy()))
    assert np.max(np.abs(a.position-[.1,0,.9]))<=.003
    for pose,action in zip(samples,a.actions):
        if action[1]=='FWD':assert abs(pose[1])<=.003


def test_sideways_drift_cannot_hide_failed_up_corrections():
    class StalledLift(MeasuredAuthor):
        def act(self,side,token,mm,follower=None):
            self.actions.append((side,token,mm,follower))
            self.position[1]+=.001 # apparent motion, no closer to target
    a=StalledLift()
    with pytest.raises(ToolExecutionError,match='no net progress'):
        move_clearance_plane(a,'left',{},[.1,0,.1],lambda:None)
    assert len(a.actions)==48


def test_measured_up_bias_adapts_without_exceeding_public_action_bound():
    class Loaded(MeasuredAuthor):
        max_mm=10
        def act(self,side,token,mm,follower=None):
            self.actions.append((side,token,mm,follower))
            if token=='UP':self.position[2]+=(mm-6.8)/1000;self.position[0]-=.0012
            elif token=='DOWN':self.position[2]-=mm/1000
            else:
                axis,sign={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1)}[token]
                self.position[axis]+=sign*mm/1000;self.position[2]-=.0018
    a=Loaded();a.position[2]=.9
    move_clearance_plane(a,'left',{},[.1,.05,.9],lambda:None)
    assert np.max(np.abs(a.position-[.1,.05,.9]))<=.003
    assert len(a.actions)<150
    assert max(r[2]for r in a.actions)<=10
    assert any(r[2]>9 for r in a.actions if r[1]=='UP')


def test_native_measured_coupled_axis_losses_still_allow_transport():
    class NativeLike(MeasuredAuthor):
        max_mm=10
        def act(self,side,token,mm,follower=None):
            self.actions.append((side,token,mm,follower))
            if token=='FWD':delta=[(mm-2.8)/1000,.00047,-.0029]
            elif token=='UP':delta=[-.00104,.000494,(mm-6.2)/1000]
            elif token=='RIGHT':delta=[-.0009,-(mm-2.)/1000,-.0018]
            elif token=='LEFT':delta=[-.0009,(mm-2.)/1000,-.0018]
            elif token=='BACK':delta=[-mm/1000,0,-.001]
            else:delta=[0,0,-mm/1000]
            self.position+=delta
    a=NativeLike();a.position[2]=.9
    move_clearance_plane(a,'left',{},[.15,0,.9],lambda:None)
    assert np.max(np.abs(a.position-[.15,0,.9]))<=.003
    assert len(a.actions)<200
    assert all(x[2]<=10 for x in a.actions)


def test_native_y_residue_requires_offset_detour_before_horizontal_sweep():
    # Native v12 X-segment boundary: Y is 1.595mm below the nominal target.
    # Keep the full 8mm margin, including the 3mm tracking budget.
    rotation=np.array([[.99996125698,-.00499963760,-.0072520934],
                       [.00499558449,.99998736382,-.00057637336],
                       [.00725488365,.00054012256,.99997353554]])
    center=np.array([-.12220887,.04840545,.85110754])
    origin=center+rotation@np.array([0.,0.,-.018])
    extent=np.abs(rotation)@np.array([.065,.185,.030])
    boundcenter=center+rotation@np.array([0.,0.,.012])
    lower=boundcenter-extent-origin;upper=boundcenter+extent-origin
    obstacles=[([.093,-.147,.8],[.247,.247,.872]),
               ([.093,-.21837,.874],[.247,-.14404,1.264])]
    direct=swept_height(origin,[.17,.05,.88],lower,upper,obstacles,margin=.008)
    detour=origin.copy();detour[1]=.060-.003
    bypass=swept_height(detour,[.17,.060,.88],lower,upper,obstacles,margin=.008)
    aligned=swept_height([.17,.057,.88],[.17,.05,.88],lower,upper,obstacles,margin=.008)
    assert direct>1.26
    assert bypass<.89 and aligned<.89


def test_native_empty_approach_axis_loss_cycle_is_compensated_without_larger_tolerance():
    from videoicl_isaaclab.execution_design_e39_reference import move_empty_waypoint
    class Empty(MeasuredAuthor):
        min_mm=.5;max_mm=10
        def tip(self,side):return self.position.copy()
        def snapshot(self):return ({'work_tray':dict(grasp=[False,False])},set())
        def act(self,side,token,mm,follower=None):
            self.actions.append((side,token,mm,follower))
            axis,sign={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}[token]
            delta=np.array([-.00095,.00060,-.00148]);delta[axis]=sign*(mm/1000-.0011)
            self.position+=delta
    a=Empty();a.position[:]=[-.176,.00304,.91587];target=[-.175,0,.918]
    guards=[]
    move_empty_waypoint(a,'left',target,lambda:guards.append(a.position.copy()))
    assert np.max(abs(a.position-target))<=.002
    assert len(a.actions)<30 and len(guards)==len(a.actions)+1
    assert all(.5<=r[2]<=10 for r in a.actions)


def test_empty_waypoint_stall_and_unexpected_payload_fail_closed():
    from videoicl_isaaclab.execution_design_e39_reference import move_empty_waypoint
    class Empty(MeasuredAuthor):
        min_mm=.5;max_mm=10
        def tip(self,side):return self.position.copy()
        def snapshot(self):return ({'work_tray':dict(grasp=[False,False])},set())
    a=Empty(blocked=True)
    with pytest.raises(ToolExecutionError,match='no measured motion'):
        move_empty_waypoint(a,'left',[.1,0,0])
    assert len(a.actions)==2
    a.snapshot=lambda:({'work_tray':dict(grasp=[True,False])},set())
    with pytest.raises(ToolExecutionError,match='unexpected payload'):
        move_empty_waypoint(a,'left',a.position)


def test_native_v15_loaded_initial_lift_closes_coupled_tracking_cycle():
    class Loaded(MeasuredAuthor):
        max_mm=10
        def act(self,side,token,mm,follower=None):
            self.actions.append((side,token,mm,follower))
            delta=np.array([-.00095,.00060,-.00148])
            axis,sign={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}[token]
            delta[axis]=sign*(mm/1000-.00110)
            self.position+=delta
    a=Loaded();a.position[:]=[-.176,.00304,.91587];goal=[-.175,0,.918]
    move_payload_point(a,'left',{},goal,lambda:None)
    assert np.max(abs(a.position-goal))<=.002
    assert len(a.actions)<30 and all(x[2]<=10 for x in a.actions)


def test_e39_actual_initial_pickup_lifts_material_point_and_preserves_reference():
    from types import SimpleNamespace
    from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
    p=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor)
    p.task='E39';p.a=SimpleNamespace(control_report={'engineering_reference_only':True})
    p.d={'target_members':['red'],'reference_objects':['reference']}
    state={n:dict(pos=np.array([x,0,.84]),mat=np.eye(3),grasp=[False,False])for n,x in [('work_tray',-.12),('red',-.12),('reference',.015)]}
    contacts={frozenset(('red','work_tray'))}
    p.snapshot=lambda:(state,contacts)
    p.hand_for=lambda name:'left';p.park_e39_idle_hand=lambda side:None
    p.ref=lambda name:dict(actor=name,local=[-.055,0,.03])
    acquired=[];p.acquire=lambda ref,side:acquired.append(side)
    p.stage=lambda stage:None;p.require_held=lambda ref,side:None
    p.point=lambda ref:np.array([-.175,0,.87])
    moved=[]
    def move_point(side,ref,target,guard):
        guard();moved.append(np.asarray(target))
    p.move_point=move_point
    p.pickup('work_tray')
    assert acquired==['left'] and np.allclose(moved[0],[-.175,0,.94])
    def corrupt_reference(side,ref,target,guard):
        state['reference']['pos'][0]+=.003;guard()
    p.move_point=corrupt_reference
    with pytest.raises(ToolExecutionError,match='disturbed the protected reference'):
        p.pickup('work_tray')


def test_v17_vertical_drop_budget_does_not_expand_xy_into_high_lid():
    lo=[-.065,-.185,0];hi=[.065,.185,.06]
    lid=([.093,-.218,.874],[.247,-.144,1.264]);box=([.093,-.147,.8],[.247,.247,.872])
    h=swept_height([-.12,.057,.9],[.17,.06,.9],lo,hi,[lid,box],margin=.008,vertical_tracking_allowance=.006)
    assert h==pytest.approx(.886)
    # Worst accepted 3mm pre-action error plus measured3.16mm lateral sag.
    assert h-.003-.003163-.872>.007
    with pytest.raises(ToolExecutionError):
        swept_height([0,0,1],[1,0,1],lo,hi,[],vertical_tracking_allowance=float('nan'))


def test_observed_v2_wrong_direction_ends_room_after_completed_action():
    class Wrong(MeasuredAuthor):
        def act(self,side,token,mm,follower=None):
            self.actions.append((side,token,mm,follower));self.position+=[.002,0,-.009]
    a=Wrong();a.position[2]=.9
    with pytest.raises(ToolExecutionError,match='moved primarily downward'):
        move_clearance_plane(a,'left',{},[.1,0,.9],lambda:None)
    assert len(a.actions)==1


def test_gravity_seating_requires_complete_projection_even_with_center_inside():
    from types import SimpleNamespace
    from videoicl_isaaclab.execution_design_e39_reference import assembly_contained_xy
    positions={'protective_box':np.zeros(3),'work_tray':np.array([0.,0.,.02]),'piece':np.array([0.,0.,.04])}
    policy=SimpleNamespace(d={'packages':[dict(container='protective_box',lower=[-.069,-.189,-.03],upper=[.069,.189,.036])],'target_members':['piece']},
        objects={'work_tray':dict(size=[.065,.185,.03],local_bounds_center=[0,0,.012]),'piece':dict(size=[.01,.02,.01])},
        frame=lambda ref:(positions[ref['actor']],np.eye(3)))
    assert assembly_contained_xy(policy,'protective_box')
    positions['work_tray'][0]=.006
    # Match the existing native 3mm geometry tolerance, rather than an
    # additional 0.1mm engineering gate. A 2mm overrun remains admitted.
    assert assembly_contained_xy(policy,'protective_box')
    positions['work_tray'][0]=.008
    assert not assembly_contained_xy(policy,'protective_box')
    positions['work_tray'][0]=0;positions['piece'][1]=.18
    assert not assembly_contained_xy(policy,'protective_box')


def test_native_release_geometry_can_end_before_an_unneeded_tracking_correction():
    a=MeasuredAuthor();checks=[]
    move_payload_point(a,'left',{},[0,0,.03],guard=lambda:checks.append(True),done=lambda:True)
    assert checks==[True]and not a.actions
