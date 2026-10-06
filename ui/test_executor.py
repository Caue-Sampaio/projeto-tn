from pathlib import Path
from datetime import datetime
import logging

from PyQt6.QtCore import Qt, QPoint
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

from db.models import BoardUnit, Machine
from engine.pdf_report import export_test_report
from engine.runner import run_test
from ui.plan_manager import PlanManager
from utils.image_paths import resolve_image_path, heal_board_images, import_image_to_project
from ui.image_marker import ImageMarker
from ui.plan_editor import PlanEditor


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
        """Exibe todos os pontos da placa de uma só vez.

        Aceita objetos TestPoint ou tuplas (x, y, refdes).
        """
        normalized = []
        for point in points or []:
            try:
                x = float(getattr(point, "x", point[0] if isinstance(point, (tuple, list)) else 0))
                y = float(getattr(point, "y", point[1] if isinstance(point, (tuple, list)) else 0))
                refdes = str(getattr(point, "refdes", point[2] if isinstance(point, (tuple, list)) and len(point) > 2 else "") or "")
            except Exception:
                continue
            normalized.append((x, y, refdes))
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

        # Desenha TODOS os pontos automaticamente.
        for x, y, refdes in self._points:
            px = x0 + int(x * sx)
            py = y0 + int(y * sy)
            painter.setPen(QPen(QColor("#EF4444"), 2))
            painter.setBrush(QColor(229, 57, 53, 165))
            painter.drawEllipse(px - 5, py - 5, 10, 10)

            if refdes:
                painter.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
                fm = painter.fontMetrics()
                label_rect = fm.boundingRect(refdes)
                label_rect.adjust(-4, -2, 4, 2)
                label_rect.moveTopLeft(QPoint(px + 7, py - 18))
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
        subtitle = QLabel("1. Escolha a máquina     2. Escolha a placa dela")
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

        machine_label = QLabel("MÁQUINA")
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
            self.machine_combo.addItem(f"Sem máquina  —  {count} placa(s) ativa(s)", self.NO_MACHINE)

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

        # Começa na máquina/placa que já estava selecionada
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
            self.info_label.setText(f"{len(boards)} placa(s) ativa(s) nesta máquina")
        else:
            self.info_label.setText("Nenhuma placa ativa nesta máquina.")
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
        self.btn_select_board = QPushButton("Selecionar maquina/placa")
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

        # Ação principal
        exec_caption = QLabel("PREPARAÇÃO & EXECUÇÃO")
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

        self.btn_start_test = QPushButton("▶  INICIAR TESTE")
        self.btn_start_test.setObjectName("primaryButton")
        self.btn_start_test.setFixedHeight(46)
        self.btn_start_test.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_start_test.setMinimumHeight(46)
        self.btn_start_test.setToolTip("Inicia o plano de teste selecionado. Atalho: Espaço.")
        self.btn_start_test.clicked.connect(self.start_test)
        layout.addWidget(self.btn_start_test)

        self.btn_export_report = QPushButton("Exportar último relatório")
        self.btn_export_report.setObjectName("secondaryButton")
        self.btn_export_report.setFixedHeight(40)
        self.btn_export_report.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_export_report.setToolTip("Exporta em PDF o último teste realizado nesta sessão.")
        self.btn_export_report.clicked.connect(self.generate_report)
        layout.addWidget(self.btn_export_report)

        layout.addStretch()

        hint = QLabel("Espaço: iniciar teste  •  Ctrl+L: limpar log")
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

        if (
            self.selected_plan is not None
            and self.selected_plan.board_model_id != board.model_id
        ):
            self.selected_plan = None
            self.lbl_plan.setText("Nenhum plano selecionado")
            self.lbl_plan_meta.setText("Etapas: —")

        self.lbl_board.setText(board.name)
        machine_text = f"  •  Máquina: {board.machine.name}" if board.machine else ""
        self.lbl_board_sn.setText(f"SN: {board.serial_number}{machine_text}")
        self.load_board_preview()
        if self.selected_plan is not None:
            self.populate_plan_steps()
        else:
            self.populate_board_points()
        self.update_button_state()

    def load_board_preview(self):
        self.board_preview.clear_image()
        self.preview_meta.setText("Sem imagem")
        self.preview_point.setText("Ponto atual: —")

        if self.selected_board is None or not self.selected_board.images:
            return

        # Regrava os caminhos como absolutos (quando o arquivo é encontrado)
        missing = heal_board_images(self.session, self.selected_board)

        for image in self.selected_board.images:
            if image not in missing:
                self.board_preview.load_image(image.path)
                self.preview_meta.setText(Path(image.path).name)
                return

        # Nenhuma imagem encontrada: pede para o usuário apontar o arquivo
        self.preview_meta.setText("Imagem cadastrada não encontrada")
        self._relocate_missing_image(missing[0])

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
        machine = f" | Máquina: {board.machine.name}" if board.machine else ""
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

    def _point_expected_basic(self, point):
        """Retorna apenas a referência principal do ponto para a tela de teste."""
        if point is None:
            return "—"
        if getattr(point, "expected_voltage_v", None) is not None:
            return self._format_compact_value(point.expected_voltage_v, "V")
        if getattr(point, "expected_frequency_hz", None) is not None:
            return self._format_compact_value(point.expected_frequency_hz, "Hz")
        if getattr(point, "expected_current_a", None) is not None:
            return self._format_compact_value(point.expected_current_a, "A")
        waveform = getattr(point, "expected_waveform", None)
        if waveform:
            return str(waveform)
        return "—"

    def populate_board_points(self):
        """Mostra os pontos da placa mesmo antes de um plano ser selecionado."""
        self.results_table.setRowCount(0)
        if self.selected_board is None:
            self.results_summary.setText("Selecione uma placa")
            return

        points = sorted(
            list(getattr(self.selected_board, "test_points", []) or []),
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

            expected = "—"
            if step.desired_value is not None:
                expected = self._format_compact_value(step.desired_value, step.unit or "")
            elif point is not None:
                expected = self._point_expected_basic(point)
            self.results_table.setItem(row, 1, QTableWidgetItem(expected))
            self.results_table.setItem(row, 2, QTableWidgetItem("—"))
            self.results_table.setItem(row, 3, QTableWidgetItem("Pronto"))

        # No plano, mantém todos os pontos associados visíveis de uma vez.
        plan_points = [step.test_point for step in steps if step.test_point is not None]
        self.board_preview.set_test_points(plan_points)
        self.board_preview.clear_test_point()
        self.preview_point.setText(
            f"{len(plan_points)} ponto(s) do plano visíveis" if plan_points else "Ponto atual: —"
        )

        self.results_summary.setText(f"{len(steps)} ponto(s) no plano")
        self.results_table.clearSelection()
        self.results_table.setCurrentCell(-1, -1)

    def update_button_state(self):
        # Mantém os botões clicáveis fora da execução.
        # select_plan(), start_test() e generate_report() já fazem
        # suas próprias validações e mostram mensagens ao usuário.
        enabled = not self.is_test_running
        self.btn_select_board.setEnabled(enabled)
        self.btn_select_plan.setEnabled(enabled)
        self.btn_create_plan.setEnabled(enabled)
        self.btn_start_test.setEnabled(enabled)
        self.btn_export_report.setEnabled(enabled)
        self.btn_map_points.setEnabled(enabled)
        self.btn_plan_editor.setEnabled(enabled)

    def check_can_start(self):
        self.update_button_state()

    # ==========================================================
    # EXECUÇÃO
    # ==========================================================

    def start_test(self):
        if not self.selected_board or not self.selected_plan:
            QMessageBox.warning(
                self,
                "Aviso",
                "Selecione uma placa e um plano de teste antes de iniciar.",
            )
            return

        if not self.selected_plan.steps:
            QMessageBox.warning(self, "Plano vazio", "O plano selecionado não possui etapas de teste.")
            return

        self.is_test_running = True
        self.progress_bar.setValue(0)
        self.progress_value_label.setText("0%")
        self.current_step_label.setText("Etapa: preparando execução")
        self.results_summary.setText("Teste em execução")
        self.board_preview.clear_test_point()
        self.preview_point.setText("Ponto atual: —")
        self.set_status("Executando", "running")
        self._set_execution_controls(False)

        self.log("=" * 58)
        self.log(f"▶ Iniciando teste: {self.selected_plan.name}")
        self.log(
            f"Placa: {self.selected_board.name} "
            f"(SN: {self.selected_board.serial_number})"
        )
        self.log("=" * 58)
        QApplication.processEvents()

        try:
            run, measurements = run_test(
                session=self.session,
                plan=self.selected_plan,
                board=self.selected_board,
                operator=self.user,
                instruments=self.instruments,
                highlight_callback=self.highlight_test_point,
                progress_callback=self.update_progress,
            )
            self.last_run = run
            self.display_test_results(run, measurements)

            reply = QMessageBox.question(
                self,
                "Relatório",
                "Teste concluído. Deseja gerar o relatório em PDF?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.generate_report()

        except Exception as exc:
            self.session.rollback()
            self.log(f"❌ ERRO DURANTE O TESTE: {exc}")
            logger.exception("Erro durante execução do teste")
            self.set_status("Erro", "error")
            self.results_summary.setText("Falha durante execução")
            QMessageBox.critical(
                self,
                "Erro durante o teste",
                f"Ocorreu um erro durante o teste:\n{exc}",
            )
        finally:
            self.is_test_running = False
            self._set_execution_controls(True)
            self.update_button_state()
            self.current_step_label.setText("Etapa: finalizada")

    def _set_execution_controls(self, enabled):
        # Durante um teste, bloqueia ações que poderiam mudar o contexto.
        # Fora da execução, todos voltam a responder ao clique.
        self.btn_select_board.setEnabled(enabled)
        self.btn_select_plan.setEnabled(enabled)
        self.btn_create_plan.setEnabled(enabled)
        self.btn_start_test.setEnabled(enabled)
        self.btn_export_report.setEnabled(enabled)
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
