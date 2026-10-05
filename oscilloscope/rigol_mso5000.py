from __future__ import annotations

import logging
from typing import Any

from .base import OscilloscopeBase, OscilloscopeReading
from .parser import parse_scpi_number

logger = logging.getLogger(__name__)


class RigolMSO5000(OscilloscopeBase):
    """Driver VISA/SCPI para a família Rigol MSO5000, incluindo MSO5074.

    As consultas de medição usam o conjunto SCPI da família MSO5000.
    Leituras individuais que não estiverem disponíveis no estado atual do
    osciloscópio são retornadas como None, sem abortar a captura inteira.
    """

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._rm = None
        self._inst = None
        self._identifier = "Rigol MSO5074"

    @property
    def identifier(self) -> str:
        return self._identifier

    def connect(self) -> None:
        try:
            import pyvisa
        except ImportError as exc:
            raise RuntimeError("PyVISA não está instalado. Execute: pip install pyvisa pyvisa-py") from exc

        backend = str(self.config.get("visa_backend") or "").strip()
        self._rm = pyvisa.ResourceManager(backend) if backend else pyvisa.ResourceManager()
        resource = str(self.config.get("resource") or "").strip()
        if not resource:
            raise RuntimeError("Selecione ou informe um recurso VISA do osciloscópio")

        self._inst = self._rm.open_resource(resource)
        self._inst.timeout = int(self.config.get("timeout_ms", 1800))
        self._inst.read_termination = str(self.config.get("read_termination", "\n"))
        self._inst.write_termination = str(self.config.get("write_termination", "\n"))

        try:
            idn = str(self._inst.query("*IDN?")).strip()
            if idn:
                self._identifier = idn
        except Exception:
            logger.warning("Conectado ao VISA, mas *IDN? falhou", exc_info=True)

    def disconnect(self) -> None:
        try:
            if self._inst is not None:
                self._inst.close()
        finally:
            self._inst = None
            if self._rm is not None:
                try:
                    self._rm.close()
                except Exception:
                    pass
                self._rm = None

    def _query_raw(self, command: str) -> str:
        if self._inst is None:
            raise RuntimeError("Osciloscópio não conectado")
        return str(self._inst.query(command)).strip()

    def _query_number(self, command: str) -> tuple[float | None, str]:
        try:
            raw = self._query_raw(command)
            return parse_scpi_number(raw), raw
        except Exception as exc:
            logger.debug("Consulta SCPI falhou: %s (%s)", command, exc)
            return None, ""

    def read_snapshot(self, channel: int) -> OscilloscopeReading:
        channel = int(channel)
        if channel not in (1, 2, 3, 4):
            raise ValueError("Canal deve ser CH1, CH2, CH3 ou CH4")
        if self._inst is None:
            raise RuntimeError("Osciloscópio não conectado")

        source = f"CHANnel{channel}"
        commands = {
            "vpp_v": f":MEASure:ITEM? VPP,{source}",
            "vrms_v": f":MEASure:ITEM? VRMS,{source}",
            "vmax_v": f":MEASure:ITEM? VMAX,{source}",
            "vmin_v": f":MEASure:ITEM? VMIN,{source}",
            "vavg_v": f":MEASure:ITEM? VAVG,{source}",
            "frequency_hz": f":MEASure:ITEM? FREQ,{source}",
            "period_s": f":MEASure:ITEM? PER,{source}",
            "duty_cycle_pct": f":MEASure:ITEM? PDUT,{source}",
        }

        values: dict[str, float | None] = {}
        raw: dict[str, str] = {}
        for key, command in commands.items():
            value, text = self._query_number(command)
            values[key] = value
            raw[key] = text

        offset, offset_raw = self._query_number(f":CHANnel{channel}:OFFSet?")
        values["vertical_offset_v"] = offset
        raw["vertical_offset_v"] = offset_raw

        reading = OscilloscopeReading(
            oscilloscope_id=self.identifier,
            channel=channel,
            raw=raw,
            **values,
        )

        if bool(self.config.get("capture_waveform", False)):
            try:
                reading.waveform = self.capture_waveform(channel)
            except Exception:
                logger.exception("Falha ao capturar forma de onda; métricas foram preservadas")

        return reading


    def read_live(self, channel: int) -> OscilloscopeReading:
        """Leitura mais leve para o display contínuo (4 consultas SCPI)."""
        channel = int(channel)
        if channel not in (1, 2, 3, 4):
            raise ValueError("Canal deve ser CH1, CH2, CH3 ou CH4")
        if self._inst is None:
            raise RuntimeError("Osciloscópio não conectado")
        source = f"CHANnel{channel}"
        specs = {
            "vpp_v": f":MEASure:ITEM? VPP,{source}",
            "vrms_v": f":MEASure:ITEM? VRMS,{source}",
            "frequency_hz": f":MEASure:ITEM? FREQ,{source}",
            "duty_cycle_pct": f":MEASure:ITEM? PDUT,{source}",
        }
        values = {}
        raw = {}
        for key, command in specs.items():
            value, text = self._query_number(command)
            values[key] = value
            raw[key] = text
        return OscilloscopeReading(
            oscilloscope_id=self.identifier,
            channel=channel,
            raw=raw,
            **values,
        )

    def capture_waveform(self, channel: int) -> dict[str, Any] | None:
        """Captura uma curva reduzida usando o subsistema :WAVeform.

        O padrão é limitado a 1200 pontos para não sobrecarregar SQLite/UI.
        """
        if self._inst is None:
            raise RuntimeError("Osciloscópio não conectado")
        channel = int(channel)
        points = max(100, min(int(self.config.get("waveform_points", 1200)), 12000))

        self._inst.write(f":WAVeform:SOURce CHANnel{channel}")
        self._inst.write(":WAVeform:MODE NORMal")
        self._inst.write(":WAVeform:FORMat BYTE")
        try:
            self._inst.write(f":WAVeform:POINts {points}")
        except Exception:
            pass

        preamble = self._query_raw(":WAVeform:PREamble?")
        parts = [p.strip() for p in preamble.split(",")]
        if len(parts) < 10:
            raise RuntimeError(f"Preamble de waveform inválido: {preamble}")

        x_inc = float(parts[4])
        x_org = float(parts[5])
        x_ref = float(parts[6])
        y_inc = float(parts[7])
        y_org = float(parts[8])
        y_ref = float(parts[9])

        data = self._inst.query_binary_values(
            ":WAVeform:DATA?",
            datatype="B",
            container=list,
            expect_termination=True,
        )
        if points and len(data) > points:
            data = data[:points]

        x_values = [((i - x_ref) * x_inc) + x_org for i in range(len(data))]
        y_values = [((float(sample) - y_org - y_ref) * y_inc) for sample in data]
        return {
            "x_s": x_values,
            "y_v": y_values,
            "points": len(data),
            "preamble": preamble,
        }
