from types import SimpleNamespace
from copy import deepcopy
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e20_reference import nearest_target_hand,measured_empty_approach_height


@pytest.mark.parametrize('mode',['blue','red_two_grips','red_fast','red_off_original_rail'])
def test_grip_tail_preserves_blue_and_scopes_liftoff_to_real_red_rail(mode):
    from videoicl_isaaclab.execution_design_e20_reference import finish_chip_grip
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    name='blue_supply_3'if mode=='blue'else'red_supply_1'
    a=SimpleNamespace(task='E20',spec={'execution_design':{'revision':'embodied50-execution-v3-20261102'},
        'fixtures':[dict(type='box',size=[.003,.012,.014])for _ in range(8)]},
        objects={name:{'source_asset':{'sha256':'0a52a9c5b908277e7e408155316a3fc55f889405d6ab0331f0922e8bb4047120'}}},
        d={'initial_storage':{'red_supply_1':'fixture7'}})
    qd=np.array([[.025,-.019]])if mode=='red_fast'else np.array([[-.0079,.0086]])
    robot=SimpleNamespace(data=SimpleNamespace(joint_pos=np.array([[.0112,.0108]]),joint_vel=qd))
    a.a=SimpleNamespace(control_report={'engineering_reference_only':True},scene=SimpleNamespace(robots={'right':robot}))
    a.c=SimpleNamespace(ids={'right':([], [0,1])})
    pos=np.array([-.29,-.2,.837]);tip=pos.copy();calls=[]
    a.held=lambda ref,side:True;a.require_held=lambda ref,side:None
    a.frame=lambda ref:(pos.copy(),np.eye(3));a.tip=lambda side:tip.copy()
    a.contact=lambda actor,support:support=='fixture7'and mode!='red_off_original_rail'and pos[2]<.840
    def act(side,action,**kwargs):
        calls.append(action)
        if action=='UP':pos[2]+=.002;tip[2]+=.002
    a.act=act
    if mode=='red_fast':
        with pytest.raises(ToolExecutionError,match='dynamically closing'):finish_chip_grip(a,{'actor':name},'right')
        assert calls==['GRASP','GRASP']
    else:
        finish_chip_grip(a,{'actor':name},'right')
        if mode=='red_two_grips':
            assert calls[:2]==['GRASP','GRASP']and all(c=='UP'for c in calls[2:])
            row=a.a.control_report['e20_small_liftoffs'][0]
            assert row['consecutive_measured_grips']>=3 and row['payload_delta_m'][2]>=.010
        else:assert calls==['GRASP','GRASP','GRASP']


@pytest.mark.parametrize('mode', ['good', 'slip', 'lost', 'stuck', 'support_persists'])
def test_small_liftoff_requires_real_chip_motion_grip_and_support_release(mode):
    from videoicl_isaaclab.execution_design_e20_reference import verify_grip_during_small_liftoff
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    a=SimpleNamespace(task='E20',spec={'execution_design':{'revision':'embodied50-execution-v3-20261102'},'fixtures':[{}]})
    a.a=SimpleNamespace(control_report={'engineering_reference_only':True})
    pos=np.array([-.29,-.2,.837]);tip=pos.copy();calls=[]
    a.frame=lambda ref:(pos.copy(),np.eye(3));a.tip=lambda side:tip.copy()
    def require(ref,side):
        if mode=='lost' and calls:raise ToolExecutionError('actual grip lost')
    a.require_held=require
    a.contact=lambda name,root:root=='fixture0' and (mode=='support_persists' or pos[2]<.840)
    def act(side,action,mm):
        assert side=='right' and action=='UP' and mm==2.
        calls.append(action);tip[2]+=.002
        if mode!='stuck':pos[2]+=.002
        if mode=='slip':pos[0]+=.004
    a.act=act
    if mode=='good':
        verify_grip_during_small_liftoff(a,{'actor':'chip'},'right')
        row=a.a.control_report['e20_small_liftoffs'][0]
        assert row['consecutive_measured_grips']>=3 and row['payload_delta_m'][2]>=.010
        assert row['original_supports']==['fixture0'] and row['remaining_supports']==[]
    else:
        with pytest.raises(ToolExecutionError):verify_grip_during_small_liftoff(a,{'actor':'chip'},'right')
        assert 'e20_small_liftoffs' not in a.a.control_report


def test_small_liftoff_rejects_other_task_before_reading_or_acting():
    from videoicl_isaaclab.execution_design_e20_reference import verify_grip_during_small_liftoff
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    with pytest.raises(ToolExecutionError,match='E20 v3'):
        verify_grip_during_small_liftoff(SimpleNamespace(task='E17'),{},'right')


def sample():
    robots={side:SimpleNamespace(data=SimpleNamespace(root_pos_w=np.array([[-.45,y,.8]])))for side,y in [('left',.35),('right',-.35)]}
    a=SimpleNamespace(task='E20',objects={'chip':{'size':[.016,.016,.001]},'lid':{'size':[.195,.065,.021]}},spec={'fixtures':[dict(type='box',xy=[-.1,-.2],z=.804,size=[.23,.12,.004])]})
    a.a=SimpleNamespace(control_report={'engineering_reference_only':True},scene=SimpleNamespace(robots=robots,world_to_task=lambda x:x),floor_clear_tcp=lambda side,floor:floor+.01)
    state={'chip':dict(pos=[-.2,-.12,.837],mat=np.eye(3)),'lid':dict(pos=[.02,-.4,.826],mat=np.eye(3))}
    a.snapshot=lambda:(state,set())
    return a,state


def test_actual_bases_select_destination_side_without_moving_source():
    a,state=sample();before=deepcopy(state)
    assert nearest_target_hand(a,[.07,.08,.82])=='left'
    assert nearest_target_hand(a,[.07,-.08,.82])=='right'
    for name in state:np.testing.assert_array_equal(state[name]['pos'],before[name]['pos'])


def test_empty_source_approach_uses_real_obstacle_and_finger_clearance():
    a,_=sample();assert measured_empty_approach_height(a,'left')==.98


def test_source_height_never_clamped_below_tall_actual_obstacle():
    a,state=sample();state['lid']['pos'][2]=1.2
    assert measured_empty_approach_height(a,'left')>1.27


@pytest.mark.parametrize('contact',[True,False])
def test_chip_handover_requires_released_actual_rail_before_second_pickup(contact):
    from videoicl_isaaclab.execution_design_e20_reference import pickup_via_transfer_support
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    a,state=sample();state['chip']['grasp']=[False,False];contacts=set();calls=[]
    a.spec['fixtures'].append(dict(type='box',xy=[-.18,-.02],z=.818,size=[.003,.012,.018]))
    a.d={};a._e20_freed_source_rail=dict(actor='fixture1',xy=[-.18,-.02],surface_z=.836)
    a.clearance=1.15;a.stage=lambda _:None;a.bottom_local=lambda _:[0,0,-.001]
    a.measured_transport_clearance=lambda *args:1.
    a.snapshot=lambda:(state,contacts)
    a.point=lambda ref:np.asarray(state['chip']['pos'])+[0,0,-.001]
    def pickup(name,side_override):
        calls.append(side_override);state[name]['grasp']=[side_override=='left',side_override=='right'];return {'actor':name},side_override
    a.pickup=pickup
    def lower(name,ref,side,local,target,rotation,support):
        assert side=='right';state[name]['pos']=target+[0,0,.001];state[name]['grasp']=[False,False]
        if contact:contacts.add(frozenset((name,support)))
    a.lower_place=lower
    if contact:
        _,side=pickup_via_transfer_support(a,'chip',[.07,.08,.82]);assert side=='left';assert calls==['right','left']
    else:
        with pytest.raises(ToolExecutionError,match='real support contact'):pickup_via_transfer_support(a,'chip',[.07,.08,.82])
        assert calls==['right']
    assert a.clearance==1.15


@pytest.mark.parametrize('condition',['I','E'])
def test_e20_ordering_reuses_existing_rail_without_scene_change(condition):
    from pathlib import Path
    from videoicl_isaaclab.realworld_scenes import load
    from videoicl_isaaclab.execution_design_scenes import build_execution_scene
    from videoicl_isaaclab.execution_design_e20_reference import replenishment_candidates,ordered_replenishment_regions,remember_freed_source_rail
    spec=build_execution_scene(load('E20','A',4201,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False),condition=condition,seed=4201)
    before=deepcopy(spec);a,_=sample();a.spec=spec;a.d=spec['execution_design']
    a.objects={o['id']:o for o in spec['objects']}
    state={o['id']:dict(pos=[*o['xy'],o['bottom']+o['size'][2]],mat=np.eye(3))for o in spec['objects']}
    a.snapshot=lambda:(state,set())
    region=ordered_replenishment_regions(a)[0];names=replenishment_candidates(a,region)
    assert region['required_color']=='blue'
    assert names[0]=='blue_supply_3'
    assert 'chip_transfer_support' not in a.d
    remember_freed_source_rail(a,names[0]);route=a._e20_freed_source_rail
    assert route['actor']==a.d['initial_storage'][names[0]]
    assert route['surface_z']==pytest.approx(.836)
    assert spec==before


def test_e20_transit_uses_full_measured_clearance_without_arbitrary_one_metre_floor():
    from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E20'
    a.objects={'chip':{'size':[.012,.012,.001]},'tray':{'size':[.195,.065,.022]}}
    state={'chip':{'pos':np.array([.11,.08,.998]),'mat':np.eye(3)},'tray':{'pos':np.array([0,.1,.822]),'mat':np.eye(3)}}
    a.snapshot=lambda:(state,set());a.spec={'fixtures':[]};a.bottom_local=lambda n:[0,0,-.001]
    a.point=lambda r:np.array([.11,.08,.997]);a.tip=lambda side:np.array([.11,.08,.998])
    a.a=SimpleNamespace(floor_clear_tcp=lambda side,floor:floor+.010)
    assert a.measured_transport_clearance('chip','left')==pytest.approx(.903)
    # Taller obstacles still force a higher route, never a convenient clamp.
    state['tray']['pos'][2]=1.1
    assert a.measured_transport_clearance('chip','left')==pytest.approx(1.181)
    state['tray']['pos'][2]=.822;a.task='E17'
    assert a.measured_transport_clearance('chip','left')==pytest.approx(1.0)


def test_free_chip_cell_prefers_actual_near_arm_without_moving_preserved_chip(monkeypatch):
    from copy import deepcopy
    from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
    from videoicl_isaaclab import execution_design_e20_reference
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E20'
    a.objects={n:{'size':[.016,.016,.001]} for n in ['chip','preserved']}
    state={'chip':{'pos':np.array([-.29,-.12,.837]),'mat':np.eye(3)},'preserved':{'pos':np.array([.111,.081,.815]),'mat':np.eye(3)}}
    a.snapshot=lambda:(state,set());a.frame=lambda ref:(np.array([0,.1,.826]),np.eye(3))
    monkeypatch.setattr(execution_design_e20_reference,'robot_bases',lambda _:dict(left=np.array([-.65,.3,.81]),right=np.array([-.65,-.3,.81])))
    region=dict(id='blue',actor='tray',lower=[.073,-.057,-.012],upper=[.187,.057,.05],candidates=list(state))
    before=deepcopy(state);target=a.free_chip_slot(region,'chip')
    np.testing.assert_allclose(target,[.111,.019,-.012])
    for name in state:np.testing.assert_equal(state[name]['pos'],before[name]['pos'])


@pytest.mark.parametrize('variant,expected', [('A',2),('B',3),('C',4)])
def test_all_variant_replenishments_fit_distinct_real_cells_without_selecting_preserved(variant,expected,monkeypatch):
    """Exercise each successive measured free-cell decision, not just A's first."""
    from pathlib import Path
    from videoicl_isaaclab.realworld_scenes import load
    from videoicl_isaaclab.execution_design_scenes import build_execution_scene
    from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
    from videoicl_isaaclab import execution_design_e20_reference as helper
    root=Path(__file__).parents[1]
    spec=build_execution_scene(load('E20',variant,4201,root/'configs/realworld_full50_bindings.json',verify_files=False),seed=4201)
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E20';a.spec=spec;a.d=spec['execution_design']
    a.objects={o['id']:o for o in spec['objects']}
    state={o['id']:dict(pos=np.array([*o['xy'],o.get('center_z',o['bottom']+o['size'][2])]),mat=np.eye(3))for o in spec['objects']}
    a.snapshot=lambda:(state,set());a.frame=lambda ref:(state[ref['actor']]['pos'],state[ref['actor']]['mat'])
    monkeypatch.setattr(helper,'robot_bases',lambda _:dict(left=np.array([-.65,.3,.81]),right=np.array([-.65,-.3,.81])))
    preserved={n:state[n]['pos'].copy() for ids in a.d['initial_preserved'].values()for n in ids}
    totals=[]
    for r in helper.ordered_replenishment_regions(a):
        assert r['count']==expected
        keep=a.d['initial_preserved'][r['id']];candidates=helper.replenishment_candidates(a,r)
        assert set(candidates).isdisjoint(keep)
        count=expected-len(keep);assert len(candidates)>=count
        occupied=[state[n]['pos'].copy()for n in keep]
        for name in candidates[:count]:
            target=np.asarray(a.free_chip_slot(r,name));half=np.array(a.objects[name]['size'])
            assert np.all(target[:2]-half[:2]>=np.array(r['lower'])[:2])
            assert np.all(target[:2]+half[:2]<=np.array(r['upper'])[:2])
            world=state[r['actor']]['pos']+target+[0,0,half[2]]
            assert all(np.linalg.norm(world[:2]-p[:2])>.032 for p in occupied)
            # Software fixture feeds the next call a hypothetical measured
            # settled pose. It is not native placement or scoring evidence.
            state[name]['pos']=world;occupied.append(world)
        assert len(occupied)==expected;totals.append(count)
    assert sum(totals)==3*expected-len(preserved)
    for name,pos in preserved.items():np.testing.assert_array_equal(state[name]['pos'],pos)
