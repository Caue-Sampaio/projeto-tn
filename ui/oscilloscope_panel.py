from __future__ import annotations

import copy
import json
import logging
import queue
import time
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSizePolicy,
    QVBoxLayout,
)

from oscilloscope.base import OscilloscopeReading
from oscilloscope.data_reader import DataReader
from oscilloscope.factory import list_visa_resources
from ui.oscilloscope_display import OscilloscopeDisplay

logger = logging.getLogger(__name__)
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "oscilloscope.json"


def _default_document() -> dict[str, Any]:
    return {
        "presets": {
            "Rigol MSO5074 - ASRL4": {
                "backend": "visa",
                "model": "Rigol MSO5074",
                "resource": "ASRL4::INSTR",
                "timeout_ms": 2500,
                "reader_hz": 12,
                "capture_waveform": True,
                "waveform_points": 1200,
            },
            "Rigol MSO5074 - USB/LAN": {
                "backend": "visa",
                "model": "Rigol MSO5074",
                "timeout_ms": 1800,
                "reader_hz": 15,
                "capture_waveform": True,
                "waveform_points": 1200,
            },
            "Simulador MSO5074": {
                "backend": "mock",
                "model": "Rigol MSO5074 (Simulado)",
                "resource": "MOCK::MSO5074",
                "timeout_ms": 1000,
                "reader_hz": 30,
                "capture_waveform": True,
                "waveform_points": 1200,
            },
        },
        "last_config": {
            "preset": "Rigol MSO5074 - ASRL4",
            "backend": "visa",
            "model": "Rigol MSO5074",
            "resource": "ASRL4::INSTR",
            "channel": 1,
            "timeout_ms": 2500,
            "reader_hz": 12,
            "read_termination": "\n",
            "write_termination": "\n",
            "visa_backend": "",
            "auto_reconnect": False,
            "capture_waveform": True,
            "waveform_points": 1200,
            "baud_rate": 0,
        },
    }


def load_config_document() -> dict[str, Any]:
    data = _default_document()
    try:
        if CONFIG_PATH.exists():
            with CONFIG_PATH.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                data["presets"].update(loaded.get("presets") or {})
                data["last_config"].update(loaded.get("last_config") or {})
    except Exception:
        logger.exception("Falha ao carregar configuração do osciloscópio")
    return data


def save_config_document(document: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
    tmp.replace(CONFIG_PATH)


class OscilloscopeSettingsDialog(QDialog):
    def __init__(self, document: dict[str, Any], config: dict[str, Any], theme, parent=None):
        super().__init__(parent)
        self.document = copy.deepcopy(document)
        self.config = dict(config)
        self.theme = theme
        self.setWindowTitle("Configuração do osciloscópio")
        self.setMinimumWidth(520)
        self._build_ui()
        self._apply_style()
        self._load(self.config)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        title = QLabel("RIGOL MSO5074")
        title.setObjectName("scopeDialogTitle")
        subtitle = QLabel("Conexão VISA e atualização da mini tela digital")
        subtitle.setObjectName("scopeMuted")
        root.addWidget(title)
        root.addWidget(subtitle)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)

        self.preset = QComboBox()
        self.preset.addItems(sorted(self.document.get("presets", {}).keys()))
        self.preset.currentTextChanged.connect(self._apply_preset)
        form.addRow("Preset", self.preset)

        self.backend = QComboBox()
        self.backend.addItem("VISA / SCPI", "visa")
        self.backend.addItem("Simulador", "mock")
        form.addRow("Backend", self.backend)

        self.model = QLineEdit()
        form.addRow("Modelo", self.model)

        self.visa_backend = QLineEdit()
        self.visa_backend.setPlaceholderText("Vazio = padrão; @py = pyvisa-py")
        form.addRow("Backend VISA", self.visa_backend)

        self.timeout = QSpinBox()
        self.timeout.setRange(200, 30000)
        self.timeout.setSuffix(" ms")
        form.addRow("Timeout", self.timeout)

        self.reader_hz = QSpinBox()
        self.reader_hz.setRange(1, 60)
        self.reader_hz.setSuffix(" Hz")
        form.addRow("Aquisição alvo", self.reader_hz)

        self.waveform_points = QSpinBox()
        self.waveform_points.setRange(200, 12000)
        self.waveform_points.setSingleStep(100)
        self.waveform_points.setSuffix(" pontos")
        form.addRow("Pontos da curva", self.waveform_points)

        self.baud_rate = QSpinBox()
        self.baud_rate.setRange(0, 2_000_000)
        self.baud_rate.setSpecialValueText("Padrão VISA")
        self.baud_rate.setSingleStep(9600)
        form.addRow("Baudrate ASRL", self.baud_rate)

        self.auto_reconnect = QCheckBox("Tentar reconectar automaticamente")
        form.addRow("", self.auto_reconnect)

        hint = QLabel(
            "Recurso atual do computador: ASRL4::INSTR. Para testar sem hardware, "
            "selecione o preset Simulador MSO5074."
        )
        hint.setObjectName("scopeMuted")
        hint.setWordWrap(True)

        root.addLayout(form)
        root.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _apply_style(self) -> None:
        t = self.theme
        self.setStyleSheet(
            f"""
            QDialog {{ background: {t.BG_PRIMARY}; color: {t.TEXT_PRIMARY}; }}
            QLabel#scopeDialogTitle {{ color: {t.ACCENT_CYAN}; font-size: 16px; font-weight: 800; }}
            QLabel#scopeMuted {{ color: {t.TEXT_MUTED}; font-size: 10px; }}
            QLineEdit, QComboBox, QSpinBox {{
                background: {t.BG_INPUT}; color: {t.TEXT_PRIMARY};
                border: 1px solid {t.BORDER_SUBTLE}; border-radius: 5px; padding: 6px 8px;
            }}
            QCheckBox {{ color: {t.TEXT_SECONDARY}; }}
            QPushButton {{
                background: {t.BG_SURFACE_ALT}; color: {t.TEXT_PRIMARY};
                border: 1px solid {t.BORDER_SUBTLE}; border-radius: 5px;
                padding: 7px 14px; font-weight: 600;
            }}
            QPushButton:hover {{ border-color: {t.ACCENT_BLUE}; }}
            """
        )

    @staticmethod
    def _set_data(combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _load(self, cfg: dict[str, Any]) -> None:
        idx = self.preset.findText(str(cfg.get("preset") or ""))
        if idx >= 0:
            self.preset.blockSignals(True)
            self.preset.setCurrentIndex(idx)
            self.preset.blockSignals(False)
        self._set_data(self.backend, str(cfg.get("backend") or "visa"))
        self.model.setText(str(cfg.get("model") or "Rigol MSO5074"))
        self.visa_backend.setText(str(cfg.get("visa_backend") or ""))
        self.timeout.setValue(int(cfg.get("timeout_ms", 2500)))
        self.reader_hz.setValue(int(cfg.get("reader_hz", 12)))
        self.waveform_points.setValue(int(cfg.get("waveform_points", 1200)))
        self.baud_rate.setValue(int(cfg.get("baud_rate", 0) or 0))
        self.auto_reconnect.setChecked(bool(cfg.get("auto_reconnect", False)))

    def _apply_preset(self, name: str) -> None:
        preset = self.document.get("presets", {}).get(name)
        if not preset:
            return
        merged = dict(self.config)
        merged.update(preset)
        merged["preset"] = name
        self.config = merged
        self._load(merged)

    def result_config(self) -> dict[str, Any]:
        return {
            **self.config,
            "preset": self.preset.currentText(),
            "backend": str(self.backend.currentData()),
            "model": self.model.text().strip() or "Rigol MSO5074",
            "visa_backend": self.visa_backend.text().strip(),
            "timeout_ms": self.timeout.value(),
            "reader_hz": self.reader_hz.value(),
            "waveform_points": self.waveform_points.value(),
            "baud_rate": self.baud_rate.value(),
            "auto_reconnect": self.auto_reconnect.isChecked(),
            "capture_waveform": True,
            "read_termination": self.config.get("read_termination", "\n"),
            "write_termination": self.config.get("write_termination", "\n"),
        }


class OscilloscopePanel(QFrame):
    """Painel de integração do scanner com a mini tela do Rigol MSO5074.

    A posição deste widget no ``ImageMarker`` não mudou. Internamente, a antiga
    área de QLabel + métricas foi substituída pelo ``OscilloscopeDisplay``.
    """

    capture_requested = pyqtSignal(int, object)
    # Emitido no máximo a ~10 Hz com a leitura do canal ativo.
    # A tela de mapeamento usa esse sinal para comparar em tempo real
    # sem salvar uma captura no banco a cada atualização.
    live_reading_changed = pyqtSignal(object)
    status_changed = pyqtSignal(str, str)

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.document = load_config_document()
        self.config = dict(self.document.get("last_config") or {})

        self.reader: DataReader | None = None
        self.reader_queue: queue.Queue = queue.Queue(maxsize=4)
        self.latest_reading: OscilloscopeReading | None = None
        self.selected_point_id: int | None = None
        self.selected_point_name = ""
        self._connected = False
        self._simulated = False
        self._expanded = True
        self._stream_paused = False
        self._last_live_emit = 0.0

        self._build_ui()
        self._apply_style()
        self.refresh_resources()
        self._sync_channel()
        self._update_controls()

        # Renderização/entrega de frames em ~30 FPS. A taxa real de aquisição
        # depende do transporte VISA; ASRL normalmente será mais lento.
        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(33)
        self.ui_timer.timeout.connect(self._drain_reader_queue)
        self.ui_timer.start()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.setObjectName("oscilloscopePanel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("scopeHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(12, 7, 10, 7)
        h.setSpacing(7)

        self.collapse_btn = QPushButton("▾")
        self.collapse_btn.setObjectName("scopeIconBtn")
        self.collapse_btn.setFixedSize(24, 24)
        self.collapse_btn.clicked.connect(self.toggle_collapsed)
        h.addWidget(self.collapse_btn)

        title = QLabel("OSCILOSCÓPIO")
        title.setObjectName("scopeTitle")
        h.addWidget(title)

        model = QLabel("• Rigol MSO5074")
        model.setObjectName("scopeMuted")
        h.addWidget(model)
        h.addStretch()

        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("scopeStatusDot")
        h.addWidget(self.status_dot)
        self.status_label = QLabel("Desconectado")
        self.status_label.setObjectName("scopeStatus")
        h.addWidget(self.status_label)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("scopeIconBtn")
        self.settings_btn.setFixedSize(28, 24)
        self.settings_btn.setToolTip("Configurar osciloscópio")
        self.settings_btn.clicked.connect(self.open_settings)
        h.addWidget(self.settings_btn)
        root.addWidget(header)

        self.body = QFrame()
        self.body.setObjectName("scopeBody")
        self.body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        b = QVBoxLayout(self.body)
        b.setContentsMargins(10, 7, 10, 9)
        b.setSpacing(6)

        # Mantemos a escolha de recurso VISA já existente, mas em uma única linha.
        connection = QHBoxLayout()
        connection.setSpacing(5)
        self.resource_combo = QComboBox()
        self.resource_combo.setEditable(True)
        self.resource_combo.setMinimumWidth(150)
        connection.addWidget(self.resource_combo, 1)

        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setObjectName("scopeIconBtn")
        self.refresh_btn.setFixedSize(28, 28)
        self.refresh_btn.setToolTip("Atualizar recursos VISA")
        self.refresh_btn.clicked.connect(self.refresh_resources)
        connection.addWidget(self.refresh_btn)

        self.connect_btn = QPushButton("Conectar")
        self.connect_btn.setObjectName("scopeConnectBtn")
        self.connect_btn.setMinimumWidth(86)
        self.connect_btn.setFixedHeight(28)
        self.connect_btn.clicked.connect(self.toggle_connection)
        connection.addWidget(self.connect_btn)
        b.addLayout(connection)

        # AQUI está a substituição principal: antiga QLabel/grade de métricas ->
        # mini tela digital com forma de onda em tempo real.
        self.scope_display = OscilloscopeDisplay(self)
        self.scope_display.start_requested.connect(self.start_stream)
        self.scope_display.pause_requested.connect(self.pause_stream)
        self.scope_display.stop_requested.connect(self.stop_stream)
        self.scope_display.channels_changed.connect(self._channels_changed)
        b.addWidget(self.scope_display)

        action = QHBoxLayout()
        action.setSpacing(6)
        self.point_label = QLabel("Ponto: nenhum")
        self.point_label.setObjectName("scopeMuted")
        action.addWidget(self.point_label)
        action.addStretch()

        self.channel_combo = QComboBox()
        self.channel_combo.addItems(["CH1", "CH2", "CH3", "CH4"])
        self.channel_combo.setFixedWidth(66)
        self.channel_combo.setToolTip("Canal usado ao capturar para o ponto selecionado")
        self.channel_combo.currentIndexChanged.connect(self._channel_changed)
        action.addWidget(self.channel_combo)

        self.capture_btn = QPushButton("Capturar no ponto")
        self.capture_btn.setObjectName("scopeCaptureBtn")
        self.capture_btn.setEnabled(False)
        self.capture_btn.setFixedHeight(28)
        self.capture_btn.clicked.connect(self.capture_now)
        action.addWidget(self.capture_btn)
        b.addLayout(action)

        self.error_label = QLabel("")
        self.error_label.setObjectName("scopeError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        b.addWidget(self.error_label)

        root.addWidget(self.body)

    def _apply_style(self) -> None:
        t = self.theme
        self.setStyleSheet(
            f"""
            QFrame#oscilloscopePanel {{
                background: {t.BG_SURFACE}; border: 1px solid {t.BORDER_SUBTLE}; border-radius: 7px;
            }}
            QFrame#scopeHeader, QFrame#scopeBody {{ background: {t.BG_SURFACE}; border: none; }}
            QLabel#scopeTitle {{ color: {t.ACCENT_CYAN}; font-size: 10px; font-weight: 800; }}
            QLabel#scopeMuted {{ color: {t.TEXT_MUTED}; font-size: 10px; }}
            QLabel#scopeStatus {{ color: {t.TEXT_SECONDARY}; font-size: 10px; font-weight: 600; }}
            QLabel#scopeStatusDot {{ color: {t.TEXT_MUTED}; font-size: 11px; }}
            QLabel#scopeError {{ color: {t.ERROR_RED}; font-size: 9px; }}
            QComboBox {{
                background: {t.BG_INPUT}; color: {t.TEXT_PRIMARY};
                border: 1px solid {t.BORDER_SUBTLE}; border-radius: 5px;
                padding: 4px 7px; min-height: 18px;
            }}
            QComboBox:focus {{ border-color: {t.ACCENT_BLUE}; }}
            QPushButton#scopeIconBtn {{
                background: transparent; color: {t.TEXT_SECONDARY}; border: none;
                border-radius: 4px; font-weight: 700; padding: 0;
            }}
            QPushButton#scopeIconBtn:hover {{ background: {t.BG_HOVER}; color: {t.TEXT_BRIGHT}; }}
            QPushButton#scopeConnectBtn {{
                background: {t.BG_SURFACE_ALT}; color: {t.TEXT_PRIMARY};
                border: 1px solid {t.BORDER_SUBTLE}; border-radius: 5px;
                padding: 4px 9px; font-weight: 700;
            }}
            QPushButton#scopeConnectBtn:hover {{ border-color: {t.ACCENT_BLUE}; }}
            QPushButton#scopeCaptureBtn {{
                background: {t.ACCENT_BLUE}; color: {t.TEXT_BRIGHT}; border: none;
                border-radius: 5px; padding: 4px 10px; font-weight: 700;
            }}
            QPushButton#scopeCaptureBtn:disabled {{
                background: {t.BG_SURFACE_ALT}; color: {t.TEXT_MUTED};
            }}
            """
        )

    # -------------------------------------------------------------- resources
    def refresh_resources(self) -> None:
        current = self.resource_combo.currentText().strip() if hasattr(self, "resource_combo") else ""
        resources = ["ASRL4::INSTR", "MOCK::MSO5074"]
        for resource in list_visa_resources(str(self.config.get("visa_backend") or "")):
            if resource not in resources:
                resources.append(resource)

        saved = str(self.config.get("resource") or "ASRL4::INSTR")
        self.resource_combo.blockSignals(True)
        self.resource_combo.clear()
        self.resource_combo.addItems(resources)
        candidate = current or saved
        idx = self.resource_combo.findText(candidate)
        if idx >= 0:
            self.resource_combo.setCurrentIndex(idx)
        else:
            self.resource_combo.setEditText(candidate)
        self.resource_combo.blockSignals(False)

    def _sync_channel(self) -> None:
        channel = max(1, min(int(self.config.get("channel", 1)), 4))
        self.channel_combo.setCurrentIndex(channel - 1)
        self.scope_display.set_active_channel(channel)

    def open_settings(self) -> None:
        if self.reader is not None and self.reader.is_alive():
            QMessageBox.information(
                self,
                "Osciloscópio conectado",
                "Desconecte o osciloscópio antes de alterar a comunicação.",
            )
            return
        dlg = OscilloscopeSettingsDialog(self.document, self.config, self.theme, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.config = dlg.result_config()
        self.document["last_config"] = dict(self.config)
        try:
            save_config_document(self.document)
        except Exception as exc:
            self._show_error(f"Não foi possível salvar a configuração: {exc}")
        self.refresh_resources()
        self._sync_channel()

    # ------------------------------------------------------------- connection
    def toggle_connection(self) -> None:
        if self.reader is not None and self.reader.is_alive():
            self.disconnect_device()
        else:
            self.connect_device()

    def connect_device(self) -> None:
        if self.reader is not None and self.reader.is_alive():
            return

        resource = self.resource_combo.currentText().strip()
        if not resource:
            self._show_error("Selecione ou informe um recurso VISA.")
            return

        self.config["resource"] = resource
        self.config["backend"] = "mock" if resource.upper().startswith("MOCK") else "visa"
        self.config["channel"] = self.channel_combo.currentIndex() + 1
        self.config["capture_waveform"] = True
        self.document["last_config"] = dict(self.config)
        try:
            save_config_document(self.document)
        except Exception:
            logger.exception("Falha ao salvar configuração do osciloscópio")

        self._clear_error()
        self._connected = False
        self._simulated = resource.upper().startswith("MOCK")
        self.status_label.setText("Conectando…")
        self.scope_display.set_status("Conectando…")

        self.reader_queue = queue.Queue(maxsize=4)
        hz = 30.0 if self._simulated else float(self.config.get("reader_hz", 12))
        self.reader = DataReader(
            self.config,
            self.reader_queue,
            active_channels=self.scope_display.active_channels(),
            target_reader_hz=hz,
        )
        self.reader.start()
        self._stream_paused = False
        self._update_controls()

    def disconnect_device(self, wait: bool = False) -> None:
        reader = self.reader
        if reader is None:
            return
        reader.stop()
        self.status_label.setText("Desconectando…")
        self.scope_display.set_status("Desconectando…")
        if wait and reader.is_alive():
            reader.join(timeout=2.5)
        self._connected = False
        self._update_controls()

    def shutdown(self) -> None:
        if hasattr(self, "ui_timer"):
            self.ui_timer.stop()
        self.disconnect_device(wait=True)

    # --------------------------------------------------------------- stream UI
    def start_stream(self) -> None:
        if self.reader is None or not self.reader.is_alive():
            self.connect_device()
            return
        self.reader.pause(False)
        self._stream_paused = False
        if hasattr(self.scope_display, "set_paused"):
            self.scope_display.set_paused(False)
        self._set_status("Simulando" if self._simulated else "Conectado")
        if self.selected_point_id is not None:
            self.point_label.setText(f"Ponto: {self.selected_point_name}")

    def pause_stream(self, paused: bool) -> None:
        if self.reader is None or not self.reader.is_alive():
            return
        self.reader.pause(paused)
        self._stream_paused = bool(paused)
        if hasattr(self.scope_display, "set_paused"):
            self.scope_display.set_paused(bool(paused))
        if paused:
            self._set_status("Pausado")
        else:
            self._set_status("Simulando" if self._simulated else "Conectado")
        if self.selected_point_id is not None:
            suffix = " • PAUSADO" if self._stream_paused else ""
            self.point_label.setText(f"Ponto: {self.selected_point_name}{suffix}")

    def stop_stream(self) -> None:
        if self.reader is None or not self.reader.is_alive():
            return
        # O botão stop interrompe a atualização sem fechar a sessão VISA.
        # "Conectar/Desconectar" continua responsável pela conexão física.
        self.reader.pause(True)
        self._stream_paused = True
        self._set_status("Parado")

    def _channels_changed(self, channels) -> None:
        if self.reader is not None and self.reader.is_alive():
            self.reader.set_channels(channels)

    def _channel_changed(self) -> None:
        channel = self.channel_combo.currentIndex() + 1
        self.config["channel"] = channel
        self.scope_display.set_active_channel(channel)

    # ------------------------------------------------------------ queue -> GUI
    def _drain_reader_queue(self) -> None:
        latest_frame = None
        while True:
            try:
                event = self.reader_queue.get_nowait()
            except queue.Empty:
                break

            event_type = event.get("type")
            if event_type == "frame":
                latest_frame = event.get("frame")
            elif event_type == "snapshot":
                self._handle_snapshot(event.get("reading"), event.get("context"))
            elif event_type == "status":
                self._handle_status(event)
            elif event_type == "error":
                self._handle_error(str(event.get("message") or "Erro de comunicação"))

        # Enquanto pausado, continuamos drenando a fila para descartar frames
        # antigos, mas não atualizamos a tela nem associamos leitura ao novo ponto.
        # Isso evita que uma leitura feita durante a troca da ponta de prova seja
        # atribuída ao ponto seguinte.
        if latest_frame is not None and not self._stream_paused:
            self.scope_display.update_frame(latest_frame)
            capture_ch = self.channel_combo.currentIndex() + 1
            metric = (latest_frame.readings or {}).get(capture_ch)
            if isinstance(metric, OscilloscopeReading):
                self.latest_reading = metric
                # A aquisição pode chegar mais rápido que a tabela precisa.
                # Limitamos a atualização visual da comparação a ~10 Hz.
                now = time.monotonic()
                if now - self._last_live_emit >= 0.10:
                    self._last_live_emit = now
                    self.live_reading_changed.emit(metric)

        if self.reader is not None and not self.reader.is_alive() and not self._connected:
            self.reader = None
            self._update_controls()

    def _handle_status(self, event: dict[str, Any]) -> None:
        connected = bool(event.get("connected"))
        simulated = bool(event.get("simulated"))
        status = str(event.get("status") or ("Conectado" if connected else "Desconectado"))
        identifier = str(event.get("identifier") or "")

        self._connected = connected
        self._simulated = simulated
        self._set_status(status)
        if connected:
            self._clear_error()
            suffix = f": {identifier}" if identifier else ""
            self.status_changed.emit(f"Osciloscópio {status.lower()}{suffix}", "success")
        self._update_controls()

    def _handle_error(self, message: str) -> None:
        self._show_error(message)
        self.status_changed.emit(f"Osciloscópio: {message}", "error")

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
        if self._simulated and self._connected:
            color = "#FACC15"
        elif self._connected:
            color = self.theme.VCC_GREEN
        else:
            color = self.theme.TEXT_MUTED
        self.status_dot.setStyleSheet(f"color: {color};")
        self.scope_display.set_status(
            text,
            connected=self._connected,
            simulated=self._simulated and self._connected,
        )

    # --------------------------------------------------------------- capture
    def capture_now(self) -> None:
        if self.selected_point_id is None:
            self.status_changed.emit("Selecione um ponto antes de capturar", "warning")
            return
        if self.reader is None or not self.reader.is_alive() or not self._connected:
            self.status_changed.emit("Conecte o osciloscópio antes de capturar", "warning")
            return

        channel = self.channel_combo.currentIndex() + 1
        self.reader.request_snapshot(channel, {"capture_point_id": self.selected_point_id})
        self.status_label.setText("Capturando…")

    def _handle_snapshot(self, reading, context) -> None:
        if not isinstance(reading, OscilloscopeReading):
            return
        self.latest_reading = reading
        if self._connected:
            self._set_status("Simulando" if self._simulated else "Conectado")
        if isinstance(context, dict) and context.get("capture_point_id"):
            self.capture_requested.emit(int(context["capture_point_id"]), reading)

    def capture_latest_for_selected(self) -> bool:
        if self.selected_point_id is None or self.latest_reading is None:
            return False
        if self.latest_reading.channel != self.channel_combo.currentIndex() + 1:
            return False
        self.capture_requested.emit(self.selected_point_id, self.latest_reading)
        return True

    def set_selected_point(self, point) -> None:
        new_id = int(point.id) if point is not None else None
        old_id = self.selected_point_id

        # Se o operador saiu de um ponto para outro, congela a aquisição antes
        # de trocar a associação. Isso dá tempo para mover fisicamente a ponta
        # do Rigol sem contaminar a leitura do próximo ponto.
        point_changed = old_id is not None and new_id != old_id
        if point_changed and self.reader is not None and self.reader.is_alive():
            self.pause_stream(True)
            self.latest_reading = None
            self.status_changed.emit(
                "Osciloscópio pausado ao trocar de ponto. Reposicione a ponta e pressione ▶ para continuar.",
                "info",
            )

        if point is None:
            self.selected_point_id = None
            self.selected_point_name = ""
            self.point_label.setText("Ponto: nenhum")
        else:
            self.selected_point_id = new_id
            self.selected_point_name = str(point.refdes)
            suffix = " • PAUSADO" if self._stream_paused else ""
            self.point_label.setText(f"Ponto: {self.selected_point_name}{suffix}")
        self._update_controls()

    def is_paused(self) -> bool:
        return bool(self._stream_paused)

    def is_continuous(self) -> bool:
        return bool(self._connected and not self._stream_paused)

    # --------------------------------------------------------------- misc UI
    def toggle_collapsed(self) -> None:
        self._expanded = not self._expanded
        self.body.setVisible(self._expanded)
        self.collapse_btn.setText("▾" if self._expanded else "▸")

    def _update_controls(self) -> None:
        running = self.reader is not None and self.reader.is_alive()
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Desconectar" if running else "Conectar")
        self.resource_combo.setEnabled(not running)
        self.refresh_btn.setEnabled(not running)
        self.settings_btn.setEnabled(not running)
        self.channel_combo.setEnabled(True)
        self.capture_btn.setEnabled(self._connected and self.selected_point_id is not None)

    def _show_error(self, text: str) -> None:
        self.error_label.setText(text)
        self.error_label.show()

    def _clear_error(self) -> None:
        self.error_label.clear()
        self.error_label.hide()
