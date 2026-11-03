"""Explicit v3 E30 half-open input calibration; no simulation state writes."""
import math
from .execution_design import REVISION_V3

SCHEMA='videoicl-e30-half-open-input-v3'


def initial_displacements(spec):
    design=spec.get('execution_design',{})
    if spec.get('id')!='E30' or design.get('revision')!=REVISION_V3 or design.get('condition') not in ('I','E'):
        return None
    sem=spec['semantic'];entry=sem.get('execution_design_drawer_input',{})
    if entry.get('schema')!=SCHEMA:raise ValueError('Explicit E30 v3 half-open input calibration required')
    values=entry.get('normalized_displacements',{})
    if set(values)!= {'upper','lower'}:raise ValueError('Both E30 initial drawer displacements required')
    mechanisms={m['id']:m for m in spec['mechanisms']}
    for side,value in values.items():
        role=sem['joint_roles'][side]
        if type(value) not in(int,float) or not math.isfinite(value) or not role['closed_tolerance']<value<role['open_threshold']:
            raise ValueError('E30 v3 input must be genuinely half-open, neither terminal-open nor closed')
        actual=mechanisms[role['mechanism']]['initial_joint_positions'][role['joint']]
        expected=role['closed']+role['direction']*value
        if not math.isclose(actual,expected,abs_tol=1e-10):raise ValueError('E30 initial joint reset differs from declared input')
    return dict(values)


def matches_initial(measured,expected,roles):
    """Tolerate small PhysX settling while retaining the declared half-open class."""
    return all(math.isfinite(measured[s]) and abs(measured[s]-v)<=.002
               and roles[s]['closed_tolerance']<measured[s]<roles[s]['open_threshold']
               for s,v in expected.items())
