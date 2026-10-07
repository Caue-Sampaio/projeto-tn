from __future__ import annotations

import json
from typing import Any

import numpy as np


METRICS = (
    ("vpp", "Vpp", "vpp_v", "tolerance_vpp_pct", "V"),
    ("vrms", "Vrms", "vrms_v", "tolerance_vrms_pct", "V"),
    ("frequency", "Freq.", "frequency_hz", "tolerance_frequency_pct", "Hz"),
)


def _float(value):
    try:
        if value is None:
            return None
        value = float(value)
        return value if np.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def format_value(value: float | None, unit: str) -> str:
    value = _float(value)
    if value is None:
        return "—"
    if unit == "Hz":
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:.3g} MHz"
        if abs(value) >= 1_000:
            return f"{value / 1_000:.3g} kHz"
        return f"{value:.4g} Hz"
    if unit == "V":
        if 0 < abs(value) < 1:
            return f"{value * 1000:.3g} mV"
        return f"{value:.4g} V"
    return f"{value:.4g} {unit}".strip()


def _parse_waveform_json(raw) -> dict[str, Any] | None:
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _waveform_arrays(waveform) -> tuple[np.ndarray, np.ndarray] | None:
    if not isinstance(waveform, dict):
        return None
    try:
        x = np.asarray(waveform.get("x_s") or [], dtype=float)
        y = np.asarray(waveform.get("y_v") or [], dtype=float)
    except Exception:
        return None
    n = min(x.size, y.size)
    if n < 16:
        return None
    x = x[:n]
    y = y[:n]
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if x.size < 16:
        return None
    x = x - x[0]
    return x, y


def waveform_similarity(reference_waveform, measured_waveform) -> float | None:
    """Correlação normalizada da forma, compensando fase/trigger.

    Amplitude e offset são normalizados porque Vpp/Vrms são comparados
    separadamente. O índice serve para enxergar deformação, duty e ruído.
    """
    reference = _waveform_arrays(reference_waveform)
    measured = _waveform_arrays(measured_waveform)
    if reference is None or measured is None:
        return None

    rx, ry = reference
    mx, my = measured
    n = int(min(400, rx.size, mx.size))
    if n < 16:
        return None

    def normalize(x, y):
        span = float(x[-1] - x[0])
        if not np.isfinite(span) or span <= 0:
            return None
        xn = (x - x[0]) / span
        target = np.linspace(0.0, 1.0, n)
        out = np.interp(target, xn, y)
        out = out - float(np.mean(out))
        std = float(np.std(out))
        if not np.isfinite(std) or std < 1e-12:
            return None
        return out / std

    a = normalize(rx, ry)
    b = normalize(mx, my)
    if a is None or b is None:
        return None

    corr = np.correlate(np.r_[b, b], a, mode="valid") / float(n)
    if corr.size == 0:
        return None
    return max(0.0, min(100.0, float(np.max(corr)) * 100.0))


def reference_summary(reference) -> str:
    if reference is None:
        return "Sem referência"
    parts: list[str] = []
    if _float(getattr(reference, "vpp_v", None)) is not None:
        parts.append(f"Vpp {format_value(reference.vpp_v, 'V')}")
    if _float(getattr(reference, "vrms_v", None)) is not None:
        parts.append(f"Vrms {format_value(reference.vrms_v, 'V')}")
    if _float(getattr(reference, "frequency_hz", None)) is not None:
        parts.append(f"F {format_value(reference.frequency_hz, 'Hz')}")
    return " • ".join(parts) if parts else "Referência sem valores numéricos"


def reading_summary(reading) -> str:
    if reading is None:
        return "—"
    parts: list[str] = []
    if _float(getattr(reading, "vpp_v", None)) is not None:
        parts.append(f"Vpp {format_value(reading.vpp_v, 'V')}")
    if _float(getattr(reading, "vrms_v", None)) is not None:
        parts.append(f"Vrms {format_value(reading.vrms_v, 'V')}")
    if _float(getattr(reading, "frequency_hz", None)) is not None:
        parts.append(f"F {format_value(reading.frequency_hz, 'Hz')}")
    return " • ".join(parts) if parts else "—"


def compare_scope_reading(reference, reading) -> dict[str, Any]:
    """Compara uma captura do Rigol com a referência do ponto.

    Status possíveis: OK, LIMITE, FALHA, SEM REF., SEM LEITURA.
    LIMITE significa >=80% da tolerância, ainda sem ultrapassá-la.
    """
    if reference is None:
        return {
            "status": "SEM REF.",
            "passed": None,
            "expected_summary": "Sem referência",
            "measured_summary": reading_summary(reading),
            "metrics": {},
            "waveform_similarity_pct": None,
            "primary_value": None,
            "primary_expected": None,
            "primary_tolerance_pct": None,
            "primary_unit": "",
        }

    if reading is None:
        return {
            "status": "SEM LEITURA",
            "passed": False,
            "expected_summary": reference_summary(reference),
            "measured_summary": "—",
            "metrics": {},
            "waveform_similarity_pct": None,
            "primary_value": None,
            "primary_expected": None,
            "primary_tolerance_pct": None,
            "primary_unit": "",
        }

    metrics: dict[str, Any] = {}
    statuses: list[str] = []
    primary = None

    for key, label, attr, tol_attr, unit in METRICS:
        expected = _float(getattr(reference, attr, None))
        if expected is None:
            continue
        measured = _float(getattr(reading, attr, None))
        tolerance_pct = _float(getattr(reference, tol_attr, None))
        if tolerance_pct is None:
            tolerance_pct = 0.0

        if measured is None:
            status = "FALHA"
            deviation_abs = None
            deviation_pct = None
            utilization_pct = None
        else:
            deviation_abs = measured - expected
            if abs(expected) > 1e-12:
                deviation_pct = deviation_abs / abs(expected) * 100.0
                error_pct = abs(deviation_pct)
            else:
                deviation_pct = None
                error_pct = 0.0 if abs(measured) <= 1e-12 else float("inf")

            if tolerance_pct <= 0:
                status = "OK" if error_pct == 0 else "FALHA"
                utilization_pct = 0.0 if error_pct == 0 else float("inf")
            else:
                utilization_pct = error_pct / tolerance_pct * 100.0
                if error_pct > tolerance_pct:
                    status = "FALHA"
                elif error_pct >= 0.8 * tolerance_pct:
                    status = "LIMITE"
                else:
                    status = "OK"

        metrics[key] = {
            "label": label,
            "unit": unit,
            "expected": expected,
            "measured": measured,
            "deviation_abs": deviation_abs,
            "deviation_pct": deviation_pct,
            "tolerance_pct": tolerance_pct,
            "utilization_pct": utilization_pct,
            "status": status,
            "expected_text": format_value(expected, unit),
            "measured_text": format_value(measured, unit),
        }
        statuses.append(status)
        if primary is None:
            primary = metrics[key]

    if not metrics:
        overall = "SEM REF."
        passed = None
    elif "FALHA" in statuses:
        overall = "FALHA"
        passed = False
    elif "LIMITE" in statuses:
        overall = "LIMITE"
        passed = True
    else:
        overall = "OK"
        passed = True

    ref_wave = _parse_waveform_json(getattr(reference, "waveform_json", None))
    measured_wave = getattr(reading, "waveform", None)
    similarity = waveform_similarity(ref_wave, measured_wave)

    return {
        "status": overall,
        "passed": passed,
        "expected_summary": reference_summary(reference),
        "measured_summary": reading_summary(reading),
        "metrics": metrics,
        "waveform_similarity_pct": similarity,
        "primary_value": None if primary is None else primary["measured"],
        "primary_expected": None if primary is None else primary["expected"],
        "primary_tolerance_pct": None if primary is None else primary["tolerance_pct"],
        "primary_unit": "" if primary is None else primary["unit"],
    }


def serialize_guided_result(result: dict[str, Any], *, channel: int | None = None) -> str:
    payload = {
        "kind": "guided_scope_v1",
        "channel": channel,
        "status": result.get("status"),
        "expected_summary": result.get("expected_summary"),
        "measured_summary": result.get("measured_summary"),
        "metrics": result.get("metrics") or {},
        "waveform_similarity_pct": result.get("waveform_similarity_pct"),
    }
    return json.dumps(payload, ensure_ascii=False)


def parse_guided_notes(notes: str | None) -> dict[str, Any] | None:
    if not notes:
        return None
    try:
        data = json.loads(notes)
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("kind") != "guided_scope_v1":
        return None
    return data
