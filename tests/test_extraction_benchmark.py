from benchmark.extraction_contracts import build_cases, run_benchmark


def test_extraction_mutation_corpus_shape_is_stable():
    cases = build_cases()

    assert len(cases) == 20
    assert sum(not case.expected_pass for case in cases) == 13
    assert sum(case.expected_pass for case in cases) == 7


def test_extraction_mutation_benchmark_meets_v0_contract():
    result = run_benchmark()

    assert result["corpus_version"] == "phantom.extraction-corpus.v1"
    assert result["cases"] == 20
    assert result["broken_cases"] == 13
    assert result["false_passes"] == 0
    assert result["false_pass_rate"] == 0.0
    assert result["valid_cases"] == 7
    assert result["false_fails"] == 0
    assert result["false_fail_rate"] == 0.0
    assert result["drift_expectation_matches"] == 20
    assert result["drift_expectation_rate"] == 1.0
