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


PASSIVE_GUIDE_POLICY='base_hand_through_passive_guide_v1'
PASSIVE_GUIDE_SCHEMAS=('e44-passive-folding-rails-v2','e44-passive-folding-rails-v3','e44-passive-folding-rails-v4')


def accumulate_passive_guided(previous,current,totals=None):
    """Count only actual base advance while a hand loads a supported base
    and the moving leaf simultaneously contacts the declared passive guide.
    Forces remain separate; no guide force is reported as hand contact.
    """
    import math
    totals=dict(totals or dict(angle=0.,joint=0.,base_displacement=[0.,0.,0.]))
    if (type(previous.get('step'))is not int or type(current.get('step'))is not int
            or previous['step']<0 or current['step']!=previous['step']+1):return totals
    fields=('angle_deg','joint_pos','base_hand_contact_force','fold_fixture_contact_force','base_table_contact_force','base_guide_contact_force')
    for sample in(previous,current):
        if any(type(sample.get(k))not in(int,float)or not math.isfinite(sample[k])for k in fields):return totals
        position=sample.get('base_pos')
        if not isinstance(position,(list,tuple))or len(position)!=3 or any(type(v)not in(int,float)or not math.isfinite(v)for v in position):return totals
    if (current['base_hand_contact_force']<=0 or current['fold_fixture_contact_force']<=0
            or max(current['base_table_contact_force'],current['base_guide_contact_force'])<=0):return totals
    motion=[b-a for a,b in zip(previous['base_pos'],current['base_pos'])]
    if math.sqrt(sum(v*v for v in motion[:2]))<=1e-8:return totals
    dq=current['joint_pos']-previous['joint_pos']
    if dq==0:return totals
    totals['angle']+=current['angle_deg']-previous['angle_deg'];totals['joint']+=dq
    totals['base_displacement']=[a+b for a,b in zip(totals['base_displacement'],motion)]
    return totals


def passive_guided_toward_final(totals,initial_angle,final_angle):
    import math
    direction=1 if final_angle>initial_angle else-1 if final_angle<initial_angle else 0
    return bool(direction*totals['angle']>=5. and abs(totals['joint'])>1e-5
                and math.sqrt(sum(v*v for v in totals['base_displacement'][:2]))>=.002)


def passive_guided_motion(samples):
    if len(samples)<3:return False
    last=samples[-1]
    if last.get('hand_contact_force')!=0 or last.get('base_hand_contact_force')!=0:return False
    if any(type(s.get('step'))is not int or s['step']<0 for s in samples):return False
    if any(b['step']!=a['step']+1 for a,b in zip(samples[:-1],samples[1:])):return False
    totals=None
    for a,b in zip(samples[:-1],samples[1:]):totals=accumulate_passive_guided(a,b,totals)
    return passive_guided_toward_final(totals,samples[0]['angle_deg'],samples[-1]['angle_deg'])
