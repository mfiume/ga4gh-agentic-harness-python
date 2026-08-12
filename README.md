# GA4GH Agentic Harness Python

An experimental, protocol-neutral async SDK for discovering and invoking GA4GH services
through the Agentic Harness Profile. It is local-development software, not a GA4GH-approved
standard or certification service.

The package exposes the approved canonical operations through the same `Harness` class used
by the JSON CLI. It has no dependency on MCP; MCP can be implemented as a thin binding over
this package later.

## Local setup

Python 3.10 or newer and [uv](https://docs.astral.sh/uv/) are expected.

```bash
uv sync --extra dev
uv run pytest
uv run ga4gh-harness ga4gh.harness.describe --pretty
```

Search the public implementation registry:

```bash
uv run ga4gh-harness ga4gh.service.search \
  --input '{"product":"DRS","limit":5}' --pretty
```

The CLI reads settings prefixed with `GA4GH_HARNESS_`. For example, use a temporary local
ledger without changing the default directory:

```bash
GA4GH_HARNESS_LEDGER_PATH=/tmp/ga4gh-runs.db \
  uv run ga4gh-harness ga4gh.harness.describe
```

See [docs/local-development.md](docs/local-development.md) for adapters, authentication,
testing, and Docker usage.

## Python API

```python
from ga4gh_agentic_harness import Harness

async with Harness() as harness:
    result = await harness.service_search(product="Beacon")
    print(result.model_dump(mode="json"))
```

All public operation results use the common envelope:

- `profile_version`
- `operation`
- `request_id`
- `status`: `success`, `partial`, or `failure`
- `data`, `errors`, and `warnings`
- `trace_id` and `evidence`
- optional `page`

## Security boundary

Inbound Harness authority and outbound service credentials are separate. The SDK never
forwards an inbound token. Outbound credentials are opaque runtime objects that are passed
only to the safe HTTP client. Tokens, authorization headers, signed URL queries, and DRS
access headers are excluded or redacted from envelopes and traces.

The environment bearer provider is for local integration testing. It requires explicit
service ID and audience pinning. Production providers should implement broker-backed OAuth,
OIDC, token exchange, or GA4GH Passport behavior behind the `CredentialProvider` protocol.

