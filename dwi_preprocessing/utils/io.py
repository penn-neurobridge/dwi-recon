"""I/O helpers — HDF5 as the primary format.

Per-subject outputs are stored as HDF5 (.h5) with groups for each
analysis type (ieeg-sc-3mmSph, sc-desikanKilliany, etc.) and datasets
for each metric (ad, count, fa, length, md, qa, rd).

Legacy .mat loading is kept for reading DSI Studio exports and
existing whole_brain_trk.mat / trksubVox.mat files.
"""

from pathlib import Path

import h5py
import numpy as np
import scipy.io as sio


# ── HDF5 (primary output format) ─────────────────────────────────────

def save_h5(path: Path, data: dict) -> None:
    """Save a nested dict to an HDF5 file.

    Top-level string keys become groups; numpy arrays become datasets.
    Supports one level of nesting (group/dataset).

    Parameters
    ----------
    path : Path
        Output .h5 file path.
    data : dict
        ``{group_name: {dataset_name: np.ndarray, ...}, ...}``
        or ``{dataset_name: np.ndarray, ...}`` for flat files.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with h5py.File(str(path), "w") as f:
        for key, val in data.items():
            if isinstance(val, dict):
                grp = f.create_group(key)
                for k2, v2 in val.items():
                    _write_dataset(grp, k2, v2)
            else:
                _write_dataset(f, key, val)


def load_h5(path: Path, group: str | None = None) -> dict:
    """Load an HDF5 file (or a single group) as a nested dict.

    Parameters
    ----------
    path : Path
        Input .h5 file.
    group : str, optional
        If given, load only this group.

    Returns
    -------
    dict of numpy arrays or nested dicts.
    """
    out: dict = {}
    with h5py.File(str(path), "r") as f:
        root = f[group] if group else f
        for key in root:
            item = root[key]
            if isinstance(item, h5py.Group):
                out[key] = {k: np.array(item[k]) for k in item}
            else:
                out[key] = np.array(item)
    return out


def _write_dataset(parent, name: str, value) -> None:
    """Write a single dataset, handling strings and arrays."""
    if isinstance(value, np.ndarray):
        if value.dtype.kind in ("U", "O", "S"):
            # String/object array → variable-length UTF-8.
            # h5py needs an object array of Python str, not a fixed-width
            # unicode array (np.astype(str) gives e.g. '<U31', which h5py
            # cannot convert).
            dt = h5py.string_dtype()
            str_arr = np.array(
                [str(x) for x in value.ravel()], dtype=object
            ).reshape(value.shape)
            parent.create_dataset(name, data=str_arr, dtype=dt)
        else:
            parent.create_dataset(name, data=value, compression="gzip")
    elif isinstance(value, str):
        parent.create_dataset(name, data=value, dtype=h5py.string_dtype())
    else:
        parent.create_dataset(name, data=value)


# ── Legacy .mat loading (for DSI Studio exports) ─────────────────────

def load_mat(path: Path, variable: str | None = None):
    """Load a .mat file, auto-detecting v5 vs v7.3 format.

    Parameters
    ----------
    path : Path
        .mat file path.
    variable : str, optional
        If given, return only this variable.

    Returns
    -------
    numpy array (if variable given) or dict of arrays.
    """
    path = str(path)

    # Try scipy first (v5 — used by DSI Studio exports)
    try:
        data = sio.loadmat(path, simplify_cells=True)
        return data[variable] if variable else data
    except NotImplementedError:
        pass  # v7.3 / HDF5

    with h5py.File(path, "r") as f:
        if variable:
            return np.array(f[variable])
        return _read_h5_recursive(f)


def _read_h5_recursive(group) -> dict:
    """Recursively read an HDF5 group into a dict."""
    out: dict = {}
    for key in group:
        item = group[key]
        if isinstance(item, h5py.Group):
            out[key] = _read_h5_recursive(item)
        else:
            out[key] = np.array(item)
    return out
