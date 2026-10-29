# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim
RUN --mount=type=secret,id=proxy_ca \
    apt-get update && apt-get install -y --no-install-recommends build-essential gfortran pkg-config git libopenblas-dev && rm -rf /var/lib/apt/lists/*
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca SSL_CERT_FILE=/run/secrets/proxy_ca GIT_SSL_CAINFO=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir pytest hypothesis
COPY . /opt/source
COPY --chmod=644 .safefix-environment.json /opt/safefix-environment.json
COPY --chmod=644 .safefix-build.py /opt/safefix-build.py
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca SSL_CERT_FILE=/run/secrets/proxy_ca GIT_SSL_CAINFO=/run/secrets/proxy_ca; fi; \
    python /opt/safefix-build.py
COPY --chmod=644 .safefix-entrypoint.py /opt/safefix-entrypoint.py
ARG PROJECT
ARG COMMIT
LABEL safefix.repository=$PROJECT safefix.commit=$COMMIT safefix.runner=generic
WORKDIR /repo
ENTRYPOINT ["python", "/opt/safefix-entrypoint.py"]
