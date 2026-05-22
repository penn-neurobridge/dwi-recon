"""I/O helpers for loading/saving .mat files.

DSI Studio and the MATLAB pipeline produce .mat files in two flavours:
  - v5 format  (scipy.io.loadmat can read)
  - v7.3 / HDF5 format  (h5py required)

The save functions always write v7.3 (HDF5) for compatibility with
large arrays (>2 GB) via h5py.
"""

import numpy as np
import scipy.io as sio
import h5py
from pathlib import Path


def load_mat(path: str | Path, variable: str | None = None):
    """Load a .mat file, auto-detecting v5 vs v7.3 format.

    Parameters
    ----------
    path : path to .mat file
    variable : if given, return only this variable; otherwise return dict

    Returns
    -------
    The requested variable (numpy array) or a dict of all variables.
    """
    path = str(path)

    # Try scipy first (v5 format — used by DSI Studio exports)
    try:
        data = sio.loadmat(path, simplify_cells=True)
        if variable:
            return data[variable]
        return data
    except NotImplementedError:
        pass  # v7.3 / HDF5 — fall through

    # HDF5 / v7.3 format (used by MATLAB save -v7.3)
    with h5py.File(path, "r") as f:
        if variable:
            return np.array(f[variable])
        return {key: np.array(f[key]) for key in f.keys()}


def save_mat_v73(path: str | Path, data_dict: dict):
    """Save arrays to a v7.3 (HDF5) .mat file.

    Parameters
    ----------
    path : output file path
    data_dict : {variable_name: numpy_array}
    """
    path = str(path)
    with h5py.File(path, "w") as f:
        for key, val in data_dict.items():
            if isinstance(val, np.ndarray):
                f.create_dataset(key, data=val, compression="gzip")
            elif isinstance(val, dict):
                grp = f.create_group(key)
                for k2, v2 in val.items():
                    if isinstance(v2, np.ndarray):
                        grp.create_dataset(k2, data=v2, compression="gzip")
            else:
                f.create_dataset(key, data=val)
