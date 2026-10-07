# ui/image_marker.py
# ──────────────────────────────────────────────────────────────────
# Redesign: Dark-mode professional UI for PCB test-point mapping.
# Style inspired by Altium Designer / KiCad / EasyEDA.
# ──────────────────────────────────────────────────────────────────
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QLineEdit,
    QFormLayout, QTextEdit, QMessageBox, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsTextItem,
    QComboBox, QSlider, QDialog, QDialogButtonBox, QSplitter, QFrame,
    QTabWidget, QMenu, QTableWidget, QTableWidgetItem, QHeaderView,
    QSpinBox, QInputDialog, QGraphicsDropShadowEffect, QGroupBox,
    QProgressBar, QListWidget, QListWidgetItem, QSizePolicy, QScrollArea,
    QGraphicsRectItem, QColorDialog, QApplication
)
from PyQt6.QtGui import (
    QPixmap, QColor, QPen, QBrush, QWheelEvent, QFont, QPainter,
    QAction, QDoubleValidator, QLinearGradient, QRadialGradient
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QPointF, QRectF, QTimer, QPropertyAnimation,
    QEasingCurve
)
from db.models import TestPoint, BoardUnit, Measurement, OscilloscopeCapture, OscilloscopeReference
from sqlalchemy.orm import Session
from ui.oscilloscope_panel import OscilloscopePanel
from ui.marker_graphics import build_marker_path, normalize_marker_shape, normalize_marker_size, MarkerAppearanceDialog
from oscilloscope.base import OscilloscopeReading
import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# DESIGN TOKENS
# ══════════════════════════════════════════════════════════════════
class Theme:
    """Centralized design tokens for the engineering UI."""

    # Backgrounds
    BG_PRIMARY     = "#0F1419"
    BG_SURFACE     = "#1A1F2E"
    BG_SURFACE_ALT = "#232A3B"
    BG_INPUT       = "#2A3142"
    BG_HOVER       = "#2E3A4E"
    BG_CANVAS      = "#0D1117"

    # Borders
    BORDER_SUBTLE  = "#2E3650"
    BORDER_FOCUS   = "#0EA5E9"
    BORDER_MUTED   = "#1E293B"

    # Text
    TEXT_PRIMARY   = "#E2E8F0"
    TEXT_SECONDARY = "#94A3B8"
    TEXT_MUTED     = "#64748B"
    TEXT_BRIGHT    = "#F8FAFC"

    # Accents
    ACCENT_CYAN    = "#00D4FF"
    ACCENT_BLUE    = "#0EA5E9"

    # Semantic
    VCC_GREEN      = "#22C55E"
    GND_GRAY       = "#64748B"
    SIGNAL_CYAN    = "#06B6D4"
    CLOCK_PURPLE   = "#A78BFA"
    ALERT_AMBER    = "#F59E0B"
    ERROR_RED      = "#EF4444"

    # Todo ponto novo nasce vermelho; a escolha individual fica persistida no DB.
    DEFAULT_POINT_COLOR = "#E53935"

    # Mantido apenas para rótulo/tipagem visual; a cor real vem de marker_color.
    # Type -> color mapping for test points
    POINT_COLORS = {
        "VCC":    "#22C55E",
        "GND":    "#64748B",
        "SIGNAL": "#06B6D4",
        "CLOCK":  "#A78BFA",
        "POWER":  "#F59E0B",
        "OTHER":  "#0EA5E9",
    }

    @staticmethod
    def point_color(refdes: str, voltage: float | None = None) -> str:
        """Determine point color from refdes name or voltage."""
        name = (refdes or "").upper()
        if "VCC" in name or "VDD" in name or "3V3" in name or "5V" in name or "12V" in name:
            return Theme.POINT_COLORS["VCC"]
        if "GND" in name or "VSS" in name or "COM" in name:
            return Theme.POINT_COLORS["GND"]
        if "CLK" in name or "CLOCK" in name or "OSC" in name:
            return Theme.POINT_COLORS["CLOCK"]
        if "SIG" in name or "DAT" in name or "TX" in name or "RX" in name:
            return Theme.POINT_COLORS["SIGNAL"]
        if voltage is not None and voltage > 1.0:
            return Theme.POINT_COLORS["POWER"]
        return Theme.POINT_COLORS["OTHER"]

    @staticmethod
    def point_type_label(refdes: str, voltage: float | None = None) -> str:
        """Return a human-readable type label."""
        name = (refdes or "").upper()
        if "VCC" in name or "VDD" in name or "3V3" in name or "5V" in name or "12V" in name:
            return "VCC"
        if "GND" in name or "VSS" in name or "COM" in name:
            return "GND"
        if "CLK" in name or "CLOCK" in name or "OSC" in name:
            return "CLOCK"
        if "SIG" in name or "DAT" in name or "TX" in name or "RX" in name:
            return "SIGNAL"
        if voltage is not None and voltage > 1.0:
            return "POWER"
        return "SIGNAL"


# ══════════════════════════════════════════════════════════════════
# TEST POINT GRAPHICS ITEM
# ══════════════════════════════════════════════════════════════════
class TestPointItem(QGraphicsPathItem):
    """Marcador interativo com formato e tamanho persistidos por ponto."""

    def __init__(self, tp: TestPoint, marker_widget):
        super().__init__()
        self.tp = tp
        self.marker_widget = marker_widget
        self._selected = False
        self._zoom_level = 1.0

        color_hex = getattr(tp, "marker_color", None) or Theme.DEFAULT_POINT_COLOR
        self._color = QColor(color_hex)
        self._color_hover = QColor(color_hex)
        self._color_hover.setAlpha(255)
        self._color_base = QColor(color_hex)
        self._color_base.setAlpha(200)
        self.base_size = normalize_marker_size(getattr(tp, "marker_size", None))
        self.marker_shape = normalize_marker_shape(getattr(tp, "marker_shape", None))

        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        self.label = QGraphicsTextItem(tp.refdes, self)
        self.label.setDefaultTextColor(QColor(Theme.TEXT_PRIMARY))
        self.label.setFont(QFont("Consolas", 7, QFont.Weight.Bold))

        self.setPos(tp.x, tp.y)
        self.refresh_appearance()
        self.update_tooltip()

    def refresh_appearance(self):
        self.base_size = normalize_marker_size(getattr(self.tp, "marker_size", None))
        self.marker_shape = normalize_marker_shape(getattr(self.tp, "marker_shape", None))
        color_hex = getattr(self.tp, "marker_color", None) or Theme.DEFAULT_POINT_COLOR
        self._color = QColor(color_hex)
        self._color_hover = QColor(color_hex)
        self._color_hover.setAlpha(255)
        self._color_base = QColor(color_hex)
        self._color_base.setAlpha(200)
        self.update_size_based_on_zoom(self._zoom_level)
        self.set_selected_style(self._selected)
        self.update_tooltip()

    def update_tooltip(self):
        tooltip_lines = [f"{self.tp.refdes}"]
        tooltip_lines.append(
            f"Marcador: {self.marker_shape} • {self.base_size}px"
        )
        if self.tp.expected_voltage_v is not None:
            tooltip_lines.append(f"Esperado: {self.tp.expected_voltage_v:.4g} V")
        if getattr(self.tp, "last_scope_vpp_v", None) is not None:
            ch = getattr(self.tp, "last_scope_channel", None)
            prefix = f"CH{ch} • " if ch else ""
            tooltip_lines.append(f"Osciloscópio: {prefix}{self.tp.last_scope_vpp_v:.6g} Vpp")
            vrms = getattr(self.tp, "last_scope_vrms_v", None)
            if vrms is not None:
                tooltip_lines.append(f"Vrms: {vrms:.6g} V")
            freq = getattr(self.tp, "last_scope_frequency_hz", None)
            if freq is not None:
                tooltip_lines.append(f"Frequência: {freq:.6g} Hz")
            captured_at = getattr(self.tp, "last_scope_at", None)
            if captured_at is not None:
                tooltip_lines.append(f"Capturada: {captured_at.strftime('%d/%m/%Y %H:%M:%S')}")
        if self.tp.tolerance_voltage_v is not None:
            tooltip_lines.append(f"Tolerância: +/-{self.tp.tolerance_voltage_v:.4g} V")
        tooltip_lines.append(f"Pos: ({self.tp.x}, {self.tp.y})")
        self.setToolTip("\n".join(tooltip_lines))

    def update_label_position(self):
        text_rect = self.label.boundingRect()
        bounds = self.path().boundingRect()
        self.label.setPos(-text_rect.width() / 2, bounds.top() - text_rect.height() - 4)

    def update_size_based_on_zoom(self, zoom_level):
        self._zoom_level = max(0.05, float(zoom_level or 1.0))
        new_size = max(5.0, self.base_size / self._zoom_level)
        self.setPath(build_marker_path(self.marker_shape, new_size))
        font_size = max(5, int(7 / self._zoom_level))
        self.label.setFont(QFont("Consolas", font_size, QFont.Weight.Bold))
        self.update_label_position()

    def set_selected_style(self, selected: bool):
        self._selected = bool(selected)
        if selected:
            self.setPen(QPen(QColor(Theme.ACCENT_CYAN), 3))
            bright = QColor(self._color.name())
            bright.setAlpha(255)
            self.setBrush(QBrush(bright))
        else:
            self.setPen(QPen(QColor(self._color.name()), 2))
            self.setBrush(QBrush(self._color_base))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.marker_widget.select_point(self.tp)
        elif event.button() == Qt.MouseButton.RightButton:
            self.marker_widget.show_point_context_menu(self.tp, event.screenPos())
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        # A posição do item é a coordenada real do ponto, independentemente do
        # formato (inclusive seta, cujo desenho não é geometricamente simétrico).
        p = self.pos()
        self.tp.x = int(round(p.x()))
        self.tp.y = int(round(p.y()))
        self.marker_widget.session.add(self.tp)
        self.marker_widget.session.commit()
        self.update_label_position()
        logger.debug(f"Ponto {self.tp.refdes} movido para ({self.tp.x}, {self.tp.y})")
        super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event):
        if not self._selected:
            self.setPen(QPen(QColor(Theme.ACCENT_CYAN), 2))
            self.setBrush(QBrush(self._color_hover))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self._selected:
            self.setPen(QPen(QColor(self._color.name()), 2))
            self.setBrush(QBrush(self._color_base))
        super().hoverLeaveEvent(event)


# ══════════════════════════════════════════════════════════════════
# ZOOMABLE GRAPHICS VIEW
# ══════════════════════════════════════════════════════════════════
class ZoomableGraphicsView(QGraphicsView):
    """QGraphicsView with zoom, drag, grid overlay and point-add support."""

    point_add_request = pyqtSignal(float, float)
    zoom_changed = pyqtSignal(float)
    mouse_moved = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setScene(QGraphicsScene(self))
        self.pixmap_item = None
        self.marker_widget = None
        self.zoom_level = 1.0
        self.max_zoom = 5.0
        self.min_zoom = 0.1
        self.show_grid = True
        self._grid_lines = []

        # Dark canvas background
        self.setBackgroundBrush(QBrush(QColor(Theme.BG_CANVAS)))
        self.setStyleSheet(f"""
            QGraphicsView {{
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 8px;
                background: {Theme.BG_CANVAS};
            }}
        """)

    def load_image(self, path):
        pix = QPixmap(path)
        if pix.isNull():
            logger.error(f"Falha ao carregar imagem: {path}")
            return False

        self.scene().clear()
        self._grid_lines = []
        self.pixmap_item = QGraphicsPixmapItem(pix)
        self.pixmap_item.setPos(0, 0)
        self.scene().addItem(self.pixmap_item)
        self.setSceneRect(self.pixmap_item.boundingRect())

        self.zoom_level = 1.0
        self.resetTransform()

        if self.show_grid:
            self._draw_grid()

        logger.info(f"Imagem carregada: {path} ({pix.width()}x{pix.height()})")
        return True

    def _draw_grid(self):
        """Draw a subtle grid overlay on the canvas."""
        # Remove existing grid
        for item in self._grid_lines:
            if item.scene():
                self.scene().removeItem(item)
        self._grid_lines = []

        if not self.pixmap_item:
            return

        rect = self.pixmap_item.boundingRect()
        grid_size = 50
        pen = QPen(QColor(Theme.TEXT_MUTED))
        pen.setWidth(0)
        pen.setStyle(Qt.PenStyle.DotLine)
        pen.setColor(QColor(100, 116, 139, 30))

        # Vertical lines
        x = 0
        while x <= rect.width():
            line = self.scene().addLine(x, 0, x, rect.height(), pen)
            line.setZValue(-1)
            self._grid_lines.append(line)
            x += grid_size

        # Horizontal lines
        y = 0
        while y <= rect.height():
            line = self.scene().addLine(0, y, rect.width(), y, pen)
            line.setZValue(-1)
            self._grid_lines.append(line)
            y += grid_size

    def toggle_grid(self, show: bool):
        self.show_grid = show
        if show:
            self._draw_grid()
        else:
            for item in self._grid_lines:
                if item.scene():
                    self.scene().removeItem(item)
            self._grid_lines = []

    def wheelEvent(self, event: QWheelEvent):
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor

        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor

        new_zoom = self.zoom_level * zoom_factor
        if self.min_zoom <= new_zoom <= self.max_zoom:
            self.zoom_level = new_zoom
            self.scale(zoom_factor, zoom_factor)

            if self.marker_widget and hasattr(self.marker_widget, 'zoom_slider'):
                slider_value = int(self.zoom_level * 100)
                self.marker_widget.zoom_slider.blockSignals(True)
                self.marker_widget.zoom_slider.setValue(slider_value)
                self.marker_widget.zoom_slider.blockSignals(False)
                self.marker_widget.update_zoom_label()

            if self.marker_widget and hasattr(self.marker_widget, 'update_points_size'):
                self.marker_widget.update_points_size()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            pos = self.mapToScene(event.position().toPoint())
            self.point_add_request.emit(pos.x(), pos.y())
        elif event.button() == Qt.MouseButton.RightButton:
            if self.marker_widget:
                pos = self.mapToScene(event.position().toPoint())
                screen_pos = event.globalPosition().toPoint()
                self.marker_widget.show_view_context_menu(pos, screen_pos)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = self.mapToScene(event.position().toPoint())
        self.mouse_moved.emit(pos.x(), pos.y())
        super().mouseMoveEvent(event)


# ══════════════════════════════════════════════════════════════════
# MEASUREMENT DIALOG
# ══════════════════════════════════════════════════════════════════
class MeasurementDialog(QDialog):
    """Dialog for real-time instrument measurements."""

    def __init__(self, instruments, parent=None):
        super().__init__(parent)
        self.instruments = instruments
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Medicao em Tempo Real")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Theme.BG_SURFACE};
                color: {Theme.TEXT_PRIMARY};
            }}
            QLabel {{
                color: {Theme.TEXT_PRIMARY};
                background: transparent;
            }}
            QGroupBox {{
                color: {Theme.TEXT_PRIMARY};
                font-weight: bold;
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 12px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: {Theme.ACCENT_BLUE};
            }}
            QComboBox {{
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 6px;
                padding: 6px 10px;
                background-color: {Theme.BG_INPUT};
                color: {Theme.TEXT_PRIMARY};
            }}
            QComboBox QAbstractItemView {{
                background-color: {Theme.BG_SURFACE_ALT};
                color: {Theme.TEXT_PRIMARY};
                selection-background-color: {Theme.ACCENT_BLUE};
            }}
        """)

        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Instruments
        instruments_group = QGroupBox("Instrumentos Conectados")
        instruments_layout = QVBoxLayout()
        self.instruments_label = QLabel()
        instruments_text = []
        if self.instruments.get("DMM"):
            instruments_text.append("  Multimetro Digital (DMM)")
        if self.instruments.get("OSC"):
            instruments_text.append("  Osciloscopio")
        if not instruments_text:
            instruments_text.append("  Nenhum instrumento conectado")
        self.instruments_label.setText("\n".join(instruments_text))
        instruments_layout.addWidget(self.instruments_label)
        instruments_group.setLayout(instruments_layout)
        layout.addWidget(instruments_group)

        # Measurement controls
        measure_group = QGroupBox("Realizar Medicao")
        measure_layout = QFormLayout()

        self.measure_type = QComboBox()
        self.measure_type.addItems(["Tensao (V)", "Corrente (A)", "Frequencia (Hz)"])
        measure_layout.addRow("Tipo:", self.measure_type)

        self.measure_button = QPushButton("Realizar Medicao")
        self.measure_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.VCC_GREEN};
                color: {Theme.BG_PRIMARY};
                border: none;
                border-radius: 6px;
                padding: 10px 16px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{ background-color: #16A34A; }}
        """)
        self.measure_button.clicked.connect(self.perform_measurement)
        measure_layout.addRow("", self.measure_button)

        self.result_label = QLabel("Aguardando medicao...")
        self.result_label.setStyleSheet(f"""
            font-size: 18px; font-weight: bold;
            padding: 12px; color: {Theme.TEXT_MUTED};
            font-family: Consolas, monospace;
        """)
        measure_layout.addRow("Resultado:", self.result_label)

        measure_group.setLayout(measure_layout)
        layout.addWidget(measure_group)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.ACCENT_BLUE};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
                min-width: 80px;
            }}
            QPushButton:hover {{ background-color: #0284C7; }}
        """)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def perform_measurement(self):
        try:
            measure_type = self.measure_type.currentText()
            result = None

            if "Tensao" in measure_type and self.instruments.get("DMM"):
                result = self.instruments["DMM"].measure_voltage()
                unit = "V"
            elif "Corrente" in measure_type and self.instruments.get("DMM"):
                result = self.instruments["DMM"].measure_current()
                unit = "A"
            elif "Frequencia" in measure_type and self.instruments.get("OSC"):
                result = self.instruments["OSC"].measure_frequency()
                unit = "Hz"

            if result is not None:
                self.result_label.setText(f"{result:.4f} {unit}")
                self.result_label.setStyleSheet(f"""
                    color: {Theme.VCC_GREEN}; font-size: 18px;
                    font-weight: bold; padding: 12px;
                    font-family: Consolas, monospace;
                """)
                logger.info(f"Medicao realizada: {result:.4f} {unit}")
            else:
                self.result_label.setText("Medicao nao disponivel")
                self.result_label.setStyleSheet(f"""
                    color: {Theme.ERROR_RED}; font-size: 18px;
                    font-weight: bold; padding: 12px;
                """)

        except Exception as e:
            logger.error(f"Erro na medicao: {e}")
            self.result_label.setText("Erro na medicao")

    def get_measurement_result(self):
        text = self.result_label.text()
        try:
            parts = text.split()
            if len(parts) >= 1:
                return float(parts[0])
        except (ValueError, IndexError):
            pass
        return None



# ══════════════════════════════════════════════════════════════════
# POINT EDIT POPUP
# ══════════════════════════════════════════════════════════════════
class PointEditDialog(QDialog):
    """Popup para editar os dados de um ponto sem ocupar espaço no scanner."""

    def __init__(self, tp: TestPoint, parent=None):
        super().__init__(parent)
        self.tp = tp
        self.setWindowTitle(f"Editar ponto - {tp.refdes}")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setMinimumHeight(560)
        self.resize(600, 620)
        self._build_ui()
        self._load_values()
        self._apply_style()

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("pointDialogLabel")
        return lbl

    def _line(self, placeholder: str = "") -> QLineEdit:
        field = QLineEdit()
        field.setObjectName("pointDialogInput")
        field.setPlaceholderText(placeholder)
        field.setMinimumHeight(34)
        return field

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        # Cabeçalho compacto.
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.title_label = QLabel(self.tp.refdes or "Ponto")
        self.title_label.setObjectName("pointDialogTitle")
        subtitle = QLabel("Edite somente as informações necessárias e salve.")
        subtitle.setObjectName("pointDialogMuted")
        title_box.addWidget(self.title_label)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        root.addLayout(header)

        info = QFrame()
        info.setObjectName("pointDialogInfo")
        info_layout = QFormLayout(info)
        info_layout.setContentsMargins(14, 12, 14, 12)
        info_layout.setHorizontalSpacing(16)
        info_layout.setVerticalSpacing(8)

        self.refdes_value = QLabel("—")
        self.coords_value = QLabel("—")
        self.scope_channel_value = QLabel("—")
        self.scope_vpp_value = QLabel("—")
        self.scope_vrms_value = QLabel("—")
        self.scope_frequency_value = QLabel("—")
        self.last_capture_time = QLabel("—")
        for widget in (
            self.refdes_value, self.coords_value, self.scope_channel_value,
            self.scope_vpp_value, self.scope_vrms_value, self.scope_frequency_value,
            self.last_capture_time,
        ):
            widget.setObjectName("pointDialogValue")

        info_layout.addRow(self._label("RefDes"), self.refdes_value)
        info_layout.addRow(self._label("Coordenadas"), self.coords_value)
        info_layout.addRow(self._label("Canal capturado"), self.scope_channel_value)
        info_layout.addRow(self._label("Vpp medido"), self.scope_vpp_value)
        info_layout.addRow(self._label("Vrms medido"), self.scope_vrms_value)
        info_layout.addRow(self._label("Frequência medida"), self.scope_frequency_value)
        info_layout.addRow(self._label("Capturada em"), self.last_capture_time)
        root.addWidget(info)

        form_frame = QFrame()
        form_frame.setObjectName("pointDialogForm")
        form = QFormLayout(form_frame)
        form.setContentsMargins(14, 14, 14, 14)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.expected_voltage = self._line("Ex: 3.3, 5.0, 12.0")
        self.expected_voltage.setValidator(QDoubleValidator(-1000, 1000, 4))
        self.expected_current = self._line("Ex: 0.1, 0.5, 1.0")
        self.expected_current.setValidator(QDoubleValidator(-100, 100, 4))
        self.expected_frequency = self._line("Ex: 1000, 12000")
        self.expected_frequency.setValidator(QDoubleValidator(0, 1e12, 2))
        self.expected_waveform = self._line("Senoidal, Quadrada, PWM...")

        self.tolerance_voltage = self._line("+/- V")
        self.tolerance_voltage.setValidator(QDoubleValidator(0, 1000, 4))
        self.tolerance_current = self._line("+/- A")
        self.tolerance_current.setValidator(QDoubleValidator(0, 100, 4))
        self.tolerance_frequency = self._line("+/- Hz")
        self.tolerance_frequency.setValidator(QDoubleValidator(0, 1e12, 2))

        form.addRow(self._label("Tensão esperada (V)"), self.expected_voltage)
        form.addRow(self._label("Corrente esperada (A)"), self.expected_current)
        form.addRow(self._label("Frequência esperada (Hz)"), self.expected_frequency)
        form.addRow(self._label("Forma de onda"), self.expected_waveform)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setObjectName("pointDialogSeparator")
        form.addRow(separator)

        form.addRow(self._label("Tolerância tensão"), self.tolerance_voltage)
        form.addRow(self._label("Tolerância corrente"), self.tolerance_current)
        form.addRow(self._label("Tolerância frequência"), self.tolerance_frequency)
        root.addWidget(form_frame)

        notes_title = self._label("Observações")
        root.addWidget(notes_title)
        self.notes = QTextEdit()
        self.notes.setObjectName("pointDialogNotes")
        self.notes.setPlaceholderText("Observações sobre este ponto de teste...")
        self.notes.setMinimumHeight(76)
        self.notes.setMaximumHeight(110)
        root.addWidget(self.notes)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if save_button:
            save_button.setText("Salvar alterações")
            save_button.setObjectName("pointDialogSave")
        if cancel_button:
            cancel_button.setText("Cancelar")
            cancel_button.setObjectName("pointDialogCancel")
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _accept_if_valid(self):
        try:
            self.values()
        except ValueError:
            QMessageBox.warning(
                self,
                "Valor inválido",
                "Revise os campos numéricos antes de salvar.",
            )
            return
        self.accept()

    def _load_values(self):
        tp = self.tp
        color_hex = getattr(tp, "marker_color", None) or Theme.DEFAULT_POINT_COLOR
        self.title_label.setStyleSheet(f"color: {color_hex};")
        self.refdes_value.setText(tp.refdes or "—")
        self.coords_value.setText(f"({tp.x}, {tp.y})")

        channel = getattr(tp, "last_scope_channel", None)
        vpp = getattr(tp, "last_scope_vpp_v", None)
        vrms = getattr(tp, "last_scope_vrms_v", None)
        freq = getattr(tp, "last_scope_frequency_hz", None)

        self.scope_channel_value.setText(f"CH{channel}" if channel else "—")
        self.scope_vpp_value.setText(f"{vpp:.6g} V" if vpp is not None else "—")
        self.scope_vrms_value.setText(f"{vrms:.6g} V" if vrms is not None else "—")
        self.scope_frequency_value.setText(f"{freq:.6g} Hz" if freq is not None else "—")

        captured_at = getattr(tp, "last_scope_at", None)
        self.last_capture_time.setText(
            captured_at.strftime("%d/%m/%Y %H:%M:%S") if captured_at else "—"
        )

        self.expected_voltage.setText("" if tp.expected_voltage_v is None else str(tp.expected_voltage_v))
        self.expected_current.setText("" if tp.expected_current_a is None else str(tp.expected_current_a))
        self.expected_frequency.setText("" if tp.expected_frequency_hz is None else str(tp.expected_frequency_hz))
        self.expected_waveform.setText(tp.expected_waveform or "")
        self.tolerance_voltage.setText("" if tp.tolerance_voltage_v is None else str(tp.tolerance_voltage_v))
        self.tolerance_current.setText("" if tp.tolerance_current_a is None else str(tp.tolerance_current_a))
        self.tolerance_frequency.setText("" if tp.tolerance_frequency_hz is None else str(tp.tolerance_frequency_hz))
        self.notes.setPlainText(tp.notes or "")

    @staticmethod
    def _to_float(text: str):
        return float(text) if text.strip() else None

    def values(self) -> dict:
        return {
            "expected_voltage_v": self._to_float(self.expected_voltage.text()),
            "expected_current_a": self._to_float(self.expected_current.text()),
            "expected_frequency_hz": self._to_float(self.expected_frequency.text()),
            "expected_waveform": self.expected_waveform.text().strip() or None,
            "tolerance_voltage_v": self._to_float(self.tolerance_voltage.text()),
            "tolerance_current_a": self._to_float(self.tolerance_current.text()),
            "tolerance_frequency_hz": self._to_float(self.tolerance_frequency.text()),
            "notes": self.notes.toPlainText().strip() or None,
        }

    def _apply_style(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: {Theme.BG_PRIMARY};
                color: {Theme.TEXT_PRIMARY};
                font-family: "Segoe UI", "Inter", Arial, sans-serif;
            }}
            QLabel#pointDialogTitle {{
                color: {Theme.TEXT_BRIGHT};
                font-size: 18px;
                font-weight: 800;
            }}
            QLabel#pointDialogMuted {{ color: {Theme.TEXT_MUTED}; font-size: 10px; }}
            QLabel#pointDialogLabel {{ color: {Theme.TEXT_SECONDARY}; font-size: 10px; }}
            QLabel#pointDialogValue {{ color: {Theme.ACCENT_CYAN}; font-family: Consolas; font-weight: 700; }}
            QFrame#pointDialogInfo, QFrame#pointDialogForm {{
                background: {Theme.BG_SURFACE};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 7px;
            }}
            QFrame#pointDialogSeparator {{
                background: {Theme.BORDER_SUBTLE};
                border: none;
                max-height: 1px;
            }}
            QLineEdit#pointDialogInput, QTextEdit#pointDialogNotes {{
                background: {Theme.BG_INPUT};
                color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 5px;
                padding: 6px 8px;
                selection-background-color: {Theme.ACCENT_BLUE};
            }}
            QLineEdit#pointDialogInput:focus, QTextEdit#pointDialogNotes:focus {{
                border-color: {Theme.ACCENT_BLUE};
            }}
            QPushButton#pointDialogSave {{
                background: {Theme.ACCENT_BLUE};
                color: {Theme.TEXT_BRIGHT};
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: 700;
            }}
            QPushButton#pointDialogCancel {{
                background: {Theme.BG_SURFACE_ALT};
                color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: 600;
            }}
        """)


# ══════════════════════════════════════════════════════════════════
# MAIN WIDGET: IMAGE MARKER
# ══════════════════════════════════════════════════════════════════
class ImageMarker(QWidget):
    """Professional PCB test-point mapping interface.

    Public API (backward compatible):
        - __init__(session, board, mode, instruments)
        - load_image(path) -> bool
        - select_point(tp)
        - refresh_points()
        - Signals: point_selected, point_updated
    """

    point_selected = pyqtSignal(object)
    point_updated = pyqtSignal(object)

    def __init__(self, session: Session, board: BoardUnit,
                 mode: str = "edit", instruments: dict | None = None):
        super().__init__()
        self.session = session
        self.board = board
        self.mode = mode
        self.instruments = instruments or {}
        self.current_point = None
        self.image_path = None
        self.current_image_slot = 1
        self.test_point_items = {}
        # Leituras ao vivo não são persistidas até o usuário capturar.
        # Elas servem apenas para a comparação instantânea na própria tela.
        self._live_scope_by_point = {}
        self._reference_cache = {}

        title_mode = "Edicao" if mode == "edit" else "Visualizacao"
        self.setWindowTitle(f"Mapeamento de Pontos - {board.name} ({title_mode})")
        self.setMinimumSize(1200, 750)

        self.setup_ui()
        self.apply_global_styles()
        self.view.point_add_request.connect(self.add_point_by_click)
        self.view.mouse_moved.connect(self._on_mouse_move)

    # ──────────────────────────────────────────────────────────────
    # UI SETUP
    # ──────────────────────────────────────────────────────────────
    def setup_ui(self):
        main_layout = QHBoxLayout()
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # LEFT: Canvas panel (50%)
        left_panel = self._build_canvas_panel()
        left_panel.setMinimumWidth(420)
        splitter.addWidget(left_panel)

        # RIGHT: Control panel (50%)
        right_panel = self._build_side_panel()
        right_panel.setMinimumWidth(420)
        splitter.addWidget(right_panel)

        # Layout meio a meio: a imagem da placa não precisa dominar a tela.
        # O osciloscópio e a tabela de pontos também precisam de espaço útil.
        splitter.setSizes([600, 600])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

    def _build_canvas_panel(self):
        """Build the left canvas panel with toolbar, view, and status bar."""
        panel = QFrame()
        panel.setObjectName("canvasPanel")
        layout = QVBoxLayout(panel)
        layout.setSpacing(0)
        layout.setContentsMargins(12, 12, 6, 12)

        # ── Toolbar ──
        toolbar = QFrame()
        toolbar.setObjectName("canvasToolbar")
        toolbar.setFixedHeight(44)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 0, 12, 0)
        toolbar_layout.setSpacing(8)

        # Board name label
        board_label = QLabel(f"{self.board.name}")
        board_label.setObjectName("toolbarTitle")
        toolbar_layout.addWidget(board_label)

        toolbar_layout.addStretch()

        # Grid toggle
        self.grid_btn = QPushButton("Grid")
        self.grid_btn.setObjectName("toolbarBtn")
        self.grid_btn.setCheckable(True)
        self.grid_btn.setChecked(True)
        self.grid_btn.setFixedSize(60, 28)
        self.grid_btn.clicked.connect(self._toggle_grid)
        toolbar_layout.addWidget(self.grid_btn)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {Theme.BORDER_SUBTLE};")
        sep.setFixedHeight(20)
        toolbar_layout.addWidget(sep)

        # Zoom controls
        zoom_icon = QLabel("Zoom")
        zoom_icon.setObjectName("toolbarLabel")
        toolbar_layout.addWidget(zoom_icon)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 500)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(120)
        self.zoom_slider.setObjectName("zoomSlider")
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        toolbar_layout.addWidget(self.zoom_slider)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("zoomValue")
        self.zoom_label.setFixedWidth(48)
        toolbar_layout.addWidget(self.zoom_label)

        self.fit_button = QPushButton("Fit")
        self.fit_button.setObjectName("toolbarBtn")
        self.fit_button.setFixedSize(44, 28)
        self.fit_button.clicked.connect(self.fit_to_view)
        toolbar_layout.addWidget(self.fit_button)

        layout.addWidget(toolbar)

        # ── Canvas View ──
        self.view = ZoomableGraphicsView()
        self.view.marker_widget = self
        self.view.setMinimumSize(400, 400)
        layout.addWidget(self.view, 1)

        # ── Status Bar ──
        status_bar = QFrame()
        status_bar.setObjectName("canvasStatusBar")
        status_bar.setFixedHeight(28)
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(12, 0, 12, 0)
        status_layout.setSpacing(16)

        self.coords_label = QLabel("X: -- Y: --")
        self.coords_label.setObjectName("statusCoords")
        status_layout.addWidget(self.coords_label)

        status_layout.addStretch()

        self.points_count_label = QLabel("0 pontos")
        self.points_count_label.setObjectName("statusInfo")
        status_layout.addWidget(self.points_count_label)

        self.status_label = QLabel("Pronto")
        self.status_label.setObjectName("statusInfo")
        status_layout.addWidget(self.status_label)

        layout.addWidget(status_bar)

        return panel

    def _build_side_panel(self):
        """Build the right panel: points table + edit form."""
        panel = QFrame()
        panel.setObjectName("sidePanel")
        layout = QVBoxLayout(panel)
        layout.setSpacing(0)
        layout.setContentsMargins(6, 12, 12, 12)

        # ── Header ──
        header = QFrame()
        header.setObjectName("sidePanelHeader")
        header.setFixedHeight(44)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 12, 0)

        title = QLabel("PONTOS DE TESTE")
        title.setObjectName("panelTitle")
        header_layout.addWidget(title)

        header_layout.addStretch()

        if self.mode == "edit":
            self.add_point_btn = QPushButton("+ Novo Ponto")
            self.add_point_btn.setObjectName("addPointBtn")
            self.add_point_btn.setFixedHeight(28)
            self.add_point_btn.clicked.connect(self.add_point_dialog)
            header_layout.addWidget(self.add_point_btn)
        else:
            self.add_point_btn = None

        layout.addWidget(header)

        # ── Osciloscópio Rigol MSO5074 ──
        # Painel compacto/colapsável. Toda comunicação VISA ocorre fora da thread da GUI.
        self.oscilloscope_panel = OscilloscopePanel(Theme, self)
        self.oscilloscope_panel.capture_requested.connect(self._persist_oscilloscope_reading)
        self.oscilloscope_panel.live_reading_changed.connect(self._on_live_scope_reading)
        self.oscilloscope_panel.waveform_similarity_changed.connect(self._on_waveform_similarity)
        self.oscilloscope_panel.status_changed.connect(self.show_status)
        layout.addWidget(self.oscilloscope_panel)
        layout.addSpacing(8)

        # ── Lista de pontos ──
        # O editor permanente foi removido desta coluna. A edição agora acontece
        # somente em popup, liberando altura para a mini tela do osciloscópio e
        # para a própria tabela de pontos.
        table_card = self._build_points_table()
        table_card.setMinimumHeight(220)
        layout.addWidget(table_card, 1)

        return panel

    def _build_points_table(self):
        """Tabela compacta + faixa de comparação detalhada do ponto selecionado."""
        card = QFrame()
        card.setObjectName("tableCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 8, 0, 0)
        card_layout.setSpacing(8)

        # Ações contextuais da seleção.
        actions = QHBoxLayout()
        actions.setContentsMargins(8, 0, 8, 0)
        actions.setSpacing(6)
        self.selected_point_hint = QLabel("Selecione um ponto para comparar")
        self.selected_point_hint.setObjectName("statusInfo")
        actions.addWidget(self.selected_point_hint)
        actions.addStretch()

        self.edit_point_btn = QPushButton("Editar ponto")
        self.edit_point_btn.setObjectName("toolbarBtn")
        self.edit_point_btn.setFixedHeight(28)
        self.edit_point_btn.setEnabled(False)
        self.edit_point_btn.clicked.connect(self.open_point_editor)
        actions.addWidget(self.edit_point_btn)
        card_layout.addLayout(actions)

        # Faixa de comparação do ponto selecionado. Em vez de colocar
        # referência/desvio/tolerância dentro da tabela, mostramos aqui com
        # espaço suficiente e leitura imediata.
        self.comparison_strip = QFrame()
        self.comparison_strip.setObjectName("comparisonStrip")
        self.comparison_strip.setVisible(False)
        self.comparison_strip.setStyleSheet(
            f"QFrame#comparisonStrip {{ background: {Theme.BG_SURFACE_ALT}; "
            f"border: 1px solid {Theme.BORDER_SUBTLE}; border-radius: 6px; }}"
        )
        strip_layout = QHBoxLayout(self.comparison_strip)
        strip_layout.setContentsMargins(8, 8, 8, 8)
        strip_layout.setSpacing(8)

        self._comparison_labels = {}
        for key, title in (("vpp", "VPP"), ("vrms", "VRMS"), ("freq", "FREQUÊNCIA")):
            metric = QFrame()
            metric.setStyleSheet(
                f"QFrame {{ background: {Theme.BG_SURFACE}; border: 1px solid {Theme.BORDER_MUTED}; "
                "border-radius: 5px; }}"
            )
            ml = QVBoxLayout(metric)
            ml.setContentsMargins(11, 8, 11, 8)
            ml.setSpacing(3)

            title_lbl = QLabel(title)
            title_lbl.setStyleSheet(f"color: {Theme.TEXT_SECONDARY}; font-size: 10px; font-weight: 700;")
            value_lbl = QLabel("—")
            value_lbl.setStyleSheet(f"color: {Theme.TEXT_BRIGHT}; font-size: 15px; font-weight: 800;")
            detail_lbl = QLabel("REF —   •   Δ —   •   TOL —")
            detail_lbl.setMinimumHeight(18)
            detail_lbl.setStyleSheet(
                f"color: {Theme.TEXT_SECONDARY}; font-size: 10px; font-weight: 600;"
            )
            detail_lbl.setWordWrap(False)

            ml.addWidget(title_lbl)
            ml.addWidget(value_lbl)
            ml.addWidget(detail_lbl)
            strip_layout.addWidget(metric, 1)
            self._comparison_labels[key] = {
                "title": title_lbl, "value": value_lbl, "detail": detail_lbl, "frame": metric
            }

        card_layout.addWidget(self.comparison_strip)

        # Comparação da forma da onda. A curva correta aparece tracejada na
        # própria tela do osciloscópio; aqui mostramos a similaridade numérica.
        self.waveform_compare_label = QLabel("FORMA DA ONDA  •  sem referência de curva")
        self.waveform_compare_label.setObjectName("statusInfo")
        self.waveform_compare_label.setMinimumHeight(22)
        self.waveform_compare_label.setStyleSheet(
            f"color: {Theme.TEXT_MUTED}; font-size: 10px; font-weight: 600; padding: 0 8px;"
        )
        card_layout.addWidget(self.waveform_compare_label)

        # Tabela compacta: visão geral de todos os pontos. Os detalhes completos
        # ficam na faixa acima e em tooltip, evitando colunas espremidas.
        self.points_table = QTableWidget()
        self.points_table.setObjectName("pointsTable")
        self.points_table.setColumnCount(7)
        self.points_table.setHorizontalHeaderLabels([
            "   ID", "Tipo", "Vpp M/R", "Vrms M/R", "Freq. M/R", "Status", "Pos (X,Y)"
        ])
        self.points_table.verticalHeader().setVisible(False)
        self.points_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.points_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.points_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.points_table.setAlternatingRowColors(True)
        self.points_table.setShowGrid(False)
        self.points_table.verticalHeader().setDefaultSectionSize(34)
        self.points_table.verticalHeader().setMinimumSectionSize(30)

        header = self.points_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setMinimumSectionSize(72)

        self.points_table.itemSelectionChanged.connect(self._on_table_selection_changed)
        if self.mode == "edit":
            self.points_table.cellDoubleClicked.connect(lambda _row, _col: self.open_point_editor())

        card_layout.addWidget(self.points_table, 1)
        return card

    def _build_edit_form(self):
        """Build the point edit form card."""
        card = QFrame()
        card.setObjectName("formCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # Form header
        form_header = QHBoxLayout()
        self.form_title = QLabel("Nenhum ponto selecionado")
        self.form_title.setObjectName("formTitle")
        form_header.addWidget(self.form_title)
        form_header.addStretch()

        if self.mode == "edit":
            self.delete_point_btn = QPushButton("Excluir")
            self.delete_point_btn.setObjectName("deleteBtn")
            self.delete_point_btn.setFixedHeight(26)
            self.delete_point_btn.clicked.connect(self.delete_current_point)
            self.delete_point_btn.setEnabled(False)
            form_header.addWidget(self.delete_point_btn)
        else:
            self.delete_point_btn = None

        layout.addLayout(form_header)

        # ── Form fields ──
        form = QFrame()
        form.setObjectName("formFields")
        form_layout = QFormLayout(form)
        form_layout.setSpacing(8)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)

        # RefDes (read-only display)
        self.refdes_label = QLabel("-")
        self.refdes_label.setObjectName("formValueLabel")
        form_layout.addRow(self._make_label("RefDes"), self.refdes_label)

        # Coordinates (read-only display)
        self.coords_display = QLabel("-")
        self.coords_display.setObjectName("formValueLabel")
        form_layout.addRow(self._make_label("Coordenadas"), self.coords_display)

        # Última leitura real (separada dos valores esperados).
        self.last_measurement_label = QLabel("—")
        self.last_measurement_label.setObjectName("formValueLabel")
        form_layout.addRow(self._make_label("Última captura"), self.last_measurement_label)

        self.last_measurement_time = QLabel("—")
        self.last_measurement_time.setObjectName("formValueLabel")
        form_layout.addRow(self._make_label("Capturada em"), self.last_measurement_time)

        # Voltage
        self.expected_voltage = QLineEdit()
        self.expected_voltage.setPlaceholderText("Ex: 3.3, 5.0, 12.0")
        self.expected_voltage.setObjectName("formInput")
        self.expected_voltage.setMinimumHeight(30)
        self.expected_voltage.setValidator(QDoubleValidator(-1000, 1000, 4))
        self.expected_voltage.textChanged.connect(lambda: self._validate_field(self.expected_voltage))
        form_layout.addRow(self._make_label("Tensao (V)"), self.expected_voltage)

        # Current
        self.expected_current = QLineEdit()
        self.expected_current.setPlaceholderText("Ex: 0.1, 0.5, 1.0")
        self.expected_current.setObjectName("formInput")
        self.expected_current.setMinimumHeight(30)
        self.expected_current.setValidator(QDoubleValidator(-100, 100, 4))
        self.expected_current.textChanged.connect(lambda: self._validate_field(self.expected_current))
        form_layout.addRow(self._make_label("Corrente (A)"), self.expected_current)

        # Frequency
        self.expected_frequency = QLineEdit()
        self.expected_frequency.setPlaceholderText("Ex: 1000, 12000")
        self.expected_frequency.setObjectName("formInput")
        self.expected_frequency.setMinimumHeight(30)
        self.expected_frequency.setValidator(QDoubleValidator(0, 1e12, 2))
        self.expected_frequency.textChanged.connect(lambda: self._validate_field(self.expected_frequency))
        form_layout.addRow(self._make_label("Frequencia (Hz)"), self.expected_frequency)

        # Waveform
        self.expected_waveform = QLineEdit()
        self.expected_waveform.setPlaceholderText("Senoidal, Quadrada...")
        self.expected_waveform.setObjectName("formInput")
        self.expected_waveform.setMinimumHeight(30)
        form_layout.addRow(self._make_label("Forma de Onda"), self.expected_waveform)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {Theme.BORDER_SUBTLE};")
        form_layout.addRow(sep)

        # Tolerance voltage
        self.tolerance_voltage = QLineEdit()
        self.tolerance_voltage.setPlaceholderText("+/- V")
        self.tolerance_voltage.setObjectName("formInput")
        self.tolerance_voltage.setMinimumHeight(30)
        self.tolerance_voltage.setValidator(QDoubleValidator(0, 1000, 4))
        self.tolerance_voltage.textChanged.connect(lambda: self._validate_field(self.tolerance_voltage))
        form_layout.addRow(self._make_label("Toler. Tensao"), self.tolerance_voltage)

        # Tolerance current
        self.tolerance_current = QLineEdit()
        self.tolerance_current.setPlaceholderText("+/- A")
        self.tolerance_current.setObjectName("formInput")
        self.tolerance_current.setMinimumHeight(30)
        self.tolerance_current.setValidator(QDoubleValidator(0, 100, 4))
        self.tolerance_current.textChanged.connect(lambda: self._validate_field(self.tolerance_current))
        form_layout.addRow(self._make_label("Toler. Corrente"), self.tolerance_current)

        # Tolerance frequency
        self.tolerance_frequency = QLineEdit()
        self.tolerance_frequency.setPlaceholderText("+/- Hz")
        self.tolerance_frequency.setObjectName("formInput")
        self.tolerance_frequency.setMinimumHeight(30)
        self.tolerance_frequency.setValidator(QDoubleValidator(0, 1e12, 2))
        self.tolerance_frequency.textChanged.connect(lambda: self._validate_field(self.tolerance_frequency))
        form_layout.addRow(self._make_label("Toler. Freq."), self.tolerance_frequency)

        layout.addWidget(form)

        # Notes
        notes_label = self._make_label("Observacoes")
        layout.addWidget(notes_label)

        self.notes_field = QTextEdit()
        self.notes_field.setObjectName("notesField")
        self.notes_field.setPlaceholderText("Observacoes sobre este ponto de teste...")
        self.notes_field.setMinimumHeight(58)
        self.notes_field.setMaximumHeight(82)
        layout.addWidget(self.notes_field)

        # ── Action buttons ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.setObjectName("ghostBtn")
        self.cancel_btn.setFixedHeight(34)
        self.cancel_btn.clicked.connect(self._on_cancel_edit)
        self.cancel_btn.setEnabled(False)

        self.save_btn = QPushButton("Salvar Alteracoes")
        self.save_btn.setObjectName("primaryBtn")
        self.save_btn.setFixedHeight(34)
        self.save_btn.clicked.connect(self.save_point_properties)
        self.save_btn.setEnabled(False)

        # A captura agora fica no painel único de osciloscópio acima da lista.
        self.measure_btn = None

        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

        return card

    def _make_label(self, text):
        """Create a form label with consistent styling."""
        label = QLabel(text)
        label.setObjectName("formLabel")
        return label

    # ──────────────────────────────────────────────────────────────
    # GLOBAL STYLESHEET
    # ──────────────────────────────────────────────────────────────
    def apply_global_styles(self):
        self.setStyleSheet(f"""
            /* ── Root ── */
            QWidget {{
                background-color: {Theme.BG_PRIMARY};
                color: {Theme.TEXT_PRIMARY};
                font-family: "Segoe UI", "Inter", Arial, sans-serif;
                font-size: 12px;
            }}

            QLabel {{
                background: transparent;
                border: none;
            }}

            /* ── Canvas Panel ── */
            QFrame#canvasPanel {{
                background: {Theme.BG_PRIMARY};
            }}

            QFrame#canvasToolbar {{
                background: {Theme.BG_SURFACE};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 8px 8px 0 0;
            }}

            QFrame#canvasStatusBar {{
                background: {Theme.BG_SURFACE_ALT};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-top: none;
                border-radius: 0 0 8px 8px;
            }}

            QLabel#toolbarTitle {{
                color: {Theme.TEXT_BRIGHT};
                font-size: 12px;
                font-weight: 700;
            }}

            QLabel#toolbarLabel {{
                color: {Theme.TEXT_SECONDARY};
                font-size: 10px;
                font-weight: 600;
            }}

            QLabel#zoomValue {{
                color: {Theme.ACCENT_CYAN};
                font-size: 11px;
                font-weight: 700;
                font-family: Consolas, monospace;
            }}

            QLabel#statusCoords {{
                color: {Theme.ACCENT_CYAN};
                font-size: 10px;
                font-family: Consolas, monospace;
                font-weight: 600;
            }}

            QLabel#statusInfo {{
                color: {Theme.TEXT_MUTED};
                font-size: 10px;
            }}

            QPushButton#toolbarBtn {{
                background: {Theme.BG_SURFACE_ALT};
                color: {Theme.TEXT_SECONDARY};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton#toolbarBtn:hover {{
                background: {Theme.BG_HOVER};
                color: {Theme.TEXT_BRIGHT};
                border-color: {Theme.ACCENT_BLUE};
            }}
            QPushButton#toolbarBtn:checked {{
                background: {Theme.ACCENT_BLUE};
                color: {Theme.TEXT_BRIGHT};
                border-color: {Theme.ACCENT_BLUE};
            }}

            QSlider#zoomSlider::groove:horizontal {{
                border: none;
                height: 4px;
                background: {Theme.BORDER_SUBTLE};
                border-radius: 2px;
            }}
            QSlider#zoomSlider::handle:horizontal {{
                background: {Theme.ACCENT_BLUE};
                border: none;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
            QSlider#zoomSlider::handle:horizontal:hover {{
                background: {Theme.ACCENT_CYAN};
            }}

            /* ── Side Panel ── */
            QFrame#sidePanel {{
                background: {Theme.BG_PRIMARY};
            }}

            QFrame#sidePanelHeader {{
                background: {Theme.BG_SURFACE};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 8px 8px 0 0;
            }}

            QLabel#panelTitle {{
                color: {Theme.ACCENT_CYAN};
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 1px;
            }}

            QPushButton#addPointBtn {{
                background: transparent;
                color: {Theme.ACCENT_BLUE};
                border: 1px solid {Theme.ACCENT_BLUE};
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 10px;
                font-weight: 700;
            }}
            QPushButton#addPointBtn:hover {{
                background: {Theme.ACCENT_BLUE};
                color: {Theme.TEXT_BRIGHT};
            }}

            /* ── Points Table ── */
            QFrame#tableCard {{
                background: {Theme.BG_SURFACE};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-top: none;
            }}

            QTableWidget#pointsTable {{
                background: {Theme.BG_SURFACE};
                alternate-background-color: {Theme.BG_SURFACE_ALT};
                color: {Theme.TEXT_PRIMARY};
                border: none;
                gridline-color: transparent;
                selection-background-color: rgba(14, 165, 233, 0.15);
                selection-color: {Theme.TEXT_BRIGHT};
                font-size: 11px;
            }}
            QTableWidget#pointsTable::item {{
                padding: 6px 8px;
                border-bottom: 1px solid {Theme.BORDER_MUTED};
            }}
            QTableWidget#pointsTable::item:selected {{
                background-color: rgba(14, 165, 233, 0.15);
                border-left: 3px solid {Theme.ACCENT_CYAN};
            }}
            QTableWidget#pointsTable::item:hover {{
                background-color: {Theme.BG_HOVER};
            }}

            QHeaderView::section {{
                background: {Theme.BG_SURFACE_ALT};
                color: {Theme.TEXT_MUTED};
                border: none;
                border-bottom: 2px solid {Theme.BORDER_SUBTLE};
                border-right: 1px solid {Theme.BORDER_MUTED};
                padding: 6px 8px;
                font-size: 9px;
                font-weight: 800;
                text-transform: uppercase;
            }}

            QTableCornerButton::section {{
                background: {Theme.BG_SURFACE_ALT};
                border: none;
            }}

            /* ── Form Card ── */
            QScrollArea#formScroll {{
                background: {Theme.BG_SURFACE};
                border: none;
            }}
            QScrollArea#formScroll > QWidget > QWidget {{
                background: {Theme.BG_SURFACE};
            }}

            QFrame#formCard {{
                background: {Theme.BG_SURFACE};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 0 0 8px 8px;
            }}

            QFrame#formFields {{
                background: transparent;
            }}

            QLabel#formTitle {{
                color: {Theme.TEXT_BRIGHT};
                font-size: 13px;
                font-weight: 700;
            }}

            QLabel#formLabel {{
                color: {Theme.TEXT_SECONDARY};
                font-size: 10px;
                font-weight: 600;
                min-width: 80px;
            }}

            QLabel#formValueLabel {{
                color: {Theme.ACCENT_CYAN};
                font-size: 12px;
                font-weight: 700;
                font-family: Consolas, monospace;
            }}

            QLineEdit#formInput {{
                background: {Theme.BG_INPUT};
                color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 12px;
                font-family: Consolas, monospace;
                selection-background-color: {Theme.ACCENT_BLUE};
            }}
            QLineEdit#formInput:focus {{
                border-color: {Theme.ACCENT_BLUE};
                background: {Theme.BG_SURFACE_ALT};
            }}
            QLineEdit#formInput:disabled {{
                background: {Theme.BG_SURFACE};
                color: {Theme.TEXT_MUTED};
                border-color: {Theme.BORDER_MUTED};
            }}
            QLineEdit#formInput[validation="invalid"] {{
                border-color: {Theme.ERROR_RED};
            }}
            QLineEdit#formInput[validation="valid"] {{
                border-color: {Theme.VCC_GREEN};
            }}

            QTextEdit#notesField {{
                background: {Theme.BG_INPUT};
                color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
                selection-background-color: {Theme.ACCENT_BLUE};
            }}
            QTextEdit#notesField:focus {{
                border-color: {Theme.ACCENT_BLUE};
            }}

            /* ── Buttons ── */
            QPushButton#primaryBtn {{
                background: {Theme.ACCENT_BLUE};
                color: {Theme.TEXT_BRIGHT};
                border: none;
                border-radius: 6px;
                padding: 0 16px;
                font-size: 11px;
                font-weight: 700;
            }}
            QPushButton#primaryBtn:hover {{
                background: #0284C7;
            }}
            QPushButton#primaryBtn:pressed {{
                background: #0369A1;
            }}
            QPushButton#primaryBtn:disabled {{
                background: {Theme.BG_SURFACE_ALT};
                color: {Theme.TEXT_MUTED};
            }}

            QPushButton#ghostBtn {{
                background: transparent;
                color: {Theme.TEXT_SECONDARY};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 6px;
                padding: 0 12px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton#ghostBtn:hover {{
                background: {Theme.BG_HOVER};
                color: {Theme.TEXT_BRIGHT};
                border-color: {Theme.TEXT_MUTED};
            }}
            QPushButton#ghostBtn:disabled {{
                color: {Theme.TEXT_MUTED};
                border-color: {Theme.BORDER_MUTED};
            }}

            QPushButton#measureBtn {{
                background: transparent;
                color: {Theme.ALERT_AMBER};
                border: 1px solid {Theme.ALERT_AMBER};
                border-radius: 6px;
                padding: 0 12px;
                font-size: 11px;
                font-weight: 700;
            }}
            QPushButton#measureBtn:hover {{
                background: {Theme.ALERT_AMBER};
                color: {Theme.BG_PRIMARY};
            }}

            QPushButton#deleteBtn {{
                background: transparent;
                color: {Theme.ERROR_RED};
                border: 1px solid rgba(239, 68, 68, 0.3);
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton#deleteBtn:hover {{
                background: {Theme.ERROR_RED};
                color: {Theme.TEXT_BRIGHT};
                border-color: {Theme.ERROR_RED};
            }}
            QPushButton#deleteBtn:disabled {{
                color: {Theme.TEXT_MUTED};
                border-color: {Theme.BORDER_MUTED};
            }}

            /* ── Scrollbar ── */
            QScrollBar:vertical {{
                background: {Theme.BG_SURFACE};
                width: 8px;
                margin: 0;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {Theme.BORDER_SUBTLE};
                min-height: 20px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {Theme.TEXT_MUTED};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar:horizontal {{
                background: {Theme.BG_SURFACE};
                height: 8px;
                margin: 0;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: {Theme.BORDER_SUBTLE};
                min-width: 20px;
                border-radius: 4px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {Theme.TEXT_MUTED};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0;
            }}

            /* ── Splitter ── */
            QSplitter::handle {{
                background: transparent;
                width: 4px;
                height: 4px;
            }}

            /* ── Tooltip ── */
            QToolTip {{
                background: {Theme.BG_SURFACE_ALT};
                color: {Theme.TEXT_BRIGHT};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
                font-family: Consolas, monospace;
            }}
        """)

    # ──────────────────────────────────────────────────────────────
    # FIELD VALIDATION
    # ──────────────────────────────────────────────────────────────
    def _validate_field(self, field: QLineEdit):
        """Apply visual feedback for inline validation."""
        text = field.text().strip()
        if not text:
            # Empty is OK (optional field)
            field.setProperty("validation", "")
            field.style().unpolish(field)
            field.style().polish(field)
            return

        validator = field.validator()
        if validator:
            state, _, _ = validator.validate(text, 0)
            if state == QDoubleValidator.State.Acceptable:
                field.setProperty("validation", "valid")
            else:
                field.setProperty("validation", "invalid")
        else:
            field.setProperty("validation", "")

        field.style().unpolish(field)
        field.style().polish(field)

    # ──────────────────────────────────────────────────────────────
    # ZOOM / GRID
    # ──────────────────────────────────────────────────────────────
    def on_zoom_changed(self, value):
        zoom_factor = value / 100.0
        self.view.resetTransform()
        self.view.scale(zoom_factor, zoom_factor)
        self.view.zoom_level = zoom_factor
        self.update_zoom_label()
        self.update_points_size()

    def update_zoom_label(self):
        val = int(self.view.zoom_level * 100)
        self.zoom_label.setText(f"{val}%")

    def update_points_size(self):
        if hasattr(self.view, 'zoom_level'):
            zoom_level = self.view.zoom_level
            for tp_id, tp_item in self.test_point_items.items():
                try:
                    if hasattr(tp_item, 'update_size_based_on_zoom'):
                        tp_item.update_size_based_on_zoom(zoom_level)
                except Exception as e:
                    logger.error(f"Erro ao atualizar ponto {tp_id}: {e}")

    def _toggle_grid(self, checked):
        self.view.toggle_grid(checked)

    def fit_to_view(self):
        if self.view.pixmap_item:
            self.view.fitInView(self.view.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            view_rect = self.view.viewport().rect()
            scene_rect = self.view.pixmap_item.boundingRect()
            zoom_x = view_rect.width() / scene_rect.width()
            zoom_y = view_rect.height() / scene_rect.height()
            zoom_level = min(zoom_x, zoom_y) * 0.9
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(int(zoom_level * 100))
            self.zoom_slider.blockSignals(False)
            self.view.zoom_level = zoom_level
            self.update_zoom_label()
            self.update_points_size()

    def _on_mouse_move(self, x, y):
        self.coords_label.setText(f"X: {int(x):>5}  Y: {int(y):>5}")

    # ──────────────────────────────────────────────────────────────
    # IMAGE LOADING
    # ──────────────────────────────────────────────────────────────
    def _detect_image_slot(self, path: str) -> int:
        """Descobre se o arquivo carregado é a Imagem 1 ou 2 da placa."""
        try:
            target = os.path.normcase(os.path.abspath(path))
            images = sorted(list(self.board.images), key=lambda i: (i.created_at or datetime.min, i.id or 0))
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            for idx, image in enumerate(images[:2], start=1):
                stored = image.path
                candidate = stored if os.path.isabs(stored) else os.path.join(project_root, stored)
                if os.path.normcase(os.path.abspath(candidate)) == target:
                    return idx
                if os.path.basename(candidate) == os.path.basename(path):
                    return idx
        except Exception:
            pass
        return 1

    def load_image(self, path: str):
        """Load a PCB image into the canvas viewer."""
        self.image_path = path
        self.current_image_slot = self._detect_image_slot(path)
        success = self.view.load_image(path)
        if success:
            self.refresh_points()
            self.show_status(f"Imagem carregada: {os.path.basename(path)}")
        else:
            self.show_status(f"Erro ao carregar imagem: {path}", "error")
        return success

    # ──────────────────────────────────────────────────────────────
    # POINTS MANAGEMENT
    # ──────────────────────────────────────────────────────────────
    @staticmethod
    def _scope_compare(measured, reference, tolerance_pct):
        """Retorna (status, desvio_assinado_pct, uso_da_tolerancia).

        status: ``OK`` até 80% da tolerância, ``LIMITE`` entre 80% e 100%,
        ``FORA`` acima de 100%. ``None`` quando não há dados suficientes.
        """
        if measured is None or reference is None or tolerance_pct is None:
            return None, None, None
        measured = float(measured)
        reference = float(reference)
        tolerance_pct = abs(float(tolerance_pct))

        if abs(reference) < 1e-12:
            if abs(measured) < 1e-12:
                return "OK", 0.0, 0.0
            return "FORA", float("inf"), float("inf")

        deviation_signed = ((measured - reference) / reference) * 100.0
        deviation_abs = abs(deviation_signed)
        if tolerance_pct <= 0.0:
            usage = 0.0 if deviation_abs <= 1e-12 else float("inf")
        else:
            usage = deviation_abs / tolerance_pct

        if usage > 1.0:
            status = "FORA"
        elif usage >= 0.80:
            status = "LIMITE"
        else:
            status = "OK"
        return status, deviation_signed, usage

    @staticmethod
    def _format_scope_pair(measured, reference, unit):
        """Formata Medido / Referência usando a mesma escala visual."""
        if measured is None and reference is None:
            return "— / —"
        if unit == "Hz":
            values = [abs(v) for v in (measured, reference) if v is not None]
            peak = max(values) if values else 0.0
            if peak >= 1_000_000:
                scale, suffix = 1_000_000.0, "MHz"
            elif peak >= 1_000:
                scale, suffix = 1_000.0, "kHz"
            else:
                scale, suffix = 1.0, "Hz"
            m = "—" if measured is None else f"{measured/scale:.4g}"
            r = "—" if reference is None else f"{reference/scale:.4g}"
            return f"{m} / {r} {suffix}"

        m = "—" if measured is None else f"{measured:.4g}"
        r = "—" if reference is None else f"{reference:.4g}"
        return f"{m} / {r} {unit}"

    @staticmethod
    def _comparison_color(status):
        if status == "OK":
            return Theme.VCC_GREEN
        if status == "LIMITE":
            return Theme.ALERT_AMBER
        if status == "FORA":
            return Theme.ERROR_RED
        return Theme.TEXT_MUTED

    @staticmethod
    def _decode_reference_waveform(ref):
        if ref is None or not getattr(ref, "waveform_json", None):
            return None
        try:
            data = json.loads(ref.waveform_json)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        if not data.get("x_s") or not data.get("y_v"):
            return None
        return data

    def _sync_reference_waveform(self, tp: TestPoint | None) -> None:
        """Carrega no mini-scope a curva correta do ponto selecionado."""
        if tp is None:
            self.oscilloscope_panel.clear_reference_waveform()
            if hasattr(self, "waveform_compare_label"):
                self.waveform_compare_label.setText("FORMA DA ONDA  •  nenhum ponto selecionado")
                self.waveform_compare_label.setStyleSheet(
                    f"color: {Theme.TEXT_MUTED}; font-size: 10px; font-weight: 600; padding: 0 8px;"
                )
            return

        ref = self._reference_for_point(tp)
        waveform = self._decode_reference_waveform(ref)
        if waveform:
            self.oscilloscope_panel.set_reference_waveform(
                waveform,
                channel=getattr(ref, "channel", 1) or 1,
                point_name=tp.refdes,
                select_channel=True,
            )
            if hasattr(self, "waveform_compare_label"):
                points = int(waveform.get("points") or len(waveform.get("y_v") or []))
                self.waveform_compare_label.setText(
                    f"FORMA DA ONDA  •  referência carregada ({points} pontos)  •  linha tracejada no osciloscópio"
                )
                self.waveform_compare_label.setStyleSheet(
                    f"color: {Theme.TEXT_SECONDARY}; font-size: 10px; font-weight: 650; padding: 0 8px;"
                )
        else:
            self.oscilloscope_panel.clear_reference_waveform()
            if hasattr(self, "waveform_compare_label"):
                self.waveform_compare_label.setText("FORMA DA ONDA  •  sem referência de curva")
                self.waveform_compare_label.setStyleSheet(
                    f"color: {Theme.ALERT_AMBER}; font-size: 10px; font-weight: 650; padding: 0 8px;"
                )

    def _on_waveform_similarity(self, payload):
        if self.current_point is None or not isinstance(payload, dict):
            return
        if int(payload.get("point_id") or -1) != int(self.current_point.id):
            return
        similarity = payload.get("similarity_pct")
        if similarity is None or not hasattr(self, "waveform_compare_label"):
            return
        similarity = float(similarity)
        # É um indicador de similaridade visual; por enquanto não altera o
        # status elétrico OK/LIMITE/FORA, que continua baseado nas tolerâncias.
        if similarity >= 90.0:
            color = Theme.VCC_GREEN
        elif similarity >= 75.0:
            color = Theme.ALERT_AMBER
        else:
            color = Theme.ERROR_RED
        self.waveform_compare_label.setText(
            f"FORMA DA ONDA  •  similaridade {similarity:.1f}%  •  tracejado = referência"
        )
        self.waveform_compare_label.setStyleSheet(
            f"color: {color}; font-size: 10px; font-weight: 750; padding: 0 8px;"
        )

    def _reference_for_point(self, tp):
        ref = self._reference_cache.get(tp.refdes)
        if ref is not None:
            return ref
        return self.session.query(OscilloscopeReference).filter_by(
            board_model_id=self.board.model_id,
            refdes=tp.refdes,
        ).one_or_none()

    def _find_point_row(self, point_id: int):
        for row in range(self.points_table.rowCount()):
            item = self.points_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == point_id:
                return row
        return None

    @staticmethod
    def _format_scope_value(value, unit):
        if value is None:
            return "—"
        value = float(value)
        if unit == "Hz":
            av = abs(value)
            if av >= 1_000_000:
                return f"{value/1_000_000:.4g} MHz"
            if av >= 1_000:
                return f"{value/1_000:.4g} kHz"
            return f"{value:.4g} Hz"
        return f"{value:.4g} {unit}"

    def _update_selected_comparison_strip(self, tp: TestPoint, reading=None):
        if tp is None or not hasattr(self, "comparison_strip"):
            if hasattr(self, "comparison_strip"):
                self.comparison_strip.setVisible(False)
            return

        ref = self._reference_for_point(tp)
        live = reading or self._live_scope_by_point.get(tp.id)
        if live is not None:
            measured = {
                "vpp": getattr(live, "vpp_v", None),
                "vrms": getattr(live, "vrms_v", None),
                "freq": getattr(live, "frequency_hz", None),
            }
        else:
            measured = {
                "vpp": getattr(tp, "last_scope_vpp_v", None),
                "vrms": getattr(tp, "last_scope_vrms_v", None),
                "freq": getattr(tp, "last_scope_frequency_hz", None),
            }

        reference = {
            "vpp": getattr(ref, "vpp_v", None) if ref else None,
            "vrms": getattr(ref, "vrms_v", None) if ref else None,
            "freq": getattr(ref, "frequency_hz", None) if ref else None,
        }
        tolerances = {
            "vpp": getattr(ref, "tolerance_vpp_pct", None) if ref else None,
            "vrms": getattr(ref, "tolerance_vrms_pct", None) if ref else None,
            "freq": getattr(ref, "tolerance_frequency_pct", None) if ref else None,
        }
        units = {"vpp": "V", "vrms": "V", "freq": "Hz"}

        for key in ("vpp", "vrms", "freq"):
            state, deviation, _usage = self._scope_compare(
                measured[key], reference[key], tolerances[key]
            )
            labels = self._comparison_labels[key]
            labels["value"].setText(self._format_scope_value(measured[key], units[key]))
            ref_text = self._format_scope_value(reference[key], units[key])
            if deviation is None:
                dev_text = "—"
            elif deviation == float("inf"):
                dev_text = "∞"
            else:
                dev_text = f"{deviation:+.1f}%"
            tol_text = "—" if tolerances[key] is None else f"±{tolerances[key]:g}%"
            labels["detail"].setText(f"REF {ref_text}   •   Δ {dev_text}   •   TOL {tol_text}")

            if ref is None:
                color = Theme.ALERT_AMBER
            elif measured[key] is None:
                color = Theme.TEXT_MUTED
            else:
                color = self._comparison_color(state)
            labels["value"].setStyleSheet(f"color: {color}; font-size: 14px; font-weight: 800;")

        self.comparison_strip.setVisible(True)

    def _update_comparison_row(self, row: int, tp: TestPoint, reading=None):
        """Atualiza visão compacta da tabela e a faixa detalhada do ponto selecionado."""
        ref = self._reference_for_point(tp)
        live = reading or self._live_scope_by_point.get(tp.id)

        if live is not None:
            measured_values = (
                getattr(live, "vpp_v", None),
                getattr(live, "vrms_v", None),
                getattr(live, "frequency_hz", None),
            )
        else:
            measured_values = (
                getattr(tp, "last_scope_vpp_v", None),
                getattr(tp, "last_scope_vrms_v", None),
                getattr(tp, "last_scope_frequency_hz", None),
            )

        if ref is not None:
            expected_values = (ref.vpp_v, ref.vrms_v, ref.frequency_hz)
            tolerances = (ref.tolerance_vpp_pct, ref.tolerance_vrms_pct, ref.tolerance_frequency_pct)
        else:
            expected_values = (None, None, None)
            tolerances = (None, None, None)

        units = ("V", "V", "Hz")
        states = []
        for col, measured, expected, tol, unit in zip(
            (2, 3, 4), measured_values, expected_values, tolerances, units
        ):
            state, deviation, _usage = self._scope_compare(measured, expected, tol)
            states.append(state)
            pair_text = self._format_scope_pair(measured, expected, unit)
            item = self.points_table.item(row, col)
            if item is None:
                item = QTableWidgetItem()
                self.points_table.setItem(row, col, item)
            item.setText(pair_text)
            item.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            if ref is None:
                color = Theme.ALERT_AMBER
            elif measured is None:
                color = Theme.TEXT_MUTED
            else:
                color = self._comparison_color(state)
            item.setForeground(QColor(color))

            if deviation is None:
                dev_text = "—"
            elif deviation == float("inf"):
                dev_text = "∞"
            else:
                dev_text = f"{deviation:+.1f}%"
            tol_text = "—" if tol is None else f"±{tol:g}%"
            item.setToolTip(
                f"Medido / Referência: {pair_text}\n"
                f"Desvio: {dev_text}\n"
                f"Tolerância: {tol_text}"
            )

        valid_states = [s for s in states if s is not None]
        if ref is None:
            status_text, status_color = "SEM REF.", Theme.ALERT_AMBER
        elif not valid_states:
            status_text, status_color = "AGUARD.", Theme.TEXT_MUTED
        elif "FORA" in valid_states:
            status_text, status_color = "FORA", Theme.ERROR_RED
        elif "LIMITE" in valid_states:
            status_text, status_color = "LIMITE", Theme.ALERT_AMBER
        else:
            status_text, status_color = "OK", Theme.VCC_GREEN

        status_item = self.points_table.item(row, 5)
        if status_item is None:
            status_item = QTableWidgetItem()
            self.points_table.setItem(row, 5, status_item)
        status_item.setText(status_text)
        status_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        status_item.setForeground(QColor(status_color))

        if self.current_point is not None and self.current_point.id == tp.id:
            source = "AO VIVO" if live is not None else "ÚLTIMA CAPTURA"
            self.selected_point_hint.setText(f"{tp.refdes} • {source} • {status_text}")
            self.selected_point_hint.setStyleSheet(f"color: {status_color}; font-weight: 700;")
            self._update_selected_comparison_strip(tp, live)

    def _on_live_scope_reading(self, reading: OscilloscopeReading):
        """Compara a leitura atual do Rigol com o ponto selecionado a ~10 Hz."""
        if self.current_point is None or not isinstance(reading, OscilloscopeReading):
            return
        point_id = self.current_point.id
        self._live_scope_by_point[point_id] = reading
        row = self._find_point_row(point_id)
        if row is not None:
            self._update_comparison_row(row, self.current_point, reading)

    def refresh_points(self):
        """Recarrega pontos e referências, mantendo a comparação no mesmo painel."""
        self.points_table.setRowCount(0)
        self.test_point_items.clear()

        for item in self.view.scene().items():
            if isinstance(item, TestPointItem):
                self.view.scene().removeItem(item)

        points = self.session.query(TestPoint).filter_by(board_id=self.board.id).all()
        points = [p for p in points if int(getattr(p, "image_slot", 1) or 1) == self.current_image_slot]
        self._reference_cache = {
            ref.refdes: ref
            for ref in self.session.query(OscilloscopeReference)
            .filter_by(board_model_id=self.board.model_id).all()
        }
        if self.current_point is not None:
            self._sync_reference_waveform(self.current_point)

        for row_idx, tp in enumerate(points):
            self.points_table.insertRow(row_idx)

            id_item = QTableWidgetItem(f"  {tp.refdes}")
            color_hex = getattr(tp, "marker_color", None) or Theme.DEFAULT_POINT_COLOR
            id_item.setForeground(QColor(color_hex))
            id_item.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
            id_item.setData(Qt.ItemDataRole.UserRole, tp.id)
            self.points_table.setItem(row_idx, 0, id_item)

            type_label = Theme.point_type_label(tp.refdes, tp.expected_voltage_v)
            type_item = QTableWidgetItem(type_label)
            type_item.setForeground(QColor(color_hex))
            type_item.setFont(QFont("Segoe UI", 9))
            self.points_table.setItem(row_idx, 1, type_item)

            # Células compactas: Vpp, Vrms, frequência e status.
            for col in (2, 3, 4, 5):
                self.points_table.setItem(row_idx, col, QTableWidgetItem("—"))

            pos_item = QTableWidgetItem(f"({tp.x}, {tp.y})")
            pos_item.setFont(QFont("Consolas", 9))
            pos_item.setForeground(QColor(Theme.TEXT_MUTED))
            self.points_table.setItem(row_idx, 6, pos_item)

            self._update_comparison_row(row_idx, tp)

            tp_item = TestPointItem(tp, self)
            self.view.scene().addItem(tp_item)
            self.test_point_items[tp.id] = tp_item

        self.update_points_size()
        self.points_count_label.setText(f"{len(points)} pontos")
        self.show_status(f"Carregados {len(points)} pontos de teste")

    def _on_table_selection_changed(self):
        """Handle selection change in the points table."""
        rows = self.points_table.selectionModel().selectedRows()
        if not rows:
            self.current_point = None
            self.oscilloscope_panel.set_selected_point(None)
            self._sync_reference_waveform(None)
            self._update_point_actions(False)
            if hasattr(self, "comparison_strip"):
                self.comparison_strip.setVisible(False)
            for tp_item in self.test_point_items.values():
                tp_item.set_selected_style(False)
            return

        row = rows[0].row()
        id_item = self.points_table.item(row, 0)
        if id_item is None:
            return
        tp_id = id_item.data(Qt.ItemDataRole.UserRole)
        self.current_point = self.session.get(TestPoint, tp_id)

        if self.current_point:
            self.oscilloscope_panel.set_selected_point(self.current_point)
            self._sync_reference_waveform(self.current_point)
            if self.oscilloscope_panel.is_paused():
                self.selected_point_hint.setText(
                    f"{self.current_point.refdes} • PAUSADO — reposicione a ponta e pressione ▶"
                )
                self.selected_point_hint.setStyleSheet(
                    f"color: {Theme.ALERT_AMBER}; font-weight: 700;"
                )
            self._update_selected_comparison_strip(self.current_point)
            self._update_point_actions(self.mode == "edit")

            for tid, tp_item in self.test_point_items.items():
                tp_item.set_selected_style(tid == tp_id)

            if tp_id in self.test_point_items:
                self.view.centerOn(self.test_point_items[tp_id])

            self.point_selected.emit(self.current_point)

    def select_point(self, tp: TestPoint):
        """Select a point programmatically (e.g., from canvas click)."""
        self.current_point = tp
        self.oscilloscope_panel.set_selected_point(tp)
        self._sync_reference_waveform(tp)
        if self.oscilloscope_panel.is_paused():
            self.selected_point_hint.setText(
                f"{tp.refdes} • PAUSADO — reposicione a ponta e pressione ▶"
            )
            self.selected_point_hint.setStyleSheet(
                f"color: {Theme.ALERT_AMBER}; font-weight: 700;"
            )
        self._update_point_actions(self.mode == "edit")

        for row in range(self.points_table.rowCount()):
            item = self.points_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == tp.id:
                self.points_table.blockSignals(True)
                self.points_table.selectRow(row)
                self.points_table.blockSignals(False)
                break

        for tid, tp_item in self.test_point_items.items():
            tp_item.set_selected_style(tid == tp.id)

        self.point_selected.emit(tp)

    def _update_point_actions(self, enabled: bool):
        if hasattr(self, "edit_point_btn"):
            self.edit_point_btn.setEnabled(bool(enabled))
        if hasattr(self, "selected_point_hint"):
            if self.current_point is not None:
                self.selected_point_hint.setText(f"Selecionado: {self.current_point.refdes}")
            else:
                self.selected_point_hint.setText("Selecione um ponto para editar")

    def open_point_editor(self, tp=None):
        """Abre as propriedades do ponto em popup, sem ocupar a tela principal."""
        tp = tp or self.current_point
        if tp is None:
            self.show_status("Selecione um ponto para editar", "warning")
            return

        # Mantém tabela, canvas e painel do osciloscópio sincronizados com o ponto.
        if self.current_point is None or self.current_point.id != tp.id:
            self.select_point(tp)

        dialog = PointEditDialog(tp, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            values = dialog.values()
            for field, value in values.items():
                setattr(tp, field, value)

            self.session.add(tp)
            self.session.commit()
            selected_id = tp.id
            self.current_point = tp
            self.refresh_points()

            # Reseleciona a linha depois do refresh.
            for row in range(self.points_table.rowCount()):
                item = self.points_table.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == selected_id:
                    self.points_table.selectRow(row)
                    break

            self.point_updated.emit(tp)
            self.show_status(f"Informações de {tp.refdes} salvas", "success")
        except ValueError:
            self.show_status("Erro: valores numéricos inválidos", "error")
        except Exception as exc:
            self.session.rollback()
            logger.exception("Erro ao salvar propriedades do ponto")
            self.show_status(f"Erro ao salvar: {exc}", "error")

    def populate_point_form(self, tp: TestPoint):
        """Fill the form with test point data."""
        if not tp:
            return

        self.form_title.setText(f"{tp.refdes}")
        color_hex = getattr(tp, "marker_color", None) or Theme.DEFAULT_POINT_COLOR
        self.form_title.setStyleSheet(f"color: {color_hex}; font-size: 14px; font-weight: 800;")

        self.refdes_label.setText(tp.refdes or "-")
        self.coords_display.setText(f"({tp.x}, {tp.y})")

        if getattr(tp, "last_scope_vpp_v", None) is not None:
            ch = getattr(tp, "last_scope_channel", None)
            parts = [f"CH{ch}" if ch else "", f"{tp.last_scope_vpp_v:.4g} Vpp"]
            freq = getattr(tp, "last_scope_frequency_hz", None)
            if freq is not None:
                parts.append(f"{freq:.4g} Hz")
            self.last_measurement_label.setText(" • ".join(p for p in parts if p))
        else:
            self.last_measurement_label.setText("—")
        captured_at = getattr(tp, "last_scope_at", None)
        self.last_measurement_time.setText(
            captured_at.strftime("%d/%m/%Y %H:%M:%S") if captured_at else "—"
        )

        self.expected_voltage.setText("" if tp.expected_voltage_v is None else str(tp.expected_voltage_v))
        self.expected_current.setText("" if tp.expected_current_a is None else str(tp.expected_current_a))
        self.expected_frequency.setText("" if tp.expected_frequency_hz is None else str(tp.expected_frequency_hz))
        self.expected_waveform.setText(tp.expected_waveform or "")

        self.tolerance_voltage.setText("" if tp.tolerance_voltage_v is None else str(tp.tolerance_voltage_v))
        self.tolerance_current.setText("" if tp.tolerance_current_a is None else str(tp.tolerance_current_a))
        self.tolerance_frequency.setText("" if tp.tolerance_frequency_hz is None else str(tp.tolerance_frequency_hz))

        self.notes_field.setPlainText(tp.notes or "")

    def clear_point_form(self):
        """Clear all form fields."""
        self.form_title.setText("Nenhum ponto selecionado")
        self.form_title.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 13px; font-weight: 700;")
        self.refdes_label.setText("-")
        self.coords_display.setText("-")
        self.last_measurement_label.setText("—")
        self.last_measurement_time.setText("—")
        self.expected_voltage.clear()
        self.expected_current.clear()
        self.expected_frequency.clear()
        self.expected_waveform.clear()
        self.tolerance_voltage.clear()
        self.tolerance_current.clear()
        self.tolerance_frequency.clear()
        self.notes_field.clear()

    def _update_form_buttons(self, enabled: bool):
        self.save_btn.setEnabled(enabled)
        self.cancel_btn.setEnabled(enabled)
        if self.delete_point_btn:
            self.delete_point_btn.setEnabled(enabled)

    def _on_cancel_edit(self):
        """Cancel editing and reload point data."""
        if self.current_point:
            self.session.refresh(self.current_point)
            self.populate_point_form(self.current_point)
        else:
            self.clear_point_form()

    # ──────────────────────────────────────────────────────────────
    # POINT CRUD
    # ──────────────────────────────────────────────────────────────
    def add_point_dialog(self):
        """Open dialog to add a new test point."""
        refdes, ok = QInputDialog.getText(
            self, "Novo Ponto de Teste",
            "Identificador (ex: TP1, VCC, GND):"
        )
        if not ok or not refdes.strip():
            return

        # Apply dark style to QInputDialog
        x, ok1 = QInputDialog.getInt(self, "Coordenada X", "Posicao X:", 100, 0, 10000)
        y, ok2 = QInputDialog.getInt(self, "Coordenada Y", "Posicao Y:", 100, 0, 10000)

        if ok1 and ok2:
            self.create_point(refdes.strip(), x, y)

    def add_point_by_click(self, x, y):
        """Add a test point at clicked canvas position."""
        if self.mode != "edit":
            return

        refdes, ok = QInputDialog.getText(
            self, "Novo Ponto de Teste",
            "Identificador (ex: TP1, VCC, GND):"
        )
        if ok and refdes.strip():
            self.create_point(refdes.strip(), int(x), int(y))

    def create_point(self, refdes, x, y):
        """Create a new test point in the database."""
        existing = self.session.query(TestPoint).filter_by(
            board_id=self.board.id, refdes=refdes
        ).first()
        if existing:
            self.show_status(f"Ja existe um ponto com RefDes '{refdes}'", "error")
            return

        try:
            tp = TestPoint(
                board_id=self.board.id,
                refdes=refdes,
                x=x,
                y=y,
                image_slot=self.current_image_slot,
                marker_color=Theme.DEFAULT_POINT_COLOR,
                marker_shape="circle", marker_size=16,
            )
            self.session.add(tp)
            self.session.commit()
            self.refresh_points()
            self.show_status(f"Ponto {refdes} criado em ({x}, {y})", "success")
            logger.info(f"Ponto criado: {refdes} at ({x}, {y})")

        except Exception as e:
            logger.error(f"Erro ao criar ponto: {e}")
            self.show_status(f"Erro ao criar ponto: {str(e)}", "error")

    def delete_current_point(self):
        """Delete the currently selected point."""
        if not self.current_point:
            return

        reply = QMessageBox.question(
            self, "Confirmar Exclusao",
            f"Excluir o ponto '{self.current_point.refdes}'?\n\nEsta acao nao pode ser desfeita.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                refdes = self.current_point.refdes

                if self.current_point.id in self.test_point_items:
                    item_to_remove = self.test_point_items[self.current_point.id]
                    self.view.scene().removeItem(item_to_remove)
                    del self.test_point_items[self.current_point.id]

                self.session.delete(self.current_point)
                self.session.commit()
                self.current_point = None
                self.oscilloscope_panel.set_selected_point(None)
                self._update_point_actions(False)
                self.refresh_points()
                self.show_status(f"Ponto {refdes} excluido", "success")
                logger.info(f"Ponto excluido: {refdes}")

            except Exception as e:
                logger.error(f"Erro ao excluir ponto: {e}")
                self.show_status(f"Erro ao excluir ponto: {str(e)}", "error")

    def save_point_properties(self):
        """Save current form values to the test point."""
        if not self.current_point:
            self.show_status("Nenhum ponto selecionado", "error")
            return

        try:
            def to_float(text):
                return float(text) if text.strip() else None

            self.current_point.expected_voltage_v = to_float(self.expected_voltage.text())
            self.current_point.expected_current_a = to_float(self.expected_current.text())
            self.current_point.expected_frequency_hz = to_float(self.expected_frequency.text())
            self.current_point.expected_waveform = self.expected_waveform.text().strip() or None

            self.current_point.tolerance_voltage_v = to_float(self.tolerance_voltage.text())
            self.current_point.tolerance_current_a = to_float(self.tolerance_current.text())
            self.current_point.tolerance_frequency_hz = to_float(self.tolerance_frequency.text())

            self.current_point.notes = self.notes_field.toPlainText().strip() or None

            self.session.commit()

            # Remember selected point id before refresh
            selected_id = self.current_point.id
            self.refresh_points()

            # Re-select the same point
            for row in range(self.points_table.rowCount()):
                item = self.points_table.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == selected_id:
                    self.points_table.selectRow(row)
                    break

            self.show_status(f"Propriedades de {self.current_point.refdes} salvas", "success")
            self.point_updated.emit(self.current_point)
            logger.info(f"Propriedades atualizadas: {self.current_point.refdes}")

        except ValueError:
            self.show_status("Erro: valores numericos invalidos", "error")
        except Exception as e:
            logger.error(f"Erro ao salvar propriedades: {e}")
            self.show_status(f"Erro ao salvar: {str(e)}", "error")

    # ──────────────────────────────────────────────────────────────
    # POINT COLOR + MULTIMETER MEASUREMENTS
    # ──────────────────────────────────────────────────────────────
    def edit_marker_appearance(self, tp=None):
        tp = tp or self.current_point
        if tp is None:
            self.show_status("Selecione um ponto para alterar o marcador", "warning")
            return
        dlg = MarkerAppearanceDialog(tp, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        shape, size = dlg.values()
        try:
            tp.marker_shape = shape
            tp.marker_size = size
            self.session.add(tp)
            self.session.commit()
            item = self.test_point_items.get(tp.id)
            if item is not None:
                item.refresh_appearance()
            self.show_status(f"Marcador de {tp.refdes} atualizado", "success")
        except Exception as exc:
            self.session.rollback()
            logger.exception("Erro ao salvar aparência do ponto")
            self.show_status(f"Erro ao salvar marcador: {exc}", "error")

    def choose_point_color(self, tp=None):
        """Altera apenas a cor do ponto escolhido e persiste no SQLite."""
        tp = tp or self.current_point
        if tp is None:
            self.show_status("Selecione um ponto para alterar a cor", "warning")
            return
        initial = QColor(getattr(tp, "marker_color", None) or Theme.DEFAULT_POINT_COLOR)
        chosen = QColorDialog.getColor(initial, self, f"Cor de {tp.refdes}")
        if chosen.isValid():
            self._save_point_color(tp, chosen.name().upper())

    def reset_point_color(self, tp=None):
        tp = tp or self.current_point
        if tp is not None:
            self._save_point_color(tp, Theme.DEFAULT_POINT_COLOR)

    def _save_point_color(self, tp: TestPoint, color_hex: str):
        try:
            tp.marker_color = color_hex
            self.session.add(tp)
            self.session.commit()
            item = self.test_point_items.get(tp.id)
            if item is not None:
                # Recarrega apenas a representação gráfica desse ponto.
                self.view.scene().removeItem(item)
                new_item = TestPointItem(tp, self)
                self.view.scene().addItem(new_item)
                self.test_point_items[tp.id] = new_item
                new_item.set_selected_style(self.current_point is not None and self.current_point.id == tp.id)
            for row in range(self.points_table.rowCount()):
                cell = self.points_table.item(row, 0)
                if cell and cell.data(Qt.ItemDataRole.UserRole) == tp.id:
                    cell.setForeground(QColor(color_hex))
                    break
            self.show_status(f"Cor de {tp.refdes} salva", "success")
        except Exception as exc:
            self.session.rollback()
            logger.exception("Erro ao salvar cor do ponto")
            self.show_status(f"Erro ao salvar cor: {exc}", "error")

    def _persist_oscilloscope_reading(self, point_id: int, reading: OscilloscopeReading):
        """Vincula uma captura do osciloscópio ao ponto e grava o histórico."""
        import json

        tp = self.session.get(TestPoint, int(point_id))
        if tp is None:
            self.show_status("O ponto selecionado não existe mais", "error")
            return

        try:
            record = OscilloscopeCapture(
                test_point_id=tp.id,
                channel=int(reading.channel),
                vpp_v=reading.vpp_v,
                vrms_v=reading.vrms_v,
                vmax_v=reading.vmax_v,
                vmin_v=reading.vmin_v,
                vavg_v=reading.vavg_v,
                frequency_hz=reading.frequency_hz,
                period_s=reading.period_s,
                duty_cycle_pct=reading.duty_cycle_pct,
                vertical_offset_v=reading.vertical_offset_v,
                oscilloscope_id=reading.oscilloscope_id or None,
                raw_json=json.dumps(reading.raw or {}, ensure_ascii=False),
                waveform_json=(
                    json.dumps(reading.waveform, ensure_ascii=False)
                    if reading.waveform is not None else None
                ),
                timestamp=reading.timestamp,
            )
            tp.last_scope_channel = int(reading.channel)
            tp.last_scope_vpp_v = reading.vpp_v
            tp.last_scope_vrms_v = reading.vrms_v
            tp.last_scope_frequency_hz = reading.frequency_hz
            tp.last_scope_duty_pct = reading.duty_cycle_pct
            tp.last_scope_at = reading.timestamp
            tp.last_oscilloscope_id = reading.oscilloscope_id or None

            self.session.add(record)
            self.session.add(tp)
            self.session.commit()

            # Mantém a leitura capturada também como valor ao vivo da sessão e
            # atualiza somente a linha correspondente, sem recriar a tela.
            selected_id = tp.id
            self._live_scope_by_point[selected_id] = reading
            self._reference_cache = {
                ref.refdes: ref
                for ref in self.session.query(OscilloscopeReference)
                .filter_by(board_model_id=self.board.model_id).all()
            }
            row = self._find_point_row(selected_id)
            if row is not None:
                self._update_comparison_row(row, tp, reading)

            graphics_item = self.test_point_items.get(selected_id)
            if graphics_item is not None:
                graphics_item.tp = tp
                graphics_item.update_tooltip()

            if self.current_point is not None and self.current_point.id == tp.id:
                self.current_point = tp
                self._update_point_actions(self.mode == "edit")

            self.point_updated.emit(tp)
            self.show_status(
                f"CH{reading.channel} • Vpp={reading.vpp_v if reading.vpp_v is not None else '—'} V • "
                f"Vrms={reading.vrms_v if reading.vrms_v is not None else '—'} V • "
                f"F={reading.frequency_hz if reading.frequency_hz is not None else '—'} Hz "
                f"vinculados ao ponto {tp.refdes}",
                "success",
            )
            logger.info(
                "Captura de osciloscópio salva: point=%s channel=CH%s vpp=%s vrms=%s freq=%s scope=%s",
                tp.refdes, reading.channel, reading.vpp_v, reading.vrms_v, reading.frequency_hz, reading.oscilloscope_id,
            )
        except Exception as exc:
            self.session.rollback()
            logger.exception("Erro ao salvar captura do osciloscópio")
            self.show_status(f"Erro ao salvar captura: {exc}", "error")

    def open_measurement_dialog(self):
        """Compatibilidade: a medição usa o painel integrado do osciloscópio."""
        if self.current_point is None:
            self.show_status("Selecione um ponto antes de capturar", "warning")
            return
        self.oscilloscope_panel.capture_now()

    # ──────────────────────────────────────────────────────────────
    # CONTEXT MENUS
    # ──────────────────────────────────────────────────────────────
    def show_point_context_menu(self, tp: TestPoint, screen_pos):
        """Show context menu for a test point."""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {Theme.BG_SURFACE_ALT};
                color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background: {Theme.ACCENT_BLUE};
                color: {Theme.TEXT_BRIGHT};
            }}
        """)

        select_action = menu.addAction(f"Selecionar {tp.refdes}")
        select_action.triggered.connect(lambda: self.select_point(tp))

        if self.mode == "edit":
            edit_action = menu.addAction("Editar informações…")
            edit_action.triggered.connect(lambda: self.open_point_editor(tp))

        menu.addSeparator()
        capture_action = menu.addAction("Capturar do osciloscópio")
        capture_action.triggered.connect(lambda: self._capture_point_from_menu(tp))

        if self.mode == "edit":
            color_action = menu.addAction("Alterar cor…")
            color_action.triggered.connect(lambda: self.choose_point_color(tp))
            appearance_action = menu.addAction("Formato e tamanho…")
            appearance_action.triggered.connect(lambda: self.edit_marker_appearance(tp))
            reset_color_action = menu.addAction("Restaurar vermelho")
            reset_color_action.triggered.connect(lambda: self.reset_point_color(tp))
            menu.addSeparator()
            delete_action = menu.addAction(f"Excluir {tp.refdes}")
            delete_action.triggered.connect(lambda: self._delete_point_by_ref(tp))

        menu.exec(screen_pos)

    def _capture_point_from_menu(self, tp: TestPoint):
        self.select_point(tp)
        self.oscilloscope_panel.capture_now()

    def _delete_point_by_ref(self, tp: TestPoint):
        """Delete a specific point (from context menu)."""
        self.current_point = tp
        self.delete_current_point()

    def show_view_context_menu(self, scene_pos, screen_pos):
        """Show context menu for the canvas view."""
        if self.mode != "edit":
            return

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {Theme.BG_SURFACE_ALT};
                color: {Theme.TEXT_PRIMARY};
                border: 1px solid {Theme.BORDER_SUBTLE};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background: {Theme.ACCENT_BLUE};
                color: {Theme.TEXT_BRIGHT};
            }}
        """)

        add_action = menu.addAction(f"Adicionar ponto em ({int(scene_pos.x())}, {int(scene_pos.y())})")
        add_action.triggered.connect(
            lambda: self.add_point_by_click(scene_pos.x(), scene_pos.y())
        )
        menu.exec(screen_pos)

    def keyPressEvent(self, event):
        """Espaço captura a leitura atual do osciloscópio no ponto selecionado."""
        focus = QApplication.focusWidget()
        editing_text = isinstance(focus, (QLineEdit, QTextEdit, QComboBox))
        if (
            event.key() == Qt.Key.Key_Space
            and not editing_text
            and self.current_point is not None
        ):
            if self.oscilloscope_panel.is_continuous():
                if not self.oscilloscope_panel.capture_latest_for_selected():
                    self.oscilloscope_panel.capture_now()
            else:
                self.oscilloscope_panel.capture_now()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if hasattr(self, "oscilloscope_panel"):
            self.oscilloscope_panel.shutdown()
        super().closeEvent(event)

    # ──────────────────────────────────────────────────────────────
    # STATUS BAR
    # ──────────────────────────────────────────────────────────────
    def show_status(self, message, msg_type="info"):
        colors = {
            "info":    Theme.ACCENT_BLUE,
            "success": Theme.VCC_GREEN,
            "warning": Theme.ALERT_AMBER,
            "error":   Theme.ERROR_RED,
        }

        icons = {
            "info":    "INFO",
            "success": "OK",
            "warning": "WARN",
            "error":   "ERR",
        }

        color = colors.get(msg_type, Theme.TEXT_MUTED)
        icon = icons.get(msg_type, "")
        self.status_label.setText(f"[{icon}] {message}")
        self.status_label.setStyleSheet(f"""
            color: {color}; font-size: 10px;
            font-weight: 600; background: transparent;
        """)

        # Auto-clear for success messages
        if msg_type in ["success", "error"]:
            QTimer.singleShot(4000, lambda: self.status_label.setText("Pronto"))
            QTimer.singleShot(4000, lambda: self.status_label.setStyleSheet(f"""
                color: {Theme.TEXT_MUTED}; font-size: 10px;
                background: transparent;
            """))

    # ──────────────────────────────────────────────────────────────
    # BACKWARD COMPATIBILITY: set_points used by old TestApp
    # ──────────────────────────────────────────────────────────────
    @property
    def image_label(self):
        """Backward compat: return self as a duck-type for set_points."""
        return self

    def set_points(self, points_data):
        """Backward compat: legacy API used by old main.py TestApp."""
        pass