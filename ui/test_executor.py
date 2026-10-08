from pathlib import Path
from datetime import datetime
import json
import logging

from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QColor, QFont, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QInputDialog,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from db.models import BoardUnit, Machine, TestRun, Measurement, OscilloscopeReference
from engine.pdf_report import export_test_report
from engine.runner import run_test
from engine.guided_diagnostic import (
    compare_scope_reading, reference_summary, reading_summary,
    serialize_guided_result, format_value,
)
from ui.plan_manager import PlanManager
from utils.image_paths import resolve_image_path, heal_board_images, import_image_to_project
from ui.image_marker import ImageMarker
from ui.plan_editor import PlanEditor
from ui.guided_scope_client import GuidedScopeClient
from ui.marker_graphics import draw_marker, normalize_marker_shape, normalize_marker_size


logger = logging.getLogger(__name__)


class FakeDMM:
    """Simulador temporário de multímetro."""

    def measure_voltage(self, range_v=None):
        return 3.29

    def measure_current(self, range_a=None):
        return 0.012


class FakeScope:
    """Simulador temporário de osciloscópio."""

    def measure_frequency(self):
        return 1000.0

    def get_waveform_summary(self):
        return "Senoidal"


class BoardPreview(QFrame):
    """Mostra a imagem da PCB somente para acompanhamento do teste."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap()
        self._point = None
        self._refdes = ""
        # Todos os pontos visíveis no preview. A seleção serve apenas para
        # destacar um deles; não é necessária para exibir os marcadores.
        self._points = []
        self.setObjectName("boardPreview")
        self.setMinimumSize(300, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def load_image(self, image_path):
        pixmap = QPixmap(str(image_path))
        self._pixmap = pixmap if not pixmap.isNull() else QPixmap()
        self._point = None
        self._refdes = ""
        self.update()

    def clear_image(self):
        self._pixmap = QPixmap()
        self._point = None
        self._refdes = ""
        self._points = []
        self.update()

    def set_test_points(self, points):
        """Exibe todos os pontos da imagem ativa, preservando a aparência de cada marcador."""
        normalized = []
        for point in points or []:
            try:
                if isinstance(point, (tuple, list)):
                    x = float(point[0]); y = float(point[1])
                    refdes = str(point[2] if len(point) > 2 else "")
                    shape = "circle"; size = 16; color = "#E53935"
                else:
                    x = float(getattr(point, "x", 0)); y = float(getattr(point, "y", 0))
                    refdes = str(getattr(point, "refdes", "") or "")
                    shape = normalize_marker_shape(getattr(point, "marker_shape", None))
                    size = normalize_marker_size(getattr(point, "marker_size", None))
                    color = getattr(point, "marker_color", None) or "#E53935"
            except Exception:
                continue
            normalized.append({"x": x, "y": y, "refdes": refdes, "shape": shape, "size": size, "color": color})
        self._points = normalized
        self.update()

    def set_test_point(self, x, y, refdes=""):
        self._point = (x, y)
        self._refdes = refdes or ""
        self.update()

    def clear_test_point(self):
        self._point = None
        self._refdes = ""
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0B1220"))

        area = self.rect().adjusted(14, 14, -14, -14)

        if self._pixmap.isNull():
            painter.setPen(QColor("#64748B"))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(
                area,
                Qt.AlignmentFlag.AlignCenter,
                "Nenhuma imagem disponível para a placa selecionada.",
            )
            return

        scaled = self._pixmap.scaled(
            area.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        x0 = area.x() + (area.width() - scaled.width()) // 2
        y0 = area.y() + (area.height() - scaled.height()) // 2
        painter.drawPixmap(x0, y0, scaled)

        sx = scaled.width() / max(self._pixmap.width(), 1)
        sy = scaled.height() / max(self._pixmap.height(), 1)

        # Desenha TODOS os pontos automaticamente, respeitando formato/tamanho/cor.
        for point in self._points:
            px = x0 + int(point["x"] * sx)
            py = y0 + int(point["y"] * sy)
            # O tamanho é proporcional ao zoom da imagem, com um mínimo para continuar legível.
            scaled_size = max(8, int(round(point["size"] * (sx + sy) / 2.0)))
            draw_marker(
                painter, px, py,
                shape=point["shape"], size=scaled_size,
                color=QColor(point["color"]), selected=False,
            )

            refdes = point["refdes"]
            if refdes:
                painter.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
                fm = painter.fontMetrics()
                label_rect = fm.boundingRect(refdes)
                label_rect.adjust(-4, -2, 4, 2)
                label_rect.moveTopLeft(QPoint(px + scaled_size // 2 + 4, py - 18))
                painter.fillRect(label_rect, QColor(11, 18, 32, 205))
                painter.setPen(QColor("#F8FAFC"))
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, refdes)

        # Se houver seleção, destaca sem esconder os demais.
        if self._point is None:
            return

        px = x0 + int(self._point[0] * sx)
        py = y0 + int(self._point[1] * sy)
        painter.setPen(QPen(QColor("#FDE047"), 3))
        painter.setBrush(QColor(253, 224, 71, 45))
        painter.drawEllipse(px - 12, py - 12, 24, 24)
        painter.setPen(QPen(QColor("#111827"), 2))
        painter.setBrush(QColor("#FDE047"))
        painter.drawEllipse(px - 4, py - 4, 8, 8)


class BoardSelectDialog(QDialog):
    """Seleção em 2 passos: primeiro a MÁQUINA, depois a PLACA dela."""

    NO_MACHINE = "sem_maquina"

    def __init__(self, session, parent=None, current_board=None):
        super().__init__(parent)
        self.session = session
        self.selected_board = None

        self.setWindowTitle("Selecionar Placa")
        self.setModal(True)
        self.setMinimumWidth(500)

        boards = (
            session.query(BoardUnit)
            .filter_by(is_active=True)
            .order_by(BoardUnit.name)
            .all()
        )
        self._boards_by_machine = {}
        for board in boards:
            key = board.machine_id if board.machine_id is not None else self.NO_MACHINE
            self._boards_by_machine.setdefault(key, []).append(board)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Cabeçalho
        header = QFrame()
        header.setObjectName("selHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 18, 24, 18)
        header_layout.setSpacing(2)
        title = QLabel("🔌  Selecionar placa para teste")
        title.setObjectName("selTitle")
        subtitle = QLabel("1. Escolha o equipamento     2. Escolha a placa dele")
        subtitle.setObjectName("selSubtitle")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        # Corpo
        body = QFrame()
        body.setObjectName("selBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 12)
        body_layout.setSpacing(6)

        machine_label = QLabel("EQUIPAMENTO")
        machine_label.setObjectName("selFieldLabel")
        self.machine_combo = QComboBox()
        self.machine_combo.setMinimumHeight(38)

        machines = session.query(Machine).order_by(Machine.name).all()
        for machine in machines:
            count = len(self._boards_by_machine.get(machine.id, []))
            code = f" [{machine.code}]" if machine.code else ""
            self.machine_combo.addItem(f"{machine.name}{code}  —  {count} placa(s) ativa(s)", machine.id)
        if self.NO_MACHINE in self._boards_by_machine:
            count = len(self._boards_by_machine[self.NO_MACHINE])
            self.machine_combo.addItem(f"Sem equipamento  —  {count} placa(s) ativa(s)", self.NO_MACHINE)

        board_label = QLabel("PLACA")
        board_label.setObjectName("selFieldLabel")
        self.board_list = QListWidget()
        self.board_list.setMinimumHeight(190)
        self.board_list.itemDoubleClicked.connect(lambda _item: self._confirm())
        self.board_list.itemSelectionChanged.connect(self._update_ok_state)

        self.info_label = QLabel("")
        self.info_label.setObjectName("selInfo")

        body_layout.addWidget(machine_label)
        body_layout.addWidget(self.machine_combo)
        body_layout.addSpacing(8)
        body_layout.addWidget(board_label)
        body_layout.addWidget(self.board_list, 1)
        body_layout.addWidget(self.info_label)
        root.addWidget(body, 1)

        # Rodapé
        footer = QFrame()
        footer.setObjectName("selFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 14, 24, 18)
        footer_layout.addStretch()

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setObjectName("selCancel")
        self.btn_cancel.setMinimumSize(110, 38)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_ok = QPushButton("Selecionar placa")
        self.btn_ok.setObjectName("selOk")
        self.btn_ok.setMinimumSize(150, 38)
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self._confirm)

        footer_layout.addWidget(self.btn_cancel)
        footer_layout.addWidget(self.btn_ok)
        root.addWidget(footer)

        self._apply_styles()
        self.machine_combo.currentIndexChanged.connect(self._fill_boards)

        # Começa na equipamento/placa que já estava selecionada
        if current_board is not None:
            key = current_board.machine_id if current_board.machine_id is not None else self.NO_MACHINE
            index = self.machine_combo.findData(key)
            if index >= 0:
                self.machine_combo.setCurrentIndex(index)
        self._fill_boards()
        if current_board is not None:
            for row in range(self.board_list.count()):
                if self.board_list.item(row).data(Qt.ItemDataRole.UserRole) == current_board.id:
                    self.board_list.setCurrentRow(row)
                    break

    def _fill_boards(self):
        self.board_list.clear()
        key = self.machine_combo.currentData()
        boards = self._boards_by_machine.get(key, [])
        for board in boards:
            item = QListWidgetItem(
                f"{board.name}   —   {board.model} v{board.version}   •   SN: {board.serial_number}"
            )
            item.setData(Qt.ItemDataRole.UserRole, board.id)
            self.board_list.addItem(item)

        if boards:
            self.board_list.setCurrentRow(0)
            self.info_label.setText(f"{len(boards)} placa(s) ativa(s) neste equipamento")
        else:
            self.info_label.setText("Nenhuma placa ativa neste equipamento.")
        self._update_ok_state()

    def _update_ok_state(self):
        self.btn_ok.setEnabled(self.board_list.currentItem() is not None)

    def _confirm(self):
        item = self.board_list.currentItem()
        if item is None:
            return
        self.selected_board = self.session.get(BoardUnit, item.data(Qt.ItemDataRole.UserRole))
        if self.selected_board is not None:
            self.accept()

    def _apply_styles(self):
        # Cores explícitas: o diálogo não depende do estilo de nenhuma tela por trás
        self.setStyleSheet("""
            QDialog { background: #FFFFFF; }
            QFrame#selHeader {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #0F766E, stop:1 #0284C7);
            }
            QLabel#selTitle {
                color: #FFFFFF; font-size: 18px; font-weight: 700; background: transparent;
            }
            QLabel#selSubtitle { color: #E0F2FE; font-size: 12px; background: transparent; }
            QFrame#selBody { background: #FFFFFF; }
            QFrame#selFooter { background: #F8FAFC; border-top: 1px solid #E2E8F0; }
            QLabel#selFieldLabel {
                color: #475569; font-size: 11px; font-weight: 700; background: transparent;
            }
            QLabel#selInfo { color: #64748B; font-size: 12px; background: transparent; }
            QComboBox {
                background: #FFFFFF; color: #0F172A;
                border: 1.5px solid #CBD5E1; border-radius: 8px;
                padding: 6px 12px; font-size: 13px;
            }
            QComboBox:focus { border: 1.5px solid #0284C7; }
            QComboBox QAbstractItemView {
                background: #FFFFFF; color: #0F172A;
                selection-background-color: #0284C7; selection-color: #FFFFFF;
            }
            QListWidget {
                background: #FFFFFF; color: #0F172A;
                border: 1.5px solid #CBD5E1; border-radius: 8px;
                font-size: 13px; outline: 0;
            }
            QListWidget::item { padding: 10px 12px; border-bottom: 1px solid #F1F5F9; }
            QListWidget::item:selected { background: #0284C7; color: #FFFFFF; }
            QListWidget::item:hover:!selected { background: #E0F2FE; color: #0F172A; }
            QPushButton#selCancel {
                background: #FFFFFF; color: #334155;
                border: 1.5px solid #CBD5E1; border-radius: 8px;
                padding: 8px 18px; font-weight: 600; font-size: 13px;
            }
            QPushButton#selCancel:hover { background: #F1F5F9; }
            QPushButton#selOk {
                background: #0F766E; color: #FFFFFF;
                border: 1px solid #0D9488; border-radius: 8px;
                padding: 8px 20px; font-weight: 700; font-size: 13px;
            }
            QPushButton#selOk:hover { background: #0D9488; }
            QPushButton#selOk:disabled {
                background: #E2E8F0; color: #94A3B8; border: 1px solid #CBD5E1;
            }
        """)


class TestExecutor(QWidget):
    """
    Aba TESTE GERAL.

    Esta tela executa testes e acompanha resultados.
    Edição de placa, mapeamento e criação de pontos permanecem nas telas próprias.
    """

    def __init__(self, session, current_user):
        super().__init__()
        self.session = session
        self.user = current_user

        self.selected_board = None
        self.selected_plan = None
        self.last_run = None
        self.plan_manager_window = None
        self.marker_page = None
        self.marker_widget = None
        self.is_test_running = False
        self.current_test_image_slot = 1

        # Diagnóstico guiado: o plano define a ordem; as referências definem
        # os valores corretos; o Rigol fornece a medição real de cada etapa.
        self.guided_steps = []
        self.guided_index = -1
        self.guided_measurements = {}
        self.current_reference = None
        self.guided_run = None
        self._scope_connected = False
        self._scope_simulated = False

        self.scope_client = GuidedScopeClient(self)
        self.scope_client.status_changed.connect(self._on_scope_status)
        self.scope_client.snapshot_ready.connect(self._on_guided_snapshot)
        self.scope_client.error.connect(self._on_scope_error)

        # Mantidos por compatibilidade com execuções antigas do projeto.
        self.instruments = {
            "DMM": FakeDMM(),
            "OSC": FakeScope(),
        }

        self.setup_ui()
        self.setup_shortcuts()
        self.update_button_state()
        self.set_status("Pronto", "ready")

    # ==========================================================
    # INTERFACE
    # ==========================================================

    def setup_ui(self):
        # Pilha: página 0 = tela de testes | página 1 = editor de pontos (embutido)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        # O estilo escuro vale só para a página de testes (não "vaza" para o editor)
        self.test_page = QWidget()
        self.test_page.setObjectName("testGeneralRoot")
        self.apply_styles(self.test_page)

        root = QVBoxLayout(self.test_page)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # Cabeçalho
        header = QFrame()
        header.setObjectName("headerCard")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 14, 20, 14)

        title_box = QVBoxLayout()
        title = QLabel("🧪  TESTE GERAL")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Execução e acompanhamento de testes da placa eletrônica")
        subtitle.setObjectName("pageSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.current_step_label = QLabel("Etapa: aguardando")
        self.current_step_label.setObjectName("mutedText")
        self.status_badge = QLabel("● PRONTO")
        self.status_badge.setObjectName("statusBadge")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_badge.setMinimumWidth(110)

        header_layout.addLayout(title_box)
        header_layout.addStretch()
        header_layout.addWidget(self.current_step_label)
        header_layout.addWidget(self.status_badge)
        root.addWidget(header)

        # Área principal: controle | imagem | resultados
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.build_control_panel())
        splitter.addWidget(self.build_preview_panel())
        splitter.addWidget(self.build_results_panel())
        splitter.setSizes([285, 560, 420])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 1)
        root.addWidget(splitter, 1)

        # Log
        log_card = QFrame()
        log_card.setObjectName("panelCard")
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(16, 12, 16, 14)
        log_layout.setSpacing(8)

        log_header = QHBoxLayout()
        log_title = QLabel("LOG / HISTÓRICO")
        log_title.setObjectName("sectionTitle")
        self.log_counter = QLabel("0 eventos")
        self.log_counter.setObjectName("mutedText")
        self.btn_clear_log = QPushButton("Limpar")
        self.btn_clear_log.setObjectName("ghostButton")
        self.btn_clear_log.setFixedHeight(34)
        self.btn_clear_log.setToolTip("Limpa somente o log exibido nesta tela.")
        self.btn_clear_log.clicked.connect(self.clear_log)

        log_header.addWidget(log_title)
        log_header.addStretch()
        log_header.addWidget(self.log_counter)
        log_header.addWidget(self.btn_clear_log)

        self.log_text = QTextEdit()
        self.log_text.setObjectName("logText")
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(90)
        self.log_text.setMaximumHeight(130)

        log_layout.addLayout(log_header)
        log_layout.addWidget(self.log_text)
        root.addWidget(log_card)

        # Área rolável: em janelas pequenas aparece barra de rolagem
        # em vez de botões ficarem sobrepostos.
        self.test_scroll = QScrollArea()
        self.test_scroll.setObjectName("testScroll")
        self.test_scroll.setWidgetResizable(True)
        self.test_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.test_scroll.setStyleSheet(
            """
            QScrollArea#testScroll { background: #0B1220; border: none; }
            QScrollArea#testScroll QScrollBar:vertical {
                background: #0B1220; width: 10px; margin: 0px; border: none;
            }
            QScrollArea#testScroll QScrollBar::handle:vertical {
                background: #334155; min-height: 24px; border-radius: 5px;
            }
            QScrollArea#testScroll QScrollBar:horizontal {
                background: #0B1220; height: 10px; margin: 0px; border: none;
            }
            QScrollArea#testScroll QScrollBar::handle:horizontal {
                background: #334155; min-width: 24px; border-radius: 5px;
            }
            QScrollArea#testScroll QScrollBar::add-line:vertical,
            QScrollArea#testScroll QScrollBar::sub-line:vertical { height: 0px; }
            QScrollArea#testScroll QScrollBar::add-line:horizontal,
            QScrollArea#testScroll QScrollBar::sub-line:horizontal { width: 0px; }
            """
        )
        self.test_scroll.setWidget(self.test_page)
        self.stack.addWidget(self.test_scroll)

    def build_control_panel(self):
        panel = QFrame()
        panel.setObjectName("panelCard")
        panel.setMinimumWidth(250)
        panel.setMaximumWidth(340)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        title = QLabel("PAINEL DE CONTROLE")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        # ──────────────────────────────────────────────────────
        # EXECUÇÃO NO TOPO
        # Os controles do diagnóstico ficam sempre visíveis logo no início
        # do painel. Nenhuma função foi alterada; apenas a posição no layout.
        execution_box = QFrame()
        execution_box.setObjectName("infoBox")
        execution_layout = QVBoxLayout(execution_box)
        execution_layout.setContentsMargins(10, 10, 10, 10)
        execution_layout.setSpacing(6)

        execution_caption = QLabel("EXECUÇÃO")
        execution_caption.setObjectName("caption")
        execution_layout.addWidget(execution_caption)

        self.btn_start_test = QPushButton("▶  INICIAR DIAGNÓSTICO")
        self.btn_start_test.setObjectName("primaryButton")
        self.btn_start_test.setFixedHeight(42)
        self.btn_start_test.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_start_test.setToolTip(
            "Inicia o diagnóstico guiado na ordem definida pelo plano. Atalho: Espaço."
        )
        self.btn_start_test.clicked.connect(self.start_test)
        execution_layout.addWidget(self.btn_start_test)

        self.btn_capture_step = QPushButton("📥  CAPTURAR ETAPA")
        self.btn_capture_step.setObjectName("primaryButton")
        self.btn_capture_step.setFixedHeight(38)
        self.btn_capture_step.setEnabled(False)
        self.btn_capture_step.setToolTip(
            "Captura Vpp, Vrms, frequência e forma de onda do ponto atual."
        )
        self.btn_capture_step.clicked.connect(self.capture_guided_step)
        execution_layout.addWidget(self.btn_capture_step)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(6)
        self.btn_prev_step = QPushButton("← Anterior")
        self.btn_prev_step.setObjectName("secondaryButton")
        self.btn_prev_step.setFixedHeight(34)
        self.btn_prev_step.setEnabled(False)
        self.btn_prev_step.clicked.connect(self.previous_guided_step)

        self.btn_skip_step = QPushButton("Pular")
        self.btn_skip_step.setObjectName("secondaryButton")
        self.btn_skip_step.setFixedHeight(34)
        self.btn_skip_step.setEnabled(False)
        self.btn_skip_step.clicked.connect(self.skip_guided_step)

        nav_row.addWidget(self.btn_prev_step)
        nav_row.addWidget(self.btn_skip_step)
        execution_layout.addLayout(nav_row)

        layout.addWidget(execution_box)

        # Placa
        board_box = QFrame()
        board_box.setObjectName("infoBox")
        board_layout = QVBoxLayout(board_box)
        board_layout.setContentsMargins(12, 10, 12, 10)
        board_layout.setSpacing(5)

        caption = QLabel("PLACA")
        caption.setObjectName("caption")
        self.lbl_board = QLabel("Nenhuma placa selecionada")
        self.lbl_board.setObjectName("infoValue")
        self.lbl_board.setWordWrap(True)
        self.lbl_board_sn = QLabel("SN: —")
        self.lbl_board_sn.setObjectName("mutedText")
        self.lbl_board_sn.setWordWrap(True)
        self.btn_select_board = QPushButton("Selecionar equipamento/placa")
        self.btn_select_board.setObjectName("secondaryButton")
        self.btn_select_board.setFixedHeight(40)
        self.btn_select_board.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_select_board.setToolTip("Seleciona uma placa ativa cadastrada.")
        self.btn_select_board.clicked.connect(self.select_board)

        board_layout.addWidget(caption)
        board_layout.addWidget(self.lbl_board)
        board_layout.addWidget(self.lbl_board_sn)
        board_layout.addWidget(self.btn_select_board)
        layout.addWidget(board_box)

        # Plano
        plan_box = QFrame()
        plan_box.setObjectName("infoBox")
        plan_layout = QVBoxLayout(plan_box)
        plan_layout.setContentsMargins(12, 10, 12, 10)
        plan_layout.setSpacing(5)

        caption = QLabel("PLANO DE TESTE")
        caption.setObjectName("caption")
        self.lbl_plan = QLabel("Nenhum plano selecionado")
        self.lbl_plan.setObjectName("infoValue")
        self.lbl_plan.setWordWrap(True)
        self.lbl_plan_meta = QLabel("Etapas: —")
        self.lbl_plan_meta.setObjectName("mutedText")
        self.btn_select_plan = QPushButton("Selecionar plano")
        self.btn_select_plan.setObjectName("secondaryButton")
        self.btn_select_plan.setFixedHeight(40)
        self.btn_select_plan.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_select_plan.setToolTip("Seleciona um plano compatível com a placa.")
        self.btn_select_plan.clicked.connect(self.select_plan)

        # Criar e selecionar são ações distintas. A criação fica no próprio
        # bloco de plano para não se misturar com a edição.
        self.btn_create_plan = QPushButton("＋ Criar plano")
        self.btn_create_plan.setObjectName("secondaryButton")
        self.btn_create_plan.setFixedHeight(40)
        self.btn_create_plan.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_create_plan.setToolTip("Cria um novo plano para a placa selecionada.")
        self.btn_create_plan.clicked.connect(self.open_plan_creator)

        plan_layout.addWidget(caption)
        plan_layout.addWidget(self.lbl_plan)
        plan_layout.addWidget(self.lbl_plan_meta)
        plan_layout.addWidget(self.btn_select_plan)
        plan_layout.addWidget(self.btn_create_plan)
        layout.addWidget(plan_box)

        # Osciloscópio compacto: no Teste Geral não mostramos a tela de onda.
        # Ele trabalha em snapshots, um por etapa do plano.
        scope_box = QFrame()
        scope_box.setObjectName("infoBox")
        scope_layout = QVBoxLayout(scope_box)
        scope_layout.setContentsMargins(12, 10, 12, 10)
        scope_layout.setSpacing(5)
        scope_caption = QLabel("OSCILOSCÓPIO")
        scope_caption.setObjectName("caption")
        scope_head = QHBoxLayout()
        self.scope_status_dot = QLabel("●")
        self.scope_status_dot.setStyleSheet("color:#64748B;")
        self.scope_status_text = QLabel("Desconectado")
        self.scope_status_text.setObjectName("mutedText")
        scope_head.addWidget(self.scope_status_dot)
        scope_head.addWidget(self.scope_status_text)
        scope_head.addStretch()
        self.scope_resource_label = QLabel(self.scope_client.resource)
        self.scope_resource_label.setObjectName("mutedText")
        self.scope_resource_label.setWordWrap(True)
        self.btn_scope_connect = QPushButton("Conectar Rigol")
        self.btn_scope_connect.setObjectName("secondaryButton")
        self.btn_scope_connect.setFixedHeight(36)
        self.btn_scope_connect.clicked.connect(self._toggle_guided_scope)
        scope_layout.addWidget(scope_caption)
        scope_layout.addLayout(scope_head)
        scope_layout.addWidget(self.scope_resource_label)
        scope_layout.addWidget(self.btn_scope_connect)
        layout.addWidget(scope_box)

        # Cartão da etapa atual do roteiro.
        guide_box = QFrame()
        guide_box.setObjectName("infoBox")
        guide_layout = QVBoxLayout(guide_box)
        guide_layout.setContentsMargins(12, 10, 12, 10)
        guide_layout.setSpacing(4)
        guide_caption = QLabel("DIAGNÓSTICO GUIADO")
        guide_caption.setObjectName("caption")
        self.guide_step_label = QLabel("Aguardando início")
        self.guide_step_label.setObjectName("infoValue")
        self.guide_step_label.setWordWrap(True)
        self.guide_instruction_label = QLabel("O plano define a ordem dos pontos.")
        self.guide_instruction_label.setObjectName("mutedText")
        self.guide_instruction_label.setWordWrap(True)
        self.guide_reference_label = QLabel("Referência: —")
        self.guide_reference_label.setObjectName("mutedText")
        self.guide_reference_label.setWordWrap(True)
        guide_layout.addWidget(guide_caption)
        guide_layout.addWidget(self.guide_step_label)
        guide_layout.addWidget(self.guide_instruction_label)
        guide_layout.addWidget(self.guide_reference_label)
        layout.addWidget(guide_box)

        # Ação principal
        exec_caption = QLabel("PREPARAÇÃO")
        exec_caption.setObjectName("caption")
        layout.addWidget(exec_caption)

        self.btn_map_points = QPushButton("📍 Mapear / Editar Pontos")
        self.btn_map_points.setObjectName("secondaryButton")
        self.btn_map_points.setFixedHeight(40)
        self.btn_map_points.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_map_points.setToolTip("Abre o editor visual de pontos da placa.")
        self.btn_map_points.clicked.connect(self.open_image_marker_edit)
        layout.addWidget(self.btn_map_points)

        self.btn_plan_editor = QPushButton("✏️ Editar Plano")
        self.btn_plan_editor.setObjectName("secondaryButton")
        self.btn_plan_editor.setFixedHeight(40)
        self.btn_plan_editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_plan_editor.setToolTip("Edita somente o plano de teste selecionado.")
        self.btn_plan_editor.clicked.connect(self.open_plan_editor)
        layout.addWidget(self.btn_plan_editor)

        self.btn_export_report = QPushButton("Exportar último relatório")
        self.btn_export_report.setObjectName("secondaryButton")
        self.btn_export_report.setFixedHeight(40)
        self.btn_export_report.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_export_report.setToolTip("Exporta em PDF o último teste realizado nesta sessão.")
        self.btn_export_report.clicked.connect(self.generate_report)
        layout.addWidget(self.btn_export_report)

        layout.addStretch()

        hint = QLabel("Espaço: iniciar diagnóstico  •  Ctrl+L: limpar log")
        hint.setObjectName("shortcutHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        return panel

    def build_preview_panel(self):
        panel = QFrame()
        panel.setObjectName("panelCard")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("PLACA EM TESTE")
        title.setObjectName("sectionTitle")
        self.preview_meta = QLabel("Sem imagem")
        self.preview_meta.setObjectName("mutedText")
        header.addWidget(title)
        header.addStretch()

        self.preview_slot1_btn = QPushButton("Imagem 1")
        self.preview_slot2_btn = QPushButton("Imagem 2")
        for btn in (self.preview_slot1_btn, self.preview_slot2_btn):
            btn.setObjectName("ghostButton")
            btn.setCheckable(True)
            btn.setFixedHeight(30)
        self.preview_slot1_btn.setChecked(True)
        self.preview_slot1_btn.clicked.connect(lambda: self.set_test_image_slot(1))
        self.preview_slot2_btn.clicked.connect(lambda: self.set_test_image_slot(2))
        header.addWidget(self.preview_slot1_btn)
        header.addWidget(self.preview_slot2_btn)
        header.addWidget(self.preview_meta)

        self.board_preview = BoardPreview()

        footer = QHBoxLayout()
        self.preview_point = QLabel("Ponto atual: —")
        self.preview_point.setObjectName("mutedText")
        legend = QLabel("● ponto em teste")
        legend.setObjectName("previewLegend")
        footer.addWidget(self.preview_point)
        footer.addStretch()
        footer.addWidget(legend)

        layout.addLayout(header)
        layout.addWidget(self.board_preview, 1)
        layout.addLayout(footer)
        return panel

    def build_results_panel(self):
        panel = QFrame()
        panel.setObjectName("panelCard")
        panel.setMinimumWidth(330)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("PONTOS DO TESTE")
        title.setObjectName("sectionTitle")
        self.results_summary = QLabel("Selecione uma placa")
        self.results_summary.setObjectName("mutedText")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.results_summary)

        # Lista propositalmente simples: nesta tela o operador precisa apenas
        # identificar o ponto, saber o valor alvo, acompanhar o valor medido e
        # enxergar o estado. Detalhes ficam no Mapeamento / Referências.
        self.results_table = QTableWidget(0, 4)
        self.results_table.setObjectName("resultsTable")
        self.results_table.setHorizontalHeaderLabels(["Ponto", "Esperado", "Medido", "Status"])
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setShowGrid(False)
        self.results_table.verticalHeader().setDefaultSectionSize(36)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.itemSelectionChanged.connect(self._on_basic_point_selected)

        progress_box = QFrame()
        progress_box.setObjectName("infoBox")
        progress_layout = QVBoxLayout(progress_box)
        progress_layout.setContentsMargins(12, 10, 12, 10)
        progress_layout.setSpacing(7)

        progress_header = QHBoxLayout()
        progress_title = QLabel("PROGRESSO GERAL")
        progress_title.setObjectName("caption")
        self.progress_value_label = QLabel("0%")
        self.progress_value_label.setObjectName("progressValue")
        progress_header.addWidget(progress_title)
        progress_header.addStretch()
        progress_header.addWidget(self.progress_value_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("testProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)

        progress_layout.addLayout(progress_header)
        progress_layout.addWidget(self.progress_bar)

        layout.addLayout(header)
        layout.addWidget(self.results_table, 1)
        layout.addWidget(progress_box)
        return panel

    def apply_styles(self, target=None):
        (target or self).setStyleSheet(
            """
            QWidget#testGeneralRoot {
                background: #0B1220;
                color: #E5E7EB;
                font-family: "Segoe UI", Arial, sans-serif;
            }

            /*
             * Corrige o "efeito de textura": alguns QLabel estavam
             * herdando fundo claro do stylesheet global da aplicação.
             */
            QWidget#testGeneralRoot QLabel {
                background-color: transparent;
                border: none;
            }
            QFrame#headerCard, QFrame#panelCard {
                background: #111827;
                border: 1px solid #243044;
                border-radius: 12px;
            }
            QFrame#infoBox {
                background: #0F172A;
                border: 1px solid #273449;
                border-radius: 9px;
            }
            QFrame#boardPreview {
                background: #0B1220;
                border: 1px dashed #334155;
                border-radius: 10px;
            }
            QLabel#pageTitle {
                color: #F8FAFC;
                font-size: 21px;
                font-weight: 800;
            }
            QLabel#pageSubtitle {
                color: #94A3B8;
                font-size: 11px;
            }
            QLabel#sectionTitle {
                color: #E2E8F0;
                font-size: 12px;
                font-weight: 800;
            }
            QLabel#caption {
                color: #67E8F9;
                font-size: 9px;
                font-weight: 800;
            }
            QLabel#infoValue {
                color: #F8FAFC;
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#mutedText {
                color: #94A3B8;
                font-size: 10px;
            }
            QLabel#previewLegend {
                color: #FDE047;
                font-size: 10px;
                font-weight: 700;
            }
            QLabel#progressValue {
                color: #22D3EE;
                font-size: 11px;
                font-weight: 800;
            }
            QLabel#shortcutHint {
                background: #0F172A;
                color: #64748B;
                border: 1px solid #1E293B;
                border-radius: 7px;
                padding: 8px;
                font-size: 9px;
            }
            QPushButton {
                border-radius: 7px;
                padding: 0px 12px;
                font-size: 10px;
                font-weight: 700;
                text-align: center;
            }

            QPushButton#primaryButton {
                background: #0891B2;
                color: #F8FAFC;
                border: 1px solid #06B6D4;
                min-height: 44px;
                max-height: 46px;
                padding: 0px 14px;
            }

            QPushButton#primaryButton:hover {
                background: #06B6D4;
            }

            QPushButton#primaryButton:pressed {
                background: #0E7490;
            }

            QPushButton#primaryButton:disabled {
                background: #1E293B;
                color: #64748B;
                border: 1px solid #334155;
            }

            QPushButton#secondaryButton {
                background: #172033;
                color: #E2E8F0;
                border: 1px solid #334155;
                min-height: 38px;
                max-height: 40px;
                padding: 0px 12px;
                text-align: left;
            }

            QPushButton#secondaryButton:hover {
                background: #1E293B;
                color: #F8FAFC;
                border: 1px solid #22D3EE;
            }

            QPushButton#secondaryButton:pressed {
                background: #0F172A;
                border: 1px solid #0891B2;
            }

            QPushButton#secondaryButton:disabled {
                background: #111827;
                color: #64748B;
                border: 1px solid #253044;
            }

            QPushButton#ghostButton {
                background: transparent;
                color: #94A3B8;
                border: 1px solid #334155;
                min-height: 32px;
                max-height: 34px;
                padding: 0px 12px;
                text-align: center;
            }

            QPushButton#ghostButton:hover {
                color: #F8FAFC;
                background: #172033;
                border: 1px solid #64748B;
            }

            QPushButton#ghostButton:pressed {
                background: #0F172A;
            }

            QProgressBar#testProgress {
                background: #0B1220;
                border: 1px solid #273449;
                border-radius: 6px;
                min-height: 10px;
                max-height: 10px;
            }
            QProgressBar#testProgress::chunk {
                background: #22D3EE;
                border-radius: 5px;
            }
            QTextEdit#logText {
                background: #070C16;
                color: #A7F3D0;
                border: 1px solid #243044;
                border-radius: 8px;
                padding: 8px;
                font-family: Consolas, monospace;
                font-size: 10px;
                selection-background-color: #164E63;
            }
            QTableWidget#resultsTable {
                background: #0B1220;
                alternate-background-color: #0F172A;
                color: #CBD5E1;
                border: 1px solid #243044;
                border-radius: 8px;
                gridline-color: #1E293B;
                selection-background-color: #164E63;
                selection-color: #F8FAFC;
                font-size: 10px;
            }
            QTableWidget#resultsTable::item {
                padding: 7px;
                border-bottom: 1px solid #1E293B;
            }
            QHeaderView::section {
                background: #172033;
                color: #94A3B8;
                border: none;
                border-right: 1px solid #243044;
                border-bottom: 1px solid #243044;
                padding: 7px;
                font-size: 9px;
                font-weight: 800;
            }

            QTableCornerButton::section {
                background: #172033;
                border: none;
                border-right: 1px solid #243044;
                border-bottom: 1px solid #243044;
            }

            QScrollBar:vertical {
                background: #0B1220;
                width: 10px;
                margin: 0px;
                border: none;
            }

            QScrollBar::handle:vertical {
                background: #334155;
                min-height: 24px;
                border-radius: 5px;
            }

            QScrollBar::handle:vertical:hover {
                background: #475569;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }

            QScrollBar:horizontal {
                background: #0B1220;
                height: 10px;
                margin: 0px;
                border: none;
            }

            QScrollBar::handle:horizontal {
                background: #334155;
                min-width: 24px;
                border-radius: 5px;
            }

            QScrollBar::handle:horizontal:hover {
                background: #475569;
            }

            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QSplitter::handle {
                background: transparent;
                width: 6px;
            }
            QToolTip {
                background: #111827;
                color: #F8FAFC;
                border: 1px solid #334155;
                padding: 5px;
            }
            """
        )

    def setup_shortcuts(self):
        self.shortcut_start = QShortcut(QKeySequence("Space"), self)
        self.shortcut_start.activated.connect(self._shortcut_start)
        self.shortcut_clear = QShortcut(QKeySequence("Ctrl+L"), self)
        self.shortcut_clear.activated.connect(self._shortcut_clear)

    # ==========================================================
    # ESTADO / LOG
    # ==========================================================

    def _shortcut_clear(self):
        if self.stack.currentWidget() is self.test_scroll:
            self.clear_log()

    def _shortcut_start(self):
        if (
            self.stack.currentWidget() is self.test_scroll
            and not self.is_test_running
            and self.selected_board is not None
            and self.selected_plan is not None
        ):
            self.start_test()

    def set_status(self, text, status_type="ready"):
        palette = {
            "ready": ("#163A2A", "#86EFAC", "#166534", "●"),
            "running": ("#083344", "#67E8F9", "#155E75", "●"),
            "success": ("#14532D", "#86EFAC", "#22C55E", "✓"),
            "warning": ("#422006", "#FDE68A", "#B45309", "⚠"),
            "error": ("#450A0A", "#FCA5A5", "#B91C1C", "✕"),
        }
        bg, fg, border, icon = palette.get(status_type, palette["ready"])
        self.status_badge.setText(f"{icon} {text.upper()}")
        self.status_badge.setStyleSheet(
            f"""
            QLabel {{
                background: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 10px;
                padding: 6px 10px;
                font-size: 10px;
                font-weight: 800;
            }}
            """
        )

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(
            f'<span style="color:#64748B">[{timestamp}]</span> {str(message)}'
        )
        count = self.log_text.document().blockCount()
        self.log_counter.setText(f"{count} evento" if count == 1 else f"{count} eventos")
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_log(self):
        if not self.log_text.toPlainText().strip():
            return
        reply = QMessageBox.question(
            self,
            "Limpar log",
            "Deseja limpar somente as mensagens exibidas nesta tela?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.log_text.clear()
            self.log_counter.setText("0 eventos")

    # ==========================================================
    # PLACA / PLANO
    # ==========================================================

    def import_board_for_test(self, board):
        self._set_board(board)
        self.log(f"📦 Placa carregada: {board.name} (SN: {board.serial_number})")

    def _set_board(self, board):
        self._close_marker_inline(refresh=False)
        self.selected_board = board
        self.current_test_image_slot = 1

        if (
            self.selected_plan is not None
            and self.selected_plan.board_model_id != board.model_id
        ):
            self.selected_plan = None
            self.lbl_plan.setText("Nenhum plano selecionado")
            self.lbl_plan_meta.setText("Etapas: —")

        self.lbl_board.setText(board.name)
        machine_text = f"  •  Equipamento: {board.machine.name}" if board.machine else ""
        self.lbl_board_sn.setText(f"SN: {board.serial_number}{machine_text}")
        self.load_board_preview()
        if self.selected_plan is not None:
            self.populate_plan_steps()
        else:
            self.populate_board_points()
        self.update_button_state()

    def _board_images_by_slot(self):
        """Retorna os dois slots de imagem sem depender da ordem da relação ORM."""
        slots = {1: None, 2: None}
        if self.selected_board is None:
            return slots
        leftovers = []
        for image in list(getattr(self.selected_board, "images", []) or []):
            desc = str(getattr(image, "description", "") or "").upper()
            if "SLOT_1" in desc or desc.endswith("1"):
                slots[1] = image
            elif "SLOT_2" in desc or desc.endswith("2"):
                slots[2] = image
            else:
                leftovers.append(image)
        for slot in (1, 2):
            if slots[slot] is None and leftovers:
                slots[slot] = leftovers.pop(0)
        return slots

    def set_test_image_slot(self, slot: int):
        self.current_test_image_slot = 2 if int(slot) == 2 else 1
        self.preview_slot1_btn.blockSignals(True)
        self.preview_slot2_btn.blockSignals(True)
        self.preview_slot1_btn.setChecked(self.current_test_image_slot == 1)
        self.preview_slot2_btn.setChecked(self.current_test_image_slot == 2)
        self.preview_slot1_btn.blockSignals(False)
        self.preview_slot2_btn.blockSignals(False)
        self.load_board_preview()
        if self.selected_plan is not None:
            self.populate_plan_steps()
        else:
            self.populate_board_points()

    def load_board_preview(self):
        self.board_preview.clear_image()
        self.preview_meta.setText(f"Imagem {self.current_test_image_slot}")
        self.preview_point.setText("Ponto atual: —")

        if self.selected_board is None or not self.selected_board.images:
            return

        missing = heal_board_images(self.session, self.selected_board)
        image = self._board_images_by_slot().get(self.current_test_image_slot)
        if image is None:
            self.preview_meta.setText(f"Imagem {self.current_test_image_slot} não cadastrada")
            return
        if image not in missing:
            self.board_preview.load_image(image.path)
            self.preview_meta.setText(f"Imagem {self.current_test_image_slot} • {Path(image.path).name}")
            return

        self.preview_meta.setText(f"Imagem {self.current_test_image_slot} não encontrada")
        self._relocate_missing_image(image)

    def _relocate_missing_image(self, image):
        resp = QMessageBox.question(
            self,
            "Imagem não encontrada",
            f"Não achei o arquivo da imagem cadastrada:\n{image.path}\n\n"
            "Deseja localizar a imagem agora?",
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Localizar imagem da placa",
            "",
            "Imagens (*.png *.jpg *.jpeg *.bmp *.gif)",
        )
        if not path:
            return

        image.path = import_image_to_project(path)
        self.session.commit()
        self.load_board_preview()

    def select_board(self):
        has_boards = self.session.query(BoardUnit).filter_by(is_active=True).first() is not None
        if not has_boards:
            QMessageBox.warning(self, "Aviso", "Nenhuma placa ativa cadastrada.")
            return

        dialog = BoardSelectDialog(self.session, self, self.selected_board)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_board is None:
            return

        board = dialog.selected_board
        self._set_board(board)
        machine = f" | Equipamento: {board.machine.name}" if board.machine else ""
        self.log(f"🔌 Placa selecionada: {board.name} (SN: {board.serial_number}){machine}")

    @staticmethod
    def _format_compact_value(value, unit):
        if value is None:
            return "—"
        try:
            value = float(value)
        except (TypeError, ValueError):
            return f"{value} {unit}".strip()
        unit = unit or ""
        if unit == "Hz":
            if abs(value) >= 1_000_000:
                return f"{value / 1_000_000:.3g} MHz"
            if abs(value) >= 1_000:
                return f"{value / 1_000:.3g} kHz"
        if unit == "A" and abs(value) < 1:
            return f"{value * 1000:.3g} mA"
        if unit == "V" and 0 < abs(value) < 1:
            return f"{value * 1000:.3g} mV"
        return f"{value:.4g} {unit}".strip()

    def _reference_for_point(self, point):
        """Busca a referência correta do mesmo modelo + RefDes."""
        if point is None or self.selected_board is None:
            return None
        try:
            return (
                self.session.query(OscilloscopeReference)
                .filter_by(
                    board_model_id=self.selected_board.model_id,
                    refdes=point.refdes,
                )
                .first()
            )
        except Exception:
            logger.exception("Falha ao buscar referência de %s", getattr(point, "refdes", "?"))
            return None

    def _point_expected_basic(self, point):
        """Resumo enxuto usado no Teste Geral. Referências têm prioridade."""
        if point is None:
            return "—"
        reference = self._reference_for_point(point)
        if reference is not None:
            # Na tabela básica mostramos apenas a primeira grandeza disponível;
            # o cartão da etapa atual mostra o conjunto completo.
            if getattr(reference, "vpp_v", None) is not None:
                return f"Vpp {format_value(reference.vpp_v, 'V')}"
            if getattr(reference, "vrms_v", None) is not None:
                return f"Vrms {format_value(reference.vrms_v, 'V')}"
            if getattr(reference, "frequency_hz", None) is not None:
                return f"F {format_value(reference.frequency_hz, 'Hz')}"

        # Fallback para projetos antigos que ainda usam valores no TestPoint.
        if getattr(point, "expected_voltage_v", None) is not None:
            return self._format_compact_value(point.expected_voltage_v, "V")
        if getattr(point, "expected_frequency_hz", None) is not None:
            return self._format_compact_value(point.expected_frequency_hz, "Hz")
        if getattr(point, "expected_current_a", None) is not None:
            return self._format_compact_value(point.expected_current_a, "A")
        waveform = getattr(point, "expected_waveform", None)
        return str(waveform) if waveform else "—"

    def populate_board_points(self):
        """Mostra os pontos da placa mesmo antes de um plano ser selecionado."""
        self.results_table.setRowCount(0)
        if self.selected_board is None:
            self.results_summary.setText("Selecione uma placa")
            return

        points = [
            p for p in (getattr(self.selected_board, "test_points", []) or [])
            if int(getattr(p, "image_slot", 1) or 1) == self.current_test_image_slot
        ]
        points = sorted(
            points,
            key=lambda p: (str(getattr(p, "refdes", "")).lower(), getattr(p, "id", 0)),
        )
        for row, point in enumerate(points):
            self.results_table.insertRow(row)
            item_point = QTableWidgetItem(point.refdes or f"P{row + 1}")
            item_point.setData(Qt.ItemDataRole.UserRole, point.id)
            self.results_table.setItem(row, 0, item_point)
            self.results_table.setItem(row, 1, QTableWidgetItem(self._point_expected_basic(point)))
            self.results_table.setItem(row, 2, QTableWidgetItem("—"))
            self.results_table.setItem(row, 3, QTableWidgetItem("Aguardando"))

        # Todos os pontos ficam visíveis na imagem sem exigir seleção.
        self.board_preview.set_test_points(points)
        self.board_preview.clear_test_point()
        self.preview_point.setText(f"{len(points)} ponto(s) visíveis" if points else "Ponto atual: —")

        if points:
            self.results_summary.setText(f"{len(points)} ponto(s)")
            self.results_table.clearSelection()
            self.results_table.setCurrentCell(-1, -1)
        else:
            self.results_summary.setText("Nenhum ponto cadastrado")

    def _on_basic_point_selected(self):
        """Destaca na imagem o ponto selecionado na lista simplificada."""
        if self.selected_board is None:
            return
        row = self.results_table.currentRow()
        if row < 0:
            return
        item = self.results_table.item(row, 0)
        if item is None:
            return
        point_id = item.data(Qt.ItemDataRole.UserRole)
        if point_id is None:
            return
        point = next(
            (p for p in (getattr(self.selected_board, "test_points", []) or []) if p.id == point_id),
            None,
        )
        if point is None:
            return
        self.board_preview.set_test_point(point.x, point.y, point.refdes)
        self.preview_point.setText(f"Ponto atual: {point.refdes}")

    def select_plan(self):
        if not self.selected_board:
            QMessageBox.warning(self, "Aviso", "Selecione uma placa primeiro.")
            return

        self.plan_manager_window = PlanManager(
            self.session,
            self.set_selected_plan,
            self.selected_board,
        )
        self.plan_manager_window.show()
        self.plan_manager_window.raise_()
        self.plan_manager_window.activateWindow()

    def set_selected_plan(self, plan):
        if plan is None:
            return
        if not self.selected_board:
            QMessageBox.warning(self, "Aviso", "Selecione uma placa primeiro.")
            return
        if plan.board_model_id != self.selected_board.model_id:
            QMessageBox.warning(
                self,
                "Plano incompatível",
                "O plano selecionado pertence a outro modelo de placa.",
            )
            return

        self.selected_plan = plan
        self.lbl_plan.setText(f"{plan.name} • v{plan.version}")
        self.lbl_plan_meta.setText(f"Etapas: {len(plan.steps)}")
        self.populate_plan_steps()
        self.log(f"📋 Plano selecionado: {plan.name} v{plan.version}")
        self.update_button_state()

    def populate_plan_steps(self):
        """Lista somente as informações básicas necessárias para executar o plano."""
        self.results_table.setRowCount(0)
        if self.selected_plan is None:
            self.populate_board_points()
            return

        steps = sorted(self.selected_plan.steps, key=lambda step: step.order_index)
        for row, step in enumerate(steps):
            self.results_table.insertRow(row)
            point = step.test_point
            refdes = point.refdes if point else "—"

            point_item = QTableWidgetItem(refdes)
            if point is not None:
                point_item.setData(Qt.ItemDataRole.UserRole, point.id)
            self.results_table.setItem(row, 0, point_item)

            expected = self._point_expected_basic(point) if point is not None else "—"
            self.results_table.setItem(row, 1, QTableWidgetItem(expected))
            self.results_table.setItem(row, 2, QTableWidgetItem("—"))
            self.results_table.setItem(row, 3, QTableWidgetItem("Pendente"))

        # No plano, mantém todos os pontos associados visíveis de uma vez.
        plan_points = [
            step.test_point for step in steps
            if step.test_point is not None
            and int(getattr(step.test_point, "image_slot", 1) or 1) == self.current_test_image_slot
        ]
        self.board_preview.set_test_points(plan_points)
        self.board_preview.clear_test_point()
        self.preview_point.setText(
            f"{len(plan_points)} ponto(s) do plano visíveis" if plan_points else "Ponto atual: —"
        )

        self.results_summary.setText(f"{len(steps)} ponto(s) no plano")
        self.results_table.clearSelection()
        self.results_table.setCurrentCell(-1, -1)

    def update_button_state(self):
        enabled = not self.is_test_running
        self.btn_select_board.setEnabled(enabled)
        self.btn_select_plan.setEnabled(enabled)
        self.btn_create_plan.setEnabled(enabled)
        # Durante a execução o mesmo botão vira CANCELAR, portanto fica ativo.
        self.btn_start_test.setEnabled(True)
        self.btn_export_report.setEnabled(enabled and self.last_run is not None)
        self.btn_map_points.setEnabled(enabled)
        self.btn_plan_editor.setEnabled(enabled)
        if hasattr(self, "btn_capture_step"):
            self.btn_capture_step.setEnabled(self.is_test_running and self._scope_connected)
            self.btn_prev_step.setEnabled(self.is_test_running and self.guided_index > 0)
            self.btn_skip_step.setEnabled(self.is_test_running)

    def check_can_start(self):
        self.update_button_state()

    # ==========================================================
    # EXECUÇÃO
    # ==========================================================

    def start_test(self):
        """Inicia/cancela o diagnóstico guiado pelo plano.

        O plano define a sequência. Os valores corretos vêm da aba Referências.
        Cada clique em "Capturar etapa" pede um snapshot ao Rigol e salva o
        resultado no TestRun atual.
        """
        if self.is_test_running:
            self.cancel_guided_test()
            return

        if not self.selected_board or not self.selected_plan:
            QMessageBox.warning(
                self,
                "Aviso",
                "Selecione uma placa e um plano de teste antes de iniciar.",
            )
            return

        steps = sorted(self.selected_plan.steps, key=lambda step: step.order_index)
        if not steps:
            QMessageBox.warning(self, "Plano vazio", "O plano selecionado não possui etapas de teste.")
            return

        missing_points = [step for step in steps if step.test_point is None]
        if missing_points:
            QMessageBox.warning(
                self,
                "Plano incompleto",
                "Existem etapas sem ponto associado. Edite o plano antes de iniciar.",
            )
            return

        if not self._scope_connected:
            reply = QMessageBox.question(
                self,
                "Conectar osciloscópio",
                "O Rigol ainda não está conectado. Deseja conectar agora usando a configuração salva?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.scope_client.connect_scope()
            else:
                return

        try:
            run = TestRun(
                board=self.selected_board,
                operator=self.user,
                plan=self.selected_plan,
                start_time=datetime.now(),
                status="running",
            )
            self.session.add(run)
            self.session.flush()
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            QMessageBox.critical(self, "Erro", f"Não foi possível iniciar a execução:\n{exc}")
            return

        self.guided_run = run
        self.last_run = None
        self.guided_steps = steps
        self.guided_measurements = {}
        self.guided_index = 0
        self.is_test_running = True

        # Prepara tabela e interface.
        self.populate_plan_steps()
        for row in range(self.results_table.rowCount()):
            self.results_table.setItem(row, 2, QTableWidgetItem("—"))
            self.results_table.setItem(row, 3, QTableWidgetItem("Pendente"))

        self.progress_bar.setValue(0)
        self.progress_value_label.setText("0%")
        self.results_summary.setText("Diagnóstico guiado em andamento")
        self.set_status("Diagnóstico", "running")
        self.btn_start_test.setText("■  CANCELAR DIAGNÓSTICO")
        self._set_execution_controls(False)

        self.log("=" * 58)
        self.log(f"▶ Diagnóstico guiado: {self.selected_plan.name}")
        self.log(f"Placa: {self.selected_board.name} (SN: {self.selected_board.serial_number})")
        self.log("O plano controla a ordem; as referências fornecem os valores corretos.")
        self.log("=" * 58)

        self._show_guided_step(0)

    def _toggle_guided_scope(self):
        if self._scope_connected or (self.scope_client.reader is not None and self.scope_client.reader.is_alive()):
            self.scope_client.disconnect_scope()
        else:
            self.scope_client.connect_scope()

    def _on_scope_status(self, text, connected, simulated):
        self._scope_connected = bool(connected)
        self._scope_simulated = bool(simulated)
        if hasattr(self, "scope_status_text"):
            self.scope_status_text.setText(text)
            color = "#FACC15" if simulated and connected else ("#22C55E" if connected else "#64748B")
            self.scope_status_dot.setStyleSheet(f"color:{color};")
            self.btn_scope_connect.setText("Desconectar" if connected else "Conectar Rigol")
        if hasattr(self, "btn_capture_step"):
            self.btn_capture_step.setEnabled(self.is_test_running and connected)
        if connected:
            self.log(f"🔌 Osciloscópio {text.lower()}: {self.scope_client.resource}")

    def _on_scope_error(self, message):
        self.log(f"❌ Osciloscópio: {message}")
        if hasattr(self, "scope_status_text"):
            self.scope_status_text.setText("Erro de comunicação")
        if self.is_test_running:
            QMessageBox.warning(self, "Osciloscópio", str(message))

    def _guided_reference(self, step):
        return self._reference_for_point(step.test_point if step else None)

    def _show_guided_step(self, index):
        if not self.is_test_running or not self.guided_steps:
            return
        index = max(0, min(int(index), len(self.guided_steps) - 1))
        self.guided_index = index
        step = self.guided_steps[index]
        point = step.test_point
        reference = self._guided_reference(step)
        self.current_reference = reference

        # Se a etapa pertence à segunda imagem, troca o preview automaticamente.
        point_slot = int(getattr(point, "image_slot", 1) or 1)
        if point_slot != self.current_test_image_slot:
            self.set_test_image_slot(point_slot)

        channel = int(getattr(reference, "channel", 1) or 1) if reference is not None else 1
        self.scope_client.set_channel(channel)

        self.guide_step_label.setText(f"Etapa {index + 1}/{len(self.guided_steps)} • {point.refdes}")
        self.guide_instruction_label.setText(step.description or "Meça o ponto destacado.")
        if reference is None:
            self.guide_reference_label.setText("Referência: não cadastrada")
            self.guide_reference_label.setStyleSheet("color:#F59E0B;")
        else:
            self.guide_reference_label.setText(
                f"CH{channel} • {reference_summary(reference)}"
            )
            self.guide_reference_label.setStyleSheet("")

        self.current_step_label.setText(f"Etapa {index + 1}/{len(self.guided_steps)}: {point.refdes}")
        self.highlight_test_point(step)
        if index < self.results_table.rowCount():
            self.results_table.selectRow(index)

        self.btn_prev_step.setEnabled(index > 0)
        self.btn_skip_step.setEnabled(True)
        self.btn_capture_step.setEnabled(self._scope_connected)
        self.btn_capture_step.setText("📥  CAPTURAR ETAPA")
        self.log(f"[{index + 1}/{len(self.guided_steps)}] {point.refdes} — {step.description}")

    def capture_guided_step(self):
        if not self.is_test_running or not self.guided_steps:
            return
        if not self._scope_connected:
            QMessageBox.warning(self, "Osciloscópio", "Conecte o Rigol antes de capturar.")
            return
        step = self.guided_steps[self.guided_index]
        reference = self._guided_reference(step)
        channel = int(getattr(reference, "channel", 1) or 1) if reference is not None else 1
        self.scope_client.set_channel(channel)
        context = {
            "run_id": self.guided_run.id if self.guided_run else None,
            "step_id": step.id,
            "index": self.guided_index,
        }
        self.btn_capture_step.setEnabled(False)
        self.btn_capture_step.setText("Capturando…")
        self.guide_instruction_label.setText("Aguarde a leitura do Rigol…")
        if not self.scope_client.capture(context):
            self.btn_capture_step.setEnabled(True)
            self.btn_capture_step.setText("📥  CAPTURAR ETAPA")

    def _on_guided_snapshot(self, reading, context):
        if not self.is_test_running or self.guided_run is None:
            return
        if not isinstance(context, dict):
            return
        step_id = context.get("step_id")
        step = next((s for s in self.guided_steps if s.id == step_id), None)
        if step is None:
            return
        reference = self._guided_reference(step)
        result = compare_scope_reading(reference, reading)
        self._save_guided_measurement(step, reading, result)
        self._update_guided_row(step, result)

        similarity = result.get("waveform_similarity_pct")
        similarity_text = f" • onda {similarity:.1f}%" if similarity is not None else ""
        self.log(
            f"{step.test_point.refdes}: {result['measured_summary']} → "
            f"{result['status']}{similarity_text}"
        )

        # Atualiza o progresso pelo número de etapas que já possuem resultado.
        done = len(self.guided_measurements)
        total = len(self.guided_steps)
        progress = int(done / total * 100) if total else 0
        self.progress_bar.setValue(progress)
        self.progress_value_label.setText(f"{progress}%")

        self.btn_capture_step.setText("📥  CAPTURAR ETAPA")

        current_index = context.get("index", self.guided_index)
        if current_index >= total - 1:
            self._finish_guided_test()
        else:
            # Mostra imediatamente o próximo ponto. Como o cliente trabalha
            # apenas por snapshots, nenhuma leitura é atribuída durante a troca
            # física da ponta de prova.
            QTimer.singleShot(450, lambda: self._show_guided_step(current_index + 1))

    def _save_guided_measurement(self, step, reading, result):
        measurement = self.guided_measurements.get(step.id)
        if measurement is None:
            measurement = Measurement(test_run=self.guided_run, step=step)
            self.session.add(measurement)
            self.guided_measurements[step.id] = measurement

        measurement.value = result.get("primary_value")
        measurement.unit = result.get("primary_unit") or ""
        measurement.passed = result.get("passed")
        measurement.notes = serialize_guided_result(
            result, channel=getattr(reading, "channel", None)
        )
        measurement.timestamp = datetime.now()

        expected = result.get("primary_expected")
        tol_pct = result.get("primary_tolerance_pct")
        if expected is not None and tol_pct is not None:
            tol_abs = abs(float(expected)) * float(tol_pct) / 100.0
            measurement.min_limit = float(expected) - tol_abs
            measurement.max_limit = float(expected) + tol_abs
        else:
            measurement.min_limit = None
            measurement.max_limit = None

        self.session.commit()

    def _row_for_step(self, step):
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item is None or step.test_point is None:
                continue
            if item.data(Qt.ItemDataRole.UserRole) == step.test_point.id:
                # Em caso de ponto repetido no plano, usa a posição da etapa.
                if row == self.guided_steps.index(step):
                    return row
        try:
            return self.guided_steps.index(step)
        except ValueError:
            return -1

    def _update_guided_row(self, step, result):
        row = self._row_for_step(step)
        if row < 0 or row >= self.results_table.rowCount():
            return
        metrics = result.get("metrics") or {}
        primary = next(iter(metrics.values()), None)
        expected_text = primary.get("expected_text") if primary else (result.get("expected_summary") or "—")
        measured_text = primary.get("measured_text") if primary else (result.get("measured_summary") or "—")
        self.results_table.setItem(row, 1, QTableWidgetItem(expected_text or "—"))
        self.results_table.setItem(row, 2, QTableWidgetItem(measured_text or "—"))
        status = result.get("status") or "—"
        status_item = QTableWidgetItem(status)
        color = {
            "OK": "#22C55E",
            "LIMITE": "#FACC15",
            "FALHA": "#EF4444",
            "SEM REF.": "#F59E0B",
            "SEM LEITURA": "#EF4444",
            "PULADO": "#94A3B8",
        }.get(status, "#CBD5E1")
        status_item.setForeground(QColor(color))
        self.results_table.setItem(row, 3, status_item)

    def previous_guided_step(self):
        if not self.is_test_running or self.guided_index <= 0:
            return
        self._show_guided_step(self.guided_index - 1)

    def skip_guided_step(self):
        if not self.is_test_running or not self.guided_steps:
            return
        step = self.guided_steps[self.guided_index]
        result = {
            "status": "PULADO",
            "passed": None,
            "expected_summary": reference_summary(self._guided_reference(step)),
            "measured_summary": "—",
            "metrics": {},
            "waveform_similarity_pct": None,
            "primary_value": None,
            "primary_expected": None,
            "primary_tolerance_pct": None,
            "primary_unit": "",
        }
        self._save_guided_measurement(step, None, result)
        self._update_guided_row(step, result)
        self.log(f"⚪ {step.test_point.refdes}: etapa pulada")
        if self.guided_index >= len(self.guided_steps) - 1:
            self._finish_guided_test()
        else:
            self._show_guided_step(self.guided_index + 1)

    def _finish_guided_test(self):
        if not self.is_test_running or self.guided_run is None:
            return
        measurements = list(self.guided_measurements.values())
        has_failure = any(m.passed is False for m in measurements)
        self.guided_run.status = "failed" if has_failure else "completed"
        self.guided_run.end_time = datetime.now()
        self.session.commit()
        self.last_run = self.guided_run

        self.is_test_running = False
        self.guided_index = -1
        self.btn_start_test.setText("▶  INICIAR DIAGNÓSTICO")
        self.btn_capture_step.setEnabled(False)
        self.btn_prev_step.setEnabled(False)
        self.btn_skip_step.setEnabled(False)
        self._set_execution_controls(True)
        self.progress_bar.setValue(100)
        self.progress_value_label.setText("100%")
        self.current_step_label.setText("Etapa: diagnóstico finalizado")
        self.guide_step_label.setText("Diagnóstico concluído")
        self.guide_instruction_label.setText("Revise os resultados e exporte o relatório.")

        ok = sum(1 for m in measurements if m.passed is True)
        fail = sum(1 for m in measurements if m.passed is False)
        skipped = sum(1 for m in measurements if m.passed is None)
        self.results_summary.setText(f"{ok} OK • {fail} falha(s) • {skipped} sem resultado")
        self.set_status("Reprovada" if has_failure else "Aprovada", "error" if has_failure else "success")
        self.log(f"■ Diagnóstico finalizado: {self.guided_run.status}")

        reply = QMessageBox.question(
            self,
            "Diagnóstico concluído",
            "Diagnóstico concluído. Deseja gerar o relatório em PDF agora?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.generate_report()

    def cancel_guided_test(self):
        if not self.is_test_running:
            return
        reply = QMessageBox.question(
            self,
            "Cancelar diagnóstico",
            "Deseja cancelar o diagnóstico em andamento?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self.guided_run is not None:
            self.guided_run.status = "cancelled"
            self.guided_run.end_time = datetime.now()
            self.session.commit()
            self.last_run = self.guided_run
        self.is_test_running = False
        self.guided_index = -1
        self.btn_start_test.setText("▶  INICIAR DIAGNÓSTICO")
        self.btn_capture_step.setEnabled(False)
        self.btn_prev_step.setEnabled(False)
        self.btn_skip_step.setEnabled(False)
        self._set_execution_controls(True)
        self.set_status("Cancelado", "warning")
        self.guide_step_label.setText("Diagnóstico cancelado")
        self.guide_instruction_label.setText("Selecione Iniciar diagnóstico para recomeçar.")

    def _set_execution_controls(self, enabled):
        # Placa/plano ficam congelados durante o roteiro, mas o botão principal
        # permanece ativo para permitir CANCELAR.
        self.btn_select_board.setEnabled(enabled)
        self.btn_select_plan.setEnabled(enabled)
        self.btn_create_plan.setEnabled(enabled)
        self.btn_start_test.setEnabled(True)
        self.btn_export_report.setEnabled(enabled and self.last_run is not None)
        self.btn_map_points.setEnabled(enabled)
        self.btn_plan_editor.setEnabled(enabled)

    def update_progress(self, current, total, description):
        progress = int((current / total) * 100) if total else 0
        self.progress_bar.setValue(progress)
        self.progress_value_label.setText(f"{progress}%")
        self.current_step_label.setText(f"Etapa {current}/{total}: {description}")
        if 0 <= current - 1 < self.results_table.rowCount():
            self.results_table.selectRow(current - 1)
        self.log(f"[{current}/{total}] {description}")
        QApplication.processEvents()

    def highlight_test_point(self, step):
        if not step.test_point:
            self.board_preview.clear_test_point()
            self.preview_point.setText("Ponto atual: sem ponto associado")
            return

        point = step.test_point
        self.board_preview.set_test_point(point.x, point.y, point.refdes)
        self.preview_point.setText(f"Ponto atual: {point.refdes} ({point.x}, {point.y})")
        QApplication.processEvents()

    def display_test_results(self, run, measurements):
        self.results_table.setRowCount(0)
        ok_count = 0
        fail_count = 0
        skipped_count = 0

        for row, measurement in enumerate(measurements):
            self.results_table.insertRow(row)
            step = measurement.step

            if measurement.passed is True:
                status = "✅ OK"
                ok_count += 1
            elif measurement.passed is False:
                status = "❌ Falha"
                fail_count += 1
            else:
                status = "⚠️ Pulado"
                skipped_count += 1

            refdes = step.test_point.refdes if step.test_point else "—"
            value = "—" if measurement.value is None else f"{measurement.value:g}"
            unit = measurement.unit or step.unit or ""

            point_item = QTableWidgetItem(refdes)
            if step.test_point is not None:
                point_item.setData(Qt.ItemDataRole.UserRole, step.test_point.id)
            self.results_table.setItem(row, 0, point_item)

            expected = "—"
            if step.desired_value is not None:
                expected = self._format_compact_value(step.desired_value, step.unit or unit)
            elif step.test_point is not None:
                expected = self._point_expected_basic(step.test_point)
            self.results_table.setItem(row, 1, QTableWidgetItem(expected))
            self.results_table.setItem(row, 2, QTableWidgetItem(f"{value} {unit}".strip()))
            self.results_table.setItem(row, 3, QTableWidgetItem(status))

            note = f" | {measurement.notes}" if measurement.notes else ""
            self.log(f"{status} {step.description}: {value} {unit}{note}")

        parts = [f"{ok_count} OK", f"{fail_count} falha(s)"]
        if skipped_count:
            parts.append(f"{skipped_count} pulado(s)")
        self.results_summary.setText(" • ".join(parts))
        self.progress_bar.setValue(100)
        self.progress_value_label.setText("100%")

        if run.status == "completed":
            self.set_status("Aprovado", "success")
        elif run.status == "failed":
            self.set_status("Falha", "error")
        elif run.status == "cancelled":
            self.set_status("Cancelado", "warning")
        else:
            self.set_status(run.status, "warning")

        if self.results_table.rowCount():
            self.results_table.selectRow(self.results_table.rowCount() - 1)

    # ==========================================================
    # RELATÓRIO
    # ==========================================================

    def generate_report(self):
        if self.last_run is None:
            QMessageBox.warning(self, "Aviso", "Nenhum teste foi executado ainda.")
            return

        image_path = self._choose_board_image()
        if image_path is None:
            return

        default_name = f"Relatorio_{self.selected_board.serial_number}_{self.last_run.id}.pdf"
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Relatório",
            default_name,
            "PDF Files (*.pdf)",
        )
        if not file_name:
            return

        try:
            export_test_report(self.last_run, image_path, file_name)
            self.log(f"💾 Relatório salvo em: {file_name}")
            QMessageBox.information(self, "Sucesso", "Relatório gerado com sucesso.")
        except Exception as exc:
            logger.exception("Erro ao gerar relatório")
            self.log(f"❌ Erro ao gerar relatório: {exc}")
            QMessageBox.critical(self, "Erro", f"Falha ao gerar PDF:\n{exc}")

    def _choose_board_image(self):
        if not self.selected_board or not self.selected_board.images:
            QMessageBox.warning(
                self,
                "Imagem necessária",
                "A placa não possui imagem cadastrada para gerar o relatório.",
            )
            return None

        paths = [image.path for image in self.selected_board.images]
        if len(paths) == 1:
            selected = paths[0]
        else:
            selected, ok = QInputDialog.getItem(
                self,
                "Selecionar Imagem",
                "Escolha a imagem usada no relatório:",
                paths,
                0,
                False,
            )
            if not ok or not selected:
                return None

        real_path = resolve_image_path(selected)
        if not real_path:
            QMessageBox.warning(
                self,
                "Imagem não encontrada",
                f"O arquivo de imagem não existe no caminho cadastrado:\n{selected}",
            )
            return None
        return real_path

    # ==========================================================
    # EDITORES (MAPEAMENTO E PLANO)
    # ==========================================================

    def open_image_marker_edit(self):
        if not self.selected_board:
            QMessageBox.warning(self, "Aviso", "Selecione uma placa antes de mapear pontos.")
            return

        if not self.selected_board.images:
            QMessageBox.warning(self, "Aviso", "A placa não possui imagens cadastradas. Cadastre uma imagem primeiro.")
            return

        paths = [image.path for image in self.selected_board.images]
        if len(paths) == 1:
            selected = paths[0]
        else:
            selected, ok = QInputDialog.getItem(
                self,
                "Selecionar Imagem",
                "Escolha a imagem para mapeamento:",
                paths,
                0,
                False,
            )
            if not ok or not selected:
                return

        real_path = resolve_image_path(selected)
        if not real_path:
            QMessageBox.warning(
                self,
                "Imagem não encontrada",
                f"O arquivo de imagem não existe no caminho cadastrado:\n{selected}",
            )
            return
        selected = real_path

        self._open_marker_inline(selected)

    def _open_marker_inline(self, image_path):
        """Abre o mapeamento de pontos DENTRO desta aba (sem janela extra)."""
        self._close_marker_inline(refresh=False)

        marker = ImageMarker(
            session=self.session,
            board=self.selected_board,
            mode="edit",
            instruments=self.instruments,
        )
        marker.setMinimumSize(900, 560)  # o original exigia 1200x750 (janela própria)
        marker.load_image(image_path)
        self.marker_widget = marker

        page = QWidget()
        page.setObjectName("markerPage")
        page.setStyleSheet(
            """
            QWidget#markerPage { background: #0B1220; }
            QFrame#markerBar {
                background: #111827;
                border-bottom: 1px solid #243044;
            }
            QLabel#markerTitle {
                background: transparent;
                color: #F8FAFC;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton#markerBack {
                background: #172033;
                color: #E2E8F0;
                border: 1px solid #334155;
                border-radius: 7px;
                padding: 0px 14px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton#markerBack:hover {
                color: #F8FAFC;
                border: 1px solid #22D3EE;
            }
            """
        )
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("markerBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 8, 12, 8)

        btn_back = QPushButton("←  Voltar aos testes")
        btn_back.setObjectName("markerBack")
        btn_back.setFixedHeight(34)
        btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back.clicked.connect(lambda _checked=False: self._close_marker_inline())

        title = QLabel(
            f"📍 Mapeamento de pontos — {self.selected_board.name} "
            f"(SN: {self.selected_board.serial_number})"
        )
        title.setObjectName("markerTitle")

        bar_layout.addWidget(btn_back)
        bar_layout.addSpacing(12)
        bar_layout.addWidget(title)
        bar_layout.addStretch()

        page_layout.addWidget(bar)
        page_layout.addWidget(marker, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)

        self.marker_page = scroll
        self.stack.addWidget(scroll)
        self.stack.setCurrentWidget(scroll)

    def _close_marker_inline(self, refresh=True):
        """Volta para a tela de testes e descarta o editor de pontos."""
        page = self.marker_page
        self.stack.setCurrentWidget(self.test_scroll)
        if page is not None:
            self.stack.removeWidget(page)
            page.deleteLater()
        self.marker_page = None
        self.marker_widget = None
        if refresh and self.selected_board is not None:
            self.load_board_preview()
            if self.selected_plan is not None:
                self.populate_plan_steps()
            else:
                self.populate_board_points()

    def open_plan_creator(self):
        """Cria um novo plano para a placa selecionada."""
        if not self.selected_board:
            QMessageBox.warning(
                self,
                "Aviso",
                "Selecione uma placa antes de criar um plano.",
            )
            return

        self.create_plan_window = PlanEditor(
            self.session,
            self.selected_board,
        )
        self.create_plan_window.plan_saved.connect(self._on_plan_saved_from_editor)
        self.create_plan_window.show()
        self.create_plan_window.raise_()
        self.create_plan_window.activateWindow()

    def open_plan_editor(self):
        """Edita exclusivamente o plano atualmente selecionado."""
        if not self.selected_board:
            QMessageBox.warning(
                self,
                "Aviso",
                "Selecione uma placa antes de editar um plano.",
            )
            return

        if not self.selected_plan:
            QMessageBox.warning(
                self,
                "Aviso",
                "Selecione um plano antes de editar.",
            )
            return

        self.editor_window = PlanEditor(
            self.session,
            self.selected_board,
            self.selected_plan,
        )
        self.editor_window.plan_saved.connect(self._on_plan_saved_from_editor)
        self.editor_window.show()
        self.editor_window.raise_()
        self.editor_window.activateWindow()

    def _on_plan_saved_from_editor(self, plan):
        """Atualiza o plano mostrado no painel após criar ou editar."""
        if plan is None:
            return
        self.set_selected_plan(plan)
    def closeEvent(self, event):
        try:
            self.scope_client.shutdown()
        except Exception:
            pass
        super().closeEvent(event)

