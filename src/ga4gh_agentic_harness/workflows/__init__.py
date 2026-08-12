"""Executable realizations of the pilot GA4GH Agentic Workflow Profiles."""

from .conformance_assessment import run as run_conformance_assessment
from .federated_wes_analysis import run as run_federated_wes_analysis
from .variant_evidence_assembly import run as run_variant_evidence_assembly

__all__ = [
    "run_conformance_assessment",
    "run_federated_wes_analysis",
    "run_variant_evidence_assembly",
]
