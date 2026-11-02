FROM python:3.12-slim-bookworm
ARG DSH_SDK_VERSION=""
RUN set -eux; \
    if [ -n "$DSH_SDK_VERSION" ]; then \
      python -m pip install --no-cache-dir "deepseek-harness-sdk==${DSH_SDK_VERSION}"; \
    else \
      python -m pip install --no-cache-dir deepseek-harness-sdk; \
    fi; \
    python -m pip check
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOME=/sandbox/state DSH_HOME=/sandbox/state
RUN mkdir -p /sandbox/lab /sandbox/state /sandbox/workspace /sandbox/results
WORKDIR /sandbox/workspace
USER 10001:10001
CMD ["python", "/sandbox/lab/src/run_phase0.py", "--help"]
