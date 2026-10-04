"""Reference plans continue through native message commands, never state writes."""
from functools import wraps
import json
from vic_apps import cross_platform


def apply_command(native_apply,state,op,target='',value='',ids=None):
    if op.startswith('handoff.'):
        return cross_platform.apply(state,op,target,value,ids)
    return native_apply(state,op,target,value,ids)


def handoff_commands(state):
    if not state.get('cross_platform'):return
    for request in state['cross_platform']['requests']:
        if request['revision']!=2:continue
        resources=[r['id'] for r in cross_platform.resources(state) if r['scope']==request['scope']]
        yield 'handoff.send',request['id'],dict(recipient=request['recipient'],resources=resources)


def with_handoffs(native_apply,tuple_size=3):
    def decorator(fn):
        @wraps(fn)
        def wrapped(initial,variant):
            state=initial
            for command in fn(initial,variant):
                yield command
                op,target,data=command[:3]
                state=apply_command(native_apply,state,op,target,json.dumps(data),command[3] if len(command)==4 else None)
            for command in handoff_commands(state):
                yield command if tuple_size==3 else (*command,[])
        return wrapped
    return decorator


def redeliver(state):
    if not state.get('cross_platform'):return state
    for receipt in list(state['cross_platform']['receipts']):
        state=cross_platform.apply(state,'handoff.withdraw',receipt['id'])
    for op,target,data in handoff_commands(state):
        state=cross_platform.apply(state,op,target,json.dumps(data))
    return state
