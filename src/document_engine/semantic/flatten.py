"""Utilities for flattening nested semantic extraction output into atomic field paths."""

from typing import Any, List, Tuple


AtomicValue = Tuple[str, Any]


def flatten_semantic_data(data: Any, prefix: str = "") -> tuple[List[AtomicValue], List[str]]:
    """Flatten nested dict/list data into canonical-like atomic field paths.

    Null scalar values are returned as abstained field paths. Empty containers do
    not fabricate dynamic indices.
    """
    values: List[AtomicValue] = []
    abstained: List[str] = []

    if isinstance(data, dict):
        for key, value in data.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            child_values, child_abstained = flatten_semantic_data(value, child)
            values.extend(child_values)
            abstained.extend(child_abstained)
        return values, abstained

    if isinstance(data, list):
        for index, value in enumerate(data):
            child = f"{prefix}[{index}]"
            child_values, child_abstained = flatten_semantic_data(value, child)
            values.extend(child_values)
            abstained.extend(child_abstained)
        return values, abstained

    if not prefix:
        return values, abstained

    if data is None:
        abstained.append(prefix)
    else:
        values.append((prefix, data))

    return values, abstained
