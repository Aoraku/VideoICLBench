"""Explicit startup-only mechanism state writes, before any physics settling.

ArticulationCfg.init_state defines defaults; it does not apply those defaults to
already authored source USD joints. Only declared new inputs opt into this hook.
"""
from .execution_design_inputs_v3 import initial_joint_positions
from .execution_design_drawers import initial_displacements


def initialize_declared_mechanisms(scene):
    declarations=[m for m in scene.spec.get('mechanisms',[]) if 'initial_joint_positions' in m]
    if not declarations:
        return []
    if getattr(scene,'_declared_mechanisms_initialized',False):
        raise RuntimeError('Declared mechanism startup state already applied; live reset forbidden')
    if initial_displacements(scene.spec) is None:
        raise ValueError('Declared mechanism initialization requires explicit supported input')
    prepared=[]
    for mechanism in declarations:
        asset=scene.mechanisms[mechanism['id']]
        names=list(asset.joint_names)
        values=initial_joint_positions(scene.spec,mechanism,names)
        positions=asset.data.default_joint_pos.clone()
        velocities=asset.data.default_joint_vel.clone()
        for index,name in enumerate(names):
            positions[:,index]=values[name]
            velocities[:,index]=0.
        prepared.append((mechanism['id'],asset,positions,velocities,values))
    # A failed partial write must not be retried against a live world.
    scene._declared_mechanisms_initialized=True
    receipts=[]
    for name,asset,positions,velocities,values in prepared:
        asset.write_joint_state_to_sim(positions,velocities)
        asset.write_data_to_sim()
        receipts.append(dict(mechanism=name,requested_joint_positions=values,
                             stage='startup_before_settling',measurement_verified=False))
    return receipts
