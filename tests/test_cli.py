from __future__ import annotations

from ga4gh_agentic_harness.cli import build_parser


def test_local_transport_options_are_explicit() -> None:
    args = build_parser().parse_args(
        [
            "ga4gh.service.search",
            "--registry-url",
            "http://127.0.0.1:18080/ga4gh/registry",
            "--allow-http",
            "--allow-private-hosts",
        ]
    )
    assert args.registry_url.endswith("/ga4gh/registry")
    assert args.allow_http is True
    assert args.allow_private_hosts is True
