import ast,hashlib,json,re
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e25_b_reference import SECTIONS,candidate_grasp,rotation_candidates
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.author_orientation import _quaternion_matrix


def author(tmp_path):
    binding=json.loads((Path(__file__).parents[1]/'configs/realworld_full50_bindings.json').read_text())
    binding['execution_design']={'revision':REVISION_V3,'condition':'I'};p=tmp_path/'binding.json';p.write_text(json.dumps(binding))
    spec=load('E25','B',4201,p,verify_files=False)
    state={'spoon':dict(mat=np.eye(3),grasp=[True,False])};contacts={frozenset(('spoon','left_finger1')),frozenset(('spoon','left_finger2'))}
    return SimpleNamespace(scene=SimpleNamespace(spec=spec,embodiment=SimpleNamespace(name='franka')),
       _execution_design_reference_authorized=True,control_report={'engineering_reference_only':True},smooth=False,
       c=SimpleNamespace(snapshot=lambda:(state,contacts)),state=state,contacts=contacts,
       tip=lambda side:np.array([-.2,0,1.]),tcp_rotation_task=lambda side:np.diag([1.,-1.,-1.]))


@pytest.mark.parametrize('name',list(SECTIONS))
def test_cross_sections_are_exact_source_geometry_and_do_not_mutate_world(tmp_path,name):
    a=author(tmp_path);spec=a.scene.spec;obj=next(o for o in spec['objects']if o['id']==name)
    raw=(Path(__file__).parents[2]/'deployment/real-text300-20261030/asset_roots/VIC_FULL50_RIGID_ASSETS'/obj['source_asset']['relative_path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==SECTIONS[name]['sha256']
    points=np.concatenate([np.array(ast.literal_eval(x))for x in re.findall(r'point3f\[\] points = (\[[^\n]+\])',raw.decode())])@_quaternion_matrix(obj['source_asset']['source_rotation']).T
    points=(points-(points.min(0)+points.max(0))/2)*(np.array(obj['size'])*2/np.ptp(points,axis=0));band=points[abs(points[:,0]-.06)<.006]
    np.testing.assert_allclose(band.min(0),SECTIONS[name]['lower'],atol=1e-10)
    np.testing.assert_allclose(band.max(0),SECTIONS[name]['upper'],atol=1e-10)
    before=json.dumps(spec,sort_keys=True);candidate=candidate_grasp(a,obj)
    assert candidate['grasp_point_local'][0]>.059 and obj['grasp_point_local'][0]<-.05
    assert json.dumps(spec,sort_keys=True)==before
    assert {k:v for k,v in candidate.items()if k!='grasp_point_local'}=={k:v for k,v in obj.items()if k!='grasp_point_local'}


@pytest.mark.parametrize('change',['A','C','source','auth','smooth'])
def test_scope_rejects_other_rules_or_untrusted_engineering(tmp_path,change):
    a=author(tmp_path)
    if change in ('A','C'):a.scene.spec['variant']=change
    elif change=='source':a.scene.spec['execution_design']['source_sha256']='wrong'
    elif change=='auth':a._execution_design_reference_authorized=False
    else:a.smooth=True
    with pytest.raises(ValueError,match='private Panda'):candidate_grasp(a,a.scene.spec['objects'][0])


def test_winding_screens_both_arcs_but_never_claims_continuity_or_actuates(tmp_path):
    a=author(tmp_path);calls=[];before=repr(a.state)
    def probe(author,controller,side,targets):
        calls.append(targets)
        return [dict(kinematically_reachable=True,minimum_joint_margin_rad=.2,candidate_joints_rad=[float(i)*.1]*7)for i,_ in enumerate(targets)]
    result=rotation_candidates(a,'left','spoon',{'object':'spoon','target':'spoon_target','yaw':np.pi,'_e07_after_relay':{}},probe)
    assert len(calls)==2 and all(len(x)==9 for x in calls)
    assert result[0]['angle_rad']>0 and result[1]['angle_rad']<0
    assert all(x['coarse_ik_screen_passed']and not x['continuous_path_verified']and not x['native_passed']for x in result)
    assert repr(a.state)==before


def test_disconnected_joint_branches_are_rejected_even_if_all_endpoints_solve(tmp_path):
    a=author(tmp_path)
    def probe(author,controller,side,targets):
        return [dict(kinematically_reachable=True,minimum_joint_margin_rad=.2,candidate_joints_rad=[(-1.)**i]*7)for i,_ in enumerate(targets)]
    result=rotation_candidates(a,'left','spoon',{'object':'spoon','target':'spoon_target','yaw':np.pi,'_e07_after_relay':{}},probe)
    assert not any(x['coarse_ik_screen_passed']for x in result)
    a.contacts.remove(frozenset(('spoon','left_finger2')))
    with pytest.raises(RuntimeError,match='actual bilateral'):rotation_candidates(a,'left','spoon',{'object':'spoon','target':'spoon_target','yaw':np.pi,'_e07_after_relay':{}},probe)


def execution_author(tmp_path):
    a=author(tmp_path);a.state['spoon']['pos']=np.array([-.2,0,.99]);q=np.zeros((1,7));q[0,6]=1.;limits=np.array([[[-3.,3.]]*7]);rotation=np.diag([1.,-1.,-1.]);actions=[]
    robot=SimpleNamespace(data=SimpleNamespace(joint_pos=q,soft_joint_pos_limits=limits),find_joints=lambda pattern:(list(range(7)),[f'panda_joint{i}'for i in range(1,8)]))
    a.scene.robots={'left':robot};a.out=tmp_path;a.stage='grasped-spoon';a.feedback={'status':'reached','joint_limit_names':[]};a.c.action_feedback=lambda:{'control_feedback':{'left':a.feedback}}
    a.tcp_rotation_task=lambda side:rotation.copy();a.finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=.99)
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    def act(left,right,rotation_deg):
        nonlocal rotation
        assert right=='STILL';axis={'ROLL_LEFT':[1,0,0],'ROLL_RIGHT':[-1,0,0],'PITCH_UP':[0,1,0],'PITCH_DOWN':[0,-1,0],'ROTATE_CCW':[0,0,1],'ROTATE_CW':[0,0,-1]}[left]
        delta=_axis_rotation(axis,np.deg2rad(rotation_deg));a.state['spoon']['mat']=delta@a.state['spoon']['mat'];rotation=delta@rotation;q[0,6]-=axis[2]*np.deg2rad(rotation_deg);actions.append(left)
    a.act=act;a.actions=actions
    return a


def continuous_probe():
    calls=[]
    def probe(a,c,side,targets):
        sign=1 if not calls else -1;calls.append(targets);rows=[]
        for i,_ in enumerate(targets):
            q=np.zeros(7);q[6]=1-sign*np.pi*i/8
            rows.append(dict(kinematically_reachable=bool(abs(q[6])<2.95),minimum_joint_margin_rad=float(3-abs(q[6])),candidate_joints_rad=q.tolist()))
        return rows
    return probe


def test_public_winding_completes_original_orientation_without_state_injection(tmp_path):
    from videoicl_isaaclab.execution_design_e25_b_reference import rotate_payload
    a=execution_author(tmp_path);before=json.dumps(a.scene.spec,sort_keys=True)
    rotate_payload(a,'spoon','left',{'object':'spoon','target':'spoon_target','yaw':np.pi,'_e07_after_relay':{}},continuous_probe())
    assert len(a.actions)>40 and set(a.actions)=={'ROTATE_CCW'}
    np.testing.assert_allclose(a.state['spoon']['mat'],np.diag([-1.,-1.,1.]),atol=.021)
    assert a.state['spoon']['grasp']==[True,False] and json.dumps(a.scene.spec,sort_keys=True)==before
    assert not a.control_report['e25_b_windings'][0]['native_passed']
    records=[json.loads(x)for x in (tmp_path/'e25-b-public-winding.private.jsonl').read_text().splitlines()]
    assert sum(x['phase']=='public_step'for x in records)==len(a.actions)


@pytest.mark.parametrize('fault',['blocked','joint_limit','slip','floor','tcp_drift','collision'])
def test_public_winding_halts_after_actual_unsafe_step(tmp_path,fault):
    from videoicl_isaaclab.execution_design_e25_b_reference import rotate_payload
    a=execution_author(tmp_path);base=a.act
    def act(*args,**kwargs):
        base(*args,**kwargs)
        if fault=='blocked':a.feedback['status']='blocked'
        elif fault=='joint_limit':a.scene.robots['left'].data.joint_pos[0,6]=-2.99
        elif fault=='slip':a.state['spoon']['grasp']=[False,False]
        elif fault=='collision':a.contacts.add(frozenset(('spoon','tray')))
        elif fault=='floor':a.finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=.80)
        else:a.tip=lambda side:np.array([-.17,.01,1.])
    a.act=act
    with pytest.raises(RuntimeError,match='IK|limit|grip|clearance|envelope|collision'):
        rotate_payload(a,'spoon','left',{'object':'spoon','target':'spoon_target','yaw':np.pi,'_e07_after_relay':{}},continuous_probe())
    assert len(a.actions)==1


def test_receiver_candidate_uses_real_mesh_floor_and_preserves_targets(tmp_path):
    from videoicl_isaaclab.execution_design_e25_b_reference import receiver_candidate
    a=author(tmp_path);a.finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',fingers=[
        dict(body_origin_task_m=[-.2,y,1.04],aabb_min_task_m=[-.215,y-.01,.99],aabb_max_task_m=[-.185,y+.01,1.05])for y in (-.04,.04)])
    targets=[dict(position=[.17,.12,.805],rotation=np.diag([-1.,1.,-1.]).tolist())];before=repr(targets)
    chosen,rows=receiver_candidate(a,'left',targets,20)
    assert np.linalg.det(chosen)==pytest.approx(1.) and rows[0]['position'][2]>.81
    assert rows[0]['position'][:2]==targets[0]['position'][:2] and repr(targets)==before
    assert not np.allclose(rows[0]['rotation'],targets[0]['rotation'])


def test_dispatcher_and_source_leveling_use_private_b_grasp(tmp_path):
    from videoicl_isaaclab.execution_design_e25_reference import grasp_spec
    a=author(tmp_path);obj=next(o for o in a.scene.spec['objects']if o['id']=='spoon')
    assert grasp_spec(a,obj)['grasp_point_local'][0]>.059
    source=(Path(__file__).parents[1]/'videoicl_isaaclab/demonstration.py').read_text()
    tree=ast.parse(source)
    assert any(isinstance(n,ast.Call)and ast.unparse(n)=='rotate_transport_payload(self, name, side, goal)'for n in ast.walk(tree))
