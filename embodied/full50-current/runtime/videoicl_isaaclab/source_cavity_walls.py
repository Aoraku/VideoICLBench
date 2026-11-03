"""Pinned source-mesh sidewall and floor checks for the curved E33 bin.

The reviewed box remains the trusted core. Only its X/Y rejection can be
corrected using the first original wall at that vertex's transverse coordinates. A vertex
below the reviewed centre-floor height must be above the highest source floor
at its own X/Y. The open-top rim envelope and 3 mm normal tolerance remain unchanged.
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
        floor_det = u[:, 0]*v[:, 1]-u[:, 1]*v[:, 0]
        floor_good = (lengths > 1e-14) & (np.abs(floor_det) > 1e-14)
        self.floor_a, self.floor_u, self.floor_v = a[floor_good], u[floor_good], v[floor_good]
        self.floor_det = floor_det[floor_good]
        self.normal_z = np.abs(normals[floor_good, 2])/lengths[floor_good]
        det = u[:, 1]*v[:, 2]-u[:, 2]*v[:, 1]
        good = (lengths > 1e-14) & (np.abs(det) > 1e-14)
        self.a, self.u, self.v = a[good], u[good], v[good]
        self.det = det[good]
        self.normal_x = np.abs(normals[good, 0])/lengths[good]
        # A Y ray uses the same first-interior-surface rule as X. The old
        # rectangular Y core can be too narrow near the curved source wall.
        y_det = u[:, 0]*v[:, 2]-u[:, 2]*v[:, 0]
        y_good = (lengths > 1e-14) & (np.abs(y_det) > 1e-14)
        self.y_a, self.y_u, self.y_v = a[y_good], u[y_good], v[y_good]
        self.y_det = y_det[y_good]
        self.normal_y = np.abs(normals[y_good, 1])/lengths[y_good]

    def contains(self, points, lower, upper, tolerance=.003):
        points = np.asarray(points, float)
        lower, upper = np.asarray(lower, float), np.asarray(upper, float)
        if points.ndim != 2 or points.shape[1:] != (3,) or not len(points) or not np.isfinite(points).all():
            return False
        if np.any(points[:, 2] > upper[2]+tolerance):
            return False
        for point in points[points[:, 2] < lower[2]-tolerance]:
            delta = point[:2]-self.floor_a[:, :2]
            beta = (delta[:, 0]*self.floor_v[:, 1]-delta[:, 1]*self.floor_v[:, 0])/self.floor_det
            gamma = (self.floor_u[:, 0]*delta[:, 1]-self.floor_u[:, 1]*delta[:, 0])/self.floor_det
            hit_z = self.floor_a[:, 2]+beta*self.floor_u[:, 2]+gamma*self.floor_v[:, 2]
            hit = (beta >= -1e-9) & (gamma >= -1e-9) & (beta+gamma <= 1+1e-9) & (hit_z <= upper[2])
            indices = np.flatnonzero(hit)
            if not len(indices):
                return False
            # First surface seen from the open top, never the outer underside
            # or a deeper surface behind the actual inner floor.
            index = indices[np.argmax(hit_z[indices])]
            penetration = hit_z[index]-point[2]
            if penetration > 0 and (self.normal_z[index] < .5 or penetration*self.normal_z[index] > tolerance):
                return False
        for axis, transverse, a, u, v, det, normal in (
                (0, (1, 2), self.a, self.u, self.v, self.det, self.normal_x),
                (1, (0, 2), self.y_a, self.y_u, self.y_v, self.y_det, self.normal_y)):
            i, j = transverse
            outside = (points[:, axis] < lower[axis]-tolerance) | (points[:, axis] > upper[axis]+tolerance)
            for point in points[outside]:
                sign = 1 if point[axis] > upper[axis] else -1
                delta = point[list(transverse)]-a[:, list(transverse)]
                beta = (delta[:, 0]*v[:, j]-delta[:, 1]*v[:, i])/det
                gamma = (u[:, i]*delta[:, 1]-u[:, j]*delta[:, 0])/det
                hit_coordinate = a[:, axis]+beta*u[:, axis]+gamma*v[:, axis]
                hit = (beta >= -1e-9) & (gamma >= -1e-9) & (beta+gamma <= 1+1e-9) & (sign*hit_coordinate > 1e-9)
                indices = np.flatnonzero(hit)
                if not len(indices):
                    return False
                index = indices[np.argmin(sign*hit_coordinate[indices])]
                wall = hit_coordinate[index]
                bound = upper[axis] if sign > 0 else lower[axis]
                # Never skip an inner surface for an outer wall or expand
                # through a nearly horizontal floor/internal rib.
                if normal[index] < .5 or sign*(wall-bound) < -tolerance:
                    return False
                if sign*(point[axis]-wall)*normal[index] > tolerance:
                    return False
        return True
