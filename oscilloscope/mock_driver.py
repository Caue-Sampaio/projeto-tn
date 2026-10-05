from __future__ import annotations

import math
import random
import time
from typing import Any

from .base import OscilloscopeBase, OscilloscopeReading


class MockOscilloscope(OscilloscopeBase):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._connected = False

    @property
    def identifier(self) -> str:
        return "RIGOL TECHNOLOGIES,MSO5074,MOCK,00.01"

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def read_snapshot(self, channel: int) -> OscilloscopeReading:
        if not self._connected:
            raise RuntimeError("Osciloscópio simulado não conectado")
        channel = int(channel)
        base_vpp = 5.0 + channel * 0.02
        vpp = base_vpp + random.uniform(-0.035, 0.035)
        freq = 1000.0 + random.uniform(-2.0, 2.0)
        vmax = vpp / 2 + random.uniform(-0.01, 0.01)
        vmin = -vpp / 2 + random.uniform(-0.01, 0.01)
        return OscilloscopeReading(
            oscilloscope_id=self.identifier,
            channel=channel,
            vpp_v=vpp,
            vrms_v=vpp / (2 * math.sqrt(2)),
            vmax_v=vmax,
            vmin_v=vmin,
            vavg_v=(vmax + vmin) / 2,
            frequency_hz=freq,
            period_s=1.0 / freq,
            duty_cycle_pct=50.0 + random.uniform(-0.4, 0.4),
            vertical_offset_v=0.0,
            raw={"source": "mock"},
        )

    def capture_waveform(self, channel: int):
        points = max(100, min(int(self.config.get("waveform_points", 1200)), 12000))
        freq = 1000.0
        dt = 1.0 / (freq * max(points // 4, 1))
        x = [i * dt for i in range(points)]
        y = [2.5 * math.sin(2 * math.pi * freq * t) for t in x]
        return {"x_s": x, "y_v": y, "points": points, "preamble": "mock"}
