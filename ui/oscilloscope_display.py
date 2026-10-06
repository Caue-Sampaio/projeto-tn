from __future__ import annotations

from typing import Any

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class OscilloscopeDisplay(QFrame):
    """Tela dupla do osciloscópio: referência à esquerda e sinal ao vivo à direita.

    As informações textuais ficam fora da área de plotagem para nunca se
    sobreporem à forma de onda. Quando ainda não há uma onda salva/recebida,
    o gráfico mostra uma linha horizontal contínua em 0 V.
    """

    start_requested = pyqtSignal()
    pause_requested = pyqtSignal(bool)
    stop_requested = pyqtSignal()
    clear_requested = pyqtSignal()
    channels_changed = pyqtSignal(object)

    CHANNEL_COLORS = {
        1: "#FACC15",
        2: "#22D3EE",
        3: "#E879F9",
        4: "#22C55E",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("miniScope")
        self.setMinimumHeight(300)
        self.setMaximumHeight(390)

        self._paused = False
        self._stopped = False
        self._status_text = "Desconectado"
        self._status_connected = False
        self._status_simulated = False

        self._last_waveforms: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._last_metrics: dict[int, Any] = {}
        self._curves: dict[int, pg.PlotDataItem] = {}
        self._channel_buttons: dict[int, QPushButton] = {}

        self._reference_waveform: tuple[np.ndarray, np.ndarray] | None = None
        self._reference_channel = 1
        self._reference_name = ""
        self._waveform_similarity_pct: float | None = None

        self._first_frame = True
        self._auto_timebase = True
        self._target_cycles = 4.0
        self._last_time_span: float | None = None
        self._default_span = 0.010

        self._build_ui()
        self._apply_style()
        self._configure_plots()
        self._show_empty_lines()
        self._update_info_labels()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)

        plots_row = QHBoxLayout()
        plots_row.setContentsMargins(0, 0, 0, 0)
        plots_row.setSpacing(8)

        # REFERÊNCIA -----------------------------------------------------
        ref_box = QFrame()
        ref_box.setObjectName("scopePane")
        ref_layout = QVBoxLayout(ref_box)
        ref_layout.setContentsMargins(6, 5, 6, 5)
        ref_layout.setSpacing(4)

        self.ref_header = QLabel("REFERÊNCIA")
        self.ref_header.setObjectName("scopePaneTitle")
        ref_layout.addWidget(self.ref_header)

        self.reference_plot = pg.PlotWidget()
        self.reference_plot.setMinimumHeight(205)
        ref_layout.addWidget(self.reference_plot, 1)

        self.ref_info = QLabel("Sem forma de onda salva • linha contínua = sem referência")
        self.ref_info.setObjectName("scopePaneInfo")
        self.ref_info.setWordWrap(False)
        ref_layout.addWidget(self.ref_info)

        plots_row.addWidget(ref_box, 1)

        # AO VIVO --------------------------------------------------------
        live_box = QFrame()
        live_box.setObjectName("scopePane")
        live_layout = QVBoxLayout(live_box)
        live_layout.setContentsMargins(6, 5, 6, 5)
        live_layout.setSpacing(4)

        self.live_header = QLabel("AO VIVO • CH1")
        self.live_header.setObjectName("scopePaneTitle")
        live_layout.addWidget(self.live_header)

        self.live_plot = pg.PlotWidget()
        self.live_plot.setMinimumHeight(205)
        live_layout.addWidget(self.live_plot, 1)

        self.live_info = QLabel("Vpp —   •   Vrms —   •   F —   •   Desconectado")
        self.live_info.setObjectName("scopePaneInfo")
        self.live_info.setWordWrap(False)
        live_layout.addWidget(self.live_info)

        plots_row.addWidget(live_box, 1)
        root.addLayout(plots_row, 1)

        # CONTROLES ------------------------------------------------------
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(4)

        for ch in range(1, 5):
            btn = QPushButton(f"CH{ch}")
            btn.setObjectName(f"scopeCh{ch}")
            btn.setCheckable(True)
            btn.setChecked(ch == 1)
            btn.setFixedSize(38, 24)
            btn.setToolTip(f"Mostrar/ocultar canal {ch}")
            btn.toggled.connect(self._emit_channels)
            self._channel_buttons[ch] = btn
            footer.addWidget(btn)

        footer.addStretch(1)

        self.start_btn = QPushButton("▶")
        self.pause_btn = QPushButton("⏸")
        self.stop_btn = QPushButton("⏹")
        self.clear_btn = QPushButton("🧹")
        self.autoset_btn = QPushButton("AUTO")

        controls = (
            (self.start_btn, "Iniciar / continuar aquisição", 26),
            (self.pause_btn, "Pausar aquisição", 26),
            (self.stop_btn, "Parar aquisição", 26),
            (self.clear_btn, "Limpar tela", 28),
            (self.autoset_btn, "Autoescala", 42),
        )
        for button, tooltip, width in controls:
            button.setObjectName("scopeMiniBtn")
            button.setToolTip(tooltip)
            button.setFixedSize(width, 24)
            footer.addWidget(button)

        root.addLayout(footer)

        self.start_btn.clicked.connect(self._start)
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.stop_btn.clicked.connect(self._stop)
        self.clear_btn.clicked.connect(self._clear)
        self.autoset_btn.clicked.connect(self.autoset)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QFrame#miniScope {
                background: #071018;
                border: 1px solid #334155;
                border-radius: 6px;
            }
            QFrame#scopePane {
                background: #08111A;
                border: 1px solid #243244;
                border-radius: 5px;
            }
            QLabel#scopePaneTitle {
                color: #E2E8F0;
                font-size: 10px;
                font-weight: 800;
                padding: 0 2px;
                border: none;
                background: transparent;
            }
            QLabel#scopePaneInfo {
                color: #CBD5E1;
                font-family: Consolas;
                font-size: 9px;
                font-weight: 600;
                padding: 2px 3px;
                border: none;
                background: #0B1622;
                border-radius: 3px;
            }
            QPushButton#scopeMiniBtn {
                background: #111C2A;
                color: #E2E8F0;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 0;
                font-size: 10px;
                font-weight: 700;
            }
            QPushButton#scopeMiniBtn:hover { border-color: #2DD4BF; }
            QPushButton#scopeMiniBtn:pressed { background: #1E293B; }

            QPushButton#scopeCh1, QPushButton#scopeCh2,
            QPushButton#scopeCh3, QPushButton#scopeCh4 {
                background: #111C2A;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 0;
                font-size: 9px;
                font-weight: 800;
            }
            QPushButton#scopeCh1 { color: #FACC15; }
            QPushButton#scopeCh2 { color: #22D3EE; }
            QPushButton#scopeCh3 { color: #E879F9; }
            QPushButton#scopeCh4 { color: #22C55E; }
            QPushButton#scopeCh1:checked { background: #4A4310; border-color: #FACC15; }
            QPushButton#scopeCh2:checked { background: #073947; border-color: #22D3EE; }
            QPushButton#scopeCh3:checked { background: #4A1E50; border-color: #E879F9; }
            QPushButton#scopeCh4:checked { background: #123B24; border-color: #22C55E; }
            """
        )

    def _configure_single_plot(self, plot: pg.PlotWidget) -> pg.PlotItem:
        plot.setBackground("#050B10")
        item = plot.getPlotItem()
        item.showGrid(x=True, y=True, alpha=0.34)
        item.setLabel("left", "V")
        item.setLabel("bottom", "Tempo", units="s")
        item.getAxis("left").setTextPen("#7D8DA3")
        item.getAxis("bottom").setTextPen("#7D8DA3")
        item.getAxis("left").setPen("#334155")
        item.getAxis("bottom").setPen("#334155")
        item.setMenuEnabled(False)
        item.setMouseEnabled(x=True, y=True)
        item.hideButtons()
        item.setXRange(0.0, self._default_span, padding=0)
        item.setYRange(-3.0, 3.0, padding=0)
        return item

    def _configure_plots(self) -> None:
        pg.setConfigOptions(antialias=False)
        self.reference_item = self._configure_single_plot(self.reference_plot)
        self.live_item = self._configure_single_plot(self.live_plot)

        self._reference_curve = self.reference_item.plot(
            [], [], pen=pg.mkPen("#E2E8F0", width=1.65), connect="finite"
        )

        for ch in range(1, 5):
            curve = self.live_item.plot(
                [], [], pen=pg.mkPen(self.CHANNEL_COLORS[ch], width=1.35), connect="finite"
            )
            curve.setVisible(ch == 1)
            self._curves[ch] = curve

    # ------------------------------------------------------------- empty state
    def _current_span(self) -> float:
        return float(self._last_time_span or self._default_span)

    def _flat_line(self, span: float | None = None) -> tuple[np.ndarray, np.ndarray]:
        span = max(float(span or self._current_span()), 1e-9)
        x = np.linspace(0.0, span, 300)
        y = np.zeros_like(x)
        return x, y

    def _show_empty_reference_line(self) -> None:
        if self._reference_waveform is None:
            self._reference_curve.setData(*self._flat_line())

    def _show_empty_live_lines(self) -> None:
        for ch, curve in self._curves.items():
            if ch not in self._last_waveforms:
                curve.setData(*self._flat_line())

    def _show_empty_lines(self) -> None:
        self._show_empty_reference_line()
        self._show_empty_live_lines()

    # -------------------------------------------------------------- channels
    def _emit_channels(self, _checked: bool | None = None) -> None:
        channels = self.active_channels()
        if not channels:
            btn = self._channel_buttons[1]
            btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(False)
            channels = [1]

        for ch, curve in self._curves.items():
            curve.setVisible(ch in channels)
        self.channels_changed.emit(channels)
        self._update_info_labels()

    def active_channels(self) -> list[int]:
        return [ch for ch, btn in self._channel_buttons.items() if btn.isChecked()]

    def set_active_channel(self, channel: int) -> None:
        channel = max(1, min(int(channel), 4))
        button = self._channel_buttons[channel]
        if not button.isChecked():
            button.setChecked(True)
        self._update_info_labels()

    # -------------------------------------------------------------- controls
    def set_paused(self, paused: bool, *, emit_signal: bool = False) -> None:
        self._paused = bool(paused)
        if not self._paused:
            self._stopped = False
        self.pause_btn.setText("▶" if self._paused else "⏸")
        if emit_signal:
            self.pause_requested.emit(self._paused)
        self._update_info_labels()

    def _start(self) -> None:
        self._stopped = False
        if self._paused:
            self.set_paused(False, emit_signal=True)
        self.start_requested.emit()

    def _toggle_pause(self) -> None:
        self._stopped = False
        self.set_paused(not self._paused, emit_signal=True)

    def _stop(self) -> None:
        self._stopped = True
        self.set_paused(True, emit_signal=False)
        self.stop_requested.emit()
        self._update_info_labels()

    def _clear(self) -> None:
        self._last_waveforms.clear()
        self._last_metrics.clear()
        self._first_frame = True
        self._last_time_span = None
        self._show_empty_lines()
        self._update_info_labels()
        self.clear_requested.emit()

    # --------------------------------------------------------------- status
    def set_status(self, text: str, *, connected: bool = False, simulated: bool = False) -> None:
        self._status_text = text
        self._status_connected = bool(connected)
        self._status_simulated = bool(simulated)
        self._update_info_labels()

    # -------------------------------------------------------------- plotting
    def update_frame(self, frame) -> None:
        if self._paused or self._stopped:
            return

        if frame.readings:
            self._last_metrics.update(frame.readings)

        for ch, (x, y) in (frame.waveforms or {}).items():
            curve = self._curves.get(ch)
            if curve is None:
                continue
            x = np.asarray(x, dtype=float)
            y = np.asarray(y, dtype=float)
            size = min(x.size, y.size)
            if size <= 1:
                continue
            x = x[:size]
            y = y[:size]
            x = x - x[0]
            self._last_waveforms[ch] = (x, y)
            curve.setData(x, y)

        self._update_reference_comparison()
        self._update_info_labels()

        if self._auto_timebase and self._last_waveforms:
            self._apply_frequency_timebase()

        if self._first_frame and self._last_waveforms:
            self._first_frame = False
            self._autoset_vertical()

    def _metric_object(self):
        channels = self.active_channels()
        for ch in channels:
            obj = self._last_metrics.get(ch)
            if obj is not None:
                return ch, obj
        return (channels[0] if channels else 1), None

    def _extract_metrics(self, obj) -> tuple[float | None, float | None, float | None]:
        if obj is None:
            return None, None, None
        if isinstance(obj, dict):
            return obj.get("vpp"), obj.get("vrms"), obj.get("freq")
        return (
            getattr(obj, "vpp_v", None),
            getattr(obj, "vrms_v", None),
            getattr(obj, "frequency_hz", None),
        )

    def _update_info_labels(self) -> None:
        # Referência
        if self._reference_waveform is None:
            self.ref_header.setText("REFERÊNCIA")
            self.ref_info.setText("Sem onda salva • linha contínua = referência vazia")
            self.ref_info.setStyleSheet("color:#94A3B8;")
        else:
            similarity = "—" if self._waveform_similarity_pct is None else f"{self._waveform_similarity_pct:.1f}%"
            name = self._reference_name or "Ponto selecionado"
            self.ref_header.setText(f"REFERÊNCIA • {name}")
            self.ref_info.setText(f"Similaridade da forma: {similarity}")
            if self._waveform_similarity_pct is None:
                color = "#CBD5E1"
            elif self._waveform_similarity_pct >= 90:
                color = "#22C55E"
            elif self._waveform_similarity_pct >= 75:
                color = "#FACC15"
            else:
                color = "#EF4444"
            self.ref_info.setStyleSheet(f"color:{color};")

        # Ao vivo
        ch, obj = self._metric_object()
        vpp, vrms, freq = self._extract_metrics(obj)
        state = "PAUSADO" if self._paused else ("PARADO" if self._stopped else "AO VIVO")
        self.live_header.setText(f"{state} • CH{ch}")

        if self._status_simulated:
            status = f"SIMULANDO • {self._status_text}"
        elif self._status_connected:
            status = f"CONECTADO • {self._status_text}"
        else:
            status = self._status_text

        self.live_info.setText(
            f"Vpp {self._fmt_voltage(vpp)}   •   "
            f"Vrms {self._fmt_voltage(vrms)}   •   "
            f"F {self._fmt_freq(freq)}   •   {status}"
        )

    # ------------------------------------------------------ waveform reference
    @staticmethod
    def _waveform_arrays(waveform) -> tuple[np.ndarray, np.ndarray] | None:
        if not isinstance(waveform, dict):
            return None
        try:
            x = np.asarray(waveform.get("x_s") or [], dtype=float)
            y = np.asarray(waveform.get("y_v") or [], dtype=float)
        except Exception:
            return None
        size = min(x.size, y.size)
        if size < 8:
            return None
        x = x[:size]
        y = y[:size]
        mask = np.isfinite(x) & np.isfinite(y)
        x, y = x[mask], y[mask]
        if x.size < 8:
            return None
        x = x - x[0]
        return x, y

    def set_reference_waveform(self, waveform, *, channel: int = 1, name: str = "") -> bool:
        parsed = self._waveform_arrays(waveform)
        if parsed is None:
            self.clear_reference_waveform()
            return False
        self._reference_waveform = parsed
        self._reference_channel = max(1, min(int(channel), 4))
        self._reference_name = str(name or "")
        self._reference_curve.setData(*parsed)
        self._update_reference_comparison()
        self._sync_reference_ranges()
        self._update_info_labels()
        return True

    def clear_reference_waveform(self) -> None:
        self._reference_waveform = None
        self._reference_name = ""
        self._waveform_similarity_pct = None
        self._show_empty_reference_line()
        self._update_info_labels()

    def current_waveform(self, channel: int | None = None) -> dict[str, Any] | None:
        channel = int(channel or self._reference_channel or 1)
        data = self._last_waveforms.get(channel)
        if data is None:
            return None
        x, y = data
        if x.size < 2 or y.size < 2:
            return None
        return {
            "x_s": [float(v) for v in x.tolist()],
            "y_v": [float(v) for v in y.tolist()],
            "points": int(min(x.size, y.size)),
            "source": "live_display",
        }

    @staticmethod
    def _shape_similarity(reference, measured) -> float | None:
        if reference is None or measured is None:
            return None
        rx, ry = reference
        mx, my = measured
        if rx.size < 16 or mx.size < 16:
            return None
        n = int(min(400, rx.size, mx.size))
        if n < 16:
            return None

        def resample(x, y):
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

        a = resample(rx, ry)
        b = resample(mx, my)
        if a is None or b is None:
            return None
        corr = np.correlate(np.r_[b, b], a, mode="valid") / float(n)
        if corr.size == 0:
            return None
        best = float(np.max(corr))
        return max(0.0, min(100.0, best * 100.0))

    def _update_reference_comparison(self) -> None:
        if self._reference_waveform is None:
            self._waveform_similarity_pct = None
            return
        measured = self._last_waveforms.get(self._reference_channel)
        self._waveform_similarity_pct = self._shape_similarity(self._reference_waveform, measured)

    def waveform_similarity(self, channel: int | None = None) -> float | None:
        if channel is not None and int(channel) != self._reference_channel:
            return None
        return self._waveform_similarity_pct

    # ------------------------------------------------------------- scaling
    @staticmethod
    def _nice_time_per_div(seconds_per_div: float) -> float:
        if not np.isfinite(seconds_per_div) or seconds_per_div <= 0:
            return 1e-3
        exponent = float(np.floor(np.log10(seconds_per_div)))
        base = 10.0 ** exponent
        normalized = seconds_per_div / base
        if normalized <= 1.0:
            nice = 1.0
        elif normalized <= 2.0:
            nice = 2.0
        elif normalized <= 5.0:
            nice = 5.0
        else:
            nice = 10.0
        return nice * base

    def _active_frequency(self) -> float | None:
        for ch in self.active_channels():
            obj = self._last_metrics.get(ch)
            _vpp, _vrms, freq = self._extract_metrics(obj)
            if freq is None:
                continue
            try:
                value = float(freq)
            except (TypeError, ValueError):
                continue
            if np.isfinite(value) and value > 0:
                return value
        return None

    def _available_x_span(self) -> float | None:
        spans: list[float] = []
        for ch in self.active_channels():
            data = self._last_waveforms.get(ch)
            if data is None:
                continue
            x, _y = data
            if x.size >= 2:
                span = float(np.max(x) - np.min(x))
                if np.isfinite(span) and span > 0:
                    spans.append(span)
        if self._reference_waveform is not None:
            rx, _ = self._reference_waveform
            if rx.size >= 2:
                span = float(np.max(rx) - np.min(rx))
                if np.isfinite(span) and span > 0:
                    spans.append(span)
        return max(spans) if spans else self._default_span

    def _set_x_range_both(self, visible_span: float) -> None:
        visible_span = max(float(visible_span), 1e-9)
        self.live_plot.setXRange(0.0, visible_span, padding=0)
        self.reference_plot.setXRange(0.0, visible_span, padding=0)
        self._show_empty_lines()

    def _apply_frequency_timebase(self) -> None:
        freq = self._active_frequency()
        available = self._available_x_span()
        if freq is None or available is None:
            return
        period = 1.0 / freq
        desired_total = max(period * self._target_cycles, 1e-9)
        per_div = self._nice_time_per_div(desired_total / 10.0)
        visible_span = min(per_div * 10.0, available)
        if self._last_time_span is not None:
            delta = abs(visible_span - self._last_time_span) / max(self._last_time_span, 1e-12)
            if delta < 0.08:
                return
        self._last_time_span = visible_span
        self._set_x_range_both(visible_span)

    def _sync_reference_ranges(self) -> None:
        if self._last_time_span is not None:
            self._set_x_range_both(self._last_time_span)
        self._autoset_vertical()

    def _autoset_vertical(self) -> None:
        ys: list[np.ndarray] = []
        for ch in self.active_channels():
            data = self._last_waveforms.get(ch)
            if data is not None and data[1].size > 1:
                ys.append(data[1])
        if self._reference_waveform is not None and self._reference_waveform[1].size > 1:
            ys.append(self._reference_waveform[1])

        # Sem onda real, mantém uma escala útil ao redor da linha de 0 V.
        if not ys:
            self.live_plot.setYRange(-1.0, 1.0, padding=0)
            self.reference_plot.setYRange(-1.0, 1.0, padding=0)
            return

        y_all = np.concatenate(ys)
        finite_y = y_all[np.isfinite(y_all)]
        if finite_y.size < 2:
            return
        ymin, ymax = float(np.min(finite_y)), float(np.max(finite_y))
        yr = max(1e-6, ymax - ymin)
        low = ymin - 0.12 * yr
        high = ymax + 0.22 * yr
        self.live_plot.setYRange(low, high, padding=0)
        self.reference_plot.setYRange(low, high, padding=0)

    def autoset(self) -> None:
        self._last_time_span = None
        self._apply_frequency_timebase()
        self._autoset_vertical()

    @staticmethod
    def _fmt_voltage(value: float | None) -> str:
        if value is None:
            return "—"
        value = float(value)
        if abs(value) < 1.0:
            return f"{value * 1e3:.2f} mV"
        return f"{value:.3g} V"

    @staticmethod
    def _fmt_freq(value: float | None) -> str:
        if value is None:
            return "—"
        value = float(value)
        if abs(value) >= 1e6:
            return f"{value / 1e6:.3g} MHz"
        if abs(value) >= 1e3:
            return f"{value / 1e3:.3g} kHz"
        return f"{value:.3g} Hz"
