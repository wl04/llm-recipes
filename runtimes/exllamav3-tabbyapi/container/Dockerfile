FROM rocm/pytorch@sha256:099f59a3bee9c436f5cc57db6bc6076fdeda579c57e9e22ae40f856d5905b3e4
ARG MAX_JOBS=4
ENV MAX_JOBS=${MAX_JOBS} \
    PYTORCH_ROCM_ARCH=gfx1201 \
    TRITON_DEFAULT_BACKEND=amd \
    PYTHONPATH=/opt/dependencies \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /opt/build
COPY versions.lock.json requirements.lock fetch_sources.py ./
RUN python3 fetch_sources.py
# Install a hashed dependency overlay, preserving the base Torch/ROCm/Triton.
RUN python3 -m pip install --no-cache-dir --no-deps --require-hashes \
    --only-binary=:all: --target /opt/dependencies -r requirements.lock
RUN python3 -m pip wheel --no-deps --no-build-isolation \
    --wheel-dir /opt/wheels /opt/src/exllamav3 \
    && python3 -m pip install --no-deps --no-compile \
       --target /opt/dependencies /opt/wheels/exllamav3-*.whl
COPY check_image.py /opt/check_image.py
RUN python3 /opt/check_image.py --build-only
WORKDIR /opt/src/tabbyAPI
CMD ["python3", "/opt/check_image.py"]
