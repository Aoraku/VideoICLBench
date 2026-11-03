"""Opt-in fresh-scene E50 contact-generation diagnostic; never source default."""
import copy
import hashlib
import math
from pathlib import Path

OFFSET = .00005
SCHEMA = 'e50-contact-skin50-diagnostic-v1'
PROFILE_FIELD = 'engineering_thin_contact_offset_m'
MARKER = 'engineering_contact_skin_diagnostic'
CARD_SHA = 'e6d4c721b74a3b6f3d273c987d06698c3b4f162de30189554de47ddee51b3f81'
ROBOT_SHA = 'dcf184538ccd43c2a43b205b34a446222e7ac65b39326d3a192adc49e6bffc5f'


def configure_spec(spec):
    from .execution_design import REVISION_V3, source_sha256
    if ((spec.get('id'), spec.get('variant'), spec.get('seed')) != ('E50', 'A', 4201)
            or spec.get('execution_design', {}).get('revision') != REVISION_V3
            or spec['execution_design'].get('source_sha256') != source_sha256(REVISION_V3)):
        raise ValueError('Exact source-checked E50 A4201 skin diagnostic required')
    card = next(o for o in spec['objects'] if o['id'] == 'card')
    if (card.get('source_asset', {}).get('sha256') != CARD_SHA
            or card['size'] != [.04415271966527, .0315, .000175]
            or card.get('reviewed_collision_settings', {}).get('coordinate_factor') != 100
            or not math.isclose(card.get('contact_offset', .0005), .0005, abs_tol=1e-12)
            or card.get('rest_offset', 0.) != 0. or MARKER in spec['semantic']):
        raise ValueError('Original conditioned 350um card and original contact skin required')
    card['contact_offset'] = OFFSET
    card['rest_offset'] = 0.
    spec['semantic'][MARKER] = dict(schema=SCHEMA, diagnostic_only=True,
        card='card', side='left', contact_offset_m=OFFSET, rest_offset_m=0.,
        source_card_sha256=CARD_SHA, source_robot_sha256=ROBOT_SHA)


def verify_only_skin_change(old, new):
    from .engineering_checkpoint import PHYSICAL_KEYS
    expected = copy.deepcopy(old)
    configure_spec(expected)
    if any(expected.get(k) != new.get(k) for k in PHYSICAL_KEYS):
        raise ValueError('Contact-skin diagnostic changed another physical input')


def mesh_fingerprint(stage, body):
    from pxr import Usd, UsdGeom
    import numpy as np
    from .engineering_checkpoint import _hash
    cache = UsdGeom.XformCache()
    inverse = cache.GetLocalToWorldTransform(body).GetInverse()
    rows = []
    for prim in Usd.PrimRange(body, Usd.TraverseInstanceProxies()):
        if not prim.IsA(UsdGeom.Mesh):
            continue
        mesh = UsdGeom.Mesh(prim)
        rows.append(dict(path=str(prim.GetPath()), points=np.asarray(mesh.GetPointsAttr().Get()).tolist(),
            counts=list(mesh.GetFaceVertexCountsAttr().Get()), indices=list(mesh.GetFaceVertexIndicesAttr().Get()),
            transform_body=np.asarray(cache.GetLocalToWorldTransform(prim) * inverse).tolist()))
    if not rows:
        raise ValueError('Source finger mesh fingerprint is empty')
    return _hash(rows)


def apply_scene(scene):
    """Author two existing finger colliders before physics initialization only."""
    value = scene.embodiment.config['physics'].get(PROFILE_FIELD)
    if value is None:
        return
    from pxr import Usd, UsdPhysics, PhysxSchema
    import omni.usd
    if value != OFFSET or scene.spec['semantic'].get(MARKER, {}).get('schema') != SCHEMA:
        raise ValueError('Skin profile requires the explicit source diagnostic marker')
    if hashlib.sha256(Path(scene.embodiment.asset_path()).read_bytes()).hexdigest() != ROBOT_SHA:
        raise ValueError('Contact-skin robot source SHA mismatch')
    stage = omni.usd.get_context().get_stage()
    rows = []
    for name in scene.embodiment.fingers:
        root = stage.GetPrimAtPath(f'{scene.root_path}/left_robot/{name}')
        before = mesh_fingerprint(stage, root)
        # USD forbids properties inside an instance proxy. Uninstance only
        # this fresh-scene collision subtree; source layers stay untouched.
        instances = set()
        for prim in Usd.PrimRange(root, Usd.TraverseInstanceProxies()):
            if not prim.HasAPI(UsdPhysics.CollisionAPI):
                continue
            node = prim
            while node and node != root:
                if node.IsInstance():
                    instances.add(str(node.GetPath()))
                node = node.GetParent()
        for path in sorted(instances):
            stage.GetPrimAtPath(path).SetInstanceable(False)
        if mesh_fingerprint(stage, root) != before:
            raise ValueError('Fresh finger composition changed source vertices/topology/transform')
        found = []
        for prim in Usd.PrimRange(root, Usd.TraverseInstanceProxies()):
            if not prim.HasAPI(UsdPhysics.CollisionAPI):
                continue
            if not UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get():
                raise ValueError('Unexpected disabled native finger collision')
            api = PhysxSchema.PhysxCollisionAPI.Apply(prim)
            previous = dict(contact_offset=str(api.GetContactOffsetAttr().Get()),
                            rest_offset=str(api.GetRestOffsetAttr().Get()))
            api.CreateContactOffsetAttr(OFFSET)
            api.CreateRestOffsetAttr(0.)
            found.append(dict(collider=str(prim.GetPath()), previous_authored_or_schema=previous,
                              contact_offset_m=OFFSET, rest_offset_m=0.,
                              uninstanced_collision_roots=sorted(instances),
                              source_geometry_before_after_sha256=before))
        if len(found) != 1:
            raise ValueError('Exactly one actual collider per source finger required')
        rows.extend(found)
    scene.engineering_thin_contact_skin_receipt = dict(schema=SCHEMA, fresh_scene_only=True,
        finger_colliders=rows, diagnostic_only=True, source_geometry_material_mass_unchanged=True)


def native_readback(controller):
    import numpy as np
    scene = controller.scene
    physics = next(iter(scene.contacts.values()))[0]._physics_sim_view
    out = {}
    for name, path in [('card', f'{scene.root_path}/Props/card')] + [
            (n, f'{scene.root_path}/left_robot/{n}') for n in scene.embodiment.fingers]:
        view = physics.create_rigid_body_view(path)
        if view is None or view.count != 1:
            raise ValueError('Exact native card/finger rigid view required')
        values = {}
        for field, method, expected in [('contact_offset_m', 'get_contact_offsets', OFFSET),
                                        ('rest_offset_m', 'get_rest_offsets', 0.)]:
            raw = getattr(view, method)()
            array = np.asarray(raw.cpu() if hasattr(raw, 'cpu') else raw)
            if array.size != 1 or not np.isfinite(array).all() or not np.allclose(array, expected, rtol=0, atol=1e-9):
                raise ValueError('Native contact-skin readback mismatch: ' + name + '/' + field)
            values[field] = array.tolist()
        out[name] = values
    return out


def verify_native_finger_geometry(controller):
    """Check original measured toe/pad rays before admitting the comparison."""
    import numpy as np
    import carb, omni.physx
    from pxr import PhysicsSchemaTools
    from isaaclab.utils.math import matrix_from_quat
    from .execution_design_native_finger_mesh import DATA
    from .engineering_native_convex_rays import line_entry
    from .source_reviewed_collisions import ray_hit_value
    scene = controller.scene
    robot = scene.robots['left']
    query = omni.physx.get_physx_scene_query_interface()
    report = {}
    for item in DATA['rows']:
        name = item['name']
        body = f'{scene.root_path}/left_robot/{name}'
        bid = robot.find_bodies(name)[0][0]
        position = robot.data.body_pos_w[0,bid].cpu().numpy()
        rotation = matrix_from_quat(robot.data.body_quat_w[0,bid]).cpu().numpy()
        vertices = np.asarray(item['vertices_body_local'])
        lo, hi = vertices.min(0), vertices.max(0)
        sites = []
        for x in (-.004, 0., .004):
            for y in (0., .004, .010):
                sites.append((np.array([x,y,hi[2]+.01]), np.array([0.,0.,-1.])))
            sign = -1. if name == scene.embodiment.fingers[0] else 1.
            for depth in (.0001,.0003,.0006):
                sites.append((np.array([x,lo[1]-.01 if sign<0 else hi[1]+.01,hi[2]-depth]), np.array([0.,-sign,0.])))
        checks = []
        for origin, direction in sites:
            expected = line_entry(vertices, origin, direction)
            hits = []
            def receive(hit):
                path = ray_hit_value(hit,'rigidBody','rigid_body')
                path = str(path if isinstance(path,str) else PhysicsSchemaTools.intToSdfPath(path))
                if path == body:
                    hits.append(np.asarray(ray_hit_value(hit,'position'),float))
                return True
            world = position + rotation@origin
            wd = rotation@direction
            query.raycast_all(carb.Float3(*map(float,world)),carb.Float3(*map(float,wd)),.15,receive)
            actual = min(hits,key=lambda point:float((point-world)@wd)) if hits else None
            error = None if expected is None or actual is None else float(np.linalg.norm(actual-(position+rotation@expected)))
            agrees = (expected is None and actual is None) or (error is not None and error<.00002)
            checks.append(dict(origin_body=origin.tolist(),direction_body=direction.tolist(),error_m=error,agrees=agrees))
        valid = [row['error_m'] for row in checks if row['error_m'] is not None]
        report[name] = dict(scope='previously measured toe and inner pad only',checks=checks,
            maximum_error_m=max(valid,default=None),passed=len(valid)>=3 and all(row['agrees']for row in checks))
    return report
