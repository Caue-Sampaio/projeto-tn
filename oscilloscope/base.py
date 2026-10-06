from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class OscilloscopeReading:
    oscilloscope_id: str
    channel: int
    timestamp: datetime = field(default_factory=datetime.now)
    vpp_v: float | None = None
    vrms_v: float | None = None
    vmax_v: float | None = None
    vmin_v: float | None = None
    vavg_v: float | None = None
    frequency_hz: float | None = None
    period_s: float | None = None
    duty_cycle_pct: float | None = None
    vertical_offset_v: float | None = None
    raw: dict[str, str] = field(default_factory=dict)
    waveform: dict[str, Any] | None = None

    @staticmethod
    def _fmt(value: float | None, unit: str, digits: int = 4) -> str:
        if value is None:
            return "—"
        abs_v = abs(value)
        if unit == "Hz":
            if abs_v >= 1_000_000:
                return f"{value/1_000_000:.3f} MHz"
            if abs_v >= 1_000:
                return f"{value/1_000:.3f} kHz"
        if unit == "s":
            if 0 < abs_v < 1e-6:
                return f"{value*1e9:.3f} ns"
            if 0 < abs_v < 1e-3:
                return f"{value*1e6:.3f} µs"
            if 0 < abs_v < 1:
                return f"{value*1e3:.3f} ms"
        return f"{value:.{digits}g} {unit}".strip()

    @property
    def display_text(self) -> str:
        """Resumo compacto das três medições principais do ponto."""
        parts: list[str] = []
        if self.vpp_v is not None:
            parts.append(f"Vpp {self._fmt(self.vpp_v, 'V')}")
        if self.vrms_v is not None:
            parts.append(f"Vrms {self._fmt(self.vrms_v, 'V')}")
        if self.frequency_hz is not None:
            parts.append(f"F {self._fmt(self.frequency_hz, 'Hz')}")
        return " • ".join(parts) if parts else f"CH{self.channel} —"

    def to_dict(self) -> dict[str, Any]:
        return {
            "oscilloscope_id": self.oscilloscope_id,
            "channel": self.channel,
            "timestamp": self.timestamp.isoformat(),
            "vpp_v": self.vpp_v,
            "vrms_v": self.vrms_v,
            "vmax_v": self.vmax_v,
            "vmin_v": self.vmin_v,
            "vavg_v": self.vavg_v,
            "frequency_hz": self.frequency_hz,
            "period_s": self.period_s,
            "duty_cycle_pct": self.duty_cycle_pct,
            "vertical_offset_v": self.vertical_offset_v,
            "raw": self.raw,
            "waveform": self.waveform,
        }


class OscilloscopeBase(ABC):
    def __init__(self, config: dict[str, Any]):
        self.config = dict(config)

    @property
    @abstractmethod
    def identifier(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def read_snapshot(self, channel: int) -> OscilloscopeReading:
        raise NotImplementedError

    def read_live(self, channel: int) -> OscilloscopeReading:
        """Leitura leve para monitoramento contínuo."""
        return self.read_snapshot(channel)

    def capture_waveform(self, channel: int) -> dict[str, Any] | None:
        return None
