from copy import deepcopy
from dataclasses import dataclass
from types import SimpleNamespace
from pathlib import Path
import ast,json,os,shutil,time
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3,source_sha256
from videoicl_isaaclab.execution_design_render_cadence import configure,FLAG,_hash
from videoicl_isaaclab.room_pool import RoomPool
from test_room_pool_actions import active_pool,config

@dataclass(frozen=True)
class Profile:
    config:dict
    path:Path
    config_hash:str
    tcp:tuple=(0.,0.,.1)


def scenes():
    cfg=config();cfg['cameras']=dict(head=dict(width=640,height=480),wrist=dict(width=640,height=480))
    profile=Profile(cfg,Path('original.json'),'original-file-sha')
    return {str(i):SimpleNamespace(spec=dict(id=task,execution_design=dict(revision=REVISION_V3,source_sha256=source_sha256(REVISION_V3))),embodiment=profile)for i,task in enumerate(['E26','E31'])}


def test_disabled_is_noop_even_for_formal_scope():
    ss=scenes();before=deepcopy(ss);ids=[id(x.embodiment)for x in ss.values()]
    result=configure(ss,execution_control=None,environ={})
    assert not result['enabled'] and ss==before and ids==[id(x.embodiment)for x in ss.values()]


@pytest.mark.parametrize('fault',['formal','scope','source','revision','smooth','flag','rate'])
def test_fail_closed_entire_cohort_before_mutation(fault):
    ss=scenes();env={FLAG:'5'};control='positive'
    if fault=='formal':control=None
    if fault=='scope':ss['1'].spec['id']='E13'
    if fault=='source':ss['1'].spec['execution_design']['source_sha256']='wrong'
    if fault=='revision':ss['1'].spec['execution_design']['revision']='old'
    if fault=='smooth':ss['1'].spec['author_smooth_recording']=True
    if fault=='flag':env[FLAG]='10'
    if fault=='rate':ss['1'].embodiment.config['physics']['render_hz']=1
    before=deepcopy(ss)
    with pytest.raises(ValueError):configure(ss,execution_control=control,environ=env)
    assert ss==before


@pytest.mark.parametrize('rate',[1,5])
def test_only_derived_render_rate_and_declarations_change(rate):
    ss=scenes();original=ss['0'].embodiment;before=deepcopy(original.config)
    result=configure(ss,execution_control='positive',environ={FLAG:str(rate)})
    assert result['enabled'] and original.config==before and original.config['physics']['render_hz']==25
    for s in ss.values():
        after=deepcopy(s.embodiment.config);assert after['physics'].pop('render_hz')==rate
        old=deepcopy(before);old['physics'].pop('render_hz');assert after==old
        assert s.spec['embodiment_config_sha256']==s.embodiment.config_hash==_hash(s.embodiment.config)
        assert s.spec['engineering_render_cadence']['encoder_fps']==rate
    assert ss['0'].embodiment.config is not ss['1'].embodiment.config
    with pytest.raises(ValueError):configure(ss,execution_control='positive',environ={FLAG:'5'})


@pytest.mark.parametrize('task',[f'E{i:02d}'for i in range(38,51)])
def test_back13_future_engineering_scoped_cadence(task):
    ss=scenes();ss['1'].spec['id']=task
    before=deepcopy(ss['1'].embodiment.config)
    result=configure(ss,execution_control='positive',environ={FLAG:'5'})
    assert result['full_tick_capture_unchanged'] and not result['physics_changed']
    after=deepcopy(ss['1'].embodiment.config)
    after['physics']['render_hz']=before['physics']['render_hz']
    assert after==before


@pytest.mark.parametrize('task',[f'E{i:02d}'for i in range(14,26)])
def test_front12_future_engineering_scoped_cadence(task):
    ss=scenes();ss['1'].spec['id']=task
    original=ss['1'].embodiment;before=deepcopy(original.config)
    result=configure(ss,execution_control='positive',environ={FLAG:'5'})
    receipt=ss['1'].spec['engineering_render_cadence']
    assert result['full_tick_capture_unchanged']and not result['physics_changed']
    assert receipt['initial_final_capture_passes_unchanged']and receipt['physics_parameters_unchanged']
    assert receipt['original_profile_sha256']==original.config_hash
    assert receipt['derived_profile_sha256']==ss['1'].embodiment.config_hash!=original.config_hash
    after=deepcopy(ss['1'].embodiment.config);after['physics']['render_hz']=before['physics']['render_hz']
    assert after==before and original.config==before


@pytest.mark.parametrize('tasks',[('E14','E25'),('E26','E31')])
@pytest.mark.parametrize('rate',[1,5])
def test_actual_roompool_preserves_all_physics_ticks_and_action_receipts(tasks,rate):
    old,controllers,sim,events=active_pool();sc={}
    for i,(room,c)in enumerate(controllers.items()):
        c.scene.spec=dict(id=tasks[i],execution_design=dict(revision=REVISION_V3,source_sha256=source_sha256(REVISION_V3)))
        c.scene.embodiment=Profile(c.scene.embodiment.config,Path('original.json'),'old')
        del c._room_pool;sc[room]=c.scene
    configure(sc,execution_control='positive',environ={FLAG:str(rate)})
    pool=RoomPool(sim,controllers);receipts=pool.action_batch({room:{}for room in controllers})
    expected_renders=int(100/(250/rate))
    assert pool.physics_ticks==100 and events.count('step')==100 and events.count('render')==expected_renders
    assert sim.current_time==pytest.approx(.4)
    for room,c in controllers.items():
        assert c.physics_ticks==100 and sum(x[0]=='hook'for x in c.events)==100
        assert sum(x==('hook',True)for x in c.events)==expected_renders
        assert receipts[room]['physics_ticks']==100 and receipts[room]['simulation_seconds']==pytest.approx(.4)


@pytest.mark.parametrize('rate',[1,5])
def test_actual_demonstration_constructor_declares_matching_encoder_rate(tmp_path,rate):
    ss=scenes();configure(ss,execution_control='positive',environ={FLAG:str(rate)});s=ss['0'];s.robots={'left':None,'right':None}
    c=SimpleNamespace(scene=s,dt=.004,device='cpu',tick_hooks=[],pose=lambda side:(None,SimpleNamespace(clone=lambda:None)))
    source=Path(__file__).resolve().parents[1]/'videoicl_isaaclab/demonstration.py'
    tree=ast.parse(source.read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='Demonstration');init=next(n for n in cls.body if isinstance(n,ast.FunctionDef)and n.name=='__init__')
    calls=[]
    def popen(args,**kwargs):calls.append(args);return SimpleNamespace(stdin=SimpleNamespace())
    namespace=dict(Path=Path,os=SimpleNamespace(environ={'VIC_FFMPEG_BINARY':'dummy'}),shutil=shutil,time=time,json=json,torch=SimpleNamespace(tensor=lambda *a,**k:None),subprocess=SimpleNamespace(Popen=popen,PIPE=-1))
    exec(compile(ast.Module(body=[init],type_ignores=[]),str(source),'exec'),namespace)
    instance=SimpleNamespace(record=lambda *a:None)
    namespace['__init__'](instance,c,tmp_path)
    assert instance.fps==rate and len(calls)==4
    assert all(args[args.index('-r')+1]==str(rate)for args in calls)
    assert [a[a.index('-s')+1]for a in calls]==['640x480','640x480','640x480','1440x720']
    assert instance.control_report['video_fps']==rate and instance.control_report['physics_dt']==.004
