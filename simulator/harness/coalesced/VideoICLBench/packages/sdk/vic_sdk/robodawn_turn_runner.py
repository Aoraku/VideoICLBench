"""Future-only decision turns: one paid response, one saved memory, exactly one command.

The executor alone touches the existing public GUI. Request retries never execute
commands. Partial/unknown execution pauses for host reconciliation, without
sealing a world or silently converting an old GUI-tools checkpoint.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from dataclasses import asdict, dataclass
import json
import math
import os
import re
from pathlib import Path
import threading
import time
import uuid

import httpx

from .robodawn_runner import (ResponsesTransport, ProviderFailure, atomic_json,
    append_json, dumps, sha, redact)
from .robodawn_context import ImageAnchor, ContextOverflow
from .robodawn_turn_context import TurnContext, TurnPolicy
from .robodawn_turn_executor import TERMINAL as GUI_TERMINAL

VERSION = 'videoicl-robodawn-single-commit 4'
PROTOCOL = 'decision_turn'
CACHE_WIRE_PROTOCOL = 'openai_responses_explicit_v1'
AFFINITY_WIRE_PROTOCOL = 'session_id_prompt_cache_key_v1'
EPISODE_INSTRUCTIONS = ('You control this episode through robot_turn. Follow the public task and the provided '
    'robot_turn contract. You have no coding or workspace task.')


class ProviderContractRejected(ValueError):
    pass
TURN_INSTRUCTIONS = '''Use exactly one robot_turn function per model decision.
Return scene, progress, memory, plan, commands together. These are your own
interpretations of the visible scene, not hidden ground truth. Update memory
in this same response (aim <=120 words; hard cap2500 characters). Preserve useful
public measurements and prior failures; do not copy full observations or reasoning.
Keep scene, progress and plan to at most about 40 words each. All three fields
are short plain text; do not narrate each queued action in prose.
Choose exactly one semantic command per model decision. Use action_batch to queue
one to 24 ordered pairs of left/right actions and their step_mm/rotation_deg.
Choose the batch length you need; there is no four-action limit. The driver fills
the visible queue, presses Commit ONCE, executes pairs in order, then returns the
final paused GUI and actual per-pair receipts. Each attempted pair counts toward
the 500 physical-action budget, including blocked attempts. Widget edits do not.
Legacy action submits one pair. No extra paid observe decision is needed.
You have no raw GUI clicking, shell, file, subagent or hidden scoring tools.
For a video condition, the assigned video's fixed demo_info gives its duration.
You may revisit it at any later decision with the sole command
{"type":"demo_frames","seconds":[...]} (one to twelve times, 0<=time<duration).
The next decision sees the latest requested demo batch with timestamps, alongside
its unchanged current GUI. This does not move the robot or require another model
call for video metadata. Text-rule conditions have no demonstration video.
You may revisit only this episode's previously seen public history using the sole
command {"type":"history","start":1,"count":1,"include_images":false}.
The dynamic history catalog gives the valid range; count<=5 (<=2 with images).
Historical images and measurements describe their old frame, not the current
world. Reinspection does not replay a command or update the current GUI.
Use depth_points commands only for explicit public sensor queries; do not mix
sensor queries and physical actions in one decision. Different valid demo, sensor
and history queries are legitimate preparation. A finite information-query budget
and repeated-identical-information guard may hold this driver for diagnosis;
these are never instructions to move blindly or end the task. There is no rule
requiring a physical move after three different information queries.
A blocked accepted Commit still counts
as a physical attempt; sensor/demo/history reads and widget edits do not. Do not replay an
accepted, pending, partial or uncertain command. done or giveup must be the sole
command and must follow the actual visible state. Ordinary prose does not end a task.
'''

@dataclass(frozen=True)
class InformationGuardPolicy:
    mode: str = 'information_gain_v1'
    max_information_decisions: int = 8
    max_repeated_queries: int = 3

    def __post_init__(self):
        if self.mode not in ('information_gain_v1', 'strict3'):
            raise ValueError('Unknown information guard mode')
        for name in ('max_information_decisions', 'max_repeated_queries'):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 64:
                raise ValueError('Information guard limits must be finite positive integers <=64')
        if self.max_repeated_queries > self.max_information_decisions:
            raise ValueError('Repeat guard cannot exceed the information-request budget')

    def instructions(self):
        if self.mode == 'strict3':
            return ('Explicit legacy strict3 diagnostic policy: three decisions without a confirmed '
                'Commit hold the driver. This policy never requires moving blindly or declaring failure.')
        return (f'Information-query policy: at most {self.max_information_decisions} consecutive successful '
            f'non-Commit decisions before a diagnostic hold; {self.max_repeated_queries} consecutive '
            'identical queries with the same public observation and same returned information also hold. '
            'Different valid preparatory queries do not trigger the repeat guard. Never move merely '
            'to reset a limit; diagnosis preserves the world and original session.')


def information_fingerprint(command, result):
    """Hash already-returned public information, ignoring call IDs/timings/notes.

    This detects exact repeated evidence, not task progress or information value.
    Pixel order and duplicate requests are canonicalized only for loop detection;
    the actual selected command and execution parameters remain untouched.
    """
    query = deepcopy(command)
    if query.get('type') == 'depth_points':
        query['pixels'] = sorted({tuple(point) for point in query['pixels']})
    if query.get('type') == 'demo_frames':
        query['seconds'] = sorted(set(query['seconds']))
    observation = result.get('observation') or {}
    public = observation.get('public_observation') or {}
    robot = public.get('robot_feedback') or {}
    observed = dict(gui_image_sha256=observation.get('image_sha256'),
        native_frame_id=public.get('native_frame_id'), observation_tick=robot.get('observation_tick'),
        step=observation.get('step'))
    returned = []
    if command['type'] == 'demo_frames':
        for a in result.get('demo_frames', []):
            if isinstance(a, ImageAnchor):
                returned.append(dict(sha256=a.sha256, source_sha256=a.source_sha256, seconds=a.seconds))
            elif isinstance(a, dict):
                returned.append({k:a.get(k) for k in ('sha256', 'source_sha256', 'seconds')})
        returned.sort(key=dumps)
    elif command['type'] == 'depth_points':
        keys = ('valid','estimated','physical_action','camera','pixel','requested_pixel','depth_m',
            'xyz_world_m','xyz_task_m','xyz_camera_m','units','coordinate_frame','reason',
            'camera_calibration','measurement_source','method','sensor_source')
        for row in result.get('results', []):
            for point in row.get('measurements', []) if isinstance(row, dict) else []:
                if isinstance(point, dict):
                    returned.append({k:deepcopy(point[k]) for k in keys if k in point})
        returned.sort(key=dumps)
    elif command['type'] == 'history':
        for row in result.get('results', []):
            receipt = row.get('receipt') if isinstance(row, dict) else None
            selected = receipt.get('history_selection') if isinstance(receipt, dict) else None
            if isinstance(selected, dict):
                returned.append(deepcopy(selected))
    else:
        returned = [{k:r[k] for k in ('ok','accepted','pending','physical_commit','status') if k in r}
            for r in result.get('results', []) if isinstance(r, dict)]
    parts = dict(query_sha256=sha(dumps(query).encode()),
        observation_sha256=sha(dumps(observed).encode()), information_sha256=sha(dumps(returned).encode()))
    return dict(**parts, signature_sha256=sha(dumps(parts).encode()))


def session_affinity_contract(config, session_id, identity):
    """Pure stable namespace -> opaque cache/routing identity, never a credential."""
    settings=config.get('provider_session_affinity')
    if settings is None:
        return dict(enabled=False)
    if not isinstance(settings,dict) or type(settings.get('enabled'))is not bool:
        raise ValueError('Explicit provider_session_affinity enabled boolean required')
    if not settings['enabled']:
        if set(settings)!={'enabled'}:
            raise ValueError('Disabled session affinity does not accept hidden settings')
        return dict(enabled=False)
    if set(settings)!={'enabled','namespace','wire_protocol'} or settings['wire_protocol']!=AFFINITY_WIRE_PROTOCOL:
        raise ValueError('Exact stable session affinity wire protocol and namespace required')
    namespace=settings['namespace']
    if not isinstance(namespace,str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,120}',namespace):
        raise ValueError('Fixed bounded session affinity namespace required')
    if config.get('policy',{}).get('cache_breakpoint_enabled'):
        raise ValueError('Stable session affinity requires provider implicit cache mode, without explicit cache extensions')
    if not isinstance(session_id,str)or not session_id or not isinstance(identity,dict)or not identity:
        raise ValueError('Original persisted session and episode identity required for affinity')
    seed=dict(schema=AFFINITY_WIRE_PROTOCOL,namespace=namespace,session_id=session_id,
        model=config['model'],episode_identity=identity)
    value='vic-'+sha(dumps(seed).encode())[:56]
    return dict(enabled=True,wire_protocol=AFFINITY_WIRE_PROTOCOL,namespace=namespace,
        affinity_id=value,affinity_sha256=sha(value.encode()),
        original_session_sha256=sha(session_id.encode()),empirically_validated=False)


ACTION_SCHEMA = dict(type='object', properties=dict(type=dict(enum=['action']),
    left=dict(type='string'), right=dict(type='string'), step_mm=dict(type='number'),
    rotation_deg=dict(type='number')), required=['type','left','right','step_mm','rotation_deg'], additionalProperties=False)
ACTION_PAIR_SCHEMA = dict(type='object', properties={k:deepcopy(v) for k,v in ACTION_SCHEMA['properties'].items() if k!='type'},
    required=['left','right','step_mm','rotation_deg'], additionalProperties=False)
ACTION_BATCH_SCHEMA = dict(type='object',properties=dict(type=dict(enum=['action_batch']),
    actions=dict(type='array',minItems=1,maxItems=24,items=ACTION_PAIR_SCHEMA)),
    required=['type','actions'],additionalProperties=False)
DEPTH_SCHEMA = dict(type='object', properties=dict(type=dict(enum=['depth_points']),
    camera=dict(type='string'), pixels=dict(type='array', minItems=1, maxItems=16,
        items=dict(type='array', minItems=2, maxItems=2, items=dict(type='number')))),
    required=['type','camera','pixels'], additionalProperties=False)
DEMO_SCHEMA = dict(type='object',properties=dict(type=dict(enum=['demo_frames']),
    seconds=dict(type='array',minItems=1,maxItems=12,items=dict(type='number',minimum=0))),
    required=['type','seconds'],additionalProperties=False)
HISTORY_SCHEMA = dict(type='object',properties=dict(type=dict(enum=['history']),
    start=dict(type='integer',minimum=1),count=dict(type='integer',minimum=1,maximum=5),
    include_images=dict(type='boolean')),required=['type','start','count','include_images'],additionalProperties=False)
DONE_SCHEMA = dict(type='object', properties=dict(type=dict(enum=['done']),summary=dict(type='string')),
    required=['type','summary'], additionalProperties=False)
GIVEUP_SCHEMA = dict(type='object', properties=dict(type=dict(enum=['giveup']),reason=dict(type='string')),
    required=['type','reason'], additionalProperties=False)
ROBOT_TURN = dict(type='function', name='robot_turn', strict=False,
    description='One complete model decision and its updated memory; execute exactly one public semantic command and at most one physical Commit.',
    parameters=dict(type='object', properties=dict(scene=dict(type='string',maxLength=600),
        progress=dict(type='string',maxLength=600),memory=dict(type='string',minLength=1,maxLength=2500),
        plan=dict(type='string',maxLength=600),commands=dict(type='array',minItems=1,maxItems=1,
            items=dict(oneOf=[ACTION_SCHEMA,ACTION_BATCH_SCHEMA,DEPTH_SCHEMA,DEMO_SCHEMA,HISTORY_SCHEMA,DONE_SCHEMA,GIVEUP_SCHEMA]))),
        required=['scene','progress','memory','plan','commands'],additionalProperties=False))


def validate_decision(response, memory_limit=2500):
    calls=[item for item in response.get('output',[]) if item.get('type')=='function_call']
    if len(calls)!=1 or calls[0].get('name')!='robot_turn':
        raise ValueError('Exactly one robot_turn function is required; no extra GUI or notes tools')
    call=calls[0]
    if not isinstance(call.get('call_id'),str)or not call['call_id']:
        raise ValueError('robot_turn requires a stable call_id')
    try:
        value=json.loads(call['arguments'],parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite decision')))
    except (KeyError,TypeError,ValueError):
        raise ValueError('robot_turn arguments must be finite JSON') from None
    if not isinstance(value,dict)or set(value)!={'scene','progress','memory','plan','commands'}:
        raise ValueError('robot_turn requires exactly scene/progress/memory/plan/commands')
    for key in ('scene','progress','plan'):
        if not isinstance(value[key],str) or len(value[key]) > 600:
            raise ValueError('Model scene/progress/plan must be short text, at most 600 characters')
    if not isinstance(value['memory'],str)or not value['memory'].strip()or len(value['memory'])>memory_limit:
        raise ValueError('Updated nonempty bounded memory must accompany every decision')
    commands=value['commands']
    if not isinstance(commands,list)or len(commands)!=1 or any(not isinstance(c,dict)for c in commands):
        raise ValueError('Each decision requires exactly one semantic command object')
    kinds={c.get('type')for c in commands}
    if kinds not in ({'action'},{'action_batch'},{'depth_points'},{'demo_frames'},{'history'},{'done'},{'giveup'}):raise ValueError('Do not mix physical, sensor-only or terminal commands')
    if kinds&{'done','giveup'}and len(commands)!=1:raise ValueError('Terminal command must be sole command')
    for c in commands:
        kind=c['type']
        allowed={'action':{'type','left','right','step_mm','rotation_deg'},'action_batch':{'type','actions'},'depth_points':{'type','camera','pixels'},'demo_frames':{'type','seconds'},'history':{'type','start','count','include_images'},'done':{'type','summary'},'giveup':{'type','reason'}}[kind]
        if set(c)!=allowed:raise ValueError('Unexpected or missing semantic command fields')
        if kind in ('action','action_batch'):
            pairs=[{k:v for k,v in c.items()if k!='type'}]if kind=='action'else c['actions']
            if not isinstance(pairs,list)or not 1<=len(pairs)<=24:raise ValueError('Action batch requires one to 24 ordered pairs')
            for pair in pairs:
                if not isinstance(pair,dict)or set(pair)!={'left','right','step_mm','rotation_deg'}:raise ValueError('Each pair requires explicit public arm actions and magnitudes')
                if any(not isinstance(pair[k],str)or not pair[k]for k in ('left','right')):raise ValueError('Explicit public left/right action tokens required')
                if any(type(pair[k])not in (int,float)or not math.isfinite(pair[k])or pair[k]<0 for k in ('step_mm','rotation_deg')):raise ValueError('Finite nonnegative public action magnitudes required')
        elif kind=='depth_points':
            if not isinstance(c['camera'],str)or not c['camera']:raise ValueError('Explicit public camera required')
            pixels=c['pixels']
            if not isinstance(pixels,list)or not 1<=len(pixels)<=16 or any(not isinstance(x,list)or len(x)!=2 or any(type(v)not in(int,float)or not math.isfinite(v)or v<0 for v in x)for x in pixels):raise ValueError('One to sixteen finite public pixels required')
        elif kind=='demo_frames':
            times=c['seconds']
            if not isinstance(times,list)or not 1<=len(times)<=12 or any(type(t)not in(int,float)or not math.isfinite(t)or t<0 for t in times):raise ValueError('One to twelve finite nonnegative demonstration times required')
        elif kind=='history':
            if type(c['start'])is not int or c['start']<1 or type(c['count'])is not int or not 1<=c['count']<=5 or type(c['include_images'])is not bool or(c['include_images']and c['count']>2):raise ValueError('Bounded episode history start/count/include_images required')
        elif not isinstance(c['summary'if kind=='done'else'reason'],str):raise ValueError('Terminal explanation must be text')
    return call['call_id'],value


class Runner:
    def __init__(self,config,*,executor=None,transport=None,sleep=time.sleep,emit=None,resume=None):
        self.config=deepcopy(config)
        if config.get('protocol')!=PROTOCOL:raise ValueError('New driver requires explicit decision_turn protocol')
        if config.get('schema')=='videoicl-robodawn-profile-v2' or config.get('decision_contract')not in (None,'single_commit_v1','single_commit_batch_v2'):
            raise ValueError('Old multi-command decision profile cannot be migrated to single-Commit')
        self.policy=TurnPolicy(**config.get('policy',{}))
        self.guard_policy=InformationGuardPolicy(**config.get('information_guard',{}))
        # Validate config before a browser/world is opened; derive the real value only from persisted state.
        session_affinity_contract(config,'config-validation',{'scope':'preflight'})
        self.session_affinity_id=None
        if self.policy.cache_breakpoint_enabled and config.get('provider_cache_wire_protocol')!=CACHE_WIRE_PROTOCOL:
            raise ValueError('Explicit cache requires verified wire format declaration openai_responses_explicit_v1')
        if config.get('provider_cache_boundary','static')not in ('static','static_and_observation'):
            raise ValueError('Unknown explicit cache boundary')
        budget=config.get('diagnostic_decisions_per_launch')
        if budget is not None and(type(budget)is not int or not 1<=budget<=20):
            raise ValueError('Diagnostic decision budget must be one to twenty or absent')
        self.profile=Path(config['profile']);self.output=Path(config['output_root'])
        if (self.profile/'robodawn-state.private.json').exists():raise ValueError('Legacy GUI-tools checkpoint cannot be converted to decision turns')
        self.directory=self.profile/'decision-turns';self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.state_file=self.profile/'decision-turn-state.private.json'
        self.events=self.directory/'events.private.jsonl'
        self.computer=json.loads(Path(config['computer_config']).read_text())
        self.identity=deepcopy(self.computer.get('program_episode_identity')or{'run_id':self.computer['run_id']})
        self.has_demo=self.computer.get('condition')!='text_rule'and bool(self.computer.get('demo_video'))
        self.model_tool=deepcopy(ROBOT_TURN)
        if not self.has_demo:
            items=self.model_tool['parameters']['properties']['commands']['items']['oneOf']
            items[:]=[v for v in items if v['properties']['type']['enum']!=['demo_frames']]
        self.config_pin=sha(dumps(config).encode());self.resume=resume
        self.executor=executor;self.transport=transport;self.sleep=sleep;self.emit=emit or(lambda row:print(dumps(row),flush=True))
        self.context=None;self.state=None

    def event(self,kind,**fields):
        row=deepcopy(fields);row.update(time=time.time(),type=kind,session_id=self.state.get('session_id')if self.state else None,protocol=PROTOCOL)
        append_json(self.events,row)

    def save(self):
        self.state['context']=self.context.export_state()
        atomic_json(self.state_file,self.state)

    def pause(self,reason,**details):
        self.state.update(phase='paused',paused=True,diagnostic=dict(reason=reason,**details))
        self.event('driver_paused',reason=reason,**details);self.save()
        self.emit(dict(type='driver.paused',session_id=self.state['session_id'],reason=reason,protocol=PROTOCOL))
        return self.state

    def set_observation(self,obs):
        if not isinstance(obs,dict)or not isinstance(obs.get('frame_id'),str):raise ValueError('Executor must return a public GUI frame')
        image=obs.get('image');digest=obs.get('image_sha256')
        if not isinstance(image,dict)or not isinstance(digest,str):raise ValueError('Actual current GUI image and SHA required')
        raw=base64.b64decode(image['image_url'].split(',',1)[1],validate=True)
        if sha(raw)!=digest:raise ValueError('Executor GUI image hash mismatch')
        width,height=obs.get('width'),obs.get('height')
        cost=math.ceil(math.ceil(width/32)*math.ceil(height/32)*1.2)if type(width)is int and type(height)is int and width>0 and height>0 else 2800
        self.context.set_current_gui(ImageAnchor(image,digest,cost,'gui',frame_id=obs['frame_id']),obs.get('public_observation'),camera_views=obs.get('camera_views'),public_gui_state={k:obs.get(k)for k in ('step','max_robot_actions','episode_status')})
        self.state['last_observation']=deepcopy(obs)

    def initialize(self):
        if self.state is not None:return
        if (self.profile/'robodawn-state.private.json').exists():raise ValueError('Legacy GUI-tools checkpoint cannot be converted to decision turns')
        if self.state_file.exists():
            state=json.loads(self.state_file.read_text())
            if state.get('protocol')!=PROTOCOL or state.get('version')!=VERSION or state.get('config_sha256')!=self.config_pin or not self.resume or self.resume!=state.get('session_id'):raise ValueError('Decision-turn resume must match original protocol/config/session')
            if state.get('information_guard_policy') != asdict(self.guard_policy):
                raise ValueError('Information guard policy must match the explicit checkpoint migration')
            self.state=state
            self.context=TurnContext.from_state(state['context'],archive_dir=self.directory/'archive',expected_identity=self.identity)
            if self.state['phase']=='executing' or self.context.protected_decision_ids:
                self.pause('unresolved_command_requires_host_reconciliation',no_replay=True)
        else:
            if self.resume:raise ValueError('Decision-turn session not found; refusing a substitute')
            if list((self.profile/'sessions').glob('*.jsonl')):raise ValueError('Existing session journal cannot change protocol')
            instruction=Path(self.config['instruction_path']).read_text()
            developer=TURN_INSTRUCTIONS+'\n'+self.guard_policy.instructions()+'\n'+self.config.get('developer_instructions','')
            self.context=TurnContext(self.identity,instruction,developer,[self.model_tool],archive_dir=self.directory/'archive',policy=self.policy)
            self.state=dict(protocol=PROTOCOL,version=VERSION,session_id=str(uuid.uuid4()),config_sha256=self.config_pin,
                identity=self.identity,phase='initializing',paused=False,terminal=False,requests=0,successes=0,failures=0,
                decisions=0,physical_turns=0,physical_commits=0,physical_action_count=0,readonly_streak=0,seen_response_ids=[],
                information_guard_policy=asdict(self.guard_policy), information_decisions=0,
                repeated_information_streak=0,last_information_signature=None,
                usage=dict(input_tokens=0,cached_input_tokens=0,output_tokens=0,reasoning_output_tokens=0),current_execution=None)
            (self.profile/'sessions').mkdir(exist_ok=True,mode=0o700)
            append_json(self.profile/'sessions'/(self.state['session_id']+'.jsonl'),dict(type='session_meta',payload=dict(id=self.state['session_id'],protocol=PROTOCOL,identity=self.identity)))
            self.event('session_started',model=self.config['model']);self.save()
        self.bind_session_affinity()
        self.emit(dict(type='thread.started',thread_id=self.state['session_id'],protocol=PROTOCOL))
        if self.state['phase']=='paused' or self.state['terminal']:return
        if self.executor is None:
            from .robodawn_turn_executor import TurnExecutor
            self.executor=TurnExecutor(self.computer,on_intent=self.on_intent,on_receipt=self.on_receipt,
                demo_frame_count=self.config.get('demo_frame_count',0),demo_timestamps=self.config.get('demo_timestamps'))
        else:
            self.executor.on_intent=self.on_intent;self.executor.on_receipt=self.on_receipt
        initialized=self.executor.initialize()
        info=initialized.get('demo_info') or {'available':False}
        info={k:deepcopy(info[k])for k in ('available','source_sha256','duration_seconds','fps','frame_count','on_demand')if k in info}
        source_sha=sha(Path(self.computer['demo_video']).read_bytes())if self.has_demo else None
        if self.has_demo and (info.get('available')is not True or info.get('source_sha256')!=source_sha or info.get('on_demand')is not True):raise ValueError('Assigned video needs verified fixed demo_info and on-demand capability')
        if not self.has_demo and info.get('available')is not False:raise ValueError('Text/no-video condition cannot acquire a demo')
        if self.state.get('demo_info')is not None and self.state['demo_info']!=info:raise ValueError('Assigned demonstration metadata changed during this same session')
        if self.state['phase']=='initializing':
            self.context.set_demo_info(info);self.state['demo_info']=deepcopy(info)
            anchors=[self.demo_anchor(value,source_sha)for value in initialized.get('demo_anchors',[])]
            self.context.set_demo_anchors(anchors);self.set_observation(initialized['observation'])
            self.state['terminal']=initialized['observation'].get('episode_status')in GUI_TERMINAL
            self.state['phase']='terminal'if self.state['terminal']else'ready';self.save()
        elif self.state['phase']=='ready':
            self.set_observation(initialized['observation']);self.save()
        if self.transport is None:
            key=os.environ.get('VIC_MODEL_API_KEY')
            if not key:raise ValueError('VIC_MODEL_API_KEY required only in child environment')
            self.transport=ResponsesTransport(self.config['base_url'],key,session_affinity_id=self.session_affinity_id)

    def bind_session_affinity(self):
        contract=session_affinity_contract(self.config,self.state['session_id'],self.identity)
        existing=self.state.get('session_affinity')
        if existing is not None and existing!=contract:
            raise ValueError('Stable session affinity checkpoint differs; explicit idle migration required')
        self.session_affinity_id=contract.get('affinity_id')
        if contract['enabled']:
            if isinstance(self.transport,ResponsesTransport):
                if self.transport.session_affinity_id not in (None,self.session_affinity_id):
                    raise ValueError('Transport affinity does not belong to the original model session')
                self.transport.session_affinity_id=self.session_affinity_id
            if existing is None:
                self.state['session_affinity']=contract
                self.event('session_affinity_bound',**{k:v for k,v in contract.items()if k!='affinity_id'},
                    same_original_session=True,cache_hit_guaranteed=False)
                self.save()

    def demo_anchor(self,value,source_sha):
        if isinstance(value,ImageAnchor):anchor=deepcopy(value)
        else:
            if not isinstance(value,dict)or value.get('kind')!='demo':raise ValueError('Demonstration anchor provenance missing')
            anchor=ImageAnchor(value['image_item'],value['sha256'],value.get('token_cost',2800),'demo',source_sha256=value.get('source_sha256'),seconds=value.get('seconds'))
        if not source_sha or anchor.source_sha256!=source_sha or anchor.kind!='demo':raise ValueError('Demo frames must match this episode assigned source SHA')
        return anchor

    def inspect_history(self,command,decision_id):
        observation=deepcopy(self.state['last_observation'])
        record=dict(decision_id=decision_id,command_index=0,command=deepcopy(command),
            frame_id=observation['frame_id'],physical_commit=False)
        self.on_intent(record)
        metadata=self.context.inspect_history(command['start'],command['count'],include_images=command['include_images'])
        # The context already carries the selected public records/images once.
        # Receipt history stores only a bounded reference, never recursively embeds them.
        summary=dict(start=command['start'],count=command['count'],include_images=command['include_images'],
            selection_metadata_sha256=sha(dumps(metadata).encode()))
        row=dict(command=deepcopy(command),ok=True,physical_commit=False,receipt=dict(history_selection=summary))
        self.on_receipt(dict(record,result=row,pending=False,uncertain=False))
        return dict(results=[row],observation=observation,physical_commits=0,pending=False,uncertain=False,
            terminal=observation.get('episode_status')in GUI_TERMINAL,step=observation.get('step'))

    def on_intent(self,record):
        if self.state['phase']!='executing' or record.get('decision_id')!=self.state['current_execution']['decision_id']:raise ValueError('Executor intent identity mismatch')
        execution=self.state['current_execution'];index=record.get('command_index')
        if type(index)is not int or not 0<=index<len(execution['commands']):raise ValueError('Executor command index mismatch')
        if any(r['command_index']==index for r in execution['intents']):raise ValueError('Duplicate executor intent; no replay')
        if record.get('requested_command',record.get('command'))!=execution['commands'][index]:raise ValueError('Executor changed selected command')
        execution['intents'].append(deepcopy(record));self.event('command_intent',record=record);self.save()

    def on_receipt(self,record):
        execution=self.state['current_execution']
        if not execution or record.get('decision_id')!=execution['decision_id']:raise ValueError('Executor receipt identity mismatch')
        index=record.get('command_index')
        if not any(r['command_index']==index for r in execution['intents']):raise ValueError('Executor receipt without checkpointed intent')
        if any(r.get('command_index')==index for r in execution['receipts']):raise ValueError('Duplicate executor receipt')
        execution['receipts'].append(deepcopy(record));self.event('command_receipt',record=record);self.save()

    def body(self,build):
        body=dict(model=self.config['model'],instructions=EPISODE_INSTRUCTIONS,input=deepcopy(build.items),tools=deepcopy(build.tools),
            tool_choice=dict(type='function',name='robot_turn'),reasoning=dict(effort=self.config.get('effort','high')),
            include=['reasoning.encrypted_content'],parallel_tool_calls=False,store=False,stream=True,max_output_tokens=8192)
        if self.session_affinity_id is not None:
            body['prompt_cache_key']=self.session_affinity_id
            self.event('session_affinity_request',affinity_sha256=sha(self.session_affinity_id.encode()),
                header_name='session-id',body_field='prompt_cache_key',cache_mode='provider_implicit',cache_hit_guaranteed=False)
        self.state['provider_instructions_contract']=dict(
            instructions_sha256=sha(EPISODE_INSTRUCTIONS.encode()),instructions_chars=len(EPISODE_INSTRUCTIONS),
            provenance='explicit_short_episode_role_v1',upstream_echo_matches=None)
        self.event('provider_instructions_declared',**self.state['provider_instructions_contract'])
        if self.policy.cache_breakpoint_enabled:
            if not self.policy.provider_cache_breakpoint_capability or self.config.get('provider_cache_wire_protocol')!=CACHE_WIRE_PROTOCOL:
                raise ValueError('Explicit cache contract is missing capability or exact wire protocol')
            boundary=build.cache_breakpoint
            message_index=boundary['boundary_message_index'];content_index=boundary['boundary_content_index']
            block=body['input'][message_index]['content'][content_index]
            if block.get('type')!='input_text':raise ValueError('Cache breakpoint must be final fixed input_text')
            block['prompt_cache_breakpoint']={'mode':'explicit'}
            body['prompt_cache_options']={'mode':'explicit','ttl':'30m'}
            boundaries=[dict(message_index=message_index,content_index=content_index,role='static')]
            if self.config.get('provider_cache_boundary')=='static_and_observation':
                if not self.policy.lean_public_input:
                    raise ValueError('Observation breakpoint requires stable-first lean ordering')
                matches=[]
                for i,item in enumerate(body['input']):
                    for j,content in enumerate(item.get('content',[])):
                        if content.get('type')!='input_text':continue
                        try:value=json.loads(content['text'])
                        except (KeyError,TypeError,ValueError):continue
                        if isinstance(value,dict)and 'current_public_observation'in value:matches.append((i,j))
                if len(matches)!=1 or matches[0][0]<=message_index:
                    raise ValueError('Unique current observation cache boundary required')
                i,j=matches[0]
                body['input'][i]['content'][j]['prompt_cache_breakpoint']={'mode':'explicit'}
                boundaries.append(dict(message_index=i,content_index=j,role='current_observation'))
            self.event('cache_wire_contract',wire_protocol=CACHE_WIRE_PROTOCOL,applied_to_wire=True,
                empirically_validated=False,boundary_message_index=message_index,boundary_content_index=content_index,
                boundaries=boundaries,
                context_static_prefix_hash=build.static_prefix_hash,
                wire_static_prefix_hash=sha(dumps(dict(instructions=body['instructions'],input=body['input'][:message_index+1],tools=body['tools'])).encode()))
        return body

    def account(self,response,number):
        rid=response.get('id')
        if not isinstance(rid,str)or not rid:raise ProviderFailure('Completed response omitted id')
        if rid in self.state['seen_response_ids']:raise ValueError('Duplicate response id; refuse duplicate usage and execution')
        usage=response.get('usage')
        if not isinstance(usage,dict)or any(type(usage.get(k))is not int or usage[k]<0 for k in ('input_tokens','output_tokens')):raise ProviderFailure('Completed response omitted numeric usage')
        cached=(usage.get('input_tokens_details')or{}).get('cached_tokens')
        written=(usage.get('input_tokens_details')or{}).get('cache_write_tokens')
        reasoning=(usage.get('output_tokens_details')or{}).get('reasoning_tokens')
        if cached is not None and(type(cached)is not int or not 0<=cached<=usage['input_tokens']):raise ProviderFailure('Invalid cached input usage')
        if written is not None and(type(written)is not int or not 0<=written<=usage['input_tokens']-(cached or 0)):raise ProviderFailure('Invalid cache write usage')
        if reasoning is not None and(type(reasoning)is not int or not 0<=reasoning<=usage['output_tokens']):raise ProviderFailure('Invalid reasoning output usage')
        # Preserve the historical usage schema. A separate evidence accumulator
        # explicitly scopes newly instrumented responses; missing writes are not zero.
        evidence=self.state.setdefault('cache_accounting',dict(first_observed_request=number,
            observed_responses=0,reported_read_tokens=0,reported_write_tokens=0,
            missing_read_responses=0,missing_write_responses=0,positive_read_responses=0))
        evidence['observed_responses']+=1
        for label,value in [('read',cached),('write',written)]:
            if value is None:evidence['missing_'+label+'_responses']+=1
            else:evidence['reported_'+label+'_tokens']+=value
        evidence['positive_read_responses']+=int(cached is not None and cached>0)
        evidence['last_response']=dict(request_number=number,response_id=rid,input_tokens=usage['input_tokens'],
            cached_input_tokens=cached,cache_write_tokens=written,
            uncached_input_tokens=usage['input_tokens']-cached if cached is not None else None,
            ordinary_input_tokens=usage['input_tokens']-cached-written if cached is not None and written is not None else None,
            explicit_wire_requested=self.policy.cache_breakpoint_enabled,
            cache_reuse_observed=cached is not None and cached>0,explicit_marker_honored=None)
        for key,value in [('input_tokens',usage['input_tokens']),('output_tokens',usage['output_tokens']),('cached_input_tokens',cached),('reasoning_output_tokens',reasoning)]:
            previous=self.state['usage'][key];self.state['usage'][key]=None if value is None or previous is None else previous+value
        self.state['seen_response_ids'].append(rid);self.state['successes']+=1
        return deepcopy(usage)

    def request(self,body):
        pinned=dumps(body);failures=0
        while True:
            self.state['requests']+=1;number=self.state['requests']
            self.state.update(phase='api_pending',pending_body=deepcopy(body),pending_body_sha256=sha(pinned.encode()),pending_request_number=number)
            self.save();atomic_json(self.directory/f'request-{number:06d}.private.json',body)
            self.event('api_start',request_number=number,body_sha256=sha(pinned.encode()))
            try:response,headers=self.transport.complete(deepcopy(body))
            except (httpx.HTTPError,ProviderFailure)as exc:
                self.state['failures']+=1;failures+=1
                fatal=getattr(exc,'status',None)in {400,401,403,404}
                wait=300 if getattr(exc,'code',None)=='insufficient_quota'else min(300,5*2**min(failures-1,6))
                self.event('api_failure',request_number=number,error_class=type(exc).__name__,status=getattr(exc,'status',None),code=getattr(exc,'code',None),message=redact(str(exc)),usage=None,retry_wait_seconds=0 if fatal else wait,will_retry=not fatal,same_body=True)
                self.save()
                if fatal:raise ProviderContractRejected('Provider configuration/cache contract rejected; no silent fallback')from exc
                self.sleep(wait);continue
            atomic_json(self.directory/f'response-{number:06d}.private.json',dict(body_sha256=sha(pinned.encode()),response=response,headers=headers))
            self.accept_response(response,number)
            return response

    def accept_response(self,response,number):
        usage=self.account(response,number)
        echoed=response.get('instructions')
        echo_hash=sha(echoed.encode()) if isinstance(echoed,str) else None
        echo_matches=(echoed==EPISODE_INSTRUCTIONS) if isinstance(echoed,str) else None
        contract=dict(instructions_sha256=sha(EPISODE_INSTRUCTIONS.encode()),instructions_chars=len(EPISODE_INSTRUCTIONS),
            provenance='explicit_short_episode_role_v1',upstream_echo_matches=echo_matches,
            response_instructions_sha256=echo_hash,response_instructions_chars=len(echoed) if isinstance(echoed,str) else None)
        self.state['provider_instructions_contract']=contract
        self.event('provider_instructions_echo',**contract,billing_effect_unverified=True)
        self.state.update(phase='response_received',response=deepcopy(response));self.state.pop('pending_body',None);self.save()
        self.event('provider_usage',request_number=number,response_id=response['id'],raw_usage=usage,cumulative_usage=self.state['usage'])
        self.event('provider_cache_usage',**self.state['cache_accounting']['last_response'])
        append_json(self.profile/'sessions'/(self.state['session_id']+'.jsonl'),dict(type='driver_usage',payload=dict(response_id=response['id'],usage=usage,protocol=PROTOCOL)))
        self.emit(dict(type='turn.completed',usage=self.state['usage'],response_id=response['id'],protocol=PROTOCOL))

    def information_guard_diagnostic(self):
        if self.guard_policy.mode == 'strict3':
            return dict(reason='three_decisions_without_physical_commit', legacy_policy=True,
                physical_action_forced=False) if self.state['readonly_streak'] >= 3 else None
        repeated = self.state.get('repeated_information_streak', 0)
        count = self.state.get('information_decisions', 0)
        if repeated >= self.guard_policy.max_repeated_queries:
            return dict(reason='repeated_identical_information', repeated_information_streak=repeated,
                threshold=self.guard_policy.max_repeated_queries, physical_action_forced=False)
        if count >= self.guard_policy.max_information_decisions:
            return dict(reason='information_request_budget_reached', information_decisions=count,
                threshold=self.guard_policy.max_information_decisions, physical_action_forced=False)
        return None

    def update_information_guard(self, command, result, commits):
        if commits > 0:
            self.state.update(information_decisions=0,repeated_information_streak=0,last_information_signature=None)
            return
        fingerprint = information_fingerprint(command, result)
        previous = self.state.get('last_information_signature')
        repeated = self.state.get('repeated_information_streak', 0)+1 if previous == fingerprint else 1
        self.state.update(information_decisions=self.state.get('information_decisions', 0)+1,
            repeated_information_streak=repeated,last_information_signature=fingerprint)
        self.event('information_query_completed',command_type=command['type'],fingerprint=fingerprint,
            information_decisions=self.state['information_decisions'],repeated_information_streak=repeated,
            value_judgment=False)

    def execute_response(self):
        response=self.state['response']
        call_id,decision=validate_decision(response,self.policy.memory_max_chars)
        decision_id='turn-'+sha((response['id']+':'+call_id).encode())[:32]
        command=decision['commands'][0]
        if command['type']=='demo_frames':
            if not self.has_demo:raise ValueError('Text/no-video condition has no demonstration command')
            duration=self.state['demo_info']['duration_seconds']
            if any(t>=duration for t in command['seconds']):raise ValueError('Demo timestamp is outside this assigned video')
        if any(item.get('type')=='function_call' and item.get('name')!='robot_turn'for item in response['output']):raise ValueError('No extra tool calls allowed')
        self.context.record_decision(decision,[],physical=False,decision_id=decision_id,state='pending')
        self.state.update(phase='executing',current_execution=dict(decision_id=decision_id,model_call_id=call_id,response_id=response['id'],commands=deepcopy(decision['commands']),intents=[],receipts=[]))
        self.save()  # Same-reply memory + planned commands are durable before any GUI intent.
        if self.policy.lean_public_input:
            consumed=self.context.clear_retrieval_views()
            self.event('retrieval_views_consumed',**consumed,policy='one_followup_response',
                memory_saved=True,api_retry_affected=False)
            self.save()
        try:
            result=self.inspect_history(command,decision_id)if command['type']=='history'else self.executor.execute(deepcopy(decision['commands']),decision_id=decision_id)
        except Exception as exc:
            self.context.reconcile(decision_id,state='unknown',results=[],physical=False)
            return self.pause('executor_interrupted_no_replay',error_class=type(exc).__name__,message=redact(str(exc)),decision_id=decision_id)
        if not isinstance(result,dict)or not isinstance(result.get('results'),list):return self.pause('invalid_executor_receipt',decision_id=decision_id)
        commits=result.get('physical_commits')
        if type(commits)is not int or not 0<=commits<=len(decision['commands']):return self.pause('invalid_executor_commit_count',decision_id=decision_id)
        physical_actions=result.get('physical_action_count',commits if command['type']=='action'else 0)
        maximum_actions=len(command['actions'])if command['type']=='action_batch'else int(command['type']=='action')
        if type(physical_actions)is not int or not 0<=physical_actions<=maximum_actions or (physical_actions>0 and commits!=1):
            return self.pause('invalid_executor_physical_action_count',decision_id=decision_id)
        if command['type']=='action_batch'and commits and 'physical_action_count'not in result:
            return self.pause('missing_batch_physical_action_count_no_replay',decision_id=decision_id)
        pending=result.get('pending',False);uncertain=result.get('uncertain',False)
        if type(pending)is not bool or type(uncertain)is not bool:return self.pause('invalid_executor_pending_flags',decision_id=decision_id)
        if type(result.get('terminal'))is not bool:return self.pause('invalid_executor_terminal_flag',decision_id=decision_id)
        gui_status=result.get('observation',{}).get('episode_status')
        gui_terminal=gui_status in GUI_TERMINAL
        if result['terminal']and not gui_terminal:return self.pause('terminal_not_confirmed_by_public_gui',decision_id=decision_id)
        rows=deepcopy(result['results']);executed=len(rows);planned=len(decision['commands'])
        if executed>planned or commits>executed or any(not isinstance(r,dict)for r in rows):return self.pause('invalid_executor_result_count',decision_id=decision_id)
        known_terminal_cutoff=(result['terminal']and gui_terminal and not pending and not uncertain
            and executed==0 and planned==1 and commits==0)
        if known_terminal_cutoff:
            rows.append(dict(command=deepcopy(decision['commands'][0]),ok=False,physical_commit=False,
                status='not_executed_due_to_public_terminal',episode_status=gui_status))
        partial=not known_terminal_cutoff and (executed!=planned or any(r.get('ok')is not True for r in rows))
        if command['type']=='action_batch'and commits and physical_actions<maximum_actions and not gui_terminal:
            partial=True
        if command['type']=='demo_frames'and not(pending or uncertain or partial):
            frames=result.get('demo_frames')
            if not isinstance(frames,list)or len(frames)!=len(command['seconds']):return self.pause('demo_frames_missing_or_incomplete',decision_id=decision_id)
            source_sha=self.state['demo_info']['source_sha256']
            anchors=[self.demo_anchor(value,source_sha)for value in frames]
            if [a.seconds for a in anchors]!=sorted(command['seconds']):
                raise ValueError('Returned demo frame timestamps must match the selected assigned-video times')
            self.context.set_demo_inspection(anchors)
        public=result.get('observation',{}).get('public_observation')
        self.context.reconcile(decision_id,state='unknown'if pending or uncertain or partial else'completed',results=rows,step=result.get('step'),tcp=public,physical=commits>0)
        if result.get('observation'):self.set_observation(result['observation'])
        self.state['physical_commits']+=commits;self.state['decisions']+=1
        self.state['physical_action_count']=self.state.get('physical_action_count',0)+physical_actions
        if pending or uncertain or partial:return self.pause('partial_or_unknown_execution_no_replay',decision_id=decision_id,pending=pending,uncertain=uncertain,partial=partial)
        self.state['terminal']=gui_terminal
        if known_terminal_cutoff:
            self.state['known_public_terminal_cutoff']=dict(decision_id=decision_id,planned=planned,executed=executed,
                not_executed=planned-executed,episode_status=gui_status,unexecuted_commands=deepcopy(decision['commands'][executed:]))
            self.event('known_public_terminal_cutoff',**self.state['known_public_terminal_cutoff'])
        self.state['physical_turns']+=int(commits>0)
        self.state['readonly_streak']=0 if commits>0 else self.state['readonly_streak']+1
        self.update_information_guard(command,result,commits)
        self.state.update(phase='terminal'if self.state['terminal']else'ready',current_execution=None)
        self.event('decision_completed',decision_id=decision_id,physical_commits=commits,
            physical_action_count=physical_actions,readonly_streak=self.state['readonly_streak']);self.save()
        guard=self.information_guard_diagnostic()
        if not self.state['terminal']and guard:
            return self.pause(**guard)
        return self.state

    def run(self,*,max_decisions=None):
        self.initialize()
        completed=0
        while not self.state['terminal']and self.state['phase']!='paused':
            diagnostic_budget=self.config.get('diagnostic_decisions_per_launch')
            if diagnostic_budget is not None and completed>=diagnostic_budget:
                return self.pause('diagnostic_decision_budget_reached',decisions_this_launch=completed,
                    accepted_actions_drained=True,world_preserved=True)
            if max_decisions is not None and completed>=max_decisions:break
            if self.state['phase']=='api_pending':
                number=self.state['pending_request_number'];local=self.directory/f'response-{number:06d}.private.json'
                if local.exists():
                    recorded=json.loads(local.read_text())
                    if recorded['body_sha256']!=self.state['pending_body_sha256']:return self.pause('local_response_request_mismatch')
                    self.accept_response(recorded['response'],number)
                else:
                    try:self.request(self.state['pending_body'])
                    except ProviderContractRejected as exc:return self.pause('provider_contract_rejected',message=redact(str(exc)),silent_fallback=False)
            elif self.state['phase']=='ready':
                guard=self.information_guard_diagnostic()
                if guard:return self.pause(**guard)
                try:build=self.context.build()
                except ContextOverflow as exc:return self.pause('context_overflow_no_material_dropped',estimated_tokens=exc.estimated_tokens)
                self.event('context_built',**{k:v for k,v in build.to_dict().items()if k not in {'items','tools'}})
                try:self.request(self.body(build))
                except ProviderContractRejected as exc:return self.pause('provider_contract_rejected',message=redact(str(exc)),silent_fallback=False)
            if self.state['phase']=='response_received':
                try:self.execute_response()
                except (ValueError,TypeError,KeyError,AttributeError)as exc:return self.pause('invalid_robot_turn_no_execution',message=redact(str(exc)))
                completed+=1
        return self.state

    def close(self):
        if self.executor:self.executor.close()
        if self.transport:self.transport.close()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--resume');args=p.parse_args(argv)
    runner=None
    try:
        runner=Runner(json.loads(args.config.read_text()),resume=args.resume)
        state=runner.run()
        if state['phase']=='paused':
            # Keep the outer graceful environment owner alive; an exit here
            # would otherwise run its seal/evaluate cleanup path.
            threading.Event().wait()
        runner.emit(dict(type='result',result='The actual public GUI reported terminal.',usage=state['usage'],is_error=False,subtype='decision_turn_terminal'))
        return 0
    except Exception as exc:
        if runner is not None and runner.state and runner.context:
            try:runner.pause('driver_error_requires_diagnosis',error_class=type(exc).__name__,message=redact(str(exc)))
            except Exception:runner.emit(dict(type='driver.paused',reason='checkpoint_error_requires_diagnosis',protocol=PROTOCOL))
        else:
            print(dumps(dict(type='driver.paused', reason='initialization_requires_diagnosis',
                message=redact(str(exc)), protocol=PROTOCOL)), flush=True)
        threading.Event().wait()
        raise
    finally:
        if runner is not None:
            runner.close()


if __name__=='__main__':raise SystemExit(main())
