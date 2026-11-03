"""Native snapshot predicates for explicitly checkpoint-assisted acceptance.

This never seals an initial state, calls result(), changes the live evaluator,
or manufactures a continuous-episode score. It compares measured final poses
and contacts to the genuine original source baseline and the native predicates.
"""
from copy import deepcopy
import math
import numpy as np


def check(spec,state,contacts,original_initial):
    from .execution_design_evidence import ExecutionDesignEvaluator
    native=ExecutionDesignEvaluator(spec)
    def clean(values):
        return {n:dict(pos=np.asarray(v['pos'],float),mat=np.asarray(v['mat'],float),
                       grasp=tuple(v.get('grasp',[False,False])))for n,v in values.items()}
    native.state=clean(state);native.contacts=set(contacts)
    native.initial=clean(original_initial)
    rule=deepcopy(native.design['local_order'])
    mapping=rule.get('reference_map')or{n:n.replace('_active','_ref')for n in rule['pieces']}
    carrier=native.initial[rule['actor']];reference=native.initial[rule.get('reference_actor','reference_tray')]
    def coord(n):return float((carrier['mat'].T@(native.initial[n]['pos']-carrier['pos']))[rule.get('axis',1)])
    def reference_coord(n):return float((reference['mat'].T@(native.initial[mapping[n]]['pos']-reference['pos']))[rule.get('axis',1)])
    rule['expected_order']=sorted(rule['pieces'],key=coord if spec['variant']=='B'else reference_coord,
                                  reverse=rule.get('descending',False))
    rule['preserved_positions']={n:(carrier['mat'].T@(native.initial[n]['pos']-carrier['pos'])).tolist()
                                 for n in rule['pieces']}if spec['variant']=='B'else{}
    rule['expected_yaws']={};rule['expected_rotations']={}
    for n in rule['pieces']:
        body=native.initial[n]if spec['variant']=='A'else native.initial[mapping[n]]
        frame=carrier if spec['variant']=='A'else reference
        rotation=frame['mat'].T@body['mat']
        rule['expected_yaws'][n]=math.atan2(rotation[1,0],rotation[0,0])
        rule['expected_rotations'][n]=rotation.tolist()
    relevant=set(native.design['target_members'])|{native.design['delivery_actor']}
    for package in native.design['packages']:
        relevant.update(package['members']);relevant.add(package['container'])
        if package.get('lid'):relevant.add(package['lid'])
    relevant.update(native.design['reference_objects'])
    predicates=dict(local_rule=bool(native.order_correct(rule)),
        packaging=all(native.package_correct(p)for p in native.design['packages']),
        destination=bool(native.destination_correct()),
        cleanup=all(native.region_correct(r,native.members(r))for r in native.design.get('cleanup_regions',[])),
        reference_preserved=all(native.unchanged(n)and native.released(n)for n in native.design['reference_objects']),
        released=all(native.released(n)for n in relevant),
        supported=relevant<=native.grounded())
    return dict(schema='e39-checkpoint-assisted-native-snapshot-predicates-v1',
        checkpoint_assisted=True,source_initial_episode_completed=False,
        continuous_episode_task_score_100=None,live_evaluator_modified=False,
        native_predicates=predicates,passed=all(predicates.values()))
