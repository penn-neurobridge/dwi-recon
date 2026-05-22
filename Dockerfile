# DWI processing and iEEG reconstruction pipeline — self-contained image.
#
# Based on the DSI Studio image (Ubuntu 20.04 with DSI Studio at
# /opt/dsi-studio/dsi_studio and a working headless Qt). We layer FSL
# (eddy/topup/bet/flirt via conda) and the uv-managed Python project on top.
# FreeSurfer is NOT needed — .mgz volumes are read with nibabel.
#
# The image is amd64-only (DSI Studio ships x86_64). On Apple Silicon build
# with:  docker build --platform linux/amd64 -t dwi-recon .

FROM dsistudio/dsistudio:hou-2026-05-17

# uv (standalone binaries from the official uv image)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# System deps for Miniforge
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget ca-certificates bzip2 && \
    rm -rf /var/lib/apt/lists/*

# Miniforge (conda) + FSL components from the official FSL conda channel
ENV FSL_CONDA_CHANNEL="https://fsl.fmrib.ox.ac.uk/fsldownloads/fslconda/public"
RUN wget -qO /tmp/miniforge.sh \
        https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh && \
    bash /tmp/miniforge.sh -b -p /opt/conda && \
    rm /tmp/miniforge.sh && \
    /opt/conda/bin/conda install -n base -y \
        -c "$FSL_CONDA_CHANNEL" -c conda-forge \
        fsl-eddy fsl-topup fsl-bet2 fsl-flirt fsl-avwutils fsl-utils && \
    /opt/conda/bin/conda clean -afy

# Runtime environment
ENV FSLDIR="/opt/conda" \
    FSLOUTPUTTYPE="NIFTI_GZ" \
    QT_QPA_PLATFORM="offscreen" \
    HOME="/tmp" \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:/opt/dsi-studio:/opt/conda/bin:$PATH"

WORKDIR /app

# Install Python dependencies first (better layer caching), then the project
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Container config: FSL at /opt/conda, DSI Studio as a local binary
COPY setup_environment.docker.json /app/setup_environment.json

# Entry point — see subcommands: `dwi` and `ieeg`.
# --no-sync: the venv is already built into the image; don't re-sync at runtime
# (avoids overhead and writing to /app/.venv when run read-only / non-root).
ENTRYPOINT ["uv", "run", "--no-sync", "run_dwi_recon.py"]
CMD ["--help"]
