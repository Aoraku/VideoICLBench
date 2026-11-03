"""Bounded engineering GUI probe against a real native room; no model/provider.

DOM coordinates are a test-driver fixture, not an agent tool. Robot inputs still
travel through screenshot-coordinate GUI clicks and the normal action barrier.
"""
import argparse
import base64
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'packages/sdk'))
from vic_sdk.embodied_gui_mcp import GuiBrowser


def admit_sensor_observation(robot, observation):
    """Audit only public same-frame sensors through the actual model-facing tools."""
    from vic_sdk.embodied_program_geometry import project_pixel
    meta=json.loads(observation.content[0].text)
    public=meta.get('public_observation',{})
    if (public.get('schema')!='videoicl-structured-observation-v1' or
        public.get('observation_contract',{}).get('depth_source')!='simulator_axial_depth'):
        raise ValueError('Structured simulator-depth observation required')
    feedback=public.get('robot_feedback',{})
    tokens=public.get('action_schema',{}).get('tokens',[])
    if len(tokens)!=15 or len(set(tokens))!=15:
        raise ValueError('Full 15-button action schema required')
    for side in ('left','right'):
        actual=robot.page.locator('#'+side+'-actions button').evaluate_all('(xs)=>xs.map(x=>x.dataset.token)')
        if actual!=tokens:raise ValueError('Visible action vocabulary mismatch')
        arm=feedback.get('arms',{}).get(side,{})
        for field,n in [('tcp_position',3),('tcp_quaternion_wxyz',4)]:
            v=arm.get(field)
            if not isinstance(v,list) or len(v)!=n or any(type(a) not in (int,float) or not math.isfinite(a) for a in v):
                raise ValueError('Missing measured TCP state '+side+' '+field)
    before=robot._visible_action_count()
    measurements={}
    for name in ('head','left_wrist','right_wrist'):
        c=feedback.get('camera_calibration',{}).get(name,{})
        if c.get('available') is not True or not all(k in c for k in ('K','T_task_from_camera','width','height')):
            raise ValueError('Missing public camera calibration '+name)
        # Inspect a small grid, not an assumed valid centre. No estimator or fill.
        pixels=[[int((c['height']-1)*r),int((c['width']-1)*u)] for r in (.25,.5,.75) for u in (.25,.5,.75)]
        first=robot.depth_points(meta['frame_id'],name,pixels)
        if first.get('native_frame_id')!=public['native_frame_id']:
            raise ValueError('Sensor query advanced the displayed frame')
        valid=[m for m in first.get('measurements',[]) if m.get('valid') is True]
        if not valid:raise ValueError('No valid original sensor sample in '+name)
        m=valid[0]
        if (m.get('measurement_source')!='simulator_depth' or m.get('estimated') is not False or
            m.get('physical_action') is not False or m.get('frame_id')!=public['native_frame_id']):
            raise ValueError('Sensor provenance mismatch')
        for key in ('K','T_task_from_camera'):
            if m.get('camera_calibration',{}).get(key)!=c[key]:raise ValueError('Sensor calibration changed')
        projected=project_pixel(m['camera_calibration'],m)
        if not projected.get('valid'):raise ValueError('Public sensor projection failed: '+str(projected))
        second=robot.depth_points(meta['frame_id'],name,[m['pixel']])['measurements'][0]
        if any(second.get(k)!=m.get(k) for k in ('valid','depth_m','frame_id','observation_tick','rgb_sha256')):
            raise ValueError('Repeated frozen sensor query changed data')
        measurements[name]=dict(sample=m,repeat_exact=True,projection=projected,valid_grid_points=len(valid))
    if robot.frame!=meta['frame_id'] or robot._visible_action_count()!=before:
        raise ValueError('Read-only sensor query changed GUI frame or action count')
    return dict(schema='videoicl-sensor-only-gui-admission-v1',frame_id=meta['frame_id'],
        native_frame_id=public['native_frame_id'],buttons_per_arm=15,steps=before,
        measured_tcp=feedback['arms'],cameras=measurements,readonly_confirmed=True)


def admit_rule_qa(robot, config):
    """Exercise real program gating with a fixed legal engineering answer, never a key."""
    from vic_sdk.embodied_program_gui import ProgramGuiSession
    from vic_sdk.rule_qa_gate import RuleQAGate
    before=robot._visible_action_count()
    session=ProgramGuiSession(robot,config)
    source='observe()\nact([{"kind":"wait","wait_ms":0}])'
    try:
        rejected=session.execute(source,'qa-engineering-before-answer')
        value=json.loads(rejected.content[0].text)
        if value.get('ok') or robot._visible_action_count()!=before:
            raise ValueError('QA gate failed to reject program input before answer')
        question=robot.qa_question()
        if question.get('status')!='awaiting_answer' or set(question['question']['options'])!=set('ABCD'):
            raise ValueError('QA engineering question unavailable')
        accepted=robot.qa_answer('A')
        if accepted!={'status':'submitted','action_allowed':True}:
            raise ValueError('QA engineering answer not persisted')
        resumed=RuleQAGate(config)
        if resumed.question().get('status')!='submitted' or not resumed.submit('B').get('reused_first_answer'):
            raise ValueError('QA first answer was not stable across reconnect')
        after=session.execute(source,'qa-engineering-after-answer')
        if not json.loads(after.content[0].text).get('ok') or robot._visible_action_count()!=before:
            raise ValueError('QA engineering answer did not unlock zero-motion input')
        saved=json.loads(resumed.answer.read_text())
        if saved['selected_option']!='A' or saved['source_sha256']!=config['rule_qa']['source_sha256']:
            raise ValueError('QA engineering receipt identity differs')
        return dict(schema='rule-qa-engineering-admission-v1',validation_only=True,scientific_evaluation=False,
            model_requests=0,source=config['condition'],source_sha256=saved['source_sha256'],
            question_id=saved['question_id'],program_input_blocked_before_answer=True,
            first_answer_persisted=True,reconnect_reuses_first_answer=True,
            fixed_test_answer='A',correct_answer_read=False,correctness_evaluated=False,
            physical_action_count_before=before,physical_action_count_after=robot._visible_action_count(),
            receipt=str(resumed.answer))
    finally:session.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--connection', type=Path, required=True)
    p.add_argument('--task-dir', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--browser-path', type=Path)
    p.add_argument('--timeout', type=int, default=600)
    p.add_argument('--profile', choices=['basic','e31_rgb_motion_v1','e31_rgbd_motion_v2','sensor_only_gui_v1','inference_motion_v1'], default='basic')
    args = p.parse_args()
    if args.timeout <= 0: p.error('A positive probe timeout is required')
    import httpx
    from PIL import Image, ImageStat
    connection = json.loads(args.connection.read_text())
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    identity = connection['identity']
    def token(name):
        path = Path(connection[name])
        return (path if path.is_absolute() else args.connection.parent/path).read_text().strip()
    demo = connection.get('demo')
    response_timeout = float(connection.get('native_response_timeout_seconds',
        connection.get('barrier_timeout_seconds',300)+120))+30
    config = dict(control_url=connection['control_url'], actor_token=token('actor_token_file'),
        run_id=identity['run_id'], output_dir=str(out), condition=connection['condition'],
        max_actions=connection['max_actions'], max_gui_inputs=100,
        deadline_unix=time.time()+args.timeout, demo_video=demo['path'] if demo else None,
        browser_path=str(args.browser_path) if args.browser_path else None,
        gui_settle_timeout_ms=int(response_timeout*1000),
        gui_observation_timeout_ms=int(response_timeout*1000))
    from vic_sdk.rule_qa_gate import load_assignment
    from vic_sdk.embodied_agent import assigned_material
    spec=json.loads((args.task_dir/'environment/native.json').read_text())
    material=assigned_material(args.task_dir,spec,connection['condition'])
    config['rule_qa']=load_assignment(args.task_dir,spec,connection['condition'],material)
    config['embodied_harness']='program_gui';config['program_episode_identity']=identity
    if connection['condition']=='text_rule':
        with httpx.Client(base_url=connection['control_url'],timeout=response_timeout,trust_env=False,
                headers={'Authorization':'Bearer '+token('actor_token_file')}) as client:
            response=client.get('/api/state');response.raise_for_status();rule=response.json().get('text_rule')
        if not isinstance(rule,str) or hashlib.sha256(rule.encode()).hexdigest()!=config['rule_qa']['source_sha256']:
            raise ValueError('QA probe text rule differs from assignment')
    report = dict(schema='videoicl-native-gui-probe-v1', identity=identity,
        condition=connection['condition'], validation_only=True, model_requests=0,
        scientific_evaluation=False, status='starting', cameras=[], timings={})
    robot = None
    started = time.monotonic()
    try:
        robot = GuiBrowser(config)
        report['timings']['browser_start_seconds'] = time.monotonic()-started
        initial_observation=robot.observe()
        def cameras(label):
            for name in ('head','left_wrist','right_wrist'):
                src = robot.page.locator('#camera-'+name).get_attribute('src')
                if not src or not src.startswith('data:image/'):
                    raise ValueError('GUI did not deliver native camera pixels: '+name)
                raw = base64.b64decode(src.split(',',1)[1])
                decoded = Image.open(io.BytesIO(raw))
                suffix = {'PNG':'png','JPEG':'jpg'}.get(decoded.format, 'image')
                pixels = decoded.convert('RGB')
                if min(pixels.size) < 2:
                    raise ValueError('Invalid camera shape')
                filename=label+'-'+name+'.'+suffix
                (out/filename).write_bytes(raw)
                report['cameras'].append(dict(phase=label,name=name,file=filename,shape=[pixels.height,pixels.width,3],
                    sha256=hashlib.sha256(raw).hexdigest(),spatial_stddev=sum(ImageStat.Stat(pixels).stddev)/3))
        cameras('before')
        strict_rgb_probe = args.profile in {'e31_rgb_motion_v1','e31_rgbd_motion_v2','inference_motion_v1'}
        if args.profile in {'e31_rgb_motion_v1','e31_rgbd_motion_v2'} and not (identity.get('task_id')=='E31' and identity.get('variant') in {'B','C'}):
            raise ValueError('E31 RGB motion engineering profile requires E31 B/C')
        report['probe_profile']=args.profile
        state_before = None
        sensor_only=args.profile in {'sensor_only_gui_v1','inference_motion_v1'}
        if sensor_only:
            report['sensor_depth_admission']=admit_sensor_observation(robot,initial_observation)
        if strict_rgb_probe:
            with httpx.Client(base_url=connection['control_url'], timeout=response_timeout,
                    trust_env=False, headers={'Authorization':'Bearer '+token('actor_token_file')}) as client:
                state_before=client.get('/api/state').json()
                report['initial_robot_feedback']=state_before.get('robot_feedback',{})
                calibration=state_before.get('robot_feedback',{}).get('camera_calibration',{})
                if set(calibration) != {'head','left_wrist','right_wrist'}:
                    raise ValueError('All three actual camera calibrations are required')
                report['camera_calibration']=calibration
                for name,c in calibration.items():
                    if not all(k in c for k in ('K','T_task_from_camera','width','height','convention')):
                        raise ValueError('Incomplete camera calibration '+name+': '+str(c))
                report['camera_calibration']=calibration
                body=dict(frame_id=state_before['frame_id'],camera='head',
                    row=calibration['head']['height']//2,col=calibration['head']['width']//2)
                measured=client.post('/api/depth-point',json=body)
                measured.raise_for_status();first=measured.json()
                measured=client.post('/api/depth-point',json=body)
                measured.raise_for_status();second=measured.json()
                for measurement in (first,second):
                    if (measurement.get('valid') is not True or measurement.get('measurement_source')!='simulator_depth' or
                        measurement.get('estimated') is not False or measurement.get('units')!='m' or
                        measurement.get('depth_convention')!='optical_axis_m' or not measurement.get('depth_m',0)>0):
                        raise ValueError('Native axial sensor depth was not returned')
                if first['depth_m']!=second['depth_m']:
                    raise ValueError('Frozen sensor query changed depth')
                state_after=client.get('/api/state').json()
                if (state_before['steps'],state_before['frame_id']) != (state_after['steps'],state_after['frame_id']):
                    raise ValueError('Read-only measurement changed robot actions or observation')
                if first.get('observation_tick')!=second.get('observation_tick') or first.get('physical_action') is not False:
                    raise ValueError('Measurement did not preserve the frozen RGB-D observation')
                report['sensor_depth_measurement']=dict(first=first,second=second,steps_unchanged=True,frame_unchanged=True)
                stale=client.post('/api/depth-point',json=dict(body,frame_id='stale-'+body['frame_id']))
                if stale.status_code!=409 or stale.json().get('error')!='stale_frame':
                    raise ValueError('Stale sensor depth query did not reject before execution')
                report['sensor_depth_measurement']['stale_rejected']=True
            for camera in report['cameras']:
                if camera['spatial_stddev']<2:
                    raise ValueError('Blank or near-uniform actual RGB camera '+camera['name'])
        if demo:
            info = robot.demo_info()
            frame = robot.demo_frame(0.)
            if not any(c.type=='image' for c in frame.content):
                raise ValueError('Assigned demonstration frame unavailable')
            video = robot.page.locator('video')
            video.wait_for(state='visible',timeout=30000)
            robot.page.wait_for_function('document.querySelector("video")?.readyState >= 2',timeout=60000)
            report['demo'] = dict(info=info, first_frame_decoded=True,
                html_video=video.evaluate('(v)=>({width:v.videoWidth,height:v.videoHeight,duration:v.duration,readyState:v.readyState})'))
        else:
            if robot.page.locator('video:visible').count():
                raise ValueError('Text room exposed a video')
            report['demo'] = dict(available=False)
        report['rule_qa_admission']=admit_rule_qa(robot,config)
        def click(selector):
            box = robot.page.locator(selector).bounding_box()
            if box is None: raise ValueError('Missing visible control '+selector)
            return dict(kind='click',x=box['x']+box['width']/2,y=box['y']+box['height']/2)
        # Probe inputs remain browser clicks; state reads below only audit receipts.
        motions=[('UP','STILL',7.5,5),('STILL','UP',50,5),('ROTATE_CCW','STILL',7.5,5)] if strict_rgb_probe else [('STILL','STILL',1,5)]
        report['motion_checks']=[]
        prior=state_before
        for index,(left,right,step,rotation) in enumerate(motions):
            before=time.monotonic()
            action_observation=robot.act(robot.frame,[click('#left-actions [data-token="'+left+'"]'),
                click('#right-actions [data-token="'+right+'"]'),click('#step-mm'),
                dict(kind='key',key='ControlOrMeta+A'),dict(kind='text',text=str(step)),
                click('#rotation-deg'),dict(kind='key',key='ControlOrMeta+A'),
                dict(kind='text',text=str(rotation)),click('#commit')])
            report['timings']['commit_'+str(index+1)+'_and_render_seconds']=time.monotonic()-before
            cameras('after-'+str(index+1))
            if sensor_only:
                old=report['sensor_depth_admission']['frame_id']
                try:robot.depth_points(old,'head',[[1,1]])
                except ValueError:report['sensor_depth_admission']['old_gui_frame_rejected_after_action']=True
                else:raise ValueError('Stale GUI frame was accepted after Commit')
                post=admit_sensor_observation(robot,action_observation)
                if post['steps']!=report['sensor_depth_admission']['steps']+index+1:
                    raise ValueError('Expected exactly one native action before sensor readback')
                report['sensor_depth_admission']['after_action']=post

            if strict_rgb_probe:
                with httpx.Client(base_url=connection['control_url'],timeout=response_timeout,
                        trust_env=False,headers={'Authorization':'Bearer '+token('actor_token_file')}) as client:
                    after=client.get('/api/state').json()
                    if index==0:
                        stale=client.post('/api/depth-point',json=body)
                        if stale.status_code!=409 or stale.json().get('error')!='stale_frame':
                            raise ValueError('Previously valid RGB-D frame was not rejected after robot movement')
                        report['sensor_depth_measurement']['previous_valid_frame_rejected_after_action']=True
                arms0=prior['robot_feedback']['arms'];arms1=after['robot_feedback']['arms']
                delta={side:[(b-a)*1000 for a,b in zip(arms0[side]['tcp_position'],arms1[side]['tcp_position'])]
                       for side in ('left','right')}
                check=dict(left=left,right=right,step_mm=step,rotation_deg=rotation,actual_delta_mm=delta,
                    before_arms=arms0,after_arms=arms1,last_action=after['robot_feedback'].get('last_action'))
                report['motion_checks'].append(check)
                if index==0 and (not 3<=delta['left'][2]<=12 or sum(v*v for v in delta['right'])**.5>2):
                    raise ValueError('Asymmetric UP7.5/STILL motion did not meet admission tolerance')
                if index==1 and (not 43<=delta['right'][2]<=57 or sum(v*v for v in delta['left'])**.5>3):
                    raise ValueError('Reachable right UP50/STILL motion did not meet admission tolerance')
                if index==2:
                    rotation_checks={}
                    for side in ('left','right'):
                        a=arms0[side]['tcp_quaternion_wxyz'];b=arms1[side]['tcp_quaternion_wxyz']
                        w,x,y,z=b;v,i,j,k=[a[0],-a[1],-a[2],-a[3]]
                        rel=[w*v-x*i-y*j-z*k,w*i+x*v+y*k-z*j,w*j-x*k+y*v+z*i,w*k+x*j-y*i+z*v]
                        if rel[0]<0:rel=[-v for v in rel]
                        angle=math.degrees(2*math.atan2(sum(v*v for v in rel[1:])**.5,rel[0]))
                        rotation_checks[side]=dict(angle_deg=angle,relative_quaternion_wxyz=rel)
                    check['rotation_checks']=rotation_checks
                    if (any(sum(v*v for v in delta[side])**.5>5 for side in ('left','right'))
                            or not 2<=rotation_checks['left']['angle_deg']<=8
                            or rotation_checks['left']['relative_quaternion_wxyz'][3]<=0
                            or rotation_checks['right']['angle_deg']>1):
                        raise ValueError('Small task-Z rotation did not meet rotation/translation tolerance')
                prior=after
        if robot._status()=='faulted': raise RuntimeError('Native GUI faulted after commit')
        robot.terminal('done','Engineering GUI probe; no model; not a benchmark attempt',robot.frame)
        if robot._status() != 'done':
            raise RuntimeError('GUI did not acknowledge the requested Done button')
        with httpx.Client(base_url=connection['control_url'],timeout=response_timeout,trust_env=False,
                headers={'Authorization':'Bearer '+token('admin_token_file')}) as client:
            response=client.post('/api/private/evaluate',json={'identity':identity})
            response.raise_for_status()
            evaluation=response.json()
            if any(evaluation.get(k)!=v for k,v in identity.items()):
                raise ValueError('Final native identity mismatch')
            if type(evaluation.get('steps')) is not int or evaluation['steps'] != len(motions):
                raise ValueError('Private evaluation did not attest the expected physical commits')
            (out/'evaluation.private.json').write_text(json.dumps(evaluation,ensure_ascii=False,indent=2)+'\n')
        events=[json.loads(line) for line in (out/'computer.jsonl').read_text().splitlines()]
        commits=sum(bool(e.get('physical_commit')) for e in events)
        if commits!=len(motions): raise ValueError('Expected exactly '+str(len(motions))+' acknowledged GUI commits')
        report.update(status='passed',gui_inputs=robot.actions,physical_commits=commits,
            native_success=evaluation.get('success'),native_score=evaluation.get('score'),
            progress_available=evaluation.get('progress_score_available'))
    except Exception as exc:
        report.update(status='failed',error_type=type(exc).__name__,error=str(exc))
    finally:
        if robot is not None: robot.close()
        report['timings']['total_seconds']=time.monotonic()-started
        (out/'probe-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ('identity','status','error_type','model_requests')}))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main())
