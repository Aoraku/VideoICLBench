"""Opt-in physical arm clearance for sequential single-hand demonstrations."""
import json
import numpy as np


def _empty(author,side):
    state,contacts=author.c.snapshot();index=0 if side=='left' else 1
    if (any(value['grasp'][index] for value in state.values())
            or any(frozenset((name,f'{side}_finger{i}')) in contacts
                   for name in state for i in (1,2))):
        raise RuntimeError('Single-hand clearance requires an empty native '+side+' hand')


def _log(author,phase):
    state,contacts=author.c.snapshot()
    row=dict(phase=phase,step=author.c.steps,tips={s:author.tip(s).tolist() for s in ('left','right')},
        objects={n:dict(position=v['pos'].tolist(),rotation=v['mat'].tolist(),grasp=v['grasp']) for n,v in state.items()},
        contacts=[sorted(pair) for pair in contacts])
    with (author.out/'single-hand-stage.private.jsonl').open('a') as stream:stream.write(json.dumps(row)+'\n')


def _park(author,side,park_z):
    _empty(author,side)
    tip=author.tip(side)
    author.move_smooth({side:[*tip[:2],max(park_z,float(tip[2]))]},tolerance=.006)
    mount=np.asarray(author.scene.embodiment.config['robots'][side]['position'],float)
    base=author.scene.world_to_task(mount+np.asarray(getattr(author.scene,'origin',(0.,0.,0.)),float))
    author.move_smooth({side:[base[0]+.15,base[1]+(.22 if side=='left' else -.22),park_z]},tolerance=.006)


def prepare_single_hand(author,side,clearance_z):
    config=author.scene.embodiment.config.get('author_recording',{})
    if not config.get('clear_idle_arm',False):return
    if side not in ('left','right') or author.scene.embodiment.name!='franka':
        raise ValueError('Single-hand clearance requires a native Panda hand')
    park_z=float(config.get('idle_park_z',1.10))
    if not np.isfinite(park_z) or not .95<=park_z<=1.15:raise ValueError('Invalid reviewed parking height')
    if not hasattr(author,'_single_hand_home_xy'):
        author._single_hand_home_xy={s:author.tip(s)[:2].copy() for s in ('left','right')}
    previous=getattr(author,'_single_hand_active',None)
    if previous==side:return
    _log(author,'before-activate-'+side)
    idle=previous or ('right' if side=='left' else 'left')
    _park(author,idle,park_z)
    if previous is not None:
        _empty(author,side)
        home=author._single_hand_home_xy[side]
        author.move_smooth({side:[*home,park_z]},tolerance=.006)
        author.move_smooth({side:[*home,min(park_z,float(clearance_z))]},tolerance=.006)
    author._single_hand_active=side
    _log(author,'after-activate-'+side)


def finish_single_hand(author):
    config=author.scene.embodiment.config.get('author_recording',{})
    if not config.get('clear_idle_arm',False):return
    side=getattr(author,'_single_hand_active',None)
    if side is None:return
    author.stage='single-hand-final-retreat'
    _log(author,'before-final-retreat')
    _empty(author,side)
    park_z=float(config.get('idle_park_z',1.10))
    tip=author.tip(side);author.move_smooth({side:[*tip[:2],max(park_z,float(tip[2]))]},tolerance=.006)
    author.neutralize_empty_wrist(side)
    _park(author,side,park_z)
    for _ in range(4):author.act()
    _log(author,'after-final-retreat')
