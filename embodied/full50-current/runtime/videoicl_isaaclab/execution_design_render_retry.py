"""Bounded render-only warmup for scoped engineering camera evidence."""
import json


def _gray_only(error):
    text=str(error)
    for prefix in ('Initial camera evidence rejected: ','Final camera evidence rejected: '):
        if text.startswith(prefix):text=text[len(prefix):]
    return text in ('All three native views are near-uniform gray',
                    'All three native views are near-uniform gray; task visibility not established')


def capture(pool, room, controller, *, passes, callback, log_path):
    spec = controller.scene.spec
    from .execution_design import REVISION_V3
    enabled = (spec.get('execution_design', {}).get('revision') == REVISION_V3
               and spec.get('id') in ({'E04', 'E08', 'E39'} | {f'E{i:02}' for i in range(14, 38)}))
    if not enabled:
        return pool.render_room(room, passes=passes, capture=callback)
    schedule = (passes, max(passes, 12), max(passes, 24))
    attempts = []
    for index, render_passes in enumerate(schedule):
        before = (pool.physics_ticks, controller.physics_ticks, controller.steps)
        error = None
        audit_path=log_path.with_name(log_path.name.replace('render-attempts','camera-audit'))
        audit_before=audit_path.stat().st_mtime_ns if audit_path.exists() else None
        try:
            result = pool.render_room(room, passes=render_passes, capture=callback)
        except RuntimeError as exc:
            error = exc
        after = (pool.physics_ticks, controller.physics_ticks, controller.steps)
        attempt=dict(passes=render_passes, before=before, after=after,
                     error=str(error) if error else None)
        if enabled:
            # Preserve each real readback even though the next capture writes
            # the same PNG/audit filenames. This records evidence, never a pass.
            import hashlib
            readback={}
            if audit_path.is_file():
                try:
                    readback['camera_audit']=json.loads(audit_path.read_text())
                    readback['audit_updated_this_attempt']=audit_path.stat().st_mtime_ns!=audit_before
                except (ValueError,OSError) as exc:readback['diagnostic_error']=str(exc)
            else:readback['diagnostic_error']='No camera audit was written by this callback'
            prefix=log_path.name.split('-render-attempts')[0]
            readback['rgb_files']={}
            for view in ('head','left_wrist','right_wrist'):
                png=log_path.with_name(prefix+'-'+view+'.png')
                if png.is_file():
                    raw=png.read_bytes();readback['rgb_files'][view]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
            attempt['actual_camera_readback']=readback
        attempts.append(attempt)
        log_path.write_text(json.dumps(attempts, indent=2))
        if after != before:
            raise RuntimeError('Engineering camera warmup advanced physics/actions')
        if error is None:
            return result
        # Warmup cannot repair calibration/pose/schema errors. Only retry the
        # exact all-three-view gray admission failure, without changing gates.
        if not _gray_only(error) or index == len(schedule)-1:
            raise error
