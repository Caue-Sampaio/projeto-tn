# ui/image_marker.py
# ──────────────────────────────────────────────────────────────────
# Redesign: Dark-mode professional UI for PCB test-point mapping.
# Style inspired by Altium Designer / KiCad / EasyEDA.
# ──────────────────────────────────────────────────────────────────
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFormLayout, QTextEdit, QMessageBox, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QGraphicsEllipseItem, QGraphicsTextItem,
    QComboBox, QSlider, QDialog, QDialogButtonBox, QSplitter, QFrame,
    QTabWidget, QMenu, QTableWidget, QTableWidgetItem, QHeaderView,
    QSpinBox, QInputDialog, QGraphicsDropShadowEffect, QGroupBox,
    QProgressBar, QListWidget, QListWidgetItem, QSizePolicy,
    QGraphicsRectItem
)
from PyQt6.QtGui import (
    QPixmap, QColor, QPen, QBrush, QWheelEvent, QFont, QPainter,
    QAction, QDoubleValidator, QLinearGradient, QRadialGradient
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QPointF, QRectF, QTimer, QPropertyAnimation,
    QEasingCurve
)
from db.models import TestPoint, BoardUnit, Measurement
from sqlalchemy.orm import Session
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
class TestPointItem(QGraphicsEllipseItem):
    """Interactive graphics item representing a test point on the PCB canvas."""

    def __init__(self, tp: TestPoint, marker_widget):
        base_size = 14
        super().__init__(-base_size / 2, -base_size / 2, base_size, base_size)
        self.tp = tp
        self.marker_widget = marker_widget
        self.base_size = base_size
        self._selected = False

        # Determine color from type/refdes
        color_hex = Theme.point_color(tp.refdes, tp.expected_voltage_v)
        self._color = QColor(color_hex)
        self._color_hover = QColor(color_hex)
        self._color_hover.setAlpha(255)
        self._color_base = QColor(color_hex)
        self._color_base.setAlpha(200)

        # Appearance
        self.setBrush(QBrush(self._color_base))
        pen = QPen(QColor(color_hex))
        pen.setWidth(2)
        self.setPen(pen)

        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        # Label
        self.label = QGraphicsTextItem(tp.refdes, self)
        self.label.setDefaultTextColor(QColor(Theme.TEXT_PRIMARY))
        self.label.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        self.update_label_position()

        # Position
        self.setPos(tp.x, tp.y)

        # Rich tooltip
        tooltip_lines = [f"{tp.refdes}"]
        if tp.expected_voltage_v is not None:
            tooltip_lines.append(f"Tensao: {tp.expected_voltage_v:.2f} V")
        if tp.tolerance_voltage_v is not None:
            tooltip_lines.append(f"Tolerancia: +/-{tp.tolerance_voltage_v:.2f} V")
        tooltip_lines.append(f"Pos: ({tp.x}, {tp.y})")
        self.setToolTip("\n".join(tooltip_lines))

    def update_label_position(self):
        text_rect = self.label.boundingRect()
        self.label.setPos(-text_rect.width() / 2, -self.base_size - 10)

    def update_size_based_on_zoom(self, zoom_level):
        new_size = max(6, self.base_size / zoom_level)
        self.setRect(-new_size / 2, -new_size / 2, new_size, new_size)
        font_size = max(5, int(7 / zoom_level))
        self.label.setFont(QFont("Consolas", font_size, QFont.Weight.Bold))
        self.update_label_position()

    def set_selected_style(self, selected: bool):
        self._selected = selected
        if selected:
            glow = QColor(Theme.ACCENT_CYAN)
            glow.setAlpha(120)
            pen = QPen(QColor(Theme.ACCENT_CYAN))
            pen.setWidth(3)
            self.setPen(pen)
            # Make the point brighter
            bright = QColor(self._color.name())
            bright.setAlpha(255)
            self.setBrush(QBrush(bright))
        else:
            pen = QPen(QColor(self._color.name()))
            pen.setWidth(2)
            self.setPen(pen)
            self.setBrush(QBrush(self._color_base))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.marker_widget.select_point(self.tp)
        elif event.button() == Qt.MouseButton.RightButton:
            screen_pos = event.screenPos()
            self.marker_widget.show_point_context_menu(self.tp, screen_pos)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        center = self.sceneBoundingRect().center()
        self.tp.x = int(center.x())
        self.tp.y = int(center.y())
        self.marker_widget.session.add(self.tp)
        self.marker_widget.session.commit()
        self.update_label_position()
        logger.debug(f"Ponto {self.tp.refdes} movido para ({self.tp.x}, {self.tp.y})")
        super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event):
        if not self._selected:
            pen = QPen(QColor(Theme.ACCENT_CYAN))
            pen.setWidth(2)
            self.setPen(pen)
            self.setBrush(QBrush(self._color_hover))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self._selected:
            pen = QPen(QColor(self._color.name()))
            pen.setWidth(2)
            self.setPen(pen)
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
        self.test_point_items = {}

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

        # LEFT: Canvas panel (60%)
        left_panel = self._build_canvas_panel()
        splitter.addWidget(left_panel)

        # RIGHT: Control panel (40%)
        right_panel = self._build_side_panel()
        splitter.addWidget(right_panel)

        splitter.setSizes([720, 480])
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)
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

        # ── Splitter for table + form ──
        inner_splitter = QSplitter(Qt.Orientation.Vertical)
        inner_splitter.setChildrenCollapsible(False)

        # Points table
        table_card = self._build_points_table()
        inner_splitter.addWidget(table_card)

        # Edit form
        form_card = self._build_edit_form()
        inner_splitter.addWidget(form_card)

        inner_splitter.setSizes([320, 380])
        inner_splitter.setStretchFactor(0, 4)
        inner_splitter.setStretchFactor(1, 6)

        layout.addWidget(inner_splitter, 1)

        return panel

    def _build_points_table(self):
        """Build the points data table."""
        card = QFrame()
        card.setObjectName("tableCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 8, 0, 0)
        card_layout.setSpacing(0)

        # Table
        self.points_table = QTableWidget()
        self.points_table.setObjectName("pointsTable")
        self.points_table.setColumnCount(5)
        self.points_table.setHorizontalHeaderLabels([
            "   ID", "Tipo", "Tensao", "Toler.", "Pos (X,Y)"
        ])
        self.points_table.verticalHeader().setVisible(False)
        self.points_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.points_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.points_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.points_table.setAlternatingRowColors(True)
        self.points_table.setShowGrid(False)

        header = self.points_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.points_table.itemSelectionChanged.connect(self._on_table_selection_changed)

        card_layout.addWidget(self.points_table)
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
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # RefDes (read-only display)
        self.refdes_label = QLabel("-")
        self.refdes_label.setObjectName("formValueLabel")
        form_layout.addRow(self._make_label("RefDes"), self.refdes_label)

        # Coordinates (read-only display)
        self.coords_display = QLabel("-")
        self.coords_display.setObjectName("formValueLabel")
        form_layout.addRow(self._make_label("Coordenadas"), self.coords_display)

        # Voltage
        self.expected_voltage = QLineEdit()
        self.expected_voltage.setPlaceholderText("Ex: 3.3, 5.0, 12.0")
        self.expected_voltage.setObjectName("formInput")
        self.expected_voltage.setValidator(QDoubleValidator(-1000, 1000, 4))
        self.expected_voltage.textChanged.connect(lambda: self._validate_field(self.expected_voltage))
        form_layout.addRow(self._make_label("Tensao (V)"), self.expected_voltage)

        # Current
        self.expected_current = QLineEdit()
        self.expected_current.setPlaceholderText("Ex: 0.1, 0.5, 1.0")
        self.expected_current.setObjectName("formInput")
        self.expected_current.setValidator(QDoubleValidator(-100, 100, 4))
        self.expected_current.textChanged.connect(lambda: self._validate_field(self.expected_current))
        form_layout.addRow(self._make_label("Corrente (A)"), self.expected_current)

        # Frequency
        self.expected_frequency = QLineEdit()
        self.expected_frequency.setPlaceholderText("Ex: 1000, 12000")
        self.expected_frequency.setObjectName("formInput")
        self.expected_frequency.setValidator(QDoubleValidator(0, 1e12, 2))
        self.expected_frequency.textChanged.connect(lambda: self._validate_field(self.expected_frequency))
        form_layout.addRow(self._make_label("Frequencia (Hz)"), self.expected_frequency)

        # Waveform
        self.expected_waveform = QLineEdit()
        self.expected_waveform.setPlaceholderText("Senoidal, Quadrada...")
        self.expected_waveform.setObjectName("formInput")
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
        self.tolerance_voltage.setValidator(QDoubleValidator(0, 1000, 4))
        self.tolerance_voltage.textChanged.connect(lambda: self._validate_field(self.tolerance_voltage))
        form_layout.addRow(self._make_label("Toler. Tensao"), self.tolerance_voltage)

        # Tolerance current
        self.tolerance_current = QLineEdit()
        self.tolerance_current.setPlaceholderText("+/- A")
        self.tolerance_current.setObjectName("formInput")
        self.tolerance_current.setValidator(QDoubleValidator(0, 100, 4))
        self.tolerance_current.textChanged.connect(lambda: self._validate_field(self.tolerance_current))
        form_layout.addRow(self._make_label("Toler. Corrente"), self.tolerance_current)

        # Tolerance frequency
        self.tolerance_frequency = QLineEdit()
        self.tolerance_frequency.setPlaceholderText("+/- Hz")
        self.tolerance_frequency.setObjectName("formInput")
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
        self.notes_field.setMaximumHeight(64)
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

        # Measure button (edit mode only)
        if self.mode == "edit":
            self.measure_btn = QPushButton("Medir")
            self.measure_btn.setObjectName("measureBtn")
            self.measure_btn.setFixedHeight(34)
            self.measure_btn.clicked.connect(self.open_measurement_dialog)
            btn_layout.addWidget(self.measure_btn)

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
    def load_image(self, path: str):
        """Load a PCB image into the canvas viewer."""
        self.image_path = path
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
    def refresh_points(self):
        """Reload all test points from DB into the table and canvas."""
        # Clear table
        self.points_table.setRowCount(0)
        self.test_point_items.clear()

        # Remove old items from scene
        for item in self.view.scene().items():
            if isinstance(item, TestPointItem):
                self.view.scene().removeItem(item)

        # Load points
        points = self.session.query(TestPoint).filter_by(board_id=self.board.id).all()

        for row_idx, tp in enumerate(points):
            # ── Add to table ──
            self.points_table.insertRow(row_idx)

            # ID with color indicator
            id_item = QTableWidgetItem(f"  {tp.refdes}")
            color_hex = Theme.point_color(tp.refdes, tp.expected_voltage_v)
            id_item.setForeground(QColor(color_hex))
            id_item.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
            id_item.setData(Qt.ItemDataRole.UserRole, tp.id)
            self.points_table.setItem(row_idx, 0, id_item)

            # Type
            type_label = Theme.point_type_label(tp.refdes, tp.expected_voltage_v)
            type_item = QTableWidgetItem(type_label)
            type_item.setForeground(QColor(color_hex))
            type_item.setFont(QFont("Segoe UI", 9))
            self.points_table.setItem(row_idx, 1, type_item)

            # Voltage
            if tp.expected_voltage_v is not None:
                v_text = f"{tp.expected_voltage_v:.2f} V"
            else:
                v_text = "--"
            v_item = QTableWidgetItem(v_text)
            v_item.setFont(QFont("Consolas", 10))
            v_item.setForeground(QColor(Theme.TEXT_PRIMARY if tp.expected_voltage_v else Theme.TEXT_MUTED))
            self.points_table.setItem(row_idx, 2, v_item)

            # Tolerance
            if tp.tolerance_voltage_v is not None:
                t_text = f"+/-{tp.tolerance_voltage_v:.2f}"
            else:
                t_text = "--"
            t_item = QTableWidgetItem(t_text)
            t_item.setFont(QFont("Consolas", 9))
            t_item.setForeground(QColor(Theme.TEXT_MUTED))
            self.points_table.setItem(row_idx, 3, t_item)

            # Position
            pos_item = QTableWidgetItem(f"({tp.x}, {tp.y})")
            pos_item.setFont(QFont("Consolas", 9))
            pos_item.setForeground(QColor(Theme.TEXT_MUTED))
            self.points_table.setItem(row_idx, 4, pos_item)

            # ── Add to canvas ──
            tp_item = TestPointItem(tp, self)
            self.view.scene().addItem(tp_item)
            self.test_point_items[tp.id] = tp_item

        # Update sizes
        self.update_points_size()
        self.points_count_label.setText(f"{len(points)} pontos")
        self.show_status(f"Carregados {len(points)} pontos de teste")

    def _on_table_selection_changed(self):
        """Handle selection change in the points table."""
        rows = self.points_table.selectionModel().selectedRows()
        if not rows:
            self.current_point = None
            self.clear_point_form()
            self._update_form_buttons(False)
            # Deselect all canvas points
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
            self.populate_point_form(self.current_point)
            self._update_form_buttons(self.mode == "edit")

            # Highlight on canvas
            for tid, tp_item in self.test_point_items.items():
                tp_item.set_selected_style(tid == tp_id)

            # Center view on selected point
            if tp_id in self.test_point_items:
                self.view.centerOn(self.test_point_items[tp_id])

            self.point_selected.emit(self.current_point)

    def select_point(self, tp: TestPoint):
        """Select a point programmatically (e.g., from canvas click)."""
        self.current_point = tp
        self.populate_point_form(tp)
        self._update_form_buttons(self.mode == "edit")

        # Select in table
        for row in range(self.points_table.rowCount()):
            item = self.points_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == tp.id:
                self.points_table.blockSignals(True)
                self.points_table.selectRow(row)
                self.points_table.blockSignals(False)
                break

        # Highlight on canvas
        for tid, tp_item in self.test_point_items.items():
            tp_item.set_selected_style(tid == tp.id)

        self.point_selected.emit(tp)

    def populate_point_form(self, tp: TestPoint):
        """Fill the form with test point data."""
        if not tp:
            return

        self.form_title.setText(f"{tp.refdes}")
        color_hex = Theme.point_color(tp.refdes, tp.expected_voltage_v)
        self.form_title.setStyleSheet(f"color: {color_hex}; font-size: 14px; font-weight: 800;")

        self.refdes_label.setText(tp.refdes or "-")
        self.coords_display.setText(f"({tp.x}, {tp.y})")

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
                y=y
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
                self.clear_point_form()
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
    # MEASUREMENTS
    # ──────────────────────────────────────────────────────────────
    def open_measurement_dialog(self):
        dialog = MeasurementDialog(self.instruments, self)
        if dialog.exec():
            result = dialog.get_measurement_result()
            if result is not None and self.current_point:
                self.show_status(f"Medicao realizada: {result}", "success")

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
            menu.addSeparator()
            delete_action = menu.addAction(f"Excluir {tp.refdes}")
            delete_action.triggered.connect(lambda: self._delete_point_by_ref(tp))

        menu.exec(screen_pos)

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