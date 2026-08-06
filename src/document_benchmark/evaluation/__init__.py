"""Evaluation package."""

from document_benchmark.evaluation.disagreement import FieldComparisonRow, compute_cross_engine_disagreement
from document_benchmark.evaluation.evaluator import Evaluator, GroundTruthMetrics

__all__ = [
    "Evaluator",
    "FieldComparisonRow",
    "GroundTruthMetrics",
    "compute_cross_engine_disagreement",
]
