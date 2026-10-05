from __future__ import annotations

import math
import re

_INVALID = {"", "OL", "OVER", "OVLD", "NAN", "INF", "+INF", "-INF", "----", "*****"}
_NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")


def parse_scpi_number(response: str | bytes | None) -> float | None:
    if response is None:
        return None
    if isinstance(response, bytes):
        response = response.decode("ascii", errors="ignore")
    text = str(response).strip().strip('"').upper()
    if text in _INVALID:
        return None
    match = _NUMBER_RE.search(text)
    if not match:
        return None
    try:
        value = float(match.group(0))
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    # Rigol e muitos instrumentos SCPI retornam valores enormes quando a
    # medição não é válida/estável.
    if abs(value) >= 9.0e36:
        return None
    return value
