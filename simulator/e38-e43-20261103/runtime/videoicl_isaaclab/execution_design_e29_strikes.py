"""Confirm v3 E29 separation across native contact-solver flicker.

One missing 4ms contact sample is not a second deliberate mallet strike.
Three successive contact-free ticks confirm release, preserving the first
separation tick and all actual impulses. A later strike is still counted.
"""
from .execution_design import REVISION_V3,source_sha256


def enabled(spec):
    d=spec.get('execution_design',{})
    return(spec.get('id')=='E29' and d.get('revision')==REVISION_V3
           and d.get('source_sha256')==source_sha256(REVISION_V3))


class SeparatedStrikes:
    def __init__(self):self.gaps={}

    def update(self,e):
        tool=e.tool['actor']
        for key,name in e.semantic['keys'].items():
            force=e.force(tool,name)
            if force>0:
                if not e.held(tool):raise ValueError('Mallet key contact without actual tool grasp')
                self.gaps.pop(key,None)
                if key not in e.pending_strikes:
                    e.pending_strikes[key]=dict(tool='mallet',key=int(key),step=e.steps,contact_impulse=0.)
                e.pending_strikes[key]['contact_impulse']+=force*e.dt
            elif key in e.pending_strikes:
                gap=self.gaps.setdefault(key,dict(first_step=e.steps,count=0,last_step=e.steps-1))
                if e.steps!=gap['last_step']+1:
                    raise ValueError('E29 release confirmation requires consecutive native ticks')
                gap['count']+=1;gap['last_step']=e.steps
                if gap['count']>=3:
                    e.strikes.append({**e.pending_strikes.pop(key),'release_step':gap['first_step'],
                        'separation_confirmation_step':e.steps,'contact_free_ticks':3})
                    e.events.append(dict(event='mallet_strike_released',key=int(key),step=gap['first_step'],
                        confirmation_step=e.steps))
                    self.gaps.pop(key)
