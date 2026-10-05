import copy, os, xml.etree.ElementTree as ET
import robocasa
from pathlib import Path
from robocasa.models.objects.objects import MJCFObject

def make_mug_scene(env):
    asset_root=Path(os.environ.get("ROBOCASA_ASSET_ROOT", str(Path(robocasa.__file__).resolve().parent / "models/assets")))
    original = env.sim.get_state().flatten()
    mug = MJCFObject('obj', str(asset_root / 'objects/objaverse/mug/mug_3/model.xml'), scale=0.7)
    root = ET.fromstring(env.sim.model.get_xml())
    asset = root.find('asset')
    for node in list(asset):
        if node.get('name', '').startswith('obj_') and not node.get('name', '').startswith('obj_container_'):
            asset.remove(node)
    for node in mug.asset:
        asset.append(copy.deepcopy(node))
    world = root.find('worldbody')
    old = world.find("body[@name='obj_main']")
    index = list(world).index(old)
    world.remove(old)
    world.insert(index, copy.deepcopy(mug.get_obj()))
    env.objects['obj'] = mug
    env.reset_from_xml_string(ET.tostring(root, encoding='unicode'))
    env.sim.set_state_from_flattened(original)
    # This is scene construction, never an execution-time state correction.
    for name in ['obj_container', 'container']:
        q = env.sim.data.get_joint_qpos(name + '_joint0').copy()
        q[:3] = [10, 10, -2]
        env.sim.data.set_joint_qpos(name + '_joint0', q)
    q = env.sim.data.get_joint_qpos('obj_joint0').copy()
    q[3:] = [1, 0, 0, 0]
    env.sim.data.set_joint_qpos('obj_joint0', q)
    env.sim.forward()
