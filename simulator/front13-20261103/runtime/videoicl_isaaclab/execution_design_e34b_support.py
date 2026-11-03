"""Private support proposals from enabled native convex material, not root Z."""
import numpy as np


def vertical_support_z(parts, xy):
    """Top of real convex material intersected by a world-vertical ray."""
    from scipy.spatial import ConvexHull
    xy = np.asarray(xy, float)
    if xy.shape != (2,) or not np.isfinite(xy).all():
        raise ValueError('Finite support ray XY required')
    hits = []
    for part in parts:
        points = np.asarray(part, float)
        if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
            raise ValueError('Complete finite native convex points required')
        lower, upper = -np.inf, np.inf
        for normal in ConvexHull(points).equations:
            residual = float(normal[:2] @ xy + normal[3])
            nz = float(normal[2])
            if abs(nz) < 1e-12:
                if residual > 1e-9:
                    lower, upper = 1., 0.
                    break
            elif nz > 0:
                upper = min(upper, -residual / nz)
            else:
                lower = max(lower, -residual / nz)
        if lower <= upper + 1e-9 and np.isfinite(upper):
            hits.append(float(upper))
    if not hits:
        raise RuntimeError('No actual native tray support under planned utensil COM')
    return max(hits)


def supported_handle_z(handle, payload_parts, support_z, clearance=.003):
    handle = np.asarray(handle, float)
    vertices = np.concatenate([np.asarray(p, float) for p in payload_parts])
    if (handle.shape != (3,) or vertices.ndim != 2 or vertices.shape[1] != 3
            or not np.isfinite(vertices).all() or not np.isfinite(handle).all()
            or not np.isfinite(support_z) or not 0 < clearance <= .005):
        raise ValueError('Actual material bounds and finite support height required')
    return float(support_z + handle[2] - vertices[:, 2].min() + clearance)
