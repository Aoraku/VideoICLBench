"""Private, atomic checkpoints at completed action boundaries; never actor-visible."""
import copy,json,os
from pathlib import Path
import torch
from .profiles import PROTOCOL


def save(controller,out,episode,status,budget):
    out=Path(out)
    value=dict(version=2,protocol=PROTOCOL,camera_profile=controller.scene.spec['camera_profile'],layout_profile=controller.scene.spec['layout_profile'],
        embodiment=controller.scene.embodiment.name,control_frame='grasp_center',embodiment_config_sha256=controller.scene.spec['embodiment_config_sha256'],
        episode_id=episode,task=controller.scene.spec['id'],variant=controller.scene.spec['variant'],
        seed=controller.scene.spec['seed'],steps=controller.steps,status=status,budget=budget,
        simulation_time=float(controller.sim.current_time),grips=dict(controller.grips),
        targets={s:tuple(t.detach().cpu().clone() for t in pair) for s,pair in controller.targets.items()},
        objects={n:o.data.root_state_w.detach().cpu().clone() for n,o in controller.scene.objects.items()},
        robots={n:dict(root=r.data.root_state_w.detach().cpu().clone(),joints=r.data.joint_pos.detach().cpu().clone(),
            velocities=r.data.joint_vel.detach().cpu().clone()) for n,r in controller.scene.robots.items()},
        evaluator=copy.deepcopy(controller.evaluator.__dict__),restore_limit='PhysX contact caches are not serialized; keep live world for exact continuation')
    target=out/'checkpoint.latest.private.pt';temp=target.with_suffix('.tmp')
    torch.save(value,temp)
    with temp.open('rb') as f:os.fsync(f.fileno())
    temp.replace(target)
    meta=dict(camera_profile=controller.scene.spec['camera_profile'],episode_id=episode,steps=controller.steps,status=status,budget=budget,action_boundary=True,
        protocol=PROTOCOL,embodiment=controller.scene.embodiment.name,layout_profile=controller.scene.spec['layout_profile'],control_frame='grasp_center',embodiment_config_sha256=controller.scene.spec['embodiment_config_sha256'],
        live_world_required_for_exact_continuation=True,checkpoint=str(target))
    temp=out/'checkpoint.status.tmp';temp.write_text(json.dumps(meta,indent=2)+'\n');temp.replace(out/'checkpoint.status.private.json')
    return meta
