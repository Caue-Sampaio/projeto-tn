# ui/plan_editor.py
from PyQt6 import QtGui
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QDialog,
    QFormLayout, QLineEdit, QComboBox, QDialogButtonBox,
    QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QHBoxLayout, QSpinBox, QTextEdit, QTabWidget, QGroupBox,
    QCheckBox, QToolButton, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer  # Adicionei QTimer aqui
from PyQt6.QtGui import QIcon, QFont
from db.models import TestStep, TestPoint, TestPlan, OscilloscopeReference
from engine.logger import log_user_action
import logging

logger = logging.getLogger(__name__)

class StepForm(QDialog):
    """Etapa do roteiro: ponto + ordem + instrução.

    Os valores corretos não pertencem ao plano. Eles são lidos da aba
    Referências para evitar cadastro duplicado.
    """

    def __init__(self, session, board, step=None):
        super().__init__()
        self.session = session
        self.board = board
        self.step = step
        self.is_edit = step is not None
        self.setWindowTitle("Editar etapa" if self.is_edit else "Nova etapa")
        self.setMinimumWidth(560)
        self.setup_ui()
        self.apply_styles()
        if self.is_edit:
            self.load_step_data()
        else:
            self._update_reference_info()

    def setup_ui(self):
        self.setObjectName("stepDialog")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("stepHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(22, 16, 22, 16)
        header_layout.setSpacing(3)
        title = QLabel("Editar etapa do diagnóstico" if self.is_edit else "Nova etapa do diagnóstico")
        title.setObjectName("stepTitle")
        subtitle = QLabel(
            "O plano define somente a ordem e a instrução. Os valores corretos e tolerâncias vêm de Referências."
        )
        subtitle.setObjectName("stepSubtitle")
        subtitle.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        body = QWidget()
        body.setObjectName("stepBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(22, 20, 22, 16)
        body_layout.setSpacing(14)

        form_card = QFrame()
        form_card.setObjectName("formCard")
        form_layout = QFormLayout(form_card)
        form_layout.setContentsMargins(18, 18, 18, 18)
        form_layout.setHorizontalSpacing(14)
        form_layout.setVerticalSpacing(12)

        self.point_select = QComboBox()
        points = (
            self.session.query(TestPoint)
            .filter_by(board_id=self.board.id)
            .order_by(TestPoint.refdes)
            .all()
        )
        self.point_select.addItem("Selecione o ponto...", None)
        for point in points:
            self.point_select.addItem(f"{point.refdes}  •  X:{point.x}  Y:{point.y}", point)
        self.point_select.currentIndexChanged.connect(self._update_reference_info)
        form_layout.addRow("Ponto *", self.point_select)

        self.reference_label = QLabel("Referência: —")
        self.reference_label.setObjectName("referenceInfo")
        self.reference_label.setWordWrap(True)
        form_layout.addRow("Valores corretos", self.reference_label)

        self.order_spinbox = QSpinBox()
        self.order_spinbox.setRange(1, 1000)
        self.order_spinbox.setValue(1)
        self.order_spinbox.setMinimumWidth(90)
        form_layout.addRow("Ordem", self.order_spinbox)

        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Ex: Verificar PWM do gate")
        self.set_field_style(self.description_input)
        form_layout.addRow("Instrução *", self.description_input)

        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("Ex: usar ponta x10, medir em relação ao GND... (opcional)")
        self.notes_input.setMaximumHeight(90)
        form_layout.addRow("Observações", self.notes_input)

        body_layout.addWidget(form_card)
        self.validation_label = QLabel("")
        self.validation_label.setObjectName("validationText")
        self.validation_label.setWordWrap(True)
        body_layout.addWidget(self.validation_label)
        root.addWidget(body)

        footer = QFrame()
        footer.setObjectName("stepFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(22, 12, 22, 16)
        footer_layout.addStretch()
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok_button.setText("Salvar etapa" if self.is_edit else "Adicionar etapa")
        ok_button.setObjectName("primaryDialogButton")
        cancel_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_button.setText("Cancelar")
        cancel_button.setObjectName("secondaryDialogButton")
        footer_layout.addWidget(self.buttons)
        root.addWidget(footer)

    def _reference_for_point(self, point):
        if point is None:
            return None
        return (
            self.session.query(OscilloscopeReference)
            .filter_by(board_model_id=self.board.model_id, refdes=point.refdes)
            .first()
        )

    @staticmethod
    def _fmt(value, unit):
        if value is None:
            return None
        value = float(value)
        if unit == "Hz":
            if abs(value) >= 1_000_000:
                return f"{value/1_000_000:.3g} MHz"
            if abs(value) >= 1_000:
                return f"{value/1_000:.3g} kHz"
        return f"{value:.4g} {unit}".strip()

    def _update_reference_info(self, *_args):
        point = self.point_select.currentData()
        reference = self._reference_for_point(point)
        if reference is None:
            self.reference_label.setText("Sem referência cadastrada para este ponto")
            self.reference_label.setStyleSheet("color:#D97706;font-weight:600;")
            return
        parts = []
        if reference.vpp_v is not None:
            parts.append(f"Vpp {self._fmt(reference.vpp_v, 'V')}")
        if reference.vrms_v is not None:
            parts.append(f"Vrms {self._fmt(reference.vrms_v, 'V')}")
        if reference.frequency_hz is not None:
            parts.append(f"F {self._fmt(reference.frequency_hz, 'Hz')}")
        parts.append(f"CH{reference.channel or 1}")
        self.reference_label.setText(" • ".join(parts))
        self.reference_label.setStyleSheet("color:#0F766E;font-weight:600;")

    def apply_styles(self):
        self.setStyleSheet("""
            QDialog#stepDialog { background-color: #F4F7F9; color: #0F172A; }
            QFrame#stepHeader { background-color: #0F172A; }
            QLabel#stepTitle { color:#FFFFFF; font-size:18px; font-weight:700; }
            QLabel#stepSubtitle { color:#CBD5E1; font-size:11px; }
            QWidget#stepBody { background-color:#F4F7F9; }
            QFrame#formCard { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:10px; }
            QFrame#stepFooter { background:#FFFFFF; border-top:1px solid #E2E8F0; }
            QLabel { color:#334155; font-size:12px; }
            QLabel#validationText { color:#DC2626; font-size:11px; font-weight:600; }
            QLabel#referenceInfo { padding:7px 4px; }
            QLineEdit, QComboBox, QSpinBox, QTextEdit {
                background:#FFFFFF; color:#0F172A; border:1px solid #CBD5E1;
                border-radius:8px; padding:7px 10px; font-size:13px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus { border:1px solid #0284C7; }
            QComboBox QAbstractItemView { background:#FFFFFF; color:#0F172A; selection-background-color:#0284C7; }
            QPushButton#primaryDialogButton {
                background:#0F766E; color:#FFFFFF; border:1px solid #0D9488;
                border-radius:8px; padding:8px 16px; font-weight:700; min-width:120px;
            }
            QPushButton#primaryDialogButton:hover { background:#0D9488; }
            QPushButton#secondaryDialogButton {
                background:#F1F5F9; color:#334155; border:1px solid #CBD5E1;
                border-radius:8px; padding:8px 16px; font-weight:600; min-width:90px;
            }
        """)

    def set_field_style(self, field):
        if isinstance(field, QLineEdit):
            field.setProperty("error", "false")

    def load_step_data(self):
        if not self.step:
            return
        self.description_input.setText(self.step.description or "")
        self.order_spinbox.setValue(self.step.order_index or 1)
        self.notes_input.setPlainText(self.step.notes or "")
        if self.step.test_point:
            for i in range(self.point_select.count()):
                point = self.point_select.itemData(i)
                if point is not None and point.id == self.step.test_point.id:
                    self.point_select.setCurrentIndex(i)
                    break
        self._update_reference_info()

    def validate_and_accept(self):
        errors = []
        if self.point_select.currentData() is None:
            errors.append("Selecione o ponto de teste")
        if not self.description_input.text().strip():
            errors.append("Informe a instrução da etapa")
        if errors:
            self.validation_label.setText(" | ".join(errors))
            return
        self.accept()

    def get_step_data(self):
        return {
            "description": self.description_input.text().strip(),
            "unit": "SCOPE",
            "order_index": self.order_spinbox.value(),
            "desired_value": None,
            "tolerance": None,
            "test_point": self.point_select.currentData(),
            "notes": self.notes_input.toPlainText().strip() or None,
        }


class PlanEditor(QWidget):
    """Editor completo de planos de teste"""
    
    plan_saved = pyqtSignal(object)  # Emite o plano salvo
    
    def __init__(self, session, board, plan=None):
        super().__init__()
        self.session = session
        self.board = board
        self.plan = plan
        self.is_edit = plan is not None
        
        self.setWindowTitle(f"Editor de Plano de Teste - {board.name}")
        self.setMinimumSize(800, 600)

        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        
        self.setup_ui()
        self.apply_styles()
        
        if self.plan:
            self.load_plan_data()
        else:
            self.create_plan()
            
    def setup_ui(self):
        """Monta o editor com foco em etapas, configurações e ação de salvar."""
        self.setObjectName("planEditorRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 14)
        layout.setSpacing(14)

        layout.addWidget(self.create_header())

        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("editorTabs")
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.addTab(self.create_steps_tab(), "Etapas de teste")
        self.tab_widget.addTab(self.create_settings_tab(), "Informações do plano")
        layout.addWidget(self.tab_widget, 1)

        self.status_label = QLabel("Pronto")
        self.status_label.setObjectName("editorStatus")
        layout.addWidget(self.status_label)

    def create_header(self):
        """Cabeçalho compacto, seguindo a mesma identidade do dashboard."""
        header = QFrame()
        header.setObjectName("editorHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)
        self.plan_title = QLabel("Novo Plano de Teste" if not self.is_edit else self.plan.name)
        self.plan_title.setObjectName("editorTitle")
        self.plan_subtitle = QLabel(
            f"Placa: {self.board.name}  •  S/N: {self.board.serial_number}"
        )
        self.plan_subtitle.setObjectName("editorSubtitle")
        info_layout.addWidget(self.plan_title)
        info_layout.addWidget(self.plan_subtitle)
        layout.addLayout(info_layout, 1)

        self.close_button = QPushButton("Fechar")
        self.close_button.setObjectName("headerSecondary")
        self.close_button.setMinimumHeight(36)
        self.close_button.clicked.connect(self.close)

        self.save_button = QPushButton("Salvar plano")
        self.save_button.setObjectName("headerPrimary")
        self.save_button.setMinimumHeight(36)
        self.save_button.clicked.connect(self.save_plan)

        layout.addWidget(self.close_button)
        layout.addWidget(self.save_button)
        return header

    def create_steps_tab(self):
        """Aba principal do editor: ações essenciais + tabela de etapas."""
        widget = QWidget()
        widget.setObjectName("stepsTab")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        toolbar = QFrame()
        toolbar.setObjectName("editorCard")
        controls_layout = QHBoxLayout(toolbar)
        controls_layout.setContentsMargins(14, 12, 14, 12)
        controls_layout.setSpacing(8)

        heading_box = QVBoxLayout()
        heading_box.setSpacing(1)
        heading = QLabel("Sequência de testes")
        heading.setObjectName("sectionTitle")
        hint = QLabel("Defina a ordem dos pontos. Os valores corretos vêm automaticamente de Referências.")
        hint.setObjectName("sectionHint")
        heading_box.addWidget(heading)
        heading_box.addWidget(hint)
        controls_layout.addLayout(heading_box, 1)

        self.add_step_button = QPushButton("Adicionar etapa")
        self.add_step_button.setObjectName("btnPrimary")
        self.add_step_button.setMinimumHeight(36)
        self.add_step_button.clicked.connect(self.add_step)

        self.edit_step_button = QPushButton("Editar")
        self.edit_step_button.setObjectName("btnSecondary")
        self.edit_step_button.setMinimumHeight(36)
        self.edit_step_button.clicked.connect(self.edit_step)
        self.edit_step_button.setEnabled(False)

        self.delete_step_button = QPushButton("Excluir")
        self.delete_step_button.setObjectName("btnDanger")
        self.delete_step_button.setMinimumHeight(36)
        self.delete_step_button.clicked.connect(self.delete_step)
        self.delete_step_button.setEnabled(False)

        # Os controles subir/descer não eram funcionais; foram retirados da UI.
        self.move_up_button = None
        self.move_down_button = None

        controls_layout.addWidget(self.add_step_button)
        controls_layout.addWidget(self.edit_step_button)
        controls_layout.addWidget(self.delete_step_button)
        layout.addWidget(toolbar)

        self.step_table = QTableWidget()
        self.step_table.setObjectName("stepTable")
        self.step_table.setColumnCount(4)
        self.step_table.setHorizontalHeaderLabels([
            "Ordem", "Ponto", "Instrução", "Referência"
        ])
        header = self.step_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.step_table.verticalHeader().setVisible(False)
        self.step_table.setAlternatingRowColors(True)
        self.step_table.setShowGrid(False)
        self.step_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.step_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.step_table.cellClicked.connect(self.on_step_selected)
        self.step_table.cellDoubleClicked.connect(self.edit_step)
        layout.addWidget(self.step_table, 1)

        footer = QHBoxLayout()
        self.stats_label = QLabel("Total de etapas: 0")
        self.stats_label.setObjectName("tableSummary")
        footer.addWidget(self.stats_label)
        footer.addStretch()
        footer.addWidget(QLabel("Duplo clique em uma etapa para editar."))
        layout.addLayout(footer)
        return widget

    def create_settings_tab(self):
        """Informações e estado do plano, sem elementos decorativos extras."""
        widget = QWidget()
        widget.setObjectName("settingsTab")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        basic_group = QGroupBox("Informações do plano")
        basic_group.setObjectName("settingsGroup")
        basic_layout = QFormLayout(basic_group)
        basic_layout.setContentsMargins(18, 18, 18, 18)
        basic_layout.setHorizontalSpacing(18)
        basic_layout.setVerticalSpacing(12)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Ex: Teste completo")
        self.set_field_style(self.name_input)
        basic_layout.addRow("Nome *", self.name_input)

        self.version_input = QLineEdit()
        self.version_input.setPlaceholderText("Ex: 1.0")
        self.set_field_style(self.version_input)
        basic_layout.addRow("Versão *", self.version_input)

        self.description_input = QTextEdit()
        self.description_input.setPlaceholderText(
            "Descreva o propósito e o escopo deste plano de teste..."
        )
        self.description_input.setMaximumHeight(120)
        basic_layout.addRow("Descrição", self.description_input)
        layout.addWidget(basic_group)

        config_group = QGroupBox("Disponibilidade")
        config_group.setObjectName("settingsGroup")
        config_layout = QVBoxLayout(config_group)
        config_layout.setContentsMargins(18, 16, 18, 16)
        self.active_checkbox = QCheckBox("Plano ativo e disponível para execução")
        self.active_checkbox.setChecked(True)
        self.active_checkbox.setToolTip("Planos inativos não aparecem para execução")
        config_layout.addWidget(self.active_checkbox)
        layout.addWidget(config_group)
        layout.addStretch()
        return widget

    def apply_styles(self):
        """Mantém a paleta do projeto e aproxima o editor do dashboard."""
        self.setStyleSheet("""
            QWidget#planEditorRoot { background-color: #F4F7F9; color: #0F172A; }
            QFrame#editorHeader {
                background-color: #0F172A; border-radius: 12px;
            }
            QLabel#editorTitle {
                color: #FFFFFF; font-size: 19px; font-weight: 700; background: transparent;
            }
            QLabel#editorSubtitle {
                color: #CBD5E1; font-size: 11px; background: transparent;
            }
            QPushButton#headerPrimary {
                background-color: #0F766E; color: #FFFFFF;
                border: 1px solid #14B8A6; border-radius: 8px;
                padding: 8px 16px; font-weight: 700;
            }
            QPushButton#headerPrimary:hover { background-color: #0D9488; }
            QPushButton#headerSecondary {
                background-color: #1E293B; color: #E2E8F0;
                border: 1px solid #475569; border-radius: 8px;
                padding: 8px 14px; font-weight: 600;
            }
            QPushButton#headerSecondary:hover { background-color: #334155; }

            QTabWidget#editorTabs::pane {
                background-color: #FFFFFF; border: 1px solid #E2E8F0;
                border-radius: 10px; top: -1px;
            }
            QTabWidget#editorTabs QTabBar::tab {
                background-color: transparent; color: #64748B;
                padding: 10px 16px; margin-right: 4px;
                border-bottom: 2px solid transparent; font-weight: 600;
            }
            QTabWidget#editorTabs QTabBar::tab:selected {
                color: #0F766E; border-bottom: 2px solid #0F766E;
            }

            QFrame#editorCard {
                background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px;
            }
            QLabel#sectionTitle { color: #0F172A; font-size: 14px; font-weight: 700; }
            QLabel#sectionHint, QLabel#tableSummary {
                color: #64748B; font-size: 11px;
            }
            QPushButton#btnPrimary {
                background-color: #0F766E; color: #FFFFFF;
                border: 1px solid #0D9488; border-radius: 8px;
                padding: 7px 14px; font-weight: 700;
            }
            QPushButton#btnPrimary:hover { background-color: #0D9488; }
            QPushButton#btnSecondary {
                background-color: #F1F5F9; color: #334155;
                border: 1px solid #CBD5E1; border-radius: 8px;
                padding: 7px 14px; font-weight: 600;
            }
            QPushButton#btnSecondary:hover { background-color: #E2E8F0; }
            QPushButton#btnDanger {
                background-color: #FEF2F2; color: #B91C1C;
                border: 1px solid #FCA5A5; border-radius: 8px;
                padding: 7px 14px; font-weight: 700;
            }
            QPushButton#btnDanger:hover { background-color: #FEE2E2; }
            QPushButton:disabled {
                background-color: #F1F5F9; color: #94A3B8; border: 1px solid #E2E8F0;
            }

            QTableWidget#stepTable {
                background-color: #FFFFFF; alternate-background-color: #F8FAFC;
                color: #0F172A; border: 1px solid #E2E8F0;
                border-radius: 9px; gridline-color: transparent; outline: 0;
            }
            QTableWidget#stepTable::item { padding: 8px; border-bottom: 1px solid #F1F5F9; }
            QTableWidget#stepTable::item:selected { background-color: #E0F2FE; color: #0F172A; }
            QHeaderView::section {
                background-color: #F8FAFC; color: #475569;
                border: none; border-bottom: 1px solid #E2E8F0;
                padding: 9px 8px; font-size: 11px; font-weight: 700;
            }

            QGroupBox#settingsGroup {
                background-color: #FFFFFF; color: #0F172A;
                border: 1px solid #E2E8F0; border-radius: 10px;
                margin-top: 12px; font-weight: 700;
            }
            QGroupBox#settingsGroup::title {
                subcontrol-origin: margin; left: 14px; padding: 0 6px;
            }
            QLineEdit, QTextEdit {
                background-color: #FFFFFF; color: #0F172A;
                border: 1px solid #CBD5E1; border-radius: 8px;
                padding: 8px 10px; font-size: 13px;
                selection-background-color: #0284C7; selection-color: #FFFFFF;
            }
            QLineEdit:focus, QTextEdit:focus { border: 1px solid #0284C7; }
            QCheckBox { color: #334155; font-size: 12px; spacing: 7px; }
            QLabel#editorStatus {
                color: #64748B; font-size: 11px; padding: 2px 4px; background: transparent;
            }
        """)

    def set_field_style(self, field):
        """Mantido para compatibilidade; os campos usam o estilo central do editor."""
        if isinstance(field, QLineEdit):
            field.setProperty("error", "false")

    def create_plan(self):
        """Cria um novo plano"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Novo Plano de Teste")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        form_layout = QFormLayout()
        
        name_input = QLineEdit()
        name_input.setPlaceholderText("Ex: Teste Completo v1.0")
        version_input = QLineEdit()
        version_input.setPlaceholderText("Ex: 1.0")
        
        form_layout.addRow("Nome do Plano:", name_input)
        form_layout.addRow("Versão:", version_input)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        
        layout.addLayout(form_layout)
        layout.addWidget(buttons)
        dialog.setLayout(layout)
        
        if dialog.exec():
            name = name_input.text().strip()
            version = version_input.text().strip()
            
            if not name or not version:
                QMessageBox.warning(self, "Erro", "Preencha todos os campos.")
                self.close()
                return
                
            self.plan = TestPlan(
                name=name, 
                version=version, 
                board_model_id=self.board.model_id,
                description=""
            )
            self.session.add(self.plan)
            self.session.commit()
            
            self.plan_title.setText(name)
            self.name_input.setText(name)
            self.version_input.setText(version)
            
            logger.info(f"Novo plano criado: {name} v{version}")
            
        else:
            self.close()
            
    def load_plan_data(self):
        """Carrega dados do plano existente"""
        if not self.plan:
            return
            
        self.plan_title.setText(self.plan.name)
        self.name_input.setText(self.plan.name)
        self.version_input.setText(self.plan.version)
        self.description_input.setPlainText(self.plan.description or "")
        self.active_checkbox.setChecked(self.plan.is_active)
        
        self.refresh_steps()
        
    def refresh_steps(self):
        """Atualiza a tabela de etapas"""
        if not self.plan:
            return
            
        steps = self.session.query(TestStep).filter_by(plan_id=self.plan.id).order_by(TestStep.order_index).all()
        self.step_table.setRowCount(len(steps))
        
        for row, step in enumerate(steps):
            point = step.test_point
            self.step_table.setItem(row, 0, QTableWidgetItem(str(step.order_index)))
            self.step_table.setItem(row, 1, QTableWidgetItem(point.refdes if point else "—"))
            self.step_table.setItem(row, 2, QTableWidgetItem(step.description or ""))

            reference_text = "Sem referência"
            if point is not None:
                reference = (
                    self.session.query(OscilloscopeReference)
                    .filter_by(board_model_id=self.board.model_id, refdes=point.refdes)
                    .first()
                )
                if reference is not None:
                    parts = []
                    if reference.vpp_v is not None:
                        parts.append(f"Vpp {reference.vpp_v:.3g} V")
                    if reference.vrms_v is not None:
                        parts.append(f"Vrms {reference.vrms_v:.3g} V")
                    if reference.frequency_hz is not None:
                        f = reference.frequency_hz
                        parts.append(f"F {f/1000:.3g} kHz" if abs(f) >= 1000 else f"F {f:.3g} Hz")
                    parts.append(f"CH{reference.channel or 1}")
                    reference_text = " • ".join(parts)
            self.step_table.setItem(row, 3, QTableWidgetItem(reference_text))
            
        self.stats_label.setText(f"Total de etapas: {len(steps)}")
        
    def on_step_selected(self, row, column):
        """Atualiza as ações disponíveis para a etapa selecionada."""
        has_selection = row >= 0
        self.edit_step_button.setEnabled(has_selection)
        self.delete_step_button.setEnabled(has_selection)

    def add_step(self):
        """Adiciona nova etapa"""
        if not self.plan:
            self.show_status("Crie o plano primeiro", "error")
            return
            
        form = StepForm(self.session, self.board)
        if form.exec():
            data = form.get_step_data()
            
            step = TestStep(
                description=data['description'],
                unit=data['unit'],
                order_index=data['order_index'],
                desired_value=data['desired_value'],
                tolerance=data['tolerance'],
                plan=self.plan,
                test_point=data['test_point'],
                notes=data['notes']
            )
            
            self.session.add(step)
            self.session.commit()
            
            self.refresh_steps()
            self.show_status("Etapa adicionada com sucesso", "success")
            logger.info(f"Etapa adicionada ao plano {self.plan.name}: {data['description']}")
            
    def edit_step(self):
        """Edita etapa selecionada"""
        row = self.step_table.currentRow()
        if row < 0:
            return
            
        step_id = int(self.step_table.item(row, 0).text())  # Usando order_index como referência
        steps = self.session.query(TestStep).filter_by(plan_id=self.plan.id).order_by(TestStep.order_index).all()
        
        if row < len(steps):
            step = steps[row]
            form = StepForm(self.session, self.board, step)
            if form.exec():
                data = form.get_step_data()
                
                step.description = data['description']
                step.unit = data['unit']
                step.order_index = data['order_index']
                step.desired_value = data['desired_value']
                step.tolerance = data['tolerance']
                step.test_point = data['test_point']
                step.notes = data['notes']
                
                self.session.commit()
                self.refresh_steps()
                self.show_status("Etapa atualizada com sucesso", "success")
                logger.info(f"Etapa atualizada: {data['description']}")
                
    def delete_step(self):
        """Exclui etapa selecionada"""
        row = self.step_table.currentRow()
        if row < 0:
            return
            
        step_id = int(self.step_table.item(row, 0).text())
        steps = self.session.query(TestStep).filter_by(plan_id=self.plan.id).order_by(TestStep.order_index).all()
        
        if row < len(steps):
            step = steps[row]
            reply = QMessageBox.question(
                self, "Confirmar Exclusão",
                f"Excluir a etapa '{step.description}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.session.delete(step)
                self.session.commit()
                self.refresh_steps()
                self.show_status("Etapa excluída com sucesso", "success")
                logger.info(f"Etapa excluída: {step.description}")
                
    def move_step_up(self):
        """Move etapa para cima"""
        # Implementar reordenação
        self.show_status("Funcionalidade em desenvolvimento", "warning")
        
    def move_step_down(self):
        """Move etapa para baixo"""
        # Implementar reordenação
        self.show_status("Funcionalidade em desenvolvimento", "warning")
        
    def save_plan(self):
        """Salva as alterações do plano"""
        if not self.plan:
            return
            
        name = self.name_input.text().strip()
        version = self.version_input.text().strip()
        
        if not name or not version:
            self.show_status("Nome e versão são obrigatórios", "error")
            return
            
        self.plan.name = name
        self.plan.version = version
        self.plan.description = self.description_input.toPlainText().strip()
        self.plan.is_active = self.active_checkbox.isChecked()
        
        self.session.commit()
        
        self.plan_title.setText(name)
        self.show_status("Plano salvo com sucesso", "success")
        self.plan_saved.emit(self.plan)
        
        logger.info(f"Plano salvo: {name} v{version}")
        
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
        self.status_label.setStyleSheet(f"color: {colors[type]}; font-size: 11px; padding: 5px;")
        
        # Limpa mensagem após 3 segundos
        if type in ["success", "error", "warning"]:
            QTimer.singleShot(3000, lambda: self.status_label.setText("Pronto"))  # ✅ AGORA CORRETO