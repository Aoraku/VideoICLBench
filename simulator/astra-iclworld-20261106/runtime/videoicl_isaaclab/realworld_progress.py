"""Private task-specific v2 progress scoring over trusted native observations.

This module neither runs physics nor certifies the origin of evidence. The caller
must supply a sealed native snapshot. ``task_score_100`` is the raw rubric score;
only the integration layer applies validated native success and the failure cap.
Missing evidence is null; a witnessed task mistake is a numeric score.
"""
from collections.abc import Mapping
from copy import deepcopy
from fractions import Fraction
import math

from . import realworld_semantic_checks as sem

PROTOCOL = 'videoicl-realworld50-task-score-v2'
COLORS = ('red', 'green', 'blue')
CARDS = tuple('card'+str(i) for i in range(1,6))


class MissingEvidence(ValueError):
    pass


def _require_clip_measurements(record):
    """A provided clip trace must contain measured joints, not just flags.

    Empty/absent records represent no established grip; a populated record
    with missing or nonfinite measurements is unscored evidence corruption.
    """
    if not isinstance(record,Mapping) or not isinstance(record.get('clip_id'),str):
        raise MissingEvidence('clip_record:malformed')
    samples=record.get('samples')
    if not sem._steps(samples,3):raise MissingEvidence('clip_samples:malformed')
    for sample in samples:
        for key in ('jaw_gap_m','joint_pos','handle_contact_force'):
            if not sem._number(sample.get(key)):raise MissingEvidence('clip_samples:'+key)
        if sample['jaw_gap_m']<0 or sample['handle_contact_force']<0:raise MissingEvidence('clip_samples:negative_measurement')
    for key in ('handles_released','edge_between_jaws'):
        if type(samples[-1].get(key))is not bool:raise MissingEvidence('clip_samples:'+key)
    for key in ('left_jaw_contact_force','right_jaw_contact_force'):
        if not sem._number(samples[-1].get(key)) or samples[-1][key]<0:raise MissingEvidence('clip_samples:'+key)


class Evidence:
    def __init__(self, observation, initial=None):
        self.o = observation
        self.initial = initial
        self.units = []
        self.denominator = None
        self.cap = None

    def get(self, name, kind=None, source=None):
        obj = self.o if source is None else source
        if not isinstance(obj, Mapping) or name not in obj or obj[name] is None:
            raise MissingEvidence(name)
        value = obj[name]
        if kind is not None and (not isinstance(value,kind) or kind is bool and type(value) is not bool):
            raise MissingEvidence(name+':malformed')
        return value

    def nullable(self,key,source=None):
        obj=self.o if source is None else source
        if not isinstance(obj,Mapping) or key not in obj:raise MissingEvidence(key)
        return obj[key]

    def seq(self, key, source=None):
        return self.get(key, (list,tuple,set,frozenset), source)

    def members(self, key, source=None):
        values = self.seq(key,source)
        if any(not isinstance(v,(str,int)) or isinstance(v,bool) for v in values) or len(set(values)) != len(values):
            raise MissingEvidence(key+':duplicate_or_invalid_identity')
        return set(values)

    def mapping(self,key,source=None):
        return self.get(key,Mapping,source)

    def boolean(self,key,source=None):
        return self.get(key,bool,source)

    def physical(self, name, *, source=None, support=True):
        obj = self.o if source is None else source
        statuses=self.mapping('progress_physical',obj)
        status=self.get(str(name),Mapping,statuses)
        fields=('released','stable','supported') if support else ('released','stable')
        return all([self.boolean(k,status) for k in fields])

    def physical_all(self,names,**kwargs):
        return all([self.physical(n,**kwargs) for n in names])

    def unit(self,name,weight,achieved):
        if type(achieved) is not bool:
            raise MissingEvidence(name+':predicate_not_boolean')
        weight=Fraction(weight)
        self.units.append(dict(id=name,weight_numerator=weight.numerator,
             weight_denominator=weight.denominator,achieved=achieved,
             score_numerator=weight.numerator if achieved else 0,
             score_denominator=weight.denominator))
        return weight if achieved else Fraction(0)

    def count(self, ids, good, errors=0):
        ids=list(ids); n=len(ids)
        if not n: raise MissingEvidence('empty_required_change_set')
        self.denominator=n
        self.cap=Fraction(100*(n-1),n)
        result=sum((self.unit(str(k),Fraction(100,n),bool(good(k))) for k in ids),Fraction(0))
        if errors:
            self.units.append(dict(id='explicit_task_violations',count=errors,
                score_numerator=-100*errors,score_denominator=n))
        return max(Fraction(0),result-Fraction(100*errors,n))

    def causal(self,name):
        return self.get(name,Mapping,self.mapping('progress_causal'))


def _angle(a,b):
    if not sem._number(a) or not sem._number(b):raise MissingEvidence('yaw:nonfinite')
    return abs((a-b+180)%360-180)<=sem.ANGLE_TOLERANCE_DEG


def _near(a,b):
    if not sem._vector(a,2) or not sem._vector(b,2):raise MissingEvidence('xy:malformed')
    return math.dist(a,b)<=sem.POSITION_TOLERANCE_M


def _edges(e,key='support_edges'):
    result=set()
    for p in e.seq(key):
        if not isinstance(p,(list,tuple)) or len(p)!=2:raise MissingEvidence(key+':malformed')
        result.add(tuple(p))
    return result


def _grounded(edges,n):
    ground={'table','rightmost'}
    for _ in range(len(edges)+1):
        ground |= {b for a,b in edges if a in ground}
    return n in ground


def _prefix_events(e, key, expected, targets=None):
    events=e.seq(key); seen=set(); prefix=[]; last=-1; broken=False
    for event in events:
        if not isinstance(event,Mapping):raise MissingEvidence(key+':malformed')
        name=e.get('object',str,event); target=e.get('target',str,event)
        step=e.get('step',int,event)
        released=e.boolean('released',event); contact=e.boolean('support_contact',event)
        if isinstance(step,bool) or step<0 or step<last:raise MissingEvidence(key+':unordered')
        if name in seen:continue
        seen.add(name)
        k=len(prefix)
        correct=(not broken and k<len(expected) and name==expected[k]
            and (targets is None or target==targets[k]) and released and contact and step>last)
        if correct:prefix.append(name)
        else:broken=True
        last=step
    return prefix


def _dynamic(e, initial_truth, final_truth):
    if set(initial_truth)!=set(final_truth):raise MissingEvidence('initial_final_atom_identity_mismatch')
    need=[k for k,v in initial_truth.items() if not v]
    damaged=sum(1 for k,v in initial_truth.items() if v and not final_truth[k])
    return e.count(need,lambda k:final_truth[k],damaged)


def _score(e,t,v):
    i='ABC'.index(v); o=e.o
    if t=='E01':
        chosen=({'burger','fries'},{'burger','drink'},{'fries','drink'})[i]
        inside=e.members('in_plate'); support=e.members('supported_in_plate');e.members('outside_plate')
        return e.count(sorted(chosen),lambda n:n in inside and n in support and e.physical(n),len(inside-chosen))
    if t in ('E02','E35'):
        order=((('red','green','blue'),('green','blue','red'),('blue','red','green')) if t=='E02'
               else (('large','medium','small'),('small','medium','large'),('large','small','medium')))[i]
        edges=_edges(e); good=[]; complete=('table',order[0]) in edges
        for a,b in zip(order,order[1:]):
            complete=complete and (a,b) in edges
            good.append(bool(complete and e.physical_all(order[:len(good)+2])))
        return e.count(range(2),lambda n:good[n])
    if t=='E03':
        order=(('red','green','blue'),('green','blue','red'),('blue','red','green'))[i]
        pairs=e.members('progress_nested_pairs'); up=e.members('upright'); outer=e.members('outer_supported')
        complete=order[0] in outer; good=[]
        for a,b in zip(order,order[1:]):
            complete=complete and a+'>'+b in pairs and a in up and b in up
            good.append(bool(complete and e.physical_all(order[:len(good)+2])))
        return e.count(range(2),lambda n:good[n])
    if t in ('E04','E05'):
        if t=='E04': expected=(dict(green='triangle',blue='circle',red='square'),dict(green='square',blue='circle',red='triangle'),dict(green='circle',blue='triangle',red='square'))[i]
        else: expected=dict(zip(('cube','sphere','triangle'),(('square','circle','triangle'),('circle','triangle','square'),('triangle','square','circle'))[i]))
        placements=e.mapping('placements'); support=e.members('supported')
        return e.count(expected,lambda n:placements.get(n)==expected[n] and n in support and e.physical(n))
    if t in ('E06','E12'):
        targets=({'left_far','left_middle','left_near'},{'right_far','right_middle','right_near'},{'left_far','left_near','right_middle'})[i] if t=='E06' else ({1,2},{3,4},{1,4})[i]
        mapping=e.mapping('ball_to_cell' if t=='E06' else 'charger_to_slot')
        valid=e.members('seated' if t=='E06' else 'physically_inserted')
        if t=='E12':valid &= e.members('supported')
        correct={target for n,target in mapping.items() if target in targets and n in valid and e.physical(n)}
        return e.count(sorted(targets),lambda target:target in correct)
    if t=='E07':
        expected=([1,2,3,4,5],[5,4,3,2,1],[3,2,1,4,5])[i]
        def truth(src):
            order=list(e.seq('far_to_near',src)); supported=e.members('supported_ranks',src); pairs=e.mapping('nonoverlap_pairs',src)
            if set(order)!=set(expected) or len(order)!=5:raise MissingEvidence('far_to_near:identities')
            out={}
            for a,b in zip(expected,expected[1:]):
                key=f'{a}|{b}'; reverse=f'{b}|{a}'
                overlap=e.boolean(key if key in pairs else reverse,pairs)
                out[key]=order.index(a)<order.index(b) and overlap and a in supported and b in supported and e.physical_all((a,b),source=src)
            return out
        if e.initial is None:raise MissingEvidence('initial_observation')
        return _dynamic(e,truth(e.initial),truth(o))
    if t=='E08':
        expected=(dict(left='toe',right='toe'),dict(left='heel',right='heel'),dict(left='toe',right='heel'))[i]
        orientation=e.mapping('toward_label');inside=e.members('in_box');support=e.members('supported_in_box')
        return e.count(expected,lambda n:orientation.get(n)==expected[n] and n in inside&support and e.physical(n))
    if t=='E09':
        shapes=('square','triangle','circle')
        expected=([{f'{c}_{s}' for s in shapes} for c in COLORS], [{f'{c}_{s}' for c in COLORS} for s in shapes],
           [{'red_circle','green_triangle','blue_square'},{'red_triangle','green_square','blue_circle'},{'red_square','green_circle','blue_triangle'}])[i]
        def truth(src):
            groups=e.seq('groups',src);support=e.members('supported',src)
            if any(not isinstance(g,(list,tuple,set)) for g in groups):raise MissingEvidence('groups:malformed')
            flat=[n for g in groups for n in g]
            if len(set(flat))!=len(flat):raise MissingEvidence('groups:duplicate_identity')
            return {str(k): any(set(g)==target for g in groups) and target<=support and e.physical_all(target,source=src) for k,target in enumerate(expected)}
        if e.initial is None:raise MissingEvidence('initial_observation')
        return _dynamic(e,truth(e.initial),truth(o))
    if t=='E10':
        all_objects={f'{c}_{s}' for c in COLORS for s in ('square','triangle','circle')}
        red={n for n in all_objects if n.startswith('red_')};square={n for n in all_objects if n.endswith('_square')}
        chosen=(red,square,red|square)[i];threaded=e.members('threaded');support=e.members('supported_on_post')
        return e.count(sorted(chosen),lambda n:n in threaded&support and e.physical(n),len(threaded-chosen))
    if t=='E11':
        initial=e.seq('initial_grid');cells=e.mapping('object_cells');support=e.members('supported')
        if not sem._grid(initial):raise MissingEvidence('initial_grid:malformed')
        expected=(initial,[[initial[1][0],initial[0][0]],[initial[1][1],initial[0][1]]],[list(row)[::-1] for row in initial])[i]
        targets={n:[r,c] for r,row in enumerate(expected) for c,n in enumerate(row)}
        return e.count(targets,lambda n:cells.get(n)==targets[n] and sum(x==targets[n] for x in cells.values())==1 and n in support and e.physical(n))
    if t in ('E13','E31','E32','E33','E34','E44'):
        required={'E13':['camera_end','back_faces_operator','stand_supported'], 'E31':['relation','bowl_up','plate_up','contained_or_covering','contacts'],
          'E32':['delivered','moved_objects'], 'E33':['all_bottles','in_bin','on_table','supported_in_bin'],
          'E34':['handle_in_cell','supported'],'E44':['dihedral_angle_deg','base_table_contact_force','external_support_contacts','fold_samples']}[t]
        for key in required+['released','stable']:e.get(key)
        result=sem.check_task(t,v,o)
        return e.count(['complete'],lambda n:bool(result['success']))
    if t=='E14':
        initial=list(e.seq('initial_top_to_bottom'));edges=_edges(e)
        if len(initial)!=4 or len(set(initial))!=4:raise MissingEvidence('initial_top_to_bottom')
        target=([initial[1],initial[0],initial[2],initial[3]], [initial[0],initial[2],initial[1],initial[3]],initial[::-1])[i][::-1]
        initial_edges=set(zip(initial[::-1],initial[::-1][1:])); wanted=set(zip(target,target[1:])); changed=sorted(wanted-initial_edges)
        def valid(edge):return edge in edges and _grounded(edges,edge[0]) and e.physical_all(edge)
        errors=sum(not valid(p) for p in wanted&initial_edges)
        return e.count(changed,valid,errors)
    if t in ('E15','E16'):
        initial=e.mapping('initial'); final=e.mapping('final');names=list(initial)
        if len(names)!=(2 if t=='E15' else 3) or set(final)!=set(names):raise MissingEvidence('initial_final_identity')
        if t=='E15':
            other={names[0]:names[1],names[1]:names[0]};support=e.members('supported')
            return e.count(names,lambda n:_near(e.get('xy',source=final[n]),e.get('xy',source=initial[other[n] if i in (0,2) else n])) and
                _angle(e.get('yaw_deg',source=final[n]),e.get('yaw_deg',source=initial[other[n] if i in (1,2) else n])) and n in support and e.physical(n))
        inside=e.members('in_tray');support=e.members('supported_in_tray');good={}
        for n in names:good[n]=n in inside&support and _angle(e.get('yaw_deg',source=final[n]),e.get('yaw_deg',source=initial[n])+(90 if i==1 else 0)) and e.physical(n)
        score=sum((e.unit(n,20,good[n]) for n in names),Fraction(0));layout=False
        if all(good.values()):
            ci=[sum(initial[n]['xy'][a] for n in names)/3 for a in (0,1)];cf=[sum(final[n]['xy'][a] for n in names)/3 for a in (0,1)]
            layout=all(_near([final[n]['xy'][a]-cf[a] for a in (0,1)],[(initial[n]['xy'][a]-ci[a])*(-1 if i==2 and a==0 else 1) for a in (0,1)]) for n in names)
        e.cap=Fraction(60);return score+e.unit('relative_layout',40,layout)
    if t=='E17':
        names=[f'{c}_{s}' for c in ('blue','green') for s in ('square','triangle')]
        expected={n:('upper' if (n.startswith('blue') if i==0 else n.endswith('triangle') if i==1 else True) else 'lower') for n in names}
        layers=e.mapping('layers');support=e.mapping('support_layers')
        return e.count(names,lambda n:layers.get(n)==expected[n] and support.get(n)==expected[n] and e.physical(n))
    if t=='E18':
        opened=e.boolean('drawer_opened_for_access');delivered=e.members('delivered');remain=e.members('in_drawer');closed=e.boolean('drawer_closed');target=COLORS[i]
        valid=target in delivered and e.physical(target);extra=len(delivered-{target});delivery=max(0,60-30*extra) if valid else 0
        e.cap=Fraction(80)
        return e.unit('opened',20,opened)+e.unit('delivered',delivery,valid)+e.unit('closed_after_delivery',20,valid and closed and remain==set(COLORS)-{target} and e.boolean('drawer_closed_after_delivery'))
    if t=='E19':
        colors=(('yellow','white','red'),('red','yellow','white'),('white','red','yellow'))[i]
        expected=dict(zip(('sprite_bottle','water_bottle','cola_bottle'),colors));mapping=e.mapping('cap_for_bottle');seated=e.members('seated');contacts=_edges(e,'contacts')
        return e.count(expected,lambda n:mapping.get(n)==expected[n] and n in seated and ((n,'cap_'+expected[n]) in contacts or ('cap_'+expected[n],n) in contacts) and e.physical('cap_'+expected[n]))
    if t=='E20':
        colors=e.mapping('chip_colors');initial=e.mapping('initial_zone_members');final=e.mapping('zone_members');unmoved=e.members('unmoved_unused');support=e.members('supported')
        target=i+2;zones=dict(circle='yellow',square='red',triangle='blue');n=3*target-2; good=0;errors=set();used=set()
        for z,color in zones.items():
            old=set(e.seq(z,initial));members=set(e.seq(z,final));used|=members
            if len(old)!=(0 if z=='square' else 1) or any(colors.get(x)!=color for x in old):raise MissingEvidence('source_initial_counts')
            correct=sorted(x for x in members if colors.get(x)==color and x in support and e.physical(x))
            good+=max(0,min(len(correct)-len(old),target-len(old)))
            errors |= {x for x in members if colors.get(x)!=color} | (old-members)
            # Preserve originally present chips when deciding which excess IDs to charge.
            ordered=sorted(set(correct)&old)+sorted(set(correct)-old)
            errors |= set(ordered[target:])
        errors |= set(colors)-used-unmoved
        e.denominator=n;e.cap=Fraction(100*(n-1),n)
        e.units=[dict(id='added_correct',count=good,denominator=n),dict(id='violations',objects=sorted(errors))]
        return Fraction(100*max(0,good-len(errors)),n)
    if t=='E21':
        order=(['red','yellow','blue','green'],['red','green','blue','yellow'],['green','blue','yellow','red'])[i];slots=['top_left','top_right','bottom_left','bottom_right']
        prefix=_prefix_events(e,'placement_events',order,slots);cells=e.mapping('cells');support=e.members('supported')
        return e.count(order,lambda n:n in prefix and cells.get(n)==slots[order.index(n)] and n in support and e.physical(n))
    if t=='E22':
        expected=dict(zip((('red','green','blue'),('green','blue','red'),('blue','red','green'))[i],('front','left','right')))
        sides=e.mapping('object_sides');support=e.members('supported')
        if e.get('reference_frame')!='car':raise MissingEvidence('car_reference_frame')
        return e.count(expected,lambda n:sides.get(n)==expected[n] and n in support and e.physical(n))
    if t=='E23':
        expected=dict(zip((('red','green','blue'),('red','blue','green'),('blue','green','red'))[i],('high','middle','low')))
        branches=e.mapping('branch_for_cup');levels=e.mapping('branch_levels');threaded=e.members('mouth_contains_branch')
        return e.count(expected,lambda n:levels.get(branches.get(n))==expected[n] and n in threaded and e.physical(n))
    if t=='E24':
        order=(['red','green','blue'],['green','blue','red'],['blue','red','green'])[i]
        prefix=_prefix_events(e,'placement_events',order,['box']*3);inside=e.members('in_box');support=e.members('supported_in_box');good={}
        yarn=o.get('inference_rule_profile')=='e24-yarn-insertion-v1'
        if not yarn:up=e.members('upright');left=list(e.seq('left_to_right'))
        for n in order:
            present=[x for x in prefix if x in inside]
            layout_valid=True if yarn else (n in up and [x for x in left if x in present]==[x for x in order if x in present])
            good[n]=n in prefix and n in inside&support and layout_valid and e.physical(n)
        score=sum((e.unit(n,25,good[n]) for n in order),Fraction(0));closed=e.boolean('lid_closed');close=o['lid_close_step'] if 'lid_close_step' in o else e.get('lid_close_step')
        # None is a measured never-closed state, not absent evidence.
        events=e.seq('placement_events');last=max([x['step'] for x in events],default=-1)
        finish=all(good.values()) and closed and type(close)is int and close>last
        e.cap=Fraction(75);return score+e.unit('lid',25,finish)
    if t in ('E25','E27'):
        names=['spoon','knife','fork'] if t=='E25' else ['spoon','fork']
        if t=='E25':regions=dict.fromkeys(names,'far') if i<2 else dict(knife='left',spoon='right',fork='right');handles=dict.fromkeys(names,('plate','away_from_plate','operator')[i])
        else:regions=(dict(fork='left',spoon='right'),dict(spoon='left',fork='right'),dict(spoon='left',fork='left'))[i];handles=dict.fromkeys(names,'operator')
        actual=e.mapping('regions');directions=e.mapping('handle_toward');support=e.members('supported');outside=e.members('outside_plate') if t=='E27' else set(names)
        good={n:actual.get(n)==regions[n] and directions.get(n)==handles[n] and n in support&outside and e.physical(n) for n in names}
        if t=='E27' and i<2:return e.count(names,lambda n:good[n])
        score=sum((e.unit(n,20,good[n]) for n in names),Fraction(0))
        if t=='E25' and i<2:
            order=list(e.seq('far_left_to_right'))
            for a,b in [('spoon','knife'),('knife','fork')]:score+=e.unit(a+'<'+b,20,good[a] and good[b] and a in order and b in order and order.index(a)<order.index(b))
            e.cap=Fraction(80)
        else:
            order=list(e.seq('right_inner_to_outer' if t=='E25' else 'left_inner_to_outer'))
            score+=e.unit('inner_outer',40 if t=='E25' else 60,good['spoon'] and good['fork'] and order==['spoon','fork']);e.cap=Fraction(80 if t=='E25' else 40)
        return score
    return _score_later(e,t,v)


def _score_later(e,t,v):
    i='ABC'.index(v);o=e.o
    if t=='E26':
        events=e.seq('bell_events');counts={'left':0,'right':0};pending={'left':None,'right':None};presses={'left':0,'right':0};last=-1
        for event in events:
            side=e.get('side',str,event);kind=e.get('event',str,event);step=e.get('step',int,event)
            if side not in counts or kind not in ('press','release') or type(step)is not int or step<last or step<0:raise MissingEvidence('bell_events:malformed')
            if kind=='press':
                if pending[side] is not None:raise MissingEvidence('bell_events:double_press')
                if not e.boolean('contact',event):raise MissingEvidence('bell_events:untrusted_press')
                presses[side]+=1;pending[side]=step
            else:
                if pending[side] is None or step<=pending[side]:raise MissingEvidence('bell_events:orphan_release')
                counts[side]+=1;pending[side]=None
            last=step
        target=({'left':9,'right':1},{'left':1,'right':9},{'left':10,'right':0})[i];score=Fraction(0)
        forbidden=i==2 and presses['right']>0
        for side,n in target.items():
            for k in range(n):score+=e.unit(f'{side}_{k+1}',10,not forbidden and presses[side]<=n and counts[side]>k)
        e.cap=Fraction(90);return score
    if t in ('E28','E46'):
        chosen=({'yellow_rectangle'},{'white_yellow_round'},{'yellow_rectangle','white_yellow_round'})[i] if t=='E28' else {'yellow_block'}
        if t=='E28':inside=e.members('in_plate');support=e.members('supported_in_plate');face=e.members('same_visible_face');wrong=bool(inside-chosen)
        else:inside={'yellow_block'} if e.nullable('block_region')==('circle','triangle','square')[i] else set();support={'yellow_block'} if e.boolean('paper_supported') else set();face=chosen;wrong=False
        score=Fraction(0);total=len(chosen)
        for n in sorted(chosen):
            causal=e.causal(n);transport=e.boolean('transport_achieved',causal);chain=e.boolean('delivery_chain_valid',causal)
            start=Fraction(30 if t=='E28' else 40,total);finish=Fraction(70 if t=='E28' else 60,total)
            score+=e.unit(n+':transport',start,transport)
            score+=e.unit(n+':delivery',finish,transport and chain and not wrong and n in inside&support&face and e.physical(n))
        e.cap=Fraction(65 if t=='E28' and i==2 else 30 if t=='E28' else 40);return score
    if t=='E29':
        expected=(list(range(1,9)),list(range(8,0,-1)),list(range(1,9))+list(range(8,0,-1)))[i]
        events=e.seq('strike_events');pending=e.seq('pending_strikes')
        # The native collector appends on release, so concurrent contacts may
        # appear in a different order from their onsets. Complete, overlapping
        # contacts are physical sequence failures, not missing evidence.
        timeline=[];last_release=-1;seen=set();by_key={}
        for event in events:
            key=e.get('key',int,event);step=e.get('step',int,event);release=e.get('release_step',int,event);impulse=e.get('contact_impulse',source=event);tool=e.get('tool',str,event)
            if (type(key)is not int or key not in range(1,9) or type(step)is not int or step<0
                    or type(release)is not int or release<=step or release<last_release
                    or not sem._number(impulse) or impulse<=0 or tool!='mallet'
                    or (key,step) in seen):raise MissingEvidence('strike_events:malformed')
            seen.add((key,step));last_release=release
            timeline.append((step,release,key));by_key.setdefault(key,[]).append((step,release))
        for event in pending:
            step=e.get('step',int,event);key=e.get('key',int,event)
            if (type(step)is not int or step<0 or type(key)is not int or key not in range(1,9)
                    or (key,step) in seen):raise MissingEvidence('pending_strikes:malformed')
            seen.add((key,step));timeline.append((step,None,key));by_key.setdefault(key,[]).append((step,None))
        # A single key cannot have two simultaneous contact intervals in the
        # native collector. Preserve null for genuinely inconsistent evidence.
        for intervals in by_key.values():
            intervals.sort(key=lambda x:x[0])
            for previous,current in zip(intervals,intervals[1:]):
                if previous[1] is None or current[0]<=previous[1]:raise MissingEvidence('strike_events:malformed')
        timeline.sort(key=lambda x:(x[0],x[2]))
        prefix=0
        for index,(step,release,key) in enumerate(timeline):
            if prefix==len(expected):break
            # Only notes fully separated before the next onset enter the
            # correct prefix. Pending or simultaneous notes cannot earn credit.
            if release is None or key!=expected[prefix]:break
            if index+1<len(timeline) and timeline[index+1][0]<=release:break
            prefix+=1
        if prefix==len(expected) and len(timeline)>len(expected):prefix-=1
        return e.count(range(len(expected)),lambda k:k<prefix)
    if t=='E30':
        joints=e.mapping('joint_displacements_m');expected=({'upper'},{'lower'},{'upper','lower'})[i]
        for x in ('upper','lower'):
            if not sem._number(e.get(x,source=joints)) or joints[x]<0:raise MissingEvidence('joint_displacements_m')
        guard=all(joints[x]<=.005 for x in {'upper','lower'}-expected)
        opened=None
        if o.get('drawer_initial_revision')=='embodied50-execution-v3-20261102':
            if not e.boolean('drawer_initial_state_valid'):raise MissingEvidence('declared_drawer_initial_state_invalid')
            opened=e.members('opened_with_contact');closed=e.members('closed_with_contact')
            guard=guard and {'upper','lower'}-expected<=closed
        return e.count(sorted(expected),lambda n:guard and joints[n]>=.015 and (opened is None or n in opened) and e.physical(n))
    if t=='E36':
        inside=e.members('in_box');support=e.members('supported_in_box');n=i+1;valid=[x for x in inside&support if e.physical(x)]
        return e.count(range(n),lambda k:len(inside)<=n and k<len(valid))
    if t=='E37':
        chosen=({'left'},{'right'},{'left','right'})[i];separated=e.members('separated');loosen=e.mapping('screw_progress');remaining=e.members('remaining_fastened');e.members('initial_fastened')
        wrong=bool(({'left','right'}-chosen)-remaining);score=Fraction(0)
        for n in sorted(chosen):
            valid=e.boolean(n,loosen);score+=e.unit(n+':loosen',Fraction(40,len(chosen)),valid)
            score+=e.unit(n+':separate',Fraction(60,len(chosen)),valid and not wrong and n in separated and e.physical(n,support=False))
        e.cap=Fraction(70 if i==2 else 40);return score
    if t=='E38':
        expected=(['red','green','blue'],['red','blue','green'],['blue','green','red'])[i];order=list(e.seq('bottom_to_top'));posts=e.mapping('post_for_ring');threaded=e.members('threaded');edges=_edges(e);prefix=0
        order=[n for n in order if n in threaded and posts.get(n)=='rightmost']
        for k,n in enumerate(expected):
            lower='rightmost' if not k else expected[k-1]
            if k>=len(order) or order[k]!=n or posts.get(n)!='rightmost' or n not in threaded or (lower,n) not in edges or not e.physical(n):break
            prefix+=1
        return e.count(expected,lambda n:expected.index(n)<prefix)
    if t=='E39':
        ref=list(e.seq('reference_order'));initial=list(e.seq('initial_order'));final=list(e.seq('final_order'));ry=e.mapping('reference_yaws');iy=e.mapping('initial_yaws');fy=e.mapping('final_yaws');support=e.members('supported');changed=e.boolean('reference_changed')
        if len(ref)!=3 or len(set(ref))!=3 or set(initial)!=set(ref) or set(final)!=set(ref):raise MissingEvidence('reference_order:identities')
        need={};keep={};done={}
        for n in ref:
            target_pos=initial.index(n) if i==1 else ref.index(n);target_yaw=iy[n] if i==0 else ry[n]
            initial_ok={'position':initial.index(n)==target_pos,'yaw':_angle(iy[n],target_yaw)}
            final_ok={'position':final.index(n)==target_pos,'yaw':_angle(fy[n],target_yaw)}
            for attr in ('position','yaw'):
                k=n+':'+attr
                if initial_ok[attr]:keep[k]=final_ok[attr]
                else:need[k]=n;done[k]=final_ok[attr] and n in support and e.physical(n)
        damage=sum(not ok for ok in keep.values())
        return e.count(need,lambda key:done[key] and not changed,damage)
    if t=='E40':
        chosen=({'circle','cross'},{'square','triangle'},{'circle','triangle','cross'})[i];markers=e.members('clipped_markers');records=e.mapping('clip_records');valid={};clip_ids={}
        for rec in records.values():_require_clip_measurements(rec)
        for marker in markers:
            rec=e.get(marker,Mapping,records);clip_id=e.get('clip_id',str,rec);clip_ids[marker]=clip_id
            valid[marker]=sem._clip_record(rec) and e.physical(clip_id)
        duplicates={cid for cid in clip_ids.values() if list(clip_ids.values()).count(cid)>1}
        wrong=sum(bool(valid[x]) for x in markers-chosen)
        return e.count(sorted(chosen),lambda n:bool(valid.get(n,False) and clip_ids[n] not in duplicates),wrong)
    if t=='E41':
        expected=(dict(short='long',medium='medium',long='short'),dict(short='short',medium='medium',long='long'),dict(short='long',medium='short',long='medium'))[i]
        extensions=e.mapping('extensions');gaps=e.mapping('end_gaps_m');axes=e.mapping('axis_alignment_cos');support=e.members('progress_supported_rows');identities=e.mapping('extension_object_ids')
        def valid(n):
            if n not in extensions:return False
            gap=e.get(n,source=gaps);axis=e.get(n,source=axes);obj=e.get(n,str,identities)
            if not sem._number(gap) or not sem._number(axis):raise MissingEvidence('extension_geometry')
            return extensions[n]==expected[n] and 0<=gap<=.015 and math.cos(math.radians(10))<=abs(axis)<=1 and n in support and list(identities.values()).count(obj)==1 and e.physical(obj)
        return e.count(expected,valid)
    if t=='E42':
        balls=list(e.seq('ball_ids'));regions=e.mapping('ball_regions');support=e.members('supported');target=('circle','triangle','square')[i]
        if len(balls)!=2 or len(set(balls))!=2:raise MissingEvidence('ball_ids')
        return e.count(balls,lambda n:e.boolean('delivery_chain_valid',e.causal(n)) and e.boolean('transport_achieved',e.causal(n)) and regions.get(n)==target and n in support and e.physical(n))
    if t=='E43':
        release=e.nullable('release');trace=e.seq('trajectory');regions=e.mapping('region_bounds');launcher=e.boolean('launcher_moved')
        if release is None and not trace:
            e.cap=Fraction(40);return Fraction(0)
        if not isinstance(release,Mapping):raise MissingEvidence('release:malformed')
        release_id=e.get('release_id',source=release)
        if not isinstance(release_id,(str,int)):raise MissingEvidence('release_id')
        if not trace:e.cap=Fraction(40);return Fraction(0)
        if not sem._steps(trace,minimum=1):raise MissingEvidence('trajectory:noncontinuous')
        for s in trace:
            if e.get('release_id',source=s)!=release_id:raise MissingEvidence('trajectory:release_mismatch')
            if not sem._vector(e.get('pos',source=s),3):raise MissingEvidence('trajectory:position')
        valid=(e.get('source',source=release)=='fixed_launcher' and e.boolean('initially_held',release) and e.boolean('released',release) and not launcher)
        direct=False
        for s in trace:
            force=e.get('hand_contact_force',source=s);guide=e.get('guide_contact_force',source=s)
            if not sem._number(force) or force<0 or not sem._number(guide) or guide<0:raise MissingEvidence('trajectory:force')
            direct |= force>0
        deflection=None
        if valid and not direct:
            for j in range(1,len(trace)-1):
                s=trace[j]
                if s['guide_contact_force']<=0 or not e.boolean('guide_held',s):continue
                a=[s['pos'][k]-trace[j-1]['pos'][k] for k in (0,1)];b=[trace[j+1]['pos'][k]-s['pos'][k] for k in (0,1)];na=math.hypot(*a);nb=math.hypot(*b)
                if na>1e-6 and nb>1e-6 and sum(x*y for x,y in zip(a,b))/(na*nb)<math.cos(.02):deflection=j;break
        crossing=False
        if deflection is not None:
            region=e.get(('circle','triangle','square')[i],Mapping,regions);low=e.get('min',source=region);high=e.get('max',source=region)
            if not sem._vector(low,2) or not sem._vector(high,2):raise MissingEvidence('region_bounds')
            crossing=any(sem._segment_rectangle(a['pos'],b['pos'],low,high) for a,b in zip(trace[deflection:-1],trace[deflection+1:]))
        e.cap=Fraction(40);return e.unit('deflection',40,deflection is not None)+e.unit('crossing',60,crossing)
    if t=='E45':
        balls=list(e.seq('initial_in_cup'));positions=e.mapping('ball_compartments');support=e.members('supported_in_compartment');remaining=e.members('in_cup');target=('circle','triangle','square')[i]
        if len(balls)!=3 or len(set(balls))!=3:raise MissingEvidence('initial_in_cup')
        good={n:e.boolean('poured_exit_valid',e.causal(n)) and e.boolean('delivery_chain_valid',e.causal(n)) and positions.get(n)==target and n in support and e.physical(n) for n in balls}
        score=sum((e.unit(n,30,good[n]) for n in balls),Fraction(0))
        finish=all(good.values()) and not remaining and e.boolean('cup_on_table') and e.boolean('cup_released') and e.physical('cup')
        e.cap=Fraction(90);return score+e.unit('cup_finished',10,finish)
    if t in ('E47','E48','E49'):
        flipped=e.members('flipped')
        if t=='E47':
            colors=e.mapping('initial_face_colors');inside=e.members('in_box');support=e.members('supported_in_box');down=e.members('face_down')
            if set(colors)!=set(CARDS) or any(c not in ('red','black') for c in colors.values()) or {colors[x] for x in CARDS[:2]}!={'red','black'}:raise MissingEvidence('initial_face_colors')
            chosen=({n for n in CARDS[:2] if colors[n]==('red','black')[i]} if i<2 else set(CARDS[:2]))
            rear=set(CARDS[2:]);reveal_guard=not (flipped&rear) and rear<=down
            score=sum((e.unit(n+':flip',10,n in flipped and reveal_guard) for n in CARDS[:2]),Fraction(0))
            both=set(CARDS[:2])<=flipped;extra=bool(inside-chosen)
            for n in sorted(chosen):score+=e.unit(n+':delivery',Fraction(80,len(chosen)),both and not extra and n in inside&support and e.physical(n))
            e.cap=Fraction(80);return score
        if t=='E48':
            chosen=CARDS[:i+1];slots=e.mapping('slot_for_card');inserted=e.members('physically_inserted');inside=e.members('in_slot');valid={}
            for n in chosen:
                if n in flipped&inserted&inside and n in slots and e.physical(n):
                    slot=slots[n]
                    if not isinstance(slot,str) or not slot:raise MissingEvidence('slot_for_card:identity')
                    valid[n]=slot
            counts={s:sum(x==s for x in valid.values()) for s in set(valid.values())};best=min(counts,key=lambda s:(-counts[s],s)) if counts else None
            score=sum((e.unit(n+':flip',Fraction(20,len(chosen)),n in flipped)+e.unit(n+':insert',Fraction(80,len(chosen)),n in valid and valid[n]==best) for n in chosen),Fraction(0))
            extra=len(flipped-set(chosen));score=max(Fraction(0),score-Fraction(100*extra,len(chosen)))
            e.units.append(dict(id='extra_flips',objects=sorted(flipped-set(chosen)),penalty_numerator=100*extra,penalty_denominator=len(chosen)))
            e.cap=(Fraction(20),Fraction(60),Fraction(220,3))[i];return score
        target=dict(zip(CARDS[:3],(('green','blue','red'),('green','red','blue'),('red','blue','green'))[i]));trays=e.mapping('tray_for_card');support=e.members('supported');untouched=e.members('untouched')
        return e.count(CARDS[:3],lambda n:n in flipped and trays.get(n)==target[n] and n in support and e.physical(n),len(set(CARDS[3:])-untouched))
    if t=='E50':
        sequence=e.o.get('clip_sequence')
        if sequence is not None:_require_clip_measurements(sequence)
        flipped=e.boolean('card_flipped');causal=e.causal('card');gripped=e.boolean('clip_grip_achieved',causal);transport=e.boolean('transport_achieved',causal);chain=e.boolean('delivery_chain_valid',causal)
        if gripped and sequence is None:raise MissingEvidence('clip_sequence')
        grip=flipped and gripped;transport=grip and transport
        delivery=transport and chain and e.nullable('card_tray')==('green','blue','red')[i] and e.boolean('card_released') and e.boolean('tray_supported') and e.physical('card')
        returned=delivery and e.boolean('clip_return_after_delivery',causal) and e.boolean('clip_on_table') and e.physical('binder_clip')
        e.cap=Fraction(90)
        return sum((e.unit(n,w,good) for n,w,good in [('flip',10,flipped),('grip',20,grip),('transport',30,transport),('delivery',30,delivery),('return',10,returned)]),Fraction(0))
    raise ValueError('Unknown task '+t)


def _unpack(value):
    """Accept either a native envelope or a private observation with status map."""
    if isinstance(value,Mapping) and value.get('schema')=='videoicl-native-progress-evidence-v2':
        obs=deepcopy(value.get('observation',{}))
        if not isinstance(obs,Mapping):return obs,value.get('initial'),False
        obs['progress_physical']=deepcopy(value.get('object_status',{}))
        ranks=obs.get('rank_label_map',{})
        for rank,label in ranks.items():
            if label in obs['progress_physical']:obs['progress_physical'][str(rank)]=obs['progress_physical'][label]
        return obs,value.get('initial'),value.get('history_valid') is True
    return deepcopy(value),None,True


def score_progress(task,variant,observation,*,initial_observation=None,history_valid=True):
    """Return task-specific raw score and witnesses; never expose to the actor.

    ``observation`` may be a videoicl-native-progress-evidence-v2 envelope.
    Native success is deliberately not an argument: callers apply the native
    success/full-score authority and returned failure_ceiling_100 separately.
    """
    if task not in {f'E{i:02d}' for i in range(1,51)} or variant not in ('A','B','C'):
        raise ValueError('Expected E01-E50 and variant A/B/C')
    obs,embedded_initial,trusted=_unpack(observation)
    initial=initial_observation if initial_observation is not None else embedded_initial
    if isinstance(initial,Mapping) and 'observation' in initial:
        initial_obs=deepcopy(initial['observation'])
        if isinstance(initial_obs,Mapping):
            initial_obs['progress_physical']=deepcopy(initial.get('object_status',{}))
            initial=initial_obs
        else:initial=None
    elif initial is not None:
        initial,_,initial_valid=_unpack(initial)
        trusted=trusted and initial_valid
    e=Evidence(obs,initial)
    base=dict(protocol=PROTOCOL,task=task,variant=variant,task_score_100=None,
        progress_available=False,units=[],missing_evidence=[],failure_ceiling_100=None,
        score_is_raw_before_native_gate=True,native_physics_verified=False)
    try:
        if isinstance(observation,Mapping) and observation.get('schema')=='videoicl-native-progress-evidence-v2' and (observation.get('task')!=task or observation.get('variant')!=variant):raise MissingEvidence('native_evidence_identity_mismatch')
        if history_valid is not True or not trusted:raise MissingEvidence('history_invalid_or_untrusted')
        if (task in ('E07','E09','E39') and isinstance(observation,Mapping)
                and observation.get('schema')=='videoicl-native-progress-evidence-v2'
                and (not isinstance(embedded_initial,Mapping) or embedded_initial.get('sealed') is not True)):
            raise MissingEvidence('initial_denominator_not_sealed')
        if not isinstance(obs,Mapping):raise MissingEvidence('observation:malformed')
        raw=Fraction(_score(e,task,variant))
        if not 0<=raw<=100:raise MissingEvidence('rubric_score_out_of_range')
        if e.cap is None:raise MissingEvidence('failure_ceiling_not_defined')
        base.update(task_score_100=float(raw),progress_available=True,units=e.units,
            raw_score_numerator=raw.numerator,raw_score_denominator=raw.denominator,
            failure_ceiling_100=float(e.cap),failure_ceiling_numerator=e.cap.numerator,
            failure_ceiling_denominator=e.cap.denominator,required_change_count=e.denominator)
    except MissingEvidence as exc:
        base['missing_evidence']=[str(exc)];base['units']=e.units
    except (KeyError,TypeError,ValueError,IndexError,ZeroDivisionError,OverflowError) as exc:
        base['missing_evidence']=['malformed_native_evidence:'+type(exc).__name__]
    return base
