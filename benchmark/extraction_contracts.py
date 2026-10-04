"""Versioned deterministic mutation corpus for PHANTOM extraction contracts."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass

from phantom.reliability import (
    ExtractionContract,
    compare_extractions,
    evaluate_extraction_contract,
)


CORPUS_VERSION = "phantom.extraction-corpus.v1"


BASELINE = {
    "product": {
        "title": "Widget Pro",
        "price": {"amount": 29.99, "currency": "USD"},
        "seller": "Acme",
        "items": [
            {"name": "Widget Pro", "sku": "W-001"},
            {"name": "Widget Case", "sku": "C-002"},
        ],
    },
    "metadata": {"source": "fixture"},
}


CONTRACT = ExtractionContract(
    required_fields=[
        "product.title",
        "product.price.amount",
        "product.price.currency",
        "product.items.0.name",
    ],
    optional_fields=[
        "product.seller",
        "product.items.1.name",
    ],
    min_required_coverage=1.0,
)


@dataclass(frozen=True)
class MutationCase:
    label: str
    payload: dict
    expected_pass: bool
    expected_payload_changed: bool


def _mutate(fn) -> dict:
    payload = copy.deepcopy(BASELINE)
    fn(payload)
    return payload


def build_cases() -> list[MutationCase]:
    cases = [
        MutationCase("baseline", copy.deepcopy(BASELINE), True, False),
        MutationCase(
            "missing_title",
            _mutate(lambda p: p["product"].pop("title")),
            False,
            True,
        ),
        MutationCase(
            "blank_title",
            _mutate(lambda p: p["product"].__setitem__("title", "   ")),
            False,
            True,
        ),
        MutationCase(
            "missing_price",
            _mutate(lambda p: p["product"].pop("price")),
            False,
            True,
        ),
        MutationCase(
            "missing_price_amount",
            _mutate(lambda p: p["product"]["price"].pop("amount")),
            False,
            True,
        ),
        MutationCase(
            "null_price_amount",
            _mutate(lambda p: p["product"]["price"].__setitem__("amount", None)),
            False,
            True,
        ),
        MutationCase(
            "missing_currency",
            _mutate(lambda p: p["product"]["price"].pop("currency")),
            False,
            True,
        ),
        MutationCase(
            "blank_currency",
            _mutate(lambda p: p["product"]["price"].__setitem__("currency", "")),
            False,
            True,
        ),
        MutationCase(
            "missing_items",
            _mutate(lambda p: p["product"].pop("items")),
            False,
            True,
        ),
        MutationCase(
            "empty_items",
            _mutate(lambda p: p["product"].__setitem__("items", [])),
            False,
            True,
        ),
        MutationCase(
            "missing_first_item_name",
            _mutate(lambda p: p["product"]["items"][0].pop("name")),
            False,
            True,
        ),
        MutationCase(
            "blank_first_item_name",
            _mutate(
                lambda p: p["product"]["items"][0].__setitem__("name", "")
            ),
            False,
            True,
        ),
        MutationCase(
            "product_replaced_with_scalar",
            {"product": "not-a-structured-payload"},
            False,
            True,
        ),
        MutationCase(
            "empty_payload",
            {},
            False,
            True,
        ),
        MutationCase(
            "optional_seller_removed",
            _mutate(lambda p: p["product"].pop("seller")),
            True,
            True,
        ),
        MutationCase(
            "price_changed",
            _mutate(
                lambda p: p["product"]["price"].__setitem__("amount", 31.49)
            ),
            True,
            True,
        ),
        MutationCase(
            "title_changed",
            _mutate(lambda p: p["product"].__setitem__("title", "Widget Pro 2")),
            True,
            True,
        ),
        MutationCase(
            "extra_noise",
            _mutate(lambda p: p.__setitem__("noise", {"unexpected": [1, 2, 3]})),
            True,
            True,
        ),
        MutationCase(
            "optional_second_item_removed",
            _mutate(lambda p: p["product"]["items"].pop(1)),
            True,
            True,
        ),
        MutationCase(
            "key_order_only",
            {
                "metadata": {"source": "fixture"},
                "product": {
                    "items": [
                        {"sku": "W-001", "name": "Widget Pro"},
                        {"sku": "C-002", "name": "Widget Case"},
                    ],
                    "seller": "Acme",
                    "price": {"currency": "USD", "amount": 29.99},
                    "title": "Widget Pro",
                },
            },
            True,
            False,
        ),
    ]
    assert len(cases) == 20
    return cases


def run_benchmark() -> dict:
    rows = []
    broken = 0
    false_passes = 0
    valid = 0
    false_fails = 0
    drift_expected = 0
    drift_correct = 0

    for case in build_cases():
        quality = evaluate_extraction_contract(case.payload, CONTRACT)
        drift = compare_extractions(BASELINE, case.payload, CONTRACT)

        if case.expected_pass:
            valid += 1
            false_fails += int(not quality.passed)
        else:
            broken += 1
            false_passes += int(quality.passed)

        if case.expected_payload_changed:
            drift_expected += 1
            drift_correct += int(drift.payload_changed)
        else:
            drift_correct += int(not drift.payload_changed)

        rows.append(
            {
                "label": case.label,
                "expected_pass": case.expected_pass,
                "actual_pass": quality.passed,
                "required_coverage": quality.required_coverage,
                "missing_required": quality.missing_required,
                "empty_required": quality.empty_required,
                "expected_payload_changed": case.expected_payload_changed,
                "actual_payload_changed": drift.payload_changed,
                "quality_report_fingerprint": quality.report_fingerprint,
                "drift_report_fingerprint": drift.report_fingerprint,
            }
        )

    total = len(rows)
    return {
        "corpus_version": CORPUS_VERSION,
        "cases": total,
        "broken_cases": broken,
        "false_passes": false_passes,
        "false_pass_rate": false_passes / broken,
        "valid_cases": valid,
        "false_fails": false_fails,
        "false_fail_rate": false_fails / valid,
        "drift_expectation_matches": drift_correct,
        "drift_expectation_rate": drift_correct / total,
        "results": rows,
    }


if __name__ == "__main__":
    print(json.dumps(run_benchmark(), indent=2))
