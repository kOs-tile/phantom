"""Provider-agnostic extraction reliability primitives."""

from phantom.reliability.contracts import (
    ExtractionContract,
    ExtractionDriftReport,
    ExtractionDriftRequest,
    ExtractionQualityReport,
    ExtractionValidationRequest,
    FieldEvidence,
    compare_extractions,
    evaluate_extraction_contract,
)

__all__ = [
    "ExtractionContract",
    "ExtractionDriftReport",
    "ExtractionDriftRequest",
    "ExtractionQualityReport",
    "ExtractionValidationRequest",
    "FieldEvidence",
    "compare_extractions",
    "evaluate_extraction_contract",
]
