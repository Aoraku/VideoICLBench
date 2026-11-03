"""Candidate geometry checks; live grasp success still needs native evidence."""
from copy import deepcopy
import pytest
from videoicl_isaaclab.execution_design_reference_grasps import HEEL_BANDS, e08_engineering_heel_grasps


def case():
    objects=[dict(id=n, source_asset=dict(sha256=v[0],source_rotation=[.5,.5,.5,.5]),
                  size=[.13,v[1],.051902870300350894]) for n,v in HEEL_BANDS.items()]
    spec=dict(id='E08',execution_design=dict(revision='embodied50-execution-v3-20261102'),objects=objects)
    grasps={n:dict(local=[-.1,0,-.005],jaw_axis_local=[0,1,0])for n in HEEL_BANDS}
    return spec,grasps


def test_centered_heel_has_two_sided_open_finger_clearance_and_preserves_task():
    spec,grasps=case();before=deepcopy((spec,grasps))
    result=e08_engineering_heel_grasps(spec,grasps)
    for name,(_,_,lo,hi)in HEEL_BANDS.items():
        y=result[name]['local'][1]
        assert lo-(y-.04)>.006 and (y+.04)-hi>.006
        assert y-lo==pytest.approx(hi-y)
        assert result[name]['local'][0]==-.11
        # Reviewed lower heel band: measured upright shoe body half-height
        # leaves >10mm table clearance for actual down-facing finger toes.
        toe=result[name]['local'][2]-.0095
        assert .8+.051902870300350894+toe>.810
        assert toe<-.02 and toe+.054>.01
    assert (spec,grasps)==before


@pytest.mark.parametrize('field',['asset','rotation','dimensions','grasp','revision'])
def test_refuses_stale_geometry_or_grasp(field):
    spec,grasps=case()
    if field=='asset':spec['objects'][0]['source_asset']['sha256']='changed'
    if field=='rotation':spec['objects'][0]['source_asset']['source_rotation']=[1,0,0,0]
    if field=='dimensions':spec['objects'][0]['size'][0]*=1.1
    if field=='grasp':grasps['left_shoe']['local'][0]=0
    if field=='revision':spec['execution_design']['revision']='old'
    with pytest.raises(ValueError):e08_engineering_heel_grasps(spec,grasps)
