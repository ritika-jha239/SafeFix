# syntax=docker/dockerfile:1
FROM python:3.12-slim
RUN --mount=type=secret,id=proxy_ca \
    apt-get update && apt-get install -y --no-install-recommends build-essential gfortran pkg-config git libopenblas-dev && rm -rf /var/lib/apt/lists/*
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir 'pytest==8.3.5' hypothesis pytest-xdist pytest-timeout pytest-cov mpmath tzdata 'numpy>=2,!=2.5.0' scipy 'Cython>=3.1.2,<3.2.6' meson-python ninja versioneer joblib threadpoolctl narwhals
ARG PROJECT
ARG COMMIT
ARG PACKAGE
LABEL safefix.repository=$PROJECT safefix.commit=$COMMIT
ENV SAFEFIX_OVERLAY_PACKAGE=$PACKAGE OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
COPY . /opt/source
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    case "$PROJECT" in \
      pandas-dev/pandas) pip install --no-cache-dir --no-build-isolation --config-settings=compile-args=-j2 '/opt/source[test]' ;; \
      scikit-learn/scikit-learn) pip install --no-cache-dir --no-build-isolation --config-settings=compile-args=-j2 /opt/source ;; \
      sympy/sympy) pip install --no-cache-dir /opt/source ;; \
      *) exit 1 ;; \
    esac
COPY --chmod=644 .safefix-runner-entrypoint.py /opt/safefix-entrypoint.py
WORKDIR /repo
ENTRYPOINT ["python", "/opt/safefix-entrypoint.py"]
