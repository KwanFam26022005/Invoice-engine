"""Field path resolution and manipulation utility for Pydantic models, dicts, and lists."""

import re
from typing import Any, List, Tuple

# Matches either a key name (e.g. 'common', 'seller') or an indexed key (e.g. 'line_items[0]')
_PATH_TOKEN_REGEX = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)(?:\[(\d+)\])?$")


def parse_field_path(path: str) -> List[Tuple[str, int | None]]:
    """Parse a dot-separated field path into a list of (key, optional_index) tuples.

    Examples:
        'common.seller.tax_id' -> [('common', None), ('seller', None), ('tax_id', None)]
        'line_items[0].description' -> [('line_items', 0), ('description', None)]

    Raises:
        ValueError: If path is empty or contains malformed tokens.
    """
    if not path or not isinstance(path, str):
        raise ValueError("Field path must be a non-empty string.")

    tokens = path.strip().split(".")
    parsed = []

    for token in tokens:
        match = _PATH_TOKEN_REGEX.match(token)
        if not match:
            raise ValueError(f"Invalid field path token: '{token}' in path '{path}'.")

        key, idx_str = match.groups()
        idx = int(idx_str) if idx_str is not None else None
        if idx is not None and idx < 0:
            raise ValueError(f"Negative array index not allowed: '{token}' in path '{path}'.")

        parsed.append((key, idx))

    return parsed


def _get_attribute_or_item(target: Any, key: str) -> Any:
    """Retrieve attribute or dict key safely without arbitrary execution."""
    if isinstance(target, dict):
        if key in target:
            return target[key]
        elif "common" in target and isinstance(target["common"], dict) and key in target["common"]:
            return target["common"][key]
        raise KeyError(f"Key '{key}' not found in dict.")
    elif hasattr(target, key) and not key.startswith("_"):
        return getattr(target, key)
    elif hasattr(target, "common") and hasattr(target.common, key) and not key.startswith("_"):
        return getattr(target.common, key)
    elif hasattr(target, "model_dump"):
        # Fallback for Pydantic if attribute exists on model
        try:
            return getattr(target, key)
        except AttributeError:
            raise AttributeError(f"Attribute '{key}' not found on object {type(target).__name__}.")
    else:
        raise AttributeError(f"Attribute or key '{key}' not found on object of type {type(target).__name__}.")


def get_field_value(obj: Any, path: str) -> Any:
    """Get value from obj at the specified field path.

    Supports dot notation and non-negative array indexing.

    Args:
        obj: Pydantic model instance, dict, or list.
        path: Field path string (e.g. 'common.seller.tax_id', 'line_items[0].amount').

    Returns:
        The target value.

    Raises:
        ValueError: For malformed paths.
        KeyError / AttributeError / IndexError: If key, attribute, or array index is missing.
    """
    tokens = parse_field_path(path)
    current = obj

    for key, idx in tokens:
        current = _get_attribute_or_item(current, key)
        if idx is not None:
            if not isinstance(current, (list, tuple)):
                raise TypeError(f"Target at key '{key}' is not a list/sequence, got {type(current).__name__}.")
            if idx >= len(current):
                raise IndexError(f"Index {idx} out of range for sequence at '{key}' (len {len(current)}).")
            current = current[idx]

    return current


def set_field_value(obj: Any, path: str, value: Any) -> Any:
    """Set value on obj at the specified field path.

    If obj is a Pydantic model, updates attributes directly or returns a modified model/dict.

    Args:
        obj: Pydantic model instance or dict.
        path: Field path string (e.g. 'common.seller.tax_id', 'line_items[0].amount').
        value: New value to set.

    Returns:
        The mutated or updated obj.

    Raises:
        ValueError: For malformed paths.
        KeyError / AttributeError / IndexError: If path elements cannot be resolved.
    """
    tokens = parse_field_path(path)
    if not tokens:
        raise ValueError("Cannot set value on an empty path.")

    # Navigate to parent container of final token
    current = obj
    for i in range(len(tokens) - 1):
        key, idx = tokens[i]
        current = _get_attribute_or_item(current, key)
        if idx is not None:
            if not isinstance(current, (list, tuple)):
                raise TypeError(f"Target at key '{key}' is not a list, got {type(current).__name__}.")
            if idx >= len(current):
                raise IndexError(f"Index {idx} out of range for list at '{key}'.")
            current = current[idx]

    target_key, target_idx = tokens[-1]

    if target_idx is not None:
        sequence = _get_attribute_or_item(current, target_key)
        if not isinstance(sequence, list):
            raise TypeError(f"Target '{target_key}' is not a mutable list.")
        if target_idx >= len(sequence):
            raise IndexError(f"Index {target_idx} out of range for list at '{target_key}'.")
        
        # If target element is an object/dict/model, and value is a primitive value being set
        sequence[target_idx] = value
    else:
        if isinstance(current, dict):
            if target_key in current:
                current[target_key] = value
            elif "common" in current and isinstance(current["common"], dict) and target_key in current["common"]:
                current["common"][target_key] = value
            else:
                current[target_key] = value
        elif hasattr(current, target_key) and not target_key.startswith("_"):
            setattr(current, target_key, value)
        elif hasattr(current, "common") and hasattr(current.common, target_key) and not target_key.startswith("_"):
            setattr(current.common, target_key, value)
        else:
            raise AttributeError(f"Cannot set attribute '{target_key}' on object of type {type(current).__name__}.")

    return obj
