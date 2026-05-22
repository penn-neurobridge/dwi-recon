"""Subprocess helper — list-style command execution.

All external tool calls (FSL, FreeSurfer, DSI Studio) go through run()
so that commands are logged consistently and never use shell=True.
"""

import subprocess
from pathlib import Path


def run(cmd: list[str | Path], log_path: Path | None = None, **kwargs) -> None:
    """Run an external command as a list of arguments.

    Parameters
    ----------
    cmd : list of str or Path
        Command and arguments. Path objects are converted to str automatically.
    log_path : Path, optional
        If given, stdout is written to this file.
    **kwargs
        Forwarded to subprocess.run (e.g. env, cwd).
    """
    cmd_str = [str(c) for c in cmd]
    print(f"  >> {' '.join(cmd_str)}")

    stdout = open(log_path, "w") if log_path else None
    try:
        subprocess.run(cmd_str, check=True, stdout=stdout, **kwargs)
    finally:
        if stdout is not None:
            stdout.close()
