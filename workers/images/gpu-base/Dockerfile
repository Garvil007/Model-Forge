# gpu-base worker image: CUDA PyTorch, Transformers, llm-compressor (GPTQ/AWQ),
# bitsandbytes (NF4), accelerate, datasets (WikiText-2/C4 calibration). Backs q_gptq,
# q_awq and q_nf4 — the catalog's existing `worker_image="gpu-base"`/`queue="gpu"`
# entries (`packages/catalog/src/modelforge_catalog/methods.py`), the same name Day 11's
# notes already flagged as a placeholder pending a real image. Also the eventual home for
# p_wanda/d_logit/d_feature/d_llm/c_tensorrt (Days 15-18), not built here.
#
# Build from the repo root (needs packages/catalog, packages/db and workers/):
#   docker build -f workers/images/gpu-base/Dockerfile -t modelforge/gpu-base:dev .
#
# Needs an NVIDIA CUDA base (not python:slim) since torch/bitsandbytes/llm-compressor
# all need real CUDA runtime libraries, not just the Python wheel — the cpu-* images'
# `python:3.12-slim` base can't run this image's op code against a real GPU, only
# against `MF_LLM_DEVICE=cpu`'s CPU test mode (see `workers/ops/_llm_gpu_common.py`).

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS builder

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3.12 python3.12-venv python3-pip \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
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

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3.12 \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system modelforge && useradd --system --gid modelforge --create-home modelforge

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/packages /app/packages
COPY --from=builder /build/workers /app/workers

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MF_LLM_DEVICE=cuda

WORKDIR /app/workers
USER modelforge

ENTRYPOINT ["python3.12", "-m", "core.runner"]
