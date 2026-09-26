# Validation plan

PHANTOM's active thesis is provider-agnostic extraction reliability. Browser
execution is replaceable; contract evidence should remain deterministic.

## Primary safety metric

**False-pass rate:** percentage of broken/incomplete extraction payloads that
still pass their declared extraction contract.

Target for deterministic fixtures: **0**.

## Benchmark corpus v0.1

- static HTML snapshots from multiple site shapes
- selector breakages
- missing required fields
- blank-but-present fields
- nested/list payloads
- locale-specific price formats
- JSON-LD/OpenGraph fallbacks
- layout mutations
- provider-normalization differences
- replay pairs with known drift
- adversarial extra fields/noise

## Metrics

- contract false-pass rate
- required-field coverage accuracy
- drift detection recall
- missing-field detection recall
- fingerprint determinism
- cross-provider payload agreement
- validation latency
- contract maintenance burden

## Exit gate

PHANTOM can claim extraction reliability only after the same contracts are run
against a versioned mutation corpus and at least two browser providers/runtimes.
Passing Playwright-only unit tests is not sufficient.
