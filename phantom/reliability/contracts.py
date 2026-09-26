"""Deterministic extraction contracts and evidence reports.

These primitives intentionally do not depend on Playwright. They can validate
payloads produced by PHANTOM, Browserbase, Cloudflare Browser Rendering, an MCP
browser tool, or any other extraction provider.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


_MISSING = object()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _resolve_path(payload: Any, path: str) -> Any:
    """Resolve dot-separated dict/list paths such as product.price or items.0.name."""
    current = payload
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return _MISSING
            current = current[segment]
            continue
        if isinstance(current, list):
            try:
                index = int(segment)
            except ValueError:
                return _MISSING
            if index < 0 or index >= len(current):
                return _MISSING
            current = current[index]
            continue
        return _MISSING
    return current


def _is_non_empty(value: Any) -> bool:
    if value is _MISSING or value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


class ExtractionContract(BaseModel):
    """Expected shape for a browser/extraction payload."""

    required_fields: list[str] = Field(default_factory=list)
    optional_fields: list[str] = Field(default_factory=list)
    min_required_coverage: float = Field(default=1.0, ge=0.0, le=1.0)
    allow_empty_required: bool = False
    contract_version: str = "1"

    @field_validator("required_fields", "optional_fields")
    @classmethod
    def normalize_paths(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            path = value.strip().strip(".")
            if not path:
                continue
            if path not in seen:
                normalized.append(path)
                seen.add(path)
        return normalized

    @model_validator(mode="after")
    def disjoint_fields(self) -> "ExtractionContract":
        overlap = set(self.required_fields) & set(self.optional_fields)
        if overlap:
            raise ValueError(
                "Fields cannot be both required and optional: "
                + ", ".join(sorted(overlap))
            )
        return self


class FieldEvidence(BaseModel):
    path: str
    present: bool
    non_empty: bool
    satisfied: bool
    value_type: str | None = None
    value_fingerprint: str | None = None


class ExtractionQualityReport(BaseModel):
    passed: bool
    required_coverage: float = Field(ge=0.0, le=1.0)
    total_required: int = Field(ge=0)
    satisfied_required: int = Field(ge=0)
    missing_required: list[str] = Field(default_factory=list)
    empty_required: list[str] = Field(default_factory=list)
    observed_fields: list[str] = Field(default_factory=list)
    evidence: dict[str, FieldEvidence] = Field(default_factory=dict)
    payload_fingerprint: str
    contract_fingerprint: str
    report_fingerprint: str = ""


class ExtractionValidationRequest(BaseModel):
    data: dict[str, Any]
    contract: ExtractionContract


class ExtractionDriftRequest(BaseModel):
    baseline: dict[str, Any]
    current: dict[str, Any]
    contract: ExtractionContract


class ExtractionDriftReport(BaseModel):
    contract_fingerprint: str
    baseline_payload_fingerprint: str
    current_payload_fingerprint: str
    payload_changed: bool
    current_contract_passed: bool
    changed_fields: list[str] = Field(default_factory=list)
    missing_now: list[str] = Field(default_factory=list)
    newly_present: list[str] = Field(default_factory=list)
    stable_fields: list[str] = Field(default_factory=list)
    report_fingerprint: str = ""


def evaluate_extraction_contract(
    data: dict[str, Any],
    contract: ExtractionContract,
) -> ExtractionQualityReport:
    """Evaluate an extraction payload without trusting the browser/provider."""
    evidence: dict[str, FieldEvidence] = {}
    missing_required: list[str] = []
    empty_required: list[str] = []
    satisfied_required = 0

    all_paths = contract.required_fields + contract.optional_fields
    for path in all_paths:
        value = _resolve_path(data, path)
        present = value is not _MISSING
        non_empty = _is_non_empty(value)
        required = path in contract.required_fields
        satisfied = present and (
            non_empty or (required and contract.allow_empty_required) or not required
        )

        if required:
            if not present:
                missing_required.append(path)
            elif not non_empty and not contract.allow_empty_required:
                empty_required.append(path)
            else:
                satisfied_required += 1

        evidence[path] = FieldEvidence(
            path=path,
            present=present,
            non_empty=non_empty,
            satisfied=satisfied,
            value_type=type(value).__name__ if present else None,
            value_fingerprint=_fingerprint(value) if present else None,
        )

    total_required = len(contract.required_fields)
    required_coverage = (
        satisfied_required / total_required if total_required else 1.0
    )
    passed = required_coverage >= contract.min_required_coverage

    report = ExtractionQualityReport(
        passed=passed,
        required_coverage=round(required_coverage, 6),
        total_required=total_required,
        satisfied_required=satisfied_required,
        missing_required=missing_required,
        empty_required=empty_required,
        observed_fields=[path for path, item in evidence.items() if item.present],
        evidence=evidence,
        payload_fingerprint=_fingerprint(data),
        contract_fingerprint=_fingerprint(contract.model_dump(mode="json")),
    )
    report.report_fingerprint = _fingerprint(
        report.model_dump(exclude={"report_fingerprint"}, mode="json")
    )
    return report



def compare_extractions(
    baseline: dict[str, Any],
    current: dict[str, Any],
    contract: ExtractionContract,
) -> ExtractionDriftReport:
    """Compare two payloads under the same deterministic extraction contract."""
    baseline_report = evaluate_extraction_contract(baseline, contract)
    current_report = evaluate_extraction_contract(current, contract)

    changed_fields: list[str] = []
    missing_now: list[str] = []
    newly_present: list[str] = []
    stable_fields: list[str] = []

    for path in contract.required_fields + contract.optional_fields:
        before = baseline_report.evidence[path]
        after = current_report.evidence[path]

        if before.present and not after.present:
            missing_now.append(path)
        elif not before.present and after.present:
            newly_present.append(path)
        elif before.present and after.present:
            if before.value_fingerprint != after.value_fingerprint:
                changed_fields.append(path)
            else:
                stable_fields.append(path)

    report = ExtractionDriftReport(
        contract_fingerprint=current_report.contract_fingerprint,
        baseline_payload_fingerprint=baseline_report.payload_fingerprint,
        current_payload_fingerprint=current_report.payload_fingerprint,
        payload_changed=(
            baseline_report.payload_fingerprint
            != current_report.payload_fingerprint
        ),
        current_contract_passed=current_report.passed,
        changed_fields=changed_fields,
        missing_now=missing_now,
        newly_present=newly_present,
        stable_fields=stable_fields,
    )
    report.report_fingerprint = _fingerprint(
        report.model_dump(exclude={"report_fingerprint"}, mode="json")
    )
    return report
