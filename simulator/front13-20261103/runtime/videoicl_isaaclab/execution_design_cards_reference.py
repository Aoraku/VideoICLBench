"""Engineering public-action route for the original E47-E49 card rules.

Card identity, flip history, slot geometry and destination scores are native.
This policy only selects actions; it never writes a payload pose or a score.
"""
import math
import numpy as np
from .execution_design_card_contract import card_reference_contract
from .realworld_tool_expert import ToolAuthor, ToolExecutionError, _axis_rotation


def slot_placement(holder_pos, holder_rotation, lower, upper, half_size, rank=0):
    """Place the true lower long edge inside the same source slot.

    The slot's local X is its long direction. The card's long X points up,
    its short Y follows that slot; each card occupies a thickness-wide layer.
    """
    hp=np.asarray(holder_pos,float);hr=np.asarray(holder_rotation,float)
    lo=np.asarray(lower,float);hi=np.asarray(upper,float);half=np.asarray(half_size,float)
    if np.any(hi<=lo) or rank<0:raise ValueError('Nonempty physical slot required')
    x=np.array([0.,0.,1.]);y=hr[:,0].copy();y[2]=0.;y/=np.linalg.norm(y)
    rotation=np.column_stack((x,y,np.cross(x,y)))
    layer=(rank-1)*2*half[2]
    local=(lo+hi)/2;local[1]+=layer
    if not lo[1]+half[2]<=local[1]<=hi[1]-half[2]:
        raise ValueError('Selected cards exceed original slot thickness')
    # Lower edge midpoint, not the card centre, is the insertion datum.
    edge=hp+hr@local
    return rotation,edge+rotation[:,0]*half[0]


class CardPolicy(ToolAuthor):
    def __init__(self,author):
        self.a=author;self.c=author.c;self.spec=author.scene.spec
        self.s=self.spec['semantic'];self.task=self.spec['id'];self.variant=self.spec['variant']
        self.contract=card_reference_contract(self.spec)
        if not author.control_report.get('engineering_reference_only'):
            raise ValueError('Private engineering card actions required')
        self.index='ABC'.index(self.variant);self.start=self.c.steps
        self.limit=self.spec.get('expert_action_budget',3000);self.operations=[]
        cfg=author.scene.embodiment.config['control']
        self.min_mm=float(cfg['step_mm'][0]);self.max_mm=min(25.,float(cfg['step_mm'][1]))
        self.min_deg=float(cfg['rotation_deg'][0]);self.max_deg=min(10.,float(cfg['rotation_deg'][1]))
        self.clearance=.98;self.objects={o['id']:o for o in self.spec['objects']}
        self.original={n:self.frame(dict(actor=n))for n in self.contract['untouched']}
        self.resume=getattr(author,'_engineering_cards_resume',{})

    def unchanged(self):
        for name,(pos,rot)in self.original.items():
            p,r=self.frame(dict(actor=name))
            if np.linalg.norm(p-pos)>.004 or np.linalg.norm(r-rot)>.08:
                raise ToolExecutionError('Unrevealed source card moved: '+name)

    def pickup_card(self,name):
        from .author_clearance import prepare_single_hand
        from .engineering_card_side_grasp import acquire
        from .engineering_thin_suffix import save_stage
        ref=dict(actor=name,local=[0.,0.,0.],jaw_axis_local=[0.,1.,0.])
        side='left' if self.frame(ref)[0][1]>=-.025 else 'right'
        self.stage('card-acquire-'+name)
        practical=self.objects[name].get('engineering_practical_card',{}).get('approximate_thickness_m')==.001
        resume=self.resume.get('card')==name
        if resume:side=self.resume['side']
        elif not practical:
            prepare_single_hand(self.a,side,self.clearance)
            self.act(side,'RELEASE')
        # Reuse the source-fidelity side-band acquisition, including its real
        # bilateral25mm lift check, instead of inventing a thicker card.
        if practical:
            from .execution_design_card_row_isolation import isolate
            if not resume or self.resume.get('entry')=='cards-isolation-ready':isolate(self,ref,side)
            # The row is clear now. Let the original public RELEASE finish
            # opening before measuring meshes for the true inward-pad grip.
            for _ in range(14):
                q=self.a.scene.robots[side].data.joint_pos[:,self.c.ids[side][1]].cpu().numpy()
                if float(np.min(q))>.0395:break
                self.act()
            else:raise ToolExecutionError('Isolated-card fingers did not fully reopen')
            positioned=resume and self.resume.get('entry')=='cards-before-grasp'
            acquire(self,ref,side,precision_full_down=not positioned,centered_com_grasp=True,
                    card_face_fraction=.5,initial_lift_step_mm=.5,
                    empty_clear_completed=True,resume_side_trim=positioned)
        else:
            acquire(self,ref,side,precision_full_down=not resume,centered_com_grasp=True,
                    card_face_fraction=.5,initial_lift_step_mm=.5,
                    empty_clear_completed=resume,resume_side_trim=resume)
        self.unchanged();save_stage(self.a,'card-acquired-'+name,dict(card=name,side=side))
        return ref,side

    def place_card(self,name,ref,side,goal,rank):
        from .engineering_thin_suffix import save_stage
        guard=lambda:self.require_held(ref,side)
        self.stage('card-deliver-'+name)
        self.move(side,[*self.tip(side)[:2],max(self.clearance,self.tip(side)[2])],guard,tolerance=.004)
        if self.task=='E48':
            entry=self.s['containers']['slot'];holder=entry['object'];hp,hr=self.frame(dict(actor=holder))
            rotation,target=slot_placement(hp,hr,entry['lower'],entry['upper'],self.objects[name]['size'],rank)
            self.rotate_actor(name,side,rotation)
        else:
            rotation=np.eye(3);self.rotate_actor(name,side,rotation)
            zone=next(z for z in self.spec['zones']if z['id']==goal['target'])
            target=np.array([*zone['xy'],float(zone['surface_z'])+.001+float(self.objects[name]['size'][2])])
        high=target.copy();high[2]=max(self.clearance,target[2]+.08)
        self.move_point(side,ref,high,guard,tolerance=.004)
        self.move_point(side,ref,target+[0.,0.,.001],guard,tolerance=.001 if self.task=='E48'else .002)
        self.release(ref,side);self.move(side,self.tip(side)+[0.,0.,.06],tolerance=.004)
        self.wait(2);self.unchanged()
        support=goal['required_support']
        if not self.contact(name,support):raise ToolExecutionError('Card lacks actual destination support: '+name)
        save_stage(self.a,'card-delivered-'+name,dict(card=name,support=support))

    def run(self):
        delivery={g['object']:g for g in self.contract['delivery_goals']}
        for rank,name in enumerate(self.contract['flip_order']):
            ref,side=self.pickup_card(name);guard=lambda:self.require_held(ref,side)
            self.stage('card-flip-'+name)
            self.move(side,[*self.tip(side)[:2],max(self.clearance,self.tip(side)[2])],guard,tolerance=.004)
            self.rotate_actor(name,side,np.eye(3));self.wait(1)
            if float(self.frame(ref)[1][2,2])<.94:raise ToolExecutionError('Actual card did not turn face up')
            self.unchanged()
            if name in delivery:self.place_card(name,ref,side,delivery[name],rank)
            else:
                zone=next(z for z in self.spec['zones']if z['id']==name+'_flip')
                target=np.array([*zone['xy'],float(zone['surface_z'])+.001+float(self.objects[name]['size'][2])])
                # The unselected revealed card stays out of the box in a clear
                # table area; the rule requires its face, not the old waypoint.
                if self.objects[name].get('engineering_practical_card'):
                    target[0]-=.105
                self.move_point(side,ref,[*target[:2],self.clearance],guard,tolerance=.004)
                self.move_point(side,ref,target,guard,tolerance=.002)
                self.release(ref,side);self.move(side,self.tip(side)+[0.,0.,.06],tolerance=.004)
        self.wait(2);self.unchanged()
        return dict(task=self.task,variant=self.variant,actions=self.c.steps-self.start,
                    operations=self.operations,execution_finished=True,physics_success_not_asserted=True)


def solve(author,checkpoint=None,context=None):
    if checkpoint is not None:
        request=context or {};options=request.get('context',{})
        if request.get('entry')not in('cards-before-grasp','cards-after-row-isolation','cards-isolation-ready') or options.get('card')!='card1' or options.get('side')not in('left','right'):
            raise ValueError('Explicit first-card pregrasp checkpoint required')
        author._engineering_cards_resume=dict(card=options['card'],side=options['side'],entry=request['entry'])
    return CardPolicy(author).run()
