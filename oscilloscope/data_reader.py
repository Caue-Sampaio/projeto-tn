from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from oscilloscope.factory import create_driver


@dataclass(slots=True)
class ScopeFrame:
    """Pacote de dados entregue pela thread para a GUI."""

    timestamp: float
    status: str
    identifier: str
    waveforms: dict[int, tuple[np.ndarray, np.ndarray]]
    readings: dict[int, Any]


class DataReader(threading.Thread):
    """Aquisição do osciloscópio fora da thread da interface.

    A GUI e o driver nunca compartilham chamadas VISA. Isso evita travamentos e
    é especialmente importante quando o recurso é ``ASRL4::INSTR``.
    """

    def __init__(
        self,
        config: dict[str, Any],
        output_queue: queue.Queue,
        *,
        active_channels: Iterable[int] = (1,),
        target_reader_hz: float = 12.0,
    ) -> None:
        super().__init__(name="ScopeDataReader", daemon=True)
        self.config = dict(config)
        self.output_queue = output_queue
        self.target_reader_hz = max(1.0, float(target_reader_hz))

        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._control_lock = threading.Lock()
        self._channels = {int(ch) for ch in active_channels if 1 <= int(ch) <= 4} or {1}
        self._capture_requests: queue.Queue[tuple[int, Any]] = queue.Queue()

        self._driver = None
        self._last_metrics: dict[int, Any] = {}
        self._identifier = "Osciloscópio"

        # Parâmetros do simulador. Ele entrega um quadro novo a cada iteração,
        # em vez de um buffer crescente, imitando a varredura de um scope real.
        self._sim_t0 = time.perf_counter()
        self._sim_sample_rate = float(self.config.get("sim_sample_rate", 50_000.0))
        self._sim_points = int(self.config.get("sim_points", 1200))
        self._sim_frequency = float(self.config.get("sim_frequency_hz", 1_000.0))
        self._sim_noise = float(self.config.get("sim_noise_v", 0.03))
        self._rng = np.random.default_rng()

    # ----------------------------------------------------------- thread-safe API
    def stop(self) -> None:
        self._stop_event.set()

    def pause(self, paused: bool = True) -> None:
        if paused:
            self._pause_event.set()
        else:
            self._pause_event.clear()

    def set_channels(self, channels: Iterable[int]) -> None:
        selected = {int(ch) for ch in channels if 1 <= int(ch) <= 4}
        with self._control_lock:
            self._channels = selected or {1}

    def request_snapshot(self, channel: int, context: Any = None) -> None:
        self._capture_requests.put((max(1, min(int(channel), 4)), context))

    # ---------------------------------------------------------------- queue
    def _put_latest(self, item: dict[str, Any]) -> None:
        try:
            self.output_queue.put_nowait(item)
            return
        except queue.Full:
            pass
        try:
            self.output_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            self.output_queue.put_nowait(item)
        except queue.Full:
            pass

    def _is_simulation(self) -> bool:
        resource = str(self.config.get("resource") or "").upper()
        return str(self.config.get("backend") or "").lower() == "mock" or resource.startswith("MOCK")

    # -------------------------------------------------------------- simulation
    def _simulation_frame(self, channel: int) -> tuple[np.ndarray, np.ndarray]:
        n = max(200, self._sim_points)
        fs = max(1_000.0, self._sim_sample_rate)
        x = np.arange(n, dtype=float) / fs
        elapsed = time.perf_counter() - self._sim_t0
        f = self._sim_frequency * (1.0 + 0.25 * (channel - 1))
        amp = 2.4 - 0.25 * (channel - 1)
        phase_t = x + elapsed

        if channel == 1:
            y = amp * np.sin(2.0 * np.pi * f * phase_t)
        elif channel == 2:
            y = amp * np.sign(np.sin(2.0 * np.pi * f * phase_t))
        elif channel == 3:
            phase = (phase_t * f) % 1.0
            y = amp * (4.0 * np.abs(phase - 0.5) - 1.0)
        else:
            y = amp * np.sin(2.0 * np.pi * f * phase_t + 0.7)

        y += self._rng.normal(0.0, self._sim_noise, size=n)
        return x, y

    @staticmethod
    def _estimate_metrics(x: np.ndarray, y: np.ndarray) -> dict[str, float | None]:
        if y.size < 3:
            return {"vpp": None, "vrms": None, "freq": None}
        vpp = float(np.max(y) - np.min(y))
        vrms = float(np.sqrt(np.mean(np.square(y))))
        freq = None
        centered = y - float(np.mean(y))
        crossings = np.where((centered[:-1] <= 0) & (centered[1:] > 0))[0]
        if crossings.size >= 2 and x.size == y.size:
            periods = np.diff(x[crossings])
            periods = periods[periods > 0]
            if periods.size:
                freq = float(1.0 / np.median(periods))
        return {"vpp": vpp, "vrms": vrms, "freq": freq}

    # --------------------------------------------------------------- hardware
    def _read_real_waveform(self, channel: int) -> tuple[np.ndarray, np.ndarray] | None:
        wf = self._driver.capture_waveform(channel)
        if not wf:
            return None
        x = np.asarray(wf.get("x_s") or [], dtype=float)
        y = np.asarray(wf.get("y_v") or [], dtype=float)
        size = min(x.size, y.size)
        if size <= 1:
            return None
        return x[:size], y[:size]

    def _handle_snapshot_requests(self) -> None:
        while True:
            try:
                channel, context = self._capture_requests.get_nowait()
            except queue.Empty:
                break
            try:
                reading = self._driver.read_snapshot(channel)
                try:
                    reading.waveform = self._driver.capture_waveform(channel)
                except Exception:
                    pass
                self._put_latest({"type": "snapshot", "reading": reading, "context": context})
            except Exception as exc:
                self._put_latest({"type": "error", "message": str(exc)})

    # -------------------------------------------------------------------- run
    def run(self) -> None:
        try:
            self._driver = create_driver(self.config)
            self._driver.connect()
            self._identifier = getattr(self._driver, "identifier", "Osciloscópio")
            simulated = self._is_simulation()
            self._put_latest({
                "type": "status",
                "connected": True,
                "simulated": simulated,
                "status": "Simulando" if simulated else "Conectado",
                "identifier": self._identifier,
            })

            metrics_deadline = 0.0
            interval = 1.0 / self.target_reader_hz

            while not self._stop_event.is_set():
                loop_start = time.perf_counter()
                self._handle_snapshot_requests()

                if self._pause_event.is_set():
                    time.sleep(0.02)
                    continue

                with self._control_lock:
                    channels = sorted(self._channels)

                waveforms: dict[int, tuple[np.ndarray, np.ndarray]] = {}
                readings: dict[int, Any] = {}
                now = time.monotonic()

                for ch in channels:
                    if simulated:
                        x, y = self._simulation_frame(ch)
                    else:
                        got = self._read_real_waveform(ch)
                        if got is None:
                            continue
                        x, y = got
                    waveforms[ch] = (x, y)

                # Consultas de métricas SCPI são mais lentas que a curva. No
                # hardware elas são atualizadas a 2 Hz; a onda continua fluida.
                if now >= metrics_deadline:
                    for ch in channels:
                        if simulated:
                            x, y = waveforms.get(ch, (np.array([]), np.array([])))
                            metrics = self._estimate_metrics(x, y)
                            readings[ch] = metrics
                            self._last_metrics[ch] = metrics
                        else:
                            try:
                                reading = self._driver.read_live(ch)
                                readings[ch] = reading
                                self._last_metrics[ch] = reading
                            except Exception:
                                if ch in self._last_metrics:
                                    readings[ch] = self._last_metrics[ch]
                    metrics_deadline = now + 0.5
                else:
                    readings = dict(self._last_metrics)

                self._put_latest({
                    "type": "frame",
                    "frame": ScopeFrame(
                        timestamp=time.time(),
                        status="Simulando" if simulated else "Conectado",
                        identifier=self._identifier,
                        waveforms=waveforms,
                        readings=readings,
                    ),
                })

                elapsed = time.perf_counter() - loop_start
                if elapsed < interval:
                    time.sleep(interval - elapsed)

        except Exception as exc:
            self._put_latest({"type": "error", "message": str(exc)})
            self._put_latest({
                "type": "status", "connected": False, "simulated": False,
                "status": "Desconectado", "identifier": "",
            })
        finally:
            try:
                if self._driver is not None:
                    self._driver.disconnect()
            except Exception:
                pass
            self._put_latest({
                "type": "status", "connected": False, "simulated": False,
                "status": "Desconectado", "identifier": "",
            })
