# gpu-base worker image: CUDA PyTorch, Transformers, llm-compressor (GPTQ/AWQ),
# bitsandbytes (NF4), accelerate, datasets (WikiText-2/C4 calibration). Backs q_gptq,
# q_awq and q_nf4 — the catalog's existing `worker_image="gpu-base"`/`queue="gpu"`
# entries (`packages/catalog/src/modelforge_catalog/methods.py`), the same name Day 11's
# notes already flagged as a placeholder pending a real image. c_tensorrt is NOT backed by
# this image — it gets its own `tensorrt` image (see workers/images/tensorrt/Dockerfile)
# so TensorRT's large CUDA wheel doesn't slow down every q_gptq/q_awq/q_nf4 job's pull.
#
# Build from the repo root (needs packages/catalog, packages/db and workers/):
#   docker build -f workers/images/gpu-base/Dockerfile -t modelforge/gpu-base:dev .
#
# Needs an NVIDIA CUDA base (not python:slim) since torch/bitsandbytes/llm-compressor
# all need real CUDA runtime libraries, not just the Python wheel — the cpu-* images'
# `python:3.12-slim` base can't run this image's op code against a real GPU, only
# against `MF_LLM_DEVICE=cpu`'s CPU test mode (see `workers/ops/_llm_gpu_common.py`).

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS builder

# Ubuntu 22.04's own repos only carry Python 3.10 — 3.12 needs the deadsnakes PPA
# (confirmed live: `apt-get install python3.12` fails with "Unable to locate package"
# straight off this base image). DEBIAN_FRONTEND=noninteractive is required: pulling in
# python3.12's `tzdata` dependency otherwise drops into an interactive "Geographic area"
# debconf prompt that hangs the build indefinitely (confirmed live).
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends software-properties-common \
 && add-apt-repository -y ppa:deadsnakes/ppa \
 && apt-get update \
 && apt-get install -y --no-install-recommends python3.12 python3.12-venv python3-pip \
 && rm -rf /var/lib/apt/lists/*

# WORKDIR matches the final stage's COPY destination (/app) deliberately: `pip install
# -e` records this absolute path in the venv's .pth files, so the editable install only
# resolves in the final image if the source ends up at the exact same path there too.
WORKDIR /app
RUN python3.12 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY workers/images/gpu-base/requirements.lock.txt ./requirements.lock.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.lock.txt \
      --extra-index-url https://download.pytorch.org/whl/cu124

COPY packages/catalog ./packages/catalog
COPY packages/db ./packages/db
COPY workers ./workers
RUN pip install --no-cache-dir --no-deps \
      -e ./packages/catalog -e ./packages/db -e ./workers


FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS final

ENV DEBIAN_FRONTEND=noninteractive
# build-essential (gcc) is required at runtime, not just build time: torch's Triton
# backend JIT-compiles CUDA kernels on first use and shells out to a real C compiler to
# do it — confirmed live via a real GPU job failing with "Failed to find C compiler"
# the first time a GPTQ/AWQ/NF4 op actually ran torch ops against the GPU (the CPU test
# path never hits this, since MF_LLM_DEVICE=cpu never reaches Triton).
RUN apt-get update \
 && apt-get install -y --no-install-recommends software-properties-common build-essential \
 && add-apt-repository -y ppa:deadsnakes/ppa \
 && apt-get update \
 && apt-get install -y --no-install-recommends python3.12 python3.12-dev \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system modelforge && useradd --system --gid modelforge --create-home modelforge

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/packages /app/packages
COPY --from=builder /app/workers /app/workers

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MF_LLM_DEVICE=cuda

WORKDIR /app/workers
USER modelforge

ENTRYPOINT ["python3.12", "-m", "core.runner"]
