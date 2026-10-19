# cpu-llm worker image: llama.cpp built from source (llama-quantize, llama-imatrix,
# llama-perplexity, convert_hf_to_gguf.py) plus a Python venv (torch CPU, transformers,
# huggingface-hub, gguf) for downloading HF repos and running the converter script.
# Backs q_gguf (GGUF quantization) and c_gguf (plain GGUF conversion) — both CPU work,
# far cheaper than the gpu-base image q_gptq/q_awq/q_nf4 need.
#
# Build from the repo root (needs packages/catalog, packages/db and workers/):
#   docker build -f workers/images/cpu-llm/Dockerfile -t modelforge/cpu-llm:dev .
#
# Multi-stage: a C++ builder stage compiles llama.cpp with cmake; a Python builder stage
# installs the pinned lock file into a venv; the final stage copies only the built
# binaries/scripts, the venv, and the three packages' source onto a slim base, so build
# tooling (cmake, g++, git, pip's wheel cache) never reaches the image that runs jobs.

FROM python:3.12-slim AS llama-cpp-builder

RUN apt-get update \
 && apt-get install -y --no-install-recommends git cmake g++ make \
 && rm -rf /var/lib/apt/lists/*

# Pinned to a specific llama.cpp release tag, not a moving branch, so a rebuild is
# reproducible. Bump deliberately, re-verify convert_hf_to_gguf.py's CLI flags and
# llama-quantize's supported type names haven't changed, and update this comment.
ARG LLAMA_CPP_REF=b4409
RUN git clone --depth 1 --branch ${LLAMA_CPP_REF} https://github.com/ggerganov/llama.cpp.git /opt/llama.cpp
WORKDIR /opt/llama.cpp
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF \
 && cmake --build build --config Release -j"$(nproc)" --target llama-quantize llama-imatrix llama-perplexity


FROM python:3.12-slim AS python-builder

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY workers/images/cpu-llm/requirements.lock.txt ./requirements.lock.txt
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

COPY --from=llama-cpp-builder /opt/llama.cpp/build/bin/llama-quantize /opt/llama.cpp/build/bin/llama-quantize
COPY --from=llama-cpp-builder /opt/llama.cpp/build/bin/llama-imatrix /opt/llama.cpp/build/bin/llama-imatrix
COPY --from=llama-cpp-builder /opt/llama.cpp/build/bin/llama-perplexity /opt/llama.cpp/build/bin/llama-perplexity
COPY --from=llama-cpp-builder /opt/llama.cpp/convert_hf_to_gguf.py /opt/llama.cpp/convert_hf_to_gguf.py
COPY --from=llama-cpp-builder /opt/llama.cpp/gguf-py /opt/llama.cpp/gguf-py
COPY --from=python-builder /opt/venv /opt/venv
COPY --from=python-builder /build/packages /app/packages
COPY --from=python-builder /build/workers /app/workers

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MF_LLAMA_CPP_CONVERT_SCRIPT=/opt/llama.cpp/convert_hf_to_gguf.py \
    MF_LLAMA_QUANTIZE_BIN=/opt/llama.cpp/build/bin/llama-quantize \
    MF_LLAMA_IMATRIX_BIN=/opt/llama.cpp/build/bin/llama-imatrix \
    MF_LLAMA_PERPLEXITY_BIN=/opt/llama.cpp/build/bin/llama-perplexity \
    MF_LLAMA_CPP_PYTHON=/opt/venv/bin/python

# convert_hf_to_gguf.py imports gguf-py as a plain sibling package (sys.path trick in
# its own __main__), not an installed distribution — PYTHONPATH covers that.
ENV PYTHONPATH="/opt/llama.cpp/gguf-py:${PYTHONPATH}"

WORKDIR /app/workers
USER modelforge

ENTRYPOINT ["python", "-m", "core.runner"]
