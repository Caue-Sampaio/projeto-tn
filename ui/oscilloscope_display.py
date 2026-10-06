from __future__ import annotations

import math
from typing import Any

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class OscilloscopeDisplay(QFrame):
    """Mini osciloscópio virtual para PyQt6 + pyqtgraph."""

    start_requested = pyqtSignal()
    pause_requested = pyqtSignal(bool)
    stop_requested = pyqtSignal()
    clear_requested = pyqtSignal()
    channels_changed = pyqtSignal(object)

    CHANNEL_COLORS = {
        1: "#2DD4BF",  # teal
        2: "#FACC15",  # amarelo
        3: "#38BDF8",  # ciano
        4: "#E879F9",  # magenta
    }
    VDIV_VALUES = [0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0]
    TDIV_VALUES = [1e-6, 2e-6, 5e-6, 10e-6, 20e-6, 50e-6, 100e-6, 200e-6, 500e-6,
                   1e-3, 2e-3, 5e-3, 10e-3, 20e-3, 50e-3, 100e-3, 200e-3, 500e-3, 1.0]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("miniScope")
        self._paused = False
        self._last_waveforms: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._last_metrics: dict[int, Any] = {}
        self._curves: dict[int, pg.PlotDataItem] = {}
        self._build_ui()
        self._apply_style()
        self._configure_plot()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel("OSCILOSCÓPIO")
        title.setObjectName("scopeTitle")
        top.addWidget(title)
        top.addStretch()
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("scopeStatusDot")
        self.status_label = QLabel("Desconectado")
        self.status_label.setObjectName("scopeStatus")
        top.addWidget(self.status_dot)
        top.addWidget(self.status_label)
        root.addLayout(top)

        channel_row = QHBoxLayout()
        channel_row.addWidget(QLabel("Canais:"))
        self.channel_checks: dict[int, QCheckBox] = {}
        for ch in range(1, 5):
            check = QCheckBox(f"CH{ch}")
            check.setChecked(ch == 1)
            check.stateChanged.connect(self._emit_channels)
            check.setStyleSheet(f"QCheckBox {{ color: {self.CHANNEL_COLORS[ch]}; font-weight: 700; }}")
            self.channel_checks[ch] = check
            channel_row.addWidget(check)
        channel_row.addStretch()
        root.addLayout(channel_row)

        self.plot = pg.PlotWidget()
        self.plot.setMinimumHeight(260)
        root.addWidget(self.plot, 1)

        controls = QHBoxLayout()
        self.start_btn = QPushButton("▶ Iniciar")
        self.pause_btn = QPushButton("⏸ Pausar")
        self.stop_btn = QPushButton("⏹ Parar")
        self.clear_btn = QPushButton("🧹 Limpar")
        self.autoset_btn = QPushButton("AUTOSET")
        controls.addWidget(self.start_btn)
        controls.addWidget(self.pause_btn)
        controls.addWidget(self.stop_btn)
        controls.addWidget(self.clear_btn)
        controls.addWidget(self.autoset_btn)
        controls.addStretch()
        root.addLayout(controls)

        scales = QGridLayout()
        scales.setHorizontalSpacing(10)
        scales.setVerticalSpacing(4)
        scales.addWidget(QLabel("V/div"), 0, 0)
        self.vdiv_slider = QSlider(Qt.Orientation.Horizontal)
        self.vdiv_slider.setRange(0, len(self.VDIV_VALUES) - 1)
        self.vdiv_slider.setValue(self.VDIV_VALUES.index(1.0))
        self.vdiv_label = QLabel("1 V/div")
        self.vdiv_label.setObjectName("scopeScale")
        scales.addWidget(self.vdiv_slider, 0, 1)
        scales.addWidget(self.vdiv_label, 0, 2)

        scales.addWidget(QLabel("Tempo/div"), 1, 0)
        self.tdiv_slider = QSlider(Qt.Orientation.Horizontal)
        self.tdiv_slider.setRange(0, len(self.TDIV_VALUES) - 1)
        self.tdiv_slider.setValue(self.TDIV_VALUES.index(1e-3))
        self.tdiv_label = QLabel("1 ms/div")
        self.tdiv_label.setObjectName("scopeScale")
        scales.addWidget(self.tdiv_slider, 1, 1)
        scales.addWidget(self.tdiv_label, 1, 2)
        root.addLayout(scales)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(18)
        self.metric_labels: dict[str, QLabel] = {}
        for i, name in enumerate(("Vpp", "Vrms", "Frequência")):
            key = name.lower()
            title_lbl = QLabel(name)
            title_lbl.setObjectName("metricName")
            value_lbl = QLabel("—")
            value_lbl.setObjectName("metricValue")
            metrics.addWidget(title_lbl, 0, i * 2)
            metrics.addWidget(value_lbl, 0, i * 2 + 1)
            self.metric_labels[key] = value_lbl
        root.addLayout(metrics)

        self.start_btn.clicked.connect(self.start_requested.emit)
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        self.clear_btn.clicked.connect(self._clear)
        self.autoset_btn.clicked.connect(self.autoset)
        self.vdiv_slider.valueChanged.connect(self._apply_manual_scale)
        self.tdiv_slider.valueChanged.connect(self._apply_manual_scale)

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QFrame#miniScope {
                background: #0F172A;
                border: 1px solid #334155;
                border-radius: 10px;
            }
            QLabel { color: #CBD5E1; font-size: 10px; }
            QLabel#scopeTitle { color: #2DD4BF; font-size: 13px; font-weight: 900; }
            QLabel#scopeStatus { color: #CBD5E1; font-weight: 700; }
            QLabel#scopeStatusDot { color: #64748B; font-size: 13px; }
            QLabel#scopeScale, QLabel#metricValue {
                color: #F8FAFC; font-family: Consolas, monospace; font-weight: 700;
            }
            QLabel#metricName { color: #64748B; font-weight: 700; }
            QPushButton {
                background: #172033;
                color: #E2E8F0;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: 700;
            }
            QPushButton:hover { border-color: #2DD4BF; }
            QPushButton:pressed { background: #1E293B; }
            QSlider::groove:horizontal { height: 4px; background: #334155; border-radius: 2px; }
            QSlider::handle:horizontal { width: 13px; margin: -5px 0; border-radius: 6px; background: #2DD4BF; }
        """)

    def _configure_plot(self) -> None:
        pg.setConfigOptions(antialias=False)
        self.plot.setBackground("#0B1220")
        item = self.plot.getPlotItem()
        item.showGrid(x=True, y=True, alpha=0.28)
        item.setLabel("left", "Tensão", units="V")
        item.setLabel("bottom", "Tempo", units="s")
        item.getAxis("left").setTextPen("#94A3B8")
        item.getAxis("bottom").setTextPen("#94A3B8")
        item.setMenuEnabled(True)
        item.setMouseEnabled(x=True, y=True)  # zoom e pan nativos
        for ch in range(1, 5):
            curve = item.plot([], [], pen=pg.mkPen(self.CHANNEL_COLORS[ch], width=1.6), name=f"CH{ch}")
            curve.setVisible(ch == 1)
            self._curves[ch] = curve

    def _emit_channels(self) -> None:
        channels = [ch for ch, check in self.channel_checks.items() if check.isChecked()]
        if not channels:
            self.channel_checks[1].blockSignals(True)
            self.channel_checks[1].setChecked(True)
            self.channel_checks[1].blockSignals(False)
            channels = [1]
        for ch, curve in self._curves.items():
            curve.setVisible(ch in channels)
        self.channels_changed.emit(channels)
        self._update_metrics_display()

    def active_channels(self) -> list[int]:
        return [ch for ch, c in self.channel_checks.items() if c.isChecked()]

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.pause_btn.setText("▶ Continuar" if self._paused else "⏸ Pausar")
        self.pause_requested.emit(self._paused)

    def set_status(self, text: str, connected: bool = False, simulated: bool = False) -> None:
        self.status_label.setText(text)
        if simulated:
            color = "#FACC15"
        elif connected:
            color = "#22C55E"
        else:
            color = "#64748B"
        self.status_dot.setStyleSheet(f"color: {color};")

    def update_frame(self, frame) -> None:
        if self._paused:
            return
        self._last_waveforms = frame.waveforms or self._last_waveforms
        self._last_metrics = frame.readings or self._last_metrics
        for ch, (x, y) in frame.waveforms.items():
            curve = self._curves.get(ch)
            if curve is not None and x.size and y.size:
                # pyqtgraph é mais eficiente com numpy e setData, sem recriar curva.
                curve.setData(x, y, connect="finite")
        self._update_metrics_display()

    def _current_metric_object(self):
        channels = self.active_channels()
        ch = channels[0] if channels else 1
        return self._last_metrics.get(ch)

    def _update_metrics_display(self) -> None:
        obj = self._current_metric_object()
        if obj is None:
            return
        if isinstance(obj, dict):
            vpp = obj.get("vpp")
            vrms = obj.get("vrms")
            freq = obj.get("freq")
        else:
            vpp = getattr(obj, "vpp_v", None)
            vrms = getattr(obj, "vrms_v", None)
            freq = getattr(obj, "frequency_hz", None)
        self.metric_labels["vpp"].setText("—" if vpp is None else f"{vpp:.4g} V")
        self.metric_labels["vrms"].setText("—" if vrms is None else f"{vrms:.4g} V")
        self.metric_labels["frequência"].setText(self._fmt_freq(freq))

    @staticmethod
    def _fmt_freq(value: float | None) -> str:
        if value is None:
            return "—"
        if abs(value) >= 1e6:
            return f"{value/1e6:.3f} MHz"
        if abs(value) >= 1e3:
            return f"{value/1e3:.3f} kHz"
        return f"{value:.3f} Hz"

    def _clear(self) -> None:
        for curve in self._curves.values():
            curve.setData([], [])
        self._last_waveforms.clear()
        self._last_metrics.clear()
        for lbl in self.metric_labels.values():
            lbl.setText("—")
        self.clear_requested.emit()

    @staticmethod
    def _fmt_time_div(value: float) -> str:
        if value < 1e-3:
            return f"{value*1e6:g} µs/div"
        if value < 1:
            return f"{value*1e3:g} ms/div"
        return f"{value:g} s/div"

    def _apply_manual_scale(self) -> None:
        vdiv = self.VDIV_VALUES[self.vdiv_slider.value()]
        tdiv = self.TDIV_VALUES[self.tdiv_slider.value()]
        self.vdiv_label.setText(f"{vdiv:g} V/div")
        self.tdiv_label.setText(self._fmt_time_div(tdiv))
        # 8 divisões verticais e 10 horizontais.
        self.plot.setYRange(-4.0 * vdiv, 4.0 * vdiv, padding=0)
        x_max = 10.0 * tdiv
        self.plot.setXRange(0.0, x_max, padding=0)

    def autoset(self) -> None:
        channels = self.active_channels()
        xs, ys = [], []
        for ch in channels:
            if ch in self._last_waveforms:
                x, y = self._last_waveforms[ch]
                if x.size:
                    xs.append(x)
                if y.size:
                    ys.append(y)
        if not xs or not ys:
            return
        x_all = np.concatenate(xs)
        y_all = np.concatenate(ys)
        if not x_all.size or not y_all.size:
            return
        ymin, ymax = float(np.min(y_all)), float(np.max(y_all))
        xmin, xmax = float(np.min(x_all)), float(np.max(x_all))
        yr = max(1e-6, ymax - ymin)
        xr = max(1e-9, xmax - xmin)
        self.plot.setYRange(ymin - 0.08 * yr, ymax + 0.08 * yr, padding=0)
        self.plot.setXRange(xmin, xmax, padding=0)
