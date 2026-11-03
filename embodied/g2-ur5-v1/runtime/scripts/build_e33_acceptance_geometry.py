#!/usr/bin/env python3
"""Rebuild E33 acceptance geometry from the six pinned original USDA assets.

This is an offline exporter, not a simulation or a scorer. It changes no body,
pose, collision mesh, tolerance or task goal. The narrow ASCII reader accepts
only the already-reviewed, transform-baked source files (verified SHA256).
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import numpy as np
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
PINNED = {
 'bin':'63f1f7303b93c8455d8d9544db7a9c0adf73b5f5913497d0f27082a92daf8963',
 'sprite':'db4d15d0478046c254e27934c1820b3e7ca900c219d217256fe20ba059bd7e44',
 'water':'c217f589d87af258e06c2d880a9524d37e1b0db367e2ce0f8948e24621ce5f6d',
 'coca_cola':'8014b588bb60ea114f80edb2df7b82405a9876e01585792b889beeb2500fbff9',
 'pepsi':'d3288bf4e1002f53b6eeb2ef0dd3544bac3990aa41411bf72a86a86969a85bcf',
 'fanta':'9bc36a97603b498aec29379bbe0491c728038d998b0d48a26f99a31f7b297439',
}

def extract(name, obj, asset_root):
    asset = obj['source_asset']; path = Path(asset_root)/asset['relative_path']
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PINNED[name] or asset['sha256'] != PINNED[name]:
        raise ValueError('Unreviewed E33 source identity: '+name)
    text = raw.decode()
    if 'xformOp' in text: raise ValueError('Expected transform-baked E33 source')
    meshes = []
    for block in re.split(r'\bdef Mesh\s+', text)[1:]:
        def array(field, dtype=float):
            match = re.search(r'\b'+field+r'\s*=\s*\[([^\]]*)\]', block)
            if not match: raise ValueError('Missing source mesh array '+field)
            return np.fromstring(re.sub('[()]','',match.group(1)),sep=',',dtype=dtype)
        # USD point3f is float32: reproduces the original loader's precision.
        points = array('points').astype(np.float32).astype(float).reshape(-1,3)
        counts = array('faceVertexCounts',int)
        if not np.all(counts == 3): raise ValueError('Expected source triangles')
        faces = array('faceVertexIndices',int).reshape(-1,3)
        if len(faces)!=len(counts) or faces.min()<0 or faces.max()>=len(points):
            raise ValueError('Invalid source triangle indices')
        collision = 'PhysicsCollisionAPI' in block[:block.index('point3f[]')]
        meshes.append((points,faces,collision))
    q = asset['source_rotation']; rotation = Rotation.from_quat(q[1:]+q[:1]).as_matrix()
    visible = np.concatenate([p@rotation.T for p,f,c in meshes if not c])
    low, high = visible.min(0), visible.max(0)
    scale = 2*np.asarray(obj['size'])/(high-low)
    normalized = [((p@rotation.T-(low+high)/2)*scale,f) for p,f,c in meshes if c]
    points = np.concatenate([p for p,f in normalized])
    triangles = np.concatenate([p[f] for p,f in normalized])
    return points,triangles

def build(bindings, asset_root, out):
    out = Path(out); out.mkdir(parents=True,exist_ok=True)
    objects = bindings['tasks']['E33']['objects']; records={}; evidence={}
    for name in PINNED:
        obj=objects[name]; points,triangles=extract(name,obj,asset_root)
        record=dict(source_asset_sha256=PINNED[name],descriptor_half_size=obj['size'],
                    source_rotation_wxyz=obj['source_asset']['source_rotation'])
        if name=='bin':
            path=out/'e33-original-bin-triangles.npz'
            np.savez_compressed(path,triangles_body_m=triangles,source_sha256=PINNED[name],
                descriptor_half_size=obj['size'],source_rotation_wxyz=record['source_rotation_wxyz'])
            record.update(path=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            evidence[name]=dict(triangles=len(triangles))
        else:
            hull=ConvexHull(points); vertices=points[hull.vertices]
            record.update(vertices_local=vertices.tolist(),source_points_sha256=hashlib.sha256(points.tobytes()).hexdigest(),
                          derivation='Convex hull of normalized original collision vertices; no box-corner approximation')
            maximum=max(float(np.max(points[i:i+1024]@hull.equations[:,:3].T+hull.equations[:,3])) for i in range(0,len(points),1024))
            evidence[name]=dict(source_points=len(points),hull_vertices=len(vertices),all_source_vertices_max_plane_error_m=maximum)
            if maximum>1e-10: raise ValueError('Hull does not cover original collision geometry')
        records[name]=record
    manifest=dict(schema='e33-source-acceptance-geometry-v1',objects=records,
                  scope='Acceptance geometry only; original XYZ limits and 3mm tolerance unchanged')
    (out/'e33-acceptance-geometry.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (out/'e33-geometry-build-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    return manifest,evidence

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',type=Path,default=ROOT/'configs/realworld_full50_bindings.json')
    p.add_argument('--asset-root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(); _,evidence=build(json.loads(a.base.read_text()),a.asset_root,a.out)
    print(json.dumps(evidence))
if __name__=='__main__': main()
