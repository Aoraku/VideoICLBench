"""Bind the existing SHA-verified actual tray walls to E45 region acceptance."""
from pathlib import Path
import hashlib

def bind(spec):
    if spec['id']!='E45':raise ValueError('E45 acceptance geometry only')
    from .source_tray_compartments import SourceTrayCompartments
    root=Path(__file__).resolve().parents[1];rel='configs/source_geometry/e45-original-tray-triangles.npz';path=root/rel
    geometry=dict(path=rel,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    actor=next(o for o in spec['objects']if o['id']==spec['semantic']['container'])
    SourceTrayCompartments(geometry,actor,root)
    spec['semantic']['source_compartment_geometry']=geometry
    spec['acceptance_geometry_revision']='e45-original-source-tray-walls-v1'
