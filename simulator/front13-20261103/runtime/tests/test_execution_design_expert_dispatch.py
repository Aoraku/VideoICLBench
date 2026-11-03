"""CPU tests of explicit reference routing, with no Isaac or model API calls."""
import ast
from pathlib import Path
from types import SimpleNamespace
import pytest
import numpy as np
from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def test_e39_reference_uses_sealed_measured_rule():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E39'
    a.d={'local_order':{'expected_order':['stale'],'expected_yaws':{'stale':99}}}
    actual=dict(actor='work_tray',pieces=['blue','red'],expected_order=['blue','red'],expected_yaws={'blue':.3,'red':-.8},match_order=False)
    a.c=SimpleNamespace(evaluator=SimpleNamespace(initial_sealed=True,initial_order_rule=actual))
    placed=[];staged=[];a.place=lambda *args:placed.append(args)
    a.frame=lambda ref:(np.zeros(3),np.eye(3))
    a.snapshot=lambda:({'blue':dict(pos=np.array([.01,.12,.02]),mat=np.eye(3)),'red':dict(pos=np.array([-.01,-.07,.02]),mat=np.eye(3))},set())
    a.bottom_local=lambda n:np.array([0,0,-.02])
    a.stage_on_table=lambda n:staged.append(n)
    a.local_stage()
    assert [x[0] for x in placed]==['blue','red']
    assert [x[3] for x in placed]==[.3,-.8]
    assert staged==['blue','red']
    np.testing.assert_allclose(placed[0][2],[.01,.12,0])
    np.testing.assert_allclose(placed[1][2],[-.01,-.07,0])
    a.c.evaluator.initial_sealed=False
    with pytest.raises(ToolExecutionError,match='sealed'):a.local_stage()
    assert len(placed)==2


def route_method(name):
    # Isolate the actual thin dispatch method from Isaac-only module imports.
    path=Path(__file__).parents[1]/'videoicl_isaaclab/demonstration.py'
    tree=ast.parse(path.read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Demonstration')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
    scope={'__name__':'videoicl_isaaclab.demonstration','__package__':'videoicl_isaaclab'};exec(compile(ast.Module(body=[method],type_ignores=[]),str(path),'exec'),scope)
    return scope[name]


@pytest.mark.parametrize('entry',['solve','solve_generated'])
def test_revision_dispatch_precedes_legacy_checks(entry):
    called=[]
    a=SimpleNamespace(scene=SimpleNamespace(spec={'id':'E01','goals':[],'execution_design':{'schema':'execution-design-v2'}}),solve_execution_design=lambda:called.append('full') or {'strict_success':True})
    assert route_method(entry)(a)=={'strict_success':True}
    assert called==['full']
    a.scene.spec.pop('execution_design')
    with pytest.raises(ValueError):route_method(entry)(a)
    assert called==['full']


def test_model_demo_export_rejects_full_workflow_before_instantiation():
    path=Path(__file__).parents[1]/'videoicl_isaaclab/demonstration.py';tree=ast.parse(path.read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='record_generated_demo')
    scope={};exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),scope)
    controller=SimpleNamespace(scene=SimpleNamespace(spec={'execution_design':{'schema':'execution-design-v2'}}))
    with pytest.raises(ValueError,match='cannot be exported'):scope['record_generated_demo'](controller,'unused')


@pytest.mark.parametrize('task,name,actor,lift',[('E09','red_circle','group_box0',.086),('E01','food','tray',0),('E09','group_box0','shipping_crate',0)])
def test_thin_sorting_payload_gravity_placement_is_scoped_and_keeps_support_check(task,name,actor,lift,monkeypatch):
    from videoicl_isaaclab import execution_design_e09_clearance
    monkeypatch.setattr(execution_design_e09_clearance,'measured_package_clearance',lambda *args:1.03)
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task=task;a.spec={'execution_design':{}}
    a.clearance=1.15;a.measured_transport_clearance=lambda *args:1.02
    a.d={'target_members':['red_circle'],'local_regions':[{'actor':'group_box0'}]}
    stages=[];calls=[];a.stage=stages.append;a.pickup=lambda n:({'actor':n},'right')
    a.frame=lambda r:(np.array([.1,.2,.8]),np.eye(3));a.bottom_local=lambda n:[0,0,-.004]
    transit_heights=[]
    a.lower_place=lambda *args,**kwargs:(calls.append((args,kwargs)),transit_heights.append(a.clearance))
    a.objects={actor:{'size':[.06,.05,.022]}}
    a.point=lambda r:np.array([0.,0.,.836]);a.tip=lambda side:np.array([0.,0.,.840])
    a.a=SimpleNamespace(floor_clear_tcp=lambda side,floor:.9)
    a.snapshot=lambda:({actor:{'pos':np.array([.1,.2,.8]),'grasp':[False,False]}},set())
    a.place(name,actor,[0,0,.01])
    np.testing.assert_allclose(calls[0][0][4],[.1,.2,.81+lift])
    assert calls[0][1]=={'support':actor}
    assert stages[-1]=='workflow-place-'+name+'-on-'+actor
    assert a.clearance==1.15
    assert transit_heights==[1.02 if task=='E09' and name=='red_circle' else 1.03 if task=='E09' else 1.15]


def test_sorting_drop_rejects_tipped_box_before_placement():
    a=ExecutionDesignAuthor.__new__(ExecutionDesignAuthor);a.task='E09'
    a.d={'target_members':['ring'],'local_regions':[{'actor':'box'}]}
    a.stage=lambda s:None;a.pickup=lambda n:({'actor':n},'right')
    a.frame=lambda r:(np.zeros(3),np.array([[1,0,0],[0,0,-1],[0,1,0]]))
    a.lower_place=lambda *args,**kwargs:pytest.fail('No placement into tipped box')
    with pytest.raises(ToolExecutionError,match='upright'):a.place('ring','box',[0,0,0])


def test_nonworkflow_contract_cannot_enter_model_demo_via_generic_route():
    a=SimpleNamespace(scene=SimpleNamespace(spec={'id':'E06','goals':[{'type':'place'}],'execution_design':{'schema':'execution-design-v2'}}))
    with pytest.raises(ValueError,match='explicit engineering'):route_method('solve_generated')(a)


@pytest.mark.parametrize('root',['/World','/World/Rooms/room_07'])
def test_finger_collision_clearance_uses_actual_room_root(root,monkeypatch):
    import sys
    looked_up=[]
    def lookup(path):looked_up.append(path);raise LookupError('stop before mesh computation')
    stage=SimpleNamespace(GetPrimAtPath=lookup)
    usd=SimpleNamespace(get_context=lambda:SimpleNamespace(get_stage=lambda:stage))
    monkeypatch.setitem(sys.modules,'omni',SimpleNamespace(usd=usd))
    monkeypatch.setitem(sys.modules,'omni.usd',usd)
    monkeypatch.setitem(sys.modules,'pxr',SimpleNamespace(Usd=SimpleNamespace(),UsdGeom=SimpleNamespace(XformCache=lambda:object()),UsdPhysics=SimpleNamespace()))
    a=SimpleNamespace(scene=SimpleNamespace(root_path=root,robots={'right':object()},embodiment=SimpleNamespace(fingers=['fingerA','fingerB'])))
    a.finger_geometry=lambda side:route_method('finger_geometry')(a,side)
    with pytest.raises(LookupError):route_method('floor_clear_tcp')(a,'right')
    assert looked_up==[root+'/right_robot/fingerA']
