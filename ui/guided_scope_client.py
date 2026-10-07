from __future__ import annotations

import queue
from typing import Any

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from oscilloscope.data_reader import DataReader
from ui.oscilloscope_panel import load_config_document


class GuidedScopeClient(QObject):
    """Cliente compacto do Rigol para o diagnóstico guiado.

    Usa a mesma DataReader em thread já usada pelo scanner, mas não desenha a
    forma de onda no Teste Geral. A aquisição contínua permanece pausada e cada
    etapa pede apenas um snapshot, evitando contaminar o ponto seguinte.
    """

    status_changed = pyqtSignal(str, bool, bool)  # texto, conectado, simulado
    snapshot_ready = pyqtSignal(object, object)   # reading, context
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        document = load_config_document()
        self.config: dict[str, Any] = dict(document.get("last_config") or {})
        self.reader: DataReader | None = None
        self.queue: queue.Queue = queue.Queue(maxsize=8)
        self.connected = False
        self.simulated = False
        self.channel = int(self.config.get("channel") or 1)

        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._drain)
        self.timer.start()

    @property
    def resource(self) -> str:
        return str(self.config.get("resource") or "ASRL4::INSTR")

    def connect_scope(self, resource: str | None = None) -> None:
        self.disconnect_scope()
        if resource:
            self.config["resource"] = resource.strip()
        resource_text = self.resource.upper()
        self.config["backend"] = "mock" if resource_text.startswith("MOCK") else "visa"
        self.config["channel"] = self.channel

        self.reader = DataReader(
            self.config,
            self.queue,
            active_channels=(self.channel,),
            target_reader_hz=float(self.config.get("reader_hz") or 8.0),
        )
        # O diagnóstico guiado trabalha por snapshots. Mantemos o streaming
        # pausado desde o início para a troca física da ponta ser segura.
        self.reader.pause(True)
        self.reader.start()
        self.status_changed.emit("Conectando…", False, False)

    def disconnect_scope(self) -> None:
        if self.reader is not None:
            try:
                self.reader.stop()
            except Exception:
                pass
        self.reader = None
        self.connected = False
        self.simulated = False
        self.status_changed.emit("Desconectado", False, False)

    def set_channel(self, channel: int) -> None:
        self.channel = max(1, min(int(channel or 1), 4))
        self.config["channel"] = self.channel
        if self.reader is not None and self.reader.is_alive():
            self.reader.set_channels((self.channel,))

    def capture(self, context: Any = None) -> bool:
        if self.reader is None or not self.reader.is_alive() or not self.connected:
            self.error.emit("Osciloscópio desconectado")
            return False
        self.reader.request_snapshot(self.channel, context)
        return True

    def _drain(self) -> None:
        while True:
            try:
                event = self.queue.get_nowait()
            except queue.Empty:
                break

            kind = event.get("type")
            if kind == "snapshot":
                self.snapshot_ready.emit(event.get("reading"), event.get("context"))
            elif kind == "status":
                self.connected = bool(event.get("connected"))
                self.simulated = bool(event.get("simulated"))
                text = str(event.get("status") or ("Conectado" if self.connected else "Desconectado"))
                self.status_changed.emit(text, self.connected, self.simulated)
            elif kind == "error":
                self.error.emit(str(event.get("message") or "Erro de comunicação"))

    def shutdown(self) -> None:
        self.timer.stop()
        self.disconnect_scope()
