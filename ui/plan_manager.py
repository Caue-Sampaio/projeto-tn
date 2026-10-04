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
        """Configura a interface do usuário"""
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Cabeçalho
        header_layout = self.create_header()
        layout.addLayout(header_layout)
        
        # Abas
        self.tab_widget = QTabWidget()
        
        # Aba de informações
        info_tab = self.create_info_tab()
        self.tab_widget.addTab(info_tab, "📋 Informações")
        
        # Aba de etapas
        steps_tab = self.create_steps_tab()
        self.tab_widget.addTab(steps_tab, "🔧 Etapas")
        
        # Aba de estatísticas
        stats_tab = self.create_stats_tab()
        self.tab_widget.addTab(stats_tab, "📊 Estatísticas")
        
        layout.addWidget(self.tab_widget)
        
        # Botões
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
        
    def create_header(self):
        """Cria cabeçalho do dialog"""
        layout = QVBoxLayout()
        
        self.title_label = QLabel(self.plan.name)
        self.title_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #2C3E50;")
        
        self.subtitle_label = QLabel(f"Versão {self.plan.version} | Placa: {self.plan.board.name}")
        self.subtitle_label.setStyleSheet("color: #7F8C8D; font-size: 14px;")
        
        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)
        
        return layout
        
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
        """Aplica estilos aos componentes"""
        self.setStyleSheet("""
            QDialog {
                background-color: #F8F9FA;
                color: #1E293B;
            }
            QLabel {
                color: #1E293B;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #BDC3C7;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
                color: #1E293B;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #1E293B;
            }
            QListWidget {
                border: 1px solid #BDC3C7;
                border-radius: 5px;
                background-color: white;
                color: #1E293B;
            }
            QTextEdit {
                border: 1px solid #BDC3C7;
                border-radius: 5px;
                background-color: white;
                color: #1E293B;
            }
            QDialogButtonBox QPushButton {
                background-color: #0284C7;
                color: white;
                border: 1px solid #0369A1;
                border-radius: 5px;
                padding: 8px 20px;
                font-weight: bold;
                min-width: 90px;
            }
            QDialogButtonBox QPushButton:hover {
                background-color: #0369A1;
            }
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
        """Configura a interface do usuário"""
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Cabeçalho
        header_layout = self.create_header()
        layout.addLayout(header_layout)
        
        # Splitter para layout responsivo
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Painel esquerdo - Lista de planos
        left_panel = self.create_plans_panel()
        splitter.addWidget(left_panel)
        
        # Painel direito - Detalhes
        right_panel = self.create_details_panel()
        splitter.addWidget(right_panel)
        
        # Configura proporções do splitter
        splitter.setSizes([400, 500])
        layout.addWidget(splitter)
        
        # Barra de status
        self.status_label = QLabel("Pronto")
        self.status_label.setStyleSheet("color: #7F8C8D; font-size: 11px; padding: 5px;")
        layout.addWidget(self.status_label)
        
        self.setLayout(layout)
        
    def create_header(self):
        """Cria cabeçalho do gerenciador"""
        layout = QHBoxLayout()
        
        # Informações
        info_layout = QVBoxLayout()
        title_label = QLabel("Gerenciador de Planos de Teste")
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #2C3E50;")
        
        subtitle_label = QLabel(f"Placa: {self.board_unit.name} ({self.board_unit.serial_number})")
        subtitle_label.setStyleSheet("color: #7F8C8D;")
        
        info_layout.addWidget(title_label)
        info_layout.addWidget(subtitle_label)
        layout.addLayout(info_layout)
        
        layout.addStretch()
        
        # Botão fechar
        self.close_button = QPushButton("Fechar")
        self.close_button.setMinimumWidth(100)
        self.close_button.clicked.connect(self.close)
        
        layout.addWidget(self.close_button)
        
        return layout
        
    def create_plans_panel(self):
        """Cria painel da lista de planos"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Controles de busca e filtro
        control_layout = QHBoxLayout()
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar planos...")
        self.search_input.textChanged.connect(self.filter_plans)
        
        self.active_only_cb = QCheckBox("Apenas ativos")
        self.active_only_cb.setChecked(True)
        self.active_only_cb.toggled.connect(self.filter_plans)
        
        control_layout.addWidget(self.search_input)
        control_layout.addWidget(self.active_only_cb)
        
        layout.addLayout(control_layout)
        
        # Lista de planos
        self.plan_list = QListWidget()
        self.plan_list.itemSelectionChanged.connect(self.on_plan_selected)
        self.plan_list.itemDoubleClicked.connect(self.view_plan_details)
        
        layout.addWidget(QLabel("Planos de Teste:"))
        layout.addWidget(self.plan_list)
        
        # Botões de ação
        buttons_layout = QHBoxLayout()
        
        self.add_btn = QPushButton("➕ Novo")
        self.add_btn.setMinimumHeight(35)
        self.add_btn.clicked.connect(self.add_plan)
        
        self.edit_btn = QPushButton("✏️ Editar")
        self.edit_btn.setMinimumHeight(35)
        self.edit_btn.clicked.connect(self.edit_plan)
        self.edit_btn.setEnabled(False)
        
        self.delete_btn = QPushButton("🗑️ Excluir")
        self.delete_btn.setMinimumHeight(35)
        self.delete_btn.clicked.connect(self.delete_plan)
        self.delete_btn.setEnabled(False)
        
        buttons_layout.addWidget(self.add_btn)
        buttons_layout.addWidget(self.edit_btn)
        buttons_layout.addWidget(self.delete_btn)
        
        layout.addLayout(buttons_layout)
        
        # Botão de seleção
        self.select_btn = QPushButton("✅ Selecionar Plano")
        self.select_btn.setMinimumHeight(40)
        self.select_btn.clicked.connect(self.select_plan)
        self.select_btn.setEnabled(False)
        
        layout.addWidget(self.select_btn)
        
        widget.setLayout(layout)
        return widget
        
    def create_details_panel(self):
        """Cria painel de detalhes"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Placeholder para detalhes
        self.details_placeholder = QLabel("Selecione um plano para ver os detalhes")
        self.details_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.details_placeholder.setStyleSheet("""
            color: #7F8C8D; 
            font-size: 14px; 
            padding: 50px;
            border: 2px dashed #BDC3C7;
            border-radius: 10px;
        """)
        
        # Widget de detalhes (será preenchido dinamicamente)
        self.details_widget = QWidget()
        self.details_layout = QVBoxLayout()
        self.details_widget.setLayout(self.details_layout)
        self.details_widget.setVisible(False)
        
        layout.addWidget(self.details_placeholder)
        layout.addWidget(self.details_widget)
        layout.addStretch()
        
        widget.setLayout(layout)
        return widget
        
    def apply_styles(self):
        """Aplica estilos aos componentes"""
        button_style = """
            QPushButton {
                background-color: #0284C7;
                color: white;
                border: 1px solid #0369A1;
                border-radius: 5px;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0369A1;
            }
            QPushButton:pressed {
                background-color: #075985;
            }
            QPushButton:disabled {
                background-color: #CBD5E1;
                color: #64748B;
                border: 1px solid #94A3B8;
            }
        """
        
        self.add_btn.setStyleSheet(button_style)
        self.edit_btn.setStyleSheet(button_style)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #EF4444;
                color: white;
                border: 1px solid #DC2626;
                border-radius: 5px;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #DC2626;
            }
            QPushButton:disabled {
                background-color: #CBD5E1;
                color: #64748B;
                border: 1px solid #94A3B8;
            }
        """)
        
        self.select_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                border: 1px solid #059669;
                border-radius: 5px;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
            QPushButton:disabled {
                background-color: #CBD5E1;
                color: #64748B;
                border: 1px solid #94A3B8;
            }
        """)
        
        self.close_button.setStyleSheet("""
            QPushButton {
                background-color: #94A3B8;
                color: white;
                border: 1px solid #64748B;
                border-radius: 5px;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #64748B;
            }
        """)
        
        self.plan_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                color: #1E293B;
                border: 1px solid #BDC3C7;
                border-radius: 5px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 10px;
                color: #1E293B;
                border-bottom: 1px solid #ECF0F1;
            }
            QListWidget::item:selected {
                background-color: #0284C7;
                color: white;
                border-radius: 3px;
            }
            QListWidget::item:hover {
                background-color: #EBF5FB;
                color: #1E293B;
            }
        """)
        
        self.search_input.setStyleSheet("""
            QLineEdit {
                border: 2px solid #BDC3C7;
                border-radius: 5px;
                padding: 8px 12px;
                font-size: 14px;
                background-color: white;
                color: #1E293B;
            }
            QLineEdit:focus {
                border-color: #0284C7;
                color: #1E293B;
            }
        """)
        
        self.active_only_cb.setStyleSheet("color: #1E293B; font-size: 12px; font-weight: 500;")
        
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
        """Mostra detalhes do plano selecionado"""
        if not self.current_plan:
            return
            
        # Limpa layout anterior
        while self.details_layout.count():
            child = self.details_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        # Cabeçalho
        title_label = QLabel(self.current_plan.name)
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #2C3E50; margin-bottom: 5px;")
        
        version_label = QLabel(f"Versão {self.current_plan.version}")
        version_label.setStyleSheet("color: #7F8C8D; font-size: 14px; margin-bottom: 15px;")
        
        # Status
        status_label = QLabel("Status: " + ("✅ Ativo" if self.current_plan.is_active else "⏸️ Inativo"))
        status_label.setStyleSheet("color: #27AE60;" if self.current_plan.is_active else "color: #E74C3C;")
        
        # Estatísticas rápidas
        steps_count = self.session.query(TestStep).filter_by(plan_id=self.current_plan.id).count()
        stats_label = QLabel(f"• {steps_count} etapas de teste\n• Criado em: {self.current_plan.created_at.strftime('%d/%m/%Y')}")
        stats_label.setStyleSheet("color: #7F8C8D; font-size: 12px; background-color: #F8F9FA; padding: 10px; border-radius: 5px;")
        
        # Descrição
        desc_label = QLabel("Descrição:")
        desc_label.setStyleSheet("font-weight: bold; color: #2C3E50; margin-top: 15px;")
        
        desc_text = QTextEdit()
        desc_text.setPlainText(self.current_plan.description or "Nenhuma descrição fornecida.")
        desc_text.setReadOnly(True)
        desc_text.setMaximumHeight(80)
        desc_text.setStyleSheet("border: 1px solid #BDC3C7; border-radius: 5px; background-color: white;")
        
        # Botão ver detalhes completos
        details_btn = QPushButton("👁️ Ver Detalhes Completos")
        details_btn.clicked.connect(self.view_plan_details)
        details_btn.setStyleSheet("""
            QPushButton {
                background-color: #17A2B8;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                font-weight: bold;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #138496;
            }
        """)
        
        self.details_layout.addWidget(title_label)
        self.details_layout.addWidget(version_label)
        self.details_layout.addWidget(status_label)
        self.details_layout.addWidget(stats_label)
        self.details_layout.addWidget(desc_label)
        self.details_layout.addWidget(desc_text)
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