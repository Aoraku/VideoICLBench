"""Focused physical / leakage contract tests, no GUI oracle used in evaluation."""
import json
import numpy as np
from physics import World

def main():
    w=World(seed=17)
    initial=w.positions()
    t=w.d.time
    w.act_pair({'left':'MV_FWD','right':'MV_UP'})
    assert abs(w.d.time-t-.9)<1e-7,'Pair was not executed in one shared interval'
    targets={a:p.copy() for a,p in w.targets.items()}
    q=w.d.qpos.copy();t=w.d.time
    try:w.act_pair({'left':'AUTO_STACK','right':'STILL'})
    except ValueError:pass
    else:raise AssertionError('Task-level action accepted')
    assert np.array_equal(w.d.qpos,q) and w.d.time==t
    w.act_pair({'left':'ROTATE_CW','right':'STILL'})
    assert np.allclose(w.targets['left'],targets['left'])
    assert not w.judge(('red','green','blue'))['success'],'Untouched scene passed'
    # Oracle used only to test the private judge in changed test layout.
    for level,color in enumerate(('red','green','blue')):
        w.pick_place('right' if color=='green' else 'left',color,level)
    good=w.judge(('red','green','blue'))
    wrong=w.judge(('blue','green','red'))
    assert good['success'],good
    assert not wrong['success'],'Wrong color order passed'
    print(json.dumps({'shared_clock':True,'invalid_action_atomic':True,'rotation':True,
                      'oracle_physics_success':good,'wrong_order_rejected':True},indent=2))

if __name__=='__main__':main()
