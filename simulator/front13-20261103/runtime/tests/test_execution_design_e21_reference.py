"""Geometry and measured guards for E21 reference; not native acceptance."""
import ast,copy,hashlib,json,re
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3,REVISION_V2
from videoicl_isaaclab.execution_design_e21_reference import grasp_spec,release_height,verify_before_release,verify_pickup_ik,PLATE_SHA
from videoicl_isaaclab.realworld_scenes import load


def author(tmp_path,variant='A',seed=4201,condition='I'):
    binding=json.loads((Path(__file__).parents[1]/'configs/realworld_full50_bindings.json').read_text());binding['execution_design']=dict(revision=REVISION_V3,condition=condition)
    p=tmp_path/'binding.json';p.write_text(json.dumps(binding));spec=load('E21',variant,seed,p,verify_files=False)
    state={o['id']:dict(pos=np.array([*o['xy'],o['bottom']+o['size'][2]]),mat=np.eye(3),grasp=[False,False])for o in spec['objects']};contacts=set();tip=np.array([.0515,.1605,.824])
    fingers=[dict(body_origin_task_m=[.05,y,.87])for y in (.14,.18)]
    geometry=dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=.815,fingers=fingers)
    a=SimpleNamespace(scene=SimpleNamespace(spec=spec,embodiment=SimpleNamespace(name='franka')),c=SimpleNamespace(snapshot=lambda:(state,contacts)),out=tmp_path,_execution_design_reference_authorized=True,tip=lambda side:tip.copy(),tcp_rotation_task=lambda side:np.eye(3),finger_geometry=lambda side:geometry)
    a.floor_clear_tcp=lambda side,floor:floor+float(tip[2]-geometry['lowest_z_task_m'])
    return a,tip,geometry


@pytest.mark.parametrize('variant',['A','B','C'])
@pytest.mark.parametrize('seed',[4201,4202,4203])
@pytest.mark.parametrize('condition',['I','E'])
def test_private_edge_pinch_preserves_every_original_rule_and_world(tmp_path,variant,seed,condition):
    a,_,_=author(tmp_path,variant,seed,condition);before=copy.deepcopy(a.scene.spec)
    for obj in a.scene.spec['objects']:
        changed=grasp_spec(a,obj)
        if obj['id']=='tray':assert changed is obj
        else:
            assert changed['grasp_point_local']==[-.01,0,0] and changed['grasp_axis_local']==[0,1,0]
            assert {k:v for k,v in changed.items()if k not in ('grasp_point_local','grasp_axis_local')}==obj
    assert a.scene.spec==before


def test_reviewed_signed_section_has_both_plate_finger_contact_sides(tmp_path):
    a,_,_=author(tmp_path);obj=next(o for o in a.scene.spec['objects']if o['id']=='yellow_block')
    path=Path(__file__).parents[2]/'deployment/real-text300-20261030/asset_roots/VIC_FULL50_RIGID_ASSETS'/obj['source_asset']['relative_path']
    raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==PLATE_SHA;text=raw.decode();assert 'xformOp:'not in text
    points=[np.asarray(ast.literal_eval(x))for x in re.findall(r'point3f\[\] points = (\[[^\n]+\])',text)]
    counts=[ast.literal_eval(x)for x in re.findall(r'int\[\] faceVertexCounts = (\[[^\n]+\])',text)]
    ids=[ast.literal_eval(x)for x in re.findall(r'int\[\] faceVertexIndices = (\[[^\n]+\])',text)]
    allp=np.concatenate(points);center=(allp.min(0)+allp.max(0))/2;scale=np.asarray(obj['size'])*2/np.ptp(allp,axis=0);cross=[]
    assert obj['source_asset']['source_rotation']==[1,0,0,0]
    for p,ns,ii in zip(points,counts,ids):
        p=(p-center)*scale;offset=0
        for n in ns:
            face=p[ii[offset:offset+n]];offset+=n
            for x,y in zip(face,np.roll(face,-1,axis=0)):
                if (x[0]+.01)*(y[0]+.01)<=0 and abs(y[0]-x[0])>1e-10:cross.append(x+(-.01-x[0])/(y[0]-x[0])*(y-x))
    np.testing.assert_allclose(np.min(cross,axis=0),[-.01,-.02,-.003],atol=1e-8)
    np.testing.assert_allclose(np.max(cross,axis=0),[-.01,.02,.003],atol=1e-8)


def configured_release(tmp_path):
    a,tip,fg=author(tmp_path);state,contacts=a.c.snapshot();goal=a.scene.spec['goals'][0];target=next(z for z in a.scene.spec['zones']if z['id']==goal['target']);name=goal['object'];tray=state['tray'];tray['pos'][2]=.82
    state[name]['pos']=tray['pos']+np.asarray(target['anchor_local_center']);state[name]['grasp']=[True,False]
    return a,tip,fg,state,contacts,name,target


def test_native_failure_finger_depth_cannot_be_released_below_rim(tmp_path):
    a,tip,fg,state,contacts,name,target=configured_release(tmp_path)
    with pytest.raises(RuntimeError,match='below rim'):verify_before_release(a,'left',name,target)
    z=release_height(a,'left',name,target,.824)
    assert z>=.861 and z<.90
    dz=z-tip[2];tip[2]+=dz;fg['lowest_z_task_m']+=dz;state[name]['pos'][2]+=dz
    verify_before_release(a,'left',name,target)
    assert state[name]['grasp']==[True,False]  # validator never manufactures release
    contacts.add(frozenset(('tray','left_finger1')))
    with pytest.raises(RuntimeError,match='contacting tray'):verify_before_release(a,'left',name,target)


def test_actual_cell_projection_and_grip_guard(tmp_path):
    a,tip,fg,state,contacts,name,target=configured_release(tmp_path);tip[2]=.88;fg['lowest_z_task_m']=.87
    state[name]['pos'][0]+=.06
    with pytest.raises(RuntimeError,match='projection'):verify_before_release(a,'left',name,target)
    state[name]['grasp']=[False,False]
    with pytest.raises(RuntimeError,match='grip lost'):verify_before_release(a,'left',name,target)


def test_actual_tray_pose_and_jaw_geometry_control_release(tmp_path):
    a,tip,fg,state,contacts,name,target=configured_release(tmp_path)
    first=release_height(a,'left',name,target,.824);state['tray']['pos'][2]+=.02
    assert release_height(a,'left',name,target,.824)==pytest.approx(first+.02)
    fg['fingers'][0]['body_origin_task_m'][2]+=.02
    with pytest.raises(RuntimeError,match='too tilted'):release_height(a,'left',name,target,.824)


def test_pickup_uses_actual_pose_and_rejects_unsafe_ik(tmp_path):
    a,_,_=author(tmp_path);seen=[]
    def good(a,c,side,targets):seen.extend(targets);return [dict(kinematically_reachable=True,minimum_joint_margin_rad=.2)]
    verify_pickup_ik(a,'right',[.14,-.1,.811],good)
    np.testing.assert_allclose(seen[0]['position'],[.14,-.1,.811])
    with pytest.raises(RuntimeError,match='joint margins'):verify_pickup_ik(a,'right',[.14,-.1,.811],lambda *x:[dict(kinematically_reachable=True,minimum_joint_margin_rad=.001)])


@pytest.mark.parametrize('authorized,revision,task',[(False,REVISION_V3,'E21'),(True,REVISION_V2,'E21'),(True,REVISION_V3,'E11')])
def test_formal_legacy_and_other_task_remain_unchanged(tmp_path,authorized,revision,task):
    a,_,_=author(tmp_path);a._execution_design_reference_authorized=authorized;a.scene.spec['execution_design']['revision']=revision;a.scene.spec['id']=task
    obj=a.scene.spec['objects'][1];assert grasp_spec(a,obj)is obj
    with pytest.raises(ValueError,match='explicit v3'):verify_pickup_ik(a,'left',[0,0,.8])


def test_unreviewed_gripper_cannot_reuse_panda_opening_envelope(tmp_path):
    a,tip,fg,state,contacts,name,target=configured_release(tmp_path);a.scene.embodiment.name='ur5_wsg'
    with pytest.raises(ValueError,match='Panda only'):release_height(a,'left',name,target,.824)


def transport_author(tmp_path):
    a,tip,fg,state,contacts,name,target=configured_release(tmp_path)
    tip[:]=[-.1,-.12,.88];state[name]['pos']=tip+[.01,0,-.01]
    fg['lowest_z_task_m']=tip[2]-.01
    contacts.update(frozenset((name,f'left_finger{i}'))for i in (1,2))
    a.stage='grasped-'+name;a.moves=[]
    def move(goals,tolerance):
        old=tip.copy();wanted=np.array(goals['left']);horizontal=np.linalg.norm(wanted[:2]-old[:2])>1e-8
        # Measured controller cross-axis drift, repeated in E21B. Only actual
        # public movement updates the fake physical state in this CPU fixture.
        tip[:]=wanted
        if horizontal:tip[2]-=.0007
        delta=tip-old;state[name]['pos']+=delta;fg['lowest_z_task_m']+=delta[2]
        a.moves.append(dict(horizontal=horizontal,tip=tip.copy(),requested=wanted.copy()))
    a.move_generated=move
    return a,tip,fg,state,contacts,name,target


def test_short_horizontal_segments_correct_accumulated_vertical_drift(tmp_path):
    from videoicl_isaaclab.execution_design_e21_reference import transport_above_rim
    a,tip,fg,state,contacts,name,target=transport_author(tmp_path);original=copy.deepcopy(a.scene.spec);tray=state['tray']['pos'].copy()
    transport_above_rim(a,'left',name,target,.88)
    assert a.scene.spec==original
    np.testing.assert_array_equal(state['tray']['pos'],tray)
    expected=tray+np.array(target['anchor_local_center']);np.testing.assert_allclose(state[name]['pos'][:2],expected[:2],atol=.002)
    horizontal=[i for i,x in enumerate(a.moves)if x['horizontal']]
    assert len(horizontal)>20
    assert all(i>0 and not a.moves[i-1]['horizontal']for i in horizontal)
    assert min(x['tip'][2]for x in a.moves)>.876
    assert state[name]['grasp']==[True,False]


@pytest.mark.parametrize('fault',['tray_contact','tray_moved','grip_loss','deep_drift'])
def test_transfer_stops_on_actual_unexpected_physics_without_faking_completion(tmp_path,fault):
    from videoicl_isaaclab.execution_design_e21_reference import transport_above_rim
    a,tip,fg,state,contacts,name,target=transport_author(tmp_path);base=a.move_generated
    def move(goals,tolerance):
        base(goals,tolerance)
        if a.moves[-1]['horizontal']:
            if fault=='tray_contact':contacts.add(frozenset(('tray','left_finger1')))
            elif fault=='tray_moved':state['tray']['pos'][0]+=.004
            elif fault=='grip_loss':state[name]['grasp']=[False,False]
            else:tip[2]-=.03;fg['lowest_z_task_m']-=.03;state[name]['pos'][2]-=.03
    a.move_generated=move
    with pytest.raises(RuntimeError,match='contact|moved|grip|clearance'):transport_above_rim(a,'left',name,target,.88)
    assert len(a.moves)==2


def test_transport_uses_actual_anchor_without_changing_source_cell(tmp_path):
    from videoicl_isaaclab.execution_design_e21_reference import transport_above_rim
    a,tip,fg,state,contacts,name,target=transport_author(tmp_path)
    state['tray']['pos'][:2]+=[-.015,.01];old=copy.deepcopy(target)
    transport_above_rim(a,'left',name,target,.88)
    np.testing.assert_allclose(state[name]['pos'][:2],(state['tray']['pos']+np.array(target['anchor_local_center']))[:2],atol=.002)
    assert target==old
