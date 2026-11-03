"""One full-source E31C recording after the proven real right pickup/lift.

No reconstruction, object-state assignment, model API or scoring substitution.
Actual native motor ticks and the unmodified native result remain evidence.
"""
import json
import numpy as np


def finish_after_lift(a,name,side,goal):
    spec=a.scene.spec
    if not(getattr(a,'_execution_design_reference_authorized',False)and spec['id']=='E31'
           and spec['variant']=='C'and spec['seed']==4201
           and spec.get('execution_design',{}).get('condition')=='I'
           and name==spec['semantic']['plate']and side=='right'
           and not getattr(a.c,'_engineering_diagnostic_only',False)
           and a.control_report.get('engineering_reference_only')is True):
        raise ValueError('Actual I E31C source-initial right-held loaded lift required')
    from .execution_design_e31_flip import invert_at_clear_site
    from .execution_design_e31_planned_place import run as place
    from .execution_design_e31_press import support_and_release
    from .execution_design_e31_open_finish import run as open_finish
    from .execution_design_e31_hand_contacts import install
    from .engineering_checkpoint import capture
    reader=getattr(a,'_e31_native_contact_reader',None)or install(a,all_robot_links=True)
    def checkpoint(stage):
        value=capture(a.c,stage,context=dict(source_initial_full_reference=True,carried_payload=a.carried_payload))
        (a.out/('e31-source-C-'+stage+'.checkpoint.private.json')).write_text(json.dumps(value,indent=2)+'\n')
    checkpoint('actual-loaded-lift')
    # Keep the actually achieved down face without an extra author-only degree.
    invert_at_clear_site(a,name,side,orientation_only=True)
    checkpoint('actual-high-inverted')
    placement=place(a,dict(place_only=True,placement_offset_xy=[-.018,0.],allow_approximate_demo=True))
    checkpoint('real-bowl-support')
    support=support_and_release(a,dict(stop_after_top_contact=True))
    checkpoint('actual-left-top-support')
    previous=getattr(a,'_engineering_e31_verified_path',False)
    a._engineering_e31_verified_path=True
    try:release=open_finish(a)
    finally:a._engineering_e31_verified_path=previous
    a.note('placed-'+name);a.note('final')
    result=a.c.evaluator.result();state,contacts=a.c.snapshot()
    values={key:value for key,value in reader['current_forces_n'].items()if key.startswith(name+'/')}
    no_hands=bool(values and all(v is not None and v<=.001 for v in values.values())and not any(state[name]['grasp']))
    contact=frozenset((name,spec['semantic']['bowl']))in contacts
    down=float(state[name]['mat'][2,2])<0.
    on_top=float(state[name]['pos'][2])>float(state[spec['semantic']['bowl']]['pos'][2])
    ready=bool(no_hands and contact and down and on_top)
    report=dict(source_initial_full_reference=True,diagnostic_only=False,
        approximate_demo_ready=ready,original_native_result=result,
        actual_plate_normal=np.asarray(state[name]['mat'])[:,2].tolist(),actual_grasps=state[name]['grasp'],
        actual_all_hand_forces_n=values,actual_bowl_plate_contact=contact,
        verified_placement=placement,actual_top_support=support,actual_release=release,
        native_score_not_modified=True,author_precision_not_required_for_recording=True)
    (a.out/'e31-source-C-final-readback.private.json').write_text(json.dumps(report,indent=2,
        default=lambda value:value.tolist()if hasattr(value,'tolist')else str(value))+'\n')
    if not ready:raise RuntimeError('E31C recording did not establish actual released down dish on bowl')
    return result
