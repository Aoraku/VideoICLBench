"""Source-required passive E47 flip preparation rails; fresh construction only."""
from copy import deepcopy
import hashlib,json
import numpy as np
SCHEMA='e47-passive-flip-edge-rails-v1'

def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def add_passive_flip_fixture(spec):
    if spec['id']!='E47'or spec.get('fixtures'):raise ValueError('Fresh E47 missing flip device only')
    old=deepcopy({k:spec.get(k)for k in('objects','fixtures','mechanisms','semantic','goals')});objects={o['id']:o for o in spec['objects']}
    vertices=[[0,-.004,0],[.045,-.004,0],[.045,-.004,.045],[0,.004,0],[.045,.004,0],[.045,.004,.045]];faces=[0,2,1,3,4,5,0,1,4,0,4,3,1,2,5,1,5,4,2,0,3,2,3,5]
    rails=[];slots={}
    for name in spec['semantic']['groups']['cards']:
        card=objects[name];x=card['xy'][0]+card['size'][0]+.003;slots[name]=[]
        for sign in(-1,1):
            slots[name].append('fixture'+str(len(rails)))
            rails.append(dict(type='mesh',mesh_data=dict(vertices=np.asarray(vertices).ravel().tolist(),faces=faces),xy=[x,card['xy'][1]+sign*.020],z=.8,
                rgba=[.46,.49,.52,1.],literal_rgba=True,passive=True,source_fixture=SCHEMA))
    spec['fixtures']=rails;spec['semantic']['execution_design_flip_fixture']=dict(schema=SCHEMA,source_lines=[66,83],source_requirement='保持翻牌装置、牌面颜色和左起顺序',
        old_physical_geometry_sha256=digest(old),fixture_geometry_sha256=digest(rails),card_slot_fixtures=slots,
        no_drive=True,no_card_constraints=True,no_initial_card_pose_change=True,native_initial_verified=False)
    for k in('objects','mechanisms','goals'):assert spec[k]==old[k]

def verify_native_initial(a):
    from pxr import UsdGeom,UsdPhysics,Gf
    import omni.usd
    s=a.scene.spec;marker=s['semantic'].get('execution_design_flip_fixture',{})
    if s['id']!='E47'or marker.get('schema')!=SCHEMA or a.c.steps!=0:raise ValueError('Fresh zero-action E47 flip-device validation required')
    state,contacts=a.c.snapshot();stage=omni.usd.get_context().get_stage();cache=UsdGeom.XformCache();fixtures={}
    for ids in marker['card_slot_fixtures'].values():
        for name in ids:
            prim=stage.GetPrimAtPath(f'{a.scene.root_path}/Task/{name}')
            if not prim or not prim.HasAPI(UsdPhysics.CollisionAPI)or prim.HasAPI(UsdPhysics.RigidBodyAPI):raise ValueError('E47 flip device must be passive static collision mesh')
            points=UsdGeom.Mesh(prim).GetPointsAttr().Get();matrix=cache.GetLocalToWorldTransform(prim)
            fixtures[name]=np.asarray([a.scene.world_to_task(np.asarray(matrix.Transform(Gf.Vec3d(*map(float,p))),float))for p in points])
    cards={o['id']:o for o in s['objects']if o['id']in marker['card_slot_fixtures']};rows=[]
    for name,o in cards.items():
        b=state[name];p=np.asarray(b['pos']);r=np.asarray(b['mat']);axis=float(r[:,2]@np.array([0,0,1]));error=float(np.linalg.norm(p[:2]-o['xy']))
        rail_contacts=[sorted(pair)for pair in contacts if name in pair and any(n in pair for n in fixtures)]
        actual_rail_min=min(float(fixtures[n][:,0].min())for n in marker['card_slot_fixtures'][name]);card_max=float(p[0]+np.abs(r[0])@np.asarray(o['size']));gap=actual_rail_min-card_max
        table=frozenset((name,'table'))in contacts
        rows.append(dict(card=name,face_axis_z=axis,xy_error_m=error,actual_rail_gap_m=gap,table_supported=table,rail_contacts=rail_contacts,
            passed=axis<-.995 and error<.001 and gap>.002 and table and not rail_contacts))
    order=sorted(cards,key=lambda n:state[n]['pos'][1],reverse=True);expected=sorted(cards,key=lambda n:cards[n]['xy'][1],reverse=True)
    row=dict(schema=SCHEMA,steps=a.c.steps,physics_ticks=a.c.physics_ticks,cards=rows,actual_order=order,expected_order=expected,
        passive_fixture_vertices_task={k:v.tolist()for k,v in fixtures.items()},initial_pose_or_joint_write_performed=False,native_whole_task_acceptance=False,
        passed=all(r['passed']for r in rows)and order==expected)
    (a.out/'e47-flip-fixture-initial.private.json').write_text(json.dumps(row,indent=2))
    if not row['passed']:raise RuntimeError('E47 flip-device native initial invariants failed')
    return row
