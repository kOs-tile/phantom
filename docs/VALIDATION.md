# Validation plan

PHANTOM's active thesis is provider-agnostic extraction reliability. Browser
execution is replaceable; contract evidence should remain deterministic.

## Primary safety metric

**False-pass rate:** percentage of broken/incomplete extraction payloads that
still pass their declared extraction contract.

Target for deterministic fixtures: **0**.

## Executable mutation corpus v0.1

The current versioned corpus contains 20 deterministic payload cases:

- canonical passing baseline
- missing required fields
- blank-but-present required fields
- missing nested objects
- null required values
- empty arrays
- broken nested/list paths
- scalar replacement of an expected structured object
- empty payload
- optional-field removal
- allowed value changes
- adversarial extra/noise fields
- key-order-only canonicalization case

Recorded CI checkpoint:

- broken/incomplete cases: **13**
- false-passes: **0**
- valid cases: **7**
- false-fails: **0**
- payload-drift expectation matches: **20/20**
- corpus version: **phantom.extraction-corpus.v1**

This benchmark exercises provider-agnostic extraction contracts directly. Static
HTML mutation and cross-provider browser/runtime validation remain future gates.

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

The versioned deterministic mutation-corpus requirement is now satisfied for the
contract layer. PHANTOM should not claim cross-provider extraction reliability
until the same contracts are exercised against at least two browser
providers/runtimes. Passing the payload corpus or Playwright-only tests is not
sufficient for that broader claim.
