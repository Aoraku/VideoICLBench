"""Measured-geometry/control checks, not native physical acceptance."""
import numpy as np
import pytest
from pathlib import Path
from videoicl_isaaclab.execution_design_e23_reference import branch_entry_geometry
from videoicl_isaaclab.realworld_scenes import load


@pytest.mark.parametrize('variant',list('ABC'))
def test_real_three_branch_corridors_are_collinear_and_cup_bottom_stays_at_tip(variant):
    spec=load('E23',variant,4201,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False)
    for branch in spec['semantic']['branches'].values():
        cup=spec['semantic']['cups']['red']
        height=np.linalg.norm(np.asarray(cup['rim_local'])-cup['bottom_local'])
        g=branch_entry_geometry(branch['base_local'],branch['tip_local'],height)
        tip=np.asarray(branch['tip_local'])
        for key in ('exterior','entry','target'):
            assert np.linalg.norm(np.cross(g[key]-tip,g['axis']))<1e-12
        assert np.dot(g['exterior']-g['entry'],g['axis'])>.08
        assert np.dot(g['entry']-tip,g['axis'])==pytest.approx(.03)
        assert np.dot(g['target']+g['axis']*height-tip,g['axis'])==pytest.approx(.008)


def test_entry_geometry_rejects_invalid_or_zero_length_native_geometry():
    for base,tip,height in (([0,0,0],[0,0,0],.088),([0,0,0],[0,0,1],float('nan')),([0,0,0],[0,0,1],0)):
        with pytest.raises(ValueError):branch_entry_geometry(base,tip,height)


def test_reference_dispatch_is_v3_only_and_does_not_claim_native_success(monkeypatch):
    from types import SimpleNamespace
    from videoicl_isaaclab.execution_design import build_task_contract,REVISION_V2
    from videoicl_isaaclab import execution_design_reference as ref
    from videoicl_isaaclab import execution_design_e23_reference as e23
    calls=[]
    monkeypatch.setattr(e23,'solve_e23_reference',lambda a:calls.append('new') or {'physics_success_not_asserted':True})
    monkeypatch.setattr(ref,'solve_structural',lambda a:calls.append('legacy') or {})
    for rev in (None,REVISION_V2):
        kw={} if rev is None else {'revision':rev}
        spec=build_task_contract('E23','A',4201,condition='I',**kw)
        spec['id']='E23';spec['variant']='A'
        author=SimpleNamespace(scene=SimpleNamespace(spec=spec),control_report={},c=SimpleNamespace(steps=0),smooth=False)
        result=ref.solve_execution_reference(author)
        assert result['native_validation_required'] and result['physics_success_not_asserted']
    assert calls==['new','legacy']


@pytest.mark.parametrize('control',['positive','wrong_rule','wrong_destination','not_released'])
def test_counterexamples_only_change_real_move_release_order_not_semantics(monkeypatch,control):
    from types import SimpleNamespace
    from copy import deepcopy
    from videoicl_isaaclab import execution_design_e23_reference as module
    from videoicl_isaaclab.execution_design_e23_geometry import BRANCHES
    semantic={'branches':{k:dict(ref={'actor':'tree'},**value)for k,value in BRANCHES.items()},
              'cups':{n:dict(axis_local=[0,0,1],bottom_local=[0,0,-.044],rim_local=[0,0,.044])for n in ('red','green','blue')}}
    before=deepcopy(semantic);log=[];held=set();released=set()
    class Policy:
        task='E23';index=0;variant='A';start=0
        def __init__(self,a):self.s=semantic;self.c=SimpleNamespace(steps=0);self.identity={n:n for n in ('red','green','blue')};self.operations=[]
        def body_point(self,ref,point):return np.asarray(point)+[0,0,.8]
        def pickup(self,name):log.append(('pickup',name));held.add(name);return {'actor':name},'right'
        def align_axis(self,*args):pass
        def stage(self,*args):pass
        def point(self,ref):return np.array([0,0,1.])
        def tip(self,side):return np.array([0,0,1.])
        def require_held(self,ref,side):assert ref['actor']in held
        def contact(self,name,support):return name in released
        def move_point(self,side,ref,target,guard):guard();log.append(('point',ref['actor'],np.asarray(target).copy()));self.c.steps+=1
        def move(self,*args):self.c.steps+=1
        def release(self,ref,side):log.append(('release',ref['actor']));held.remove(ref['actor']);released.add(ref['actor']);self.c.steps+=1
        def wait(self,*args):self.c.steps+=1
    monkeypatch.setattr(module,'StructuralAuthor',Policy)
    from videoicl_isaaclab import execution_design_e23_orientation
    monkeypatch.setattr(execution_design_e23_orientation,'align_cup_axis_incremental',lambda *args,**kwargs:None)
    from videoicl_isaaclab import execution_design_e23_clearance
    monkeypatch.setattr(execution_design_e23_clearance,'prepare_rotation_workspace',lambda *args:None)
    from videoicl_isaaclab.execution_design import REVISION_V3,source_sha256
    author=SimpleNamespace(scene=SimpleNamespace(spec={'execution_design':{'revision':REVISION_V3,'source_sha256':source_sha256(REVISION_V3)}}),control_report={'engineering_reference_only':True})
    result=module.solve_e23_reference(author)if control=='positive'else module.solve_e23_negative_reference(author,control)
    expected=['green','red','blue']if control=='wrong_rule'else['red','green','blue']
    assert [entry[1]for entry in log if entry[0]=='pickup']==expected
    assert semantic==before and result['physics_success_not_asserted']
    last_moves=[entry[2]for entry in log if entry[:2]==('point','blue')]
    branch=BRANCHES['0'];g=branch_entry_geometry(np.asarray(branch['base_local'])+[0,0,.8],np.asarray(branch['tip_local'])+[0,0,.8],.088)
    np.testing.assert_allclose(last_moves[-1],g['entry']if control=='wrong_destination'else g['target'])
    assert held==({'blue'}if control=='not_released'else set())
    assert len([entry for entry in log if entry[0]=='release'])==(2 if control=='not_released'else 3)
    if control!='positive':assert result['perturbation']['native_condition_observed']is None


@pytest.mark.parametrize('task',['E23','E24'])
@pytest.mark.parametrize('fault',['no_engineering','old_revision','bad_source'])
def test_private_negative_routes_reject_formal_or_unpinned_author_before_actions(task,fault):
    from types import SimpleNamespace
    from videoicl_isaaclab.execution_design import REVISION_V3,REVISION_V2,source_sha256
    from videoicl_isaaclab.execution_design_e24_reference import solve_e24_negative_reference
    from videoicl_isaaclab.execution_design_e23_reference import solve_e23_negative_reference
    design=dict(revision=REVISION_V3,source_sha256=source_sha256(REVISION_V3))
    if fault=='old_revision':design['revision']=REVISION_V2
    if fault=='bad_source':design['source_sha256']='changed'
    author=SimpleNamespace(scene=SimpleNamespace(spec={'execution_design':design}),control_report={'engineering_reference_only':fault!='no_engineering'})
    # A missing controller deliberately makes entering structural policy setup
    # fail loudly; scope must reject before accessing controller/physical state.
    with pytest.raises(ValueError):
        (solve_e23_negative_reference if task=='E23' else solve_e24_negative_reference)(author,'wrong_rule')
