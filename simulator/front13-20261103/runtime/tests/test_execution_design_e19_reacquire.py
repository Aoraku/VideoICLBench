from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as N
import ast,hashlib,json,re
import numpy as np
import pytest
from scipy.spatial import ConvexHull
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.realworld_tool_expert import ToolAuthor,ToolExecutionError,_axis_rotation
from videoicl_isaaclab.execution_design_segments_e19_e25 import run_segment
from videoicl_isaaclab import execution_design_e19_reacquire as candidate


def scene(tmp_path):
    binding=json.loads((Path(__file__).parents[1]/'configs/realworld_full50_bindings.json').read_text());binding['execution_design']={'revision':REVISION_V3,'condition':'I'}
    path=tmp_path/'binding.json';path.write_text(json.dumps(binding));return load('E19','C',4201,path,verify_files=False)


class PhysicalFixtureTool(ToolAuthor):
    """Only this fixture models physical responses; production never writes them."""
    def __init__(self,a,fault=None):
        self.a=a;self.c=a.c;self.spec=a.scene.spec;self.s=self.spec['semantic'];self.task='E19';self.variant='C'
        self.objects={o['id']:o for o in self.spec['objects']};self.operations=[];self.start=self.c.steps;self.limit=300
        self.min_mm=.5;self.max_mm=10.;self.min_deg=.5;self.max_deg=10.;self.fault=fault;self.calls=[];self.releases=0
        mouth=np.array([.06,.15,.9])+np.array(self.s['mouths']['water_bottle']['center_local'])
        self.state={'water_bottle':dict(pos=np.array([.06,.15,.9]),mat=np.eye(3),grasp=[False,False]),'cap_red':dict(pos=mouth+[.001,.001,.003],mat=_axis_rotation([1,0,0],np.deg2rad(13.65)),grasp=[False,False])}
        self.contacts={frozenset(('cap_red','water_bottle'))};self.tcp=self.state['cap_red']['pos']+[0,0,.075];self.jaw=np.array([0.,1.,0.]);self.released=False
    def ref(self,name):return dict(actor=name,**deepcopy(self.s['structural_grasps'][name]))
    def label(self,name):return self.objects[name].get('semantic_identity',self.objects[name].get('identity',name))
    def body_point(self,ref,local):return self.point({**ref,'local':local})
    def snapshot(self):return self.state,self.contacts
    def tip(self,side):return self.tcp.copy()
    def act(self,side=None,token='STILL',mm=1.,degrees=5.,follower=None):
        self.calls.append(token);self.c.steps+=1
        if token=='RELEASE':
            if self.state['cap_red']['grasp'][0]:
                self.releases+=1;self.state['cap_red']['grasp']=[False,False];self.released=True
                mouth=self.point({'actor':'water_bottle','local':self.s['mouths']['water_bottle']['center_local']})
                self.state['cap_red']['pos']=mouth+[0,0,-.003]
                self.state['cap_red']['mat']=np.eye(3)
                self.contacts=set()if self.fault=='missing_final_support'else{frozenset(('cap_red','water_bottle'))}
        elif token=='GRASP':
            if self.fault!='no_grip':
                self.state['cap_red']['grasp']=[True,False]
                self.contacts.update(frozenset(('cap_red','left_finger'+str(i)))for i in (1,2))
        elif token in ('FWD','BACK','LEFT','RIGHT','UP','DOWN'):
            axis,sign={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}[token]
            delta=np.eye(3)[axis]*sign*mm/1000;self.tcp+=delta
            if self.state['cap_red']['grasp'][0]:
                self.state['cap_red']['pos']+=delta
                self.contacts.discard(frozenset(('cap_red','water_bottle')))
                if self.fault=='lift_slip':self.state['cap_red']['grasp']=[False,False]
        elif token!='STILL':
            axis={'ROLL_LEFT':[1,0,0],'ROLL_RIGHT':[-1,0,0],'PITCH_UP':[0,1,0],'PITCH_DOWN':[0,-1,0],'ROTATE_CCW':[0,0,1],'ROTATE_CW':[0,0,-1]}[token]
            delta=_axis_rotation(axis,np.deg2rad(degrees));self.jaw=delta@self.jaw
            if self.state['cap_red']['grasp'][0]:self.state['cap_red']['mat']=delta@self.state['cap_red']['mat']
        if self.fault=='bottle_push':self.state['water_bottle']['pos'][0]+=.003
        elif self.fault=='finger_bottle_contact':self.contacts.add(frozenset(('water_bottle','left_finger1')))
    def geometry(self,side):
        return dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=float(self.tcp[2]-.006),
            fingers=[{'body_origin_task_m':(self.tcp+self.jaw*sign*.04).tolist()}for sign in (1,-1)])


def setup(tmp_path,monkeypatch,fault=None):
    a=N(scene=N(spec=scene(tmp_path),embodiment=N(name='franka')),c=N(steps=0),smooth=False,_execution_design_reference_authorized=True,
        control_report={'engineering_reference_only':True},out=tmp_path,carried_payload=None)
    t=PhysicalFixtureTool(a,fault);a.finger_geometry=t.geometry
    robot=N(find_joints=lambda pattern:([0,1],['panda_finger_joint1','panda_finger_joint2']),data=N(joint_vel=np.array([[-.0526,.0693]])))
    a.scene.robots={'left':robot}
    monkeypatch.setattr(candidate,'StructuralAuthor',lambda author:t)
    p=dict(side='left',grasp_local_z_m=.0055,expected_source_pose=deepcopy(t.state['cap_red']),expected_bottle_pose=deepcopy(t.state['water_bottle']),action_limit=300)
    return a,t,p


def test_higher_point_is_inside_original_solid_cap_lid_geometry(tmp_path):
    spec=scene(tmp_path);obj=next(o for o in spec['objects']if o['id']=='cap_red')
    asset=Path(__file__).parents[2]/'deployment/real-text300-20261030/asset_roots/VIC_MECHANISM_ASSETS'/obj['source_asset']['relative_path'];raw=asset.read_bytes();assert hashlib.sha256(raw).hexdigest()==candidate.CAP_SHA
    meshes=[np.array(ast.literal_eval(x))for x in re.findall(r'point3f\[\] points = (\[[^\n]+\])',raw.decode())];allpoints=np.concatenate(meshes);center=(allpoints.min(0)+allpoints.max(0))/2;scale=np.array(obj['size'])*2/np.ptp(allpoints,axis=0)
    lid=(meshes[0]-center)*scale;hull=ConvexHull(lid)
    assert np.all(hull.equations[:,:3]@np.array([0,0,.0055])+hull.equations[:,3]<=1e-9)
    assert .003<.0055<obj['size'][2]and spec['semantic']['structural_grasps']['cap_red']['local']==[0,0,.003]


def test_real_reacquisition_lift_and_original_release_without_replaying_other_caps(tmp_path,monkeypatch):
    a,t,p=setup(tmp_path,monkeypatch);before=deepcopy(a.scene.spec);original_act=t.act
    result=run_segment(a,'e19_c_reacquire_red_water',p)
    assert result['local_completed']and set(result)=={'local_completed','operations','active_actions'}
    assert t.releases==1 and t.calls.count('GRASP')==1 and a.carried_payload is None
    assert a.scene.spec==before and t.act==original_act
    logs=[json.loads(x)for x in(tmp_path/'e19-c-terminal-reacquisition.private.jsonl').read_text().splitlines()]
    assert [r['phase']for r in logs]==['terminal_entry','actual_higher_point_reacquired','actual_red_cap_lifted','actual_reacquisition_placement_complete']
    assert logs[0]['higher_grasp_local']==[0.,0.,.0055]
    assert logs[1]['actual_cap_grasp']==[True,False]
    assert all(r['actual_bottle_pose']==logs[0]['actual_bottle_pose']for r in logs)
    assert not any(k in result for k in ('task_score_100','success','strict_success'))


@pytest.mark.parametrize('fault',['bottle_push','finger_bottle_contact','no_grip','lift_slip','missing_final_support'])
def test_first_physical_failure_stops_and_cannot_claim_local_placement(tmp_path,monkeypatch,fault):
    a,t,p=setup(tmp_path,monkeypatch,fault);original_act=t.act
    with pytest.raises(ToolExecutionError):run_segment(a,'e19_c_reacquire_red_water',p)
    assert t.act==original_act
    if fault in ('bottle_push','finger_bottle_contact'):assert len(t.calls)==1
    elif fault in ('no_grip','lift_slip'):assert t.releases==0
    else:assert t.releases==1


@pytest.mark.parametrize('fault',['source','jaw','offset','held','support','pose'])
def test_wrong_source_or_terminal_context_rejects_before_public_action(tmp_path,monkeypatch,fault):
    a,t,p=setup(tmp_path,monkeypatch)
    if fault=='source':t.objects['cap_red']['source_asset']['sha256']='bad'
    elif fault=='jaw':a.scene.spec['semantic']['structural_grasps']['cap_red']['jaw_axis_local']=[1,0,0]
    elif fault=='offset':p['grasp_local_z_m']=.0085
    elif fault=='held':t.state['cap_red']['grasp'][0]=True
    elif fault=='support':t.contacts.clear()
    else:p['expected_source_pose']['pos'][0]+=.01
    with pytest.raises((ValueError,ToolExecutionError)):run_segment(a,'e19_c_reacquire_red_water',p)
    assert t.calls==[]


@pytest.mark.parametrize('mode',['C_red','C_yellow','A_red','formal_red'])
def test_full_source_ref_uses_only_validated_c_red_higher_point(tmp_path,monkeypatch,mode):
    from videoicl_isaaclab.realworld_structural_expert import StructuralAuthor
    a,t,p=setup(tmp_path,monkeypatch);t.grasps=t.s['structural_grasps'];before=deepcopy(t.spec)
    name='cap_red'
    if mode=='C_yellow':name='cap_yellow'
    elif mode=='A_red':t.spec['variant']='A';before=deepcopy(t.spec)
    elif mode=='formal_red':a.control_report['engineering_reference_only']=False
    result=StructuralAuthor.ref(t,name)
    if mode=='C_red':
        assert result['local']==[0.,0.,.0055]and result['jaw_axis_local']==[0,1,0]
        assert candidate.higher_red_cap_ref(t,result)==result
    else:assert result['local']==t.grasps[name]['local']
    assert t.spec==before
