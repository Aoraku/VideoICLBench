"""Public measured in-place half-turns of the two unchanged E15B source Ts."""
import math
from types import SimpleNamespace
import numpy as np
from .execution_design_segments_e15_recover import _capture,_margin,_preflight
from .execution_design_e24_transit import screen_joint_segment
from .realworld_tool_expert import _axis_rotation
from .realworld_semantic_checks import POSITION_TOLERANCE_M,ANGLE_TOLERANCE_DEG

SOURCE_HASHES=dict(red_t='98bae9ae3dddf67e58004695930c09f3d36f715dfa2bf5d65d1ed2b7179fa493',
                   blue_t='f6634d82aa7e5a389b17f8ce40af445a82e156a02c1c45d08c64838b6c41b7c2')

def wrap(value):return math.atan2(math.sin(value),math.cos(value))


class MeasuredT:
    def __init__(self,author,name):
        from .execution_design_e15_wrist import _scope
        from .execution_design_segments_e15 import _goal
        _scope(author);self.a=author;self.c=author.c;self.spec=author.scene.spec
        if self.spec.get('variant')!='B'or self.spec['execution_design'].get('condition')!='I':
            raise ValueError('Measured E15 B/I reference only')
        self.objects={o['id']:o for o in self.spec['objects']};self.name=name
        if name not in SOURCE_HASHES or self.objects[name].get('source_asset',{}).get('sha256')!=SOURCE_HASHES[name]:
            raise ValueError('Unchanged original T source required')
        self.protected='blue_t'if name=='red_t'else'red_t'
        self.goal=_goal(self.spec,name,name+'_target');self.zone=next(z for z in self.spec['zones']if z['id']==self.goal['target'])
        state,_=self.c.snapshot();body=state[self.protected]
        self.saved=(np.asarray(body['pos']).copy(),np.asarray(body['mat']).copy())
        self.p=SimpleNamespace(a=author,c=self.c,spec=self.spec,objects=self.objects,tip=author.tip,snapshot=self.c.snapshot)
        self.carrying=False;self.operations=[];self.start=self.c.steps

    def guard(self):
        state,contacts=self.c.snapshot();other=state[self.protected];body=state[self.name]
        if(any(other['grasp'])or frozenset((self.protected,'table'))not in contacts
                or np.linalg.norm(np.asarray(other['pos'])-self.saved[0])>.002
                or np.linalg.norm(np.asarray(other['mat'])-self.saved[1])>.02):
            raise RuntimeError('Protected original T moved during measured half-turn')
        if self.carrying and(not body['grasp'][1]or body['grasp'][0]
                or not all(frozenset((self.name,'right_finger'+str(i)))in contacts for i in(1,2))):
            raise RuntimeError('Actual bilateral T grip lost during public reference')
        return state,contacts

    def model(self):
        self.guard();m,all_obstacles=_capture(self.p)
        if _margin(m['q'],m['limits'])<=.02:raise RuntimeError('Actual T reference lacks original20mrad joint reserve')
        feedback=self.c.action_feedback().get('control_feedback',{}).get('right',{})
        if(feedback.get('status')=='blocked'or feedback.get('joint_limit_names')or feedback.get('consecutive_ik_refusals',0)>0):
            raise RuntimeError('Actual T public controller refused an increment')
        prefix='object:'+self.name+':'
        target=[o for o in all_obstacles if o['name'].startswith(prefix)]
        table=[o for o in all_obstacles if o['name']=='table'];assert target and len(table)==1
        environment=[o for o in all_obstacles if o['name']!='table'and not o['name'].startswith(prefix)]
        if self.carrying:m=dict(m,clouds=m['clouds']+[dict(name='held:'+o['name'],influence=7,points=o['points'])for o in target])
        return m,environment,table,target

    def step(self,token,delta=None,degrees=None):
        if self.c.steps-self.start>=650:raise RuntimeError('Bounded measured T reference exhausted')
        m,environment,table,target=self.model()
        position=m['position']if delta is None else m['position']+delta
        rotation=m['rotation']if degrees is None else _axis_rotation([0,0,1],math.radians(degrees))@m['rotation']
        receipt=_preflight(m,environment,position,rotation)
        robot=dict(m,clouds=[c for c in m['clouds']if not c['name'].startswith('held:')])
        candidate=np.asarray(receipt['candidate_joints_rad'])
        screen_joint_segment(robot,m['q'],candidate,table,margin=1e-6)
        if not self.carrying:
            palm=dict(robot,clouds=[c for c in robot['clouds']if'finger'not in c['name']])
            screen_joint_segment(palm,m['q'],candidate,target,margin=.002)
        if degrees is None:self.a.act('STILL',token,float(np.linalg.norm(delta)*1000))
        else:self.a.act('STILL',token,rotation_deg=abs(degrees))
        after,environment,table,target=self.model()
        screen_joint_segment(after,after['q'],after['q'],environment,margin=.005)
        robot=dict(after,clouds=[c for c in after['clouds']if not c['name'].startswith('held:')])
        screen_joint_segment(robot,after['q'],after['q'],table,margin=1e-6)
        if self.carrying and min(float(o['points'][:,2].min())for o in target)<float(table[0]['hi'][2])-1e-5:
            raise RuntimeError('Actual held T crossed original table')
        if np.linalg.norm(after['q']-m['q'])>=.35:raise RuntimeError('Measured T left original nearby joint branch')
        if delta is not None and float((after['position']-m['position'])@(delta/np.linalg.norm(delta)))<.0001:
            raise RuntimeError('Actual public T translation failed to advance')
        receipt.update(public_token=token,degrees=degrees,actual_margin_rad=_margin(after['q'],after['limits']))
        self.operations.append(receipt)

    def move(self,goal,tolerance=.006):
        goal=np.asarray(goal,float)
        for _ in range(240):
            m,_,_,_=self.model();error=goal-m['position']
            if np.max(np.abs(error))<=tolerance:return
            if not self.carrying and _margin(m['q'],m['limits'])<.040:
                sign=1. if m['q'][6]>0 else-1.
                self.step('ROTATE_CCW'if sign>0 else'ROTATE_CW',degrees=sign*2.)
                continue
            axis=int(np.argmax(np.abs(error)));delta=np.zeros(3);delta[axis]=math.copysign(min(.005,abs(float(error[axis]))),error[axis])
            self.step((('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(delta[axis]<0)],delta=delta)
        raise RuntimeError('Measured three-mm T waypoint exhausted')

    def acquire(self):
        state,contacts=self.guard()
        if any(any(body['grasp'])for body in state.values())or frozenset((self.name,'table'))not in contacts:
            raise RuntimeError('Real empty hands and supported original T required')
        self.a.stage='E15-measured-empty-three-mm-'+self.name
        self.a.act('STILL','RELEASE');self.guard()
        height=.96;self.move([*self.a.tip('right')[:2],height])
        # Empty yaw is not a task requirement. Retain the real current hand
        # pose and let the native bilateral grasp validate the original stem.
        # The old extra alignment consumed50 actions despite a usable9deg
        # residual. No source object, native goal or grasp flag is changed.
        m,_,_,_=self.model();body=self.guard()[0][self.name]
        axis=np.asarray(body['mat'])@np.asarray(self.objects[self.name]['grasp_axis_local'])
        current=m['rotation'][:,1];angle=wrap(math.atan2(axis[1],axis[0])-math.atan2(current[1],current[0]))
        if angle>math.pi/2:angle-=math.pi
        if angle<-math.pi/2:angle+=math.pi
        self.operations.append(dict(operation='retain_actual_empty_hand_without_private_yaw_zeroing',
                                    measured_opposed_axis_deviation_rad=angle))
        body=self.guard()[0][self.name];point=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(self.objects[self.name]['grasp_point_local'])
        self.move([*point[:2],height],tolerance=.002)
        self.a.stage='E15-measured-real-pad-descent-'+self.name
        for _ in range(120):
            geometry=self.a.finger_geometry('right')
            if geometry.get('source')!='actual_collision_mesh_current_body_pose':raise RuntimeError('Actual T finger mesh required')
            lowest=float(geometry['lowest_z_task_m'])
            if lowest<=.8035:
                if lowest<.800001:raise RuntimeError('Actual T finger crossed original table')
                break
            self.step('DOWN',delta=np.array([0.,0.,-min(.003,lowest-.803)]))
        else:raise RuntimeError('Measured T pad descent exhausted')
        self.a.stage='E15-real-bilateral-GRASP-'+self.name
        for _ in range(3):
            self.a.act('STILL','GRASP');state,contacts=self.guard()
            if state[self.name]['grasp'][1]and all(frozenset((self.name,'right_finger'+str(i)))in contacts for i in(1,2)):
                self.carrying=True;break
        else:raise RuntimeError('Actual T lacks bilateral grasp within original three attempts')
        self.a.carried_payload=(self.name,'right');origin=self.a.tip('right').copy()
        for _ in range(20):
            remaining=.020-float(self.a.tip('right')[2]-origin[2])
            if remaining<=.001:return
            self.step('UP',delta=np.array([0.,0.,min(.002,max(.0005,remaining))]))
        raise RuntimeError('Actual T short lift failed')

    def finish(self):
        self.guard();m,_,_,_=self.model();sign=1. if m['q'][6]>0 else-1.
        self.a.stage='E15-measured-held-half-turn-'+self.name
        for _ in range(110):
            body=self.guard()[0][self.name];r=np.asarray(body['mat']);yaw=math.atan2(r[1,0],r[0,0]);remaining=wrap(self.goal['yaw']-yaw)
            if abs(remaining)<=math.radians(6):break
            directed=remaining if remaining*sign>=0 else remaining+sign*2*math.pi
            if abs(directed)>math.radians(200):raise RuntimeError('Actual T selected winding exceeds reviewed half-turn')
            degrees=sign*min(4.,max(.5,abs(math.degrees(directed))))
            self.step('ROTATE_CCW'if sign>0 else'ROTATE_CW',degrees=degrees)
            after=np.asarray(self.guard()[0][self.name]['mat']);advanced=wrap(math.atan2(after[1,0],after[0,0])-yaw)
            if advanced*sign<math.radians(.01):raise RuntimeError('Actual T rotation failed to advance')
        else:raise RuntimeError('Actual T half-turn exhausted')
        self.a.stage='E15-measured-original-XY-return-'+self.name
        for _ in range(40):
            body=self.guard()[0][self.name];error=np.asarray(self.zone['xy'])-np.asarray(body['pos'])[:2]
            if np.max(np.abs(error))<=.007:break
            axis=int(np.argmax(np.abs(error)));delta=np.zeros(3);delta[axis]=math.copysign(min(.003,abs(float(error[axis]))),error[axis])
            self.step((('FWD','BACK'),('LEFT','RIGHT'))[axis][int(delta[axis]<0)],delta=delta)
        else:raise RuntimeError('Actual T original XY return exhausted')
        for _ in range(30):
            _,_,_,target=self.model();gap=min(float(o['points'][:,2].min())for o in target)-float(self.zone.get('surface_z',.8))
            if gap<=.005:break
            self.step('DOWN',delta=np.array([0.,0.,-min(.002,gap-.004)]))
        else:raise RuntimeError('Actual T release height unreachable')
        self.a.carried_payload=None;self.carrying=False;self.a.release_generated('right')
        for _ in range(10):self.step('UP',delta=np.array([0.,0.,.002]))
        state,contacts=self.guard();body=state[self.name];r=np.asarray(body['mat']);error=wrap(math.atan2(r[1,0],r[0,0])-self.goal['yaw'])
        if(any(body['grasp'])or frozenset((self.name,'table'))not in contacts
                or np.linalg.norm(np.asarray(body['pos'])[:2]-self.zone['xy'])>POSITION_TOLERANCE_M
                or abs(error)>math.radians(ANGLE_TOLERANCE_DEG)):
            raise RuntimeError('Actual T failed unchanged native position/yaw/support goal')
        return dict(actor=self.name,actual_position_task_m=np.asarray(body['pos']).tolist(),original_yaw_error_rad=error,
                    public_actions=self.c.steps-self.start,real_released_table_support=True)


def run_segment(a,segment,parameters):
    cp=getattr(a,'_engineering_resume_checkpoint',{})
    if(segment!='e15_b_complete_blue_from95'or parameters!={}or a.scene.spec.get('seed')!=4201
            or(cp.get('source',{}).get('steps'),cp.get('source',{}).get('physics_ticks'))!=(95,9503)
            or cp.get('diagnostic_only')is not True or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Admitted original E15B native95/9503 red-released boundary required')
    reference=MeasuredT(a,'blue_t');reference.acquire();result=reference.finish()
    return dict(local_completed=True,operations=reference.operations,actions=a.c.steps-reference.start,
                original_blue_result=result,full_task_completed=False)


def solve(a):
    if getattr(a,'_engineering_resume_checkpoint',None):raise ValueError('Fresh source-initial full E15B required')
    operations=[]
    for name in('red_t','blue_t'):
        reference=MeasuredT(a,name);reference.acquire();operations.append(reference.finish())
    for _ in range(5):a.act()
    score=a.c.evaluator.result()
    if not score['success']:raise RuntimeError('Measured original E15B full source-initial native evaluator failed')
    a.note('final')
    return score
