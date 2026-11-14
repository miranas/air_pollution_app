from typing import Any,Optional

def _to_float(value: Any) -> Optional[float]:
    """
    Convert value to float, return None on failure.

    Args:
        value: Any value (number, string, None).

    Returns:
        float or None: Converted value, or None if conversion fails.
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number
