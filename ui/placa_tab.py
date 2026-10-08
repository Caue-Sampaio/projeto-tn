# ui/placa_tab.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QMessageBox, QFileDialog, QFormLayout,
    QGroupBox, QTabWidget, QTextEdit, QComboBox, QDialog, QDialogButtonBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QFrame,
    QProgressBar, QInputDialog, QListWidgetItem, QCheckBox, QSizePolicy, QGridLayout,
    QTreeWidget, QTreeWidgetItem, QScrollArea, QStyledItemDelegate, QSpinBox,
    QStackedWidget, QMenu, QToolButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QUrl, QTimer
from PyQt6.QtGui import QFont, QPixmap, QBrush, QColor, QIcon, QDesktopServices
from sqlalchemy import func
from sqlalchemy.orm import Session
from db.models import (BoardUnit, BoardModel, User, BoardImage, TestPoint, TestPlan, TestRun, Machine,
                       MachineDocument, MachineFault)
from engine.logger import log_user_action
from utils.image_paths import import_image_to_project, resolve_image_path, heal_board_images
import logging
import os
import shutil
from pathlib import Path
from datetime import datetime, time

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


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _machine_file_path(stored_path):
    """Resolve um arquivo do dossiê, aceitando caminhos antigos/absolutos."""
    if not stored_path:
        return None
    candidate = Path(str(stored_path))
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate if candidate.exists() else None


def _copy_machine_document(source_path: str, machine_id: int) -> str:
    """Copia o documento para dentro do projeto e devolve caminho relativo."""
    source = Path(source_path)
    target_dir = PROJECT_ROOT / "documents" / "machines" / str(machine_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_name = source.name.replace(" ", "_")
    target = target_dir / f"{stamp}_{safe_name}"
    shutil.copy2(source, target)
    return str(target.relative_to(PROJECT_ROOT))


class MachineDocumentDialog(QDialog):
    """Cadastro profissional de datasheet/documento da máquina."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adicionar documento técnico")
        self.setModal(True)
        self.setMinimumWidth(620)
        self._selected_file = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        title = QLabel("Documento técnico")
        title.setObjectName("docDlgTitle")
        subtitle = QLabel("Anexe datasheet, manual, diagrama, procedimento ou outro arquivo útil do equipamento.")
        subtitle.setObjectName("docDlgSub")
        subtitle.setWordWrap(True)
        root.addWidget(title); root.addWidget(subtitle)

        form = QFormLayout()
        form.setHorizontalSpacing(14); form.setVerticalSpacing(10)
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Ex.: Manual elétrico, Datasheet do drive, Diagrama hidráulico")
        file_row = QHBoxLayout(); file_row.setSpacing(8)
        self.file_input = QLineEdit(); self.file_input.setReadOnly(True)
        self.file_input.setPlaceholderText("Nenhum arquivo selecionado")
        browse = QPushButton("Selecionar arquivo")
        browse.setObjectName("dlgSecondary")
        browse.clicked.connect(self._browse)
        file_row.addWidget(self.file_input, 1); file_row.addWidget(browse)
        file_wrap = QWidget(); file_wrap.setLayout(file_row)
        self.notes = QTextEdit(); self.notes.setMinimumHeight(90)
        self.notes.setPlaceholderText("Observações opcionais: revisão, equipamento relacionado, páginas importantes...")
        form.addRow("Título *", self.title_input)
        form.addRow("Arquivo *", file_wrap)
        form.addRow("Observações", self.notes)
        root.addLayout(form)

        actions = QHBoxLayout(); actions.addStretch()
        cancel = QPushButton("Cancelar"); cancel.setObjectName("dlgSecondary")
        save = QPushButton("Adicionar ao dossiê"); save.setObjectName("dlgPrimary")
        cancel.clicked.connect(self.reject); save.clicked.connect(self._validate)
        actions.addWidget(cancel); actions.addWidget(save); root.addLayout(actions)

        self.setStyleSheet("""
            QDialog { background:#FFFFFF; color:#0F172A; }
            QLabel#docDlgTitle { font:700 20px 'Segoe UI'; color:#0F172A; }
            QLabel#docDlgSub { font:11px 'Segoe UI'; color:#64748B; }
            QLineEdit, QTextEdit { background:#FFFFFF; color:#0F172A; border:1px solid #CBD5E1;
                border-radius:8px; padding:8px 10px; font-size:12px; }
            QLineEdit:focus, QTextEdit:focus { border-color:#0F766E; }
            QPushButton#dlgPrimary { background:#0F766E; color:white; border:none; border-radius:8px;
                min-height:38px; padding:0 16px; font-weight:700; }
            QPushButton#dlgSecondary { background:#F8FAFC; color:#334155; border:1px solid #CBD5E1;
                border-radius:8px; min-height:36px; padding:0 14px; font-weight:600; }
        """)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar documento técnico", "",
            "Documentos técnicos (*.pdf *.doc *.docx *.xls *.xlsx *.txt *.csv *.png *.jpg *.jpeg *.zip);;Todos os arquivos (*.*)"
        )
        if path:
            self._selected_file = path
            self.file_input.setText(path)
            if not self.title_input.text().strip():
                self.title_input.setText(Path(path).stem.replace("_", " "))

    def _validate(self):
        if not self.title_input.text().strip():
            QMessageBox.warning(self, "Documento", "Informe um título para o documento.")
            return
        if not self._selected_file:
            QMessageBox.warning(self, "Documento", "Selecione o arquivo que será anexado.")
            return
        self.accept()

    def values(self):
        return self.title_input.text().strip(), self._selected_file, self.notes.toPlainText().strip()


class MachineFaultDialog(QDialog):
    """Cadastro/edição de defeito recorrente e solução conhecida."""

    def __init__(self, parent=None, fault=None):
        super().__init__(parent)
        self.setWindowTitle("Editar defeito recorrente" if fault else "Novo defeito recorrente")
        self.setModal(True)
        self.setMinimumSize(680, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)
        title = QLabel("Base de defeitos recorrentes")
        title.setObjectName("faultDlgTitle")
        subtitle = QLabel("Registre sintomas conhecidos e o procedimento que resolveu o problema. Isso vira conhecimento técnico reutilizável.")
        subtitle.setObjectName("faultDlgSub"); subtitle.setWordWrap(True)
        root.addWidget(title); root.addWidget(subtitle)

        form = QFormLayout(); form.setHorizontalSpacing(14); form.setVerticalSpacing(10)
        self.title_input = QLineEdit(fault.title if fault else "")
        self.title_input.setPlaceholderText("Ex.: Não inicializa, falha E11, motor não parte")
        self.symptom = QTextEdit(); self.symptom.setMinimumHeight(90)
        self.symptom.setPlaceholderText("Descreva como o defeito se apresenta, alarmes e comportamento observado.")
        self.cause = QTextEdit(); self.cause.setMinimumHeight(85)
        self.cause.setPlaceholderText("Causa provável ou causa confirmada.")
        self.solution = QTextEdit(); self.solution.setMinimumHeight(125)
        self.solution.setPlaceholderText("Passo a passo recomendado para diagnosticar e corrigir.")
        self.notes = QTextEdit(); self.notes.setMinimumHeight(70)
        self.notes.setPlaceholderText("Cuidados, peças usadas, medições de confirmação, observações adicionais.")
        self.occurrences = QSpinBox(); self.occurrences.setRange(1, 9999); self.occurrences.setValue(int(fault.occurrences or 1) if fault else 1)
        if fault:
            self.symptom.setPlainText(fault.symptom or "")
            self.cause.setPlainText(fault.probable_cause or "")
            self.solution.setPlainText(fault.solution or "")
            self.notes.setPlainText(fault.notes or "")
        form.addRow("Defeito / título *", self.title_input)
        form.addRow("Sintoma *", self.symptom)
        form.addRow("Causa provável", self.cause)
        form.addRow("Como corrigir *", self.solution)
        form.addRow("Ocorrências", self.occurrences)
        form.addRow("Observações", self.notes)
        root.addLayout(form)

        actions = QHBoxLayout(); actions.addStretch()
        cancel = QPushButton("Cancelar"); cancel.setObjectName("dlgSecondary")
        save = QPushButton("Salvar conhecimento técnico"); save.setObjectName("dlgPrimary")
        cancel.clicked.connect(self.reject); save.clicked.connect(self._validate)
        actions.addWidget(cancel); actions.addWidget(save); root.addLayout(actions)

        self.setStyleSheet("""
            QDialog { background:#FFFFFF; color:#0F172A; }
            QLabel#faultDlgTitle { font:700 20px 'Segoe UI'; color:#0F172A; }
            QLabel#faultDlgSub { font:11px 'Segoe UI'; color:#64748B; }
            QLineEdit, QTextEdit, QSpinBox { background:#FFFFFF; color:#0F172A; border:1px solid #CBD5E1;
                border-radius:8px; padding:7px 10px; font-size:12px; }
            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus { border-color:#0F766E; }
            QPushButton#dlgPrimary { background:#0F766E; color:white; border:none; border-radius:8px;
                min-height:38px; padding:0 16px; font-weight:700; }
            QPushButton#dlgSecondary { background:#F8FAFC; color:#334155; border:1px solid #CBD5E1;
                border-radius:8px; min-height:36px; padding:0 14px; font-weight:600; }
        """)

    def _validate(self):
        if not self.title_input.text().strip() or not self.symptom.toPlainText().strip() or not self.solution.toPlainText().strip():
            QMessageBox.warning(self, "Defeito recorrente", "Preencha o título, o sintoma e como corrigir.")
            return
        self.accept()

    def values(self):
        return {
            "title": self.title_input.text().strip(),
            "symptom": self.symptom.toPlainText().strip(),
            "probable_cause": self.cause.toPlainText().strip() or None,
            "solution": self.solution.toPlainText().strip(),
            "occurrences": int(self.occurrences.value()),
            "notes": self.notes.toPlainText().strip() or None,
        }


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
    """Cadastro profissional de placa com imagem opcional."""

    def __init__(self, machines, submit, parent=None, machine_id=None):
        super().__init__(parent)
        self._submit = submit
        self._image_path = None
        self.created_board = None

        self.setWindowTitle("Cadastrar Placa")
        self.setModal(True)
        self.resize(820, 620)
        self.setMinimumSize(760, 580)
        self._build_ui(machines, machine_id)
        self._apply_style()
        self.name_input.setFocus()

    def _field_label(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("boardDlgFieldLabel")
        return lbl

    def _line(self, placeholder=""):
        edit = QLineEdit()
        edit.setObjectName("boardDlgInput")
        edit.setPlaceholderText(placeholder)
        edit.setMinimumHeight(42)
        return edit

    def _card(self, title, subtitle=""):
        frame = QFrame(); frame.setObjectName("boardDlgCard")
        lay = QVBoxLayout(frame); lay.setContentsMargins(18, 16, 18, 16); lay.setSpacing(11)
        ttl = QLabel(title); ttl.setObjectName("boardDlgSectionTitle"); lay.addWidget(ttl)
        if subtitle:
            sub = QLabel(subtitle); sub.setObjectName("boardDlgSectionSub"); sub.setWordWrap(True); lay.addWidget(sub)
        return frame, lay

    def _build_ui(self, machines, machine_id):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        header = QFrame(); header.setObjectName("boardDlgHeader")
        hl = QHBoxLayout(header); hl.setContentsMargins(24, 18, 24, 18); hl.setSpacing(14)
        title_box = QVBoxLayout(); title_box.setSpacing(3)
        title = QLabel("Cadastrar placa"); title.setObjectName("boardDlgTitle")
        subtitle = QLabel("Registre os dados de identificação da placa e vincule-a a um equipamento, se necessário.")
        subtitle.setObjectName("boardDlgSubtitle"); subtitle.setWordWrap(True)
        title_box.addWidget(title); title_box.addWidget(subtitle); hl.addLayout(title_box, 1)
        chip = QLabel("NOVO CADASTRO"); chip.setObjectName("boardDlgChip"); hl.addWidget(chip, 0, Qt.AlignmentFlag.AlignTop)
        root.addWidget(header)

        scroll = QScrollArea(); scroll.setObjectName("boardDlgScroll"); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(); body.setObjectName("boardDlgBody")
        body_l = QVBoxLayout(body); body_l.setContentsMargins(20, 18, 20, 18); body_l.setSpacing(14)

        top = QHBoxLayout(); top.setSpacing(14)

        id_card, id_l = self._card("Identificação da placa", "Dados principais usados para localizar e identificar a placa no sistema.")
        self.machine_combo = QComboBox(); self.machine_combo.setObjectName("boardDlgCombo"); self.machine_combo.setMinimumHeight(42)
        self.machine_combo.addItem("— Sem equipamento —", None)
        for mid, text in machines:
            self.machine_combo.addItem(text, mid)
        if machine_id is not None:
            idx = self.machine_combo.findData(machine_id)
            if idx >= 0: self.machine_combo.setCurrentIndex(idx)

        self.name_input = self._line("Ex.: Placa de controle principal")
        self.model_input = self._line("Ex.: PCB-X1")
        self.version_input = self._line("Ex.: RevA, 1.0")
        self.serial_input = self._line("Ex.: SN001, 2024001")

        id_l.addWidget(self._field_label("EQUIPAMENTO")); id_l.addWidget(self.machine_combo)
        id_l.addWidget(self._field_label("NOME DA PLACA *")); id_l.addWidget(self.name_input)

        model_row = QHBoxLayout(); model_row.setSpacing(12)
        model_col = QVBoxLayout(); model_col.setSpacing(6); model_col.addWidget(self._field_label("MODELO *")); model_col.addWidget(self.model_input)
        version_col = QVBoxLayout(); version_col.setSpacing(6); version_col.addWidget(self._field_label("VERSÃO *")); version_col.addWidget(self.version_input)
        model_row.addLayout(model_col, 2); model_row.addLayout(version_col, 1)
        id_l.addLayout(model_row)

        id_l.addWidget(self._field_label("NÚMERO DE SÉRIE *")); id_l.addWidget(self.serial_input)
        self.error_label = QLabel(""); self.error_label.setObjectName("boardDlgError"); self.error_label.setWordWrap(True); id_l.addWidget(self.error_label)
        top.addWidget(id_card, 3)

        image_card, image_l = self._card("Imagem da placa", "Use uma foto nítida da PCB para facilitar identificação e mapeamento.")
        self.image_preview = QLabel("Sem imagem")
        self.image_preview.setObjectName("boardDlgImage")
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setMinimumSize(260, 190)
        self.image_preview.setMaximumHeight(230)
        image_l.addWidget(self.image_preview, 1)

        image_actions = QHBoxLayout(); image_actions.setSpacing(8)
        pick_btn = QPushButton("Escolher imagem"); pick_btn.setObjectName("boardDlgSecondary"); pick_btn.clicked.connect(self._pick_image)
        remove_btn = QPushButton("Remover"); remove_btn.setObjectName("boardDlgGhost"); remove_btn.clicked.connect(self._remove_image)
        image_actions.addWidget(pick_btn, 1); image_actions.addWidget(remove_btn)
        image_l.addLayout(image_actions)
        top.addWidget(image_card, 2)
        body_l.addLayout(top)

        hint_card, hint_l = self._card("Próximos passos", "Após cadastrar a placa, você poderá abrir os detalhes para inserir pontos de teste, referências e imagens adicionais.")
        hint = QLabel("A placa poderá ser movida entre equipamentos posteriormente sem perder seus pontos ou histórico.")
        hint.setObjectName("boardDlgHint"); hint.setWordWrap(True); hint_l.addWidget(hint)
        body_l.addWidget(hint_card)
        body_l.addStretch(1)
        scroll.setWidget(body); root.addWidget(scroll, 1)

        footer = QFrame(); footer.setObjectName("boardDlgFooter")
        fl = QHBoxLayout(footer); fl.setContentsMargins(20, 12, 20, 12); fl.setSpacing(10)
        note = QLabel("* Campos obrigatórios"); note.setObjectName("boardDlgFooterHint")
        cancel = QPushButton("Cancelar"); cancel.setObjectName("boardDlgSecondary"); cancel.setMinimumHeight(40); cancel.clicked.connect(self.reject)
        save = QPushButton("Cadastrar placa"); save.setObjectName("boardDlgPrimary"); save.setMinimumHeight(40); save.setMinimumWidth(160); save.setDefault(True); save.clicked.connect(self._save)
        fl.addWidget(note); fl.addStretch(1); fl.addWidget(cancel); fl.addWidget(save)
        root.addWidget(footer)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background:#F4F7FA; color:#0F172A; font-family:"Segoe UI", "Inter", Arial, sans-serif; }
            QFrame#boardDlgHeader { background:#0B1220; border-bottom:1px solid #1E293B; }
            QLabel#boardDlgTitle { color:#FFFFFF; font-size:20px; font-weight:800; }
            QLabel#boardDlgSubtitle { color:#94A3B8; font-size:11px; }
            QLabel#boardDlgChip { color:#67E8F9; background:#0B2533; border:1px solid #155E75; border-radius:11px; padding:6px 10px; font-size:9px; font-weight:800; }
            QWidget#boardDlgBody, QScrollArea#boardDlgScroll, QScrollArea#boardDlgScroll > QWidget > QWidget { background:#F4F7FA; border:none; }
            QFrame#boardDlgCard { background:#FFFFFF; border:1px solid #DCE3EA; border-radius:11px; }
            QLabel#boardDlgSectionTitle { color:#0F172A; font-size:13px; font-weight:800; }
            QLabel#boardDlgSectionSub { color:#64748B; font-size:10px; }
            QLabel#boardDlgFieldLabel { color:#475569; font-size:9px; font-weight:800; letter-spacing:.5px; }
            QLabel#boardDlgError { color:#DC2626; font-size:11px; font-weight:700; }
            QLabel#boardDlgHint { color:#475569; font-size:11px; }
            QLabel#boardDlgImage { background:#F8FAFC; color:#94A3B8; border:1px dashed #CBD5E1; border-radius:9px; font-size:11px; }
            QLineEdit#boardDlgInput, QComboBox#boardDlgCombo { background:#F8FAFC; color:#0F172A; border:1px solid #CBD5E1; border-radius:8px; padding:9px 11px; font-size:12px; selection-background-color:#0F766E; selection-color:#FFFFFF; }
            QLineEdit#boardDlgInput:focus, QComboBox#boardDlgCombo:focus { background:#FFFFFF; border:1px solid #0F766E; }
            QComboBox#boardDlgCombo QAbstractItemView { background:#FFFFFF; color:#0F172A; border:1px solid #CBD5E1; selection-background-color:#CCFBF1; selection-color:#0F766E; }
            QFrame#boardDlgFooter { background:#FFFFFF; border-top:1px solid #E2E8F0; }
            QLabel#boardDlgFooterHint { color:#94A3B8; font-size:9px; }
            QPushButton#boardDlgPrimary { background:#0F766E; color:#FFFFFF; border:none; border-radius:8px; padding:9px 18px; font-size:12px; font-weight:800; }
            QPushButton#boardDlgPrimary:hover { background:#0D9488; }
            QPushButton#boardDlgSecondary, QPushButton#boardDlgGhost { background:#FFFFFF; color:#334155; border:1px solid #CBD5E1; border-radius:8px; padding:8px 12px; font-size:10px; font-weight:700; }
            QPushButton#boardDlgSecondary:hover, QPushButton#boardDlgGhost:hover { background:#F1F5F9; border-color:#94A3B8; }
        """)

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Escolher imagem da placa", "", "Imagens (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
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
            self.image_preview.clear(); self.image_preview.setText("Sem imagem"); return
        self.image_preview.setText("")
        self.image_preview.setPixmap(pixmap.scaled(QSize(250, 205), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

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
            self.error_label.setText(error)
            return
        self.created_board = board
        self.accept()


class MachineDialog(QDialog):
    """Cadastro/edição de equipamento com dossiê técnico inicial."""

    def __init__(self, parent=None, machine=None):
        super().__init__(parent)
        self._editing = machine is not None
        self._machine = machine
        self._session = getattr(parent, "session", None)
        self._image_path = machine.image_path if (machine and machine.image_path) else None
        self._documents = []
        self._faults = []
        self._load_dossier_buffers()

        self.setWindowTitle("Editar Equipamento" if self._editing else "Cadastrar Equipamento")
        self.setModal(True)
        self.resize(900, 760)
        self.setMinimumSize(800, 680)
        self._build_ui(machine)
        self._apply_style()
        self._refresh_image_preview()
        self._refresh_dossier_lists()
        self.name_input.setFocus()

    def _load_dossier_buffers(self):
        if not self._machine or self._session is None:
            return
        docs = self._session.query(MachineDocument).filter(MachineDocument.machine_id == self._machine.id).order_by(MachineDocument.id.asc()).all()
        self._documents = [
            {
                "id": d.id,
                "title": d.title,
                "file_path": d.file_path,
                "original_name": getattr(d, "original_name", None),
                "notes": getattr(d, "notes", None),
                "source_path": None,
            }
            for d in docs
        ]
        faults = self._session.query(MachineFault).filter(MachineFault.machine_id == self._machine.id).order_by(MachineFault.id.asc()).all()
        self._faults = [
            {
                "id": f.id,
                "title": f.title,
                "symptom": f.symptom,
                "probable_cause": f.probable_cause,
                "solution": f.solution,
                "occurrences": int(f.occurrences or 1),
                "notes": f.notes,
            }
            for f in faults
        ]

    def _field_label(self, text):
        label = QLabel(text)
        label.setObjectName("equipmentDlgFieldLabel")
        return label

    def _card(self, title_text, sub_text=""):
        frame = QFrame(); frame.setObjectName("equipmentDlgCard")
        lay = QVBoxLayout(frame); lay.setContentsMargins(18, 16, 18, 16); lay.setSpacing(12)
        t = QLabel(title_text); t.setObjectName("equipmentDlgSectionTitle"); lay.addWidget(t)
        if sub_text:
            s = QLabel(sub_text); s.setObjectName("equipmentDlgSectionSub"); s.setWordWrap(True); lay.addWidget(s)
        return frame, lay

    def _build_ui(self, machine):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        header = QFrame(); header.setObjectName("equipmentDlgHeader")
        hl = QHBoxLayout(header); hl.setContentsMargins(24, 18, 24, 18); hl.setSpacing(14)
        title_box = QVBoxLayout(); title_box.setSpacing(3)
        title = QLabel("Editar equipamento" if self._editing else "Cadastrar equipamento")
        title.setObjectName("equipmentDlgTitle")
        subtitle = QLabel(
            "Atualize os dados do equipamento e mantenha seu dossiê técnico organizado." if self._editing
            else "Cadastre o equipamento e, se desejar, já inclua datasheets e defeitos conhecidos."
        )
        subtitle.setObjectName("equipmentDlgSubtitle"); subtitle.setWordWrap(True)
        title_box.addWidget(title); title_box.addWidget(subtitle); hl.addLayout(title_box, 1)
        chip = QLabel("EDIÇÃO" if self._editing else "NOVO CADASTRO"); chip.setObjectName("equipmentDlgChip")
        hl.addWidget(chip, 0, Qt.AlignmentFlag.AlignTop); root.addWidget(header)

        scroll = QScrollArea(); scroll.setObjectName("equipmentDlgScroll"); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(); body.setObjectName("equipmentDlgBody")
        body_layout = QVBoxLayout(body); body_layout.setContentsMargins(20, 18, 20, 18); body_layout.setSpacing(14)

        top = QHBoxLayout(); top.setSpacing(14)
        id_card, id_l = self._card("Identificação", "Dados principais usados para localizar o equipamento no sistema.")
        self.name_input = QLineEdit(machine.name if machine else ""); self.name_input.setObjectName("equipmentDlgInput")
        self.name_input.setPlaceholderText("Ex.: Inversor Linha 2, Fresadora CNC 01..."); self.name_input.setMinimumHeight(42)
        self.code_input = QLineEdit((machine.code or "") if machine else ""); self.code_input.setObjectName("equipmentDlgInput")
        self.code_input.setPlaceholderText("Ex.: EQP-001"); self.code_input.setMinimumHeight(42)
        id_l.addWidget(self._field_label("NOME DO EQUIPAMENTO *")); id_l.addWidget(self.name_input)
        id_l.addWidget(self._field_label("CÓDIGO / IDENTIFICAÇÃO (OPCIONAL)")); id_l.addWidget(self.code_input)
        self.error_label = QLabel(""); self.error_label.setObjectName("equipmentDlgError"); self.error_label.setWordWrap(True); id_l.addWidget(self.error_label)
        id_l.addStretch(1); top.addWidget(id_card, 3)

        image_card, image_l = self._card("Imagem do equipamento", "Foto ou ilustração para identificação visual.")
        self.image_preview = QLabel("Sem imagem"); self.image_preview.setObjectName("equipmentDlgImage")
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter); self.image_preview.setMinimumSize(240, 150); self.image_preview.setMaximumHeight(180)
        image_actions = QHBoxLayout(); image_actions.setSpacing(8)
        pick_btn = QPushButton("Escolher imagem"); pick_btn.setObjectName("equipmentDlgSecondary"); pick_btn.clicked.connect(self._pick_image)
        remove_btn = QPushButton("Remover"); remove_btn.setObjectName("equipmentDlgGhost"); remove_btn.clicked.connect(self._remove_image)
        image_actions.addWidget(pick_btn, 1); image_actions.addWidget(remove_btn); image_l.addWidget(self.image_preview, 1); image_l.addLayout(image_actions)
        top.addWidget(image_card, 2); body_layout.addLayout(top)

        desc_card, desc_l = self._card("Descrição técnica", "Informações úteis para identificar ou contextualizar o equipamento.")
        self.desc_input = QTextEdit(); self.desc_input.setObjectName("equipmentDlgNotes"); self.desc_input.setMinimumHeight(105)
        self.desc_input.setPlaceholderText("Ex.: equipamento da linha de envase, painel 02, responsável pelo acionamento principal...")
        if machine and machine.description: self.desc_input.setPlainText(machine.description)
        desc_l.addWidget(self.desc_input); body_layout.addWidget(desc_card)

        dossier_card, dossier_l = self._card(
            "Dossiê técnico inicial",
            "Você pode anexar documentos e registrar defeitos conhecidos agora. Também será possível alterar isso depois no painel do equipamento."
        )
        dossier_cols = QHBoxLayout(); dossier_cols.setSpacing(14)

        doc_box = QFrame(); doc_box.setObjectName("equipmentDlgDossierBox")
        dl = QVBoxLayout(doc_box); dl.setContentsMargins(14, 12, 14, 12); dl.setSpacing(9)
        dt = QLabel("DOCUMENTOS / DATASHEETS"); dt.setObjectName("equipmentDlgMiniTitle"); dl.addWidget(dt)
        ds = QLabel("Manuais, datasheets, diagramas, procedimentos e outros arquivos técnicos."); ds.setWordWrap(True); ds.setObjectName("equipmentDlgMiniSub"); dl.addWidget(ds)
        self.docs_list = QListWidget(); self.docs_list.setObjectName("equipmentDlgList"); self.docs_list.setMinimumHeight(145); dl.addWidget(self.docs_list, 1)
        da = QHBoxLayout(); da.setSpacing(7)
        add_doc = QPushButton("+ Adicionar arquivo"); add_doc.setObjectName("equipmentDlgMiniPrimary"); add_doc.clicked.connect(self._add_document_buffer)
        rem_doc = QPushButton("Remover"); rem_doc.setObjectName("equipmentDlgMiniGhost"); rem_doc.clicked.connect(self._remove_document_buffer)
        da.addWidget(add_doc, 1); da.addWidget(rem_doc); dl.addLayout(da); dossier_cols.addWidget(doc_box, 1)

        fault_box = QFrame(); fault_box.setObjectName("equipmentDlgDossierBox")
        flt = QVBoxLayout(fault_box); flt.setContentsMargins(14, 12, 14, 12); flt.setSpacing(9)
        ft = QLabel("DEFEITOS CONHECIDOS"); ft.setObjectName("equipmentDlgMiniTitle"); flt.addWidget(ft)
        fs = QLabel("Sintomas, causas prováveis e procedimentos de correção já conhecidos."); fs.setWordWrap(True); fs.setObjectName("equipmentDlgMiniSub"); flt.addWidget(fs)
        self.faults_list = QListWidget(); self.faults_list.setObjectName("equipmentDlgList"); self.faults_list.setMinimumHeight(145)
        self.faults_list.itemDoubleClicked.connect(lambda _item: self._edit_fault_buffer()); flt.addWidget(self.faults_list, 1)
        fa = QHBoxLayout(); fa.setSpacing(7)
        add_fault = QPushButton("+ Adicionar defeito"); add_fault.setObjectName("equipmentDlgMiniPrimary"); add_fault.clicked.connect(self._add_fault_buffer)
        edit_fault = QPushButton("Editar"); edit_fault.setObjectName("equipmentDlgMiniGhost"); edit_fault.clicked.connect(self._edit_fault_buffer)
        rem_fault = QPushButton("Remover"); rem_fault.setObjectName("equipmentDlgMiniGhost"); rem_fault.clicked.connect(self._remove_fault_buffer)
        fa.addWidget(add_fault, 1); fa.addWidget(edit_fault); fa.addWidget(rem_fault); flt.addLayout(fa); dossier_cols.addWidget(fault_box, 1)

        dossier_l.addLayout(dossier_cols); body_layout.addWidget(dossier_card); body_layout.addStretch(1)
        scroll.setWidget(body); root.addWidget(scroll, 1)

        footer = QFrame(); footer.setObjectName("equipmentDlgFooter")
        footer_l = QHBoxLayout(footer); footer_l.setContentsMargins(20, 12, 20, 12); footer_l.setSpacing(10)
        hint = QLabel("* Campo obrigatório • documentos e defeitos são salvos junto com o equipamento"); hint.setObjectName("equipmentDlgFooterHint")
        cancel = QPushButton("Cancelar"); cancel.setObjectName("equipmentDlgSecondary"); cancel.setMinimumHeight(40); cancel.clicked.connect(self.reject)
        save = QPushButton("Salvar alterações" if self._editing else "Cadastrar equipamento"); save.setObjectName("equipmentDlgPrimary")
        save.setMinimumHeight(40); save.setMinimumWidth(180); save.setDefault(True); save.clicked.connect(self._validate)
        footer_l.addWidget(hint); footer_l.addStretch(1); footer_l.addWidget(cancel); footer_l.addWidget(save); root.addWidget(footer)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background:#F4F7FA; color:#0F172A; font-family:"Segoe UI", "Inter", Arial, sans-serif; }
            QFrame#equipmentDlgHeader { background:#0B1220; border-bottom:1px solid #1E293B; }
            QLabel#equipmentDlgTitle { color:#FFFFFF; font-size:20px; font-weight:800; }
            QLabel#equipmentDlgSubtitle { color:#94A3B8; font-size:11px; }
            QLabel#equipmentDlgChip { color:#67E8F9; background:#0B2533; border:1px solid #155E75; border-radius:11px; padding:6px 10px; font-size:9px; font-weight:800; }
            QWidget#equipmentDlgBody, QScrollArea#equipmentDlgScroll, QScrollArea#equipmentDlgScroll > QWidget > QWidget { background:#F4F7FA; border:none; }
            QFrame#equipmentDlgCard { background:#FFFFFF; border:1px solid #DCE3EA; border-radius:11px; }
            QLabel#equipmentDlgSectionTitle { color:#0F172A; font-size:13px; font-weight:800; }
            QLabel#equipmentDlgSectionSub { color:#64748B; font-size:10px; }
            QLabel#equipmentDlgFieldLabel { color:#475569; font-size:9px; font-weight:800; letter-spacing:.5px; }
            QLabel#equipmentDlgError { color:#DC2626; font-size:11px; font-weight:650; }
            QLineEdit#equipmentDlgInput, QTextEdit#equipmentDlgNotes { background:#F8FAFC; color:#0F172A; border:1px solid #CBD5E1; border-radius:8px; padding:9px 11px; font-size:12px; selection-background-color:#0F766E; selection-color:#FFFFFF; }
            QLineEdit#equipmentDlgInput:focus, QTextEdit#equipmentDlgNotes:focus { background:#FFFFFF; border:1px solid #0F766E; }
            QLabel#equipmentDlgImage { background:#F8FAFC; color:#94A3B8; border:1px dashed #CBD5E1; border-radius:9px; font-size:11px; }
            QFrame#equipmentDlgDossierBox { background:#F8FAFC; border:1px solid #E2E8F0; border-radius:9px; }
            QLabel#equipmentDlgMiniTitle { color:#334155; font-size:9px; font-weight:900; letter-spacing:.5px; }
            QLabel#equipmentDlgMiniSub { color:#64748B; font-size:9px; }
            QListWidget#equipmentDlgList { background:#FFFFFF; color:#0F172A; border:1px solid #D7E0E8; border-radius:8px; padding:4px; outline:none; }
            QListWidget#equipmentDlgList::item { min-height:38px; padding:5px 8px; border-bottom:1px solid #EEF2F6; }
            QListWidget#equipmentDlgList::item:selected { background:#E6FFFB; color:#0F766E; border-radius:5px; }
            QFrame#equipmentDlgFooter { background:#FFFFFF; border-top:1px solid #E2E8F0; }
            QLabel#equipmentDlgFooterHint { color:#94A3B8; font-size:9px; }
            QPushButton#equipmentDlgPrimary { background:#0F766E; color:#FFFFFF; border:none; border-radius:8px; padding:9px 18px; font-size:12px; font-weight:800; }
            QPushButton#equipmentDlgPrimary:hover { background:#0D9488; }
            QPushButton#equipmentDlgSecondary, QPushButton#equipmentDlgGhost, QPushButton#equipmentDlgMiniGhost { background:#FFFFFF; color:#334155; border:1px solid #CBD5E1; border-radius:8px; padding:8px 12px; font-size:10px; font-weight:700; }
            QPushButton#equipmentDlgSecondary:hover, QPushButton#equipmentDlgGhost:hover, QPushButton#equipmentDlgMiniGhost:hover { background:#F1F5F9; border-color:#94A3B8; }
            QPushButton#equipmentDlgMiniPrimary { background:#ECFDF5; color:#0F766E; border:1px solid #99F6E4; border-radius:8px; padding:8px 12px; font-size:10px; font-weight:800; }
            QPushButton#equipmentDlgMiniPrimary:hover { background:#CCFBF1; }
        """)

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Escolher imagem do equipamento", "", "Imagens (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if path: self._image_path = path; self._refresh_image_preview()

    def _remove_image(self):
        self._image_path = None; self._refresh_image_preview()

    def _refresh_image_preview(self):
        real = resolve_image_path(self._image_path) if self._image_path else None
        pixmap = QPixmap(real) if real else QPixmap()
        if pixmap.isNull():
            self.image_preview.clear(); self.image_preview.setText("Sem imagem" if not self._image_path else "Imagem\nnão encontrada"); return
        self.image_preview.setText("")
        self.image_preview.setPixmap(pixmap.scaled(QSize(230, 160), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _refresh_dossier_lists(self):
        self.docs_list.clear()
        for doc in self._documents:
            name = doc.get("original_name") or (Path(doc.get("source_path") or doc.get("file_path") or "arquivo").name)
            item = QListWidgetItem(f"{doc.get('title') or 'Documento'}\n{name}")
            item.setToolTip(doc.get("notes") or name); self.docs_list.addItem(item)
        self.faults_list.clear()
        for fault in self._faults:
            count = int(fault.get("occurrences") or 1)
            item = QListWidgetItem(f"{fault.get('title') or 'Defeito'}\n{count} ocorrência(s) • {fault.get('symptom') or ''}")
            item.setToolTip(fault.get("solution") or ""); self.faults_list.addItem(item)

    def _add_document_buffer(self):
        dlg = MachineDocumentDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        title, source, notes = dlg.values()
        self._documents.append({"id": None, "title": title, "file_path": None, "original_name": Path(source).name, "notes": notes or None, "source_path": source})
        self._refresh_dossier_lists(); self.docs_list.setCurrentRow(self.docs_list.count() - 1)

    def _remove_document_buffer(self):
        row = self.docs_list.currentRow()
        if row < 0: return
        del self._documents[row]; self._refresh_dossier_lists()

    def _add_fault_buffer(self):
        dlg = MachineFaultDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        data = dlg.values(); data["id"] = None; self._faults.append(data)
        self._refresh_dossier_lists(); self.faults_list.setCurrentRow(self.faults_list.count() - 1)

    def _edit_fault_buffer(self):
        row = self.faults_list.currentRow()
        if row < 0: return
        data = self._faults[row]
        class _FaultProxy:
            pass
        proxy = _FaultProxy()
        for key in ("title", "symptom", "probable_cause", "solution", "occurrences", "notes"):
            setattr(proxy, key, data.get(key))
        dlg = MachineFaultDialog(self, proxy)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        edited = dlg.values(); edited["id"] = data.get("id"); self._faults[row] = edited; self._refresh_dossier_lists(); self.faults_list.setCurrentRow(row)

    def _remove_fault_buffer(self):
        row = self.faults_list.currentRow()
        if row < 0: return
        del self._faults[row]; self._refresh_dossier_lists()

    def _validate(self):
        if not self.name_input.text().strip():
            self.error_label.setText("Informe o nome do equipamento."); self.name_input.setFocus(); return
        self.error_label.clear(); self.accept()

    def values(self):
        return (
            self.name_input.text().strip(),
            self.code_input.text().strip(),
            self.desc_input.toPlainText().strip(),
            self._image_path,
            [dict(d) for d in self._documents],
            [dict(f) for f in self._faults],
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
        self.machine_label = QLabel(self.board.machine.name if self.board.machine else "Sem equipamento")
        basic_layout.addRow("Equipamento:", self.machine_label)
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



class StatusBadge(QLabel):
    """Badge semântico reutilizável para estados de máquina/placa."""

    def __init__(self, text: str, tone: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setObjectName("statusBadge")
        self.setProperty("tone", tone)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)


class BoardCatalogCard(QFrame):
    """Linha/card reutilizável de uma placa dentro de uma máquina."""

    clicked = pyqtSignal(int)
    doubleClicked = pyqtSignal(int)
    detailsRequested = pyqtSignal(int)
    testRequested = pyqtSignal(int)
    moveRequested = pyqtSignal(int)
    deleteRequested = pyqtSignal(int)

    def __init__(self, board: BoardUnit, last_run=None, selected=False, parent=None):
        super().__init__(parent)
        self.board_id = int(board.id)
        self.setObjectName("boardCatalogCard")
        self.setProperty("selected", bool(selected))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f"Placa {board.name}")

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 10, 10)
        row.setSpacing(10)

        thumb = QLabel()
        thumb.setObjectName("boardThumb")
        thumb.setFixedSize(44, 44)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = QPixmap()
        if board.images:
            real = resolve_image_path(board.images[0].path)
            pix = QPixmap(real) if real else QPixmap()
        if pix.isNull():
            thumb.setText("PCB")
        else:
            thumb.setPixmap(pix.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))
        row.addWidget(thumb)

        info = QVBoxLayout(); info.setSpacing(2)
        name = QLabel(board.name or f"Placa {board.id}")
        name.setObjectName("boardCatalogName")
        name.setWordWrap(True)
        model = board.model or "Sem modelo"
        version = f" • v{board.version}" if board.version else ""
        category = (board.board_model.category or "").strip() if board.board_model else ""
        type_part = f"{category}  •  " if category else ""
        meta = QLabel(f"{type_part}{model}{version}  •  SN {board.serial_number or '—'}")
        meta.setObjectName("boardCatalogMeta")
        info.addWidget(name)
        info.addWidget(meta)

        if last_run is not None:
            stamp = last_run.start_time.strftime("%d/%m/%Y %H:%M") if last_run.start_time else "—"
            test_line = QLabel(f"Último teste: {stamp}")
            test_line.setObjectName("boardLastTest")
            info.addWidget(test_line)
        row.addLayout(info, 1)

        status_tone = "success" if board.is_active else "neutral"
        status = StatusBadge("ATIVA" if board.is_active else "INATIVA", status_tone)
        row.addWidget(status)

        if last_run is None:
            test_badge = StatusBadge("PENDENTE", "warning")
        else:
            run_status = (last_run.status or "").lower()
            if run_status == "completed":
                test_badge = StatusBadge("TESTADA", "success")
            elif run_status == "running":
                test_badge = StatusBadge("EM TESTE", "warning")
            elif run_status == "failed":
                test_badge = StatusBadge("FALHA", "danger")
            else:
                test_badge = StatusBadge((last_run.status or "—").upper(), "neutral")
        row.addWidget(test_badge)

        details = QToolButton()
        details.setObjectName("cardIconButton")
        details.setText("↗")
        details.setToolTip("Ver detalhes da placa")
        details.setAccessibleName("Ver detalhes")
        details.clicked.connect(lambda: self.detailsRequested.emit(self.board_id))
        row.addWidget(details)

        more = QToolButton()
        more.setObjectName("cardIconButton")
        more.setText("⋯")
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more.setToolTip("Mais ações")
        menu = QMenu(more)
        act_details = menu.addAction("Ver detalhes")
        act_test = menu.addAction("Ir para teste")
        act_move = menu.addAction("Mover placa")
        menu.addSeparator()
        act_delete = menu.addAction("Excluir placa")
        act_details.triggered.connect(lambda: self.detailsRequested.emit(self.board_id))
        act_test.triggered.connect(lambda: self.testRequested.emit(self.board_id))
        act_move.triggered.connect(lambda: self.moveRequested.emit(self.board_id))
        act_delete.triggered.connect(lambda: self.deleteRequested.emit(self.board_id))
        more.setMenu(menu)
        row.addWidget(more)

    def set_selected(self, selected: bool):
        self.setProperty("selected", bool(selected))
        self.style().unpolish(self); self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.board_id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit(self.board_id)
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.doubleClicked.emit(self.board_id)
            event.accept(); return
        super().keyPressEvent(event)


class MachineCatalogCard(QFrame):
    """Card expansível de máquina com suas placas vinculadas."""

    machineClicked = pyqtSignal(int)
    expandedChanged = pyqtSignal(int, bool)
    editRequested = pyqtSignal(int)
    deleteRequested = pyqtSignal(int)
    boardClicked = pyqtSignal(int)
    boardDoubleClicked = pyqtSignal(int)
    boardDetailsRequested = pyqtSignal(int)
    boardTestRequested = pyqtSignal(int)
    boardMoveRequested = pyqtSignal(int)
    boardDeleteRequested = pyqtSignal(int)

    def __init__(self, machine: Machine, boards, last_runs: dict, *, expanded=False,
                 selected_machine=False, selected_board_id=None, compact=False, parent=None):
        super().__init__(parent)
        self.machine_id = int(machine.id)
        self._expanded = bool(expanded)
        self._compact = bool(compact and not expanded)
        self.setObjectName("machineCatalogCard")
        self.setProperty("selected", bool(selected_machine))
        self.setProperty("compact", self._compact)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame(); header.setObjectName("machineCardHeader")
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        if self._compact:
            h = QHBoxLayout(header); h.setContentsMargins(10, 9, 8, 9); h.setSpacing(7)
        else:
            h = QHBoxLayout(header); h.setContentsMargins(14, 13, 10, 13); h.setSpacing(10)

        image = QLabel(); image.setObjectName("machineCardImage")
        image.setFixedSize(36, 36) if self._compact else image.setFixedSize(48, 48)
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        real = resolve_image_path(machine.image_path) if machine.image_path else None
        pix = QPixmap(real) if real else QPixmap()
        if pix.isNull(): image.setText("M")
        else:
            thumb_size = 32 if self._compact else 44
            image.setPixmap(pix.scaled(thumb_size, thumb_size, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation))
        h.addWidget(image)

        text = QVBoxLayout(); text.setSpacing(2)
        title = QLabel(machine.name); title.setObjectName("machineCardTitle")
        code = machine.code or f"ID #{machine.id}"
        self._machine_code = code
        self._total_board_count = len(boards)
        self.meta_label = QLabel(f"{code}  •  {len(boards)} placa(s)")
        self.meta_label.setObjectName("machineCardMeta")
        text.addWidget(title); text.addWidget(self.meta_label)
        h.addLayout(text, 1)

        state = StatusBadge("CADASTRADA", "neutral")
        state.setVisible(not self._compact)
        h.addWidget(state)

        more = QToolButton(); more.setObjectName("cardIconButton"); more.setText("⋯")
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        edit = menu.addAction("Editar equipamento")
        delete = menu.addAction("Excluir equipamento")
        edit.triggered.connect(lambda: self.editRequested.emit(self.machine_id))
        delete.triggered.connect(lambda: self.deleteRequested.emit(self.machine_id))
        more.setMenu(menu)
        more.setVisible(not self._compact)
        h.addWidget(more)

        self.expand_btn = QToolButton(); self.expand_btn.setObjectName("expandButton")
        self.expand_btn.setText("⌄" if self._expanded else "›")
        self.expand_btn.setToolTip("Expandir/recolher placas")
        self.expand_btn.clicked.connect(self._toggle)
        h.addWidget(self.expand_btn)
        root.addWidget(header)

        # Clique em qualquer área livre do cabeçalho seleciona a máquina e alterna expansão.
        header.mousePressEvent = self._header_press

        self.boards_frame = QFrame(); self.boards_frame.setObjectName("machineBoardsArea")
        self.boards_layout = QVBoxLayout(self.boards_frame)
        self.boards_layout.setContentsMargins(12, 2, 12, 12); self.boards_layout.setSpacing(7)
        self.board_cards = {}
        for board in boards:
            row = BoardCatalogCard(
                board, last_runs.get(board.id), selected=(board.id == selected_board_id), parent=self
            )
            row.clicked.connect(self.boardClicked)
            row.doubleClicked.connect(self.boardDoubleClicked)
            row.detailsRequested.connect(self.boardDetailsRequested)
            row.testRequested.connect(self.boardTestRequested)
            row.moveRequested.connect(self.boardMoveRequested)
            row.deleteRequested.connect(self.boardDeleteRequested)
            self.board_cards[int(board.id)] = row
            self.boards_layout.addWidget(row)

        self.empty_boards_label = QLabel("Nenhuma placa vinculada a este equipamento")
        self.empty_boards_label.setObjectName("machineNoBoards")
        self.empty_boards_label.setVisible(not bool(boards))
        self.boards_layout.addWidget(self.empty_boards_label)

        self.boards_frame.setVisible(self._expanded)
        root.addWidget(self.boards_frame)

    def apply_board_filter(self, visible_board_ids, *, force_expand=False):
        """Filtra as placas sem destruir/recriar os widgets do card.

        Isso evita o flicker que ocorria quando o catálogo inteiro era montado
        novamente a cada tecla da pesquisa ou alteração de filtro.
        """
        visible_ids = {int(bid) for bid in visible_board_ids}
        for bid, card in self.board_cards.items():
            card.setVisible(bid in visible_ids)

        visible_count = len(visible_ids)
        self.meta_label.setText(f"{self._machine_code}  •  {visible_count} placa(s)")
        self.empty_boards_label.setText(
            "Nenhuma placa corresponde aos filtros neste equipamento"
            if self.board_cards else
            "Nenhuma placa vinculada a este equipamento"
        )
        self.empty_boards_label.setVisible(visible_count == 0)

        expanded_visually = bool(force_expand or self._expanded)
        self.boards_frame.setVisible(expanded_visually)
        self.expand_btn.setText("⌄" if expanded_visually else "›")

    def _header_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.machineClicked.emit(self.machine_id)
            self._toggle()

    def _toggle(self):
        self._expanded = not self._expanded
        self.boards_frame.setVisible(self._expanded)
        self.expand_btn.setText("⌄" if self._expanded else "›")
        self.expandedChanged.emit(self.machine_id, self._expanded)

    def set_selected(self, selected: bool):
        self.setProperty("selected", bool(selected))
        self.style().unpolish(self); self.style().polish(self)


class FilterBar(QFrame):
    """Busca, filtros e ordenação com visual de chips técnicos."""

    changed = pyqtSignal()
    viewChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("filterBar")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 11, 14, 11)
        row.setSpacing(9)

        self.search = QLineEdit()
        self.search.setObjectName("catalogSearch")
        self.search.setPlaceholderText("Buscar equipamento, placa, modelo, código ou SN…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(300)
        self.search.setMinimumHeight(38)

        # Não reconstrói o catálogo a cada tecla. Em Windows, recriar todos os
        # cards/miniaturas em cada textChanged pode causar um flash visual da
        # janela/console que está por trás do aplicativo. O debounce espera o
        # operador terminar de digitar antes de aplicar o filtro.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self.changed.emit)
        self.search.textChanged.connect(lambda _text: self._search_timer.start())
        row.addWidget(self.search, 1)

        self.status = self._make_filter(132)
        self.status.addItem("Todos os status", "all")
        self.status.addItem("Somente ativas", "active")
        self.status.addItem("Somente inativas", "inactive")
        self._bind_filter(self.status, "all")
        row.addWidget(self.status)

        self.machine = self._make_filter(156)
        self.machine.addItem("Todos os equipamentos", None)
        self._bind_filter(self.machine, None)
        row.addWidget(self.machine)

        self.board_type = self._make_filter(138)
        self.board_type.addItem("Todos os tipos", None)
        self._bind_filter(self.board_type, None)
        row.addWidget(self.board_type)

        self.sort = QComboBox()
        self.sort.setObjectName("catalogSort")
        self.sort.setMinimumWidth(142)
        self.sort.setMinimumHeight(38)
        self.sort.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sort.addItem("Nome A–Z", "name")
        self.sort.addItem("Mais recentes", "recent")
        self.sort.addItem("Por status", "status")
        self.sort.currentIndexChanged.connect(self.changed)
        row.addWidget(self.sort)


    def _make_filter(self, width: int) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName("catalogFilter")
        combo.setMinimumWidth(width)
        combo.setMinimumHeight(38)
        combo.setCursor(Qt.CursorShape.PointingHandCursor)
        combo.setProperty("active", False)
        return combo

    def _bind_filter(self, combo: QComboBox, neutral_value) -> None:
        combo.currentIndexChanged.connect(
            lambda _index, c=combo, neutral=neutral_value: self._update_filter_state(c, neutral)
        )
        combo.currentIndexChanged.connect(self.changed)

    @staticmethod
    def _update_filter_state(combo: QComboBox, neutral_value) -> None:
        active = combo.currentData() != neutral_value
        combo.setProperty("active", active)
        combo.style().unpolish(combo)
        combo.style().polish(combo)
        combo.update()

    def refresh_visual_states(self) -> None:
        self._update_filter_state(self.status, "all")
        self._update_filter_state(self.machine, None)
        self._update_filter_state(self.board_type, None)

class PlacaTab(QWidget):
    """Aba completa para gerenciamento de placas"""
    
    board_imported = pyqtSignal(object)  # Emite a placa importada
    board_details_requested = pyqtSignal(int)  # Abre /placas/:id/detalhes

    EMPTY_TEXT = "📋\n\nSelecione uma placa na lista para ver os detalhes\nou um equipamento para ver o resumo dele"
    
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
        """Catálogo técnico de máquinas/placas + painel contextual à direita."""
        self.setObjectName("placaRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Visualização única: lista vertical, mais compacta e legível.
        self.catalog_view_mode = "list"
        self._expanded_machine_ids = set()
        self._machine_cards = {}
        self._board_cards = {}
        self._last_catalog_columns = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 12)
        root.setSpacing(12)

        root.addWidget(self.create_header())
        root.addWidget(self.create_stats_panel())

        self.filter_bar = FilterBar(self)
        self.filter_bar.changed.connect(self.filter_boards)
        root.addWidget(self.filter_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("catalogSplitter")
        splitter.setHandleWidth(8)
        splitter.setChildrenCollapsible(False)

        # A coluna do inventário continua menor que o painel de detalhes,
        # porém com largura suficiente para não cortar nome/modelo, badges e
        # ações das máquinas/placas. O usuário ainda pode arrastar a divisória.
        left_panel = self.create_left_panel()
        left_panel.setMinimumWidth(500)
        left_panel.setMaximumWidth(640)

        right_panel = self.create_right_panel()
        right_panel.setMinimumWidth(600)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        # Em uma janela ~1500 px, abre perto de 36/64: inventário legível,
        # mas o painel contextual ainda recebe a maior parte da tela.
        splitter.setSizes([560, 980])
        root.addWidget(splitter, 1)

        self.status_label = QLabel("Pronto")
        self.status_label.setObjectName("statusText")
        root.addWidget(self.status_label)

    def create_header(self):
        header = QFrame(); header.setObjectName("placaHeader")
        row = QHBoxLayout(header); row.setContentsMargins(22, 17, 18, 17); row.setSpacing(12)

        text_box = QVBoxLayout(); text_box.setSpacing(3)
        eyebrow = QLabel("GESTÃO DE ATIVOS ELETRÔNICOS"); eyebrow.setObjectName("placaEyebrow")
        title = QLabel("Equipamentos e Placas"); title.setObjectName("placaTitle")
        self.catalog_subtitle = QLabel("0 equipamentos • 0 placas cadastradas")
        self.catalog_subtitle.setObjectName("placaSubtitle")
        text_box.addWidget(eyebrow); text_box.addWidget(title); text_box.addWidget(self.catalog_subtitle)
        row.addLayout(text_box, 1)

        self.add_machine_btn = QPushButton("+ Novo Equipamento")
        self.add_machine_btn.setObjectName("btnSecondaryHeader")
        self.add_machine_btn.setMinimumHeight(40)
        self.add_machine_btn.clicked.connect(self.add_machine)
        row.addWidget(self.add_machine_btn)

        self.add_board_btn = QPushButton("+ Nova Placa")
        self.add_board_btn.setObjectName("btnPrimaryHeader")
        self.add_board_btn.setMinimumHeight(40)
        self.add_board_btn.clicked.connect(lambda _checked=False: self.add_board_dialog())
        row.addWidget(self.add_board_btn)
        return header

    def _stat_card(self, caption, attr, accent=False):
        card = QFrame(); card.setObjectName("catalogStatCard")
        card.setProperty("accent", bool(accent))
        box = QVBoxLayout(card); box.setContentsMargins(15, 11, 15, 11); box.setSpacing(2)
        cap = QLabel(caption); cap.setObjectName("catalogStatCaption")
        val = QLabel("0"); val.setObjectName("catalogStatValue")
        box.addWidget(cap); box.addWidget(val)
        setattr(self, attr, val)
        return card

    def create_stats_panel(self):
        wrap = QWidget(); row = QHBoxLayout(wrap); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(10)
        row.addWidget(self._stat_card("TOTAL DE EQUIPAMENTOS", "stat_machines"))
        row.addWidget(self._stat_card("TOTAL DE PLACAS", "stat_boards"))
        row.addWidget(self._stat_card("ATIVAS / INATIVAS", "stat_active_split", True))
        row.addWidget(self._stat_card("TESTES HOJE", "stat_tests_today"))
        return wrap

    def create_left_panel(self):
        card = QFrame(); card.setObjectName("catalogCard")
        layout = QVBoxLayout(card); layout.setContentsMargins(12, 12, 12, 12); layout.setSpacing(10)

        top = QHBoxLayout(); top.setSpacing(8)
        title_box = QVBoxLayout(); title_box.setSpacing(1)
        title = QLabel("Inventário técnico"); title.setObjectName("catalogSectionTitle")
        self.catalog_result_label = QLabel("Todos os equipamentos e placas")
        self.catalog_result_label.setObjectName("catalogSectionSub")
        title_box.addWidget(title); title_box.addWidget(self.catalog_result_label)
        top.addLayout(title_box, 1)
        hint = QLabel("Clique no equipamento para expandir • duplo clique na placa para abrir")
        hint.setObjectName("catalogHint")
        top.addWidget(hint)
        layout.addLayout(top)

        self.catalog_scroll = QScrollArea(); self.catalog_scroll.setObjectName("catalogScroll")
        self.catalog_scroll.setWidgetResizable(True); self.catalog_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.catalog_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.catalog_host = QWidget(); self.catalog_host.setObjectName("catalogHost")
        self.catalog_layout = QGridLayout(self.catalog_host)
        self.catalog_layout.setContentsMargins(2, 2, 2, 2)
        self.catalog_layout.setHorizontalSpacing(10); self.catalog_layout.setVerticalSpacing(10)
        self.catalog_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.catalog_scroll.setWidget(self.catalog_host)
        layout.addWidget(self.catalog_scroll, 1)

        self.catalog_empty = QFrame(); self.catalog_empty.setObjectName("catalogEmpty")
        empty_box = QVBoxLayout(self.catalog_empty); empty_box.setContentsMargins(28, 42, 28, 42); empty_box.setSpacing(8)
        icon = QLabel("PCB"); icon.setObjectName("emptyIcon"); icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_title = QLabel("Nenhum equipamento cadastrado"); self.empty_title.setObjectName("emptyTitle"); self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_text = QLabel("Cadastre o primeiro equipamento para começar a organizar suas placas.")
        self.empty_text.setObjectName("emptyText"); self.empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter); self.empty_text.setWordWrap(True)
        empty_btn = QPushButton("+ Novo Equipamento"); empty_btn.setObjectName("btnPrimary"); empty_btn.clicked.connect(self.add_machine)
        empty_btn.setMaximumWidth(170)
        empty_box.addStretch(); empty_box.addWidget(icon); empty_box.addWidget(self.empty_title); empty_box.addWidget(self.empty_text)
        empty_box.addWidget(empty_btn, 0, Qt.AlignmentFlag.AlignCenter); empty_box.addStretch()
        self.catalog_empty.setVisible(False)
        layout.addWidget(self.catalog_empty, 1)
        return card

    def _set_catalog_view(self, mode: str = "list"):
        """Mantido por compatibilidade interna; a tela usa somente o modo lista."""
        self.catalog_view_mode = "list"
        self._last_catalog_columns = 1
        self._rebuild_catalog()

    def _catalog_columns(self):
        return 1

    def resizeEvent(self, event):
        super().resizeEvent(event)

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
        """Estilo técnico/industrial moderno, mantendo a identidade do sistema."""
        self.setStyleSheet("""
            QWidget#placaRoot { background:#F3F6F8; color:#0F172A; font-family:'Segoe UI'; }
            QSplitter#catalogSplitter::handle { background:transparent; }

            QFrame#placaHeader { background:#0B1220; border:1px solid #1E293B; border-radius:12px; }
            QLabel#placaEyebrow { color:#2DD4BF; font-size:9px; font-weight:800; letter-spacing:1px; }
            QLabel#placaTitle { color:#F8FAFC; font-size:22px; font-weight:750; }
            QLabel#placaSubtitle { color:#94A3B8; font-size:11px; }
            QPushButton#btnPrimaryHeader { background:#0F766E; color:white; border:1px solid #14B8A6;
                border-radius:8px; padding:0 16px; font-weight:700; }
            QPushButton#btnPrimaryHeader:hover { background:#0D9488; }
            QPushButton#btnSecondaryHeader { background:#172033; color:#E2E8F0; border:1px solid #334155;
                border-radius:8px; padding:0 16px; font-weight:650; }
            QPushButton#btnSecondaryHeader:hover { border-color:#2DD4BF; background:#1E293B; }

            QFrame#catalogStatCard { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:10px; }
            QFrame#catalogStatCard[accent="true"] { border-color:#99F6E4; background:#F0FDFA; }
            QLabel#catalogStatCaption { color:#64748B; font-size:9px; font-weight:800; letter-spacing:.5px; }
            QLabel#catalogStatValue { color:#0F172A; font-size:20px; font-weight:750; }

            QFrame#filterBar {
                background:#FFFFFF;
                border:1px solid #E2E8F0;
                border-radius:12px;
            }
            QLineEdit#catalogSearch {
                background:#F8FAFC;
                color:#0F172A;
                border:1px solid #E2E8F0;
                border-radius:9px;
                min-height:38px;
                padding:0 12px;
                font-size:11px;
                selection-background-color:#99F6E4;
            }
            QLineEdit#catalogSearch:hover { background:#FFFFFF; border-color:#CBD5E1; }
            QLineEdit#catalogSearch:focus {
                background:#FFFFFF;
                border:1px solid #0F766E;
            }

            QComboBox#catalogFilter, QComboBox#catalogSort {
                background:#F8FAFC;
                color:#475569;
                border:1px solid #E2E8F0;
                border-radius:18px;
                min-height:38px;
                padding:0 30px 0 13px;
                font-size:10px;
                font-weight:650;
            }
            QComboBox#catalogFilter:hover, QComboBox#catalogSort:hover {
                background:#F1F5F9;
                color:#0F172A;
                border-color:#CBD5E1;
            }
            QComboBox#catalogFilter:focus, QComboBox#catalogSort:focus {
                background:#FFFFFF;
                color:#0F172A;
                border:1px solid #0F766E;
            }
            QComboBox#catalogFilter[active="true"] {
                background:#F0FDFA;
                color:#0F766E;
                border:1px solid #5EEAD4;
                font-weight:750;
            }
            QComboBox#catalogFilter[active="true"]:hover {
                background:#CCFBF1;
                border-color:#2DD4BF;
            }
            QComboBox#catalogFilter::drop-down, QComboBox#catalogSort::drop-down {
                subcontrol-origin:padding;
                subcontrol-position:top right;
                width:28px;
                border:none;
                background:transparent;
            }
            QComboBox#catalogFilter QAbstractItemView, QComboBox#catalogSort QAbstractItemView {
                background:#FFFFFF;
                color:#0F172A;
                border:1px solid #CBD5E1;
                outline:0;
                padding:5px;
                selection-background-color:#CCFBF1;
                selection-color:#0F766E;
            }

            QFrame#viewSwitch {
                background:#F1F5F9;
                border:1px solid #E2E8F0;
                border-radius:9px;
            }
            QToolButton#viewToggle {
                background:transparent;
                color:#64748B;
                border:none;
                border-radius:6px;
                min-width:34px;
                min-height:32px;
                font-size:15px;
                font-weight:750;
            }
            QToolButton#viewToggle:hover { background:#E2E8F0; color:#0F172A; }
            QToolButton#viewToggle:checked {
                background:#FFFFFF;
                color:#0F766E;
                border:1px solid #CBD5E1;
            }

            QFrame#catalogCard, QFrame#card { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:11px; }
            QLabel#catalogSectionTitle { color:#0F172A; font-size:14px; font-weight:750; }
            QLabel#catalogSectionSub { color:#64748B; font-size:10px; }
            QLabel#catalogHint { color:#94A3B8; font-size:9px; }
            QScrollArea#catalogScroll, QWidget#catalogHost { background:transparent; border:none; }

            QFrame#machineCatalogCard { background:#FFFFFF; border:1px solid #DCE3EA; border-radius:10px; }
            QFrame#machineCatalogCard[selected="true"] { border:1px solid #0F766E; background:#FCFFFE; }
            QFrame#machineCatalogCard[compact="true"] { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:9px; }
            QFrame#machineCatalogCard[compact="true"]:hover { border-color:#94A3B8; background:#F8FAFC; }
            QFrame#machineCardHeader { background:transparent; border:none; }
            QLabel#machineCardImage { background:#F1F5F9; color:#64748B; border:1px solid #E2E8F0; border-radius:8px;
                font-weight:800; }
            QLabel#machineCardTitle { color:#0F172A; font-size:13px; font-weight:750; }
            QLabel#machineCardMeta { color:#64748B; font-size:10px; }
            QFrame#machineBoardsArea { background:#F8FAFC; border-top:1px solid #EEF2F7; border-bottom-left-radius:9px; border-bottom-right-radius:9px; }
            QLabel#machineNoBoards { color:#94A3B8; font-size:10px; padding:8px; }
            QToolButton#expandButton, QToolButton#cardIconButton { background:#F8FAFC; color:#475569; border:1px solid #E2E8F0;
                border-radius:6px; min-width:28px; min-height:28px; font-weight:800; }
            QToolButton#expandButton:hover, QToolButton#cardIconButton:hover { border-color:#0F766E; color:#0F766E; background:#F0FDFA; }

            QFrame#boardCatalogCard { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:8px; }
            QFrame#boardCatalogCard:hover { background:#F8FFFD; border-color:#99F6E4; }
            QFrame#boardCatalogCard[selected="true"] { background:#ECFDF5; border:1px solid #0F766E; }
            QLabel#boardThumb { background:#F8FAFC; color:#64748B; border:1px solid #E2E8F0; border-radius:7px; font-size:9px; font-weight:800; }
            QLabel#boardCatalogName { color:#0F172A; font-size:11px; font-weight:750; }
            QLabel#boardCatalogMeta, QLabel#boardLastTest { color:#64748B; font-size:9px; }

            QLabel#statusBadge { border-radius:7px; padding:4px 8px; font-size:8px; font-weight:800; }
            QLabel#statusBadge[tone="success"] { background:#DCFCE7; color:#166534; border:1px solid #BBF7D0; }
            QLabel#statusBadge[tone="warning"] { background:#FEF3C7; color:#92400E; border:1px solid #FDE68A; }
            QLabel#statusBadge[tone="danger"] { background:#FEE2E2; color:#991B1B; border:1px solid #FECACA; }
            QLabel#statusBadge[tone="neutral"] { background:#F1F5F9; color:#64748B; border:1px solid #E2E8F0; }

            QFrame#catalogEmpty { background:#FAFCFD; border:1px dashed #CBD5E1; border-radius:10px; }
            QLabel#emptyIcon { color:#0F766E; font-size:17px; font-weight:800; }
            QLabel#emptyTitle { color:#0F172A; font-size:15px; font-weight:750; }
            QLabel#emptyText { color:#64748B; font-size:11px; }
            QFrame#skeletonCard { background:#F8FAFC; border:1px solid #E2E8F0; border-radius:10px; }
            QFrame#skeletonLine { background:#E2E8F0; border:none; border-radius:4px; }

            QPushButton#btnPrimary { background:#0F766E; color:#FFFFFF; border:1px solid #0D9488; border-radius:8px;
                padding:7px 13px; font-size:12px; font-weight:700; }
            QPushButton#btnPrimary:hover { background:#0D9488; }
            QPushButton#btnSecondary, QPushButton#btnGhost, QPushButton#btnBlue, QPushButton#btnPurple {
                background:#F1F5F9; color:#334155; border:1px solid #CBD5E1; border-radius:8px;
                padding:7px 13px; font-size:12px; font-weight:600; }
            QPushButton#btnSecondary:hover, QPushButton#btnGhost:hover, QPushButton#btnBlue:hover, QPushButton#btnPurple:hover { background:#E2E8F0; }
            QPushButton#btnDanger, QPushButton#btnDangerSoft { background:#FEF2F2; color:#B91C1C; border:1px solid #FCA5A5;
                border-radius:8px; padding:7px 13px; font-size:12px; font-weight:700; }
            QPushButton#btnDanger:hover, QPushButton#btnDangerSoft:hover { background:#FEE2E2; }

            QLabel#emptyState { color:#64748B; font-size:12px; background:#F8FAFC; border:1px dashed #CBD5E1; border-radius:10px; padding:24px; }
            QLabel#detailTitle { color:#0F172A; font-size:20px; font-weight:700; }
            QLabel#statusOn { background:#F0FDFA; color:#0F766E; border:1px solid #14B8A6; border-radius:8px; padding:4px 9px; font-size:10px; font-weight:700; }
            QLabel#statusOff { background:#F1F5F9; color:#64748B; border:1px solid #CBD5E1; border-radius:8px; padding:4px 9px; font-size:10px; font-weight:700; }
            QLabel#machineChip { background:#E0F2FE; color:#0369A1; border-radius:8px; padding:4px 9px; font-size:10px; font-weight:700; }
            QFrame#infoTile { background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; }
            QLabel#tileCaption { color:#64748B; font-size:9px; font-weight:700; }
            QLabel#tileText { color:#0F172A; font-size:13px; font-weight:600; }
            QFrame#statTile { background:#F0FDFA; border:1px solid #CCFBF1; border-radius:8px; }
            QLabel#tileValue { color:#0F766E; font-size:19px; font-weight:700; }
            QLabel#tileLabel { color:#475569; font-size:9px; font-weight:700; }
            QLabel#sectionTitle { color:#0F172A; font-size:12px; font-weight:700; }
            QLabel#descText { color:#334155; font-size:12px; }
            QLabel#statusText { color:#64748B; font-size:10px; padding:2px 4px; }

            /* Dossiê técnico da máquina */
            QFrame#machineHero { background:#0B1220; border:1px solid #1E293B; border-radius:12px; }
            QLabel#machineEyebrow { color:#2DD4BF; font-size:9px; font-weight:800; letter-spacing:1px; }
            QLabel#machineHeroTitle { color:#FFFFFF; font-size:21px; font-weight:750; }
            QLabel#machineHeroMeta { color:#94A3B8; font-size:10px; }
            QPushButton#btnHeroPrimary { background:#0F766E; color:#FFFFFF; border:none; border-radius:8px; min-height:38px; padding:0 15px; font-weight:700; }
            QPushButton#btnHeroSecondary { background:#172033; color:#E2E8F0; border:1px solid #334155; border-radius:8px; min-height:38px; padding:0 15px; font-weight:650; }
            QTabWidget#machineTabs::pane { border:0; background:transparent; }
            QTabWidget#machineTabs QTabBar::tab { background:#F1F5F9; color:#64748B; border:1px solid #E2E8F0; padding:9px 16px; margin-right:4px; border-top-left-radius:7px; border-top-right-radius:7px; font-weight:650; }
            QTabWidget#machineTabs QTabBar::tab:selected { background:#FFFFFF; color:#0F172A; border-bottom-color:#FFFFFF; }
            QFrame#machineSummaryCard, QFrame#machineContentCard, QFrame#faultDetailCard { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:10px; }
            QLabel#machineSectionLabel { color:#64748B; font-size:9px; font-weight:800; letter-spacing:.7px; }
            QFrame#machineSummaryLine { border-bottom:1px solid #EEF2F7; }
            QLabel#summaryCaption { color:#64748B; font-size:11px; }
            QLabel#summaryValue { color:#0F172A; font-size:12px; font-weight:700; }
            QLabel#machineDesc { color:#334155; font-size:11px; }
            QFrame#linkedBoardRow { background:#F8FAFC; border:1px solid #EEF2F7; border-radius:8px; }
            QLabel#linkedBoardName { color:#0F172A; font-size:12px; font-weight:700; }
            QLabel#linkedBoardMeta { color:#64748B; font-size:10px; }
            QLabel#linkedBoardState { color:#0F766E; font-size:9px; font-weight:800; }
            QLabel#machineEmpty { color:#94A3B8; font-size:11px; padding:12px; }
            QLabel#machineTabTitle { color:#0F172A; font-size:16px; font-weight:750; }
            QLabel#machineTabSub { color:#64748B; font-size:10px; }
            /* Tabelas do dossiê técnico */
            QTableWidget#machineDataTable {
                background:#FFFFFF;
                alternate-background-color:#F8FAFC;
                color:#1E293B;
                border:1px solid #D7E0EA;
                border-radius:10px;
                gridline-color:transparent;
                selection-background-color:#E6F7F4;
                selection-color:#0F172A;
                outline:0;
                font:11px 'Segoe UI';
            }
            QTableWidget#machineDataTable::item {
                padding:9px 10px;
                border-bottom:1px solid #EEF2F7;
            }
            QTableWidget#machineDataTable::item:hover {
                background:#F1F7F9;
            }
            QTableWidget#machineDataTable::item:selected {
                background:#DDF5F1;
                color:#0F172A;
                border-bottom:1px solid #BFE7E0;
            }
            QTableWidget#machineDataTable QHeaderView::section {
                background:#F4F7FA;
                color:#475569;
                border:0;
                border-bottom:1px solid #D7E0EA;
                padding:10px 9px;
                font:700 10px 'Segoe UI';
            }
            QTableWidget#machineDataTable QTableCornerButton::section {
                background:#F4F7FA;
                border:0;
                border-bottom:1px solid #D7E0EA;
            }
            QTableWidget#machineDataTable QScrollBar:vertical {
                background:transparent; width:10px; margin:4px 2px 4px 2px;
            }
            QTableWidget#machineDataTable QScrollBar::handle:vertical {
                background:#CBD5E1; min-height:28px; border-radius:5px;
            }
            QTableWidget#machineDataTable QScrollBar::handle:vertical:hover { background:#94A3B8; }
            QTableWidget#machineDataTable QScrollBar::add-line:vertical,
            QTableWidget#machineDataTable QScrollBar::sub-line:vertical { height:0; }

            QFrame#orphanSection { background:#F8FAFC; border:1px solid #E2E8F0; border-radius:12px; }
            QLabel#orphanSectionTitle { color:#334155; font-size:12px; font-weight:800; letter-spacing:0.6px; }
            QLabel#orphanSectionMeta { color:#64748B; font-size:11px; font-weight:600; }

            QFrame#faultDetailCard {
                background:#FBFDFE;
                border:1px solid #DCE5ED;
                border-left:4px solid #0F766E;
                border-radius:10px;
            }
            QLabel#faultDetailTitle { color:#0F172A; font-size:15px; font-weight:750; }
            QLabel#faultDetailBody { color:#334155; font:11px 'Segoe UI'; line-height:1.35; }
            QLabel#faultHint { color:#94A3B8; font-size:10px; }
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
        """Dossiê técnico profissional exibido quando uma máquina é selecionada."""
        clear_layout(self.details_layout)
        self.session.refresh(machine)

        # ── Cabeçalho do dossiê ─────────────────────────────────────────
        hero = QFrame(); hero.setObjectName("machineHero")
        hero_row = QHBoxLayout(hero); hero_row.setContentsMargins(18, 16, 18, 16); hero_row.setSpacing(14)
        hero_text = QVBoxLayout(); hero_text.setSpacing(3)
        eyebrow = QLabel("DOSSIÊ TÉCNICO DO EQUIPAMENTO"); eyebrow.setObjectName("machineEyebrow")
        title = QLabel(machine.name); title.setObjectName("machineHeroTitle"); title.setWordWrap(True)
        meta_parts = []
        if machine.code: meta_parts.append(f"Código {machine.code}")
        meta_parts.append(f"{len(machine.boards)} placa(s)")
        meta_parts.append(f"{len(machine.documents)} documento(s)")
        meta_parts.append(f"{len(machine.faults)} defeito(s) conhecido(s)")
        meta = QLabel("  •  ".join(meta_parts)); meta.setObjectName("machineHeroMeta")
        hero_text.addWidget(eyebrow); hero_text.addWidget(title); hero_text.addWidget(meta)
        hero_row.addLayout(hero_text, 1)
        edit_btn = QPushButton("Editar equipamento"); edit_btn.setObjectName("btnHeroSecondary"); edit_btn.clicked.connect(self.edit_machine)
        add_btn = QPushButton("Cadastrar placa"); add_btn.setObjectName("btnHeroPrimary"); add_btn.clicked.connect(self._start_board_for_machine)
        hero_row.addWidget(edit_btn); hero_row.addWidget(add_btn)
        self.details_layout.addWidget(hero)

        tabs = QTabWidget(); tabs.setObjectName("machineTabs"); tabs.setDocumentMode(True)
        self.details_layout.addWidget(tabs, 1)

        # ── Visão geral ─────────────────────────────────────────────────
        overview = QWidget(); ov = QVBoxLayout(overview); ov.setContentsMargins(4, 12, 4, 4); ov.setSpacing(12)
        overview_top = QHBoxLayout(); overview_top.setSpacing(14)
        image_label = ImagePreviewLabel(); image_label.setMinimumSize(300, 245)
        real = resolve_image_path(machine.image_path) if machine.image_path else None
        if not (real and image_label.load(real)):
            image_label.show_message("Nenhuma imagem cadastrada\nUse 'Editar equipamento' para adicionar")
        overview_top.addWidget(image_label, 1)

        summary = QFrame(); summary.setObjectName("machineSummaryCard"); sb = QVBoxLayout(summary); sb.setContentsMargins(16, 14, 16, 14); sb.setSpacing(8)
        sh = QLabel("RESUMO"); sh.setObjectName("machineSectionLabel"); sb.addWidget(sh)
        code_value = machine.code or "—"
        for caption, value in (("Código", code_value), ("Placas vinculadas", str(len(machine.boards))),
                               ("Documentos técnicos", str(len(machine.documents))),
                               ("Defeitos catalogados", str(len(machine.faults)))):
            line = QFrame(); line.setObjectName("machineSummaryLine"); ll = QHBoxLayout(line); ll.setContentsMargins(0, 7, 0, 7)
            c = QLabel(caption); c.setObjectName("summaryCaption")
            v = QLabel(value); v.setObjectName("summaryValue")
            ll.addWidget(c); ll.addStretch(); ll.addWidget(v); sb.addWidget(line)
        if machine.description:
            sb.addSpacing(4)
            dt = QLabel("DESCRIÇÃO"); dt.setObjectName("machineSectionLabel"); sb.addWidget(dt)
            desc = QLabel(machine.description); desc.setObjectName("machineDesc"); desc.setWordWrap(True); sb.addWidget(desc)
        sb.addStretch()
        overview_top.addWidget(summary, 1)
        ov.addLayout(overview_top)

        boards_card = QFrame(); boards_card.setObjectName("machineContentCard")
        bc = QVBoxLayout(boards_card); bc.setContentsMargins(16, 14, 16, 14); bc.setSpacing(8)
        bt = QLabel("PLACAS DESTE EQUIPAMENTO"); bt.setObjectName("machineSectionLabel"); bc.addWidget(bt)
        if machine.boards:
            for board in sorted(machine.boards, key=lambda b: b.name.lower()):
                row = QFrame(); row.setObjectName("linkedBoardRow"); rl = QHBoxLayout(row); rl.setContentsMargins(10, 8, 10, 8)
                name = QLabel(board.name); name.setObjectName("linkedBoardName")
                detail = QLabel(f"{board.model or '—'}  •  SN {board.serial_number or '—'}"); detail.setObjectName("linkedBoardMeta")
                state = QLabel("ATIVA" if board.is_active else "INATIVA"); state.setObjectName("linkedBoardState")
                rl.addWidget(name); rl.addWidget(detail, 1); rl.addWidget(state); bc.addWidget(row)
        else:
            empty = QLabel("Nenhuma placa vinculada a este equipamento."); empty.setObjectName("machineEmpty"); bc.addWidget(empty)
        ov.addWidget(boards_card)
        tabs.addTab(overview, "Visão Geral")

        # ── Documentos técnicos ─────────────────────────────────────────
        docs = QWidget(); dl = QVBoxLayout(docs); dl.setContentsMargins(4, 12, 4, 4); dl.setSpacing(10)
        doc_head = QHBoxLayout()
        doc_text = QVBoxLayout(); doc_text.setSpacing(2)
        dtitle = QLabel("Documentos técnicos"); dtitle.setObjectName("machineTabTitle")
        dsub = QLabel("Datasheets, manuais, diagramas e procedimentos ficam centralizados neste dossiê."); dsub.setObjectName("machineTabSub")
        doc_text.addWidget(dtitle); doc_text.addWidget(dsub); doc_head.addLayout(doc_text, 1)
        add_doc = QPushButton("+ Adicionar documento"); add_doc.setObjectName("btnPrimary"); doc_head.addWidget(add_doc)
        dl.addLayout(doc_head)
        doc_table = QTableWidget(0, 4); doc_table.setObjectName("machineDataTable")
        doc_table.setHorizontalHeaderLabels(["DOCUMENTO", "ARQUIVO", "ADICIONADO EM", "ID"])
        doc_table.verticalHeader().setVisible(False)
        doc_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        doc_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        doc_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        doc_table.setAlternatingRowColors(True)
        doc_table.setShowGrid(False)
        doc_table.setWordWrap(False)
        doc_table.verticalHeader().setDefaultSectionSize(44)
        doc_table.horizontalHeader().setMinimumHeight(38)
        doc_table.horizontalHeader().setHighlightSections(False)
        doc_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        doc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        doc_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        doc_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        doc_table.setMinimumHeight(275)
        doc_table.setToolTip("Duplo clique para abrir o documento selecionado")
        for row, doc in enumerate(machine.documents):
            doc_table.insertRow(row)
            values = (
                doc.title,
                doc.original_name or Path(doc.file_path).name,
                doc.created_at.strftime("%d/%m/%Y  %H:%M"),
                f"#{doc.id}",
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, doc.id)
                if col == 0:
                    font = item.font(); font.setBold(True); item.setFont(font)
                    item.setForeground(QColor("#0F172A"))
                elif col in (2, 3):
                    item.setForeground(QColor("#64748B"))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter)
                else:
                    item.setForeground(QColor("#475569"))
                doc_table.setItem(row, col, item)
        doc_actions = QHBoxLayout(); doc_actions.addStretch()
        open_doc = QPushButton("Abrir documento"); open_doc.setObjectName("btnSecondary")
        remove_doc = QPushButton("Remover do dossiê"); remove_doc.setObjectName("btnDanger")
        doc_actions.addWidget(open_doc); doc_actions.addWidget(remove_doc)
        dl.addWidget(doc_table, 1); dl.addLayout(doc_actions)
        add_doc.clicked.connect(self._add_machine_document)
        open_doc.clicked.connect(lambda: self._open_machine_document(doc_table))
        remove_doc.clicked.connect(lambda: self._remove_machine_document(doc_table))
        doc_table.cellDoubleClicked.connect(lambda *_: self._open_machine_document(doc_table))
        tabs.addTab(docs, "Documentos Técnicos")

        # ── Defeitos recorrentes ────────────────────────────────────────
        faults = QWidget(); fl = QVBoxLayout(faults); fl.setContentsMargins(4, 12, 4, 4); fl.setSpacing(10)
        fault_head = QHBoxLayout()
        ftbox = QVBoxLayout(); ftbox.setSpacing(2)
        ftitle = QLabel("Defeitos recorrentes"); ftitle.setObjectName("machineTabTitle")
        fsub = QLabel("Base de conhecimento: sintomas, causas prováveis e como corrigir."); fsub.setObjectName("machineTabSub")
        ftbox.addWidget(ftitle); ftbox.addWidget(fsub); fault_head.addLayout(ftbox, 1)
        add_fault = QPushButton("+ Registrar defeito"); add_fault.setObjectName("btnPrimary"); fault_head.addWidget(add_fault)
        fl.addLayout(fault_head)

        fault_table = QTableWidget(0, 4); fault_table.setObjectName("machineDataTable")
        fault_table.setHorizontalHeaderLabels(["DEFEITO / SINTOMA", "CAUSA PROVÁVEL", "OCORRÊNCIAS", "ATUALIZADO"])
        fault_table.verticalHeader().setVisible(False)
        fault_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        fault_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        fault_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        fault_table.setAlternatingRowColors(True)
        fault_table.setShowGrid(False)
        fault_table.setWordWrap(False)
        fault_table.verticalHeader().setDefaultSectionSize(46)
        fault_table.horizontalHeader().setMinimumHeight(38)
        fault_table.horizontalHeader().setHighlightSections(False)
        fault_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        fault_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        fault_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        fault_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        fault_table.setMinimumHeight(210)
        fault_table.setToolTip("Selecione um defeito para ver o procedimento completo abaixo")
        for row, fault in enumerate(machine.faults):
            fault_table.insertRow(row)
            symptom_preview = (fault.symptom or "").replace("\n", " ")
            if len(symptom_preview) > 76: symptom_preview = symptom_preview[:73] + "..."
            cause_preview = (fault.probable_cause or "—").replace("\n", " ")
            if len(cause_preview) > 68: cause_preview = cause_preview[:65] + "..."
            values = (
                f"{fault.title}  •  {symptom_preview}" if symptom_preview else fault.title,
                cause_preview,
                str(fault.occurrences or 1),
                fault.updated_at.strftime("%d/%m/%Y"),
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, fault.id)
                if col == 0:
                    font = item.font(); font.setBold(True); item.setFont(font)
                    item.setForeground(QColor("#0F172A"))
                elif col == 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    font = item.font(); font.setBold(True); item.setFont(font)
                    item.setForeground(QColor("#0F766E"))
                    item.setBackground(QColor("#F0FDFA"))
                elif col == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setForeground(QColor("#64748B"))
                else:
                    item.setForeground(QColor("#475569"))
                fault_table.setItem(row, col, item)
        fl.addWidget(fault_table)

        fault_detail = QFrame(); fault_detail.setObjectName("faultDetailCard")
        fd = QVBoxLayout(fault_detail); fd.setContentsMargins(16, 14, 16, 14); fd.setSpacing(7)
        fault_detail_title = QLabel("Procedimento de correção"); fault_detail_title.setObjectName("faultDetailTitle")
        fault_hint = QLabel("Selecione um defeito na tabela para visualizar sintoma, causa provável e solução conhecida.")
        fault_hint.setObjectName("faultHint"); fault_hint.setWordWrap(True)
        fault_detail_body = QLabel(""); fault_detail_body.setObjectName("faultDetailBody"); fault_detail_body.setWordWrap(True); fault_detail_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        fd.addWidget(fault_detail_title); fd.addWidget(fault_hint); fd.addWidget(fault_detail_body)
        fl.addWidget(fault_detail)

        def update_fault_detail():
            fid = self._selected_table_id(fault_table)
            fault = self.session.get(MachineFault, fid) if fid else None
            if not fault:
                fault_detail_title.setText("Procedimento de correção")
                fault_hint.setText("Selecione um defeito na tabela para visualizar sintoma, causa provável e solução conhecida.")
                fault_detail_body.setText("")
                return
            fault_detail_title.setText(fault.title)
            fault_hint.setText(f"{int(fault.occurrences or 1)} ocorrência(s) registrada(s) • atualizado em {fault.updated_at.strftime('%d/%m/%Y')}")
            cause = fault.probable_cause or "Não informada"
            notes = fault.notes or "—"
            fault_detail_body.setText(
                f"SINTOMA\n{fault.symptom or '—'}\n\n"
                f"CAUSA PROVÁVEL\n{cause}\n\n"
                f"PROCEDIMENTO DE CORREÇÃO\n{fault.solution or '—'}\n\n"
                f"OBSERVAÇÕES\n{notes}"
            )
        fault_table.itemSelectionChanged.connect(update_fault_detail)
        fault_table.cellDoubleClicked.connect(lambda *_: self._edit_machine_fault(fault_table))

        fault_actions = QHBoxLayout(); fault_actions.addStretch()
        plus_one = QPushButton("+1 ocorrência"); plus_one.setObjectName("btnSecondary")
        edit_fault = QPushButton("Editar"); edit_fault.setObjectName("btnSecondary")
        remove_fault = QPushButton("Excluir"); remove_fault.setObjectName("btnDanger")
        fault_actions.addWidget(plus_one); fault_actions.addWidget(edit_fault); fault_actions.addWidget(remove_fault)
        fl.addLayout(fault_actions)
        add_fault.clicked.connect(self._add_machine_fault)
        plus_one.clicked.connect(lambda: self._increment_machine_fault(fault_table))
        edit_fault.clicked.connect(lambda: self._edit_machine_fault(fault_table))
        remove_fault.clicked.connect(lambda: self._remove_machine_fault(fault_table))
        tabs.addTab(faults, "Defeitos Recorrentes")

        self.details_placeholder.setVisible(False)
        self.details_widget.setVisible(True)

    @staticmethod
    def _selected_table_id(table):
        rows = table.selectionModel().selectedRows() if table.selectionModel() else []
        if not rows:
            return None
        item = table.item(rows[0].row(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _add_machine_document(self):
        machine = self.current_machine
        if machine is None:
            return
        dialog = MachineDocumentDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        title, source, notes = dialog.values()
        try:
            stored = _copy_machine_document(source, machine.id)
            doc = MachineDocument(machine_id=machine.id, title=title, file_path=stored,
                                  original_name=Path(source).name, notes=notes or None)
            self.session.add(doc); self.session.commit()
            self.show_machine_details(machine)
            self.show_status(f"Documento '{title}' adicionado ao dossiê.", "success")
        except Exception as exc:
            self.session.rollback(); logger.exception("Erro ao anexar documento da máquina")
            QMessageBox.critical(self, "Documento", f"Não foi possível adicionar o documento:\n{exc}")

    def _open_machine_document(self, table):
        doc_id = self._selected_table_id(table)
        if not doc_id:
            QMessageBox.information(self, "Documento", "Selecione um documento para abrir."); return
        doc = self.session.get(MachineDocument, int(doc_id))
        real = _machine_file_path(doc.file_path) if doc else None
        if not real:
            QMessageBox.warning(self, "Documento", "O arquivo não foi encontrado no dossiê."); return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(real)))

    def _remove_machine_document(self, table):
        doc_id = self._selected_table_id(table)
        if not doc_id:
            return
        doc = self.session.get(MachineDocument, int(doc_id))
        if not doc:
            return
        if QMessageBox.question(self, "Remover documento", f"Remover '{doc.title}' do dossiê?\n\nO arquivo físico será mantido na pasta do projeto.") != QMessageBox.StandardButton.Yes:
            return
        self.session.delete(doc); self.session.commit(); self.show_machine_details(self.current_machine)

    def _add_machine_fault(self):
        machine = self.current_machine
        if machine is None:
            return
        dialog = MachineFaultDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = dialog.values()
        try:
            fault = MachineFault(machine_id=machine.id, **data)
            self.session.add(fault); self.session.commit(); self.show_machine_details(machine)
            self.show_status(f"Defeito '{fault.title}' registrado.", "success")
        except Exception as exc:
            self.session.rollback(); QMessageBox.critical(self, "Defeito recorrente", str(exc))

    def _edit_machine_fault(self, table):
        fid = self._selected_table_id(table)
        if not fid:
            QMessageBox.information(self, "Defeito recorrente", "Selecione um defeito para editar."); return
        fault = self.session.get(MachineFault, int(fid))
        if not fault:
            return
        dialog = MachineFaultDialog(self, fault)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        for key, value in dialog.values().items():
            setattr(fault, key, value)
        fault.updated_at = datetime.utcnow()
        self.session.commit(); self.show_machine_details(self.current_machine)

    def _increment_machine_fault(self, table):
        fid = self._selected_table_id(table)
        if not fid:
            QMessageBox.information(self, "Ocorrência", "Selecione um defeito."); return
        fault = self.session.get(MachineFault, int(fid))
        if fault:
            fault.occurrences = int(fault.occurrences or 0) + 1
            fault.updated_at = datetime.utcnow(); self.session.commit(); self.show_machine_details(self.current_machine)

    def _remove_machine_fault(self, table):
        fid = self._selected_table_id(table)
        if not fid:
            return
        fault = self.session.get(MachineFault, int(fid))
        if not fault:
            return
        if QMessageBox.question(self, "Excluir defeito", f"Excluir '{fault.title}' da base de conhecimento?") != QMessageBox.StandardButton.Yes:
            return
        self.session.delete(fault); self.session.commit(); self.show_machine_details(self.current_machine)

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
        lines.append("Use \"Cadastrar nova placa\" para adicionar placas a este equipamento.")
        return "\n".join(lines)

    def _last_runs_map(self, boards):
        result = {}
        for board in boards:
            latest = (
                self.session.query(TestRun)
                .filter(TestRun.board_id == board.id)
                .order_by(TestRun.start_time.desc())
                .first()
            )
            result[board.id] = latest
        return result

    def _refresh_filter_options(self, machines, boards):
        if not hasattr(self, "filter_bar"):
            return
        current_machine = self.filter_bar.machine.currentData()
        current_type = self.filter_bar.board_type.currentData()

        self.filter_bar.machine.blockSignals(True)
        self.filter_bar.machine.clear(); self.filter_bar.machine.addItem("Todos os equipamentos", None)
        for m in machines:
            self.filter_bar.machine.addItem(m.name, m.id)
        idx = self.filter_bar.machine.findData(current_machine)
        self.filter_bar.machine.setCurrentIndex(idx if idx >= 0 else 0)
        self.filter_bar.machine.blockSignals(False)

        categories = sorted({(b.board_model.category or "").strip() for b in boards if b.board_model and (b.board_model.category or "").strip()})
        self.filter_bar.board_type.blockSignals(True)
        self.filter_bar.board_type.clear(); self.filter_bar.board_type.addItem("Todos os tipos", None)
        for category in categories:
            self.filter_bar.board_type.addItem(category, category)
        idx = self.filter_bar.board_type.findData(current_type)
        self.filter_bar.board_type.setCurrentIndex(idx if idx >= 0 else 0)
        self.filter_bar.board_type.blockSignals(False)
        self.filter_bar.refresh_visual_states()

    def refresh_boards(self, select_board_id=None, select_machine_id=None):
        """Recarrega inventário, métricas e filtros sem alterar a lógica do banco."""
        try:
            machines = self.session.query(Machine).order_by(Machine.name).all()
            boards = self.session.query(BoardUnit).order_by(BoardUnit.name).all()
            self._catalog_machines = machines
            self._catalog_boards = boards
            self._last_runs = self._last_runs_map(boards)

            if select_board_id is not None:
                board = self.session.get(BoardUnit, int(select_board_id))
                if board:
                    self.current_board = board
                    self.current_machine = board.machine
                    if board.machine_id:
                        self._expanded_machine_ids.add(int(board.machine_id))
            elif select_machine_id is not None:
                self.current_machine = self.session.get(Machine, int(select_machine_id))
                self.current_board = None
                if self.current_machine:
                    self._expanded_machine_ids.add(int(self.current_machine.id))

            self._refresh_filter_options(machines, boards)

            active = sum(1 for b in boards if b.is_active)
            inactive = len(boards) - active
            today_start = datetime.combine(datetime.now().date(), time.min)
            tests_today = self.session.query(TestRun).filter(TestRun.start_time >= today_start).count()
            self.stat_machines.setText(str(len(machines)))
            self.stat_boards.setText(str(len(boards)))
            self.stat_active_split.setText(f"{active} / {inactive}")
            self.stat_tests_today.setText(str(tests_today))
            self.catalog_subtitle.setText(f"{len(machines)} equipamento(s) • {len(boards)} placa(s) cadastrada(s)")

            self._rebuild_catalog()
            if self.current_board:
                self.show_board_details()
            elif self.current_machine:
                self.show_machine_details(self.current_machine)
            elif not machines:
                self.hide_board_details()
            self.show_status(f"Carregadas {len(boards)} placas em {len(machines)} equipamentos")
        except Exception as exc:
            logger.exception("Erro ao carregar catálogo")
            self.show_error_state(str(exc))

    def _filtered_catalog(self):
        machines = list(getattr(self, "_catalog_machines", []))
        boards = list(getattr(self, "_catalog_boards", []))
        search = self.filter_bar.search.text().strip().lower() if hasattr(self, "filter_bar") else ""
        status = self.filter_bar.status.currentData() if hasattr(self, "filter_bar") else "all"
        machine_filter = self.filter_bar.machine.currentData() if hasattr(self, "filter_bar") else None
        type_filter = self.filter_bar.board_type.currentData() if hasattr(self, "filter_bar") else None
        sort_mode = self.filter_bar.sort.currentData() if hasattr(self, "filter_bar") else "name"

        def board_matches(board):
            if status == "active" and not board.is_active: return False
            if status == "inactive" and board.is_active: return False
            if machine_filter is not None and board.machine_id != machine_filter: return False
            category = (board.board_model.category or "") if board.board_model else ""
            if type_filter is not None and category != type_filter: return False
            if search:
                hay = " ".join([
                    board.name or "", board.model or "", board.version or "", board.serial_number or "",
                    board.machine.name if board.machine else "",
                    board.machine.code if board.machine and board.machine.code else "",
                    category,
                ]).lower()
                if search not in hay:
                    return False
            return True

        filtered_boards = [b for b in boards if board_matches(b)]
        boards_by_machine = {}
        for b in filtered_boards:
            boards_by_machine.setdefault(b.machine_id, []).append(b)

        machine_rows = []
        for m in machines:
            if machine_filter is not None and m.id != machine_filter:
                continue
            machine_hay = f"{m.name or ''} {m.code or ''} {m.description or ''}".lower()
            machine_direct_match = bool(search and search in machine_hay)
            child_boards = boards_by_machine.get(m.id, [])
            # Se a máquina casa diretamente com a busca, mostra também suas placas que respeitam os demais filtros.
            if machine_direct_match and search:
                child_boards = [b for b in boards if b.machine_id == m.id and
                                (status == "all" or (status == "active" and b.is_active) or (status == "inactive" and not b.is_active)) and
                                (type_filter is None or ((b.board_model.category or "") if b.board_model else "") == type_filter)]
            if not search and machine_filter is None and status == "all" and type_filter is None:
                child_boards = [b for b in boards if b.machine_id == m.id]
            if child_boards or machine_direct_match or (not search and status == "all" and type_filter is None):
                machine_rows.append((m, child_boards))

        # Grupo virtual para placas sem máquina
        orphan_boards = boards_by_machine.get(None, [])
        if orphan_boards:
            virtual = None
            machine_rows.append((virtual, orphan_boards))

        if sort_mode == "recent":
            def recency(row):
                _, bs = row
                stamps = [self._last_runs.get(b.id).start_time for b in bs if self._last_runs.get(b.id) and self._last_runs.get(b.id).start_time]
                return max(stamps) if stamps else datetime.min
            machine_rows.sort(key=recency, reverse=True)
        elif sort_mode == "status":
            machine_rows.sort(key=lambda row: (sum(1 for b in row[1] if not b.is_active), (row[0].name if row[0] else "ZZZ").lower()))
        else:
            machine_rows.sort(key=lambda row: (row[0].name.lower() if row[0] else "zzzzzz"))

        return machine_rows

    def _clear_catalog_layout(self):
        while self.catalog_layout.count():
            item = self.catalog_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._machine_cards = {}
        self._board_cards = {}

    def _rebuild_catalog(self):
        """Reconstrói os widgets somente quando os DADOS do inventário mudam.

        Pesquisa, filtros e ordenação não passam mais por este método. Eles
        apenas mostram/ocultam e reordenam widgets já existentes, evitando o
        flash percebido no Windows a cada atualização visual da lista.
        """
        if not hasattr(self, "catalog_scroll"):
            return

        machines = list(getattr(self, "_catalog_machines", []))
        boards = list(getattr(self, "_catalog_boards", []))
        boards_by_machine = {}
        for board in boards:
            boards_by_machine.setdefault(board.machine_id, []).append(board)

        old_scroll_value = self.catalog_scroll.verticalScrollBar().value()
        self.catalog_host.setUpdatesEnabled(False)
        try:
            # Remove somente em uma atualização real de dados (CRUD/sincronização).
            while self.catalog_layout.count():
                item = self.catalog_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()

            self._machine_cards = {}
            self._board_cards = {}
            self._orphan_board_cards = {}
            self._orphan_section = None

            row_index = 0
            for machine in machines:
                machine_boards = boards_by_machine.get(machine.id, [])
                card = MachineCatalogCard(
                    machine,
                    machine_boards,
                    self._last_runs,
                    expanded=(machine.id in self._expanded_machine_ids),
                    compact=False,
                    selected_machine=(
                        self.current_machine is not None
                        and self.current_board is None
                        and self.current_machine.id == machine.id
                    ),
                    selected_board_id=(self.current_board.id if self.current_board else None),
                )
                card.machineClicked.connect(self._select_machine_by_id)
                card.expandedChanged.connect(self._machine_expanded_changed)
                card.editRequested.connect(self._edit_machine_by_id)
                card.deleteRequested.connect(self._delete_machine_by_id)
                card.boardClicked.connect(self._select_board_by_id)
                card.boardDoubleClicked.connect(self._open_board_by_id)
                card.boardDetailsRequested.connect(self._open_board_by_id)
                card.boardTestRequested.connect(self._test_board_by_id)
                card.boardMoveRequested.connect(self._move_board_by_id)
                card.boardDeleteRequested.connect(self._delete_board_by_id)

                self._machine_cards[int(machine.id)] = card
                self._board_cards.update(card.board_cards)
                self.catalog_layout.addWidget(card, row_index, 0)
                row_index += 1

            orphan_boards = boards_by_machine.get(None, [])
            if orphan_boards:
                section = QFrame()
                section.setObjectName("orphanSection")
                section_layout = QVBoxLayout(section)
                section_layout.setContentsMargins(14, 14, 14, 14)
                section_layout.setSpacing(10)

                title_row = QHBoxLayout()
                title_row.setContentsMargins(0, 0, 0, 0)
                title_row.setSpacing(8)
                title = QLabel("PLACAS SEM EQUIPAMENTO")
                title.setObjectName("orphanSectionTitle")
                self._orphan_subtitle = QLabel(f"{len(orphan_boards)} placa(s) aguardando vínculo")
                self._orphan_subtitle.setObjectName("orphanSectionMeta")
                title_row.addWidget(title)
                title_row.addWidget(self._orphan_subtitle)
                title_row.addStretch(1)
                section_layout.addLayout(title_row)

                orphan_host = QWidget()
                orphan_list = QVBoxLayout(orphan_host)
                orphan_list.setContentsMargins(0, 0, 0, 0)
                orphan_list.setSpacing(7)
                for board in orphan_boards:
                    bc = BoardCatalogCard(
                        board,
                        self._last_runs.get(board.id),
                        selected=bool(self.current_board and self.current_board.id == board.id),
                    )
                    self._wire_board_card(bc)
                    self._orphan_board_cards[int(board.id)] = bc
                    self._board_cards[int(board.id)] = bc
                    orphan_list.addWidget(bc)

                section_layout.addWidget(orphan_host)
                self._orphan_section = section
                self.catalog_layout.addWidget(section, row_index, 0)

            self._last_catalog_columns = 1
        finally:
            self.catalog_host.setUpdatesEnabled(True)

        # Aplica pesquisa/filtros sem recriar nada.
        self._apply_catalog_filter_in_place()
        bar = self.catalog_scroll.verticalScrollBar()
        bar.setValue(min(old_scroll_value, bar.maximum()))

    def _apply_catalog_filter_in_place(self):
        """Aplica busca, filtros e ordenação reaproveitando os cards existentes."""
        if not hasattr(self, "catalog_scroll"):
            return

        rows = self._filtered_catalog()
        machine_rows = [(machine, boards) for machine, boards in rows if machine is not None]
        orphan_boards = []
        for machine, boards in rows:
            if machine is None:
                orphan_boards.extend(boards)

        total_boards = sum(len(bs) for _, bs in machine_rows) + len(orphan_boards)
        visible_groups = len(machine_rows) + (1 if orphan_boards else 0)
        self.catalog_result_label.setText(
            f"{visible_groups} grupo(s) • {total_boards} placa(s) visível(is)"
        )

        no_data = (
            len(getattr(self, "_catalog_machines", [])) == 0
            and len(getattr(self, "_catalog_boards", [])) == 0
        )
        if not rows:
            self.catalog_scroll.setVisible(False)
            self.catalog_empty.setVisible(True)
            self.empty_title.setText(
                "Nenhum equipamento cadastrado" if no_data else "Nenhum resultado encontrado"
            )
            self.empty_text.setText(
                "Cadastre o primeiro equipamento para começar a organizar suas placas."
                if no_data else
                "Ajuste a busca ou os filtros para visualizar outros itens."
            )
            return

        self.catalog_empty.setVisible(False)
        self.catalog_scroll.setVisible(True)

        visible_machine_ids = {int(machine.id) for machine, _ in machine_rows}
        visible_orphan_ids = {int(board.id) for board in orphan_boards}
        search_active = bool(self.filter_bar.search.text().strip())

        self.catalog_host.setUpdatesEnabled(False)
        try:
            # Retira os itens do layout, mas NÃO destrói widgets.
            while self.catalog_layout.count():
                self.catalog_layout.takeAt(0)

            row_index = 0
            for machine, boards in machine_rows:
                card = self._machine_cards.get(int(machine.id))
                if card is None:
                    continue
                card.setVisible(True)
                card.apply_board_filter(
                    [board.id for board in boards],
                    force_expand=search_active,
                )
                self.catalog_layout.addWidget(card, row_index, 0)
                row_index += 1

            for mid, card in self._machine_cards.items():
                if mid not in visible_machine_ids:
                    card.setVisible(False)

            if self._orphan_section is not None:
                for bid, card in self._orphan_board_cards.items():
                    card.setVisible(bid in visible_orphan_ids)
                self._orphan_section.setVisible(bool(visible_orphan_ids))
                if hasattr(self, "_orphan_subtitle"):
                    self._orphan_subtitle.setText(
                        f"{len(visible_orphan_ids)} placa(s) aguardando vínculo"
                    )
                if visible_orphan_ids:
                    self.catalog_layout.addWidget(self._orphan_section, row_index, 0)
        finally:
            self.catalog_host.setUpdatesEnabled(True)
            self.catalog_host.update()

    def _wire_board_card(self, card):
        card.clicked.connect(self._select_board_by_id)
        card.doubleClicked.connect(self._open_board_by_id)
        card.detailsRequested.connect(self._open_board_by_id)
        card.testRequested.connect(self._test_board_by_id)
        card.moveRequested.connect(self._move_board_by_id)
        card.deleteRequested.connect(self._delete_board_by_id)

    def _machine_expanded_changed(self, machine_id, expanded):
        if expanded:
            self._expanded_machine_ids.add(int(machine_id))
        else:
            self._expanded_machine_ids.discard(int(machine_id))
        # No modo Grid, expandir muda o card de compacto (meia largura) para
        # completo (largura inteira). Reconstruir o catálogo torna a mudança
        # visual imediata e faz os botões Grid/Lista terem comportamento real.
        if self.catalog_view_mode == "grid":
            self._rebuild_catalog()

    def _apply_catalog_selection(self):
        selected_machine = self.current_machine.id if self.current_machine and self.current_board is None else None
        selected_board = self.current_board.id if self.current_board else None
        for mid, card in self._machine_cards.items(): card.set_selected(mid == selected_machine)
        for bid, card in self._board_cards.items(): card.set_selected(bid == selected_board)

    def _select_machine_by_id(self, machine_id):
        machine = self.session.get(Machine, int(machine_id))
        if not machine: return
        self.current_machine = machine; self.current_board = None
        self.show_machine_details(machine); self._apply_catalog_selection()

    def _select_board_by_id(self, board_id):
        board = self.session.get(BoardUnit, int(board_id))
        if not board: return
        self.current_board = board; self.current_machine = board.machine
        self.show_board_details(); self._apply_catalog_selection()

    def _open_board_by_id(self, board_id):
        self._select_board_by_id(board_id)
        self.board_details_requested.emit(int(board_id))

    def _test_board_by_id(self, board_id):
        self._select_board_by_id(board_id)
        self.import_board()

    def _move_board_by_id(self, board_id):
        self._select_board_by_id(board_id); self.move_board()

    def _delete_board_by_id(self, board_id):
        self._select_board_by_id(board_id); self.delete_board()

    def _edit_machine_by_id(self, machine_id):
        self._select_machine_by_id(machine_id); self.edit_machine()

    def _delete_machine_by_id(self, machine_id):
        self._select_machine_by_id(machine_id); self.delete_machine()

    def filter_boards(self):
        # Busca/filtros agora são aplicados sobre os widgets existentes.
        # Nada é destruído/recriado a cada tecla.
        self._apply_catalog_filter_in_place()

    def _update_selection_actions(self, kind):
        # Ações agora ficam nos próprios cards/menu contextual.
        return

    def on_board_selected(self):
        # Mantido por compatibilidade com versões antigas que chamavam este método.
        return

    def show_loading_state(self):
        """Skeleton discreto para quando o catálogo passar a carregar de forma assíncrona."""
        if not hasattr(self, "catalog_layout"):
            return
        self.catalog_empty.setVisible(False); self.catalog_scroll.setVisible(True)
        self._clear_catalog_layout()
        columns = max(1, self._catalog_columns())
        for i in range(columns * 2):
            card = QFrame(); card.setObjectName("skeletonCard"); card.setMinimumHeight(118)
            box = QVBoxLayout(card); box.setContentsMargins(16, 16, 16, 16); box.setSpacing(9)
            for width in (170, 230, 120):
                line = QFrame(); line.setObjectName("skeletonLine"); line.setFixedSize(width, 12)
                box.addWidget(line)
            row, col = divmod(i, columns)
            self.catalog_layout.addWidget(card, row, col)

    def show_error_state(self, message):
        if not hasattr(self, "catalog_empty"): return
        self.catalog_scroll.setVisible(False); self.catalog_empty.setVisible(True)
        self.empty_title.setText("Não foi possível carregar o inventário")
        self.empty_text.setText(str(message) or "Tente novamente.")

    def _sync_equipment_dossier(self, machine, documents, faults):
        """Sincroniza documentos e defeitos do formulário com o dossiê persistido."""
        existing_docs = {d.id: d for d in self.session.query(MachineDocument).filter(MachineDocument.machine_id == machine.id).all()}
        keep_doc_ids = {int(d["id"]) for d in documents if d.get("id")}
        for doc_id, obj in existing_docs.items():
            if doc_id not in keep_doc_ids:
                self.session.delete(obj)
        for data in documents:
            if data.get("id"):
                obj = existing_docs.get(int(data["id"]))
                if obj:
                    obj.title = data.get("title") or obj.title
                    obj.notes = data.get("notes") or None
                continue
            source = data.get("source_path")
            if not source:
                continue
            stored = _copy_machine_document(source, machine.id)
            self.session.add(MachineDocument(
                machine_id=machine.id,
                title=data.get("title") or Path(source).stem,
                file_path=stored,
                original_name=data.get("original_name") or Path(source).name,
                notes=data.get("notes") or None,
            ))

        existing_faults = {f.id: f for f in self.session.query(MachineFault).filter(MachineFault.machine_id == machine.id).all()}
        keep_fault_ids = {int(f["id"]) for f in faults if f.get("id")}
        for fault_id, obj in existing_faults.items():
            if fault_id not in keep_fault_ids:
                self.session.delete(obj)
        for data in faults:
            payload = {k: data.get(k) for k in ("title", "symptom", "probable_cause", "solution", "occurrences", "notes")}
            if data.get("id"):
                obj = existing_faults.get(int(data["id"]))
                if obj:
                    for key, value in payload.items():
                        setattr(obj, key, value)
            else:
                self.session.add(MachineFault(machine_id=machine.id, **payload))

    def add_machine(self):
        """Cadastra uma nova máquina."""
        dialog = MachineDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, code, description, image, documents, faults = dialog.values()

        if self._machine_name_taken(name):
            QMessageBox.warning(self, "Equipamento duplicado", f"Já existe um equipamento chamado '{name}'.")
            return

        try:
            image_path = import_image_to_project(image) if image else None
            machine = Machine(
                name=name, code=code or None, description=description or None, image_path=image_path
            )
            self.session.add(machine)
            self.session.flush()
            self._sync_equipment_dossier(machine, documents, faults)
            self.session.commit()
            log_user_action(self.current_user, "machine_created", {"machine_name": name, "code": code})
            self.refresh_boards(select_machine_id=machine.id)
            self.show_status(f"Equipamento '{name}' cadastrado. Agora cadastre as placas dele.", "success")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Erro ao cadastrar equipamento: {e}")
            self.show_status(f"Erro ao cadastrar equipamento: {e}", "error")

    def edit_machine(self):
        """Edita a máquina selecionada (ou a máquina da placa selecionada)."""
        machine = self.current_machine
        if machine is None:
            return

        dialog = MachineDialog(self, machine)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, code, description, image, documents, faults = dialog.values()

        if self._machine_name_taken(name, ignore_id=machine.id):
            QMessageBox.warning(self, "Equipamento duplicado", f"Já existe um equipamento chamado '{name}'.")
            return

        try:
            machine.name = name
            machine.code = code or None
            machine.description = description or None
            if image != machine.image_path:  # trocou ou removeu a imagem
                machine.image_path = import_image_to_project(image) if image else None
            self._sync_equipment_dossier(machine, documents, faults)
            self.session.commit()
            log_user_action(self.current_user, "machine_updated", {"machine_name": name})
            self.refresh_boards()
            self.show_status(f"Equipamento '{name}' atualizado", "success")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Erro ao editar equipamento: {e}")
            self.show_status(f"Erro ao editar equipamento: {e}", "error")

    def delete_machine(self):
        """Exclui a máquina. As placas NÃO são apagadas: passam para 'Sem máquina'."""
        machine = self.current_machine
        if machine is None:
            return

        count = len(machine.boards)
        text = f"Excluir o equipamento '{machine.name}'?\n\n"
        if count:
            text += f"• As {count} placa(s) dele NÃO serão apagadas: ficarão em 'Sem equipamento'.\n"
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
            self.show_status(f"Equipamento '{name}' excluído", "success")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Erro ao excluir equipamento: {e}")
            QMessageBox.critical(self, "Erro", f"Erro ao excluir equipamento:\n{e}")

    def move_board(self):
        """Move a placa selecionada para outra máquina."""
        board = self.current_board
        if board is None:
            return

        machines = self.session.query(Machine).order_by(Machine.name).all()
        if not machines:
            QMessageBox.information(
                self, "Nenhum equipamento",
                "Ainda não há equipamentos cadastrados.\nUse o botão '+ Novo Equipamento' primeiro.",
            )
            return

        options = ["— Sem equipamento —"] + [self._machine_option_text(m) for m in machines]
        current_index = 0
        for i, m in enumerate(machines, start=1):
            if m.id == board.machine_id:
                current_index = i
                break

        choice, ok = QInputDialog.getItem(
            self, "Mover placa", f"Mover '{board.name}' para qual equipamento?",
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
            destino = new_machine.name if new_machine else "Sem equipamento"
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
        machine_name = board.machine.name if board.machine else "Sem equipamento"
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
                
    def _on_board_double_clicked(self, item, _column=0):
        """Compatibilidade com a antiga árvore: abre detalhes quando recebe um nó de placa."""
        data = item.data(0, NODE_ROLE) if item is not None else None
        if data and data[0] == "board":
            self._open_board_by_id(int(data[1]))

    def view_board_details(self, *_args):
        """Abre /placas/:id/detalhes no conteúdo principal.

        O antigo diálogo permanece no arquivo por compatibilidade, mas deixou
        de ser o ponto de acesso principal.
        """
        if not self.current_board:
            return
        self.board_details_requested.emit(int(self.current_board.id))
        
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