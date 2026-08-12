# Local development

## Architecture

`Harness` owns canonical operation semantics. `ServiceRegistry` normalizes registry records;
DRS, TRS, Beacon v2, and WES adapters map operations to native APIs; `SafeHttpClient` enforces
transport policy; and `WorkflowRunLedger` stores WES submission state in SQLite.

Endpoints do not have to appear in the public implementation registry. Pass trusted,
explicit `ServiceDescriptor` values through `ServiceRegistry(..., static_services=[...])` for
private services, local services, or public services discovered out of band.

The default policy allows read-only operations. WES submission and cancellation require the
profile scopes `ga4gh:workflow:submit` and `ga4gh:workflow:cancel` respectively (or `ga4gh:*`):

```bash
uv run ga4gh-harness ga4gh.wes.run.cancel \
  --scope ga4gh:workflow:cancel \
  --input '{"service_id":"example-wes","run_id":"run-123"}'
```

This only satisfies the local Harness policy. The target WES still makes the final
authorization decision.

## Tests

The default test suite is fully mocked and makes no network calls:

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

Live tests are disabled unless both the marker and environment flag are supplied:

```bash
uv run pytest -m live --run-live
```

Live tests are read-only. No live WES submission or cancellation is part of the suite.

## Local Docker image

Build and invoke the image without deploying it:

```bash
docker build -t ga4gh-agentic-harness:local .
docker run --rm ga4gh-agentic-harness:local ga4gh.harness.describe --pretty
```

Persist a local WES ledger by mounting `/data` and setting
`GA4GH_HARNESS_LEDGER_PATH=/data/runs.db`. Do not bake tokens into the image. Pass local test
credentials as runtime environment variables and use a pinned `CredentialProvider` in Python.

## Transport defaults

- HTTPS is required.
- Private, loopback, link-local, reserved, and metadata destinations are blocked.
- Credentialed redirects cannot cross origins.
- GET, HEAD, and OPTIONS receive bounded retries; mutations do not.
- Responses are size-limited and transport errors become structured envelopes.

Private endpoints can be tested by explicitly setting
`GA4GH_HARNESS_ALLOW_PRIVATE_HOSTS=true`. Use this only in a controlled local network and
prefer `GA4GH_HARNESS_ALLOWED_HOSTS` to restrict the destinations.

For a local GA4GH Service Registry, the equivalent explicit CLI invocation is:

```bash
uv run ga4gh-harness ga4gh.service.search \
  --registry-url http://127.0.0.1:18080/ga4gh/registry \
  --allow-http --allow-private-hosts \
  --input '{"product":"drs"}' --pretty
```

The HTTP and private-host flags are opt-in and should not be used for remote services.
