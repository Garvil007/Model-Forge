# cpu-torch worker image: PyTorch CPU, ONNX, ONNX Runtime, onnxconverter-common,
# safetensors, Ultralytics. Backs q_fp16/q_bf16/q_int8_dyn jobs whose source model is
# ONNX, PyTorch (state_dict or TorchScript) or safetensors.
#
# Build from the repo root (needs packages/catalog, packages/db and workers/):
#   docker build -f workers/images/cpu-torch/Dockerfile -t modelforge/cpu-torch:dev .
#
# Multi-stage: the builder stage compiles into a venv using the pinned lock file; the
# final stage copies only that venv plus the three packages' source onto a slim base, so
# build tooling (gcc, pip's wheel cache) never reaches the image that actually runs jobs.

FROM python:3.12-slim AS builder

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY workers/images/cpu-torch/requirements.lock.txt ./requirements.lock.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.lock.txt \
      --extra-index-url https://download.pytorch.org/whl/cpu

COPY packages/catalog ./packages/catalog
COPY packages/db ./packages/db
COPY workers ./workers
RUN pip install --no-cache-dir --no-deps \
      -e ./packages/catalog -e ./packages/db -e ./workers


FROM python:3.12-slim AS final

RUN groupadd --system modelforge && useradd --system --gid modelforge --create-home modelforge
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/packages /app/packages
COPY --from=builder /build/workers /app/workers

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app/workers
USER modelforge

ENTRYPOINT ["python", "-m", "core.runner"]
