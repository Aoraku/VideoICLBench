"""E43 source slide-rail viscous resistance, never a closed-position servo.

The gate is an independent prismatic joint, for which PhysX articulation
jointFriction is ineffective. A zero-stiffness, zero-velocity drive provides
bounded passive dissipation. This is a viscous approximation, not static
friction: sufficiently long waiting can still produce slow drift.
"""
import math

REVISION='embodied50-execution-v3-20261102'
SETTINGS=dict(model='bounded_viscous_rail_v1',damping_n_s_per_m=1000.,maximum_resistance_n=.08)


def native_readback_matches(values):
    return (values.get('stiffness_n_per_m')==0 and values.get('target_velocity_m_s')==0
        and not values.get('position_target_authored',True)
        and math.isclose(values.get('damping_n_s_per_m',float('nan')),SETTINGS['damping_n_s_per_m'],rel_tol=0,abs_tol=1e-5)
        and math.isclose(values.get('maximum_resistance_n',float('nan')),SETTINGS['maximum_resistance_n'],rel_tol=0,abs_tol=1e-8))


def configure_spec(spec):
    if spec.get('id')!='E43' or spec.get('execution_design',{}).get('revision')!=REVISION:
        raise ValueError('Reviewed E43 v3 passive slide rail only')
    matches=[j for j in spec.get('joints',[])if j.get('child')=='gate']
    if len(matches)!=1:raise ValueError('Exactly one E43 source gate joint required')
    joint=matches[0]
    if joint.get('parent') or joint.get('type')!='prismatic' or joint.get('axis')!='Y' or 'spring'in joint:
        raise ValueError('Unactuated world Y rail required')
    joint['passive_rail']=dict(SETTINGS)


def validated_settings(spec,joint):
    if spec.get('id')!='E43' or spec.get('execution_design',{}).get('revision')!=REVISION:
        raise ValueError('Passive source rail is E43 v3 only')
    if (joint.get('child')!='gate' or joint.get('parent') or joint.get('type')!='prismatic'
            or joint.get('axis')!='Y' or 'spring'in joint or joint.get('passive_rail')!=SETTINGS):
        raise ValueError('Exact reviewed passive rail parameters required')
    if not all(math.isfinite(v)and v>0 for v in(SETTINGS['damping_n_s_per_m'],SETTINGS['maximum_resistance_n'])):
        raise ValueError('Finite passive dissipation required')
    return dict(SETTINGS)


def apply_usd(joint,spec,record,UsdPhysics):
    values=validated_settings(spec,record)
    drive=UsdPhysics.DriveAPI.Apply(joint.GetPrim(),'linear')
    drive.CreateTypeAttr('force')
    drive.CreateStiffnessAttr(0.)
    drive.CreateTargetVelocityAttr(0.)
    drive.CreateDampingAttr(values['damping_n_s_per_m'])
    drive.CreateMaxForceAttr(values['maximum_resistance_n'])
    # No targetPosition is authored. There is no closed gate position force.
    return values
