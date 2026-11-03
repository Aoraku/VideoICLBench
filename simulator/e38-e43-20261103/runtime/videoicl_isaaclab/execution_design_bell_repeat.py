"""Opt-in shorter public E26 engineering repeat, never a physics shortcut."""
import os
from .execution_design import REVISION_V3,source_sha256


def enabled(author):
    if os.environ.get('VIC_ENGINEERING_BELL_SHORT_REPEAT')!='1':return False
    spec=getattr(author,'spec',{});design=spec.get('execution_design',{})
    return bool(spec.get('id')=='E26' and design.get('revision')==REVISION_V3
        and design.get('source_sha256')==source_sha256(REVISION_V3)
        and getattr(author.a,'control_report',{}).get('engineering_reference_only')
        and not spec.get('author_smooth_recording',False))
