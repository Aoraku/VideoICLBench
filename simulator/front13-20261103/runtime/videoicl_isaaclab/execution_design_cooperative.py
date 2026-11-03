"""Same-thread engineering references sharing the unchanged native barrier.

Workers yield only at a public action boundary. No simulator API runs on a
background thread, and a new tick cannot begin until every active room supplies
its own real action. Importing this module starts nothing.
"""
import json
import threading
from pathlib import Path

# Reviewed generated placement routes only. Complex front-half workflows keep
# serialized reference execution until their own action-boundary audit passes.
FRONT_GENERATED_TASKS=frozenset(('E05','E11','E13','E14','E15','E16','E21','E22','E25'))

FRONT_STRUCTURAL_TASKS=frozenset(('E08',))
FRONT_WORKFLOW_TASKS=frozenset(('E17','E20'))

def enabled_for(controllers,environ):
    """Explicit, fresh engineering invocation only; no production opt-in."""
    value=environ.get('VIC_ENGINEERING_COOPERATIVE_REFERENCES','0')
    if value=='0':return False
    if value!='1':raise ValueError('Invalid engineering cooperative opt-in')
    from .execution_design import REVISION_V3
    for c in controllers.values():
        spec=c.scene.spec;design=spec.get('execution_design',{})
        task=spec.get('id','')
        if task not in ({f'E{i:02}'for i in range(26,51)}|FRONT_GENERATED_TASKS|FRONT_STRUCTURAL_TASKS|FRONT_WORKFLOW_TASKS) or design.get('revision')!=REVISION_V3:
            raise ValueError('Cooperative references require reviewed explicit v3 engineering cases')
        if task in FRONT_GENERATED_TASKS|FRONT_STRUCTURAL_TASKS:
            if spec.get('author_smooth_recording',False):
                raise ValueError('Front-half cooperative references require public discrete actions')
            if not spec.get('goals') or any(g.get('type')!='place' for g in spec['goals']):
                raise ValueError('Front-half cooperative references require reviewed placement goals')
        if task in FRONT_STRUCTURAL_TASKS:
            # StructuralAuthor's non-smooth route is all public act except
            # optional idle-arm parking and pre-grasp yaw helpers. Reject
            # those options before workers can bypass the shared barrier.
            embodiment=getattr(c.scene,'embodiment',None)
            config=getattr(embodiment,'config',None)
            if not isinstance(config,dict):raise ValueError('Measured E08 embodiment configuration required')
            if config.get('author_recording',{}).get('clear_idle_arm',False):
                raise ValueError('E08 continuous idle-arm parking is not cooperative')
            grasps=spec.get('semantic',{}).get('structural_grasps',{})
            if not grasps or any(g.get('pre_grasp_task_yaw_rad',0)!=0 for g in grasps.values()):
                raise ValueError('E08 continuous pre-grasp yaw is not cooperative')
        if task in FRONT_WORKFLOW_TASKS:
            if spec.get('author_smooth_recording',False):
                raise ValueError('Workflow cooperative references require public discrete actions')
            config=getattr(getattr(c.scene,'embodiment',None),'config',None)
            if not isinstance(config,dict):raise ValueError('Measured workflow embodiment configuration required')
            recording=config.get('author_recording',{})
            if recording.get('clear_idle_arm',False)or recording.get('pre_grasp_opening_m')is not None:
                raise ValueError('Workflow direct idle-arm or gripper preparation is not cooperative')
            grasps={**spec.get('semantic',{}).get('structural_grasps',{}),**design.get('grasps',{})}
            if not grasps or any(g.get('pre_grasp_task_yaw_rad',0)!=0 for g in grasps.values()):
                raise ValueError('Workflow continuous pre-grasp yaw is not cooperative')
    return True

class CooperativeReferences:
    def __init__(self,pool,out):
        from greenlet import getcurrent
        self.pool=pool;self.out=Path(out);self.parent=getcurrent()
        self.thread=threading.get_ident();self.workers={};self.batches=0

    def submit(self,room,command):
        from greenlet import getcurrent
        if threading.get_ident()!=self.thread or self.workers.get(room)is not getcurrent():
            raise RuntimeError('Engineering action must yield from its own same-thread reference')
        if room in self.pool.terminal:raise RuntimeError('Engineering room already sealed')
        # Reject a bad reference command before it can poison a sibling batch.
        self.pool.controllers[room].validate_action(**command)
        return self.parent.switch(dict(kind='public_action',room=room,command=dict(command)))

    def run(self,jobs):
        from greenlet import greenlet,getcurrent
        if getcurrent()is not self.parent or threading.get_ident()!=self.thread:
            raise RuntimeError('Native barrier must run on its original thread')
        if self.workers:raise RuntimeError('Engineering scheduler is single-use')
        if set(jobs)!=set(self.pool.controllers)-set(self.pool.terminal):
            raise ValueError('One reference is required for every active native room')
        self.workers={room:greenlet(job,parent=self.parent)for room,job in jobs.items()}
        pending={}
        def accept(room,event):
            worker=self.workers[room]
            if worker.dead:
                if room not in self.pool.terminal:raise RuntimeError('Reference returned without native terminal seal')
                return
            if not isinstance(event,dict)or event.get('kind')!='public_action'or event.get('room')!=room:
                raise RuntimeError('Reference yielded outside its public action boundary')
            pending[room]=event['command']
        try:
            for room,worker in self.workers.items():accept(room,worker.switch())
            while pending:
                active=set(self.pool.controllers)-set(self.pool.terminal)
                if set(pending)!=active:raise RuntimeError('Missing active reference at native barrier')
                commands=pending;pending={}
                receipts=self.pool.action_batch(commands)
                if set(receipts)!=set(commands):raise RuntimeError('Native receipt identities differ from commands')
                self.batches+=1
                path=self.out/'cooperative-barrier-actions.private.jsonl'
                with path.open('a')as stream:
                    from .execution_design_native_capture import _json
                    stream.write(json.dumps(dict(engineering_only=True,batch=self.batches,
                        commands=commands,receipts=receipts),default=_json)+'\n')
                path.chmod(0o600)
                # All references observe the same completed physical batch;
                # no further physics advances during these same-thread calls.
                for room,receipt in receipts.items():accept(room,self.workers[room].switch(receipt))
        except BaseException as error:
            # Preserve each case's own final capture via its normal finally.
            # Never retry a possibly partially accepted native action batch.
            for worker in self.workers.values():
                if not worker.dead:
                    try:worker.throw(RuntimeError('Shared engineering batch aborted: '+type(error).__name__))
                    except BaseException:pass
            raise
        if not all(worker.dead for worker in self.workers.values()):
            raise RuntimeError('Reference did not terminate at final barrier')
        return dict(mode='same_thread_cooperative_public_actions',native_batches=self.batches,
            model_launch_enabled=False)


def verify_private_dependency(vendor, expected_hashes=None):
    """CPU-only ABI/import/yield roundtrip; never import Isaac or create a pool."""
    import hashlib
    import importlib
    import platform
    import sys
    vendor=Path(vendor).resolve(strict=True)
    if not vendor.is_dir():raise RuntimeError('Private engineering vendor is not a directory')
    hashes={}
    if not expected_hashes:raise ValueError('Verified private dependency manifest is required')
    for name,digest in expected_hashes.items():
        path=(vendor/name).resolve(strict=True)
        if not path.is_relative_to(vendor)or not path.is_file():raise ValueError('Dependency path escapes private vendor')
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        if actual!=digest:raise ValueError('Private dependency checksum mismatch: '+name)
        hashes[name]=actual
    if 'greenlet/__init__.py'not in hashes:raise ValueError('Private greenlet package missing from verified manifest')
    previous=list(sys.path)
    try:
        sys.path.insert(0,str(vendor))
        package=importlib.import_module('greenlet')
        extension=importlib.import_module('greenlet._greenlet')
        paths={key:Path(module.__file__).resolve(strict=True)for key,module in [('package',package),('extension',extension)]}
        for key,path in paths.items():
            if not path.is_relative_to(vendor)or str(path.relative_to(vendor))not in hashes:
                raise RuntimeError('Imported dependency is not the verified private '+key)
        parent=package.getcurrent();thread=threading.get_ident();events=[]
        def worker():
            if threading.get_ident()!=thread:raise RuntimeError('Greenlet changed OS thread')
            events.append('worker_yield');value=parent.switch('yielded')
            if value!='resume' or threading.get_ident()!=thread:raise RuntimeError('Greenlet resumed incorrectly')
            events.append('worker_return');return 'finished'
        child=package.greenlet(worker,parent=parent)
        if child.switch()!='yielded' or child.dead:raise RuntimeError('Greenlet first yield failed')
        if child.switch('resume')!='finished' or not child.dead:raise RuntimeError('Greenlet resume failed')
        return dict(passed=True,version=package.__version__,python=sys.version,
                    interpreter=sys.executable,cache_tag=sys.implementation.cache_tag,
                    machine=platform.machine(),module_paths={k:str(v)for k,v in paths.items()},
                    extension_sha256=hashlib.sha256(paths['extension'].read_bytes()).hexdigest(),
                    verified_files=len(hashes),same_thread_yield_resume=events,
                    simulator_imported=any(k in sys.modules for k in ('isaacsim','omni.isaac','isaaclab')),
                    gpu_or_simulation_started=False)
    finally:sys.path[:]=previous
