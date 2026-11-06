"""Small public-action liftoff for the v3 E04 engineering reference only."""
import json
import numpy as np
from .execution_design import REVISION_V3


def lift_from_support(author, name, side):
    """Verify retained native grip through the first 12 mm of actual lift.

    This chooses smaller ordinary UP commands; it never changes the public
    controller, force, friction, object pose, or evaluator. The historical
    8 mm lift lost a rim grasp despite settled bilateral contact beforehand.
    """
    spec = author.scene.spec
    if not (getattr(author, '_execution_design_reference_authorized', False)
            and spec.get('id') == 'E04'
            and spec.get('execution_design', {}).get('revision') == REVISION_V3):
        raise ValueError('E04 liftoff requires explicit v3 engineering reference')
    if side not in ('left', 'right'):
        raise ValueError('Unknown hand')
    index = 0 if side == 'left' else 1
    initial, _ = author.c.snapshot()
    start_z = float(initial[name]['pos'][2])
    token = ('UP' if getattr(author, 'generated_axis_signs', {}).get(side, {}).get(2, 1) > 0 else 'DOWN')
    for step in range(25):
        state, contacts = author.c.snapshot()
        body = state[name]
        rise = float(body['pos'][2]) - start_z
        record = dict(object=name, side=side, sample=step, actual_object_rise_m=rise,
                      actual_tcp_task_m=np.asarray(author.tip(side)).tolist(),
                      native_grasp=bool(body['grasp'][index]),
                      table_contact=frozenset((name, 'table')) in contacts,
                      public_step_mm=2., physics_parameters_changed=False)
        with (author.out / 'e04-liftoff.private.jsonl').open('a') as stream:
            stream.write(json.dumps(record) + '\n')
        if not body['grasp'][index]:
            raise RuntimeError('Actual E04 rim grip lost during small-step liftoff: ' + name)
        if rise >= .012:
            if record['table_contact']:
                raise RuntimeError('E04 lifted payload still contacts table: ' + name)
            return
        if step == 24:
            break
        author.act(token if side == 'left' else 'STILL', token if side == 'right' else 'STILL', 2.)
    raise RuntimeError('E04 small-step liftoff failed to raise the actual object: ' + name)
