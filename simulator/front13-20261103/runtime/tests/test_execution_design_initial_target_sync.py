"""CPU snapshot derivation audits only; not native physics acceptance."""
from copy import deepcopy
from pathlib import Path
import math
import numpy as np
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
from videoicl_isaaclab.realworld_evaluator_selector import create_evaluator
from videoicl_isaaclab.realworld_native_evidence import NativeTaskEvaluator
from videoicl_isaaclab.realworld_progress_evidence import seal_initial
BINDINGS=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json'
TASKS=('E14','E15','E16','E22','E31','E41')
def yaw(a):
    c,s=math.cos(a),math.sin(a)
    return np.array([[c,-s,0],[s,c,0],[0,0,1.]])
def initial(spec):
    return {o['id']:dict(pos=np.array([*o['xy'],o.get('center_z',o['bottom']+o['size'][2])]),mat=yaw(o.get('yaw',0)),grasp=(False,False))for o in spec['objects']}
def tick(e,state,contacts):
    for _ in range(8):e.update(deepcopy(state),set(contacts),.1)
    assert e.history_valid,e.errors
    return e.observation,e.last['checks']
@pytest.mark.parametrize('task',TASKS)
@pytest.mark.parametrize('variant',list('ABC'))
@pytest.mark.parametrize('seed',(4201,4202,4203))
@pytest.mark.parametrize('condition',('I','E'))
def test_changed_inputs_reach_native_evaluator(task,variant,seed,condition):
    old=load(task,variant,0,BINDINGS,verify_files=False)
    spec=apply_execution_inputs(old,condition=condition,seed=seed,revision=REVISION_V3)
    e=create_evaluator(spec);assert isinstance(e,NativeTaskEvaluator)
    state=initial(spec);start=deepcopy(state);contacts={frozenset((n,'table'))for n in state}
    if task=='E14':
        order=sorted(state,key=lambda n:state[n]['pos'][2])
        contacts={frozenset((a,b))for a,b in zip(['table']+order,order)}
    tick(e,state,contacts)
    seal_initial(e)
    assert e.progress_initial_sealed
    assert e.progress_initial_objects=={n:dict(pos=start[n]['pos'].tolist(),mat=start[n]['mat'].tolist(),grasp=list(start[n]['grasp']))for n in start}
    for n in state:assert np.array_equal(e.initial[n]['pos'],start[n]['pos'])
    if task=='E14':
        names=e.group('blocks');top=sorted(names,key=lambda n:start[n]['pos'][2],reverse=True)
        desired={'A':[top[1],top[0],top[2],top[3]],'B':[top[0],top[2],top[1],top[3]],'C':top[::-1]}[variant]
        contacts=set();height=.8;below='table'
        for n in desired[::-1]:
            half=e.objects[n]['size'][2];state[n]['pos'][2]=height+half;height+=half*2
            contacts.add(frozenset((below,n)));below=n
        obs,checks=tick(e,state,contacts)
        assert obs['initial_top_to_bottom']==[e.label(n)for n in top]
        assert checks['top_indexed_reordering'] and checks['physical_support_chain']
        assert top!=[o['id']for o in sorted(old['objects'],key=lambda o:o['bottom'],reverse=True)]
    elif task=='E15':
        a,b=e.group('blocks');other={a:b,b:a}
        for n in(a,b):
            state[n]['pos'][:2]=start[other[n]if variant in'AC'else n]['pos'][:2]
            state[n]['mat']=start[other[n]if variant in'BC'else n]['mat'].copy()
        obs,checks=tick(e,state,contacts)
        assert checks['position_swap_or_preservation'] and checks['orientation_swap_or_preservation']
        for n in(a,b):assert obs['initial'][e.label(n)]['xy']==start[n]['pos'][:2].tolist()
        legacy=initial(old)
        for n in(a,b):
            state[n]['pos'][:2]=legacy[other[n]if variant in'AC'else n]['pos'][:2]
            state[n]['mat']=legacy[other[n]if variant in'BC'else n]['mat'].copy()
        _,wrong=tick(e,state,contacts)
        assert not(wrong['position_swap_or_preservation']and wrong['orientation_swap_or_preservation'])
    elif task=='E16':
        names=e.group('pieces');center=np.mean([start[n]['pos'][:2]for n in names],axis=0);tray=start['tray']['pos'][:2]
        for n in names:
            relative=start[n]['pos'][:2]-center
            if variant=='C':relative[0]*=-1
            state[n]['pos'][:2]=tray+relative
            state[n]['mat']=yaw(math.pi/2 if variant=='B'else 0)@start[n]['mat']
        obs,checks=tick(e,state,contacts)
        assert checks['relative_positions'] and checks['individual_orientations']
        for n in names:assert obs['initial'][e.label(n)]['xy']==start[n]['pos'][:2].tolist()
        state[names[0]]['pos'][0]+=.05
        _,wrong=tick(e,state,contacts);assert not wrong['relative_positions']
    elif task=='E22':
        car=e.semantic['car'];axes=np.asarray(e.semantic['car_frame'])
        labels={'A':('red','green','blue'),'B':('green','blue','red'),'C':('blue','red','green')}[variant]
        names={e.label(n):n for n in e.group('blocks')}
        for label,offset in zip(labels,([.13,0,0],[0,.13,0],[0,-.13,0])):
            state[names[label]]['pos'][:2]=(start[car]['pos']+start[car]['mat']@axes@np.asarray(offset))[:2]
        _,checks=tick(e,state,contacts);assert checks['car_side_mapping']
        state[car]['mat']=initial(old)[car]['mat']
        _,wrong=tick(e,state,contacts);assert not wrong['car_side_mapping']
    elif task=='E31':
        moving,support=e.semantic['moving'],e.semantic['support']
        state[moving]['pos'][:2]=state[support]['pos'][:2]
        state[moving]['pos'][2]=state[support]['pos'][2]+e.objects[support]['size'][2]+e.objects[moving]['size'][2]
        if variant=='C':state['plate']['mat']=np.diag([1.,-1.,-1.])
        contacts.add(frozenset(('bowl','plate')))
        _,checks=tick(e,state,contacts)
        assert checks['container_relation'] and checks['plate_face_orientation'] and checks['real_bowl_plate_contact']
        assert next(z for z in spec['zones']if z['id']=='support_center')['xy']==start[support]['pos'][:2].tolist()
        state[moving]['pos'][:2]+=np.array([.3,0])
        _,wrong=tick(e,state,contacts);assert not wrong['containment_or_rim_coverage']
    else:
        for ref,piece in e.semantic['mapping'].items():
            endpoint=start[ref]['pos']+start[ref]['mat']@np.asarray(e.semantic['end_points'][ref])
            state[piece]['pos']=endpoint-state[piece]['mat']@np.asarray(e.semantic['start_points'][piece])+np.array([-.001,0,0])
        obs,checks=tick(e,state,contacts)
        assert checks['length_pairing'] and checks['endpoints_adjacent'] and checks['axes_collinear']
        assert all(abs(gap-.001)<1e-10 for gap in obs['end_gaps_m'].values())
        assert e.semantic['end_points']!=old['semantic']['end_points']
        state[next(iter(e.semantic['mapping'].values()))]['pos'][0]-=.04
        _,wrong=tick(e,state,contacts);assert not wrong['endpoints_adjacent']
