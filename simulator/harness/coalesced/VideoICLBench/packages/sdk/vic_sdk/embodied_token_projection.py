"""Future-only, lossless MCP text projection. Never operates the environment.

Input must already have passed the existing SDK public-observation whitelist.
This module is NOT a replacement for that whitelist or any safety/receipt logic.
"""
from copy import deepcopy
import hashlib
import fcntl
import json
import os
from pathlib import Path
import tempfile
import threading

CONTRACT = ('Some repeated text is represented by a videoicl-text-ref-v1 object. '
            'Call observation_metadata(ref) to read its exact value. '
            'All current images, frame IDs and dynamic robot/calibration data remain inline. '
            'A _lean_static_fields entry names exact fields merged back into that object. '
            'References are text only, never authorization to act on an old frame.')


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


class ProjectionBypass(ValueError):
    """Original public data uses reserved keys; preserve the entire MCP response."""


class TextProjection:
    def __init__(self, state_dir, episode_id, mode="factored"):
        if not isinstance(episode_id, str) or not episode_id:
            raise ValueError('episode identity required')
        if mode not in ("compact", "factored"): raise ValueError("unknown projection mode")
        self.mode = mode
        self.episode_id = episode_id
        self.path = Path(state_dir) / 'text-registry.private.json'
        self.lock = threading.RLock()
        self.values = {}
        if mode == "compact": return  # No registry creation/loading in whitespace-only mode.
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.exists():
            saved = json.loads(self.path.read_text())
            if saved['episode_id'] != episode_id:
                raise ValueError('registry belongs to another episode')
            self.values = saved['values']
            for ref, value in self.values.items():
                if self._digest(value) != ref:
                    raise ValueError('registry digest mismatch')

    def _digest(self, value):
        return hashlib.sha256((self.episode_id+'\0'+compact_json(value)).encode()).hexdigest()

    def _load_merge(self):
        if not self.path.exists(): return
        saved=json.loads(self.path.read_text())
        if saved['episode_id'] != self.episode_id:
            raise ValueError('registry belongs to another episode')
        for ref,value in saved['values'].items():
            if self._digest(value) != ref: raise ValueError('registry digest mismatch')
        self.values={**saved['values'],**self.values}

    def _save(self):
        fd=os.open(self.path.parent/'registry.lock',os.O_RDWR|os.O_CREAT,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX)
            self._load_merge()
            self._save_locked()
        finally:
            fcntl.flock(fd,fcntl.LOCK_UN)
            os.close(fd)

    def _save_locked(self):
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix='.text-registry-')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(compact_json(dict(episode_id=self.episode_id, values=self.values)))
                f.flush(); os.fsync(f.fileno())
            os.replace(tmp, self.path)
            dfd = os.open(self.path.parent, os.O_RDONLY)
            try: os.fsync(dfd)
            finally: os.close(dfd)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)

    def _reference(self, value):
        ref = self._digest(value)
        if ref not in self.values:
            self.values[ref] = deepcopy(value)
            try: self._save()  # Durability precedes publishing any reference.
            except BaseException:
                del self.values[ref]
                raise
        return {'schema':'videoicl-text-ref-v1','ref':ref}

    def metadata(self, ref):
        with self.lock:
            if ref not in self.values: self._load_merge()
            if ref not in self.values:
                raise ValueError('unknown episode-local text reference')
            return deepcopy(self.values[ref])

    def restore(self, value):
        if isinstance(value, dict):
            if set(value) == {'schema','ref'} and value['schema'] == 'videoicl-text-ref-v1':
                return self.metadata(value['ref'])
            out={k:self.restore(v) for k,v in value.items() if k != '_lean_static_fields'}
            if '_lean_static_fields' in value:
                fields=self.restore(value['_lean_static_fields'])
                if not isinstance(fields,dict) or set(fields)&set(out):
                    raise ValueError('invalid static field bundle')
                out.update(fields)
            return out
        if isinstance(value, list): return [self.restore(v) for v in value]
        return deepcopy(value)

    def _factor_fields(self, obj, names):
        if not isinstance(obj,dict) or '_lean_static_fields' in obj: return
        fields={k:obj[k] for k in names if k in obj}
        if len(compact_json(fields)) <= 180: return
        ref=self._reference(fields)
        for k in fields: del obj[k]
        obj['_lean_static_fields']=ref

    @staticmethod
    def _reserved(value):
        if isinstance(value,dict):
            if '_lean_static_fields' in value or (set(value)=={'schema','ref'} and value['schema']=='videoicl-text-ref-v1'): return True
            return any(TextProjection._reserved(v) for v in value.values())
        return isinstance(value,list) and any(TextProjection._reserved(v) for v in value)

    def project(self, value):
        with self.lock:
            # Never hide receipt safety fields behind a whole-response reference.
            # The MCP boundary catches this and returns the original response intact.
            if self._reserved(value): raise ProjectionBypass('reserved keys in original public data')
            return self._project(value)

    def _project(self, value):
        if isinstance(value, list): return [self._project(x) for x in value]
        if not isinstance(value, dict): return deepcopy(value)
        out = deepcopy(value)
        # Only a recognized already-public observation may supply static metadata.
        if out.get('schema') == 'videoicl-structured-observation-v1' and isinstance(out.get('native_frame_id'),str):
            for field in ('action_schema','observation_contract'):
                item=out.get(field)
                if isinstance(item,dict) and len(compact_json(item)) > 180:
                    out[field]=self._reference(item)
            robot=out.get('robot_feedback',{})
            self._factor_fields(robot,('coordinate_frame','units'))
            for arm in robot.get('arms',{}).values():
                self._factor_fields(arm,('joint_names',))
            for camera in robot.get('camera_calibration',{}).values():
                self._factor_fields(camera,('convention','units','pixel_convention','optical_convention'))
            return out  # All dynamic K/T/TCP, dimensions, source, validity remain inline.
        # Dedupe only the entire stdout when it exactly echoes the returned observation.
        observation = out.get('observation')
        stdout = out.get('stdout')
        if isinstance(observation,dict) and isinstance(stdout,str):
            try: echoed=json.loads(stdout)
            except (ValueError,TypeError): echoed=None
            if echoed == observation and len(stdout)>180:
                out['stdout']=self._reference(stdout)
        return {k:self._project(v) for k,v in out.items()}

    def mcp_result(self, result):
        """Copy only JSON text blocks; preserve image blocks and error flag exactly.

        On storage/projection failure return ORIGINAL result: never hide accepted
        action outcomes behind a newly introduced projection exception.
        """
        try:
            blocks=[]
            for block in result.content:
                if block.type != 'text': blocks.append(block); continue
                try: raw=json.loads(block.text)
                except (ValueError,TypeError): blocks.append(block); continue
                blocks.append(block.model_copy(update={'text':compact_json(raw if self.mode == 'compact' else self.project(raw))}))
            return result.model_copy(update={'content':blocks})
        except Exception:
            return result
