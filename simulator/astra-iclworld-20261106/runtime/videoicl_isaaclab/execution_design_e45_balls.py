"""E45-only source-round balls, preserving the measured native mass/COM/I."""
import copy
import numpy as np
from .layout import rotation_matrix

SOURCE_SHA='257fb8afcd8eb2787aa4c59fd39314b036f78287e4d277f210168048f8becc1a'
BALLS=('dark_green','red','light_green')
BASELINE_ARTIFACT_SHA='83d71f5eb878ad0692b8cca68882d1b65b36106969b442f043ecd0cbb32656fb'
NATIVE_MASS_PROPERTIES={'masses_kg': [[0.002491751918569207]], 'inertias_kg_m2': [[1.6070332264916942e-07, -5.3061199878357e-10, 1.1905800789691057e-09, -5.306102224267306e-10, 1.678405112670589e-07, -6.261657858885883e-10, 1.1905765262554269e-09, -6.261657858885883e-10, 1.6619641485249304e-07]], 'centres_of_mass': [[-0.00010476490569999442, 0.00019799266010522842, -8.093220822047442e-05, -0.19317832589149475, 0.091667041182518, 0.0455787256360054, 0.975808322429657]]}
NATIVE_SOURCE_MASS_PROPERTIES={'cup': {'masses_kg': [[0.059999994933605194]], 'inertias_kg_m2': [[7.90489575592801e-05, -4.0475573115372754e-08, -1.952554384843097e-08, -4.047466362067098e-08, 7.945122342789546e-05, -1.4848944829282118e-07, -1.952554384843097e-08, -1.4848944829282118e-07, 6.78974756738171e-05]], 'centres_of_mass': [[-3.677891982079018e-06, -0.00018355173233430833, -0.006568017415702343, -0.0063758231699466705, 0.0012130588293075562, 0.0490921214222908, 0.9987732172012329]]}, 'dark_green': {'masses_kg': [[0.002491751918569207]], 'inertias_kg_m2': [[1.6070332264916942e-07, -5.3061199878357e-10, 1.1905800789691057e-09, -5.306102224267306e-10, 1.678405112670589e-07, -6.261657858885883e-10, 1.1905765262554269e-09, -6.261657858885883e-10, 1.6619641485249304e-07]], 'centres_of_mass': [[-0.00010476490569999442, 0.00019799266010522842, -8.093220822047442e-05, -0.19317832589149475, 0.091667041182518, 0.0455787256360054, 0.975808322429657]]}, 'red': {'masses_kg': [[0.002491751918569207]], 'inertias_kg_m2': [[1.6070332264916942e-07, -5.3061199878357e-10, 1.1905800789691057e-09, -5.306102224267306e-10, 1.678405112670589e-07, -6.261657858885883e-10, 1.1905765262554269e-09, -6.261657858885883e-10, 1.6619641485249304e-07]], 'centres_of_mass': [[-0.00010476490569999442, 0.00019799266010522842, -8.093220822047442e-05, -0.19317832589149475, 0.091667041182518, 0.0455787256360054, 0.975808322429657]]}, 'light_green': {'masses_kg': [[0.002491751918569207]], 'inertias_kg_m2': [[1.6070332264916942e-07, -5.3061199878357e-10, 1.1905800789691057e-09, -5.306102224267306e-10, 1.678405112670589e-07, -6.261657858885883e-10, 1.1905765262554269e-09, -6.261657858885883e-10, 1.6619641485249304e-07]], 'centres_of_mass': [[-0.00010476490569999442, 0.00019799266010522842, -8.093220822047442e-05, -0.19317832589149475, 0.091667041182518, 0.0455787256360054, 0.975808322429657]]}}


def settings_for(obj):
    source=obj.get('source_asset',{})
    if (obj.get('id')not in BALLS or obj.get('kind')!='sphere'
            or source.get('root_env')!='VIC_FULL50_RIGID_ASSETS'
            or source.get('relative_path')!='sphere_white.usda'or source.get('sha256')!=SOURCE_SHA
            or not np.allclose(obj.get('size',[]),[.01316]*3,atol=1e-12,rtol=0)
            or not np.allclose(obj.get('local_bounds_center',[0,0,0]),[0,0,0],atol=1e-12,rtol=0)
            or obj.get('mass')!=.002491752 or obj.get('static_friction')!=.8
            or obj.get('dynamic_friction')!=.6 or obj.get('restitution')!=0):
        raise ValueError('Exact E45 source-round ball and unchanged material required')
    return dict(source_sha256=SOURCE_SHA,approximation='analyticSphere',
        preserve_native_mass_properties=copy.deepcopy(NATIVE_MASS_PROPERTIES),native_mass_baseline_sha256=BASELINE_ARTIFACT_SHA)


def configure_spec(spec):
    if spec.get('id')!='E45':raise ValueError('E45-only reviewed source balls')
    objects={o['id']:o for o in spec['objects']}
    for name in BALLS:
        obj=objects[name]
        if obj.get('reviewed_collision_settings'):raise ValueError('Ball already has an adapter')
        obj['reviewed_collision_settings']=settings_for(obj)
    return list(BALLS)


def verify_only_ball_adapters(old,new):
    if old.get('id')!='E45'or new.get('id')!='E45':raise ValueError('E45 migration only')
    expected=copy.deepcopy(old);configure_spec(expected)
    from .engineering_checkpoint import PHYSICAL_KEYS
    if any(expected.get(k)!=new.get(k)for k in PHYSICAL_KEYS):raise ValueError('E45 migration changed other physical inputs')
    return list(BALLS)


def apply_source_mass_binding(root,obj):
    from pxr import UsdPhysics,Gf
    if obj.get('reviewed_collision_settings')!=settings_for(obj):
        raise ValueError('Mass binding requires exact reviewed E45 source sphere adapter')
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
