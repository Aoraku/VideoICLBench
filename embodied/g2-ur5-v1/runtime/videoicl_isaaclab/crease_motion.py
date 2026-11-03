"""Signed force-attributed crease displacement, independent of movement speed."""


def accumulate_driven(previous, current, totals=None, *, require_joint=False):
    """Add only measured, consecutive, force-bearing interval displacement.

    Regrasping does not erase prior work. Reverse motion cancels forward motion;
    zero-force drift and missing intervals contribute nothing. The sample force
    applies to the interval ending at that sample (native trace convention).
    """
    totals=dict(totals or dict(angle=0.,joint=0.,coupled_angle=0.))
    if (type(previous.get('step')) is not int or type(current.get('step')) is not int
            or previous['step']<0 or current['step']!=previous['step']+1
            or current['hand_contact_force']<=0):return totals
    da=current['angle_deg']-previous['angle_deg']
    totals['angle']+=da
    if require_joint:
        dq=current['joint_pos']-previous['joint_pos']
        totals['joint']+=dq
        # Joint sign depends on the crease axis and normal convention. Do not
        # impose a global sign; require joint motion on the very same interval.
        if dq!=0:totals['coupled_angle']+=da
    return totals


def driven_toward_final(totals, initial_angle, final_angle, *, require_joint=False):
    direction=1 if final_angle>initial_angle else -1 if final_angle<initial_angle else 0
    valid=direction*totals['angle']>=5.
    if require_joint:
        valid=valid and direction*totals['coupled_angle']>=5. and abs(totals['joint'])>1e-5
    return bool(valid)


def contact_driven_motion(samples):
    if len(samples)<2:return False
    if any(type(s.get('step')) is not int or s['step']<0 for s in samples):return False
    if any(b['step']!=a['step']+1 for a,b in zip(samples[:-1],samples[1:])):return False
    totals=None
    for previous,current in zip(samples[:-1],samples[1:]):
        totals=accumulate_driven(previous,current,totals)
    return driven_toward_final(totals,samples[0]['angle_deg'],samples[-1]['angle_deg'])
