import ast,hashlib,json,re
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3,REVISION_V2
from videoicl_isaaclab.execution_design_e25_reference import grasp_spec,TAIL_GRASPS
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.author_orientation import _quaternion_matrix


def scene(tmp_path,variant='A'):
    b=json.loads((Path(__file__).parents[1]/'configs/realworld_full50_bindings.json').read_text());b['execution_design']={'revision':REVISION_V3,'condition':'I'}
    p=tmp_path/'binding.json';p.write_text(json.dumps(b));return load('E25',variant,4201,p,verify_files=False)


@pytest.mark.parametrize('name',['knife','fork'])
def test_pinned_source_mesh_contains_reviewed_handle_section(name,tmp_path):
    spec=scene(tmp_path);obj=next(o for o in spec['objects']if o['id']==name);record=TAIL_GRASPS[name]
    source=Path(__file__).parents[2]/'deployment/real-text300-20261030/asset_roots/VIC_FULL50_RIGID_ASSETS'/obj['source_asset']['relative_path']
    raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==record['sha256']
    text=raw.decode();assert 'xformOp:'not in text  # source files have baked node transforms
    arrays=re.findall(r'point3f\[\] points = (\[[^\n]+\])',text)
    points=np.concatenate([np.array(ast.literal_eval(a))for a in arrays])@_quaternion_matrix(obj['source_asset']['source_rotation']).T
    points=(points-(points.min(0)+points.max(0))/2)*(np.asarray(obj['size'])*2/np.ptp(points,axis=0))
    band=points[np.abs(points[:,0]+.08)<.006]
    np.testing.assert_allclose(band.min(0),record['section_lower'],atol=1e-10)
    np.testing.assert_allclose(band.max(0),record['section_upper'],atol=1e-10)
    old=json.dumps(spec,sort_keys=True);a=SimpleNamespace(scene=SimpleNamespace(spec=spec),_execution_design_reference_authorized=True)
    new=grasp_spec(a,obj)
    assert new is not obj and new['grasp_point_local'][0]<obj['grasp_point_local'][0]-.02
    assert json.dumps(spec,sort_keys=True)==old
    assert {k:v for k,v in new.items()if k!='grasp_point_local'}=={k:v for k,v in obj.items()if k!='grasp_point_local'}


@pytest.mark.parametrize('change',[{'variant':'C'},{'id':'E27'},{'revision':REVISION_V2},{'authorized':False}])
def test_other_rules_revisions_and_production_keep_original_grasp(tmp_path,change):
    spec=scene(tmp_path);obj=next(o for o in spec['objects']if o['id']=='knife')
    spec.update({k:v for k,v in change.items()if k in ('id','variant')});spec['execution_design']['revision']=change.get('revision',REVISION_V3)
    a=SimpleNamespace(scene=SimpleNamespace(spec=spec),_execution_design_reference_authorized=change.get('authorized',True))
    assert grasp_spec(a,obj)is obj


def test_unknown_source_is_blocked_not_silently_regrasped(tmp_path):
    spec=scene(tmp_path);obj=next(o for o in spec['objects']if o['id']=='knife');obj['source_asset']['sha256']='unknown'
    a=SimpleNamespace(scene=SimpleNamespace(spec=spec),_execution_design_reference_authorized=True)
    with pytest.raises(ValueError,match='exact reviewed source'):grasp_spec(a,obj)


def test_endpoint_selection_and_actual_acquisition_consume_same_private_grasp():
    root=Path(__file__).parents[1]/'videoicl_isaaclab'
    for name,call in [('demonstration.py','grasp_spec(self, spec)'),('execution_design_generated_route.py','grasp_spec(author, obj)')]:
        tree=ast.parse((root/name).read_text());assert any(isinstance(n,ast.Call)and ast.unparse(n)==call for n in ast.walk(tree))


def test_receiver_pitch_preserves_pinch_line_and_conservative_actual_finger_floor(tmp_path):
    from videoicl_isaaclab.execution_design_e25_reference import receiver_pitch_candidate
    a=SimpleNamespace(scene=SimpleNamespace(spec=scene(tmp_path),embodiment=SimpleNamespace(name='franka')),
        _execution_design_reference_authorized=True,tip=lambda side:np.array([0,0,1.]),tcp_rotation_task=lambda side:np.diag([1.,-1.,-1.]),
        finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',fingers=[dict(aabb_min_task_m=[-.015,-.06,.99],aabb_max_task_m=[.015,.06,1.05])]))
    targets=[dict(position=[.15,.12,.805],rotation=np.diag([1.,-1.,-1.]))];before=repr(targets)
    chosen,rows=receiver_pitch_candidate(a,'left',targets)
    np.testing.assert_allclose(chosen[:,1],[0,-1,0],atol=1e-10)
    np.testing.assert_allclose(rows[0]['rotation'],chosen)
    assert rows[0]['position'][:2]==[.15,.12] and rows[0]['position'][2]>.810
    assert repr(targets)==before
    a.scene.spec['variant']='B'
    with pytest.raises(ValueError,match='E25A'):receiver_pitch_candidate(a,'left',targets)


def test_receiver_preparation_requires_actual_release_and_public_rotation(tmp_path):
    from videoicl_isaaclab.execution_design_e25_reference import prepare_receiver
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    spec=scene(tmp_path);R=np.diag([1.,-1.,-1.]);desired=_axis_rotation([0,-1,0],np.deg2rad(8))@R;tip=np.array([-.28,-.03,.92])
    bodies={o['id']:dict(mat=np.eye(3),grasp=[False,False])for o in spec['objects']};contacts={frozenset(('spoon','table'))};actions=[]
    a=SimpleNamespace(scene=SimpleNamespace(spec=spec),control_report={'engineering_reference_only':True},smooth=False,
        _execution_design_reference_authorized=True,c=SimpleNamespace(snapshot=lambda:(bodies,contacts)),tip=lambda side:tip.copy(),
        tcp_rotation_task=lambda side:R.copy(),finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=float(tip[2]-.01)))
    def move(goals):tip[:]=goals['left']
    def act(left,right,rotation_deg):
        nonlocal R
        assert right=='STILL';actions.append(left);axis={'PITCH_UP':[0,1,0],'PITCH_DOWN':[0,-1,0]}[left];R=_axis_rotation(axis,np.deg2rad(rotation_deg))@R
    a.scene.robots={'left':SimpleNamespace(data=SimpleNamespace(joint_pos=np.zeros((1,7)),soft_joint_pos_limits=np.array([[[-3.,3.]]*7])),find_joints=lambda pattern:(list(range(7)),[f'q{i}'for i in range(7)]))}
    a.c.action_feedback=lambda:{'control_feedback':{'left':{'status':'reached','joint_limit_names':[]}}}
    a.move_generated=move;a.act=act;goal={'_e07_after_relay':{},'_e25_receiver_rotation_task':desired.tolist()}
    prepare_receiver(a,'left','spoon',goal,.89,[-.28,-.03]);assert actions==['PITCH_DOWN','PITCH_DOWN']
    assert a.control_report['e25_receiver_orientation']['actual_error_rad']<.001
    bodies['spoon']['grasp']=[True,False]
    with pytest.raises(RuntimeError,match='released supported'):prepare_receiver(a,'left','spoon',goal,.89,[-.28,-.03])
    bodies['spoon']['grasp']=[False,False];contacts.clear()
    with pytest.raises(RuntimeError,match='released supported'):prepare_receiver(a,'left','spoon',goal,.89,[-.28,-.03])


def source_palm_author(tmp_path):
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    s=scene(tmp_path);r=_axis_rotation([1,0,0],np.deg2rad(8))@np.diag([1.,-1.,-1.]);tip=np.array([-.19,-.3,.90])
    state={o['id']:dict(mat=np.eye(3),grasp=[False,False])for o in s['objects']};contacts={frozenset(('knife','table'))};actions=[]
    a=SimpleNamespace(scene=SimpleNamespace(spec=s,embodiment=SimpleNamespace(name='franka')),
        _execution_design_reference_authorized=True,smooth=False,control_report={'engineering_reference_only':True},
        c=SimpleNamespace(snapshot=lambda:(state,contacts),action_feedback=lambda:{'control_feedback':{'right':{'status':'reached','joint_limit_names':[]}}}),
        tip=lambda side:tip.copy(),tcp_rotation_task=lambda side:r.copy(),actions=actions)
    a.finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=float(tip[2]-.025),
        fingers=[dict(body_origin_task_m=(tip+r[:,1]*.04).tolist()),dict(body_origin_task_m=(tip-r[:,1]*.04).tolist())])
    def move(goals):tip[:]=goals['right'];actions.append('move')
    def act(left,right,rotation_deg):
        nonlocal r
        assert left=='STILL';actions.append(right)
        axes={'ROLL_LEFT':[1,0,0],'ROLL_RIGHT':[-1,0,0],'PITCH_UP':[0,1,0],'PITCH_DOWN':[0,-1,0],'ROTATE_CCW':[0,0,1],'ROTATE_CW':[0,0,-1]}
        r=_axis_rotation(axes[right],np.deg2rad(rotation_deg))@r
    a.move_generated=move;a.act=act
    return a,state,contacts


def test_source_knife_levels_actual_empty_palm_without_moving_source_or_receiver(tmp_path):
    from videoicl_isaaclab.execution_design_e25_reference import prepare_source_palm
    a,state,contacts=source_palm_author(tmp_path);before=json.dumps(a.scene.spec,sort_keys=True);original=state['knife']['mat'].copy()
    prepare_source_palm(a,'right','knife',{})
    assert a.actions==['move','ROLL_RIGHT','ROLL_RIGHT']
    np.testing.assert_allclose(a.tcp_rotation_task('right')[2],[0,0,-1],atol=1e-8)
    np.testing.assert_array_equal(state['knife']['mat'],original)
    assert json.dumps(a.scene.spec,sort_keys=True)==before and not a.control_report['e25_source_palm']['native_grasp_validated']
    a.actions.clear();prepare_source_palm(a,'left','knife',{'_e07_after_relay':{}});assert not a.actions


@pytest.mark.parametrize('change',['spoon','fork'])
def test_source_knife_candidate_leaves_other_rules_and_members_untouched(tmp_path,change):
    from videoicl_isaaclab.execution_design_e25_reference import prepare_source_palm
    a,state,contacts=source_palm_author(tmp_path)
    name='knife'
    if change in ('B','C'):a.scene.spec['variant']=change
    else:name=change
    prepare_source_palm(a,'right',name,{})
    assert not a.actions


@pytest.mark.parametrize('change',['held','missing_support','source','production','legacy','blocked'])
def test_source_knife_guards_do_not_forge_support_or_ignore_controller_rejection(tmp_path,change):
    from videoicl_isaaclab.execution_design_e25_reference import prepare_source_palm
    a,state,contacts=source_palm_author(tmp_path)
    if change=='held':state['knife']['grasp']=[False,True]
    elif change=='missing_support':contacts.clear()
    elif change=='source':next(o for o in a.scene.spec['objects']if o['id']=='knife')['source_asset']['sha256']='bad'
    elif change=='production':a._execution_design_reference_authorized=False
    elif change=='legacy':a.scene.spec['execution_design']['revision']=REVISION_V2
    else:a.c.action_feedback=lambda:{'control_feedback':{'right':{'status':'blocked','joint_limit_names':[]}}}
    with pytest.raises((RuntimeError,ValueError)):prepare_source_palm(a,'right','knife',{})
    if change!='blocked':assert not a.actions


def test_c_source_knife_levels_only_empty_palm_preserving_original_grasp_and_goal(tmp_path):
    from videoicl_isaaclab.execution_design_e25_reference import prepare_source_palm
    a,state,contacts=source_palm_author(tmp_path);a.scene.spec=scene(tmp_path,'C')
    before=json.dumps(a.scene.spec,sort_keys=True)
    obj=next(o for o in a.scene.spec['objects']if o['id']=='knife')
    assert grasp_spec(a,obj)is obj
    prepare_source_palm(a,'right','knife',{})
    assert a.actions==['move','ROLL_RIGHT','ROLL_RIGHT']
    assert json.dumps(a.scene.spec,sort_keys=True)==before
    np.testing.assert_array_equal(state['knife']['mat'],np.eye(3))
    a.actions.clear();obj['source_asset']['sha256']='unreviewed'
    with pytest.raises(ValueError,match='exact reviewed knife'):prepare_source_palm(a,'right','knife',{})
    assert not a.actions


@pytest.mark.parametrize('name',['spoon'])
def test_c_other_sources_keep_existing_reference(tmp_path,name):
    from videoicl_isaaclab.execution_design_e25_reference import prepare_source_palm
    a,state,contacts=source_palm_author(tmp_path);a.scene.spec=scene(tmp_path,'C')
    prepare_source_palm(a,'right',name,{})
    assert not a.actions


def test_c_source_fork_reuses_empty_palm_preparation_without_grasp_or_goal_change(tmp_path):
    from videoicl_isaaclab.execution_design_e25_reference import prepare_source_palm
    a,state,contacts=source_palm_author(tmp_path);a.scene.spec=scene(tmp_path,'C');contacts.add(frozenset(('fork','table')))
    before=json.dumps(a.scene.spec,sort_keys=True);obj=next(o for o in a.scene.spec['objects']if o['id']=='fork')
    assert grasp_spec(a,obj)is obj
    prepare_source_palm(a,'right','fork',{})
    assert a.actions==['move','ROLL_RIGHT','ROLL_RIGHT']and json.dumps(a.scene.spec,sort_keys=True)==before
    np.testing.assert_array_equal(state['fork']['mat'],np.eye(3))
    a.actions.clear();prepare_source_palm(a,'left','fork',{'_e07_after_relay':{}});assert a.actions==[]
    obj['source_asset']['sha256']='unreviewed'
    with pytest.raises(ValueError,match='exact reviewed fork'):prepare_source_palm(a,'right','fork',{})
    assert a.actions==[]


@pytest.mark.parametrize('failure',[None,'stalled','blocked','joint_limit'])
def test_receiver_partial_rotations_use_actual_progress_not_fixed_40_cutoff(tmp_path,failure):
    from videoicl_isaaclab.execution_design_e25_reference import prepare_receiver
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    spec=scene(tmp_path);base=np.diag([1.,-1.,-1.]);desired=_axis_rotation([0,-1,0],np.deg2rad(8))@base
    R=_axis_rotation([1,0,0],np.deg2rad(-45))@desired;tip=np.array([-.28,-.03,.92]);actions=[]
    bodies={o['id']:dict(mat=np.eye(3),grasp=[False,False])for o in spec['objects']};contacts={frozenset(('knife','table'))}
    q=np.zeros((1,7));limits=np.array([[[-3.,3.]]*7]);feedback={'status':'partial','joint_limit_names':[]}
    robot=SimpleNamespace(data=SimpleNamespace(joint_pos=q,soft_joint_pos_limits=limits),find_joints=lambda p:(list(range(7)),[f'q{i}'for i in range(7)]))
    a=SimpleNamespace(scene=SimpleNamespace(spec=spec,robots={'left':robot}),control_report={'engineering_reference_only':True},smooth=False,out=tmp_path,
        _execution_design_reference_authorized=True,c=SimpleNamespace(snapshot=lambda:(bodies,contacts),action_feedback=lambda:{'control_feedback':{'left':feedback}}),
        tip=lambda side:tip.copy(),tcp_rotation_task=lambda side:R.copy(),finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=.90))
    def move(goals):tip[:]=goals['left']
    def act(left,right,rotation_deg):
        nonlocal R
        assert right=='STILL';actions.append(left)
        if failure=='stalled':return
        if failure=='blocked':feedback['status']='blocked'
        if failure=='joint_limit':q[0,0]=2.99
        axis={'ROLL_LEFT':[1,0,0],'ROLL_RIGHT':[-1,0,0],'PITCH_UP':[0,1,0],'PITCH_DOWN':[0,-1,0],'ROTATE_CCW':[0,0,1],'ROTATE_CW':[0,0,-1]}[left]
        R=_axis_rotation(axis,np.deg2rad(rotation_deg)*.25)@R
    a.move_generated=move;a.act=act;goal={'_e07_after_relay':{},'_e25_receiver_rotation_task':desired.tolist()}
    if failure:
        with pytest.raises(RuntimeError):prepare_receiver(a,'left','knife',goal,.89,[-.28,-.03])
        assert len(actions)<15
    else:
        before=json.dumps(spec,sort_keys=True);prepare_receiver(a,'left','knife',goal,.89,[-.28,-.03])
        assert 40<len(actions)<160 and a.control_report['e25_receiver_orientation']['actual_error_rad']<np.deg2rad(.75)
        assert json.dumps(spec,sort_keys=True)==before and not a.control_report['e25_receiver_orientation']['native_grasp_verified']
