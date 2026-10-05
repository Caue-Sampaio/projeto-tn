from __future__ import annotations

import copy
import json
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSpinBox, QSizePolicy, QVBoxLayout, QWidget
)

from oscilloscope.base import OscilloscopeReading
from oscilloscope.factory import create_driver, list_visa_resources

logger = logging.getLogger(__name__)
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "oscilloscope.json"


def _default_document() -> dict[str, Any]:
    return {
        "presets": {
            "Rigol MSO5074 - USB/LAN": {
                "backend": "visa", "model": "Rigol MSO5074",
                "timeout_ms": 1800, "poll_interval_ms": 500,
                "capture_waveform": False, "waveform_points": 1200,
            },
            "Simulador MSO5074": {
                "backend": "mock", "model": "Rigol MSO5074 (Simulado)",
                "resource": "MOCK::MSO5074", "timeout_ms": 1000,
                "poll_interval_ms": 500, "capture_waveform": False,
                "waveform_points": 1200,
            },
        },
        "last_config": {
            "preset": "Simulador MSO5074", "backend": "mock",
            "model": "Rigol MSO5074 (Simulado)", "resource": "MOCK::MSO5074",
            "channel": 1, "timeout_ms": 1800, "poll_interval_ms": 500,
            "read_termination": "\n", "write_termination": "\n",
            "visa_backend": "", "auto_reconnect": True,
            "capture_waveform": False, "waveform_points": 1200,
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


class OscilloscopeWorker(QThread):
    connection_changed = pyqtSignal(bool, str)
    reading_ready = pyqtSignal(object, object)
    error = pyqtSignal(str)

    def __init__(self, config: dict[str, Any], parent=None):
        super().__init__(parent)
        self.config = dict(config)
        self._commands: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._stop_event = threading.Event()
        self._driver = None
        self._continuous = False
        self._consecutive_errors = 0
        self._channel = int(self.config.get("channel", 1))

    def request_read(self, context=None) -> None:
        self._commands.put(("read", context))

    def set_continuous(self, enabled: bool) -> None:
        self._commands.put(("continuous", bool(enabled)))

    def set_channel(self, channel: int) -> None:
        self._commands.put(("channel", int(channel)))

    def stop(self) -> None:
        self._stop_event.set()
        self._commands.put(("stop", None))

    def _connect(self) -> None:
        self._driver = create_driver(self.config)
        self._driver.connect()
        self._consecutive_errors = 0
        self.connection_changed.emit(True, self._driver.identifier)

    def _disconnect(self) -> None:
        try:
            if self._driver is not None:
                self._driver.disconnect()
        except Exception:
            logger.exception("Erro ao desconectar osciloscópio")
        self._driver = None
        self.connection_changed.emit(False, "Desconectado")

    def _read(self, context=None, live: bool = False) -> None:
        if self._driver is None:
            raise RuntimeError("Osciloscópio não conectado")
        reading = (
            self._driver.read_live(self._channel)
            if live else self._driver.read_snapshot(self._channel)
        )
        self._consecutive_errors = 0
        self.reading_ready.emit(reading, context)

    def _try_reconnect(self) -> None:
        if not bool(self.config.get("auto_reconnect", True)):
            return
        try:
            if self._driver is not None:
                self._driver.disconnect()
            self.connection_changed.emit(False, "Reconectando…")
            self._connect()
        except Exception as exc:
            self.error.emit(f"Falha ao reconectar: {exc}")

    def run(self) -> None:
        poll_s = max(0.2, int(self.config.get("poll_interval_ms", 500)) / 1000.0)
        try:
            self._connect()
        except Exception as exc:
            self.error.emit(f"Falha ao conectar: {exc}")
            self.connection_changed.emit(False, "Falha na conexão")
            return

        next_poll = time.monotonic()
        try:
            while not self._stop_event.is_set():
                try:
                    command, payload = self._commands.get(timeout=0.08)
                except queue.Empty:
                    command, payload = None, None

                if command == "stop":
                    break
                if command == "continuous":
                    self._continuous = bool(payload)
                    next_poll = time.monotonic()
                elif command == "channel":
                    self._channel = int(payload)
                    next_poll = time.monotonic()
                elif command == "read":
                    try:
                        self._read(payload)
                    except Exception as exc:
                        self._consecutive_errors += 1
                        self.error.emit(str(exc))
                        if self._consecutive_errors >= 2:
                            self._try_reconnect()

                if self._continuous and time.monotonic() >= next_poll:
                    try:
                        self._read(None, live=True)
                    except Exception as exc:
                        self._consecutive_errors += 1
                        self.error.emit(str(exc))
                        if self._consecutive_errors >= 2:
                            self._try_reconnect()
                    next_poll = time.monotonic() + poll_s
        finally:
            self._disconnect()


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
        subtitle = QLabel("Conexão VISA, monitoramento e captura de forma de onda")
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

        self.poll = QSpinBox()
        self.poll.setRange(200, 10000)
        self.poll.setSingleStep(100)
        self.poll.setSuffix(" ms")
        form.addRow("Intervalo contínuo", self.poll)

        self.auto_reconnect = QCheckBox("Tentar reconectar automaticamente")
        form.addRow("", self.auto_reconnect)

        self.capture_waveform = QCheckBox("Salvar amostra da forma de onda junto à captura")
        form.addRow("", self.capture_waveform)

        self.waveform_points = QSpinBox()
        self.waveform_points.setRange(100, 12000)
        self.waveform_points.setSingleStep(100)
        self.waveform_points.setSuffix(" pontos")
        form.addRow("Amostra da curva", self.waveform_points)

        hint = QLabel("Para LAN você pode digitar manualmente um recurso VISA TCPIP no painel principal.")
        hint.setObjectName("scopeMuted")
        hint.setWordWrap(True)

        root.addLayout(form)
        root.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _apply_style(self) -> None:
        t = self.theme
        self.setStyleSheet(f"""
            QDialog {{ background: {t.BG_PRIMARY}; color: {t.TEXT_PRIMARY}; }}
            QLabel#scopeDialogTitle {{ color: {t.ACCENT_CYAN}; font-size: 16px; font-weight: 800; }}
            QLabel#scopeMuted {{ color: {t.TEXT_MUTED}; font-size: 10px; }}
            QLineEdit, QComboBox, QSpinBox {{ background: {t.BG_INPUT}; color: {t.TEXT_PRIMARY}; border: 1px solid {t.BORDER_SUBTLE}; border-radius: 5px; padding: 6px 8px; }}
            QCheckBox {{ color: {t.TEXT_SECONDARY}; }}
            QPushButton {{ background: {t.BG_SURFACE_ALT}; color: {t.TEXT_PRIMARY}; border: 1px solid {t.BORDER_SUBTLE}; border-radius: 5px; padding: 7px 14px; font-weight: 600; }}
            QPushButton:hover {{ border-color: {t.ACCENT_BLUE}; }}
        """)

    def _set_data(self, combo: QComboBox, value: str) -> None:
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
        self.timeout.setValue(int(cfg.get("timeout_ms", 1800)))
        self.poll.setValue(int(cfg.get("poll_interval_ms", 500)))
        self.auto_reconnect.setChecked(bool(cfg.get("auto_reconnect", True)))
        self.capture_waveform.setChecked(bool(cfg.get("capture_waveform", False)))
        self.waveform_points.setValue(int(cfg.get("waveform_points", 1200)))

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
            "poll_interval_ms": self.poll.value(),
            "auto_reconnect": self.auto_reconnect.isChecked(),
            "capture_waveform": self.capture_waveform.isChecked(),
            "waveform_points": self.waveform_points.value(),
            "read_termination": self.config.get("read_termination", "\n"),
            "write_termination": self.config.get("write_termination", "\n"),
        }


class OscilloscopePanel(QFrame):
    capture_requested = pyqtSignal(int, object)
    status_changed = pyqtSignal(str, str)

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.document = load_config_document()
        self.config = dict(self.document.get("last_config") or {})
        self.worker: OscilloscopeWorker | None = None
        self.selected_point_id: int | None = None
        self.selected_point_name = ""
        self.latest_reading: OscilloscopeReading | None = None
        self._connected = False
        self._expanded = True
        self._build_ui()
        self._apply_style()
        self.refresh_resources()
        self._sync_channel()
        self._update_controls()

    def _build_ui(self) -> None:
        self.setObjectName("oscilloscopePanel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame(); header.setObjectName("scopeHeader")
        h = QHBoxLayout(header); h.setContentsMargins(12, 8, 10, 8); h.setSpacing(8)
        self.collapse_btn = QPushButton("▾"); self.collapse_btn.setObjectName("scopeIconBtn"); self.collapse_btn.setFixedSize(24, 24); self.collapse_btn.clicked.connect(self.toggle_collapsed)
        h.addWidget(self.collapse_btn)
        title = QLabel("OSCILOSCÓPIO"); title.setObjectName("scopeTitle"); h.addWidget(title)
        model = QLabel("• Rigol MSO5074"); model.setObjectName("scopeMuted"); h.addWidget(model)
        h.addStretch()
        self.status_dot = QLabel("●"); self.status_dot.setObjectName("scopeStatusDot"); h.addWidget(self.status_dot)
        self.status_label = QLabel("Desconectado"); self.status_label.setObjectName("scopeStatus"); h.addWidget(self.status_label)
        self.settings_btn = QPushButton("⚙"); self.settings_btn.setObjectName("scopeIconBtn"); self.settings_btn.setFixedSize(28, 24); self.settings_btn.setToolTip("Configurar osciloscópio"); self.settings_btn.clicked.connect(self.open_settings); h.addWidget(self.settings_btn)
        root.addWidget(header)

        self.body = QFrame(); self.body.setObjectName("scopeBody"); self.body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        b = QVBoxLayout(self.body); b.setContentsMargins(12, 10, 12, 12); b.setSpacing(8)

        connection = QHBoxLayout(); connection.setSpacing(6)
        self.resource_combo = QComboBox(); self.resource_combo.setEditable(True); self.resource_combo.setMinimumWidth(160); connection.addWidget(self.resource_combo, 1)
        self.refresh_btn = QPushButton("↻"); self.refresh_btn.setObjectName("scopeIconBtn"); self.refresh_btn.setFixedSize(30, 30); self.refresh_btn.setToolTip("Atualizar recursos VISA"); self.refresh_btn.clicked.connect(self.refresh_resources); connection.addWidget(self.refresh_btn)
        self.connect_btn = QPushButton("Conectar"); self.connect_btn.setObjectName("scopeConnectBtn"); self.connect_btn.setMinimumWidth(92); self.connect_btn.clicked.connect(self.toggle_connection); connection.addWidget(self.connect_btn)
        b.addLayout(connection)

        channel_row = QHBoxLayout(); channel_row.setSpacing(8)
        ch_label = QLabel("Canal"); ch_label.setObjectName("scopeMuted"); channel_row.addWidget(ch_label)
        self.channel_combo = QComboBox(); self.channel_combo.addItems(["CH1", "CH2", "CH3", "CH4"]); self.channel_combo.setFixedWidth(78); self.channel_combo.currentIndexChanged.connect(self._channel_changed); channel_row.addWidget(self.channel_combo)
        channel_row.addStretch()
        self.continuous_check = QCheckBox("Monitoramento contínuo"); self.continuous_check.setObjectName("scopeContinuous"); self.continuous_check.setEnabled(False); self.continuous_check.toggled.connect(self._continuous_toggled); channel_row.addWidget(self.continuous_check)
        b.addLayout(channel_row)

        self.display = QLabel("— —"); self.display.setObjectName("scopeDisplay"); self.display.setMinimumHeight(44); b.addWidget(self.display)

        metrics = QGridLayout(); metrics.setHorizontalSpacing(12); metrics.setVerticalSpacing(4)
        self.metric_labels: dict[str, QLabel] = {}
        specs = [("Vpp", "vpp"), ("Vrms", "vrms"), ("Freq.", "freq"), ("Duty", "duty")]
        for i, (name, key) in enumerate(specs):
            name_label = QLabel(name); name_label.setObjectName("scopeMetricName")
            value_label = QLabel("—"); value_label.setObjectName("scopeMetricValue")
            row, col = divmod(i, 2)
            metrics.addWidget(name_label, row, col * 2)
            metrics.addWidget(value_label, row, col * 2 + 1)
            self.metric_labels[key] = value_label
        metrics.setColumnStretch(1, 1); metrics.setColumnStretch(3, 1)
        b.addLayout(metrics)

        action = QHBoxLayout(); action.setSpacing(8)
        self.point_label = QLabel("Ponto: nenhum"); self.point_label.setObjectName("scopeMuted"); action.addWidget(self.point_label)
        action.addStretch()
        self.capture_btn = QPushButton("Capturar no ponto selecionado"); self.capture_btn.setObjectName("scopeCaptureBtn"); self.capture_btn.setEnabled(False); self.capture_btn.clicked.connect(self.capture_now); action.addWidget(self.capture_btn)
        b.addLayout(action)

        self.error_label = QLabel(""); self.error_label.setObjectName("scopeError"); self.error_label.setWordWrap(True); self.error_label.hide(); b.addWidget(self.error_label)
        root.addWidget(self.body)

    def _apply_style(self) -> None:
        t = self.theme
        self.setStyleSheet(f"""
            QFrame#oscilloscopePanel {{ background: {t.BG_SURFACE}; border: 1px solid {t.BORDER_SUBTLE}; border-radius: 7px; }}
            QFrame#scopeHeader, QFrame#scopeBody {{ background: {t.BG_SURFACE}; border: none; }}
            QLabel#scopeTitle {{ color: {t.ACCENT_CYAN}; font-size: 10px; font-weight: 800; }}
            QLabel#scopeMuted, QLabel#scopeMetricName {{ color: {t.TEXT_MUTED}; font-size: 10px; }}
            QLabel#scopeStatus {{ color: {t.TEXT_SECONDARY}; font-size: 10px; font-weight: 600; }}
            QLabel#scopeStatusDot {{ color: {t.TEXT_MUTED}; font-size: 11px; }}
            QLabel#scopeDisplay {{ color: {t.TEXT_BRIGHT}; background: {t.BG_CANVAS}; border: 1px solid {t.BORDER_SUBTLE}; border-radius: 6px; padding: 7px 12px; font-family: Consolas, monospace; font-size: 18px; font-weight: 800; }}
            QLabel#scopeMetricValue {{ color: {t.TEXT_PRIMARY}; font-family: Consolas, monospace; font-size: 10px; font-weight: 700; }}
            QLabel#scopeError {{ color: {t.ERROR_RED}; font-size: 9px; }}
            QComboBox {{ background: {t.BG_INPUT}; color: {t.TEXT_PRIMARY}; border: 1px solid {t.BORDER_SUBTLE}; border-radius: 5px; padding: 5px 8px; min-height: 18px; }}
            QComboBox:focus {{ border-color: {t.ACCENT_BLUE}; }}
            QCheckBox#scopeContinuous {{ color: {t.TEXT_SECONDARY}; font-size: 10px; }}
            QPushButton#scopeIconBtn {{ background: transparent; color: {t.TEXT_SECONDARY}; border: none; border-radius: 4px; font-weight: 700; }}
            QPushButton#scopeIconBtn:hover {{ background: {t.BG_HOVER}; color: {t.TEXT_BRIGHT}; }}
            QPushButton#scopeConnectBtn {{ background: {t.BG_SURFACE_ALT}; color: {t.TEXT_PRIMARY}; border: 1px solid {t.BORDER_SUBTLE}; border-radius: 5px; padding: 6px 10px; font-weight: 700; }}
            QPushButton#scopeConnectBtn:hover {{ border-color: {t.ACCENT_BLUE}; }}
            QPushButton#scopeCaptureBtn {{ background: {t.ACCENT_BLUE}; color: {t.TEXT_BRIGHT}; border: none; border-radius: 5px; padding: 7px 12px; font-weight: 700; }}
            QPushButton#scopeCaptureBtn:disabled {{ background: {t.BG_SURFACE_ALT}; color: {t.TEXT_MUTED}; }}
        """)

    def refresh_resources(self) -> None:
        current = self.resource_combo.currentText().strip() if hasattr(self, "resource_combo") else ""
        resources = ["MOCK::MSO5074"]
        resources.extend(r for r in list_visa_resources(str(self.config.get("visa_backend") or "")) if r not in resources)
        saved = str(self.config.get("resource") or "")
        self.resource_combo.blockSignals(True)
        self.resource_combo.clear(); self.resource_combo.addItems(resources)
        candidate = current or saved
        if candidate:
            idx = self.resource_combo.findText(candidate)
            if idx >= 0: self.resource_combo.setCurrentIndex(idx)
            else: self.resource_combo.setEditText(candidate)
        self.resource_combo.blockSignals(False)

    def _sync_channel(self) -> None:
        channel = max(1, min(int(self.config.get("channel", 1)), 4))
        self.channel_combo.setCurrentIndex(channel - 1)

    def open_settings(self) -> None:
        if self._connected:
            QMessageBox.information(self, "Osciloscópio conectado", "Desconecte o osciloscópio antes de alterar a comunicação.")
            return
        dlg = OscilloscopeSettingsDialog(self.document, self.config, self.theme, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.config = dlg.result_config()
        self.document["last_config"] = dict(self.config)
        try: save_config_document(self.document)
        except Exception as exc: self._show_error(f"Não foi possível salvar a configuração: {exc}")
        self.refresh_resources(); self._sync_channel()

    def toggle_connection(self) -> None:
        if self.worker is not None and self.worker.isRunning(): self.disconnect_device()
        else: self.connect_device()

    def connect_device(self) -> None:
        if self.worker is not None and self.worker.isRunning(): return
        resource = self.resource_combo.currentText().strip()
        if not resource:
            self._show_error("Selecione ou informe um recurso VISA."); return
        self.config["resource"] = resource
        self.config["backend"] = "mock" if resource.upper().startswith("MOCK") else "visa"
        self.config["channel"] = self.channel_combo.currentIndex() + 1
        self.document["last_config"] = dict(self.config)
        try: save_config_document(self.document)
        except Exception: logger.exception("Falha ao salvar configuração do osciloscópio")
        self._clear_error(); self.status_label.setText("Conectando…"); self.connect_btn.setEnabled(False)
        self.worker = OscilloscopeWorker(self.config, self)
        self.worker.connection_changed.connect(self._on_connection_changed)
        self.worker.reading_ready.connect(self._on_reading)
        self.worker.error.connect(self._on_worker_error)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def disconnect_device(self, wait: bool = False) -> None:
        worker = self.worker
        if worker is None: return
        self.continuous_check.blockSignals(True); self.continuous_check.setChecked(False); self.continuous_check.blockSignals(False)
        worker.stop(); self.status_label.setText("Desconectando…")
        if wait: worker.wait(2500)
        self._connected = False; self._update_controls()

    def shutdown(self) -> None:
        self.disconnect_device(wait=True)

    def _on_connection_changed(self, connected: bool, identifier: str) -> None:
        self._connected = connected
        self.status_label.setText("Conectado" if connected else identifier)
        self.status_dot.setStyleSheet(f"color: {self.theme.VCC_GREEN if connected else self.theme.TEXT_MUTED};")
        if connected:
            self._clear_error(); self.status_changed.emit(f"Osciloscópio conectado: {identifier}", "success")
        self._update_controls()

    def _on_worker_finished(self) -> None:
        self._connected = False; self.worker = None; self.status_label.setText("Desconectado")
        self.status_dot.setStyleSheet(f"color: {self.theme.TEXT_MUTED};"); self._update_controls()

    def _on_worker_error(self, message: str) -> None:
        self._show_error(message); self.status_changed.emit(f"Osciloscópio: {message}", "error")

    def _channel_changed(self) -> None:
        channel = self.channel_combo.currentIndex() + 1
        self.config["channel"] = channel
        if self.worker is not None and self.worker.isRunning(): self.worker.set_channel(channel)
        self.latest_reading = None; self._clear_metrics()

    def _continuous_toggled(self, enabled: bool) -> None:
        if self.worker is not None and self.worker.isRunning(): self.worker.set_continuous(enabled)
        self.status_changed.emit("Monitoramento contínuo ativado" if enabled else "Monitoramento contínuo desativado", "info")

    def capture_now(self) -> None:
        if self.selected_point_id is None:
            self.status_changed.emit("Selecione um ponto antes de capturar", "warning"); return
        if self.worker is None or not self.worker.isRunning() or not self._connected:
            self.status_changed.emit("Conecte o osciloscópio antes de capturar", "warning"); return
        self.worker.request_read({"capture_point_id": self.selected_point_id})
        self.status_label.setText("Lendo…")

    def capture_latest_for_selected(self) -> bool:
        if self.selected_point_id is None or self.latest_reading is None: return False
        if self.latest_reading.channel != self.channel_combo.currentIndex() + 1: return False
        self.capture_requested.emit(self.selected_point_id, self.latest_reading)
        return True

    def _on_reading(self, reading: OscilloscopeReading, context) -> None:
        self.latest_reading = reading; self._update_metrics(reading)
        if self._connected: self.status_label.setText("Conectado")
        if isinstance(context, dict) and context.get("capture_point_id"):
            self.capture_requested.emit(int(context["capture_point_id"]), reading)

    def set_selected_point(self, point) -> None:
        if point is None:
            self.selected_point_id = None; self.selected_point_name = ""; self.point_label.setText("Ponto: nenhum")
        else:
            self.selected_point_id = int(point.id); self.selected_point_name = str(point.refdes); self.point_label.setText(f"Ponto: {self.selected_point_name}")
        self._update_controls()

    def is_continuous(self) -> bool:
        return self.continuous_check.isChecked()

    def toggle_collapsed(self) -> None:
        self._expanded = not self._expanded; self.body.setVisible(self._expanded); self.collapse_btn.setText("▾" if self._expanded else "▸")

    def _update_metrics(self, r: OscilloscopeReading) -> None:
        self.display.setText(r.display_text)
        self.metric_labels["vpp"].setText(OscilloscopeReading._fmt(r.vpp_v, "V"))
        self.metric_labels["vrms"].setText(OscilloscopeReading._fmt(r.vrms_v, "V"))
        self.metric_labels["freq"].setText(OscilloscopeReading._fmt(r.frequency_hz, "Hz"))
        self.metric_labels["duty"].setText("—" if r.duty_cycle_pct is None else f"{r.duty_cycle_pct:.3g} %")

    def _clear_metrics(self) -> None:
        self.display.setText("— —")
        for label in self.metric_labels.values(): label.setText("—")

    def _update_controls(self) -> None:
        running = self.worker is not None and self.worker.isRunning()
        self.connect_btn.setEnabled(True); self.connect_btn.setText("Desconectar" if running else "Conectar")
        self.resource_combo.setEnabled(not running); self.refresh_btn.setEnabled(not running); self.settings_btn.setEnabled(not running)
        self.continuous_check.setEnabled(self._connected)
        self.channel_combo.setEnabled(True)
        self.capture_btn.setEnabled(self._connected and self.selected_point_id is not None)

    def _show_error(self, text: str) -> None:
        self.error_label.setText(text); self.error_label.show()

    def _clear_error(self) -> None:
        self.error_label.clear(); self.error_label.hide()
