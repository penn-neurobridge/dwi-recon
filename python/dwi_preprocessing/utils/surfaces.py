"""FreeSurfer surface and coordinate utilities.

Python equivalents of the MATLAB dependencies:
  - read_surf.m   -> nibabel.freesurfer.read_geometry
  - vox2ras_tkreg -> vox2ras_tkreg()
  - vox2ras_0to1  -> vox2ras_0to1()
"""

import numpy as np
import nibabel.freesurfer as fs


def read_surf(surf_path: str) -> tuple[np.ndarray, np.ndarray]:
    """Read a FreeSurfer surface file.

    Returns
    -------
    vertices : (N, 3) float array
    faces : (M, 3) int array  (0-indexed)
    """
    vertices, faces = fs.read_geometry(surf_path)
    return vertices, faces


def vox2ras_tkreg(image_size: tuple, pixel_dims: tuple) -> np.ndarray:
    """Compute the FreeSurfer tkRAS voxel-to-RAS matrix.

    Equivalent to the MATLAB vox2ras_tkreg.m:
        T = [-Dc/2  0     0     Nc*Dc/2;
              0     0     Ds/2 -Ns*Ds/2;
              0    -Dr/2  0     Nr*Dr/2;
              0     0     0     1       ]

    where Nc, Nr, Ns are image dimensions and Dc, Dr, Ds are voxel sizes.

    Parameters
    ----------
    image_size : (Nc, Nr, Ns)
    pixel_dims : (Dc, Dr, Ds)
    """
    Nc, Nr, Ns = image_size[0], image_size[1], image_size[2]
    Dc, Dr, Ds = pixel_dims[0], pixel_dims[1], pixel_dims[2]

    T = np.array([
        [-Dc, 0,    0,   (Nc * Dc) / 2],
        [0,   0,    Ds, -(Ns * Ds) / 2],
        [0,  -Dr,   0,   (Nr * Dr) / 2],
        [0,   0,    0,   1             ]
    ], dtype=np.float64)

    return T


def vox2ras_0to1(M: np.ndarray) -> np.ndarray:
    """Convert a 0-indexed vox2ras matrix to 1-indexed.

    Equivalent to MATLAB vox2ras_0to1.m:
        M_1based = M * [I  [1;1;1;0]; 0 0 0 1]
    which shifts the origin by one voxel.
    """
    shift = np.eye(4, dtype=np.float64)
    shift[0, 3] = 1.0
    shift[1, 3] = 1.0
    shift[2, 3] = 1.0
    return M @ shift
