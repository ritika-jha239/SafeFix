# syntax=docker/dockerfile:1
FROM python:3.12-slim
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then \
      PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir pytest==8.3.5; \
    else pip install --no-cache-dir pytest==8.3.5; fi
# Add selected repository runtime/test dependencies to a derived image.
# Do not copy API keys or Git credentials into this image.
WORKDIR /repo
