"""E46 v3 requires measured blade insertion followed by a hand-free lift.

Reuse the native geometry/contact witness without widening the E28 task gate.
This applies to formal evaluation as well as independent engineering references.
"""
from .execution_design_e28_scoop import ScoopWitness, REVISION


def enabled(spec):
    return spec.get('id') == 'E46' and spec.get('execution_design', {}).get('revision') == REVISION


__all__ = ['ScoopWitness', 'REVISION', 'enabled']
