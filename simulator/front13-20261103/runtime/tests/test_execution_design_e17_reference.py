from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e17_reference import measured_shelf_entry


def sample(tall=False):
    state={'green':dict(pos=np.array([-.2,-.08,.90]),mat=np.eye(3)),
           'stand':dict(pos=np.array([.17,.12,.8]),mat=np.eye(3)),
           'source':dict(pos=np.array([-.2,-.08,.824]),mat=np.eye(3))}
    objects={'green':dict(size=[.02,.02,.003]),'stand':dict(size=[.105,.105,.138],local_bounds_center=[0,0,.138]),'source':dict(size=[.07,.17,.018])}
    if tall:
        state['obstacle']=dict(pos=np.array([-.14,-.02,1.2]),mat=np.eye(3));objects['obstacle']=dict(size=[.015,.015,.03])
    point=np.array([-.2,-.08,.897])
    a=SimpleNamespace(task='E17',objects=objects,spec={'fixtures':[]})
    a.snapshot=lambda:(state,set());a.frame=lambda ref:(state[ref['actor']]['pos'],state[ref['actor']]['mat']);a.point=lambda ref:point.copy();a.tip=lambda side:point+[0,0,.012];a.bottom_local=lambda name:[0,0,-.003]
    a.a=SimpleNamespace(control_report={'engineering_reference_only':True},floor_clear_tcp=lambda side,floor:floor+.012,
                        finger_geometry=lambda side:{'fingers':[{'aabb_min_task_m':(point+[-.075,-.04,-.01]).tolist(),'aabb_max_task_m':(point+[.025,.04,.06]).tolist()}]})
    return a


def test_measured_finger_clearance_extends_entry_without_using_high_stand_as_crossing():
    a=sample();entry,height=measured_shelf_entry(a,'green','right','stand',[-.038,-.038,.00343],.15)
    assert entry==pytest.approx(-.195)
    assert height==pytest.approx(.98)
    assert a.a.control_report['e17_lower_entry_routes'][0]['actual_obstacle_top_m']==pytest.approx(.842)


def test_real_tall_obstacle_is_not_clamped_to_low_transport():
    a=sample(True);_,height=measured_shelf_entry(a,'green','right','stand',[-.038,-.038,.00343],.15)
    assert height>1.25


@pytest.mark.parametrize('variant',['A','B','C'])
def test_lower_reference_keeps_rule_members_and_uses_original_safe_quadrants(variant):
    from pathlib import Path
    from copy import deepcopy
    from videoicl_isaaclab.realworld_scenes import load
    from videoicl_isaaclab.execution_design_scenes import build_execution_scene
    from videoicl_isaaclab.execution_design_e17_reference import source_side_lower_slot
    spec=build_execution_scene(load('E17',variant,4201,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False),seed=4201)
    original=deepcopy(spec);region=next(r for r in spec['execution_design']['local_regions']if r['id']=='lower')
    a=SimpleNamespace(task='E17',geometry=spec['semantic']['structural_expert'],s=spec['semantic'])
    targets=[source_side_lower_slot(a,i,len(region['members']))for i in range(len(region['members']))]
    assert len({tuple(x)for x in targets})==len(targets)
    reviewed={tuple(v[:2])for v in a.geometry['shelf_positions'].values()}
    assert all(x[0]<0 and any(np.allclose(np.asarray(x[:2])-np.sign(x[:2])*.010,p)for p in reviewed)for x in targets)
    assert all(np.linalg.norm(np.abs(x[:2])+.020)<.102 for x in targets)
    assert set(region['members'])=={n for n,layer in spec['semantic']['required_layers'].items()if layer=='lower'}
    assert spec==original


def test_triangle_reference_requires_identical_mesh_and_preserves_source_and_other_grasps():
    from copy import deepcopy
    from videoicl_isaaclab.execution_design_e17_reference import measured_triangle_grasps
    sha='caae5e783af9afae7ee6c1933e42a1654d746635873c7a1bb221ea4554a70e7b'
    spec={'id':'E17','objects':[
        {'id':'triangle','size':[.02,.017320508,.003],'source_asset':{'sha256':sha}},
        {'id':'other','size':[.02,.017320508,.003],'source_asset':{'sha256':'different'}},
    ]}
    grasps={n:{'local':[0,0,0],'jaw_axis_local':[1,0,0],'hand':'right'}for n in ['triangle','other']}
    before=deepcopy((spec,grasps));out=measured_triangle_grasps(spec,grasps)
    assert out['triangle']['local']==pytest.approx([0,-.005773502666666666,0])
    assert out['triangle']['hand']=='right' and out['other']==grasps['other']
    assert (spec,grasps)==before
    spec['objects'][0]['size'][0]=.04
    with pytest.raises(RuntimeError,match='source scale'):
        measured_triangle_grasps(spec,grasps)


def ingress_sample():
    a=sample();state=a.snapshot()[0];state['stand']['pos']=np.array([.04,.05,.8])
    state['source']['pos']=np.array([-.20,-.12,.826]);a.objects['source']['size']=[.09,.17,.018]
    a.a.scene=SimpleNamespace(origin=np.zeros(3),world_to_task=lambda x:x,layout=SimpleNamespace(config={'table':dict(position=[0,0,.4],size=[.7,1.2,.8])}))
    point=a.point({});a.a.finger_geometry=lambda side:{'fingers':[dict(aabb_min_task_m=(point+[-.025,-.025,-.008]).tolist(),aabb_max_task_m=(point+[.025,.025,.050]).tolist())]}
    return a


def test_lower_ingress_avoids_actual_source_box_on_descent_and_horizontal_segments():
    from videoicl_isaaclab.execution_design_e17_reference import clear_lower_ingress
    a=ingress_sample();route=clear_lower_ingress(a,'green','right','stand',[-.17,-.038,.025],[-.038,-.038,.025])
    assert route[0][1]>.025
    assert route[1][1]==pytest.approx(route[0][1])
    np.testing.assert_allclose(route[-1],[-.038,-.038,.025])
    assert 'source' in a.a.control_report['e17_clear_ingress'][0]['avoided']


def test_lower_ingress_rejects_obstacle_across_full_low_corridor():
    from videoicl_isaaclab.execution_design_e17_reference import clear_lower_ingress
    a=ingress_sample();state=a.snapshot()[0]
    state['block']=dict(pos=np.array([.002,.06,.84]),mat=np.eye(3));a.objects['block']=dict(size=[.02,.08,.03])
    with pytest.raises(RuntimeError,match='blocked by measured solids'):
        clear_lower_ingress(a,'green','right','stand',[-.17,-.038,.025],[-.038,-.038,.025])


def test_dynamic_shelf_target_matches_real_component_hull_and_existing_region():
    """Native uses convexHull per component, not the visual concave floor."""
    import re
    from pathlib import Path
    from scipy.spatial import ConvexHull
    from videoicl_isaaclab.execution_design_e17_reference import collision_shelf_target
    from videoicl_isaaclab.realworld_scenes import load
    from videoicl_isaaclab.execution_design_scenes import build_execution_scene
    runtime=Path(__file__).parents[1]
    spec=build_execution_scene(load('E17','A',4201,runtime/'configs/realworld_full50_bindings.json',verify_files=False),seed=4201)
    a=SimpleNamespace(task='E17',objects={o['id']:o for o in spec['objects']})
    source=(runtime.parent/'deployment/real-text300-20261030/asset_roots/VIC_MECHANISM_ASSETS/two_tier_cake_stand_parts/visual.usda').read_text()
    for layer,index,xy in [('lower',0,[-.048,-.048]),('upper',1,[-.038,-.038])]:
        mesh=source.split('def Mesh "mesh_'+str(index)+'_component_'+str(index)+'"',1)[1]
        points=re.search(r'point3f\[\] points = \[(.*?)\]',mesh,re.S).group(1)
        vertices=np.array([tuple(map(float,p.split(',')))for p in re.findall(r'\(([^()]*)\)',points)])
        equation=ConvexHull(vertices).equations
        upward=equation[equation[:,2]>1e-10]
        hulltop=np.min(-(upward[:,0]*xy[0]+upward[:,1]*xy[1]+upward[:,3])/upward[:,2])
        original=[*xy,spec['semantic']['shelves'][layer]['center_local'][2]]
        target=collision_shelf_target(a,'stand',layer,original)
        lift=next(o for o in spec['objects']if o['id']=='stand').get('e17_stand_geometry',{}).get('upper_tier_lift_m',0.) if layer=='upper' else 0.
        assert target[2]==pytest.approx(hulltop+lift,abs=1e-9)
        assert original[2]==spec['semantic']['shelves'][layer]['center_local'][2]
        region=next(r for r in spec['execution_design']['local_regions']if r['id']==layer)
        assert 0 < target[2]-region['lower'][2] < .018
        assert target[2]+.006 < region['upper'][2]
    with pytest.raises(Exception,match='Unreviewed dynamic shelf collision asset'):
        a.objects['stand']['mechanical_asset']['sha256']='different'
        collision_shelf_target(a,'stand','lower',[-.048,-.048,.00343])


def test_measured_release_leaves_actual_finger_clearance_and_rejects_upper_collision():
    from videoicl_isaaclab.execution_design_e17_reference import measured_shelf_release
    a=sample();a.objects['stand'].update(dynamic_mechanical_asset=True,mechanical_asset={'sha256':'6cd3a9ec1b8664a9bca2ed034ac49808e7fbf8b82d2482b927c4e2fa727f5186'})
    target=measured_shelf_release(a,'green','right','stand','lower',[-.048,-.048,.00343])
    # Sample's real finger box extends ten millimetres below the payload.
    assert target[2]==pytest.approx(.016795216+.020)
    assert target[2]+.060 < .13299377-.010
    old=a.a.finger_geometry
    def tall(side):
        result=old(side);result['fingers'][0]['aabb_max_task_m'][2]+=.08;return result
    a.a.finger_geometry=tall
    with pytest.raises(Exception,match='do not fit'):
        measured_shelf_release(a,'green','right','stand','lower',[-.048,-.048,.00343])
