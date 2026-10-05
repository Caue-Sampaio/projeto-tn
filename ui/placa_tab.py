# ui/placa_tab.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QMessageBox, QFileDialog, QFormLayout,
    QGroupBox, QTabWidget, QTextEdit, QComboBox, QDialog, QDialogButtonBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QFrame,
    QProgressBar, QInputDialog, QListWidgetItem, QCheckBox, QSizePolicy, QGridLayout,
    QTreeWidget, QTreeWidgetItem, QScrollArea, QStyledItemDelegate
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QPixmap, QBrush, QColor, QIcon
from sqlalchemy import func
from sqlalchemy.orm import Session
from db.models import BoardUnit, BoardModel, User, BoardImage, TestPoint, TestPlan, TestRun, Machine
from engine.logger import log_user_action
from utils.image_paths import import_image_to_project, resolve_image_path, heal_board_images
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# Dado guardado em cada nó da árvore: ("machine" | "board" | "orphan", id)
NODE_ROLE = Qt.ItemDataRole.UserRole

def clear_layout(layout):
    """Remove widgets E sub-layouts de um layout (evita botões 'fantasma')."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())
            item.layout().deleteLater()


class CleanCellEditDelegate(QStyledItemDelegate):
    """Editor inline com margem real dentro da célula.

    O editor padrão do Qt ocupa todo o retângulo do item e, combinado com o
    padding da tabela, pode parecer cortado/fora de alinhamento. Este delegate
    mantém o campo alguns pixels para dentro da célula e preserva a mesma
    linguagem visual do restante da interface.
    """

    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            editor.setObjectName("pointsInlineEditor")
            editor.setMinimumHeight(30)
        return editor

    def updateEditorGeometry(self, editor, option, index):
        # Mantém o editor totalmente dentro da linha, evitando clipping.
        editor.setGeometry(option.rect.adjusted(4, 4, -4, -4))


class ImagePreviewLabel(QLabel):
    """Mostra a imagem da placa redimensionada, mantendo a proporção."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(280, 220)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setStyleSheet(
            "background-color: #0F172A; color: #94A3B8; "
            "border: 1px solid #E2E8F0; border-radius: 12px; padding: 6px;"
        )
        self.show_message("Sem imagem")

    def show_message(self, text):
        self._pixmap = QPixmap()
        self.clear()
        self.setText(text)

    def load(self, path):
        pix = QPixmap(str(path))
        if pix.isNull():
            self.show_message("Não foi possível abrir a imagem:\n" + str(path))
            return False
        self._pixmap = pix
        self._rescale()
        return True

    def _rescale(self):
        if self._pixmap.isNull():
            return
        target = QSize(max(1, self.width() - 16), max(1, self.height() - 16))
        self.setText("")
        self.setPixmap(
            self._pixmap.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()


class BoardDialog(QDialog):
    """Janela para cadastrar uma placa dentro de uma máquina (com imagem opcional)."""

    def __init__(self, machines, submit, parent=None, machine_id=None):
        """machines: lista de (id, texto). submit: função que grava a placa e
        devolve (placa, None) ou (None, mensagem_de_erro)."""
        super().__init__(parent)
        self._submit = submit
        self._image_path = None
        self.created_board = None

        self.setWindowTitle("Nova Placa")
        self.setModal(True)
        self.setMinimumWidth(540)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("dlgHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 18, 24, 18)
        header_layout.setSpacing(2)
        title = QLabel("🔌  Nova placa")
        title.setObjectName("dlgTitle")
        subtitle = QLabel("Cadastre a placa e escolha a máquina à qual ela pertence.")
        subtitle.setObjectName("dlgSubtitle")
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        body = QFrame()
        body.setObjectName("dlgBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 18, 24, 12)
        body_layout.setSpacing(6)

        def field_label(text):
            label = QLabel(text)
            label.setObjectName("dlgFieldLabel")
            return label

        def line_edit(placeholder):
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            edit.setMinimumHeight(40)
            return edit

        self.machine_combo = QComboBox()
        self.machine_combo.setMinimumHeight(40)
        self.machine_combo.addItem("— Sem máquina —", None)
        for mid, text in machines:
            self.machine_combo.addItem(text, mid)
        if machine_id is not None:
            index = self.machine_combo.findData(machine_id)
            if index >= 0:
                self.machine_combo.setCurrentIndex(index)

        self.name_input = line_edit("Ex: Placa de Controle, Fonte Principal...")
        self.model_input = line_edit("Ex: PCB-X1, MainBoard...")
        self.version_input = line_edit("Ex: 1.0, RevA...")
        self.serial_input = line_edit("Ex: SN001, 2024001...")

        model_box = QVBoxLayout()
        model_box.setSpacing(6)
        model_box.addWidget(field_label("MODELO *"))
        model_box.addWidget(self.model_input)
        version_box = QVBoxLayout()
        version_box.setSpacing(6)
        version_box.addWidget(field_label("VERSÃO *"))
        version_box.addWidget(self.version_input)
        model_row = QHBoxLayout()
        model_row.setSpacing(14)
        model_row.addLayout(model_box, 1)
        model_row.addLayout(version_box, 1)

        self.error_label = QLabel("")
        self.error_label.setObjectName("dlgError")
        self.error_label.setWordWrap(True)

        self.image_preview = QLabel("Sem imagem")
        self.image_preview.setObjectName("dlgImage")
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setFixedSize(170, 112)

        pick_btn = QPushButton("🖼️  Escolher imagem")
        pick_btn.setObjectName("dlgGhost")
        pick_btn.setMinimumHeight(36)
        pick_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pick_btn.clicked.connect(self._pick_image)
        remove_btn = QPushButton("Remover imagem")
        remove_btn.setObjectName("dlgGhost")
        remove_btn.setMinimumHeight(36)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(self._remove_image)
        image_buttons = QVBoxLayout()
        image_buttons.setSpacing(8)
        image_buttons.addWidget(pick_btn)
        image_buttons.addWidget(remove_btn)
        image_buttons.addStretch()
        image_row = QHBoxLayout()
        image_row.setSpacing(14)
        image_row.addWidget(self.image_preview)
        image_row.addLayout(image_buttons, 1)

        body_layout.addWidget(field_label("MÁQUINA"))
        body_layout.addWidget(self.machine_combo)
        body_layout.addSpacing(6)
        body_layout.addWidget(field_label("NOME DA PLACA *"))
        body_layout.addWidget(self.name_input)
        body_layout.addSpacing(6)
        body_layout.addLayout(model_row)
        body_layout.addSpacing(6)
        body_layout.addWidget(field_label("NÚMERO DE SÉRIE *"))
        body_layout.addWidget(self.serial_input)
        body_layout.addWidget(self.error_label)
        body_layout.addSpacing(4)
        body_layout.addWidget(field_label("IMAGEM DA PLACA (OPCIONAL)"))
        body_layout.addLayout(image_row)
        root.addWidget(body)

        footer = QFrame()
        footer.setObjectName("dlgFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 14, 24, 18)
        footer_layout.addStretch()
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setObjectName("dlgCancel")
        cancel_btn.setMinimumSize(110, 38)
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Cadastrar placa")
        save_btn.setObjectName("dlgSave")
        save_btn.setMinimumSize(160, 38)
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        footer_layout.addWidget(cancel_btn)
        footer_layout.addWidget(save_btn)
        root.addWidget(footer)

        self.setStyleSheet("""
            QDialog { background: #FFFFFF; }
            QFrame#dlgHeader {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #0F766E, stop:1 #0284C7);
            }
            QLabel#dlgTitle {
                color: #FFFFFF; font-size: 18px; font-weight: 700; background: transparent;
            }
            QLabel#dlgSubtitle { color: #E0F2FE; font-size: 12px; background: transparent; }
            QFrame#dlgBody { background: #FFFFFF; }
            QFrame#dlgFooter { background: #F8FAFC; border-top: 1px solid #E2E8F0; }
            QLabel#dlgFieldLabel {
                color: #475569; font-size: 11px; font-weight: 700; background: transparent;
            }
            QLabel#dlgError {
                color: #DC2626; font-size: 12px; font-weight: 600; background: transparent;
            }
            QLabel#dlgImage {
                background: #F8FAFC; color: #94A3B8; font-size: 12px;
                border: 1.5px dashed #CBD5E1; border-radius: 10px;
            }
            QLineEdit, QComboBox {
                background: #FFFFFF; color: #0F172A;
                border: 1.5px solid #CBD5E1; border-radius: 8px;
                padding: 8px 12px; font-size: 13px;
                selection-background-color: #0284C7; selection-color: #FFFFFF;
            }
            QLineEdit:focus, QComboBox:focus { border: 1.5px solid #0284C7; }
            QComboBox QAbstractItemView {
                background: #FFFFFF; color: #0F172A;
                selection-background-color: #0284C7; selection-color: #FFFFFF;
            }
            QPushButton#dlgGhost {
                background: #F1F5F9; color: #1E293B;
                border: 1px solid #CBD5E1; border-radius: 8px;
                padding: 6px 14px; font-weight: 600; font-size: 12px;
            }
            QPushButton#dlgGhost:hover { background: #E2E8F0; }
            QPushButton#dlgCancel {
                background: #FFFFFF; color: #334155;
                border: 1.5px solid #CBD5E1; border-radius: 8px;
                padding: 8px 18px; font-weight: 600; font-size: 13px;
            }
            QPushButton#dlgCancel:hover { background: #F1F5F9; }
            QPushButton#dlgSave {
                background: #0F766E; color: #FFFFFF;
                border: 1px solid #0D9488; border-radius: 8px;
                padding: 8px 20px; font-weight: 700; font-size: 13px;
            }
            QPushButton#dlgSave:hover { background: #0D9488; }
        """)
        self.name_input.setFocus()

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Escolher imagem da placa", "",
            "Imagens (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
        )
        if path:
            self._image_path = path
            self._refresh_image_preview()

    def _remove_image(self):
        self._image_path = None
        self._refresh_image_preview()

    def _refresh_image_preview(self):
        pixmap = QPixmap(self._image_path) if self._image_path else QPixmap()
        if pixmap.isNull():
            self.image_preview.clear()
            self.image_preview.setText("Sem imagem")
            return
        self.image_preview.setText("")
        self.image_preview.setPixmap(
            pixmap.scaled(
                QSize(160, 102),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _save(self, *_args):
        board, error = self._submit(
            self.name_input.text().strip(),
            self.model_input.text().strip(),
            self.version_input.text().strip(),
            self.serial_input.text().strip(),
            self.machine_combo.currentData(),
            self._image_path,
        )
        if error:
            self.error_label.setText(error)  # o erro aparece aqui dentro, sem fechar a janela
            return
        self.created_board = board
        self.accept()


class MachineDialog(QDialog):
    """Janela para cadastrar ou editar uma máquina (com imagem ilustrativa opcional)."""

    def __init__(self, parent=None, machine=None):
        super().__init__(parent)
        editing = machine is not None
        self.setWindowTitle("Editar Máquina" if editing else "Nova Máquina")
        self.setModal(True)
        self.setMinimumWidth(500)
        self._image_path = machine.image_path if (machine and machine.image_path) else None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Cabeçalho
        header = QFrame()
        header.setObjectName("dlgHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 18, 24, 18)
        header_layout.setSpacing(2)
        title = QLabel("🏭  Editar máquina" if editing else "🏭  Nova máquina")
        title.setObjectName("dlgTitle")
        subtitle = QLabel(
            "Atualize os dados do equipamento." if editing
            else "Cadastre o equipamento. Depois você poderá adicionar as placas que ele possui."
        )
        subtitle.setObjectName("dlgSubtitle")
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        # Corpo
        body = QFrame()
        body.setObjectName("dlgBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 12)
        body_layout.setSpacing(6)

        def field_label(text):
            label = QLabel(text)
            label.setObjectName("dlgFieldLabel")
            return label

        self.name_input = QLineEdit(machine.name if machine else "")
        self.name_input.setPlaceholderText("Ex: Fresadora CNC 01, Inversor Linha 2...")
        self.name_input.setMinimumHeight(40)
        self.name_input.returnPressed.connect(self._validate)

        self.code_input = QLineEdit((machine.code or "") if machine else "")
        self.code_input.setPlaceholderText("Ex: MAQ-001")
        self.code_input.setMinimumHeight(40)

        self.desc_input = QTextEdit()
        self.desc_input.setPlaceholderText("Observações sobre a máquina (local, linha de produção, fabricante...)")
        self.desc_input.setFixedHeight(80)
        if machine and machine.description:
            self.desc_input.setPlainText(machine.description)

        self.error_label = QLabel("")
        self.error_label.setObjectName("dlgError")

        # Imagem ilustrativa
        self.image_preview = QLabel("Sem imagem")
        self.image_preview.setObjectName("dlgImage")
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setFixedSize(170, 112)

        pick_btn = QPushButton("🖼️  Escolher imagem")
        pick_btn.setObjectName("dlgGhost")
        pick_btn.setMinimumHeight(36)
        pick_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pick_btn.clicked.connect(self._pick_image)

        remove_btn = QPushButton("Remover imagem")
        remove_btn.setObjectName("dlgGhost")
        remove_btn.setMinimumHeight(36)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(self._remove_image)

        image_buttons = QVBoxLayout()
        image_buttons.setSpacing(8)
        image_buttons.addWidget(pick_btn)
        image_buttons.addWidget(remove_btn)
        image_buttons.addStretch()

        image_row = QHBoxLayout()
        image_row.setSpacing(14)
        image_row.addWidget(self.image_preview)
        image_row.addLayout(image_buttons, 1)

        body_layout.addWidget(field_label("NOME DA MÁQUINA *"))
        body_layout.addWidget(self.name_input)
        body_layout.addWidget(self.error_label)
        body_layout.addSpacing(4)
        body_layout.addWidget(field_label("CÓDIGO (OPCIONAL)"))
        body_layout.addWidget(self.code_input)
        body_layout.addSpacing(10)
        body_layout.addWidget(field_label("DESCRIÇÃO (OPCIONAL)"))
        body_layout.addWidget(self.desc_input)
        body_layout.addSpacing(10)
        body_layout.addWidget(field_label("IMAGEM ILUSTRATIVA (OPCIONAL)"))
        body_layout.addLayout(image_row)
        root.addWidget(body)

        # Rodapé
        footer = QFrame()
        footer.setObjectName("dlgFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 14, 24, 18)
        footer_layout.addStretch()

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setObjectName("dlgCancel")
        cancel_btn.setMinimumSize(110, 38)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Salvar alterações" if editing else "Cadastrar máquina")
        save_btn.setObjectName("dlgSave")
        save_btn.setMinimumSize(160, 38)
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._validate)

        footer_layout.addWidget(cancel_btn)
        footer_layout.addWidget(save_btn)
        root.addWidget(footer)

        # Cores explícitas: o diálogo não depende do estilo de nenhuma tela por trás
        self.setStyleSheet("""
            QDialog { background: #FFFFFF; }
            QFrame#dlgHeader {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #0F766E, stop:1 #0284C7);
            }
            QLabel#dlgTitle {
                color: #FFFFFF; font-size: 18px; font-weight: 700; background: transparent;
            }
            QLabel#dlgSubtitle { color: #E0F2FE; font-size: 12px; background: transparent; }
            QFrame#dlgBody { background: #FFFFFF; }
            QFrame#dlgFooter { background: #F8FAFC; border-top: 1px solid #E2E8F0; }
            QLabel#dlgFieldLabel {
                color: #475569; font-size: 11px; font-weight: 700; background: transparent;
            }
            QLabel#dlgError { color: #DC2626; font-size: 12px; background: transparent; }
            QLabel#dlgImage {
                background: #F8FAFC; color: #94A3B8; font-size: 12px;
                border: 1.5px dashed #CBD5E1; border-radius: 10px;
            }
            QLineEdit, QTextEdit {
                background: #FFFFFF; color: #0F172A;
                border: 1.5px solid #CBD5E1; border-radius: 8px;
                padding: 8px 12px; font-size: 13px;
                selection-background-color: #0284C7; selection-color: #FFFFFF;
            }
            QLineEdit:focus, QTextEdit:focus { border: 1.5px solid #0284C7; }
            QPushButton#dlgGhost {
                background: #F1F5F9; color: #1E293B;
                border: 1px solid #CBD5E1; border-radius: 8px;
                padding: 6px 14px; font-weight: 600; font-size: 12px;
            }
            QPushButton#dlgGhost:hover { background: #E2E8F0; }
            QPushButton#dlgCancel {
                background: #FFFFFF; color: #334155;
                border: 1.5px solid #CBD5E1; border-radius: 8px;
                padding: 8px 18px; font-weight: 600; font-size: 13px;
            }
            QPushButton#dlgCancel:hover { background: #F1F5F9; }
            QPushButton#dlgSave {
                background: #0F766E; color: #FFFFFF;
                border: 1px solid #0D9488; border-radius: 8px;
                padding: 8px 20px; font-weight: 700; font-size: 13px;
            }
            QPushButton#dlgSave:hover { background: #0D9488; }
        """)
        self._refresh_image_preview()
        self.name_input.setFocus()

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Escolher imagem da máquina", "",
            "Imagens (*.png *.jpg *.jpeg *.bmp *.gif *.webp)",
        )
        if path:
            self._image_path = path
            self._refresh_image_preview()

    def _remove_image(self):
        self._image_path = None
        self._refresh_image_preview()

    def _refresh_image_preview(self):
        real = resolve_image_path(self._image_path) if self._image_path else None
        pixmap = QPixmap(real) if real else QPixmap()
        if pixmap.isNull():
            self.image_preview.clear()
            self.image_preview.setText("Sem imagem" if not self._image_path else "Imagem\nnão encontrada")
            return
        self.image_preview.setText("")
        self.image_preview.setPixmap(
            pixmap.scaled(
                QSize(160, 102),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _validate(self):
        if not self.name_input.text().strip():
            self.error_label.setText("Informe o nome da máquina.")
            self.name_input.setFocus()
            return
        self.accept()

    def values(self):
        """Devolve (nome, código, descrição, caminho_da_imagem_ou_None)."""
        return (
            self.name_input.text().strip(),
            self.code_input.text().strip(),
            self.desc_input.toPlainText().strip(),
            self._image_path,
        )


class BoardDetailsDialog(QDialog):
    """Dialog para visualizar detalhes completos da placa"""
    
    def __init__(self, board, session):
        super().__init__()
        self.board = board
        self.session = session
        
        self.setWindowTitle(f"Detalhes da Placa - {board.name}")
        self.setMinimumSize(700, 600)
        
        self.setup_ui()
        self.load_board_data()
        self.apply_styles()
        
    def setup_ui(self):
        """Detalhes da placa em uma janela limpa, com navegação por abas."""
        self.setObjectName("boardDetailsDialog")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        layout.addWidget(self.create_header())

        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("boardDetailsTabs")
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.addTab(self.create_info_tab(), "Informações")
        self.tab_widget.addTab(self.create_points_tab(), "Pontos de teste")
        self.tab_widget.addTab(self.create_history_tab(), "Histórico")
        self.tab_widget.addTab(self.create_images_tab(), "Imagens")
        layout.addWidget(self.tab_widget, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        close_btn.setText("Fechar")
        close_btn.setObjectName("detailsClose")
        layout.addWidget(buttons)

    def create_header(self):
        """Cabeçalho contextual da placa."""
        frame = QFrame()
        frame.setObjectName("boardDetailsHeader")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        info = QVBoxLayout()
        info.setSpacing(3)
        self.title_label = QLabel(self.board.name)
        self.title_label.setObjectName("boardDetailsTitle")
        self.subtitle_label = QLabel(
            f"{self.board.model}  •  S/N: {self.board.serial_number}"
        )
        self.subtitle_label.setObjectName("boardDetailsSubtitle")
        info.addWidget(self.title_label)
        info.addWidget(self.subtitle_label)
        layout.addLayout(info, 1)

        status = QLabel("ATIVA" if self.board.is_active else "INATIVA")
        status.setObjectName("boardStatusActive" if self.board.is_active else "boardStatusInactive")
        layout.addWidget(status, alignment=Qt.AlignmentFlag.AlignTop)
        return frame

    def create_info_tab(self):
        """Cria aba de informações"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Informações básicas
        basic_group = QGroupBox("Informações da Placa")
        basic_layout = QFormLayout()
        
        self.name_label = QLabel(self.board.name)
        self.model_label = QLabel(f"{self.board.model} v{self.board.version}")
        self.serial_label = QLabel(self.board.serial_number)
        self.operator_label = QLabel(self.board.operator.username if self.board.operator else "N/A")
        self.created_label = QLabel(self.board.created_at.strftime("%d/%m/%Y %H:%M") if self.board.created_at else "N/A")
        self.status_label = QLabel("✅ Ativa" if self.board.is_active else "❌ Inativa")
        
        basic_layout.addRow("Nome:", self.name_label)
        basic_layout.addRow("Modelo/Versão:", self.model_label)
        self.machine_label = QLabel(self.board.machine.name if self.board.machine else "Sem máquina")
        basic_layout.addRow("Máquina:", self.machine_label)
        basic_layout.addRow("Número de Série:", self.serial_label)
        basic_layout.addRow("Operador:", self.operator_label)
        basic_layout.addRow("Criada em:", self.created_label)
        basic_layout.addRow("Status:", self.status_label)
        
        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)
        
        # Estatísticas
        stats_group = QGroupBox("Estatísticas")
        stats_layout = QFormLayout()
        
        # Calcula estatísticas
        points_count = self.session.query(TestPoint).filter_by(board_id=self.board.id).count()
        plans_count = self.session.query(TestPlan).filter_by(board_model_id=self.board.model_id).count()
        runs_count = self.session.query(TestRun).filter_by(board_id=self.board.id).count()
        images_count = self.session.query(BoardImage).filter_by(board_id=self.board.id).count()
        
        self.points_label = QLabel(str(points_count))
        self.plans_label = QLabel(str(plans_count))
        self.runs_label = QLabel(str(runs_count))
        self.images_label = QLabel(str(images_count))
        
        stats_layout.addRow("Pontos de Teste:", self.points_label)
        stats_layout.addRow("Planos de Teste:", self.plans_label)
        stats_layout.addRow("Execuções:", self.runs_label)
        stats_layout.addRow("Imagens:", self.images_label)
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        layout.addStretch()
        
        widget.setLayout(layout)
        return widget
        
    def create_points_tab(self):
        """Cria aba de pontos de teste"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Tabela de pontos
        self.points_table = QTableWidget()
        self.points_table.setColumnCount(5)
        self.points_table.setHorizontalHeaderLabels([
            "RefDes", "X", "Y", "Tensão Esperada", "Corrente Esperada"
        ])

        # O editor padrão do QTableWidget ficava visualmente quebrado ao
        # entrar em edição. O delegate abaixo corrige a geometria do campo sem
        # alterar a lógica de edição já existente.
        self.points_table.setItemDelegate(CleanCellEditDelegate(self.points_table))
        self.points_table.verticalHeader().setDefaultSectionSize(40)
        self.points_table.verticalHeader().setMinimumSectionSize(40)

        # Configurar cabeçalho
        header = self.points_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # RefDes
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # X
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Y
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # Tensão
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)  # Corrente
        
        # Carrega pontos
        points = self.session.query(TestPoint).filter_by(board_id=self.board.id).all()
        self.points_table.setRowCount(len(points))
        
        for row, point in enumerate(points):
            self.points_table.setItem(row, 0, QTableWidgetItem(point.refdes))
            self.points_table.setItem(row, 1, QTableWidgetItem(str(point.x)))
            self.points_table.setItem(row, 2, QTableWidgetItem(str(point.y)))
            self.points_table.setItem(row, 3, QTableWidgetItem(
                f"{point.expected_voltage_v:.3f} V" if point.expected_voltage_v else "-"
            ))
            self.points_table.setItem(row, 4, QTableWidgetItem(
                f"{point.expected_current_a:.3f} A" if point.expected_current_a else "-"
            ))
        
        layout.addWidget(QLabel(f"Total de pontos: {len(points)}"))
        layout.addWidget(self.points_table)
        
        widget.setLayout(layout)
        return widget
        
    def create_history_tab(self):
        """Cria aba de histórico de testes"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Lista de execuções
        self.runs_list = QListWidget()
        
        # Carrega histórico
        runs = self.session.query(TestRun).filter_by(board_id=self.board.id).order_by(TestRun.start_time.desc()).limit(50).all()
        
        for run in runs:
            status_icon = "✅" if run.status == "completed" else "❌" if run.status == "failed" else "🔄"
            plan_name = run.plan.name if run.plan else "N/A"
            item_text = f"{status_icon} {run.start_time.strftime('%d/%m/%Y %H:%M')} - {plan_name} - {run.status}"
            
            item = QListWidgetItem(item_text)  # ✅ AGORA CORRETO
            self.runs_list.addItem(item)
            
        layout.addWidget(QLabel(f"Últimas {len(runs)} execuções:"))
        layout.addWidget(self.runs_list)
        
        widget.setLayout(layout)
        return widget
        
    def create_images_tab(self):
        """Cria aba de imagens"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Lista de imagens
        self.images_list = QListWidget()
        
        # Carrega imagens
        images = self.session.query(BoardImage).filter_by(board_id=self.board.id).all()
        
        for image in images:
            filename = os.path.basename(image.path)
            item_text = f"🖼️ {filename}"
            if image.description:
                item_text += f" - {image.description}"
                
            item = QListWidgetItem(item_text)  # ✅ AGORA CORRETO
            item.setToolTip(image.path)
            item.setData(Qt.ItemDataRole.UserRole, image.path)
            self.images_list.addItem(item)

        self.images_list.setMaximumHeight(110)
        self.dialog_preview = ImagePreviewLabel()
        self.images_list.currentItemChanged.connect(self._on_dialog_image_changed)

        layout.addWidget(QLabel(f"Imagens associadas ({len(images)}):"))
        layout.addWidget(self.images_list)
        layout.addWidget(self.dialog_preview, 1)

        if images:
            self.images_list.setCurrentRow(0)
        else:
            self.dialog_preview.show_message("Nenhuma imagem cadastrada.")
        
        widget.setLayout(layout)
        return widget
        
    def _on_dialog_image_changed(self, current, previous=None):
        if current is None:
            return
        stored = current.data(Qt.ItemDataRole.UserRole)
        real = resolve_image_path(stored)
        if real:
            self.dialog_preview.load(real)
        else:
            self.dialog_preview.show_message("Arquivo não encontrado:\n" + str(stored))

    def apply_styles(self):
        """Aplica a mesma paleta do restante do programa."""
        self.setStyleSheet("""
            QDialog#boardDetailsDialog { background-color: #F4F7F9; color: #0F172A; }
            QFrame#boardDetailsHeader { background-color: #0F172A; border-radius: 10px; }
            QLabel#boardDetailsTitle { color: #FFFFFF; font-size: 18px; font-weight: 700; }
            QLabel#boardDetailsSubtitle { color: #CBD5E1; font-size: 11px; }
            QLabel#boardStatusActive {
                background-color: #134E4A; color: #CCFBF1;
                border: 1px solid #2DD4BF; border-radius: 8px;
                padding: 4px 9px; font-size: 10px; font-weight: 700;
            }
            QLabel#boardStatusInactive {
                background-color: #1E293B; color: #CBD5E1;
                border: 1px solid #475569; border-radius: 8px;
                padding: 4px 9px; font-size: 10px; font-weight: 700;
            }
            QTabWidget#boardDetailsTabs::pane {
                background-color: #FFFFFF; border: 1px solid #E2E8F0;
                border-radius: 9px; top: -1px;
            }
            QTabWidget#boardDetailsTabs QTabBar::tab {
                color: #64748B; padding: 9px 14px; margin-right: 3px;
                border-bottom: 2px solid transparent; font-weight: 600;
            }
            QTabWidget#boardDetailsTabs QTabBar::tab:selected {
                color: #0F766E; border-bottom: 2px solid #0F766E;
            }
            QGroupBox {
                background-color: #FFFFFF; color: #0F172A;
                border: 1px solid #E2E8F0; border-radius: 9px;
                margin-top: 12px; font-weight: 700;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
            QLabel { color: #334155; }
            QTableWidget, QListWidget {
                background-color: #FFFFFF; color: #0F172A;
                border: 1px solid #E2E8F0; border-radius: 8px; outline: 0;
            }
            QTableWidget::item, QListWidget::item { padding: 7px; }
            QTableWidget::item:selected, QListWidget::item:selected {
                background-color: #E0F2FE; color: #0F172A;
            }
            QLineEdit#pointsInlineEditor {
                background-color: #FFFFFF;
                color: #0F172A;
                border: 1px solid #0F766E;
                border-radius: 6px;
                padding: 3px 8px;
                selection-background-color: #CCFBF1;
                selection-color: #0F172A;
            }
            QHeaderView::section {
                background-color: #F8FAFC; color: #475569;
                border: none; border-bottom: 1px solid #E2E8F0;
                padding: 8px; font-size: 11px; font-weight: 700;
            }
            QPushButton#detailsClose {
                background-color: #F1F5F9; color: #334155;
                border: 1px solid #CBD5E1; border-radius: 8px;
                padding: 8px 16px; font-weight: 600; min-width: 90px;
            }
            QPushButton#detailsClose:hover { background-color: #E2E8F0; }
        """)

    def load_board_data(self):
        """Carrega dados da placa"""
        # Já carregado durante a criação da UI
        pass


class PlacaTab(QWidget):
    """Aba completa para gerenciamento de placas"""
    
    board_imported = pyqtSignal(object)  # Emite a placa importada

    EMPTY_TEXT = "📋\n\nSelecione uma placa na lista para ver os detalhes\nou uma máquina para ver o resumo dela"
    
    def __init__(self, session: Session, import_callback, current_user: User = None):
        super().__init__()
        self.session = session
        self.import_callback = import_callback
        self.current_user = current_user
        self.current_board = None
        self.current_machine = None

        self.setup_ui()
        self.apply_styles()
        self.refresh_boards()
        
    def setup_ui(self):
        """Monta a aba: banner de resumo + (coluna esquerda | coluna direita) + status."""
        self.setObjectName("placaRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 12)
        root.setSpacing(16)

        root.addWidget(self.create_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(14)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.create_left_panel())
        splitter.addWidget(self.create_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([490, 560])
        root.addWidget(splitter, 1)

        self.status_label = QLabel("Pronto")
        self.status_label.setObjectName("statusText")
        root.addWidget(self.status_label)

    # ------------------------------------------------------------------
    # CABEÇALHO (banner com resumo)
    # ------------------------------------------------------------------
    def create_header(self):
        """Cabeçalho compacto, no mesmo padrão visual do dashboard."""
        header = QFrame()
        header.setObjectName("placaHeader")
        row = QHBoxLayout(header)
        row.setContentsMargins(20, 16, 20, 16)
        row.setSpacing(14)

        text_box = QVBoxLayout()
        text_box.setSpacing(3)
        title = QLabel("Placas e máquinas")
        title.setObjectName("placaTitle")
        subtitle = QLabel("Organize as placas, imagens e vínculos com as máquinas")
        subtitle.setObjectName("placaSubtitle")
        operator = QLabel(
            f"Operador: {self.current_user.username if self.current_user else 'N/A'}"
        )
        operator.setObjectName("placaOperator")
        text_box.addWidget(title)
        text_box.addWidget(subtitle)
        text_box.addWidget(operator)
        row.addLayout(text_box, 1)

        for caption, attr in (
            ("MÁQUINAS", "stat_machines"),
            ("PLACAS", "stat_boards"),
            ("ATIVAS", "stat_active"),
        ):
            chip = QFrame()
            chip.setObjectName("headerStat")
            chip.setMinimumWidth(88)
            box = QVBoxLayout(chip)
            box.setContentsMargins(12, 7, 12, 7)
            box.setSpacing(0)
            value = QLabel("0")
            value.setObjectName("headerStatValue")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label = QLabel(caption)
            label.setObjectName("headerStatLabel")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(value)
            box.addWidget(label)
            setattr(self, attr, value)
            row.addWidget(chip)
        return header

    def create_left_panel(self):
        """Lista de máquinas/placas e ações relacionadas à seleção atual."""
        container = QWidget()
        container.setObjectName("leftColumn")
        container.setMinimumWidth(420)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(12)

        card = QFrame()
        card.setObjectName("card")
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 16, 16, 16)
        box.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(8)
        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        card_title = QLabel("Máquinas e placas")
        card_title.setObjectName("cardTitle")
        self.machine_count_label = QLabel("Nenhuma máquina cadastrada")
        self.machine_count_label.setObjectName("cardSub")
        title_box.addWidget(card_title)
        title_box.addWidget(self.machine_count_label)
        head.addLayout(title_box, 1)

        self.add_machine_btn = QPushButton("Nova máquina")
        self.add_machine_btn.setObjectName("btnSecondary")
        self.add_machine_btn.setMinimumHeight(36)
        self.add_machine_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_machine_btn.clicked.connect(self.add_machine)
        head.addWidget(self.add_machine_btn)

        self.add_board_btn = QPushButton("Nova placa")
        self.add_board_btn.setObjectName("btnPrimary")
        self.add_board_btn.setMinimumHeight(36)
        self.add_board_btn.setToolTip("Cadastrar uma placa na máquina selecionada")
        self.add_board_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_board_btn.clicked.connect(lambda _checked=False: self.add_board_dialog())
        head.addWidget(self.add_board_btn)
        box.addLayout(head)

        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar máquina ou placa...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.filter_boards)
        self.active_only_cb = QCheckBox("Apenas ativas")
        self.active_only_cb.setObjectName("activeOnly")
        self.active_only_cb.setChecked(True)
        self.active_only_cb.toggled.connect(self.filter_boards)
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.active_only_cb)
        box.addLayout(search_row)

        self.board_tree = QTreeWidget()
        self.board_tree.setObjectName("boardTree")
        self.board_tree.setHeaderHidden(True)
        self.board_tree.setMinimumHeight(280)
        self.board_tree.setAnimated(True)
        self.board_tree.setIndentation(18)
        self.board_tree.setIconSize(QSize(32, 32))
        self.board_tree.setFrameShape(QFrame.Shape.NoFrame)
        self.board_tree.itemSelectionChanged.connect(self.on_board_selected)
        self.board_tree.itemDoubleClicked.connect(self.view_board_details)
        box.addWidget(self.board_tree, 1)

        action_title = QLabel("Ações da seleção")
        action_title.setObjectName("sectionLabel")
        box.addWidget(action_title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        def action_button(text, object_name, handler):
            button = QPushButton(text)
            button.setObjectName(object_name)
            button.setMinimumHeight(36)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(handler)
            button.setEnabled(False)
            return button

        self.details_btn = action_button("Ver detalhes", "btnSecondary", self.view_board_details)
        self.import_btn = action_button("Importar para teste", "btnPrimary", self.import_board)
        self.move_btn = action_button("Mover placa", "btnSecondary", self.move_board)
        self.delete_btn = action_button("Excluir placa", "btnDanger", self.delete_board)
        self.edit_machine_btn = action_button("Editar máquina", "btnSecondary", self.edit_machine)
        self.delete_machine_btn = action_button("Excluir máquina", "btnDanger", self.delete_machine)

        # Ações contextuais: a interface mostra SOMENTE os controles do tipo
        # de item selecionado. Isso evita manter ações de máquina visíveis
        # quando o usuário está trabalhando em uma placa (e vice-versa).
        self.board_action_buttons = [
            self.details_btn, self.import_btn, self.move_btn, self.delete_btn
        ]
        self.machine_action_buttons = [
            self.edit_machine_btn, self.delete_machine_btn
        ]

        grid.addWidget(self.details_btn, 0, 0)
        grid.addWidget(self.import_btn, 0, 1)
        grid.addWidget(self.move_btn, 1, 0)
        grid.addWidget(self.delete_btn, 1, 1)
        grid.addWidget(self.edit_machine_btn, 0, 0)
        grid.addWidget(self.delete_machine_btn, 0, 1)
        box.addLayout(grid)

        # Sem seleção não há ações da seleção para mostrar.
        self.action_title = action_title
        self._update_selection_actions(None)
        layout.addWidget(card, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        scroll.viewport().setAutoFillBackground(False)
        container.setAutoFillBackground(False)
        scroll.setWidget(container)
        return scroll

    def create_right_panel(self):
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        scroll.viewport().setAutoFillBackground(False)

        inner = QWidget()
        inner.setAutoFillBackground(False)
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(0)

        # Estado vazio
        self.details_placeholder = QLabel(self.EMPTY_TEXT)
        self.details_placeholder.setObjectName("emptyState")
        self.details_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.details_placeholder.setWordWrap(True)
        self.details_placeholder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Detalhes (preenchidos dinamicamente)
        self.details_widget = QWidget()
        self.details_widget.setAutoFillBackground(False)
        self.details_layout = QVBoxLayout(self.details_widget)
        self.details_layout.setContentsMargins(0, 0, 0, 0)
        self.details_layout.setSpacing(14)
        self.details_widget.setVisible(False)

        inner_layout.addWidget(self.details_placeholder, 1)
        inner_layout.addWidget(self.details_widget, 1)

        scroll.setWidget(inner)
        card_layout.addWidget(scroll)
        return card

    # ------------------------------------------------------------------
    # ESTILO DA ABA INTEIRA (todos os seletores são por nome: nada vaza para diálogos)
    # ------------------------------------------------------------------
    def apply_styles(self):
        """Visual alinhado ao dashboard, preservando a paleta atual do projeto."""
        self.setStyleSheet("""
            QWidget#placaRoot { background-color: #F4F7F9; }
            QWidget#placaRoot QSplitter::handle { background: transparent; }

            QFrame#placaHeader { background-color: #0F172A; border-radius: 12px; }
            QLabel#placaTitle { color: #FFFFFF; font-size: 19px; font-weight: 700; }
            QLabel#placaSubtitle { color: #CBD5E1; font-size: 11px; }
            QLabel#placaOperator { color: #94A3B8; font-size: 10px; }
            QFrame#headerStat {
                background-color: #1E293B; border: 1px solid #334155; border-radius: 8px;
            }
            QLabel#headerStatValue { color: #FFFFFF; font-size: 19px; font-weight: 700; }
            QLabel#headerStatLabel { color: #94A3B8; font-size: 9px; font-weight: 700; }

            QFrame#card {
                background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px;
            }
            QLabel#cardTitle { color: #0F172A; font-size: 14px; font-weight: 700; }
            QLabel#cardSub { color: #64748B; font-size: 11px; }
            QLabel#sectionLabel { color: #475569; font-size: 10px; font-weight: 700; }

            QFrame#card QLineEdit, QFrame#card QComboBox {
                background-color: #FFFFFF; color: #0F172A;
                border: 1px solid #CBD5E1; border-radius: 8px;
                padding: 8px 10px; font-size: 12px;
                selection-background-color: #0284C7; selection-color: #FFFFFF;
            }
            QFrame#card QLineEdit:focus, QFrame#card QComboBox:focus {
                border: 1px solid #0284C7;
            }
            QCheckBox#activeOnly { color: #334155; font-size: 11px; spacing: 6px; }

            QTreeWidget#boardTree {
                background-color: #FFFFFF; color: #0F172A;
                border: 1px solid #E2E8F0; border-radius: 8px;
                font-size: 12px; outline: 0; padding: 3px;
            }
            QTreeWidget#boardTree::item {
                padding: 7px 5px; border-radius: 6px; margin: 1px 2px;
            }
            QTreeWidget#boardTree::item:selected { background-color: #E0F2FE; color: #0F172A; }
            QTreeWidget#boardTree::item:hover:!selected { background-color: #F8FAFC; }

            QPushButton#btnPrimary {
                background-color: #0F766E; color: #FFFFFF;
                border: 1px solid #0D9488; border-radius: 8px;
                padding: 7px 13px; font-size: 12px; font-weight: 700;
            }
            QPushButton#btnPrimary:hover { background-color: #0D9488; }
            QPushButton#btnSecondary, QPushButton#btnGhost, QPushButton#btnBlue, QPushButton#btnPurple {
                background-color: #F1F5F9; color: #334155;
                border: 1px solid #CBD5E1; border-radius: 8px;
                padding: 7px 13px; font-size: 12px; font-weight: 600;
            }
            QPushButton#btnSecondary:hover, QPushButton#btnGhost:hover,
            QPushButton#btnBlue:hover, QPushButton#btnPurple:hover { background-color: #E2E8F0; }
            QPushButton#btnDanger, QPushButton#btnDangerSoft {
                background-color: #FEF2F2; color: #B91C1C;
                border: 1px solid #FCA5A5; border-radius: 8px;
                padding: 7px 13px; font-size: 12px; font-weight: 700;
            }
            QPushButton#btnDanger:hover, QPushButton#btnDangerSoft:hover { background-color: #FEE2E2; }
            QPushButton:disabled {
                background-color: #F1F5F9; color: #94A3B8; border: 1px solid #E2E8F0;
            }

            QLabel#emptyState {
                color: #64748B; font-size: 13px;
                background-color: #F8FAFC;
                border: 1px dashed #CBD5E1; border-radius: 10px; padding: 28px;
            }
            QLabel#detailTitle { color: #0F172A; font-size: 20px; font-weight: 700; }
            QLabel#statusOn {
                background-color: #F0FDFA; color: #0F766E;
                border: 1px solid #14B8A6; border-radius: 8px;
                padding: 4px 9px; font-size: 10px; font-weight: 700;
            }
            QLabel#statusOff {
                background-color: #F1F5F9; color: #64748B;
                border: 1px solid #CBD5E1; border-radius: 8px;
                padding: 4px 9px; font-size: 10px; font-weight: 700;
            }
            QLabel#machineChip {
                background-color: #E0F2FE; color: #0369A1;
                border-radius: 8px; padding: 4px 9px; font-size: 10px; font-weight: 700;
            }
            QFrame#infoTile {
                background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px;
            }
            QLabel#tileCaption { color: #64748B; font-size: 9px; font-weight: 700; }
            QLabel#tileText { color: #0F172A; font-size: 13px; font-weight: 600; }
            QFrame#statTile {
                background-color: #F0FDFA; border: 1px solid #CCFBF1; border-radius: 8px;
            }
            QLabel#tileValue { color: #0F766E; font-size: 19px; font-weight: 700; }
            QLabel#tileLabel { color: #475569; font-size: 9px; font-weight: 700; }
            QLabel#sectionTitle { color: #0F172A; font-size: 12px; font-weight: 700; }
            QLabel#descText { color: #334155; font-size: 12px; }
            QLabel#statusText { color: #64748B; font-size: 11px; padding: 2px 4px; }
        """)

    def _machine_icon(self, image_path):
        """Miniatura da máquina para a árvore (ou None se não houver imagem)."""
        real = resolve_image_path(image_path) if image_path else None
        if not real:
            return None
        pixmap = QPixmap(real)
        if pixmap.isNull():
            return None
        return QIcon(pixmap.scaled(
            QSize(68, 68),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))

    def show_machine_details(self, machine):
        """Painel da direita quando uma máquina está selecionada."""
        clear_layout(self.details_layout)

        title = QLabel(machine.name)
        title.setObjectName("detailTitle")
        title.setWordWrap(True)

        def chip(text):
            label = QLabel(text)
            label.setObjectName("machineChip")
            label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            return label

        boards = list(machine.boards)
        chips = QHBoxLayout()
        chips.setSpacing(8)
        if machine.code:
            chips.addWidget(chip(f"Código {machine.code}"))
        chips.addWidget(chip(f"{len(boards)} placa(s)"))
        chips.addStretch()

        image_label = ImagePreviewLabel()
        real = resolve_image_path(machine.image_path) if machine.image_path else None
        if not (real and image_label.load(real)):
            image_label.show_message(
                "Nenhuma imagem cadastrada para esta máquina.\nUse 'Editar máquina' para adicionar uma."
            )

        self.details_layout.addWidget(title)
        self.details_layout.addLayout(chips)
        self.details_layout.addWidget(image_label, 1)

        if machine.description:
            desc_title = QLabel("Descrição")
            desc_title.setObjectName("sectionTitle")
            desc = QLabel(machine.description)
            desc.setObjectName("descText")
            desc.setWordWrap(True)
            self.details_layout.addWidget(desc_title)
            self.details_layout.addWidget(desc)

        boards_title = QLabel("Placas desta máquina")
        boards_title.setObjectName("sectionTitle")
        self.details_layout.addWidget(boards_title)
        if boards:
            for board in sorted(boards, key=lambda b: b.name.lower()):
                state = "Ativa" if board.is_active else "Inativa"
                line = QLabel(f"{board.name}  •  SN: {board.serial_number}  •  {state}")
                line.setObjectName("descText")
                self.details_layout.addWidget(line)
        else:
            empty = QLabel("Nenhuma placa cadastrada nesta máquina.")
            empty.setObjectName("descText")
            self.details_layout.addWidget(empty)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        edit_btn = QPushButton("Editar máquina")
        edit_btn.setObjectName("btnSecondary")
        edit_btn.setMinimumHeight(38)
        edit_btn.clicked.connect(self.edit_machine)
        add_btn = QPushButton("Cadastrar placa")
        add_btn.setObjectName("btnPrimary")
        add_btn.setMinimumHeight(38)
        add_btn.clicked.connect(self._start_board_for_machine)
        actions.addWidget(edit_btn)
        actions.addWidget(add_btn, 1)
        self.details_layout.addLayout(actions)

        self.details_placeholder.setVisible(False)
        self.details_widget.setVisible(True)

    def _start_board_for_machine(self):
        """Abre a janela de nova placa já apontando para a máquina selecionada."""
        machine_id = self.current_machine.id if self.current_machine is not None else None
        self.add_board_dialog(machine_id=machine_id)

    def _machine_option_text(self, machine):
        return f"{machine.name} [{machine.code}]" if machine.code else machine.name

    def _machine_label(self, machine, count):
        code = f" [{machine.code}]" if machine.code else ""
        return f"🏭 {machine.name}{code} — {count} placa(s)"

    def _machine_summary(self, machine):
        lines = [f"🏭 {machine.name}"]
        if machine.code:
            lines.append(f"Código: {machine.code}")
        lines.append(f"{len(machine.boards)} placa(s) cadastrada(s)")
        if machine.description:
            lines.append("")
            lines.append(machine.description)
        lines.append("")
        lines.append("Use \"Cadastrar nova placa\" para adicionar placas a esta máquina.")
        return "\n".join(lines)

    def refresh_boards(self, select_board_id=None, select_machine_id=None):
        """Atualiza a árvore (máquina -> placas), o combo de máquinas e as estatísticas."""
        tree = self.board_tree

        # Lembra o que estava aberto e selecionado
        previous_keys = set()
        expanded_keys = set()
        for i in range(tree.topLevelItemCount()):
            top = tree.topLevelItem(i)
            key = top.data(0, NODE_ROLE)
            previous_keys.add(key)
            if top.isExpanded():
                expanded_keys.add(key)

        if select_board_id is None and select_machine_id is None:
            selected = tree.selectedItems()
            if selected:
                data = selected[0].data(0, NODE_ROLE)
                if data and data[0] == "board":
                    select_board_id = data[1]
                elif data and data[0] == "machine":
                    select_machine_id = data[1]

        tree.blockSignals(True)
        tree.clear()

        machines = self.session.query(Machine).order_by(Machine.name).all()
        boards = self.session.query(BoardUnit).order_by(BoardUnit.name).all()

        boards_by_machine = {}
        for board in boards:
            boards_by_machine.setdefault(board.machine_id, []).append(board)

        groups = [(("machine", m.id), self._machine_label(m, len(boards_by_machine.get(m.id, []))),
                   m.description or m.name, boards_by_machine.get(m.id, []), m.image_path) for m in machines]
        orphans = boards_by_machine.get(None, [])
        if orphans:
            groups.append((("orphan", None), f"📦 Sem máquina — {len(orphans)} placa(s)",
                           "Placas que ainda não foram associadas a uma máquina", orphans, None))

        item_to_select = None
        for key, label, tooltip, group_boards, group_image in groups:
            top = QTreeWidgetItem([label])
            top.setData(0, NODE_ROLE, key)
            top.setToolTip(0, tooltip)
            icon = self._machine_icon(group_image)
            if icon is not None:
                top.setIcon(0, icon)
            font = top.font(0)
            font.setBold(True)
            top.setFont(0, font)
            tree.addTopLevelItem(top)

            group_has_target = False  # True só quando uma PLACA deste grupo está selecionada
            if key == ("machine", select_machine_id):
                item_to_select = top

            for board in group_boards:
                status_icon = "✅" if board.is_active else "⏸️"
                child = QTreeWidgetItem(
                    [f"{status_icon} {board.name} — {board.model} v{board.version} — SN:{board.serial_number}"]
                )
                child.setData(0, NODE_ROLE, ("board", board.id))
                if not board.is_active:
                    child.setForeground(0, QBrush(QColor("#94A3B8")))
                top.addChild(child)
                if select_board_id is not None and board.id == select_board_id:
                    item_to_select = child
                    group_has_target = True

            # Os grupos começam FECHADOS. Só ficam abertos os que o usuário já abriu
            # ou o que contém a placa selecionada (para ela não ficar escondida).
            top.setExpanded(key in expanded_keys or group_has_target)

        if item_to_select is not None:
            tree.setCurrentItem(item_to_select)
            item_to_select.setSelected(True)
        tree.blockSignals(False)

        self.filter_boards()
        self.on_board_selected()

        # Estatísticas (banner e cartão)
        active_boards = sum(1 for b in boards if b.is_active)
        self.stat_machines.setText(str(len(machines)))
        self.stat_boards.setText(str(len(boards)))
        self.stat_active.setText(str(active_boards))
        if machines:
            self.machine_count_label.setText(f"{len(machines)} máquina(s)  •  {len(boards)} placa(s)")
        else:
            self.machine_count_label.setText("Nenhuma máquina cadastrada")
        self.show_status(f"Carregadas {len(boards)} placas e {len(machines)} máquinas")

    def filter_boards(self):
        """Filtra a árvore pela busca (nome da máquina ou da placa) e por 'apenas ativas'."""
        search = self.search_input.text().strip().lower()
        active_only = self.active_only_cb.isChecked()

        for i in range(self.board_tree.topLevelItemCount()):
            top = self.board_tree.topLevelItem(i)
            kind = top.data(0, NODE_ROLE)[0]
            group_matches = bool(search) and search in top.text(0).lower()

            visible_children = 0
            for j in range(top.childCount()):
                child = top.child(j)
                board_id = child.data(0, NODE_ROLE)[1]
                board = self.session.get(BoardUnit, board_id)

                matches_search = (not search) or group_matches or search in child.text(0).lower()
                matches_active = (not active_only) or (board is not None and board.is_active)
                show = matches_search and matches_active
                child.setHidden(not show)
                if show:
                    visible_children += 1

            if search:
                top.setHidden(not (group_matches or visible_children > 0))
                if visible_children:
                    top.setExpanded(True)
            else:
                # máquinas sem placas continuam visíveis; o grupo "Sem máquina" some se vazio
                top.setHidden(kind == "orphan" and visible_children == 0)

    def _update_selection_actions(self, kind):
        """Mostra somente as ações pertinentes ao item selecionado.

        ``kind`` pode ser ``"machine"``, ``"board"`` ou ``None``.
        Em vez de deixar controles sem função apenas desabilitados, eles são
        realmente ocultados e deixam de ocupar espaço no layout.
        """
        show_board = kind == "board"
        show_machine = kind == "machine"

        for button in self.board_action_buttons:
            button.setVisible(show_board)
            button.setEnabled(show_board)

        for button in self.machine_action_buttons:
            button.setVisible(show_machine)
            button.setEnabled(show_machine)

        self.action_title.setVisible(show_board or show_machine)

    def on_board_selected(self):
        """Trata a seleção na árvore (máquina ou placa)."""
        selected = self.board_tree.selectedItems()
        data = selected[0].data(0, NODE_ROLE) if selected else None
        kind = data[0] if data else None

        board = None
        machine = None
        if kind == "board":
            board = self.session.get(BoardUnit, data[1])
            machine = board.machine if board else None
        elif kind == "machine":
            machine = self.session.get(Machine, data[1])

        self.current_board = board
        self.current_machine = machine

        has_board = board is not None
        self._update_selection_actions(kind if (has_board or machine is not None) else None)

        try:
            if has_board:
                self.show_board_details()
            elif kind == "machine" and machine is not None:
                self.show_machine_details(machine)
            else:
                self.hide_board_details()
                self.details_placeholder.setText(self.EMPTY_TEXT)
        except Exception as exc:  # um erro de exibição nunca deve fechar o programa
            logger.exception("Erro ao mostrar detalhes")
            self.hide_board_details()
            self.details_placeholder.setText(f"Não foi possível carregar os detalhes.\n\n{exc}")

    def add_machine(self):
        """Cadastra uma nova máquina."""
        dialog = MachineDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, code, description, image = dialog.values()

        if self._machine_name_taken(name):
            QMessageBox.warning(self, "Máquina duplicada", f"Já existe uma máquina chamada '{name}'.")
            return

        try:
            image_path = import_image_to_project(image) if image else None
            machine = Machine(
                name=name, code=code or None, description=description or None, image_path=image_path
            )
            self.session.add(machine)
            self.session.commit()
            log_user_action(self.current_user, "machine_created", {"machine_name": name, "code": code})
            self.refresh_boards(select_machine_id=machine.id)
            self.show_status(f"Máquina '{name}' cadastrada. Agora cadastre as placas dela.", "success")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Erro ao cadastrar máquina: {e}")
            self.show_status(f"Erro ao cadastrar máquina: {e}", "error")

    def edit_machine(self):
        """Edita a máquina selecionada (ou a máquina da placa selecionada)."""
        machine = self.current_machine
        if machine is None:
            return

        dialog = MachineDialog(self, machine)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, code, description, image = dialog.values()

        if self._machine_name_taken(name, ignore_id=machine.id):
            QMessageBox.warning(self, "Máquina duplicada", f"Já existe uma máquina chamada '{name}'.")
            return

        try:
            machine.name = name
            machine.code = code or None
            machine.description = description or None
            if image != machine.image_path:  # trocou ou removeu a imagem
                machine.image_path = import_image_to_project(image) if image else None
            self.session.commit()
            log_user_action(self.current_user, "machine_updated", {"machine_name": name})
            self.refresh_boards()
            self.show_status(f"Máquina '{name}' atualizada", "success")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Erro ao editar máquina: {e}")
            self.show_status(f"Erro ao editar máquina: {e}", "error")

    def delete_machine(self):
        """Exclui a máquina. As placas NÃO são apagadas: passam para 'Sem máquina'."""
        machine = self.current_machine
        if machine is None:
            return

        count = len(machine.boards)
        text = f"Excluir a máquina '{machine.name}'?\n\n"
        if count:
            text += f"• As {count} placa(s) dela NÃO serão apagadas: ficarão em 'Sem máquina'.\n"
        text += "\nEsta ação não pode ser desfeita."

        reply = QMessageBox.question(
            self, "Confirmar Exclusão", text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            name = machine.name
            for board in list(machine.boards):
                board.machine = None
            self.session.delete(machine)
            self.session.commit()
            log_user_action(self.current_user, "machine_deleted", {"machine_name": name, "boards_moved": count})
            self.refresh_boards()
            self.show_status(f"Máquina '{name}' excluída", "success")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Erro ao excluir máquina: {e}")
            QMessageBox.critical(self, "Erro", f"Erro ao excluir máquina:\n{e}")

    def move_board(self):
        """Move a placa selecionada para outra máquina."""
        board = self.current_board
        if board is None:
            return

        machines = self.session.query(Machine).order_by(Machine.name).all()
        if not machines:
            QMessageBox.information(
                self, "Nenhuma máquina",
                "Ainda não há máquinas cadastradas.\nUse o botão '➕ Nova Máquina' primeiro.",
            )
            return

        options = ["— Sem máquina —"] + [self._machine_option_text(m) for m in machines]
        current_index = 0
        for i, m in enumerate(machines, start=1):
            if m.id == board.machine_id:
                current_index = i
                break

        choice, ok = QInputDialog.getItem(
            self, "Mover placa", f"Mover '{board.name}' para qual máquina?",
            options, current_index, False,
        )
        if not ok:
            return

        position = options.index(choice)
        new_machine = None if position == 0 else machines[position - 1]

        try:
            board.machine = new_machine
            self.session.commit()
            log_user_action(self.current_user, "board_moved", {
                "board_name": board.name,
                "machine": new_machine.name if new_machine else None,
            })
            self.refresh_boards(select_board_id=board.id)
            destino = new_machine.name if new_machine else "Sem máquina"
            self.show_status(f"Placa '{board.name}' movida para '{destino}'", "success")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Erro ao mover placa: {e}")
            self.show_status(f"Erro ao mover placa: {e}", "error")

    def _machine_name_taken(self, name, ignore_id=None):
        query = self.session.query(Machine).filter(func.lower(Machine.name) == name.lower())
        if ignore_id is not None:
            query = query.filter(Machine.id != ignore_id)
        return query.first() is not None

    def show_board_details(self):
        """Resumo da placa selecionada, com dados, métricas e imagem."""
        board = self.current_board
        if not board:
            return

        clear_layout(self.details_layout)

        def chip(text, object_name):
            label = QLabel(text)
            label.setObjectName(object_name)
            label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            return label

        def info_tile(caption, value):
            frame = QFrame()
            frame.setObjectName("infoTile")
            box = QVBoxLayout(frame)
            box.setContentsMargins(12, 9, 12, 9)
            box.setSpacing(2)
            cap = QLabel(caption.upper())
            cap.setObjectName("tileCaption")
            val = QLabel(value or "—")
            val.setObjectName("tileText")
            val.setWordWrap(True)
            box.addWidget(cap)
            box.addWidget(val)
            return frame

        def stat_tile(value, caption):
            frame = QFrame()
            frame.setObjectName("statTile")
            box = QVBoxLayout(frame)
            box.setContentsMargins(8, 9, 8, 9)
            box.setSpacing(0)
            num = QLabel(str(value))
            num.setObjectName("tileValue")
            num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cap = QLabel(caption)
            cap.setObjectName("tileLabel")
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.addWidget(num)
            box.addWidget(cap)
            return frame

        title = QLabel(board.name)
        title.setObjectName("detailTitle")
        title.setWordWrap(True)
        self.details_layout.addWidget(title)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        chips.addWidget(chip("ATIVA" if board.is_active else "INATIVA",
                             "statusOn" if board.is_active else "statusOff"))
        machine_name = board.machine.name if board.machine else "Sem máquina"
        chips.addWidget(chip(machine_name, "machineChip"))
        chips.addStretch()
        self.details_layout.addLayout(chips)

        created = board.created_at.strftime("%d/%m/%Y") if board.created_at else "—"
        info_grid = QGridLayout()
        info_grid.setHorizontalSpacing(8)
        info_grid.setVerticalSpacing(8)
        info_grid.addWidget(info_tile("Modelo", board.model), 0, 0)
        info_grid.addWidget(info_tile("Versão", board.version), 0, 1)
        info_grid.addWidget(info_tile("Número de série", board.serial_number), 1, 0)
        info_grid.addWidget(info_tile("Cadastrada em", created), 1, 1)
        self.details_layout.addLayout(info_grid)

        points_count = self.session.query(TestPoint).filter_by(board_id=board.id).count()
        plans_count = self.session.query(TestPlan).filter_by(board_model_id=board.model_id).count()
        runs_count = self.session.query(TestRun).filter_by(board_id=board.id).count()
        images_count = len(board.images)
        stats = QHBoxLayout()
        stats.setSpacing(8)
        stats.addWidget(stat_tile(points_count, "PONTOS"))
        stats.addWidget(stat_tile(plans_count, "PLANOS"))
        stats.addWidget(stat_tile(runs_count, "EXECUÇÕES"))
        stats.addWidget(stat_tile(images_count, "IMAGENS"))
        self.details_layout.addLayout(stats)

        preview_header = QHBoxLayout()
        preview_title = QLabel("Imagem da placa")
        preview_title.setObjectName("sectionTitle")
        self.preview_combo = QComboBox()
        self.preview_combo.setMinimumWidth(170)
        self.preview_combo.currentIndexChanged.connect(self._on_preview_choice)
        preview_header.addWidget(preview_title)
        preview_header.addStretch()
        preview_header.addWidget(self.preview_combo)
        self.details_layout.addLayout(preview_header)

        self.preview_label = ImagePreviewLabel()
        self.details_layout.addWidget(self.preview_label, 1)
        self.locate_btn = QPushButton("Localizar imagem")
        self.locate_btn.setObjectName("btnSecondary")
        self.locate_btn.setMinimumHeight(34)
        self.locate_btn.clicked.connect(self.locate_image)
        self.locate_btn.setVisible(False)
        self.details_layout.addWidget(self.locate_btn)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        open_btn = QPushButton("Detalhes completos")
        open_btn.setObjectName("btnSecondary")
        open_btn.setMinimumHeight(38)
        open_btn.clicked.connect(self.view_board_details)
        image_btn = QPushButton("Adicionar imagem")
        image_btn.setObjectName("btnPrimary")
        image_btn.setMinimumHeight(38)
        image_btn.clicked.connect(self.add_image)
        actions.addWidget(open_btn)
        actions.addWidget(image_btn)
        self.details_layout.addLayout(actions)

        try:
            self._fill_preview()
        except Exception as exc:
            import traceback
            logger.error("Erro na pré-visualização: %s", traceback.format_exc())
            self.preview_label.show_message(f"Erro ao carregar a prévia:\n{exc}")

        self.details_placeholder.setVisible(False)
        self.details_widget.setVisible(True)

    def _fill_preview(self):
        """Carrega a imagem da placa selecionada no painel de detalhes."""
        board = self.current_board
        self.preview_images = list(board.images) if board else []

        # regrava caminhos como absolutos quando o arquivo é achado
        missing = heal_board_images(self.session, board) if board else []

        self.preview_combo.blockSignals(True)
        self.preview_combo.clear()
        for image in self.preview_images:
            self.preview_combo.addItem(os.path.basename(image.path))
        self.preview_combo.blockSignals(False)
        self.preview_combo.setVisible(len(self.preview_images) > 1)

        if not self.preview_images:
            self.locate_btn.setVisible(False)
            self.preview_label.show_message(
                "Nenhuma imagem cadastrada.\nClique em 'Adicionar Imagem'."
            )
            return

        # começa pela primeira imagem que existe
        start = 0
        for i, image in enumerate(self.preview_images):
            if image not in missing:
                start = i
                break
        self.preview_combo.setCurrentIndex(start)
        self._on_preview_choice(start)

    def _on_preview_choice(self, index):
        if index < 0 or index >= len(self.preview_images):
            return
        image = self.preview_images[index]
        real = resolve_image_path(image.path)
        if real:
            self.locate_btn.setVisible(False)
            self.preview_label.load(real)
        else:
            self.locate_btn.setVisible(True)
            self.preview_label.show_message(
                "Arquivo da imagem não encontrado:\n" + str(image.path)
            )

    def locate_image(self):
        """Deixa o usuário apontar onde está o arquivo de uma imagem perdida."""
        index = self.preview_combo.currentIndex()
        if index < 0 or index >= len(self.preview_images):
            index = 0
        image = self.preview_images[index]

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
        self.show_board_details()

    def hide_board_details(self):
        """Esconde detalhes da placa"""
        self.details_placeholder.setVisible(True)
        self.details_widget.setVisible(False)
        
    def _create_board(self, nome, modelo, versao, serial, machine_id, image=None):
        """Grava a placa. Devolve (placa, None) em caso de sucesso ou (None, mensagem de erro)."""
        faltando = [
            rotulo for rotulo, valor in (
                ("nome", nome), ("modelo", modelo), ("versão", versao), ("número de série", serial)
            ) if not valor
        ]
        if faltando:
            return None, "Preencha: " + ", ".join(faltando) + "."

        if self.session.query(BoardUnit).filter_by(serial_number=serial).first():
            return None, f"Já existe uma placa com o número de série {serial}."

        try:
            # Garante que existe um BoardModel
            board_model = self.session.query(BoardModel).filter_by(name=modelo, version=versao).first()
            if not board_model:
                board_model = BoardModel(name=modelo, version=versao)
                self.session.add(board_model)
                self.session.flush()

            new_board = BoardUnit(
                name=nome,
                model=modelo,
                version=versao,
                serial_number=serial,
                machine_id=machine_id,
                board_model=board_model,
                operator=self.current_user
            )
            self.session.add(new_board)

            if image:
                self.session.add(BoardImage(board=new_board, path=import_image_to_project(image)))

            self.session.commit()
        except Exception as exc:
            self.session.rollback()  # sem isso a sessão fica quebrada e as próximas tentativas também falham
            logger.exception("Erro ao cadastrar placa")
            return None, f"Erro ao cadastrar placa: {exc}"

        log_user_action(self.current_user, "board_created", {
            "board_name": nome,
            "model": modelo,
            "version": versao,
            "serial": serial,
            "machine_id": machine_id
        })
        return new_board, None

    def add_board_dialog(self, *_args, machine_id=None):
        """Abre a janela de nova placa (já com a máquina selecionada, se houver)."""
        machines = [
            (m.id, self._machine_option_text(m))
            for m in self.session.query(Machine).order_by(Machine.name).all()
        ]
        if machine_id is None and self.current_machine is not None:
            machine_id = self.current_machine.id

        dialog = BoardDialog(machines, self._create_board, self, machine_id)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.created_board is not None:
            board = dialog.created_board
            self.refresh_boards(select_board_id=board.id)
            self.show_status(f"Placa '{board.name}' cadastrada com sucesso!", "success")

    def add_image(self):
        """Adiciona imagem à placa selecionada"""
        if not self.current_board:
            self.show_status("Selecione uma placa primeiro", "error")
            return

        path, _ = QFileDialog.getOpenFileName(
            self, 
            "Selecionar Imagem da Placa",
            "", 
            "Imagens (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        
        if path:
            try:
                # Pede descrição opcional
                description, ok = QInputDialog.getText(
                    self, 
                    "Descrição da Imagem",
                    "Descrição (opcional):",
                    text=f"Imagem da placa {self.current_board.name}"
                )
                
                saved_path = import_image_to_project(path)
                img = BoardImage(
                    board=self.current_board, 
                    path=saved_path,
                    description=description if ok and description.strip() else None
                )
                self.session.add(img)
                self.session.commit()
                
                self.session.refresh(self.current_board)
                self.show_board_details()
                self.show_status("Imagem adicionada à placa com sucesso", "success")
                log_user_action(self.current_user, "board_image_added", {
                    "board_name": self.current_board.name,
                    "image_path": path
                })
                
            except Exception as e:
                logger.error(f"Erro ao adicionar imagem: {e}")
                self.show_status(f"Erro ao adicionar imagem: {str(e)}", "error")
                
    def delete_board(self):
        """Exclui placa selecionada"""
        if not self.current_board:
            return
            
        # Verifica dependências
        points_count = self.session.query(TestPoint).filter_by(board_id=self.current_board.id).count()
        plans_count = self.session.query(TestPlan).filter_by(board_model_id=self.current_board.model_id).count()
        runs_count = self.session.query(TestRun).filter_by(board_id=self.current_board.id).count()
        
        warning_text = f"Excluir a placa '{self.current_board.name}'?\n\n"
        if points_count > 0:
            warning_text += f"• {points_count} pontos de teste serão removidos\n"
        if plans_count > 0:
            warning_text += f"• {plans_count} planos de teste serão removidos\n"
        if runs_count > 0:
            warning_text += f"• {runs_count} execuções de teste serão removidas\n"
            
        warning_text += "\nEsta ação não pode ser desfeita!"

        reply = QMessageBox.question(
            self, 
            "Confirmar Exclusão",
            warning_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                board_name = self.current_board.name
                self.session.delete(self.current_board)
                self.session.commit()
                
                self.refresh_boards()
                self.show_status(f"Placa '{board_name}' excluída com sucesso", "success")
                log_user_action(self.current_user, "board_deleted", {"board_name": board_name})
                
            except Exception as e:
                logger.error(f"Erro ao excluir placa: {e}")
                QMessageBox.critical(self, "Erro", f"Erro ao excluir placa:\n{str(e)}")
                
    def view_board_details(self):
        """Abre dialog com detalhes completos da placa"""
        if not self.current_board:
            return
            
        dialog = BoardDetailsDialog(self.current_board, self.session)
        dialog.exec()
        
    def import_board(self):
        """Importa placa para teste"""
        if not self.current_board:
            QMessageBox.warning(self, "Erro", "Selecione uma placa para importar.")
            return
            
        if not self.current_board.is_active:
            reply = QMessageBox.question(
                self, "Placa Inativa",
                f"A placa '{self.current_board.name}' está inativa. Deseja importá-la mesmo assim?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
                
        self.import_callback(self.current_board)
        self.show_status(f"Placa '{self.current_board.name}' importada para teste", "success")
        log_user_action(self.current_user, "board_imported", {"board_name": self.current_board.name})
        
    def show_status(self, message, type="info"):
        """Exibe mensagem de status"""
        colors = {
            "info": "#3498DB",
            "success": "#27AE60",
            "warning": "#F39C12",
            "error": "#E74C3C"
        }
        
        icon = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}
        
        self.status_label.setText(f"{icon[type]} {message}")
        self.status_label.setStyleSheet(
            f"color: {colors[type]}; font-size: 12px; font-weight: 600; padding: 2px 6px; background: transparent;"
        )
        
        # Limpa mensagem após 3 segundos para sucesso/erro
        if type in ["success", "error"]:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(3000, lambda: self.status_label.setText("Pronto"))