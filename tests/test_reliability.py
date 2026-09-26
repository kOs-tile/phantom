from phantom.reliability.contracts import (
    ExtractionContract,
    evaluate_extraction_contract,
)


def test_full_required_coverage_passes():
    contract = ExtractionContract(
        required_fields=["product.title", "product.price.amount"],
        optional_fields=["product.seller"],
    )
    payload = {
        "product": {
            "title": "Widget",
            "price": {"amount": 19.99},
        }
    }

    report = evaluate_extraction_contract(payload, contract)

    assert report.passed is True
    assert report.required_coverage == 1.0
    assert report.missing_required == []
    assert report.empty_required == []
    assert report.evidence["product.price.amount"].value_type == "float"


def test_missing_required_field_fails_closed():
    contract = ExtractionContract(
        required_fields=["title", "price"],
        min_required_coverage=1.0,
    )
    report = evaluate_extraction_contract({"title": "Widget"}, contract)

    assert report.passed is False
    assert report.required_coverage == 0.5
    assert report.missing_required == ["price"]


def test_blank_required_field_is_not_satisfied_by_default():
    contract = ExtractionContract(required_fields=["title"])
    report = evaluate_extraction_contract({"title": "   "}, contract)

    assert report.passed is False
    assert report.empty_required == ["title"]


def test_partial_coverage_threshold_is_explicit():
    contract = ExtractionContract(
        required_fields=["title", "price", "currency"],
        min_required_coverage=2 / 3,
    )
    report = evaluate_extraction_contract(
        {"title": "Widget", "price": 10.0},
        contract,
    )

    assert report.passed is True
    assert report.satisfied_required == 2
    assert report.missing_required == ["currency"]


def test_nested_list_paths_are_supported():
    contract = ExtractionContract(
        required_fields=["items.0.name", "items.1.name"],
    )
    report = evaluate_extraction_contract(
        {"items": [{"name": "A"}, {"name": "B"}]},
        contract,
    )

    assert report.passed is True


def test_fingerprints_are_canonical_and_deterministic():
    contract = ExtractionContract(required_fields=["a", "b"])
    first = evaluate_extraction_contract({"b": 2, "a": 1}, contract)
    second = evaluate_extraction_contract({"a": 1, "b": 2}, contract)

    assert first.payload_fingerprint == second.payload_fingerprint
    assert first.contract_fingerprint == second.contract_fingerprint


def test_payload_change_changes_fingerprint():
    contract = ExtractionContract(required_fields=["price"])
    first = evaluate_extraction_contract({"price": 10.0}, contract)
    second = evaluate_extraction_contract({"price": 11.0}, contract)

    assert first.payload_fingerprint != second.payload_fingerprint
    assert (
        first.evidence["price"].value_fingerprint
        != second.evidence["price"].value_fingerprint
    )


def test_optional_missing_field_does_not_fail_contract():
    contract = ExtractionContract(
        required_fields=["title"],
        optional_fields=["seller"],
    )
    report = evaluate_extraction_contract({"title": "Widget"}, contract)

    assert report.passed is True
    assert report.evidence["seller"].present is False
