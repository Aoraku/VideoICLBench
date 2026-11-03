from copy import deepcopy
import pytest
from videoicl_isaaclab.crease_motion import PASSIVE_GUIDE_POLICY,passive_guided_motion
from videoicl_isaaclab.realworld_semantic_checks import check_task


def observations():
    samples=[]
    for i in range(12):
        samples.append(dict(step=i,angle_deg=180.-8*i,hand_contact_force=0.,joint_pos=-i*.1,
            base_pos=[i*.001,0.,.8006],base_hand_contact_force=.8 if i<11 else 0.,
            fold_fixture_contact_force=.4 if i<11 else 0.,base_table_contact_force=.4,base_guide_contact_force=0.))
    return dict(released=True,stable=True,dihedral_angle_deg=92.,base_table_contact_force=.4,external_support_contacts=[],fold_samples=samples,
                native_passive_crease_fixture=dict(policy=PASSIVE_GUIDE_POLICY,schema='e44-passive-folding-rails-v3',final_fixture_contacts=[]))


def test_real_base_push_through_fixture_passes_without_inventing_leaf_hand_force():
    o=observations();assert passive_guided_motion(o['fold_samples'])
    r=check_task('E44','A',o)
    assert r['success']
    assert all(s['hand_contact_force']==0 for s in o['fold_samples'])


@pytest.mark.parametrize('missing',('hand','fixture','base_advance','support','fixture_declaration','final_external_support','not_released','missing_tick','non_joint_motion','base_guide_still_support'))
def test_passive_cause_and_true_release_fail_closed(missing):
    o=observations()
    for s in o['fold_samples']:
        if missing=='hand':s['base_hand_contact_force']=0.
        if missing=='fixture':s['fold_fixture_contact_force']=0.
        if missing=='base_advance':s['base_pos']=[0.,0.,.8006]
        if missing=='support':s['base_table_contact_force']=0.;s['base_guide_contact_force']=0.
        if missing=='non_joint_motion':s['joint_pos']=0.
    if missing=='fixture_declaration':o.pop('native_passive_crease_fixture')
    if missing=='final_external_support':o['external_support_contacts']=[['cardboard/fold','fixture0']]
    if missing=='not_released':o['fold_samples'][-1]['base_hand_contact_force']=.8
    if missing=='base_guide_still_support':o['native_passive_crease_fixture']['final_fixture_contacts']=[['cardboard/base','fixture2']]
    if missing=='missing_tick':del o['fold_samples'][4]
    assert not check_task('E44','A',o)['success']


def test_native_adapter_records_separate_real_forces_and_measured_base_motion():
    import math
    import numpy as np
    from videoicl_isaaclab.realworld_tool_evidence import ToolTaskEvaluator
    e=ToolTaskEvaluator.__new__(ToolTaskEvaluator);e.crease=dict(mechanism='cardboard',base=dict(body='base',normal_local=[0,0,1],contact_body='base'),fold=dict(body='fold',normal_local=[0,0,1],contact_body='fold'))
    e.semantic=dict(execution_design_fold_fixture=dict(schema='e44-passive-folding-rails-v3',fixture_contact_ids=['rail','bar'],rail_contact_ids=['rail'],base_guide_contact_ids=['bar']))
    e.fold_samples=[];e.crease_driven=False;e.extra_checks={}
    for sample in observations()['fold_samples']:
        t=math.radians(180-sample['angle_deg']);r=np.array([[math.cos(t),0,math.sin(t)],[0,1,0],[-math.sin(t),0,math.cos(t)]])
        e.body=lambda mechanism,name:(np.array(sample['base_pos']),np.eye(3)if name=='base'else r)
        e.joint=lambda c:sample['joint_pos'];e.steps=sample['step']
        e.hand_force=lambda name:sample['base_hand_contact_force']if name=='base'else 0.
        e.force=lambda a,b:sample['fold_fixture_contact_force']if(a,b)==('fold','rail')else sample['base_table_contact_force']if(a,b)==('base','table')else 0.
        e._crease_history()
    assert e.extra_checks['actual_crease_joint_contact_motion']
    assert all(s['hand_contact_force']==0 for s in e.fold_samples)
    assert e.fold_samples[4]['base_pos']==observations()['fold_samples'][4]['base_pos']
