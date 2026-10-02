from pathlib import Path
from datetime import datetime
import logging

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QColor, QFont, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QInputDialog,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from db.models import BoardUnit
from engine.pdf_report import export_test_report
from engine.runner import run_test
from ui.plan_manager import PlanManager


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
        self.setObjectName("boardPreview")
        self.setMinimumSize(360, 300)
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

        if self._point is None:
            return

        sx = scaled.width() / max(self._pixmap.width(), 1)
        sy = scaled.height() / max(self._pixmap.height(), 1)
        px = x0 + int(self._point[0] * sx)
        py = y0 + int(self._point[1] * sy)

        painter.setPen(QPen(QColor("#EF4444"), 3))
        painter.setBrush(QColor(239, 68, 68, 45))
        painter.drawEllipse(px - 12, py - 12, 24, 24)

        painter.setPen(QPen(QColor("#111827"), 2))
        painter.setBrush(QColor("#FDE047"))
        painter.drawEllipse(px - 4, py - 4, 8, 8)

        if self._refdes:
            fm = painter.fontMetrics()
            label_rect = fm.boundingRect(self._refdes)
            label_rect.adjust(-7, -4, 7, 4)
            label_rect.moveTopLeft(QPoint(px + 14, py - 28))
            painter.fillRect(label_rect, QColor("#111827"))
            painter.setPen(QColor("#F8FAFC"))
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, self._refdes)


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
        self.setObjectName("testGeneralRoot")
        self.apply_styles()

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

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
        self.log_text.setMinimumHeight(120)
        self.log_text.setMaximumHeight(175)

        log_layout.addLayout(log_header)
        log_layout.addWidget(self.log_text)
        root.addWidget(log_card)

    def build_control_panel(self):
        panel = QFrame()
        panel.setObjectName("panelCard")
        panel.setMinimumWidth(265)
        panel.setMaximumWidth(340)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

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
        self.btn_select_board = QPushButton("Selecionar placa")
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

        plan_layout.addWidget(caption)
        plan_layout.addWidget(self.lbl_plan)
        plan_layout.addWidget(self.lbl_plan_meta)
        plan_layout.addWidget(self.btn_select_plan)
        layout.addWidget(plan_box)

        # Ação principal
        exec_caption = QLabel("EXECUÇÃO")
        exec_caption.setObjectName("caption")
        layout.addWidget(exec_caption)

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

        hint = QLabel("ATALHOS\nEspaço  • iniciar teste\nCtrl+L  • limpar log")
        hint.setObjectName("shortcutHint")
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
        panel.setMinimumWidth(360)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("RESULTADOS")
        title.setObjectName("sectionTitle")
        self.results_summary = QLabel("Aguardando teste")
        self.results_summary.setObjectName("mutedText")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.results_summary)

        self.results_table = QTableWidget(0, 4)
        self.results_table.setObjectName("resultsTable")
        self.results_table.setHorizontalHeaderLabels(["Status", "Etapa", "Ponto", "Valor"])
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

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

    def apply_styles(self):
        self.setStyleSheet(
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
        self.shortcut_clear.activated.connect(self.clear_log)

    # ==========================================================
    # ESTADO / LOG
    # ==========================================================

    def _shortcut_start(self):
        if (
            not self.is_test_running
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
        self.selected_board = board

        if (
            self.selected_plan is not None
            and self.selected_plan.board_model_id != board.model_id
        ):
            self.selected_plan = None
            self.lbl_plan.setText("Nenhum plano selecionado")
            self.lbl_plan_meta.setText("Etapas: —")
            self.results_table.setRowCount(0)

        self.lbl_board.setText(board.name)
        self.lbl_board_sn.setText(f"SN: {board.serial_number}")
        self.load_board_preview()
        self.update_button_state()

    def load_board_preview(self):
        self.board_preview.clear_image()
        self.preview_meta.setText("Sem imagem")
        self.preview_point.setText("Ponto atual: —")

        if self.selected_board is None or not self.selected_board.images:
            return

        for image in self.selected_board.images:
            if Path(image.path).exists():
                self.board_preview.load_image(image.path)
                self.preview_meta.setText(Path(image.path).name)
                return

        self.preview_meta.setText("Imagem cadastrada não encontrada")

    def select_board(self):
        boards = self.session.query(BoardUnit).filter_by(is_active=True).all()
        if not boards:
            QMessageBox.warning(self, "Aviso", "Nenhuma placa ativa cadastrada.")
            return

        items = [f"{board.serial_number} - {board.name}" for board in boards]
        item, ok = QInputDialog.getItem(
            self, "Selecionar Placa", "Escolha a placa:", items, 0, False
        )
        if not ok or not item:
            return

        serial_number = item.split(" - ", 1)[0]
        board = (
            self.session.query(BoardUnit)
            .filter_by(serial_number=serial_number)
            .first()
        )
        if board is None:
            QMessageBox.warning(self, "Erro", "A placa selecionada não foi encontrada.")
            return

        self._set_board(board)
        self.log(f"🔌 Placa selecionada: {board.name} (SN: {board.serial_number})")

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
        self.results_table.setRowCount(0)
        if self.selected_plan is None:
            self.results_summary.setText("Aguardando teste")
            return

        steps = sorted(self.selected_plan.steps, key=lambda step: step.order_index)
        for row, step in enumerate(steps):
            self.results_table.insertRow(row)
            self.results_table.setItem(row, 0, QTableWidgetItem("○"))
            self.results_table.setItem(row, 1, QTableWidgetItem(step.description or f"Etapa {row + 1}"))
            refdes = step.test_point.refdes if step.test_point else "—"
            self.results_table.setItem(row, 2, QTableWidgetItem(refdes))

            expected = "—"
            if step.desired_value is not None:
                expected = f"{step.desired_value:g} {step.unit or ''}".strip()
                if step.tolerance is not None:
                    expected += f" ± {step.tolerance:g}"
            self.results_table.setItem(row, 3, QTableWidgetItem(expected))

        self.results_summary.setText(f"{len(steps)} etapas preparadas")

    def update_button_state(self):
        # Mantém os botões clicáveis fora da execução.
        # select_plan(), start_test() e generate_report() já fazem
        # suas próprias validações e mostram mensagens ao usuário.
        enabled = not self.is_test_running
        self.btn_select_board.setEnabled(enabled)
        self.btn_select_plan.setEnabled(enabled)
        self.btn_start_test.setEnabled(enabled)
        self.btn_export_report.setEnabled(enabled)

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
        self.btn_start_test.setEnabled(enabled)
        self.btn_export_report.setEnabled(enabled)

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

            self.results_table.setItem(row, 0, QTableWidgetItem(status))
            self.results_table.setItem(row, 1, QTableWidgetItem(step.description or "—"))
            self.results_table.setItem(row, 2, QTableWidgetItem(refdes))
            self.results_table.setItem(row, 3, QTableWidgetItem(f"{value} {unit}".strip()))

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

        if not Path(selected).exists():
            QMessageBox.warning(
                self,
                "Imagem não encontrada",
                f"O arquivo de imagem não existe no caminho cadastrado:\n{selected}",
            )
            return None
        return selected
