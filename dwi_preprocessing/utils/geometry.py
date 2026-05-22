"""Geometry utilities — point-in-mesh tests.

Python equivalent of MATLAB inpolyhedron.m using trimesh.
"""

import numpy as np
import trimesh


def inpolyhedron(vertices: np.ndarray, faces: np.ndarray,
                 points: np.ndarray) -> np.ndarray:
    """Test whether points are inside a closed triangular mesh.

    Parameters
    ----------
    vertices : (V, 3) array — mesh vertices
    faces : (F, 3) array — mesh face indices (0-indexed)
    points : (P, 3) array — query points

    Returns
    -------
    inside : (P,) bool array — True if the point is inside the mesh
    """
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
    return mesh.contains(points)
