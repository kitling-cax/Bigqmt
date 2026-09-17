# This image contains only the dependency-free Coordinator read-only surface.
# It has no QMT client, Redis client, broker credential, order writer, or NAS
# runtime mount.  Build from repository root:
# docker build -f container/coordinator/Dockerfile -t kitling-bigqmt-coordinator:<version> .
ARG PYTHON_BASE_IMAGE=python:3.12-slim
FROM ${PYTHON_BASE_IMAGE}

RUN useradd --system --uid 10001 --create-home --home-dir /nonexistent coordinator
WORKDIR /app
COPY src /app/src
COPY scripts/coordinator /app/scripts/coordinator
COPY progress/multi_host_program.yaml /app/progress/multi_host_program.yaml
COPY container/coordinator/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY container/coordinator/healthcheck.py /usr/local/bin/healthcheck.py
RUN chmod 0555 /usr/local/bin/entrypoint.sh /usr/local/bin/healthcheck.py

ENV PYTHONPATH=/app/src
ENV BIGQMT_COORDINATOR_BIND=0.0.0.0
ENV BIGQMT_COORDINATOR_PORT=18443
ENV BIGQMT_COORDINATOR_MODE=SHADOW_READONLY
ENV BIGQMT_EXECUTION_WRITES_DISABLED=1
ENV BIGQMT_LEASE_GRANTS_DISABLED=1
ENV BIGQMT_INTENT_CONFIRM_DISABLED=1
USER 10001:10001
EXPOSE 18443
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
