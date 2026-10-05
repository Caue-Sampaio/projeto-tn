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
from db.models import TestStep, TestPoint, TestPlan
from engine.logger import log_user_action
import logging

logger = logging.getLogger(__name__)

class StepForm(QDialog):
    """Formulário para adicionar/editar uma etapa ao plano"""
    
    def __init__(self, session, board, step=None):
        super().__init__()
        self.session = session
        self.board = board
        self.step = step  # Se for edição
        self.is_edit = step is not None
        
        self.setWindowTitle("Editar Etapa de Teste" if self.is_edit else "Nova Etapa de Teste")
        self.setMinimumWidth(500)
        
        self.setup_ui()
        self.apply_styles()
        
        if self.is_edit:
            self.load_step_data()
            
    def setup_ui(self):
        """Monta o formulário de etapa com a mesma linguagem visual do dashboard."""
        self.setObjectName("stepDialog")
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("stepHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(22, 16, 22, 16)
        header_layout.setSpacing(3)

        title = QLabel("Editar etapa" if self.is_edit else "Nova etapa")
        title.setObjectName("stepTitle")
        subtitle = QLabel(
            "Defina o ponto, o valor esperado e a tolerância desta medição."
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
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Ex: Tensão de alimentação")
        self.description_input.setToolTip("Descrição clara e objetiva da etapa de teste")
        self.set_field_style(self.description_input)
        form_layout.addRow("Descrição *", self.description_input)

        measurement_row = QHBoxLayout()
        measurement_row.setSpacing(10)
        self.unit_select = QComboBox()
        self.unit_select.addItems(["V", "A", "Ω", "Hz", "°C", "%", "dB", "s", "W"])
        self.unit_select.setEditable(True)
        self.unit_select.setToolTip("Unidade de medida")
        self.unit_select.setMinimumWidth(110)

        self.order_spinbox = QSpinBox()
        self.order_spinbox.setRange(1, 1000)
        self.order_spinbox.setValue(1)
        self.order_spinbox.setToolTip("Ordem de execução da etapa")
        self.order_spinbox.setMinimumWidth(90)

        measurement_row.addWidget(QLabel("Unidade"))
        measurement_row.addWidget(self.unit_select)
        measurement_row.addSpacing(10)
        measurement_row.addWidget(QLabel("Ordem"))
        measurement_row.addWidget(self.order_spinbox)
        measurement_row.addStretch()
        form_layout.addRow("Medição", measurement_row)

        values_row = QHBoxLayout()
        values_row.setSpacing(10)
        self.desired_input = QLineEdit()
        self.desired_input.setPlaceholderText("Ex: 3.3")
        self.desired_input.setToolTip("Valor esperado para a medição")
        validator = QtGui.QDoubleValidator()
        validator.setBottom(0)
        self.desired_input.setValidator(validator)
        self.set_field_style(self.desired_input)

        self.tolerance_input = QLineEdit()
        self.tolerance_input.setPlaceholderText("Ex: 0.1")
        self.tolerance_input.setToolTip("Margem de tolerância aceitável (±)")
        self.tolerance_input.setValidator(validator)
        self.set_field_style(self.tolerance_input)

        values_row.addWidget(QLabel("Desejado"))
        values_row.addWidget(self.desired_input, 1)
        values_row.addWidget(QLabel("Tolerância ±"))
        values_row.addWidget(self.tolerance_input, 1)
        form_layout.addRow("Valores", values_row)

        self.point_select = QComboBox()
        points = self.session.query(TestPoint).filter_by(board_id=self.board.id).all()
        self.points = points
        self.point_select.addItem("Nenhum ponto associado", None)
        for point in points:
            self.point_select.addItem(
                f"{point.refdes}  •  X:{point.x}  Y:{point.y}", point
            )
        self.point_select.setToolTip("Ponto físico da placa associado à etapa")
        form_layout.addRow("Ponto de teste", self.point_select)

        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("Observações adicionais sobre esta etapa...")
        self.notes_input.setMaximumHeight(88)
        self.notes_input.setToolTip("Informações complementares sobre a etapa")
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

    def apply_styles(self):
        """Aplica a paleta já usada no programa, sem introduzir novas cores."""
        self.setStyleSheet("""
            QDialog#stepDialog { background-color: #F4F7F9; color: #0F172A; }
            QFrame#stepHeader { background-color: #0F172A; }
            QLabel#stepTitle {
                color: #FFFFFF; font-size: 18px; font-weight: 700; background: transparent;
            }
            QLabel#stepSubtitle {
                color: #CBD5E1; font-size: 11px; background: transparent;
            }
            QWidget#stepBody { background-color: #F4F7F9; }
            QFrame#formCard {
                background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px;
            }
            QFrame#stepFooter {
                background-color: #FFFFFF; border-top: 1px solid #E2E8F0;
            }
            QLabel { color: #334155; font-size: 12px; }
            QLabel#validationText { color: #DC2626; font-size: 11px; font-weight: 600; }
            QLineEdit, QComboBox, QSpinBox, QTextEdit {
                background-color: #FFFFFF; color: #0F172A;
                border: 1px solid #CBD5E1; border-radius: 8px;
                padding: 7px 10px; font-size: 13px;
                selection-background-color: #0284C7; selection-color: #FFFFFF;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {
                border: 1px solid #0284C7;
            }
            QComboBox QAbstractItemView {
                background-color: #FFFFFF; color: #0F172A;
                selection-background-color: #0284C7; selection-color: #FFFFFF;
            }
            QPushButton#primaryDialogButton {
                background-color: #0F766E; color: #FFFFFF;
                border: 1px solid #0D9488; border-radius: 8px;
                padding: 8px 16px; font-weight: 700; min-width: 120px;
            }
            QPushButton#primaryDialogButton:hover { background-color: #0D9488; }
            QPushButton#secondaryDialogButton {
                background-color: #F1F5F9; color: #334155;
                border: 1px solid #CBD5E1; border-radius: 8px;
                padding: 8px 16px; font-weight: 600; min-width: 90px;
            }
            QPushButton#secondaryDialogButton:hover { background-color: #E2E8F0; }
        """)

    def set_field_style(self, field):
        """Mantido por compatibilidade; o estilo agora é centralizado no diálogo."""
        if isinstance(field, QLineEdit):
            field.setProperty("error", "false")

    def load_step_data(self):
        """Carrega dados da etapa para edição"""
        if not self.step:
            return
            
        self.description_input.setText(self.step.description or "")
        self.unit_select.setCurrentText(self.step.unit or "V")
        self.order_spinbox.setValue(self.step.order_index or 1)
        self.desired_input.setText(str(self.step.desired_value) if self.step.desired_value else "")
        self.tolerance_input.setText(str(self.step.tolerance) if self.step.tolerance else "")
        self.notes_input.setPlainText(self.step.notes or "")
        
        # Seleciona ponto de teste
        if self.step.test_point:
            for i in range(self.point_select.count()):
                if self.point_select.itemData(i) == self.step.test_point:
                    self.point_select.setCurrentIndex(i)
                    break
                    
    def validate_and_accept(self):
        """Valida os dados antes de aceitar"""
        errors = self.validate_form()
        
        if errors:
            self.validation_label.setText("❌ " + " | ".join(errors))
            return
            
        self.accept()
        
    def validate_form(self):
        """Valida os dados do formulário"""
        errors = []
        
        # Descrição obrigatória
        if not self.description_input.text().strip():
            errors.append("Informe a descrição da etapa")
            self.mark_field_error(self.description_input)
        else:
            self.clear_field_error(self.description_input)
            
        # Valida valores numéricos
        desired_text = self.desired_input.text().strip()
        tolerance_text = self.tolerance_input.text().strip()
        
        if desired_text:
            try:
                float(desired_text)
                self.clear_field_error(self.desired_input)
            except ValueError:
                errors.append("Valor desejado deve ser um número")
                self.mark_field_error(self.desired_input)
                
        if tolerance_text:
            try:
                tolerance = float(tolerance_text)
                if tolerance < 0:
                    errors.append("Tolerância não pode ser negativa")
                    self.mark_field_error(self.tolerance_input)
                else:
                    self.clear_field_error(self.tolerance_input)
            except ValueError:
                errors.append("Tolerância deve ser um número")
                self.mark_field_error(self.tolerance_input)
                
        return errors
        
    def mark_field_error(self, field):
        """Marca campo com erro"""
        field.setProperty("error", "true")
        field.style().unpolish(field)
        field.style().polish(field)
        
    def clear_field_error(self, field):
        """Remove marcação de erro do campo"""
        field.setProperty("error", "false")
        field.style().unpolish(field)
        field.style().polish(field)
        
    def get_step_data(self):
        """Retorna os dados do formulário"""
        selected_index = self.point_select.currentIndex()
        point = self.point_select.itemData(selected_index) if selected_index >= 0 else None
        
        return {
            'description': self.description_input.text().strip(),
            'unit': self.unit_select.currentText().strip(),
            'order_index': self.order_spinbox.value(),
            'desired_value': float(self.desired_input.text()) if self.desired_input.text().strip() else None,
            'tolerance': float(self.tolerance_input.text()) if self.tolerance_input.text().strip() else None,
            'test_point': point,
            'notes': self.notes_input.toPlainText().strip() or None
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
        hint = QLabel("Adicione e edite somente as etapas necessárias para este plano.")
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
        self.step_table.setColumnCount(6)
        self.step_table.setHorizontalHeaderLabels([
            "Ordem", "Descrição", "Unidade", "Desejado", "Tolerância", "Ponto"
        ])
        header = self.step_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
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
            self.step_table.setItem(row, 0, QTableWidgetItem(str(step.order_index)))
            self.step_table.setItem(row, 1, QTableWidgetItem(step.description or ""))
            self.step_table.setItem(row, 2, QTableWidgetItem(step.unit or ""))
            self.step_table.setItem(row, 3, QTableWidgetItem(
                f"{step.desired_value:.3f}" if step.desired_value else "-"
            ))
            self.step_table.setItem(row, 4, QTableWidgetItem(
                f"±{step.tolerance:.3f}" if step.tolerance else "-"
            ))
            self.step_table.setItem(row, 5, QTableWidgetItem(
                step.test_point.refdes if step.test_point else "-"
            ))
            
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