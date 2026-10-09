"""One process owns one GL context and simulation. JSON-lines private IPC."""
import contextlib
import json
import sys
import traceback

def main():
    env=None
    for line in sys.stdin:
        try:
            req=json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                if req['op']=='init':
                    from .catalog import task_spec
                    from .environment import DesktopDual
                    env=DesktopDual(task_spec(req['task'],req['variant']),seed=req['seed'])
                    result={'ready':True}
                elif req['op']=='observe': result={'images':env.images()}
                elif req['op']=='action':
                    env.action(req['left'],req['right']); result={'ok':True}
                elif req['op']=='score': result=env.score()
                elif req['op']=='close':
                    if env: env.close()
                    result={'closed':True}
                else: raise ValueError('Unknown operation')
            print(json.dumps({'result':result}),flush=True)
            if req['op']=='close': break
        except Exception:
            traceback.print_exc(file=sys.stderr)
            print(json.dumps({'error':'Simulation operation failed; see private worker log'}),flush=True)
    if env:
        with contextlib.redirect_stdout(sys.stderr): env.close()

if __name__=='__main__': main()
