"""E02 v3 I/E engineering edge-offset pinch; source and stacking goals unchanged."""
from copy import deepcopy
import numpy as np
from .execution_design import REVISION_V3

SOURCE_SHA='fed57b9b0e69a5b8b98d75324ed6856c0cdb21ebc56c8f98cb372670255b61bb'


def grasp_spec(author,obj):
    spec=author.scene.spec;design=spec.get('execution_design',{})
    if not(getattr(author,'_execution_design_reference_authorized',False)
      and spec.get('id')=='E02' and design.get('revision')==REVISION_V3
      and design.get('condition')in ('I','E') and obj.get('id')in ('red','green','blue')):return obj
    if (obj.get('source_asset',{}).get('sha256')!=SOURCE_SHA
      or not np.allclose(obj.get('size',[]),[.02,.02,.003],atol=1e-10,rtol=0)
      or obj.get('grasp_axis_local')!=[0,1,0]):
        raise ValueError('E02 engineering near-edge pinch requires exact reviewed plate geometry')
    # The source plate spansX±20mm and retains its two realY-side edges at
    # thisX=-10mm cross-section. The finger may overhang; no geometry is added.
    # This reduces the I layout central plate TCP reach by10mm. Every pickup
    # still must establish actual bilateral contact/holding and a genuine lift.
    result=deepcopy(obj);result['grasp_point_local']=[-.010,0.,0.]
    return result
