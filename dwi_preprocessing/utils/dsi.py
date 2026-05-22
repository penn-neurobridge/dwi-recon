"""DSI Studio invocation — local binary or Docker container.

DSI Studio can run either as a locally installed binary or via the
official Docker image (dsistudio/dsistudio), pinned to a version tag.
``run_dsi`` builds the right command for the configured mode and runs it.

For Docker, host directories referenced in the arguments are bind-mounted
at identical paths (``-v /host/dir:/host/dir``) so the absolute paths in
the DSI Studio arguments work unchanged inside the container.
"""

from pathlib import Path

from dwi_preprocessing.utils.shell import run


def run_dsi(cfg, args: list[str], extra_mounts: list[Path] | None = None) -> None:
    """Run a DSI Studio command (local binary or Docker).

    Parameters
    ----------
    cfg : Config
        Pipeline configuration. Uses cfg.dsi_use_docker, cfg.dsi_studio_image,
        cfg.docker_cmd, cfg.docker_platform, and cfg.dsi_studio (local binary).
    args : list of str
        DSI Studio arguments, e.g. ["--action=src", "--source=/abs/path", ...].
        Do NOT include the executable itself.
    extra_mounts : list of Path, optional
        Additional host directories to bind-mount (e.g. an atlas directory
        that isn't referenced directly in args).
    """
    if cfg.dsi_use_docker:
        cmd = _docker_command(cfg, args, extra_mounts)
    else:
        cmd = [cfg.dsi_studio, *args]
    run(cmd)


def _docker_command(cfg, args: list[str], extra_mounts: list[Path] | None) -> list[str]:
    """Build a `docker run` command with identical-path bind mounts."""
    mounts = _collect_mount_dirs(args)
    if extra_mounts:
        for m in extra_mounts:
            mounts.add(Path(m))

    cmd = [cfg.docker_cmd, "run", "--rm"]

    # Run as the host user so outputs aren't root-owned
    cmd += ["--user", f"{_uid()}:{_gid()}"]

    # Headless Qt: the DSI Studio CLI still initialises Qt, which fails with
    # an "xcb" plugin error when no display is present. Force offscreen.
    cmd += ["-e", "QT_QPA_PLATFORM=offscreen"]

    # With --user the container has no writable HOME; DSI Studio writes its
    # config/model cache under HOME. Point it at the (writable) container /tmp.
    cmd += ["-e", "HOME=/tmp"]

    # Platform (Apple Silicon needs linux/amd64 emulation)
    if cfg.docker_platform:
        cmd += ["--platform", cfg.docker_platform]

    for d in sorted(str(m) for m in mounts):
        cmd += ["-v", f"{d}:{d}"]

    cmd += [cfg.dsi_studio_image, "dsi_studio", *args]
    return cmd


def _collect_mount_dirs(args: list[str]) -> set[Path]:
    """Find host directories to mount from absolute paths in the arguments.

    Scans ``--key=value`` arguments; for each value that is an absolute path,
    mounts its directory (the path itself if it is a directory, otherwise its
    parent — which exists for output files yet to be created).
    """
    dirs: set[Path] = set()
    for arg in args:
        if "=" not in arg:
            continue
        _, _, value = arg.partition("=")
        # values may be comma-separated (e.g. --connectivity_value=fa,md)
        for token in value.split(","):
            token = token.strip()
            if not token.startswith("/"):
                continue
            p = Path(token)
            # Mount the directory exactly as referenced in the args (do NOT
            # resolve symlinks) so the container path matches the arg string.
            d = p if p.is_dir() else p.parent
            if d.exists():
                dirs.add(d)
    return dirs


def _uid() -> int:
    import os
    return os.getuid()


def _gid() -> int:
    import os
    return os.getgid()
