"""Source-mesh sidewall checks for the curved E33 bin.

The reviewed box remains the trusted core. Only its X rejection can be
corrected, using the first original wall at that vertex's actual Y/Z. The
original Y/Z envelope and 3 mm normal-distance tolerance remain unchanged.
"""
from pathlib import Path
import hashlib
import numpy as np


class SourceCavityWalls:
    def __init__(self, geometry, actor, root=None):
        root = Path(root or Path(__file__).resolve().parents[1]).resolve()
        path = (root / geometry['path']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Cavity mesh must belong to the frozen runtime')
        if hashlib.sha256(path.read_bytes()).hexdigest() != geometry['sha256']:
            raise ValueError('Cavity mesh archive identity mismatch')
        with np.load(path, allow_pickle=False) as data:
            if str(data['source_sha256']) != actor['source_asset']['sha256']:
                raise ValueError('Cavity mesh source identity mismatch')
            if not np.allclose(data['descriptor_half_size'], actor['size'], atol=1e-12, rtol=0):
                raise ValueError('Cavity mesh source dimensions mismatch')
            if 'source_rotation_wxyz' in data and not np.allclose(data['source_rotation_wxyz'], actor['source_asset']['source_rotation'], atol=1e-12, rtol=0):
                raise ValueError('Cavity mesh source rotation mismatch')
            triangles = np.asarray(data['triangles_body_m'], float)
        if triangles.ndim != 3 or triangles.shape[1:] != (3, 3) or not np.isfinite(triangles).all():
            raise ValueError('Finite original source triangles required')
        a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
        u, v = b-a, c-a
        normals = np.cross(u, v)
        lengths = np.linalg.norm(normals, axis=1)
        det = u[:, 1]*v[:, 2]-u[:, 2]*v[:, 1]
        good = (lengths > 1e-14) & (np.abs(det) > 1e-14)
        self.a, self.u, self.v = a[good], u[good], v[good]
        self.det = det[good]
        self.normal_x = np.abs(normals[good, 0])/lengths[good]

    def contains(self, points, lower, upper, tolerance=.003):
        points = np.asarray(points, float)
        lower, upper = np.asarray(lower, float), np.asarray(upper, float)
        if points.ndim != 2 or points.shape[1:] != (3,) or not len(points) or not np.isfinite(points).all():
            return False
        if np.any(points[:, 1:] < lower[1:]-tolerance) or np.any(points[:, 1:] > upper[1:]+tolerance):
            return False
        for point in points[(points[:, 0] < lower[0]-tolerance) | (points[:, 0] > upper[0]+tolerance)]:
            sign = 1 if point[0] > upper[0] else -1
            delta = point[1:]-self.a[:, 1:]
            beta = (delta[:, 0]*self.v[:, 2]-delta[:, 1]*self.v[:, 1])/self.det
            gamma = (self.u[:, 1]*delta[:, 1]-self.u[:, 2]*delta[:, 0])/self.det
            hit_x = self.a[:, 0]+beta*self.u[:, 0]+gamma*self.v[:, 0]
            hit = (beta >= -1e-9) & (gamma >= -1e-9) & (beta+gamma <= 1+1e-9) & (sign*hit_x > 1e-9)
            indices = np.flatnonzero(hit)
            if not len(indices):
                return False
            index = indices[np.argmin(sign*hit_x[indices])]
            wall = hit_x[index]
            bound = upper[0] if sign > 0 else lower[0]
            # A nearly horizontal floor or an internal rib cannot enlarge the
            # old sidewall envelope. Never skip a nearer hit for an outer face.
            if self.normal_x[index] < .5 or sign*(wall-bound) < -tolerance:
                return False
            if sign*(point[0]-wall)*self.normal_x[index] > tolerance:
                return False
        return True
