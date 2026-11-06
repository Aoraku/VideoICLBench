"""E43-only round-ball collision fidelity with measured source mass binding."""
import copy
import numpy as np
from .layout import rotation_matrix

SOURCE_SHA='257fb8afcd8eb2787aa4c59fd39314b036f78287e4d277f210168048f8becc1a'
BASELINE_ARTIFACT_SHA='d5357530263083dfbeba1a720cd8ae85917de6218d05f76fc596bdbe0149585b'
NATIVE_MASS_PROPERTIES={'masses_kg': [[0.00800000037997961]], 'inertias_kg_m2': [[5.780656806564366e-07, -4.218762228447304e-09, -1.861060638930212e-09, -4.218735583094713e-09, 5.826055939905928e-07, 2.252036779282207e-09, -1.8610677443575696e-09, 2.252022568427492e-09, 5.944352210462966e-07]], 'centres_of_mass': [[-0.00010868914978345856, 8.609940414316952e-05, 0.00020848399435635656, -0.1301027238368988, -0.0479816272854805, 0.2583145797252655, 0.9560568332672119]]}


def settings_for(obj):
    source=obj.get('source_asset',{})
    if (obj.get('id')!='ball' or obj.get('kind')!='sphere' or
            source.get('root_env')!='VIC_FULL50_RIGID_ASSETS' or
            source.get('relative_path')!='sphere_white.usda' or source.get('sha256')!=SOURCE_SHA or
            not np.allclose(obj['size'],[.013652941818490449,.014,.013857428965220098],atol=1e-12,rtol=0) or
            obj.get('mass')!=.008 or obj.get('static_friction')!=.8 or obj.get('dynamic_friction')!=.6 or
            obj.get('restitution')!=0):
        raise ValueError('Exact E43 source ball geometry and unchanged material required')
    return dict(source_sha256=SOURCE_SHA,approximation='analyticSphere',
        preserve_native_mass_properties=copy.deepcopy(NATIVE_MASS_PROPERTIES),
        native_mass_baseline_sha256=BASELINE_ARTIFACT_SHA)


def configure_spec(spec):
    if spec.get('id')!='E43':raise ValueError('E43-only analytic source ball')
    ball=next(o for o in spec['objects']if o['id']=='ball')
    if ball.get('reviewed_collision_settings'):raise ValueError('Existing ball adapter needs independent review')
    ball['reviewed_collision_settings']=settings_for(ball)
    return ['ball']


def verify_only_ball_adapter(old,new):
    if old.get('id')!='E43' or new.get('id')!='E43':raise ValueError('E43 migration only')
    expected=copy.deepcopy(old);configure_spec(expected)
    from .engineering_checkpoint import PHYSICAL_KEYS
    if any(expected.get(k)!=new.get(k)for k in PHYSICAL_KEYS):
        raise ValueError('E43 migration changed other physical inputs')
    return ['ball']


def apply_source_mass_binding(root,obj):
    from pxr import UsdPhysics,Gf
    if obj.get('reviewed_collision_settings')!=settings_for(obj):
        raise ValueError('Mass binding requires exact reviewed E43 sphere adapter')
    row=NATIVE_MASS_PROPERTIES;com=np.asarray(row['centres_of_mass'][0]);q=com[3:]
    rotation=rotation_matrix([q[3],*q[:3]])
    inertia=np.asarray(row['inertias_kg_m2'][0]).reshape(3,3)
    principal=rotation.T@inertia@rotation
    if np.max(np.abs(principal-np.diag(np.diag(principal))))>1e-12 or np.any(np.diag(principal)<=0):
        raise ValueError('Measured E43 inertia/principal axes binding inconsistent')
    api=UsdPhysics.MassAPI.Apply(root)
    api.CreateMassAttr(float(row['masses_kg'][0][0]))
    api.CreateCenterOfMassAttr(Gf.Vec3f(*map(float,com[:3])))
    api.CreateDiagonalInertiaAttr(Gf.Vec3f(*map(float,np.diag(principal))))
    api.CreatePrincipalAxesAttr(Gf.Quatf(float(q[3]),Gf.Vec3f(*map(float,q[:3]))))
