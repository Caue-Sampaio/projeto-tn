from __future__ import annotations

import json
import os
from datetime import datetime

from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QPen, QPixmap, QFont, QDoubleValidator, QPainter
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QFrame, QSplitter, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsPathItem, QGraphicsTextItem, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QDialog, QDialogButtonBox, QFormLayout,
    QLineEdit, QTextEdit, QSlider, QInputDialog, QMenu, QColorDialog
)

from db.models import BoardUnit, TestPoint, OscilloscopeReference
from ui.marker_graphics import build_marker_path, normalize_marker_shape, normalize_marker_size, MarkerAppearanceDialog
from oscilloscope.base import OscilloscopeReading
from ui.oscilloscope_panel import OscilloscopePanel


class RefTheme:
    # Página de referência: fundo preto real para destacar PCB e osciloscópio.
    BG_PRIMARY = "#000000"
    BG_SURFACE = "#0B0F14"
    BG_SURFACE_ALT = "#111722"
    BG_INPUT = "#151C28"
    BG_HOVER = "#182231"
    BG_CANVAS = "#030507"
    BORDER_SUBTLE = "#263244"
    TEXT_PRIMARY = "#E2E8F0"
    TEXT_SECONDARY = "#94A3B8"
    TEXT_MUTED = "#64748B"
    TEXT_BRIGHT = "#F8FAFC"
    ACCENT_CYAN = "#00D4FF"
    ACCENT_BLUE = "#0EA5E9"
    VCC_GREEN = "#22C55E"
    ALERT_AMBER = "#F59E0B"
    ERROR_RED = "#EF4444"
    DEFAULT_POINT_COLOR = "#E53935"


class ReferenceGraphicsView(QGraphicsView):
    """Canvas da placa com pan, zoom e posicionamento de novos pontos."""

    point_place_requested = pyqtSignal(float, float)
    zoom_changed = pyqtSignal(int)

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._zoom_percent = 100
        self._placement_mode = False
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def set_placement_mode(self, enabled: bool):
        self._placement_mode = bool(enabled)
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.setDragMode(
            QGraphicsView.DragMode.NoDrag if enabled
            else QGraphicsView.DragMode.ScrollHandDrag
        )

    def fit_scene(self):
        rect = self.scene().sceneRect()
        if rect.isNull():
            rect = self.scene().itemsBoundingRect()
        if rect.isNull():
            return
        self.resetTransform()
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom_percent = 100
        self.zoom_changed.emit(100)

    def set_zoom_percent(self, value: int):
        value = max(25, min(400, int(value)))
        if value == self._zoom_percent:
            return
        factor = value / float(self._zoom_percent)
        self.scale(factor, factor)
        self._zoom_percent = value
        self.zoom_changed.emit(value)

    def wheelEvent(self, event):
        if not self.scene().items():
            return super().wheelEvent(event)
        step = 115 / 100 if event.angleDelta().y() > 0 else 100 / 115
        target = int(round(self._zoom_percent * step))
        target = max(25, min(400, target))
        self.set_zoom_percent(target)
        event.accept()

    def mousePressEvent(self, event):
        if self._placement_mode and event.button() == Qt.MouseButton.LeftButton:
            pos = self.mapToScene(event.position().toPoint())
            if self.scene().sceneRect().contains(pos):
                self.point_place_requested.emit(pos.x(), pos.y())
                event.accept()
                return
        super().mousePressEvent(event)


class ReferencePointItem(QGraphicsPathItem):
    """Ponto da placa na aba Referências.

    Usa o mesmo comportamento básico do mapeamento principal: selecionar,
    arrastar para mover, duplo clique e menu de contexto.
    """

    def __init__(self, point: TestPoint, owner: "ReferenceMeasurements"):
        super().__init__()
        self.point = point
        self.owner = owner
        self.setPos(point.x, point.y)
        self._apply_color(getattr(point, "marker_color", None) or RefTheme.DEFAULT_POINT_COLOR)
        self.setZValue(20)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self.label = QGraphicsTextItem(point.refdes, self)
        self.label.setDefaultTextColor(QColor("#FFFFFF"))
        self.label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.update_appearance()
        self._update_tooltip()

    def _apply_color(self, color_hex: str):
        self._color_hex = color_hex
        color = QColor(color_hex)
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor("#FFFFFF"), 1.3))

    def update_color(self, color_hex: str):
        self._apply_color(color_hex)
        self.set_selected(
            self.owner.current_point is not None
            and self.owner.current_point.id == self.point.id
        )
        self._update_tooltip()

    def update_appearance(self):
        shape = normalize_marker_shape(getattr(self.point, "marker_shape", None))
        size = normalize_marker_size(getattr(self.point, "marker_size", None))
        self.setPath(build_marker_path(shape, size))
        self.label.setPos(size / 2 + 3, -size / 2 - 8)
        self._update_tooltip()

    def _update_tooltip(self):
        self.setToolTip(
            f"{self.point.refdes}\n"
            f"Posição: ({self.point.x}, {self.point.y})\n"
            f"Marcador: {normalize_marker_shape(getattr(self.point, 'marker_shape', None))} • "
            f"{normalize_marker_size(getattr(self.point, 'marker_size', None))} px\n"
            "Arraste para mover • botão direito para opções"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.owner.select_point(self.point)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            # Não consome o evento: o QGraphicsItem precisa recebê-lo para mover.
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.owner.select_point(self.point)
            self.owner.show_point_context_menu(self.point, event.screenPos())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if event.button() == Qt.MouseButton.LeftButton:
            pos = self.pos()
            new_x = int(round(pos.x()))
            new_y = int(round(pos.y()))
            if new_x != self.point.x or new_y != self.point.y:
                self.owner.point_moved(self.point, new_x, new_y)
            self._update_tooltip()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.owner.select_point(self.point)
            self.owner.edit_reference()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def set_selected(self, selected: bool):
        if selected:
            self.setPen(QPen(QColor(RefTheme.ACCENT_CYAN), 2.5))
        else:
            self.setPen(QPen(QColor("#FFFFFF"), 1.3))


class ReferenceEditDialog(QDialog):
    def __init__(self, point: TestPoint, reference: OscilloscopeReference | None, parent=None):
        super().__init__(parent)
        self.point = point
        self.reference = reference
        self.setWindowTitle(f"Referência correta — {point.refdes}")
        self.setMinimumWidth(500)
        self._build()
        self._load()
        self._style()

    def _number(self, label: str, suffix: str = ""):
        edit = QLineEdit()
        edit.setPlaceholderText(suffix)
        edit.setValidator(QDoubleValidator(-1e12, 1e12, 9, edit))
        self.form.addRow(label, edit)
        return edit

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        title = QLabel(f"{self.point.refdes} — medição correta")
        title.setObjectName("title")
        root.addWidget(title)
        info = QLabel("Você pode capturar pelo osciloscópio ou corrigir os valores manualmente.")
        info.setObjectName("muted")
        root.addWidget(info)

        self.form = QFormLayout()
        self.form.setVerticalSpacing(9)
        self.channel = self._number("Canal", "1 a 4")
        self.vpp = self._number("Vpp correto (V)")
        self.vrms = self._number("Vrms correto (V)")
        self.freq = self._number("Frequência correta (Hz)")
        self.duty = self._number("Duty correto (%)")
        self.vmax = self._number("Vmax (V)")
        self.vmin = self._number("Vmin (V)")
        self.vavg = self._number("V médio / DC (V)")
        self.tol_vpp = self._number("Tolerância Vpp (%)")
        self.tol_vrms = self._number("Tolerância Vrms (%)")
        self.tol_freq = self._number("Tolerância frequência (%)")
        root.addLayout(self.form)

        root.addWidget(QLabel("Observações"))
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(90)
        root.addWidget(self.notes)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @staticmethod
    def _set(edit: QLineEdit, value):
        edit.setText("" if value is None else f"{value:g}")

    def _load(self):
        ref = self.reference
        self._set(self.channel, getattr(ref, "channel", 1) if ref else 1)
        self._set(self.vpp, getattr(ref, "vpp_v", None))
        self._set(self.vrms, getattr(ref, "vrms_v", None))
        self._set(self.freq, getattr(ref, "frequency_hz", None))
        self._set(self.duty, getattr(ref, "duty_cycle_pct", None))
        self._set(self.vmax, getattr(ref, "vmax_v", None))
        self._set(self.vmin, getattr(ref, "vmin_v", None))
        self._set(self.vavg, getattr(ref, "vavg_v", None))
        self._set(self.tol_vpp, getattr(ref, "tolerance_vpp_pct", 10.0) if ref else 10.0)
        self._set(self.tol_vrms, getattr(ref, "tolerance_vrms_pct", 10.0) if ref else 10.0)
        self._set(self.tol_freq, getattr(ref, "tolerance_frequency_pct", 5.0) if ref else 5.0)
        self.notes.setPlainText(getattr(ref, "notes", "") or "")

    @staticmethod
    def _float(edit: QLineEdit):
        value = edit.text().strip().replace(",", ".")
        return float(value) if value else None

    def values(self):
        channel = int(self._float(self.channel) or 1)
        return {
            "channel": max(1, min(channel, 4)),
            "vpp_v": self._float(self.vpp),
            "vrms_v": self._float(self.vrms),
            "frequency_hz": self._float(self.freq),
            "duty_cycle_pct": self._float(self.duty),
            "vmax_v": self._float(self.vmax),
            "vmin_v": self._float(self.vmin),
            "vavg_v": self._float(self.vavg),
            "tolerance_vpp_pct": self._float(self.tol_vpp) or 10.0,
            "tolerance_vrms_pct": self._float(self.tol_vrms) or 10.0,
            "tolerance_frequency_pct": self._float(self.tol_freq) or 5.0,
            "notes": self.notes.toPlainText().strip() or None,
        }

    def _style(self):
        t = RefTheme
        self.setStyleSheet(f"""
            QDialog {{ background:{t.BG_PRIMARY}; color:{t.TEXT_PRIMARY}; }}
            QLabel#title {{ color:{t.TEXT_BRIGHT}; font-size:16px; font-weight:800; }}
            QLabel#muted {{ color:{t.TEXT_MUTED}; }}
            QLineEdit, QTextEdit {{ background:{t.BG_INPUT}; color:{t.TEXT_PRIMARY};
                border:1px solid {t.BORDER_SUBTLE}; border-radius:5px; padding:6px 8px; }}
            QLineEdit:focus, QTextEdit:focus {{ border-color:{t.ACCENT_BLUE}; }}
            QPushButton {{ background:{t.BG_SURFACE_ALT}; color:{t.TEXT_PRIMARY};
                border:1px solid {t.BORDER_SUBTLE}; border-radius:5px; padding:7px 14px; }}
        """)


class ReferenceMeasurements(QWidget):
    """Única tela extra para cadastrar as medições corretas de placas boas."""

    def __init__(self, session, current_user=None, parent=None):
        super().__init__(parent)
        self.session = session
        self.current_user = current_user
        self.current_board: BoardUnit | None = None
        self.current_point: TestPoint | None = None
        self.current_image_slot: int = 1
        self.point_items: dict[int, ReferencePointItem] = {}
        self._build_ui()
        self._apply_style()
        self.refresh_boards()

    def _build_ui(self):
        # A página usa toda a área disponível. O fundo do widget raiz é preto
        # para que qualquer pequeno espaço entre os blocos nunca apareça branco.
        self.setObjectName("referencePage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Cabeçalho compacto: mantém o contexto sem consumir área útil.
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(44)
        h = QHBoxLayout(header)
        h.setContentsMargins(12, 0, 12, 0)
        h.setSpacing(10)

        title = QLabel("MEDIÇÕES DE REFERÊNCIA")
        title.setObjectName("pageTitle")
        h.addWidget(title)

        separator = QLabel("•")
        separator.setObjectName("muted")
        h.addWidget(separator)

        subtitle = QLabel("Valores corretos da placa boa para comparação no reparo")
        subtitle.setObjectName("headerSubtitle")
        h.addWidget(subtitle)
        h.addStretch()

        root.addWidget(header)

        # Seleção de placa no MESMO padrão da aba Testes.
        # Em vez de um combo com todas as placas misturadas, mostramos um card
        # compacto e reutilizamos o mesmo diálogo Máquina -> Placa.
        board_select_card = QFrame()
        board_select_card.setObjectName("boardSelectCard")
        board_select_layout = QHBoxLayout(board_select_card)
        board_select_layout.setContentsMargins(12, 7, 12, 7)
        board_select_layout.setSpacing(10)

        board_info = QVBoxLayout()
        board_info.setSpacing(2)

        caption = QLabel("PLACA DE REFERÊNCIA")
        caption.setObjectName("caption")
        self.selected_board_label = QLabel("Nenhuma placa selecionada")
        self.selected_board_label.setObjectName("infoValue")
        self.selected_board_label.setWordWrap(True)
        self.selected_board_meta = QLabel("Máquina: —   •   Modelo: —   •   SN: —")
        self.selected_board_meta.setObjectName("muted")
        self.selected_board_meta.setWordWrap(True)

        board_info.addWidget(caption)
        board_info.addWidget(self.selected_board_label)
        board_info.addWidget(self.selected_board_meta)
        board_select_layout.addLayout(board_info, 1)

        self.select_board_btn = QPushButton("Selecionar máquina/placa")
        self.select_board_btn.setObjectName("selectBoardBtn")
        self.select_board_btn.setMinimumWidth(190)
        self.select_board_btn.setFixedHeight(38)
        self.select_board_btn.clicked.connect(self.select_board)
        board_select_layout.addWidget(self.select_board_btn)

        root.addWidget(board_select_card)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainReferenceSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(4)

        # LEFT 50%: imagem + pontos
        left = QFrame()
        left.setObjectName("panel")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(8, 8, 8, 8)
        lv.setSpacing(6)
        bar = QHBoxLayout()
        bar.setSpacing(7)
        self.board_label = QLabel("Nenhuma placa selecionada")
        self.board_label.setObjectName("sectionTitle")
        bar.addWidget(self.board_label)

        self.image1_btn = QPushButton("Img 1")
        self.image2_btn = QPushButton("Img 2")
        for _btn in (self.image1_btn, self.image2_btn):
            _btn.setCheckable(True)
            _btn.setFixedWidth(52)
        self.image1_btn.setChecked(True)
        self.image1_btn.clicked.connect(lambda: self.set_image_slot(1))
        self.image2_btn.clicked.connect(lambda: self.set_image_slot(2))
        bar.addWidget(self.image1_btn)
        bar.addWidget(self.image2_btn)
        bar.addStretch()

        # Criação de ponto diretamente na aba de referência. O ponto é salvo
        # em TestPoint, portanto aparece também na tela normal de Testes.
        self.add_point_btn = QPushButton("+ Novo ponto")
        self.add_point_btn.setObjectName("addPointBtn")
        self.add_point_btn.setCheckable(True)
        self.add_point_btn.setToolTip("Ative e clique na posição desejada sobre a placa")
        self.add_point_btn.toggled.connect(self._toggle_point_placement)
        bar.addWidget(self.add_point_btn)

        zoom_text = QLabel("Zoom")
        zoom_text.setObjectName("muted")
        bar.addWidget(zoom_text)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(25, 400)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(105)
        self.zoom_slider.setToolTip("Zoom da imagem da placa")
        bar.addWidget(self.zoom_slider)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("zoomValue")
        self.zoom_label.setFixedWidth(42)
        bar.addWidget(self.zoom_label)

        self.fit_btn = QPushButton("Fit")
        self.fit_btn.setToolTip("Ajustar a placa à área disponível")
        self.fit_btn.clicked.connect(self.fit_image)
        bar.addWidget(self.fit_btn)
        lv.addLayout(bar)

        self.scene = QGraphicsScene(self)
        self.view = ReferenceGraphicsView(self.scene, self)
        self.view.setObjectName("boardView")
        self.view.zoom_changed.connect(self._view_zoom_changed)
        self.view.point_place_requested.connect(self._place_new_point)
        self.zoom_slider.valueChanged.connect(self.view.set_zoom_percent)
        lv.addWidget(self.view, 1)
        splitter.addWidget(left)

        # RIGHT 50%: osciloscópio + referências
        right = QFrame()
        right.setObjectName("panel")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 8, 8, 8)
        rv.setSpacing(6)

        self.scope = OscilloscopePanel(RefTheme, self)
        self.scope.capture_requested.connect(self._save_capture_as_reference)
        self.scope.status_changed.connect(self._status_from_scope)
        self.scope.capture_btn.setText("Salvar como referência")
        rv.addWidget(self.scope)

        actions = QHBoxLayout()
        self.selection_label = QLabel("Ponto: nenhum")
        self.selection_label.setObjectName("muted")
        actions.addWidget(self.selection_label)
        actions.addStretch()

        self.point_options_btn = QPushButton("Opções do ponto")
        self.point_options_btn.setEnabled(False)
        self.point_options_btn.setToolTip("Mover, editar informações, alterar cor ou excluir o ponto")
        self.point_options_btn.clicked.connect(self._show_selected_point_menu)
        actions.addWidget(self.point_options_btn)

        self.edit_btn = QPushButton("Editar referência")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self.edit_reference)
        actions.addWidget(self.edit_btn)
        self.clear_btn = QPushButton("Limpar referência")
        self.clear_btn.setEnabled(False)
        self.clear_btn.clicked.connect(self.clear_reference)
        actions.addWidget(self.clear_btn)
        rv.addLayout(actions)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "Ponto", "Vpp correto", "Vrms correto", "Freq. correta",
            "Tol. Vpp", "Tol. Vrms", "Tol. Freq.", "Onda", "Atualizado"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        hdr = self.table.horizontalHeader()
        for col in range(8):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._table_selection)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit_reference())
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_context_menu)
        rv.addWidget(self.table, 1)

        self.status = QLabel("Pronto")
        self.status.setObjectName("muted")
        rv.addWidget(self.status)
        splitter.addWidget(right)

        splitter.setSizes([600, 600])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

    def refresh_boards(self):
        """Atualiza o card da placa sem usar um combo global de placas."""
        self._update_selected_board_card()
        if self.current_board is None:
            self._board_changed(None)

    def open_for_board(self, board_id: int) -> bool:
        """Abre a página de referências já contextualizada para uma placa.

        Usado por PlacaDetalhes. É o equivalente ao contexto
        ``/preferencias?placaId=<id>`` em uma aplicação desktop PyQt6.
        """
        board = self.session.get(BoardUnit, int(board_id))
        if board is None:
            return False
        self._board_changed(board)
        return True

    def select_board(self):
        """Abre exatamente o mesmo seletor Máquina -> Placa usado na aba Testes."""
        has_boards = self.session.query(BoardUnit).filter_by(is_active=True).first() is not None
        if not has_boards:
            QMessageBox.warning(self, "Aviso", "Nenhuma placa ativa cadastrada.")
            return

        # Import local para evitar acoplamento/ciclo durante a inicialização da UI.
        # Dessa forma a aba Referências usa o MESMO diálogo da aba Testes.
        from ui.test_executor import BoardSelectDialog

        dialog = BoardSelectDialog(self.session, self, self.current_board)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_board is None:
            return

        self._board_changed(dialog.selected_board)

    def _update_selected_board_card(self):
        board = self.current_board
        if board is None:
            self.selected_board_label.setText("Nenhuma placa selecionada")
            self.selected_board_meta.setText("Máquina: —   •   Modelo: —   •   SN: —")
            self.select_board_btn.setText("Selecionar máquina/placa")
            return

        model_name = board.board_model.name if getattr(board, "board_model", None) else (board.model or "—")
        machine_name = board.machine.name if getattr(board, "machine", None) else "Sem máquina"
        serial = board.serial_number or "—"

        self.selected_board_label.setText(board.name or "Placa sem nome")
        self.selected_board_meta.setText(
            f"Máquina: {machine_name}   •   Modelo: {model_name}   •   SN: {serial}"
        )
        self.select_board_btn.setText("Trocar máquina/placa")

    def _board_changed(self, board=None):
        if hasattr(self, "add_point_btn") and self.add_point_btn.isChecked():
            self._end_point_placement()
        self.current_board = board
        self.current_image_slot = 1
        self.current_point = None
        self.scope.set_selected_point(None)
        self.scope.clear_reference_waveform()
        self.edit_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        if hasattr(self, "point_options_btn"):
            self.point_options_btn.setEnabled(False)
        self.selection_label.setText("Ponto: nenhum")
        self._update_selected_board_card()
        self._load_board_scene()
        self.refresh_table()

    def _load_board_scene(self):
        self.scene.clear()
        self.point_items.clear()
        if not self.current_board:
            self.board_label.setText("Nenhuma placa selecionada")
            return
        self.board_label.setText(
            f"{self.current_board.name} — modelo {self.current_board.board_model.name if self.current_board.board_model else self.current_board.model}"
        )
        images = sorted(self.current_board.images, key=lambda x: (x.created_at or datetime.min, x.id or 0))
        image = images[self.current_image_slot - 1] if len(images) >= self.current_image_slot else None
        if image:
            path = image.path
            if not os.path.isabs(path):
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                candidate = os.path.join(project_root, path)
                if os.path.exists(candidate):
                    path = candidate
            pix = QPixmap(path)
            if not pix.isNull():
                self.scene.addItem(QGraphicsPixmapItem(pix))
                self.scene.setSceneRect(QRectF(pix.rect()))

        points = self.session.query(TestPoint).filter_by(board_id=self.current_board.id).all()
        points = [p for p in points if int(getattr(p, "image_slot", 1) or 1) == self.current_image_slot]
        for point in points:
            item = ReferencePointItem(point, self)
            self.scene.addItem(item)
            self.point_items[point.id] = item
        self.fit_image()

    def set_image_slot(self, slot: int):
        self.current_image_slot = 2 if int(slot) == 2 else 1
        self.image1_btn.blockSignals(True); self.image2_btn.blockSignals(True)
        self.image1_btn.setChecked(self.current_image_slot == 1)
        self.image2_btn.setChecked(self.current_image_slot == 2)
        self.image1_btn.blockSignals(False); self.image2_btn.blockSignals(False)
        self.current_point = None
        self.scope.set_selected_point(None)
        self.scope.clear_reference_waveform()
        self.selection_label.setText("Ponto: nenhum")
        self._load_board_scene()

    def fit_image(self):
        if not self.scene.items():
            return
        self.view.fit_scene()

    def _view_zoom_changed(self, value: int):
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(int(value))
        self.zoom_slider.blockSignals(False)
        self.zoom_label.setText(f"{int(value)}%")

    def _toggle_point_placement(self, enabled: bool):
        if enabled and not self.current_board:
            QMessageBox.information(self, "Novo ponto", "Selecione primeiro uma máquina/placa.")
            self.add_point_btn.blockSignals(True)
            self.add_point_btn.setChecked(False)
            self.add_point_btn.blockSignals(False)
            return
        if enabled and not self.scene.items():
            QMessageBox.information(self, "Novo ponto", "A placa selecionada não possui imagem para posicionar o ponto.")
            self.add_point_btn.blockSignals(True)
            self.add_point_btn.setChecked(False)
            self.add_point_btn.blockSignals(False)
            return

        self.view.set_placement_mode(enabled)
        self.add_point_btn.setText("Clique na placa…" if enabled else "+ Novo ponto")
        self.status.setText(
            "Clique na posição desejada da placa para criar o ponto." if enabled
            else "Pronto"
        )

    def _end_point_placement(self):
        self.view.set_placement_mode(False)
        self.add_point_btn.blockSignals(True)
        self.add_point_btn.setChecked(False)
        self.add_point_btn.blockSignals(False)
        self.add_point_btn.setText("+ Novo ponto")

    def _place_new_point(self, x: float, y: float):
        if not self.current_board:
            self._end_point_placement()
            return

        refdes, ok = QInputDialog.getText(
            self,
            "Novo ponto de teste",
            "Identificador do ponto (ex.: TP1, VCC, GND):",
        )
        if not ok or not refdes.strip():
            self._end_point_placement()
            self.status.setText("Criação do ponto cancelada.")
            return

        refdes = refdes.strip()
        existing = self.session.query(TestPoint).filter_by(
            board_id=self.current_board.id, refdes=refdes
        ).first()
        if existing:
            QMessageBox.warning(
                self, "Ponto existente",
                f"Já existe um ponto chamado '{refdes}' nesta placa."
            )
            self._end_point_placement()
            return

        try:
            point = TestPoint(
                board_id=self.current_board.id,
                refdes=refdes,
                x=int(round(x)),
                y=int(round(y)),
                image_slot=self.current_image_slot,
                marker_color=RefTheme.DEFAULT_POINT_COLOR,
                marker_shape="circle",
                marker_size=16,
            )
            self.session.add(point)
            self.session.commit()
            self._end_point_placement()
            self._load_board_scene()
            self.refresh_table()
            self.select_point(point)
            self.status.setText(
                f"Ponto {refdes} criado em ({point.x}, {point.y}). Agora você pode salvar a referência."
            )
        except Exception as exc:
            self.session.rollback()
            self._end_point_placement()
            QMessageBox.critical(self, "Erro", f"Não foi possível criar o ponto: {exc}")

    def refresh_table(self):
        self.table.setRowCount(0)
        if not self.current_board:
            return
        points = self.session.query(TestPoint).filter_by(board_id=self.current_board.id).order_by(TestPoint.id).all()
        model_id = self.current_board.model_id
        refs = {
            r.refdes: r for r in self.session.query(OscilloscopeReference)
            .filter_by(board_model_id=model_id).all()
        }
        for row, point in enumerate(points):
            ref = refs.get(point.refdes)
            self.table.insertRow(row)
            item = QTableWidgetItem(point.refdes)
            item.setData(Qt.ItemDataRole.UserRole, point.id)
            item.setForeground(QColor(getattr(point, "marker_color", None) or RefTheme.DEFAULT_POINT_COLOR))
            item.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            self.table.setItem(row, 0, item)

            values = [
                (getattr(ref, "vpp_v", None), " V"),
                (getattr(ref, "vrms_v", None), " V"),
                (getattr(ref, "frequency_hz", None), " Hz"),
                (getattr(ref, "tolerance_vpp_pct", None), " %"),
                (getattr(ref, "tolerance_vrms_pct", None), " %"),
                (getattr(ref, "tolerance_frequency_pct", None), " %"),
            ]
            for col, (value, suffix) in enumerate(values, start=1):
                text = "--" if value is None else f"{value:.6g}{suffix}"
                cell = QTableWidgetItem(text)
                cell.setForeground(QColor(RefTheme.VCC_GREEN if value is not None else RefTheme.TEXT_MUTED))
                self.table.setItem(row, col, cell)
            waveform = self._decode_reference_waveform(ref)
            if waveform:
                points = int(waveform.get("points") or len(waveform.get("y_v") or []))
                wave_item = QTableWidgetItem(f"✓ {points} pts")
                wave_item.setForeground(QColor(RefTheme.ACCENT_CYAN))
                wave_item.setToolTip("Forma de onda correta salva para comparação visual")
            else:
                wave_item = QTableWidgetItem("--")
                wave_item.setForeground(QColor(RefTheme.TEXT_MUTED))
            self.table.setItem(row, 7, wave_item)

            updated = getattr(ref, "updated_at", None)
            updated_text = updated.strftime("%d/%m/%Y %H:%M") if updated else "--"
            self.table.setItem(row, 8, QTableWidgetItem(updated_text))

    def _table_selection(self):
        items = self.table.selectedItems()
        if not items:
            return
        row = self.table.currentRow()
        id_item = self.table.item(row, 0)
        point_id = id_item.data(Qt.ItemDataRole.UserRole) if id_item else None
        if point_id:
            point = self.session.get(TestPoint, int(point_id))
            if point:
                self.select_point(point)

    def select_point(self, point: TestPoint):
        slot = int(getattr(point, "image_slot", 1) or 1)
        if slot != self.current_image_slot:
            self.set_image_slot(slot)
        self.current_point = point
        for pid, item in self.point_items.items():
            item.set_selected(pid == point.id)
        self.selection_label.setText(f"Ponto: {point.refdes}")
        self.scope.set_selected_point(point)
        self._show_saved_reference_waveform(point)
        self.edit_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.point_options_btn.setEnabled(True)

        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == point.id:
                self.table.blockSignals(True)
                self.table.selectRow(row)
                self.table.blockSignals(False)
                break

    def point_moved(self, point: TestPoint, x: int, y: int):
        """Persiste a nova posição quando o usuário arrasta um ponto."""
        try:
            point.x = int(x)
            point.y = int(y)
            self.session.add(point)
            self.session.commit()
            self.status.setText(f"{point.refdes} movido para ({point.x}, {point.y}).")
        except Exception as exc:
            self.session.rollback()
            # Reposiciona visualmente para o último valor persistido.
            item = self.point_items.get(point.id)
            if item is not None:
                self.session.refresh(point)
                item.setPos(point.x, point.y)
            QMessageBox.critical(self, "Erro", f"Não foi possível mover o ponto: {exc}")

    def edit_point_properties(self, point: TestPoint | None = None):
        """Abre o mesmo popup de informações usado na tela de mapeamento."""
        point = point or self.current_point
        if point is None:
            return
        self.select_point(point)
        # Import local: evita acoplamento durante a inicialização da aplicação.
        from ui.image_marker import PointEditDialog

        dlg = PointEditDialog(point, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            for field, value in dlg.values().items():
                setattr(point, field, value)
            self.session.add(point)
            self.session.commit()
            self.refresh_table()
            self.status.setText(f"Informações de {point.refdes} atualizadas.")
        except Exception as exc:
            self.session.rollback()
            QMessageBox.critical(self, "Erro", f"Não foi possível salvar o ponto: {exc}")

    def choose_point_color(self, point: TestPoint | None = None):
        point = point or self.current_point
        if point is None:
            return
        initial = QColor(getattr(point, "marker_color", None) or RefTheme.DEFAULT_POINT_COLOR)
        chosen = QColorDialog.getColor(initial, self, f"Cor de {point.refdes}")
        if not chosen.isValid():
            return
        self._save_point_color(point, chosen.name().upper())

    def reset_point_color(self, point: TestPoint | None = None):
        point = point or self.current_point
        if point is not None:
            self._save_point_color(point, RefTheme.DEFAULT_POINT_COLOR)

    def _save_point_color(self, point: TestPoint, color_hex: str):
        try:
            point.marker_color = color_hex
            self.session.add(point)
            self.session.commit()
            item = self.point_items.get(point.id)
            if item is not None:
                item.update_color(color_hex)
            self.refresh_table()
            self.status.setText(f"Cor de {point.refdes} atualizada.")
        except Exception as exc:
            self.session.rollback()
            QMessageBox.critical(self, "Erro", f"Não foi possível alterar a cor: {exc}")

    def edit_marker_appearance(self, point: TestPoint | None = None):
        point = point or self.current_point
        if point is None:
            return
        self.select_point(point)
        dlg = MarkerAppearanceDialog(point, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            shape, size = dlg.values()
            point.marker_shape = shape
            point.marker_size = size
            self.session.add(point)
            self.session.commit()
            item = self.point_items.get(point.id)
            if item is not None:
                item.update_appearance()
                item.set_selected(True)
            self.status.setText(f"Marcador de {point.refdes}: {shape} • {size}px")
        except Exception as exc:
            self.session.rollback()
            QMessageBox.critical(self, "Erro", f"Não foi possível alterar o marcador: {exc}")

    def delete_point(self, point: TestPoint | None = None):
        point = point or self.current_point
        if point is None:
            return
        reply = QMessageBox.question(
            self,
            "Excluir ponto",
            f"Excluir o ponto '{point.refdes}' desta placa?\n\n"
            "A referência correta do modelo não será apagada automaticamente.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            point_id = point.id
            refdes = point.refdes
            item = self.point_items.pop(point_id, None)
            if item is not None:
                self.scene.removeItem(item)
            self.session.delete(point)
            self.session.commit()
            if self.current_point is not None and self.current_point.id == point_id:
                self.current_point = None
                self.scope.set_selected_point(None)
                self.selection_label.setText("Ponto: nenhum")
                self.edit_btn.setEnabled(False)
                self.clear_btn.setEnabled(False)
                self.point_options_btn.setEnabled(False)
            self.refresh_table()
            self.status.setText(f"Ponto {refdes} excluído.")
        except Exception as exc:
            self.session.rollback()
            self._load_board_scene()
            self.refresh_table()
            QMessageBox.critical(self, "Erro", f"Não foi possível excluir o ponto: {exc}")

    def _show_selected_point_menu(self):
        if self.current_point is None:
            return
        pos = self.point_options_btn.mapToGlobal(self.point_options_btn.rect().bottomLeft())
        self.show_point_context_menu(self.current_point, pos)

    def _table_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if item is None:
            return
        row = item.row()
        id_item = self.table.item(row, 0)
        point_id = id_item.data(Qt.ItemDataRole.UserRole) if id_item else None
        if not point_id:
            return
        point = self.session.get(TestPoint, int(point_id))
        if point is None:
            return
        self.select_point(point)
        self.show_point_context_menu(point, self.table.viewport().mapToGlobal(pos))

    def show_point_context_menu(self, point: TestPoint, global_pos):
        """Mesmas ações de manutenção do ponto da tela de mapeamento."""
        self.select_point(point)
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background:{RefTheme.BG_SURFACE_ALT}; color:{RefTheme.TEXT_PRIMARY};
                border:1px solid {RefTheme.BORDER_SUBTLE}; padding:4px;
            }}
            QMenu::item {{ padding:7px 22px; border-radius:4px; }}
            QMenu::item:selected {{ background:{RefTheme.ACCENT_BLUE}; color:#FFFFFF; }}
        """)

        edit_info = menu.addAction("Editar informações do ponto…")
        edit_info.triggered.connect(lambda: self.edit_point_properties(point))

        edit_ref = menu.addAction("Editar valores corretos…")
        edit_ref.triggered.connect(self.edit_reference)

        menu.addSeparator()
        color = menu.addAction("Alterar cor…")
        color.triggered.connect(lambda: self.choose_point_color(point))
        reset = menu.addAction("Restaurar vermelho")
        reset.triggered.connect(lambda: self.reset_point_color(point))
        appearance = menu.addAction("Formato / tamanho do marcador…")
        appearance.triggered.connect(lambda: self.edit_marker_appearance(point))

        menu.addSeparator()
        remove = menu.addAction(f"Excluir {point.refdes}")
        remove.triggered.connect(lambda: self.delete_point(point))
        menu.exec(global_pos)

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

    def _show_saved_reference_waveform(self, point: TestPoint) -> None:
        if not self.current_board or point is None:
            self.scope.clear_reference_waveform()
            return
        ref = self.session.query(OscilloscopeReference).filter_by(
            board_model_id=self.current_board.model_id,
            refdes=point.refdes,
        ).one_or_none()
        waveform = self._decode_reference_waveform(ref)
        if waveform:
            self.scope.set_reference_waveform(
                waveform,
                channel=getattr(ref, "channel", 1) or 1,
                point_name=point.refdes,
                select_channel=True,
            )
        else:
            self.scope.clear_reference_waveform()

    def _reference_for_current(self):
        if not self.current_board or not self.current_point:
            return None
        return self.session.query(OscilloscopeReference).filter_by(
            board_model_id=self.current_board.model_id,
            refdes=self.current_point.refdes,
        ).one_or_none()

    def _save_capture_as_reference(self, point_id: int, reading: OscilloscopeReading):
        if not self.current_board:
            return
        point = self.session.get(TestPoint, point_id)
        if not point:
            return
        ref = self.session.query(OscilloscopeReference).filter_by(
            board_model_id=self.current_board.model_id,
            refdes=point.refdes,
        ).one_or_none()
        if ref is None:
            ref = OscilloscopeReference(
                board_model_id=self.current_board.model_id,
                refdes=point.refdes,
                tolerance_vpp_pct=10.0,
                tolerance_vrms_pct=10.0,
                tolerance_frequency_pct=5.0,
            )
            self.session.add(ref)
        ref.source_board_id = self.current_board.id
        ref.source_serial = self.current_board.serial_number
        ref.channel = reading.channel
        ref.vpp_v = reading.vpp_v
        ref.vrms_v = reading.vrms_v
        ref.vmax_v = reading.vmax_v
        ref.vmin_v = reading.vmin_v
        ref.vavg_v = reading.vavg_v
        ref.frequency_hz = reading.frequency_hz
        ref.period_s = reading.period_s
        ref.duty_cycle_pct = reading.duty_cycle_pct
        ref.vertical_offset_v = reading.vertical_offset_v
        ref.oscilloscope_id = reading.oscilloscope_id

        # Salva também a curva completa tempo x tensão. A captura SCPI é a
        # preferência; se ela vier vazia (por exemplo, por timeout de waveform),
        # usamos a curva que já está sendo exibida na mini tela.
        waveform = reading.waveform or self.scope.current_waveform(reading.channel)
        ref.waveform_json = (
            json.dumps(waveform, ensure_ascii=False, separators=(",", ":"))
            if waveform else None
        )
        ref.updated_at = datetime.now()
        self.session.commit()
        self.refresh_table()
        self._show_saved_reference_waveform(point)

        wave_points = 0
        if waveform:
            wave_points = int(waveform.get("points") or len(waveform.get("y_v") or []))
        if wave_points:
            self.status.setText(
                f"Referência de {point.refdes} salva: Vpp, Vrms, frequência e forma de onda ({wave_points} pontos)."
            )
        else:
            self.status.setText(
                f"Referência de {point.refdes} salva sem curva. Tente capturar novamente para gravar a forma de onda."
            )

    def edit_reference(self):
        if not self.current_point or not self.current_board:
            return
        ref = self._reference_for_current()
        dlg = ReferenceEditDialog(self.current_point, ref, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if ref is None:
            ref = OscilloscopeReference(
                board_model_id=self.current_board.model_id,
                refdes=self.current_point.refdes,
                source_board_id=self.current_board.id,
                source_serial=self.current_board.serial_number,
            )
            self.session.add(ref)
        for key, value in dlg.values().items():
            setattr(ref, key, value)
        ref.updated_at = datetime.now()
        self.session.commit()
        self.refresh_table()
        self._show_saved_reference_waveform(self.current_point)
        self.status.setText(f"Referência de {self.current_point.refdes} atualizada.")

    def clear_reference(self):
        ref = self._reference_for_current()
        if not ref:
            return
        if QMessageBox.question(
            self, "Limpar referência",
            f"Apagar a referência correta de {self.current_point.refdes}?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.session.delete(ref)
        self.session.commit()
        self.scope.clear_reference_waveform()
        self.refresh_table()
        self.status.setText("Referência removida.")

    def _status_from_scope(self, message: str, level: str):
        self.status.setText(message)

    def shutdown(self):
        if hasattr(self, "scope"):
            self.scope.shutdown()

    def _apply_style(self):
        t = RefTheme
        self.setStyleSheet(f"""
            /* Fundo preto real da página de referência */
            QWidget#referencePage {{
                background:#000000;
                border:none;
            }}
            QWidget {{
                color:{t.TEXT_PRIMARY};
                font-family:'Segoe UI', Arial;
                background:{t.BG_PRIMARY};
            }}

            QFrame#header {{
                background:#070A0F;
                border:1px solid #1E293B;
                border-left:3px solid {t.ACCENT_CYAN};
                border-radius:7px;
            }}
            QFrame#panel, QFrame#boardSelectCard {{
                background:{t.BG_SURFACE};
                border:1px solid {t.BORDER_SUBTLE};
                border-radius:8px;
            }}

            QLabel#pageTitle {{ color:#FFFFFF; font-size:16px; font-weight:800; }}
            QLabel#headerSubtitle {{ color:#718096; font-size:11px; }}
            QLabel#sectionTitle {{ color:#F8FAFC; font-size:12px; font-weight:700; }}
            QLabel#caption {{ color:{t.ACCENT_CYAN}; font-size:10px; font-weight:800; }}
            QLabel#infoValue {{ color:#FFFFFF; font-size:14px; font-weight:700; }}
            QLabel#muted {{ color:#7C8AA0; }}
            QLabel#zoomValue {{ color:{t.ACCENT_CYAN}; font-size:10px; font-weight:700; }}

            QPushButton {{
                background:{t.BG_SURFACE_ALT};
                color:{t.TEXT_PRIMARY};
                border:1px solid {t.BORDER_SUBTLE};
                border-radius:6px;
                padding:6px 10px;
                font-weight:600;
            }}
            QPushButton:hover {{
                background:{t.BG_HOVER};
                border-color:#3B82F6;
                color:#FFFFFF;
            }}
            QPushButton:pressed {{ background:#0F172A; }}
            QPushButton:disabled {{ color:#556276; background:#0D121A; border-color:#1B2431; }}
            QPushButton#selectBoardBtn {{
                background:#141C28;
                color:#F8FAFC;
                border:1px solid #334155;
                border-radius:7px;
                padding:7px 12px;
                font-weight:700;
            }}
            QPushButton#selectBoardBtn:hover {{ border-color:{t.ACCENT_BLUE}; background:#182435; }}
            QPushButton#addPointBtn:checked {{ background:{t.ACCENT_BLUE}; color:#FFFFFF; border-color:{t.ACCENT_CYAN}; }}

            QSlider::groove:horizontal {{ height:4px; background:#1B2533; border-radius:2px; }}
            QSlider::sub-page:horizontal {{ background:{t.ACCENT_BLUE}; border-radius:2px; }}
            QSlider::handle:horizontal {{ width:14px; margin:-5px 0; background:{t.ACCENT_CYAN}; border-radius:7px; }}

            QComboBox {{
                background:{t.BG_INPUT};
                color:{t.TEXT_PRIMARY};
                border:1px solid {t.BORDER_SUBTLE};
                border-radius:6px;
                padding:6px 8px;
            }}
            QComboBox QAbstractItemView {{ background:#0D131C; color:#E5E7EB; selection-background-color:#164E63; }}

            QGraphicsView#boardView {{
                background:{t.BG_CANVAS};
                border:1px solid #202B3A;
                border-radius:5px;
            }}

            QTableWidget {{
                background:#080B10;
                alternate-background-color:#0E141D;
                color:{t.TEXT_PRIMARY};
                border:1px solid #202B3A;
                border-radius:5px;
                selection-background-color:#123B4D;
                selection-color:#FFFFFF;
            }}
            QHeaderView::section {{
                background:#101722;
                color:#9FB0C7;
                border:none;
                border-bottom:1px solid #253247;
                padding:7px;
                font-size:9px;
                font-weight:700;
            }}

            QSplitter#mainReferenceSplitter {{ background:#000000; border:none; }}
            QSplitter#mainReferenceSplitter::handle {{ background:#111827; width:4px; }}
            QSplitter::handle {{ background:#111827; width:4px; }}
            QScrollBar:vertical {{ background:#05070A; width:10px; margin:0; }}
            QScrollBar::handle:vertical {{ background:#263244; min-height:28px; border-radius:5px; }}
            QScrollBar::handle:vertical:hover {{ background:#334155; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
            QScrollBar:horizontal {{ background:#05070A; height:10px; margin:0; }}
            QScrollBar::handle:horizontal {{ background:#263244; min-width:28px; border-radius:5px; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}
        """)
