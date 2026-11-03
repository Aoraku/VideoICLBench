"""Lossless private measurement capture for isolated engineering controls.

This records the evaluator's native substep inputs without changing physics or
scoring. It never launches a process, changes a task, or grants model admission.
The resulting evidence is diagnostic until reviewed against the release gate.
"""
import gzip
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path


def _json(value):
    if hasattr(value, 'tolist'):
        return value.tolist()
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    raise TypeError(type(value).__name__)


def _write(path, value):
    path.write_text(json.dumps(value, default=_json, ensure_ascii=False, indent=2)+'\n')
    path.chmod(0o600)


def _artifact(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024), b''):
            h.update(chunk)
    return dict(path=str(path), sha256=h.hexdigest(), bytes=path.stat().st_size)


class NativeCapture:
    """Install before settling; close only after the reference control stops."""
    def __init__(self, controller, out):
        self.c=controller
        self.e=controller.evaluator
        self.out=Path(out)
        self.out.mkdir(exist_ok=False, parents=True)
        self.original_update=self.e.update
        self.count=0
        self.closed=False
        self.first_action=controller.steps
        self.paths={k:self.out/(k+'.private.jsonl.gz') for k in ('trajectory','contacts')}
        from .execution_design_e19_capture import capture_for
        self.e19_release_capture=capture_for(controller)
        if self.e19_release_capture is not None:
            self.paths['e19_cap_release_dynamics']=self.out/'e19-cap-release-dynamics.private.jsonl.gz'
        if controller.scene.spec.get('id')=='E43':
            self.paths['e43_assembly_startup']=self.out/'e43-assembly-startup.private.jsonl.gz'
        self.streams={k:gzip.open(p,'wt',encoding='utf-8',compresslevel=1) for k,p in self.paths.items()}
        for path in self.paths.values():path.chmod(0o600)
        self.e.update=self.update
        spec=controller.scene.spec
        masses={}
        for name,asset in getattr(controller.scene,'objects',{}).items():
            try:
                masses[name]=dict(measured=True,kg=asset.root_physx_view.get_masses().cpu().tolist())
            except Exception as exc:
                masses[name]=dict(measured=False,error=type(exc).__name__+': '+str(exc))
        derived_stand=None
        if spec.get('id')=='E17' and any(o.get('e17_stand_geometry') for o in spec.get('objects',[])):
            from .execution_design_e17_stand import native_readback
            derived_stand=native_readback(controller.scene)
        _write(self.out/'identity.private.json', dict(
            pid=os.getpid(), start_ticks=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],
            task=spec['id'],variant=spec['variant'],seed=spec['seed'],
            execution_design=spec['execution_design'],
            actual_physx_masses=masses,
            **({'derived_stand_native_readback':derived_stand} if derived_stand is not None else {}),
            source_files_verified=spec.get('source_files_verified') is True,
            engineering_reference_only=True, eligible_as_model_demo=False))

    def update(self, state, contacts, dt):
        # Save exactly what the native controller supplies, before evaluating it.
        self.count+=1
        row=dict(tick=self.count, dt=dt, native_physics_tick=self.c.physics_ticks,
                 actions=self.c.steps, state=state)
        # Controller supplies update_mechanisms immediately before update. Its
        # pending snapshot is consumed below, so capture it before evaluation.
        mechanisms=getattr(self.e,'pending_mechanisms',None)
        if mechanisms is not None:
            row['mechanisms']=deepcopy(mechanisms)
        self.streams['trajectory'].write(json.dumps(row,default=_json,separators=(',',':'))+'\n')
        self.streams['contacts'].write(json.dumps(dict(
            tick=self.count, contacts=sorted(sorted(pair) for pair in contacts)),separators=(',',':'))+'\n')
        if self.e19_release_capture is not None:
            dynamics=self.e19_release_capture.sample(self.count,state,contacts)
            self.streams['e19_cap_release_dynamics'].write(json.dumps(dynamics,default=_json,separators=(',',':'))+'\n')
        if 'e43_assembly_startup' in self.streams and self.c.steps==self.first_action:
            # Read-only evidence of the assembled source constraint before
            # any public action; retain actual force, not contact booleans only.
            if self.count==1 or self.count%120==0:
                startup=dict(tick=self.count,native_physics_tick=self.c.physics_ticks,
                    actions=self.c.steps,state={k:state[k]for k in ('gate','launcher','ball')},
                    contact_forces_n=[dict(bodies=sorted(pair),force_n=float(force))
                        for pair,force in getattr(self.c,'contact_forces',{}).items()
                        if 'gate'in pair or 'ball'in pair])
                self.streams['e43_assembly_startup'].write(json.dumps(startup,default=_json,separators=(',',':'))+'\n')
        self.original_update(state,contacts,dt)
        if self.count%240==0:
            for stream in self.streams.values():stream.flush()

    def close(self, *, error=None, final_rgb_path=None, actions_path=None):
        if self.closed:return
        self.closed=True
        self.e.update=self.original_update
        for stream in self.streams.values():stream.close()
        state,contacts=self.c.snapshot()
        final=self.out/'final-snapshot.private.json'
        final_data=dict(state=state,contacts=contacts,result=self.e.result(),
                        native_physics_tick=self.c.physics_ticks,actions=self.c.steps)
        snapshot_mechanisms=getattr(self.c,'snapshot_mechanisms',None)
        if snapshot_mechanisms is not None:
            final_data['mechanisms']=snapshot_mechanisms()
        _write(final,final_data)
        artifacts={k:_artifact(p) for k,p in self.paths.items()}
        artifacts['final_snapshot']=_artifact(final)
        for name,path in [('final_rgb',final_rgb_path),('native_actions',actions_path)]:
            if path is not None and Path(path).is_file():artifacts[name]=_artifact(Path(path))
        _write(self.out/'capture.private.json',dict(
            schema='videoicl-native-execution-v2-capture-v1',
            evidence_origin='native_controller_evaluator_inputs',
            engineering_reference_only=True, eligible_as_model_demo=False,
            measured_substeps=self.count,native_action_count=self.c.steps-self.first_action,
            result=self.e.result(),error=error,artifacts=artifacts,
            acceptance='pending_independent_review'))
