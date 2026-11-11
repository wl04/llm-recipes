FROM rocm/dev-ubuntu-24.04@sha256:5ed1362ea542a928651e4c710b44024ebe98870f74159cb70f0265aec8ef0abe

ARG MAX_JOBS=4
ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/opt/venv/bin:/opt/rocm/bin:$PATH \
    PYTHONPATH=/opt/src/strata:/opt/src/llama_cpp/gguf-py \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ROCM_PATH=/opt/rocm \
    HIP_PATH=/opt/rocm

# A dated Ubuntu snapshot locks the distribution build dependencies.
RUN rm -f /etc/apt/sources.list /etc/apt/sources.list.d/* \
    && printf '%s\n' \
       'deb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/20261111T000000Z noble main universe' \
       'deb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/20261111T000000Z noble-updates main universe' \
       'deb [check-valid-until=no] https://snapshot.ubuntu.com/ubuntu/20261111T000000Z noble-security main universe' \
       > /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends build-essential ca-certificates git \
       python3 python3-venv libnuma-dev libgomp1 libatomic1 libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY versions.lock.json requirements.lock build-requirements.lock fetch_sources.py check_image.py check_hip.cpp /opt/build/
RUN python3 -m venv /opt/venv \
    && python3 -m pip install --require-hashes --no-deps --only-binary=:all: \
       -r /opt/build/requirements.lock -r /opt/build/build-requirements.lock \
    && python3 -m pip check \
    && python3 /opt/build/fetch_sources.py

# CMake can link ROCm libraries by absolute path; relocated executables also
# need those directories registered with the runtime loader.
RUN set -eux; \
    printf '%s\n' /opt/rocm/lib /opt/rocm/lib64 > /etc/ld.so.conf.d/strata-rocm.conf; \
    find -L /opt/rocm -name 'libhipblas.so.3' -printf '%h\n' \
      >> /etc/ld.so.conf.d/strata-rocm.conf; \
    ldconfig; \
    ldconfig -p | grep -F 'libhipblas.so.3'

RUN set -eux; command -v hipcc; hipcc --version

RUN set -eux; cmake -S /opt/src/strata -B /opt/build/engine -G Ninja \
       -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=/opt/rocm \
       -DSTRATA_ENABLE_HIP=ON -DSTRATA_ENABLE_CUDA=OFF \
       -DCMAKE_HIP_ARCHITECTURES=gfx1201 -DSTRATA_BUILD_TESTS=OFF \
       -DSTRATA_PREFILL_MMQ=ON -DSTRATA_PORTABLE=ON \
    && cmake --build /opt/build/engine --target strata --parallel "$MAX_JOBS"

RUN set -eux; cmake -S /opt/src/strata/tools/vision -B /opt/build/vision -G Ninja \
       -DCMAKE_BUILD_TYPE=Release -DLLAMA_DIR=/opt/src/llama_cpp \
       -DSTRATA_VISION_CUDA=OFF -DSTRATA_VISION_HIP=OFF -DSTRATA_PORTABLE=ON \
    && cmake --build /opt/build/vision --target strata-vision --parallel "$MAX_JOBS"

RUN set -eux; mkdir -p /opt/strata/bin \
    && cp /opt/build/engine/strata /opt/build/vision/bin/strata-vision /opt/strata/bin/

RUN set -eux; hipcc --offload-arch=gfx1201 /opt/build/check_hip.cpp -o /opt/strata/bin/check_hip

RUN python3 -c 'import serve.server'

RUN set -eux; ldd /opt/strata/bin/strata; /opt/strata/bin/strata --help

RUN set -eux; ldd /opt/strata/bin/strata-vision; /opt/strata/bin/strata-vision --version

WORKDIR /opt/src/strata
CMD ["python3", "/opt/build/check_image.py"]
