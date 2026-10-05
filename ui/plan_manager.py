# ui/plan_manager.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QMessageBox, QInputDialog,
    QDialog, QFormLayout, QDialogButtonBox, QTabWidget, QTextEdit,
    QGroupBox, QCheckBox, QProgressBar, QSplitter, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon
from sqlalchemy.orm import Session
from db.models import TestPlan, TestStep, BoardUnit
from engine.logger import log_user_action
import logging

logger = logging.getLogger(__name__)

class PlanDetailsDialog(QDialog):
    """Dialog para visualizar detalhes do plano"""
    
    def __init__(self, plan, session):
        super().__init__()
        self.plan = plan
        self.session = session
        
        self.setWindowTitle(f"Detalhes do Plano - {plan.name}")
        self.setMinimumSize(600, 500)
        
        self.setup_ui()
        self.load_plan_details()
        self.apply_styles()
        
    def setup_ui(self):
        """Detalhes do plano em uma janela compacta e coerente com o dashboard."""
        self.setObjectName("planDetailsDialog")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        layout.addWidget(self.create_header())

        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("detailsTabs")
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.addTab(self.create_info_tab(), "Informações")
        self.tab_widget.addTab(self.create_steps_tab(), "Etapas")
        self.tab_widget.addTab(self.create_stats_tab(), "Estatísticas")
        layout.addWidget(self.tab_widget, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        close_btn.setText("Fechar")
        close_btn.setObjectName("detailsClose")
        layout.addWidget(buttons)

    def create_header(self):
        """Cabeçalho contextual do plano."""
        frame = QFrame()
        frame.setObjectName("detailsHeader")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(3)

        self.title_label = QLabel(self.plan.name)
        self.title_label.setObjectName("detailsTitle")
        board_name = self.plan.board.name if self.plan.board else "—"
        self.subtitle_label = QLabel(
            f"Versão {self.plan.version}  •  Placa: {board_name}"
        )
        self.subtitle_label.setObjectName("detailsSubtitle")
        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)
        return frame

    def create_info_tab(self):
        """Cria aba de informações"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Informações básicas
        basic_group = QGroupBox("Informações Básicas")
        basic_layout = QFormLayout()
        
        self.name_label = QLabel(self.plan.name)
        self.version_label = QLabel(self.plan.version)
        self.board_label = QLabel(f"{self.plan.board.name} ({self.plan.board.serial_number})")
        self.status_label = QLabel("✅ Ativo" if self.plan.is_active else "❌ Inativo")
        self.created_label = QLabel(self.plan.created_at.strftime("%d/%m/%Y %H:%M") if self.plan.created_at else "N/A")
        
        basic_layout.addRow("Nome:", self.name_label)
        basic_layout.addRow("Versão:", self.version_label)
        basic_layout.addRow("Placa:", self.board_label)
        basic_layout.addRow("Status:", self.status_label)
        basic_layout.addRow("Criado em:", self.created_label)
        
        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)
        
        # Descrição
        desc_group = QGroupBox("Descrição")
        desc_layout = QVBoxLayout()
        
        self.desc_text = QTextEdit()
        self.desc_text.setPlainText(self.plan.description or "Nenhuma descrição fornecida.")
        self.desc_text.setReadOnly(True)
        self.desc_text.setMaximumHeight(120)
        
        desc_layout.addWidget(self.desc_text)
        desc_group.setLayout(desc_layout)
        layout.addWidget(desc_group)
        
        layout.addStretch()
        
        widget.setLayout(layout)
        return widget
        
    def create_steps_tab(self):
        """Cria aba de etapas"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Lista de etapas
        self.steps_list = QListWidget()
        
        # Carrega etapas
        steps = self.session.query(TestStep).filter_by(plan_id=self.plan.id).order_by(TestStep.order_index).all()
        for step in steps:
            item_text = f"{step.order_index}. {step.description}"
            if step.unit:
                item_text += f" ({step.unit})"
            if step.desired_value is not None:
                item_text += f" - {step.desired_value}"
                if step.tolerance is not None:
                    item_text += f" ± {step.tolerance}"
            if step.test_point:
                item_text += f" @ {step.test_point.refdes}"
                
            item = QListWidgetItem(item_text)
            self.steps_list.addItem(item)
            
        layout.addWidget(QLabel(f"Total de etapas: {len(steps)}"))
        layout.addWidget(self.steps_list)
        
        widget.setLayout(layout)
        return widget
        
    def create_stats_tab(self):
        """Cria aba de estatísticas"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Estatísticas básicas
        stats_group = QGroupBox("Estatísticas do Plano")
        stats_layout = QFormLayout()
        
        steps = self.session.query(TestStep).filter_by(plan_id=self.plan.id).all()
        
        # Conta tipos de unidades
        units = {}
        for step in steps:
            unit = step.unit or "Sem unidade"
            units[unit] = units.get(unit, 0) + 1
            
        units_text = "\n".join([f"{unit}: {count}" for unit, count in units.items()])
        
        self.total_steps_label = QLabel(str(len(steps)))
        self.units_label = QLabel(units_text)
        self.with_points_label = QLabel(str(sum(1 for s in steps if s.test_point)))
        self.with_values_label = QLabel(str(sum(1 for s in steps if s.desired_value is not None)))
        
        stats_layout.addRow("Total de etapas:", self.total_steps_label)
        stats_layout.addRow("Etapas com pontos:", self.with_points_label)
        stats_layout.addRow("Etapas com valores:", self.with_values_label)
        stats_layout.addRow("Distribuição por unidade:", self.units_label)
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        layout.addStretch()
        
        widget.setLayout(layout)
        return widget
        
    def apply_styles(self):
        """Mantém a paleta existente e reduz o peso visual do diálogo."""
        self.setStyleSheet("""
            QDialog#planDetailsDialog { background-color: #F4F7F9; color: #0F172A; }
            QFrame#detailsHeader { background-color: #0F172A; border-radius: 10px; }
            QLabel#detailsTitle { color: #FFFFFF; font-size: 18px; font-weight: 700; }
            QLabel#detailsSubtitle { color: #CBD5E1; font-size: 11px; }
            QTabWidget#detailsTabs::pane {
                background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 9px; top: -1px;
            }
            QTabWidget#detailsTabs QTabBar::tab {
                color: #64748B; padding: 9px 14px; border-bottom: 2px solid transparent; font-weight: 600;
            }
            QTabWidget#detailsTabs QTabBar::tab:selected {
                color: #0F766E; border-bottom: 2px solid #0F766E;
            }
            QGroupBox {
                background-color: #FFFFFF; color: #0F172A;
                border: 1px solid #E2E8F0; border-radius: 9px;
                margin-top: 12px; font-weight: 700;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
            QLabel { color: #334155; }
            QListWidget, QTextEdit {
                background-color: #FFFFFF; color: #0F172A;
                border: 1px solid #E2E8F0; border-radius: 8px;
            }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #F1F5F9; }
            QPushButton#detailsClose {
                background-color: #F1F5F9; color: #334155;
                border: 1px solid #CBD5E1; border-radius: 8px;
                padding: 8px 16px; font-weight: 600; min-width: 90px;
            }
            QPushButton#detailsClose:hover { background-color: #E2E8F0; }
        """)

    def load_plan_details(self):
        """Carrega detalhes do plano"""
        # Já carregado durante a criação da UI
        pass


class PlanManager(QWidget):
    """Gerenciador completo de planos de teste"""
    
    plan_selected = pyqtSignal(object)  # Emite o plano selecionado
    
    def __init__(self, session: Session, select_callback, board_unit: BoardUnit):
        super().__init__()
        self.session = session
        self.select_callback = select_callback
        self.board_unit = board_unit
        self.current_plan = None
        self.editor_window = None

        self.setWindowTitle(f"Gerenciar Planos de Teste - {board_unit.name}")
        self.setMinimumSize(900, 600)
        
        self.setup_ui()
        self.apply_styles()
        self.load_plans()
        
    def setup_ui(self):
        """Monta o gerenciador em dois painéis: planos e detalhes."""
        self.setObjectName("planManagerRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 14)
        layout.setSpacing(14)
        layout.addWidget(self.create_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("planSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(12)
        splitter.addWidget(self.create_plans_panel())
        splitter.addWidget(self.create_details_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([390, 520])
        layout.addWidget(splitter, 1)

        self.status_label = QLabel("Pronto")
        self.status_label.setObjectName("managerStatus")
        layout.addWidget(self.status_label)

    def create_header(self):
        """Cabeçalho compacto com contexto da placa e ação de fechar."""
        frame = QFrame()
        frame.setObjectName("managerHeader")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(14)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)
        title_label = QLabel("Planos de teste")
        title_label.setObjectName("managerTitle")
        subtitle_label = QLabel(
            f"{self.board_unit.name}  •  S/N: {self.board_unit.serial_number}"
        )
        subtitle_label.setObjectName("managerSubtitle")
        info_layout.addWidget(title_label)
        info_layout.addWidget(subtitle_label)
        layout.addLayout(info_layout, 1)

        self.close_button = QPushButton("Fechar")
        self.close_button.setObjectName("headerSecondary")
        self.close_button.setMinimumHeight(36)
        self.close_button.clicked.connect(self.close)
        layout.addWidget(self.close_button)
        return frame

    def create_plans_panel(self):
        """Lista de planos com busca e ações essenciais."""
        card = QFrame()
        card.setObjectName("managerCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Planos disponíveis")
        title.setObjectName("cardTitle")
        hint = QLabel("Selecione um plano para visualizar, editar ou usar.")
        hint.setObjectName("cardHint")
        layout.addWidget(title)
        layout.addWidget(hint)

        control_layout = QHBoxLayout()
        control_layout.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar plano...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.filter_plans)
        self.active_only_cb = QCheckBox("Apenas ativos")
        self.active_only_cb.setChecked(True)
        self.active_only_cb.toggled.connect(self.filter_plans)
        control_layout.addWidget(self.search_input, 1)
        control_layout.addWidget(self.active_only_cb)
        layout.addLayout(control_layout)

        self.plan_list = QListWidget()
        self.plan_list.setObjectName("planList")
        self.plan_list.itemSelectionChanged.connect(self.on_plan_selected)
        self.plan_list.itemDoubleClicked.connect(self.view_plan_details)
        layout.addWidget(self.plan_list, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.add_btn = QPushButton("Novo plano")
        self.add_btn.setObjectName("btnPrimary")
        self.add_btn.clicked.connect(self.add_plan)

        self.edit_btn = QPushButton("Editar")
        self.edit_btn.setObjectName("btnSecondary")
        self.edit_btn.clicked.connect(self.edit_plan)
        self.edit_btn.setEnabled(False)

        self.delete_btn = QPushButton("Excluir")
        self.delete_btn.setObjectName("btnDanger")
        self.delete_btn.clicked.connect(self.delete_plan)
        self.delete_btn.setEnabled(False)

        for button in (self.add_btn, self.edit_btn, self.delete_btn):
            button.setMinimumHeight(36)
        actions.addWidget(self.add_btn)
        actions.addWidget(self.edit_btn)
        actions.addWidget(self.delete_btn)
        layout.addLayout(actions)

        self.select_btn = QPushButton("Usar plano selecionado")
        self.select_btn.setObjectName("btnSelect")
        self.select_btn.setMinimumHeight(40)
        self.select_btn.clicked.connect(self.select_plan)
        self.select_btn.setEnabled(False)
        layout.addWidget(self.select_btn)
        return card

    def create_details_panel(self):
        """Resumo do plano selecionado."""
        card = QFrame()
        card.setObjectName("managerCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.details_placeholder = QLabel(
            "Selecione um plano para visualizar as informações."
        )
        self.details_placeholder.setObjectName("emptyState")
        self.details_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.details_placeholder.setWordWrap(True)

        self.details_widget = QWidget()
        self.details_layout = QVBoxLayout(self.details_widget)
        self.details_layout.setContentsMargins(0, 0, 0, 0)
        self.details_layout.setSpacing(12)
        self.details_widget.setVisible(False)

        layout.addWidget(self.details_placeholder, 1)
        layout.addWidget(self.details_widget, 1)
        return card

    def apply_styles(self):
        """Estilo alinhado ao dashboard, usando apenas a paleta já existente."""
        self.setStyleSheet("""
            QWidget#planManagerRoot { background-color: #F4F7F9; color: #0F172A; }
            QSplitter#planSplitter::handle { background: transparent; }
            QFrame#managerHeader { background-color: #0F172A; border-radius: 12px; }
            QLabel#managerTitle { color: #FFFFFF; font-size: 19px; font-weight: 700; }
            QLabel#managerSubtitle { color: #CBD5E1; font-size: 11px; }
            QPushButton#headerSecondary {
                background-color: #1E293B; color: #E2E8F0;
                border: 1px solid #475569; border-radius: 8px;
                padding: 8px 14px; font-weight: 600;
            }
            QPushButton#headerSecondary:hover { background-color: #334155; }

            QFrame#managerCard {
                background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px;
            }
            QLabel#cardTitle { color: #0F172A; font-size: 14px; font-weight: 700; }
            QLabel#cardHint { color: #64748B; font-size: 11px; }
            QLineEdit {
                background-color: #FFFFFF; color: #0F172A;
                border: 1px solid #CBD5E1; border-radius: 8px;
                padding: 8px 10px; font-size: 12px;
            }
            QLineEdit:focus { border: 1px solid #0284C7; }
            QCheckBox { color: #334155; font-size: 11px; spacing: 6px; }

            QListWidget#planList {
                background-color: #FFFFFF; color: #0F172A;
                border: 1px solid #E2E8F0; border-radius: 8px; outline: 0; padding: 3px;
            }
            QListWidget#planList::item {
                padding: 10px 8px; border-bottom: 1px solid #F1F5F9; border-radius: 6px;
            }
            QListWidget#planList::item:selected { background-color: #E0F2FE; color: #0F172A; }
            QListWidget#planList::item:hover:!selected { background-color: #F8FAFC; }

            QPushButton#btnPrimary, QPushButton#btnSelect {
                background-color: #0F766E; color: #FFFFFF;
                border: 1px solid #0D9488; border-radius: 8px;
                padding: 7px 13px; font-weight: 700;
            }
            QPushButton#btnPrimary:hover, QPushButton#btnSelect:hover { background-color: #0D9488; }
            QPushButton#btnSecondary {
                background-color: #F1F5F9; color: #334155;
                border: 1px solid #CBD5E1; border-radius: 8px;
                padding: 7px 13px; font-weight: 600;
            }
            QPushButton#btnSecondary:hover { background-color: #E2E8F0; }
            QPushButton#btnDanger {
                background-color: #FEF2F2; color: #B91C1C;
                border: 1px solid #FCA5A5; border-radius: 8px;
                padding: 7px 13px; font-weight: 700;
            }
            QPushButton#btnDanger:hover { background-color: #FEE2E2; }
            QPushButton:disabled {
                background-color: #F1F5F9; color: #94A3B8; border: 1px solid #E2E8F0;
            }

            QLabel#emptyState {
                color: #64748B; font-size: 13px;
                background-color: #F8FAFC; border: 1px dashed #CBD5E1;
                border-radius: 9px; padding: 28px;
            }
            QLabel#detailTitle { color: #0F172A; font-size: 20px; font-weight: 700; }
            QLabel#detailMeta { color: #64748B; font-size: 11px; }
            QLabel#statusActive {
                background-color: #F0FDFA; color: #0F766E;
                border: 1px solid #14B8A6; border-radius: 8px;
                padding: 4px 9px; font-size: 10px; font-weight: 700;
            }
            QLabel#statusInactive {
                background-color: #F1F5F9; color: #64748B;
                border: 1px solid #CBD5E1; border-radius: 8px;
                padding: 4px 9px; font-size: 10px; font-weight: 700;
            }
            QFrame#metricCard {
                background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px;
            }
            QLabel#metricValue { color: #0F766E; font-size: 20px; font-weight: 700; }
            QLabel#metricLabel { color: #64748B; font-size: 10px; font-weight: 600; }
            QLabel#detailSection { color: #0F172A; font-size: 12px; font-weight: 700; }
            QTextEdit#detailDescription {
                background-color: #F8FAFC; color: #334155;
                border: 1px solid #E2E8F0; border-radius: 8px; padding: 7px;
            }
            QPushButton#detailsButton {
                background-color: #F1F5F9; color: #334155;
                border: 1px solid #CBD5E1; border-radius: 8px;
                padding: 8px 12px; font-weight: 600;
            }
            QPushButton#detailsButton:hover { background-color: #E2E8F0; }
            QLabel#managerStatus { color: #64748B; font-size: 11px; padding: 2px 4px; }
        """)

    def load_plans(self):
        """Carrega a lista de planos"""
        self.plan_list.clear()
        plans = self.session.query(TestPlan).filter_by(board_model_id=self.board_unit.model_id).all()
        
        for plan in plans:
            status_icon = "✅" if plan.is_active else "⏸️"
            item_text = f"{status_icon} {plan.name} v{plan.version}"
            
            # Adiciona informações adicionais
            steps_count = self.session.query(TestStep).filter_by(plan_id=plan.id).count()
            item_text += f" ({steps_count} etapas)"
            
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, plan.id)
            
            # Destaca planos inativos
            if not plan.is_active:
                item.setForeground(Qt.GlobalColor.gray)
                
            self.plan_list.addItem(item)
            
        self.show_status(f"Carregados {len(plans)} planos")
        
    def filter_plans(self):
        """Filtra a lista de planos baseado na busca"""
        search_text = self.search_input.text().lower()
        active_only = self.active_only_cb.isChecked()
        
        for i in range(self.plan_list.count()):
            item = self.plan_list.item(i)
            plan_id = item.data(Qt.ItemDataRole.UserRole)
            plan = self.session.get(TestPlan, plan_id)
            
            # Verifica filtros
            matches_search = search_text in item.text().lower()
            matches_active = not active_only or plan.is_active
            
            item.setHidden(not (matches_search and matches_active))
            
    def on_plan_selected(self):
        """Handle seleção de plano"""
        row = self.plan_list.currentRow()
        has_selection = row >= 0
        
        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)
        self.select_btn.setEnabled(has_selection)
        
        if has_selection:
            item = self.plan_list.item(row)
            plan_id = item.data(Qt.ItemDataRole.UserRole)
            self.current_plan = self.session.get(TestPlan, plan_id)
            self.show_plan_details()
        else:
            self.current_plan = None
            self.hide_plan_details()
            
    def show_plan_details(self):
        """Mostra um resumo limpo do plano selecionado."""
        if not self.current_plan:
            return

        while self.details_layout.count():
            child = self.details_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                while child.layout().count():
                    nested = child.layout().takeAt(0)
                    if nested.widget():
                        nested.widget().deleteLater()

        title = QLabel(self.current_plan.name)
        title.setObjectName("detailTitle")
        version = QLabel(f"Versão {self.current_plan.version}")
        version.setObjectName("detailMeta")

        status = QLabel("ATIVO" if self.current_plan.is_active else "INATIVO")
        status.setObjectName("statusActive" if self.current_plan.is_active else "statusInactive")
        status.setMaximumWidth(80)

        head = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_box.addWidget(title)
        title_box.addWidget(version)
        head.addLayout(title_box, 1)
        head.addWidget(status, alignment=Qt.AlignmentFlag.AlignTop)
        self.details_layout.addLayout(head)

        steps_count = self.session.query(TestStep).filter_by(plan_id=self.current_plan.id).count()
        created = self.current_plan.created_at.strftime('%d/%m/%Y') if self.current_plan.created_at else "—"

        def metric(value, caption):
            frame = QFrame()
            frame.setObjectName("metricCard")
            box = QVBoxLayout(frame)
            box.setContentsMargins(12, 10, 12, 10)
            box.setSpacing(1)
            value_label = QLabel(str(value))
            value_label.setObjectName("metricValue")
            caption_label = QLabel(caption)
            caption_label.setObjectName("metricLabel")
            box.addWidget(value_label)
            box.addWidget(caption_label)
            return frame

        metrics = QHBoxLayout()
        metrics.setSpacing(8)
        metrics.addWidget(metric(steps_count, "ETAPAS"))
        metrics.addWidget(metric(created, "CRIADO EM"))
        self.details_layout.addLayout(metrics)

        desc_label = QLabel("Descrição")
        desc_label.setObjectName("detailSection")
        desc_text = QTextEdit()
        desc_text.setObjectName("detailDescription")
        desc_text.setPlainText(self.current_plan.description or "Nenhuma descrição fornecida.")
        desc_text.setReadOnly(True)
        desc_text.setMaximumHeight(110)
        self.details_layout.addWidget(desc_label)
        self.details_layout.addWidget(desc_text)

        details_btn = QPushButton("Ver detalhes completos")
        details_btn.setObjectName("detailsButton")
        details_btn.clicked.connect(self.view_plan_details)
        self.details_layout.addWidget(details_btn)
        self.details_layout.addStretch()

        self.details_placeholder.setVisible(False)
        self.details_widget.setVisible(True)

    def hide_plan_details(self):
        """Esconde detalhes do plano"""
        self.details_placeholder.setVisible(True)
        self.details_widget.setVisible(False)
        
    def add_plan(self):
        """Adiciona novo plano"""
        print("🔧 DEBUG: add_plan chamado")
        from ui.plan_editor import PlanEditor
        
        if self.editor_window:
            self.editor_window.close()
    
        self.editor_window = PlanEditor(self.session, self.board_unit)  # ← Guarde a referência
        self.editor_window.plan_saved.connect(self.on_plan_saved)
        self.editor_window.show()
        
    def on_plan_saved(self, plan):
        """Handle quando um plano é salvo"""
        self.load_plans()
        self.show_status(f"Plano '{plan.name}' salvo com sucesso", "success")
        
    def edit_plan(self):
        """Edita plano selecionado"""
        if not self.current_plan:
            return
            
        from ui.plan_editor import PlanEditor
        
        if self.editor_window:
            self.editor_window.close()
    
        self.editor_window = PlanEditor(self.session, self.board_unit, self.current_plan)  # ← Guarde a referência
        self.editor_window.plan_saved.connect(self.on_plan_saved)
        self.editor_window.show()
    
    def view_plan_details(self):
        """Abre dialog com detalhes completos do plano"""
        if not self.current_plan:
            return
            
        dialog = PlanDetailsDialog(self.current_plan, self.session)
        dialog.exec()

    def delete_plan(self):
        """Exclui plano selecionado"""
        if not self.current_plan:
            return
            
        # Verifica se há etapas associadas
        steps_count = self.session.query(TestStep).filter_by(plan_id=self.current_plan.id).count()
        
        reply = QMessageBox.question(
            self, "Confirmar Exclusão",
            f"Excluir o plano '{self.current_plan.name}'?\n\n"
            f"Esta ação irá remover {steps_count} etapas associadas e não pode ser desfeita.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                plan_name = self.current_plan.name
                self.session.delete(self.current_plan)
                self.session.commit()
                
                self.load_plans()
                self.show_status(f"Plano '{plan_name}' excluído com sucesso", "success")
                log_user_action(None, "plan_deleted", {"plan_name": plan_name, "steps_count": steps_count})
                
            except Exception as e:
                logger.error(f"Erro ao excluir plano: {e}")
                QMessageBox.critical(self, "Erro", f"Erro ao excluir plano:\n{str(e)}")
                
    def view_plan_details(self):
        """Abre dialog com detalhes completos do plano"""
        if not self.current_plan:
            return
            
        dialog = PlanDetailsDialog(self.current_plan, self.session)
        dialog.exec()
        
    def select_plan(self):
        """Seleciona plano para uso"""
        if not self.current_plan:
            QMessageBox.warning(self, "Erro", "Selecione um plano para usar.")
            return
            
        if not self.current_plan.is_active:
            reply = QMessageBox.question(
                self, "Plano Inativo",
                f"O plano '{self.current_plan.name}' está inativo. Deseja usá-lo mesmo assim?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
                
        self.select_callback(self.current_plan)
        self.show_status(f"Plano '{self.current_plan.name}' selecionado", "success")
        log_user_action(None, "plan_selected", {"plan_name": self.current_plan.name})
        self.close()
        
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
        
        # Limpa mensagem após 3 segundos para sucesso/erro
        if type in ["success", "error"]:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(3000, lambda: self.status_label.setText("Pronto"))