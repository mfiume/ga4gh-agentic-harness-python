FROM python:3.12-slim AS builder

WORKDIR /build
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv build --wheel && uv pip install --system --target /install dist/*.whl

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 harness
COPY --from=builder /install /usr/local/lib/python3.12/site-packages
USER harness
WORKDIR /home/harness
ENTRYPOINT ["python", "-m", "ga4gh_agentic_harness"]
CMD ["ga4gh.harness.describe", "--pretty"]
