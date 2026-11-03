"""Versioned physical settling policy, separate from task geometry/actions.

The user permits small final wobble for the revised E26-E37 task work. Other
tasks and older task contracts retain their existing measured-pose envelope.
"""
from dataclasses import dataclass,asdict
import math


@dataclass(frozen=True)
class StabilityPolicy:
    version:str
    seconds:float
    translation_m:float
    rotation_matrix:float
    description:str

    def record(self):return asdict(self)


LEGACY=StabilityPolicy('native-pose-envelope-v1',.5,.002,.02,
    '0.5s continuous pose envelope: 2mm translation, .02 rotation-matrix Frobenius')
LIGHT=StabilityPolicy('execution-v3-e26-e37-light-settle-20261103',.5,.005,
    2*math.sqrt(2)*math.sin(math.radians(5.)/2),
    '0.5s continuous pose envelope: 5mm translation, 5deg rotation; release/support/task predicates unchanged')
LIGHT_TASKS=frozenset('E%02d'%i for i in range(26,38))


def for_evaluator(e):
    spec=getattr(e,'spec',{})
    task=spec.get('id','')
    if (spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
            and task in LIGHT_TASKS):return LIGHT
    return LEGACY
