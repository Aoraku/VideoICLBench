import math
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e28_reference import level_handle
from videoicl_isaaclab.execution_design_e35_retreat import lift_above_stack
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def rot(axis,deg):
 a=math.radians(deg);c,s=math.cos(a),math.sin(a)
 return (np.array([[1,0,0],[0,c,-s],[0,s,c]]),np.array([[c,0,s],[0,1,0],[-s,0,c]]),np.array([[c,-s,0],[s,c,0],[0,0,1]]))[axis]


class Tool:
 def __init__(self,stalled=False):
  self.mat=rot(0,-35)@rot(2,90);self.tcp=np.array([0.,-.3,1.02]);self.start=self.tcp.copy();self.stalled=stalled;self.calls=[]
 def snapshot(self):return {'spatula':{'mat':self.mat}},{}
 def tip(self,s):return self.tcp.copy()
 def contact(self,*args):return False
 def move(self,s,p,g):g();self.tcp=np.asarray(p).copy();self.calls.append(('move',self.tcp.copy()))
 def act(self,s,t,degrees):
  assert degrees<=4
  if not self.stalled:
   axis=0 if t.startswith('ROLL')else 1 if t.startswith('PITCH')else 2
   sign=1 if t in ('ROLL_LEFT','PITCH_UP','ROTATE_CCW')else -1
   self.mat=rot(axis,degrees*sign)@self.mat
  self.tcp[2]-=.006;self.calls.append(('rotate',t))


def test_tilt_corrected_without_unnecessary_yaw_and_drift_accumulation():
 a=Tool();direction=level_handle(a,'spatula','right',lambda:None)
 assert direction[1]>.99 and abs(direction[0])<.02
 assert np.allclose(a.tcp,a.start)
 assert len(a.calls)<30
 assert not any(c[1]=='ROTATE_CW'for c in a.calls if c[0]=='rotate')


def test_stalled_orientation_is_bounded():
 a=Tool(stalled=True)
 with pytest.raises(ToolExecutionError,match='stalled'):level_handle(a,'spatula','right',lambda:None)
 assert len(a.calls)==22
 assert np.allclose(a.tcp,a.start)


def test_empty_retreat_uses_completed_stack_not_initial_clearance(tmp_path):
 a=SimpleNamespace(out=tmp_path,tcp=np.array([-.14,0.,.91]))
 a.scene=SimpleNamespace(spec={'objects':[{'id':'top','size':[.0273]*3}]})
 a.c=SimpleNamespace(snapshot=lambda:({'top':{'pos':np.array([-.14,0,.8855]),'mat':np.eye(3)}},{}))
 a.tip=lambda side:a.tcp.copy()
 a.finger_geometry=lambda side:{'lowest_z_task_m':float(a.tcp[2]-.04)}
 calls=[]
 def move(target,tolerance):
  p=np.array(target['left']);assert np.allclose(p[:2],a.tcp[:2]);calls.append(p);a.tcp=p
 a.move_generated=move
 z=lift_above_stack(a,'left',.91)
 assert z>=.8855+.0273+.025+.04
 assert len(calls)==1
 assert (tmp_path/'E35-retreat-clearance.private.json').exists()


def test_e35_release_uses_live_lower_cube_and_measured_payload_not_old_tcp_offset(tmp_path):
 from videoicl_isaaclab.execution_design_e35_retreat import align_actual_stack_release
 a=SimpleNamespace(out=tmp_path,tcp=np.array([-.14,.012,.92]),calls=[])
 state={'small':dict(pos=np.array([-.14,-.004,.811]),mat=np.eye(3),grasp=[False,False]),
        'large':dict(pos=np.array([-.14,.012,.861]),mat=np.eye(3),grasp=[True,False])}
 a.scene=SimpleNamespace(spec={'objects':[dict(id='small',size=[.011]*3),dict(id='large',size=[.027]*3)]})
 a.c=SimpleNamespace(snapshot=lambda:(state,{}));a.tip=lambda side:a.tcp.copy()
 def move(target,tolerance):
  dest=np.asarray(target['left']);delta=dest-a.tcp
  # True payload follows only 80% of requested displacement: stale offset
  # correction would leave a persistent centering error.
  state['large']['pos']+=delta*.8;a.tcp=dest;a.calls.append(delta.copy())
 a.move_generated=move
 align_actual_stack_release(a,'large','left',{'required_support':'small'},{'xy':[-.14,0.],'surface_z':.822})
 assert abs(state['large']['pos'][1]-state['small']['pos'][1])<=.0015
 assert abs(state['large']['pos'][2]-.852)<=.0015
 assert len(a.calls)>1 and len(a.calls)<=16
 assert (tmp_path/'E35-actual-stack-release.private.jsonl').exists()


def test_blade_lowering_stops_on_measured_table_not_impossible_midpoint(monkeypatch,tmp_path):
 from videoicl_isaaclab.execution_design_e28_reference import lower_edge_to_table
 a=SimpleNamespace(p=np.array([0.,0.,.819]),calls=[],a=SimpleNamespace(out=tmp_path),c=SimpleNamespace(steps=1))
 monkeypatch.setattr('videoicl_isaaclab.execution_design_e28_reference.actual_leading_surfaces',lambda *args:dict(bottom_z=.8005,top_z=.803,vertex_count=100))
 a.point=lambda ref:a.p.copy()
 a.contact=lambda actor,other:a.p[2]<=.80300001
 def act(side,token,mm):
  assert token=='DOWN';a.calls.append(mm);a.p[2]=max(.803,a.p[2]-mm/1000.)
 a.act=act
 def move(side,edge,target,guard,tolerance):
  assert target[2]==a.p[2];a.p=np.asarray(target).copy()
 a.move_point=move
 z=lower_edge_to_table(a,'spatula','right',{},[0.,0.,.799],.800,lambda:None)
 assert z==pytest.approx(.803) and len(a.calls)==4


def test_wrong_handle_table_contact_cannot_stand_in_for_low_blade():
 from videoicl_isaaclab.execution_design_e28_reference import lower_edge_to_table
 a=SimpleNamespace(point=lambda ref:np.array([0.,0.,.825]),contact=lambda *args:True)
 with pytest.raises(ToolExecutionError,match='usable leading-edge height'):
  lower_edge_to_table(a,'spatula','right',{},[0.,0.,.799],.800,lambda:None)


def test_thick_front_edge_is_not_accepted_just_because_tool_touches_table(monkeypatch):
 from videoicl_isaaclab.execution_design_e28_reference import lower_edge_to_table
 a=SimpleNamespace(point=lambda ref:np.array([0.,0.,.802]),contact=lambda *args:True)
 monkeypatch.setattr('videoicl_isaaclab.execution_design_e28_reference.actual_leading_surfaces',lambda *args:dict(bottom_z=.801,top_z=.812,vertex_count=100))
 with pytest.raises(ToolExecutionError,match='collision tip surfaces'):
  lower_edge_to_table(a,'spatula','right',{},[0.,0.,.799],.800,lambda:None)


def test_e28_open_finger_target_is_outside_food_and_above_measured_table():
 from videoicl_isaaclab.execution_design_e28_backstop import finger_target
 f=dict(aabb_min_task_m=[-.01,-.02,.90],aabb_max_task_m=[.01,.02,.95])
 center,target=finger_target(np.array([0.,0.,.807]),np.array([.02,.017,.007]),np.array([0.,1.,0.]),f)
 assert target[1]-.02==pytest.approx(.019)
 assert target[2]-.025==pytest.approx(.8005)


def test_e28_relative_entry_does_not_count_food_pushed_with_blade(monkeypatch,tmp_path):
 from videoicl_isaaclab.execution_design_e28_backstop import insert
 monkeypatch.setattr('videoicl_isaaclab.execution_design_e28_backstop.place',lambda *args:'left')
 a=SimpleNamespace(a=SimpleNamespace(out=tmp_path),c=SimpleNamespace(steps=0),p=np.array([0.,-.025,.802]),food=np.array([0.,0.,.807]))
 a.spec={'objects':[{'id':'food','size':[.02,.017,.007]}]}
 a.s={'tools':{'main':dict(actor='spatula',support_bounds={'lower':[.070,-.038,-.012],'upper':[.125,.038,.01]})}}
 a.contact=lambda *args:True
 a.snapshot=lambda:({'food':dict(pos=a.food.copy(),mat=np.eye(3),grasp=[False,False]),'spatula':dict(pos=a.p-np.array([0.,.133,.0]),mat=rot(2,90))},{})
 a.point=lambda edge:a.p.copy();a.stage=lambda s:None
 a.tip=lambda s:np.array([0.,0.,1.])
 def move_point(side,edge,target,guard,tolerance):
  delta=np.asarray(target)-a.p;a.p=np.asarray(target);a.food[:2]+=delta[:2];a.c.steps+=1
 a.move_point=move_point
 a.act=lambda side,token,mm:move_point(side,{},a.p+np.array([0,mm/1000,0]),lambda:None,.001)
 a.move=lambda *args:pytest.fail('A pushed food cannot trigger hand withdrawal or lift')
 with pytest.raises(ToolExecutionError,match='no progress relative to food'):
  insert(a,'food',{},'right',np.array([0.,1.,0.]),.802,lambda:None)
 assert a.c.steps<20
 assert (tmp_path/'E28-relative-insertion.private.jsonl').exists()


def test_e28_backstop_withdraws_before_hand_free_blade_lift(monkeypatch,tmp_path):
 monkeypatch.setattr('videoicl_isaaclab.execution_design_e28_backstop.withdraw',lambda a,food,side,direction,guard:a.withdraw.append((side,a.p[1])))
 from videoicl_isaaclab.execution_design_e28_backstop import insert
 monkeypatch.setattr('videoicl_isaaclab.execution_design_e28_backstop.place',lambda *args:'left')
 a=SimpleNamespace(a=SimpleNamespace(out=tmp_path),c=SimpleNamespace(steps=0),p=np.array([0.,-.025,.802]),withdraw=[])
 a.spec={'objects':[{'id':'food','size':[.02,.017,.007]}]}
 a.s={'tools':{'main':dict(actor='spatula',support_bounds={'lower':[.070,-.038,-.012],'upper':[.125,.038,.01]})}}
 a.contact=lambda *args:True
 a.snapshot=lambda:({'food':dict(pos=np.array([0.,0.,.807]),mat=np.eye(3),grasp=[False,False]),'spatula':dict(pos=a.p-np.array([0.,.133,.0]),mat=rot(2,90))},{})
 a.point=lambda edge:a.p.copy();a.stage=lambda s:None;a.tip=lambda s:np.array([0.,0.,1.])
 def move_point(side,edge,target,guard,tolerance):
  assert np.asarray(target)[1]-a.p[1]==pytest.approx(.003)
  assert tolerance==.001
  a.p=np.asarray(target);a.c.steps+=1
 a.move_point=move_point
 a.act=lambda side,token,mm:move_point(side,{},a.p+np.array([0,mm/1000,0]),lambda:None,.001)
 a.move=lambda side,target,guard:a.withdraw.append((side,a.p[1],np.asarray(target)[2]))
 insert(a,'food',{},'right',np.array([0.,1.,0.]),.802,lambda:None)
 assert len(a.withdraw)==1 and .013<=a.withdraw[0][1]<=.016
 assert .013<=a.p[1]<=.016


def test_e28_backstop_retreat_clears_load_column_before_rising(tmp_path):
 from videoicl_isaaclab.execution_design_e28_backstop import withdraw
 a=SimpleNamespace(a=SimpleNamespace(out=tmp_path),c=SimpleNamespace(steps=0),tcp=np.array([0.,.03,.81]),calls=[])
 a.spec={'objects':[dict(id='food',size=[.02,.017,.007])]}
 a._e28_backstop_park=np.array([-.19,.30,.90])
 a.stage=lambda name:None;a.tip=lambda side:a.tcp.copy()
 a.snapshot=lambda:({'food':dict(pos=np.array([0.,0.,.807]),mat=np.eye(3))},set())
 a.a.finger_geometry=lambda side:{'fingers':[dict(aabb_min_task_m=(a.tcp-[.01,.01,.01]).tolist(),aabb_max_task_m=(a.tcp+[.01,.01,.01]).tolist())]}
 def move(side,target,guard,**kwargs):
  guard();a.calls.append(np.asarray(target)-a.tcp);a.tcp=np.asarray(target).copy()
 a.move=move
 withdraw(a,'food','left',np.array([0,1,0]),lambda:None)
 assert np.allclose(a.calls[0],[0,.003,0])
 assert np.allclose(a.calls[1],[-.1,0,0])
 assert a.calls[2][2]>.1 and np.allclose(a.calls[2][:2],[0,0])
 assert np.allclose(a.tcp[:2],[-.19,.30])
 assert (tmp_path/'E28-backstop-retreat.private.jsonl').exists()


def test_e28_retreat_does_not_raise_hand_when_real_fingers_failed_to_move(tmp_path):
 from videoicl_isaaclab.execution_design_e28_backstop import withdraw
 a=SimpleNamespace(a=SimpleNamespace(out=tmp_path),c=SimpleNamespace(steps=0),tcp=np.array([0.,.03,.81]),calls=[])
 a.spec={'objects':[dict(id='food',size=[.02,.017,.007])]}
 a._e28_backstop_park=np.array([-.19,.30,.90]);a.stage=lambda name:None;a.tip=lambda side:a.tcp.copy()
 a.snapshot=lambda:({'food':dict(pos=np.array([0.,0.,.807]),mat=np.eye(3))},set())
 a.a.finger_geometry=lambda side:{'fingers':[dict(aabb_min_task_m=[-.01,.02,.80],aabb_max_task_m=[.01,.04,.85])]}
 a.move=lambda side,target,guard,**kwargs:a.calls.append(np.asarray(target).copy())
 with pytest.raises(ToolExecutionError,match='release actual side contact'):
  withdraw(a,'food','left',np.array([0,1,0]),lambda:None)
 assert len(a.calls)==10 and all(q[2]==pytest.approx(.81)for q in a.calls)


def test_e28_loaded_side_contact_releases_normally_before_tangential_retreat(tmp_path):
 from videoicl_isaaclab.execution_design_e28_backstop import withdraw
 a=SimpleNamespace(a=SimpleNamespace(out=tmp_path),c=SimpleNamespace(steps=0),tcp=np.array([0.,.03,.81]),calls=[])
 a.spec={'objects':[dict(id='food',size=[.02,.017,.007])]}
 a._e28_backstop_park=np.array([-.19,.3,.9]);a.stage=lambda name:None;a.tip=lambda side:a.tcp.copy()
 def snapshot():
  contacts={frozenset(('food','left_finger2'))}if a.tcp[1]<.038 else set()
  return {'food':dict(pos=np.array([0.,0.,.807]),mat=np.eye(3))},contacts
 a.snapshot=snapshot
 a.a.finger_geometry=lambda side:{'fingers':[dict(aabb_min_task_m=(a.tcp-[.01,.01,.01]).tolist(),aabb_max_task_m=(a.tcp+[.01,.01,.01]).tolist())]}
 def move(side,target,guard,**kwargs):
  guard();delta=np.asarray(target)-a.tcp
  if snapshot()[1]:assert delta[1]>0 and abs(delta[0])<1e-12 and abs(delta[2])<1e-12
  a.calls.append(delta);a.tcp=np.asarray(target).copy()
 a.move=move
 withdraw(a,'food','left',np.array([0.,1.,0.]),lambda:None)
 assert len(a.calls)>=6 and all(np.allclose(d,[0.,.003,0.])for d in a.calls[:3])


@pytest.mark.parametrize('deadband',[0.,3.5,5.75])
def test_e28_open_finger_jaw_aligns_across_insertion_not_toward_plate(deadband):
 from videoicl_isaaclab.execution_design_e28_backstop import align_open_fingers
 a=SimpleNamespace(yaw=0.,tcp=np.array([-.19,.3,1.08]),calls=[])
 a.tip=lambda side:a.tcp.copy();a.move=lambda side,target,guard:None
 def geometry(side):
  delta=rot(2,a.yaw)@np.array([0.,.05,0.])
  return dict(fingers=[dict(aabb_center_task_m=(a.tcp-delta).tolist()),dict(aabb_center_task_m=(a.tcp+delta).tolist())],lowest_z_task_m=1.04)
 a.a=SimpleNamespace(finger_geometry=geometry)
 def act(side,token,degrees):
  a.yaw+=(1 if token=='ROTATE_CCW'else -1)*max(0.,degrees-deadband);a.calls.append(token)
 a.act=act
 align_open_fingers(a,'left',np.array([0.,1.,0.]),lambda:None)
 centers=geometry('left')['fingers']
 assert abs(centers[0]['aabb_center_task_m'][1]-centers[1]['aabb_center_task_m'][1])<.007
 assert len(a.calls)<=50


def test_e28_other_open_finger_plate_collision_rejected_before_lowering():
 from videoicl_isaaclab.execution_design_e28_backstop import require_finger_clearance
 a=SimpleNamespace(spec={'objects':[dict(id='food',size=[.02]*3),dict(id='plate',size=[.1,.1,.014])]},s={'tools':{'main':{'actor':'spatula'}}})
 a.snapshot=lambda:({'plate':dict(pos=np.array([0.,.15,.814]),mat=np.eye(3))},set())
 a.a=SimpleNamespace(finger_geometry=lambda side:{'fingers':[dict(aabb_min_task_m=[-.07,.04,1.],aabb_max_task_m=[-.04,.07,1.05])]})
 with pytest.raises(ToolExecutionError,match='plate'):
  require_finger_clearance(a,'food','left',np.array([0.,0.,-.20]))


@pytest.mark.parametrize('active,expected',[('rectangle','positive'),('round','negative')])
def test_backstop_selects_finger_by_real_neighbour_clearance(active,expected):
 from videoicl_isaaclab.execution_design_e28_backstop import choose_backstop_finger
 fingers=[]
 for name,x in [('negative',-.055),('positive',.055)]:
  center=np.array([x,0.,1.08]);fingers.append(dict(name=name,aabb_center_task_m=center.tolist(),aabb_min_task_m=(center-[.01,.01,.03]).tolist(),aabb_max_task_m=(center+[.01,.01,.03]).tolist()))
 state={'rectangle':dict(pos=np.array([-.055,0,.807]),mat=np.eye(3)),'round':dict(pos=np.array([.055,0,.807]),mat=np.eye(3))}
 a=SimpleNamespace(spec={'objects':[dict(id=n,size=[.0235,.017,.007])for n in state]},s={'tools':{'main':{'actor':'spatula'}}})
 a.snapshot=lambda:(state,set());a.a=SimpleNamespace(finger_geometry=lambda side:{'fingers':fingers})
 selected=choose_backstop_finger(a,active,'left',np.array([0.,1.,0.]),state[active]['pos'],np.array([.0235,.017,.007]),fingers)
 assert selected==expected


def test_e28_real_v15_shallow_tip_overlap_is_not_a_load_ready_blade():
 from videoicl_isaaclab.execution_design_e28_backstop import center_over_blade
 tool={'support_bounds':{'lower':[.070018,-.037615,-.012298],'upper':[.124997,.037615,.009448]}}
 state={'pos':np.zeros(3),'mat':np.eye(3)}
 assert not center_over_blade(tool,state,np.array([.1319,.003,-.003]))[0]
 assert center_over_blade(tool,state,np.array([.119,.003,-.003]))[0]
 assert not center_over_blade(tool,state,np.array([.119,.038,-.003]))[0]


def test_e28_already_detached_high_fingers_clear_sideways_without_unneeded_normal_pushes(tmp_path):
 from videoicl_isaaclab.execution_design_e28_backstop import withdraw
 a=SimpleNamespace(a=SimpleNamespace(out=tmp_path),c=SimpleNamespace(steps=0),tcp=np.array([0.,0.,.89]),calls=[])
 a.spec={'objects':[dict(id='food',size=[.02,.017,.007])]};a._e28_short_backstop_retreat=True
 a.stage=lambda name:None;a.tip=lambda side:a.tcp.copy()
 a.snapshot=lambda:({'food':dict(pos=np.array([0.,0.,.820]),mat=np.eye(3))},set())
 a.a.finger_geometry=lambda side:{'fingers':[dict(aabb_min_task_m=(a.tcp-[.01,.01,.01]).tolist(),aabb_max_task_m=(a.tcp+[.01,.01,.01]).tolist())]}
 def move(side,target,guard,**kwargs):
  guard();a.calls.append(np.asarray(target)-a.tcp);a.tcp=np.asarray(target).copy()
 a.move=move
 withdraw(a,'food','left',np.array([0.,1.,0.]),lambda:None)
 assert np.allclose(a.calls[0],[-.1,0.,0.])
 assert np.allclose(a.calls[1],[0.,0.,.04])


def test_e28_food_movement_after_real_hand_separation_uses_load_guard_not_drag_label(tmp_path):
 from videoicl_isaaclab.execution_design_e28_backstop import withdraw
 a=SimpleNamespace(a=SimpleNamespace(out=tmp_path),c=SimpleNamespace(steps=0),tcp=np.array([0.,0.,.89]),food=np.array([0.,0.,.820]),calls=[])
 a.spec={'objects':[dict(id='food',size=[.02,.017,.007])]};a._e28_short_backstop_retreat=True
 a.stage=lambda name:None;a.tip=lambda side:a.tcp.copy()
 a.snapshot=lambda:({'food':dict(pos=a.food.copy(),mat=np.eye(3))},set())
 a.a.finger_geometry=lambda side:{'fingers':[dict(aabb_min_task_m=(a.tcp-[.01,.01,.01]).tolist(),aabb_max_task_m=(a.tcp+[.01,.01,.01]).tolist())]}
 def move(side,target,guard,**kwargs):
  guard();a.calls.append(np.asarray(target)-a.tcp);a.tcp=np.asarray(target).copy()
  if len(a.calls)==1:a.food[0]+=.006
  guard()
 a.move=move
 guard_calls=[]
 withdraw(a,'food','left',np.array([0.,1.,0.]),lambda:guard_calls.append(True))
 assert len(a.calls)==2 and len(guard_calls)>=4
