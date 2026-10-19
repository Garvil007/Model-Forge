# cpu-convert worker image: PyTorch CPU + TensorFlow + OpenVINO/NNCF + onnx2tf/onnx2torch/
# tf2onnx + Optimum + Ultralytics. Backs the Convert tab's c_onnx, c_tflite,
# c_torchscript, c_savedmodel, c_safetensors and c_openvino jobs (everything except
# TensorRT and Core ML) — a single combined image rather than splitting across
# cpu-torch/cpu-tf because several of these ops need both frameworks within one job (see
# requirements.lock.txt's header for why).
#
# Build from the repo root (needs packages/catalog, packages/db and workers/):
#   docker build -f workers/images/cpu-convert/Dockerfile -t modelforge/cpu-convert:dev .
#
# Multi-stage: the builder stage compiles into a venv using the pinned lock file; the
# final stage copies only that venv plus the three packages' source onto a slim base, so
# build tooling (gcc, pip's wheel cache) never reaches the image that actually runs jobs.

FROM python:3.12-slim AS builder

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY workers/images/cpu-convert/requirements.lock.txt ./requirements.lock.txt
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
    PYTHONDONTWRITEBYTECODE=1 \
    TF_CPP_MIN_LOG_LEVEL=2

WORKDIR /app/workers
USER modelforge

ENTRYPOINT ["python", "-m", "core.runner"]
