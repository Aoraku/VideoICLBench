"""Explicit one-millimetre card approximation for expedited engineering.

Requested practical task construction, not a source-exact350um certificate.
The exact original source IDs, XY outline, face, mass and task rule remain.
Fresh worlds only; no checkpoint migration or old-score relabelling.
"""
import math
from .execution_design_thin_cooking import SOURCES,TASKS

SCHEMA='engineering-practical-card-1mm-v1'
HALF_THICKNESS=.0005


def configure_spec(spec):
    if spec.get('id')not in TASKS:raise ValueError('Practical card task scope required')
    changed=[]
    for obj in spec['objects']:
        source=obj.get('source_asset',{})
        if source.get('relative_path')not in SOURCES:continue
        if source.get('sha256')!=SOURCES[source['relative_path']]:raise ValueError('Original card source SHA mismatch')
        if obj.get('engineering_practical_card'):raise ValueError('Fresh unadapted card required')
        old=float(obj['size'][2])
        if not math.isclose(old,.000175,abs_tol=1e-12):raise ValueError('Original350um source thickness required')
        obj['size']=list(obj['size']);obj['size'][2]=HALF_THICKNESS
        obj['source_asset']=dict(source,allow_nonuniform_scale=True)
        obj.setdefault('adaptations',[]).append(
            'Explicit expedited engineering approximation: original350um card thickness becomes1mm; original XY outline, face identity and mass retained.')
        # Retain the original bottom plane and face-down initial relation.
        if 'center_z'in obj:obj['center_z']+=HALF_THICKNESS-old
        obj['engineering_practical_card']=dict(schema=SCHEMA,original_thickness_m=2*old,
            approximate_thickness_m=2*HALF_THICKNESS,source_exact_geometry=False,
            user_policy='expedited_functional_acceptance',mass_changed=False,rule_changed=False)
        changed.append(obj['id'])
    if not changed:raise ValueError('No original card available for practical approximation')
    spec['semantic']['engineering_card_approximation']=dict(schema=SCHEMA,cards=changed,
        thickness_m=2*HALF_THICKNESS,source_exact_geometry=False)
    if spec['id']=='E48':
        # Translate the complete workpiece arrangement together. The far
        # card edge was beyond the Panda's side-pushing workspace; all task
        # objects retain their exact relative positions and original order.
        for obj in spec['objects']:obj['xy']=[float(obj['xy'][0])-.10,float(obj['xy'][1])]
        for zone in spec.get('zones',[]):zone['xy']=[float(zone['xy'][0])-.10,float(zone['xy'][1])]
        spec['semantic']['engineering_workspace_translation']=dict(
            translation_task_m=[-.10,0.,0.],all_objects_and_zones=True,
            original_object_relative_positions_preserved=True)
    return changed
