"""Maintainer-only physics checks. Never exposed through Computer MCP or the actor GUI."""
import json
from pathlib import Path
import torch
from PIL import Image
from isaaclab.utils.math import quat_apply


def check_grasp(controller, out):
    """Lift/release a real F01 cube using ordinary counted translation/gripper actions."""
    if controller.scene.spec['id'] != 'F01':
        raise ValueError('Grasp diagnostic is defined only for the F01 red cube')
    scene=controller.scene;side='right';obj=scene.objects['red'];robot=scene.robots[side]
    arm,fingers,bid=controller.ids[side];out=Path(out)
    offset=torch.tensor([scene.embodiment.tcp],device=controller.device)
    receipts=[]
    def act(token,mm=20):
        receipt=controller.action('STILL',token,mm)
        receipts.append(dict(token=token,step_mm=mm,**receipt))
    def tip():
        world=robot.data.body_pos_w[:,bid]+quat_apply(robot.data.body_quat_w[:,bid],offset)
        return torch.as_tensor(scene.world_to_task(world.cpu().numpy()),device=controller.device,dtype=world.dtype)
    def move(point):
        target=torch.tensor([point],device=controller.device)
        for _ in range(45):
            error=(target-tip())[0]
            if error.abs().max().item()<.0035:return
            axis=int(error.abs().argmax());sign=error[axis].item()>0
            token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][not sign]
            act(token,min(25.,max(.5,abs(error[axis].item())*1000)))
        raise RuntimeError('Grasp diagnostic could not reach the waypoint using UI actions')
    def capture(name):
        for _ in range(3):controller.sim.render();scene.update(controller.dt)
        for key in ('head','right_wrist'):
            Image.fromarray(scene.cameras[key].data.output['rgb'][0,:,:,:3].cpu().numpy()).save(out/(name+'-'+key+'.png'))
    initial=obj.data.root_pos_w[0].clone()
    # The truth-based waypoint planner is QA only, not an evaluated agent or demo policy.
    start=scene.world_to_task(initial.cpu().numpy()).tolist()
    point=start.copy();point[2]+=.15
    move(point);capture('approach')
    move(start);act('GRASP');capture('closed')
    point=tip()[0].cpu().tolist();point[2]+=.12
    move(point);capture('lifted')
    state,contacts=controller.snapshot()
    rise=float(obj.data.root_pos_w[0,2]-initial[2])
    bilateral=all(frozenset(('red',f'right_finger{i}')) in contacts for i in (1,2))
    held=bool(state['red']['grasp'][1])
    act('RELEASE')
    for _ in range(4):act('STILL')
    capture('released');state,contacts=controller.snapshot()
    released=not any(state['red']['grasp'])
    on_table=frozenset(('red','table')) in contacts
    result=dict(check='physical_grasp_lift_release',task='F01',object='red',
        rise_m=rise,bilateral_finger_contacts_at_lift=bilateral,held_at_lift=held,
        released=released,table_contact_after_release=on_table,
        passed=rise>.07 and bilateral and held and released and on_table,
        validation_only=True,full_task_solved=False,actions=receipts)
    (out/'grasp_check.private.json').write_text(json.dumps(result,indent=2)+'\n')
    print('VIDEOICL_GRASP_CHECK '+json.dumps(result),flush=True)
    if not result['passed']:raise RuntimeError('Physical grasp/lift/release check failed; see private report')
