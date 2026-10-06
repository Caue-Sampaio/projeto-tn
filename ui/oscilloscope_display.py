from __future__ import annotations

from typing import Any

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QVBoxLayout, QWidget


class OscilloscopeDisplay(QFrame):
    """Mini tela digital de osciloscópio.

    O widget foi pensado para substituir a antiga área numérica sem mudar a
    posição do ``OscilloscopePanel`` no scanner. O desenho usa pyqtgraph e só
    recebe dados pela thread de aquisição; nenhuma operação VISA é feita aqui.
    """

    start_requested = pyqtSignal()
    pause_requested = pyqtSignal(bool)
    stop_requested = pyqtSignal()
    clear_requested = pyqtSignal()
    channels_changed = pyqtSignal(object)

    # Cores próximas de um osciloscópio real e fáceis de distinguir no fundo escuro.
    CHANNEL_COLORS = {
        1: "#FACC15",  # amarelo
        2: "#22D3EE",  # ciano
        3: "#E879F9",  # magenta
        4: "#22C55E",  # verde
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("miniScope")
        self.setMinimumHeight(270)
        self.setMaximumHeight(340)

        self._paused = False
        self._stopped = False
        self._status_text = "Desconectado"
        self._status_connected = False
        self._status_simulated = False
        self._last_waveforms: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._last_metrics: dict[int, Any] = {}
        self._curves: dict[int, pg.PlotDataItem] = {}
        self._channel_buttons: dict[int, QPushButton] = {}
        self._first_frame = True
        # Base de tempo automática: mantém poucas ondas completas visíveis
        # mesmo quando a frequência sobe. 10 divisões horizontais, escala 1-2-5.
        self._auto_timebase = True
        self._target_cycles = 4.0
        self._last_time_span: float | None = None

        self._build_ui()
        self._apply_style()
        self._configure_plot()
        self._update_overlay()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        self.plot = pg.PlotWidget()
        self.plot.setMinimumHeight(220)
        self.plot.setSizePolicy(self.plot.sizePolicy().horizontalPolicy(), self.plot.sizePolicy().verticalPolicy())
        root.addWidget(self.plot, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(4)

        for ch in range(1, 5):
            btn = QPushButton(f"CH{ch}")
            btn.setObjectName(f"scopeCh{ch}")
            btn.setCheckable(True)
            btn.setChecked(ch == 1)
            btn.setFixedSize(38, 22)
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
            button.setFixedSize(width, 22)
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

    def _configure_plot(self) -> None:
        pg.setConfigOptions(antialias=False)
        self.plot.setBackground("#050B10")
        item = self.plot.getPlotItem()
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

        for ch in range(1, 5):
            curve = item.plot(
                [], [],
                pen=pg.mkPen(self.CHANNEL_COLORS[ch], width=1.35),
                connect="finite",
            )
            curve.setVisible(ch == 1)
            self._curves[ch] = curve

        # Métricas e estado aparecem dentro da área do gráfico, sem consumir
        # uma nova linha do layout.
        self._metrics_overlay = pg.TextItem(anchor=(0, 0), color="#E2E8F0")
        self._status_overlay = pg.TextItem(anchor=(1, 0), color="#94A3B8")
        item.addItem(self._metrics_overlay, ignoreBounds=True)
        item.addItem(self._status_overlay, ignoreBounds=True)
        item.getViewBox().sigRangeChanged.connect(self._position_overlays)

        # Faixa inicial agradável para o modo simulado.
        item.setXRange(0.0, 0.010, padding=0)
        item.setYRange(-3.0, 3.0, padding=0)
        self._position_overlays()

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
        self._update_overlay()

    def active_channels(self) -> list[int]:
        return [ch for ch, btn in self._channel_buttons.items() if btn.isChecked()]

    def set_active_channel(self, channel: int) -> None:
        """Garante que o canal escolhido para captura também esteja visível."""
        channel = max(1, min(int(channel), 4))
        button = self._channel_buttons[channel]
        if not button.isChecked():
            button.setChecked(True)

    # -------------------------------------------------------------- controls
    def set_paused(self, paused: bool, *, emit_signal: bool = False) -> None:
        """Atualiza visualmente o estado de pausa sem depender de clique do usuário.

        Usado pelo painel quando o operador troca de ponto: a forma de onda fica
        congelada enquanto a ponta de prova é reposicionada.
        """
        self._paused = bool(paused)
        if not self._paused:
            self._stopped = False
        self.pause_btn.setText("▶" if self._paused else "⏸")
        if emit_signal:
            self.pause_requested.emit(self._paused)

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

    def _clear(self) -> None:
        for curve in self._curves.values():
            curve.setData([], [])
        self._last_waveforms.clear()
        self._last_metrics.clear()
        self._first_frame = True
        self._last_time_span = None
        self._update_overlay()
        self.clear_requested.emit()

    # --------------------------------------------------------------- status
    def set_status(self, text: str, *, connected: bool = False, simulated: bool = False) -> None:
        self._status_text = text
        self._status_connected = bool(connected)
        self._status_simulated = bool(simulated)
        self._update_overlay()

    # -------------------------------------------------------------- plotting
    def update_frame(self, frame) -> None:
        if self._paused or self._stopped:
            return

        if frame.waveforms:
            self._last_waveforms = frame.waveforms
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
            # O instrumento pode devolver origem absoluta/negativa. Na mini tela
            # usamos sempre o primeiro ponto como t=0 para a curva não "andar".
            x = x - x[0]
            self._last_waveforms[ch] = (x, y)
            curve.setData(x, y)

        self._update_overlay()

        # Ajusta continuamente apenas a BASE DE TEMPO. Isso evita que sinais de
        # frequência alta fiquem comprimidos no mesmo intervalo de 10 ms.
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

    def _update_overlay(self) -> None:
        ch, obj = self._metric_object()
        vpp, vrms, freq = self._extract_metrics(obj)
        color = self.CHANNEL_COLORS.get(ch, "#FACC15")

        self._metrics_overlay.setHtml(
            "<div style='font-family:Consolas;font-size:9px;'>"
            f"<span style='color:{color};font-weight:700;'>CH{ch}</span> &nbsp;"
            f"<span style='color:#94A3B8;'>Vpp</span> <b>{self._fmt_voltage(vpp)}</b> &nbsp;"
            f"<span style='color:#94A3B8;'>Vrms</span> <b>{self._fmt_voltage(vrms)}</b> &nbsp;"
            f"<span style='color:#94A3B8;'>F</span> <b>{self._fmt_freq(freq)}</b>"
            "</div>"
        )

        if self._status_simulated:
            status_color = "#FACC15"
        elif self._status_connected:
            status_color = "#22C55E"
        else:
            status_color = "#64748B"
        self._status_overlay.setHtml(
            "<div style='font-family:Segoe UI;font-size:9px;'>"
            f"<span style='color:{status_color};'>●</span> "
            f"<span style='color:#CBD5E1;'>{self._status_text}</span>"
            "</div>"
        )
        self._position_overlays()

    def _position_overlays(self, *_args) -> None:
        if not hasattr(self, "_metrics_overlay"):
            return
        view = self.plot.getPlotItem().getViewBox()
        (xmin, xmax), (ymin, ymax) = view.viewRange()
        dx = max(1e-12, xmax - xmin)
        dy = max(1e-12, ymax - ymin)
        self._metrics_overlay.setPos(xmin + 0.015 * dx, ymax - 0.04 * dy)
        self._status_overlay.setPos(xmax - 0.015 * dx, ymax - 0.04 * dy)

    @staticmethod
    def _nice_time_per_div(seconds_per_div: float) -> float:
        """Arredonda a escala para a sequência clássica 1-2-5 do osciloscópio."""
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
        """Retorna a frequência válida do primeiro canal ativo com medição."""
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
            if x.size < 2:
                continue
            finite = x[np.isfinite(x)]
            if finite.size < 2:
                continue
            span = float(np.max(finite) - np.min(finite))
            if span > 0:
                spans.append(span)
        return max(spans) if spans else None

    def _apply_frequency_timebase(self) -> None:
        """Ajusta o eixo X à frequência para manter ~4 ciclos na tela.

        A tela tem 10 divisões horizontais. A escala escolhida é arredondada
        para 1-2-5 (ex.: 1 ms/div, 2 ms/div, 5 ms/div, 100 us/div).
        """
        freq = self._active_frequency()
        available = self._available_x_span()
        if freq is None or available is None:
            return

        period = 1.0 / freq
        desired_total = max(period * self._target_cycles, 1e-9)
        per_div = self._nice_time_per_div(desired_total / 10.0)
        visible_span = per_div * 10.0

        # Nunca pede uma janela maior do que o bloco de amostras recebido.
        visible_span = min(visible_span, available)

        # Evita ficar recalculando a faixa por pequenas oscilações de frequência.
        if self._last_time_span is not None:
            delta = abs(visible_span - self._last_time_span) / max(self._last_time_span, 1e-12)
            if delta < 0.08:
                return

        self._last_time_span = visible_span
        self.plot.setXRange(0.0, visible_span, padding=0)

    def _autoset_vertical(self) -> None:
        """Autoescala somente a amplitude, preservando a base de tempo automática."""
        channels = self.active_channels()
        ys: list[np.ndarray] = []
        for ch in channels:
            data = self._last_waveforms.get(ch)
            if data is None:
                continue
            _x, y = data
            if y.size > 1:
                ys.append(y)
        if not ys:
            return

        y_all = np.concatenate(ys)
        finite_y = y_all[np.isfinite(y_all)]
        if finite_y.size < 2:
            return

        ymin, ymax = float(np.min(finite_y)), float(np.max(finite_y))
        yr = max(1e-6, ymax - ymin)
        self.plot.setYRange(ymin - 0.12 * yr, ymax + 0.28 * yr, padding=0)

    def autoset(self) -> None:
        """AUTO: reajusta amplitude e recalcula imediatamente a base de tempo."""
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
