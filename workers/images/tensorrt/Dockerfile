# tensorrt worker image: NVIDIA TensorRT + cuda-python + ONNX Runtime (CPU, for the
# accuracy-check comparison in workers/ops/convert_tensorrt.py) + Ultralytics (for the
# YOLO->ONNX hop). Backs only c_tensorrt (`worker_image="tensorrt"`, `queue="gpu"` in
# packages/catalog/src/modelforge_catalog/converts.py) — split out from gpu-base
# deliberately: TensorRT's own wheel plus its CUDA runtime libraries are large, and
# bundling them into gpu-base (which backs the much more frequently queued q_gptq/q_awq/
# q_nf4 jobs) would make every one of those jobs' cold-start pull that much slower for a
# dependency they never use.
#
# Build from the repo root (needs packages/catalog, packages/db and workers/):
#   docker build -f workers/images/tensorrt/Dockerfile -t modelforge/tensorrt:dev .
#
# Needs an NVIDIA CUDA + TensorRT base (not python:slim) since `tensorrt`'s Python bindings
# load real CUDA/TensorRT shared libraries, not just a Python wheel — building (and running)
# an engine needs a real GPU, same constraint `gpu-base`'s Dockerfile documents for its own
# CUDA-dependent ops.

FROM nvcr.io/nvidia/tensorrt:24.08-py3 AS builder

WORKDIR /build
RUN python3 -m venv /opt/venv --system-site-packages
ENV PATH="/opt/venv/bin:$PATH"

COPY workers/images/tensorrt/requirements.lock.txt ./requirements.lock.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.lock.txt

COPY packages/catalog ./packages/catalog
COPY packages/db ./packages/db
COPY workers ./workers
RUN pip install --no-cache-dir --no-deps \
      -e ./packages/catalog -e ./packages/db -e ./workers


FROM nvcr.io/nvidia/tensorrt:24.08-py3 AS final

RUN groupadd --system modelforge && useradd --system --gid modelforge --create-home modelforge

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/packages /app/packages
COPY --from=builder /build/workers /app/workers

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app/workers
USER modelforge

ENTRYPOINT ["python3", "-m", "core.runner"]
