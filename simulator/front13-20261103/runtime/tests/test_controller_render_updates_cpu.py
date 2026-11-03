"""Exercise production tick ordering without importing the native simulator.

The fake renderer observes a moving wrist. A pose update after rendering would
capture the previous pose and fail. Contacts and evaluator calls are counted on
every physical tick, independently of camera sampling.
"""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT=Path(__file__).resolve().parents[1]/'videoicl_isaaclab'


def methods(filename,classname,names):
    tree=ast.parse((ROOT/filename).read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==classname)
    selected=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in names]
    assert len(selected)==len(names)
    namespace={}
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(ROOT/filename),'exec'),namespace)
    return {name:namespace[name] for name in names}


_scene_methods=methods('scene.py','TabletopScene',
    ['update_physics','prepare_render','update_render_cameras','update'])
_tick=methods('control.py','Controller',['tick'])['tick']


class Scene:
    def __init__(self,events):
        self.events=events;self.actual_wrist=0;self.camera_pose=None
        self.robots={};self.mechanisms={}
        self.objects={'body':SimpleNamespace(update=lambda dt:events.append(('body',dt)))}
        self.contacts={'body':(SimpleNamespace(update=lambda dt:events.append(('contact',dt))),[])}
        self.cameras={'wrist':SimpleNamespace(update=lambda dt:events.append(('camera',dt)))}

    def apply_passive_efforts(self):self.events.append(('effort',))
    def sync_wrist_cameras(self):
        self.camera_pose=self.actual_wrist
        self.events.append(('sync',self.camera_pose))


for _name,_method in _scene_methods.items():setattr(Scene,_name,_method)


class Controller:
    tick=_tick

    def __init__(self):
        self.events=[];self.scene=Scene(self.events);self.dt=.004
        self.physics_ticks=0;self.tick_hooks=[lambda c,r:self.events.append(('hook',r))]
        self.sim=SimpleNamespace(step=self.step,render=self.render)
        self.evaluator=SimpleNamespace(update=lambda s,c,dt:self.events.append(('evidence',dt)),
            update_mechanisms=lambda m:self.events.append(('mechanisms',)),
            update_contact_forces=lambda f:self.events.append(('forces',)))
        self.contact_forces={}

    def step(self,render):
        assert render is False
        self.scene.actual_wrist+=1;self.events.append(('physics',self.scene.actual_wrist))
    def render(self):self.events.append(('render',self.scene.camera_pose))
    def snapshot(self):self.events.append(('snapshot',));return {},set()
    def snapshot_mechanisms(self):return {}


def test_camera_samples_latest_physics_pose_only_on_render_ticks():
    c=Controller()
    for _ in range(9):c.tick(render=False)
    assert not any(e[0] in ('sync','camera','render') for e in c.events)
    c.tick(render=True)
    assert [e for e in c.events if e[0]=='render']==[('render',10)]
    assert [e for e in c.events if e[0]=='sync']==[('sync',10)]
    assert [e[1] for e in c.events if e[0]=='camera']==pytest.approx([.04])
    # All measured-body/contact/evidence work is retained at the physical rate.
    for name in ('physics','body','contact','snapshot','mechanisms','forces','evidence','hook'):
        assert sum(e[0]==name for e in c.events)==10
    assert c.physics_ticks==10
    tail=c.events[c.events.index(('physics',10)):]
    assert [e[0] for e in tail]==[
        'physics','body','contact','sync','render','camera','snapshot',
        'mechanisms','forces','evidence','hook']


def test_camera_elapsed_time_accumulates_once_and_resets_after_each_frame():
    c=Controller()
    for ticks in (7,11,3):
        for _ in range(ticks-1):c.tick(render=False)
        c.tick(render=True)
    assert [e for e in c.events if e[0]=='render']==[('render',7),('render',18),('render',21)]
    elapsed=[e[1] for e in c.events if e[0]=='camera']
    assert elapsed==pytest.approx([.028,.044,.012])
    assert sum(elapsed)==pytest.approx(c.physics_ticks*c.dt)
    assert c.scene._camera_elapsed_dt==0.


def test_legacy_full_scene_update_keeps_camera_and_physics_updates():
    events=[];scene=Scene(events);scene.actual_wrist=4
    scene.update(.004);scene.update(0.)
    assert events==[
        ('body',.004),('contact',.004),('sync',4),('camera',.004),
        ('body',0.),('contact',0.),('sync',4),('camera',0.)]


def test_older_scene_adapter_without_split_api_keeps_tick_contract():
    c=Controller()
    c.scene=SimpleNamespace(robots={},actual_wrist=0,camera_pose=None,
        apply_passive_efforts=lambda:c.events.append(('effort',)),
        update=lambda dt:c.events.append(('legacy_update',dt)))
    c.tick(render=False);c.tick(render=True)
    assert [e for e in c.events if e[0]=='legacy_update']==[
        ('legacy_update',.004),('legacy_update',.004),('legacy_update',0.)]
    assert c.physics_ticks==2
    assert sum(e[0]=='evidence' for e in c.events)==2
