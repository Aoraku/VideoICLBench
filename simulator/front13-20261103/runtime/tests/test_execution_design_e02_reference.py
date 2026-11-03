"""Reviewed plate grasp geometry only; native reach and grip remain unverified."""
import ast,hashlib,json,re
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3,REVISION_V2
from videoicl_isaaclab.execution_design_e02_reference import grasp_spec,SOURCE_SHA
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.author_orientation import _quaternion_matrix


def scene(tmp_path,variant='A',condition='I'):
    b=json.loads((Path(__file__).parents[1]/'configs/realworld_full50_bindings.json').read_text())
    b['execution_design']={'revision':REVISION_V3,'condition':condition}
    p=tmp_path/'binding.json';p.write_text(json.dumps(b));return load('E02',variant,4201,p,verify_files=False)


def test_exact_native_source_has_both_real_side_walls_at_private_pinch(tmp_path):
    obj=scene(tmp_path)['objects'][0]
    source=Path(__file__).parents[2]/'deployment/real-text300-20261030/asset_roots/VIC_FULL50_RIGID_ASSETS'/obj['source_asset']['relative_path']
    raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_SHA
    text=raw.decode();assert 'xformOp:' not in text
    arrays=[np.array(ast.literal_eval(x)) for x in re.findall(r'point3f\[\] points = (\[[^\n]+\])',text)]
    counts=[ast.literal_eval(x) for x in re.findall(r'int\[\] faceVertexCounts = (\[[^\n]+\])',text)]
    indices=[ast.literal_eval(x) for x in re.findall(r'int\[\] faceVertexIndices = (\[[^\n]+\])',text)]
    rotation=_quaternion_matrix(obj['source_asset']['source_rotation']);world=np.concatenate(arrays)@rotation.T
    center=(world.min(0)+world.max(0))/2;scale=np.asarray(obj['size'])*2/np.ptp(world,axis=0)
    crosses=[]
    for points,ns,ids in zip(arrays,counts,indices):
        points=(points@rotation.T-center)*scale;offset=0
        for n in ns:
            face=points[ids[offset:offset+n]];offset+=n
            for a,b in zip(face,np.roll(face,-1,axis=0)):
                if (a[0]+.01)*(b[0]+.01)<=0 and abs(b[0]-a[0])>1e-10:
                    crosses.append(a+(-.01-a[0])/(b[0]-a[0])*(b-a))
    cross=np.asarray(crosses);assert len(cross)>0
    np.testing.assert_allclose(cross.min(0),[-.01,-.02,-.003],atol=1e-8)
    np.testing.assert_allclose(cross.max(0),[-.01,.02,.003],atol=1e-8)
    # Both finger contact bands still contain actual plate side surface.
    for sign in (-1,1):assert np.any(np.abs(cross[:,1]-sign*.02)<1e-8)


@pytest.mark.parametrize('variant',['A','B','C'])
@pytest.mark.parametrize('condition',['I','E'])
def test_private_grasp_changes_no_source_geometry_goal_or_rule(tmp_path,variant,condition):
    spec=scene(tmp_path,variant,condition);original=json.dumps(spec,sort_keys=True)
    author=SimpleNamespace(scene=SimpleNamespace(spec=spec),_execution_design_reference_authorized=True)
    for obj in spec['objects']:
        changed=grasp_spec(author,obj)
        assert changed['grasp_point_local']==[-.01,0,0]
        assert {k:v for k,v in changed.items()if k!='grasp_point_local'}=={k:v for k,v in obj.items()if k!='grasp_point_local'}
        assert changed is not obj
    assert json.dumps(spec,sort_keys=True)==original


@pytest.mark.parametrize('condition,revision,authorized',[('R',REVISION_V3,True),('I',REVISION_V2,True),('I',REVISION_V3,False)])
def test_old_and_formal_routes_are_unchanged(tmp_path,condition,revision,authorized):
    spec=scene(tmp_path);spec['execution_design'].update(condition=condition,revision=revision)
    author=SimpleNamespace(scene=SimpleNamespace(spec=spec),_execution_design_reference_authorized=authorized)
    for obj in spec['objects']:assert grasp_spec(author,obj)is obj


def test_unknown_geometry_is_not_silently_used(tmp_path):
    spec=scene(tmp_path);obj=spec['objects'][0];obj['source_asset']['sha256']='unknown'
    author=SimpleNamespace(scene=SimpleNamespace(spec=spec),_execution_design_reference_authorized=True)
    with pytest.raises(ValueError,match='exact reviewed'):grasp_spec(author,obj)
