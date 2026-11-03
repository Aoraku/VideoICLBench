"""Isolated source-initial E37 left-handle prefix; never whole-task credit."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import numpy as np


def acquire_left(author):
    spec=author.scene.spec
    if not (author.control_report.get('engineering_reference_only') is True
            and spec.get('id')=='E37' and spec.get('seed')==4201
            and spec.get('execution_design',{}).get('condition')=='R'
            and spec['execution_design'].get('revision')=='embodied50-execution-v3-20261102'):
        raise ValueError('Explicit E37 R4201 engineering-only source prefix required')
    from .realworld_structural_expert import StructuralAuthor,ToolExecutionError
    from .engineering_checkpoint import capture
    from .execution_design_jacobian_reference import capture as measured_jacobian
    from .execution_design_thin_edge import table_bounds_task
    from .execution_design_branch_geometry import collision_parts_task
    from types import SimpleNamespace
    policy=StructuralAuthor(author);name='driver';side='left'
    ref=dict(actor=name,**deepcopy(policy.geometry['driver_grasp']))
    author.stage='e37-source-left-original-thick-handle'
    policy.acquire(ref,side)
    policy.require_held(ref,side)
    author.carried_payload=(name,side)
    author.stage='e37-source-left-true-table-departure'
    tip=policy.tip(side)
    policy.move(side,[*tip[:2],max(policy.clearance,float(tip[2])+.10)],
        lambda:policy.require_held(ref,side))
    if policy.contact(name,'table'):
        raise ToolExecutionError('Source left driver has not actually departed the table')
    for _ in range(3):
        policy.act();policy.require_held(ref,side)
    def frame(value):return policy.frame(value)
    pieces=collision_parts_task(SimpleNamespace(a=author,frame=frame),name)
    lowest=min(float(p[:,2].min())for p in pieces)
    if lowest<table_bounds_task(author.scene)['top']+.01:
        raise ToolExecutionError('Source left tool lacks real material table clearance')
    stage='e37-source-left-grasp-and-clear'
    checkpoint=capture(author.c,stage,context=dict(carried_payload=[name,side],
        role='left',active_side=side,source_initial_prefix_only=True))
    path=Path(author.out)/'checkpoints/source-left-grasp-and-clear.private.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=(json.dumps(checkpoint,indent=2)+'\n').encode();path.write_bytes(raw);path.chmod(0o600)
    measured=measured_jacobian(author,author.c,side)
    report=dict(task='E37',variant=spec['variant'],source_initial_prefix_only=True,
        prefix_passed=True,native_task_acceptance=False,side=side,grasp_ref=ref,
        actual_held=bool(policy.held(ref,side)),actual_material_lowest_z=lowest,
        actions=author.c.steps-policy.start,checkpoint=dict(path=str(path),
            sha256=hashlib.sha256(raw).hexdigest(),source=checkpoint['source']),
        native_jacobian=measured)
    (Path(author.out)/'e37-source-left-prefix.private.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
