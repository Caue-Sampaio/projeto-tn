# ui/placa_tab.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QMessageBox, QFileDialog, QFormLayout,
    QGroupBox, QTabWidget, QTextEdit, QComboBox, QDialog, QDialogButtonBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QFrame,
    QProgressBar, QInputDialog, QListWidgetItem, QCheckBox  # Adicionei QListWidgetItem e QCheckBox aqui
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap
from sqlalchemy.orm import Session
from db.models import BoardUnit, BoardModel, User, BoardImage, TestPoint, TestPlan, TestRun
from engine.logger import log_user_action
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

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
        
        # Aba de pontos de teste
        points_tab = self.create_points_tab()
        self.tab_widget.addTab(points_tab, "📍 Pontos de Teste")
        
        # Aba de histórico
        history_tab = self.create_history_tab()
        self.tab_widget.addTab(history_tab, "📊 Histórico")
        
        # Aba de imagens
        images_tab = self.create_images_tab()
        self.tab_widget.addTab(images_tab, "🖼️ Imagens")
        
        layout.addWidget(self.tab_widget)
        
        # Botões
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
        
    def create_header(self):
        """Cria cabeçalho do dialog"""
        layout = QVBoxLayout()
        
        self.title_label = QLabel(self.board.name)
        self.title_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #2C3E50;")
        
        self.subtitle_label = QLabel(f"Modelo: {self.board.model} | S/N: {self.board.serial_number}")
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
        plans_count = self.session.query(TestPlan).filter_by(board_model_id=self.board.board_model_id).count()
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
            self.images_list.addItem(item)
            
        layout.addWidget(QLabel(f"Imagens associadas ({len(images)}):"))
        layout.addWidget(self.images_list)
        
        widget.setLayout(layout)
        return widget
        
    def apply_styles(self):
        """Aplica estilos aos componentes"""
        self.setStyleSheet("""
            QDialog {
                background-color: #F8F9FA;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #BDC3C7;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QTableWidget {
                border: 1px solid #BDC3C7;
                border-radius: 5px;
                background-color: white;
            }
            QListWidget {
                border: 1px solid #BDC3C7;
                border-radius: 5px;
                background-color: white;
            }
        """)
        
    def load_board_data(self):
        """Carrega dados da placa"""
        # Já carregado durante a criação da UI
        pass


class PlacaTab(QWidget):
    """Aba completa para gerenciamento de placas"""
    
    board_imported = pyqtSignal(object)  # Emite a placa importada
    
    def __init__(self, session: Session, import_callback, current_user: User = None):
        super().__init__()
        self.session = session
        self.import_callback = import_callback
        self.current_user = current_user
        self.current_board = None

        self.setup_ui()
        self.apply_styles()
        self.refresh_boards()
        
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
        
        # Painel esquerdo - Cadastro e lista
        left_panel = self.create_left_panel()
        splitter.addWidget(left_panel)
        
        # Painel direito - Detalhes
        right_panel = self.create_right_panel()
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
        """Cria cabeçalho da aba"""
        layout = QHBoxLayout()
        
        # Informações
        info_layout = QVBoxLayout()
        title_label = QLabel("Gerenciamento de Placas")
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #2C3E50;")
        
        user_label = QLabel(f"Usuário: {self.current_user.username if self.current_user else 'N/A'}")
        user_label.setStyleSheet("color: #7F8C8D;")
        
        info_layout.addWidget(title_label)
        info_layout.addWidget(user_label)
        layout.addLayout(info_layout)
        
        layout.addStretch()
        
        # Estatísticas rápidas
        stats_layout = QVBoxLayout()
        self.stats_label = QLabel("Carregando...")
        self.stats_label.setStyleSheet("color: #7F8C8D; font-size: 12px; text-align: right;")
        stats_layout.addWidget(self.stats_label)
        layout.addLayout(stats_layout)
        
        return layout
        
    def create_left_panel(self):
        """Cria painel esquerdo (cadastro e lista)"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Grupo de cadastro
        cadastro_group = QGroupBox("Cadastrar Nova Placa")
        cadastro_layout = QFormLayout()
        cadastro_layout.setSpacing(10)
        
        self.nome_input = QLineEdit()
        self.nome_input.setPlaceholderText("Ex: Placa de Demonstração, Protótipo X...")
        self.set_field_style(self.nome_input)
        
        self.modelo_input = QLineEdit()
        self.modelo_input.setPlaceholderText("Ex: PCB-X1, MainBoard...")
        self.set_field_style(self.modelo_input)
        
        self.versao_input = QLineEdit()
        self.versao_input.setPlaceholderText("Ex: 1.0, 2.1, RevA...")
        self.set_field_style(self.versao_input)
        
        self.serial_input = QLineEdit()
        self.serial_input.setPlaceholderText("Ex: SN001, 2024001...")
        self.set_field_style(self.serial_input)
        
        cadastro_layout.addRow("Nome:*", self.nome_input)
        cadastro_layout.addRow("Modelo:*", self.modelo_input)
        cadastro_layout.addRow("Versão:*", self.versao_input)
        cadastro_layout.addRow("Número de Série:*", self.serial_input)
        
        cadastro_group.setLayout(cadastro_layout)
        layout.addWidget(cadastro_group)
        
        # Botões de ação do cadastro
        cadastro_buttons = QHBoxLayout()
        
        self.limpar_btn = QPushButton("🧹 Limpar")
        self.limpar_btn.setMinimumHeight(35)
        self.limpar_btn.clicked.connect(self.limpar_formulario)
        
        self.salvar_btn = QPushButton("💾 Cadastrar Placa")
        self.salvar_btn.setMinimumHeight(35)
        self.salvar_btn.clicked.connect(self.add_board)
        
        cadastro_buttons.addWidget(self.limpar_btn)
        cadastro_buttons.addWidget(self.salvar_btn)
        
        layout.addLayout(cadastro_buttons)
        
        # Separador
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("color: #BDC3C7; margin: 10px 0px;")
        layout.addWidget(separator)
        
        # Controles da lista
        list_controls = QHBoxLayout()
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar placas...")
        self.search_input.textChanged.connect(self.filter_boards)
        
        self.active_only_cb = QCheckBox("Apenas ativas")  # ✅ AGORA CORRETO
        self.active_only_cb.setChecked(True)
        self.active_only_cb.toggled.connect(self.filter_boards)
        
        list_controls.addWidget(self.search_input)
        list_controls.addWidget(self.active_only_cb)
        
        layout.addLayout(list_controls)
        
        # Lista de placas
        self.board_list = QListWidget()
        self.board_list.itemSelectionChanged.connect(self.on_board_selected)
        self.board_list.itemDoubleClicked.connect(self.view_board_details)
        
        layout.addWidget(QLabel("Placas Cadastradas:"))
        layout.addWidget(self.board_list)
        
        # Botões de ação da lista
        list_buttons = QHBoxLayout()
        
        self.details_btn = QPushButton("👁️ Detalhes")
        self.details_btn.setMinimumHeight(35)
        self.details_btn.clicked.connect(self.view_board_details)
        self.details_btn.setEnabled(False)
        
        self.import_btn = QPushButton("📥 Importar para Teste")
        self.import_btn.setMinimumHeight(35)
        self.import_btn.clicked.connect(self.import_board)
        self.import_btn.setEnabled(False)
        
        self.delete_btn = QPushButton("🗑️ Excluir Placa")
        self.delete_btn.setMinimumHeight(35)
        self.delete_btn.clicked.connect(self.delete_board)
        self.delete_btn.setEnabled(False)
        
        list_buttons.addWidget(self.details_btn)
        list_buttons.addWidget(self.import_btn)
        list_buttons.addWidget(self.delete_btn)
        
        layout.addLayout(list_buttons)
        
        widget.setLayout(layout)
        return widget
        
    def create_right_panel(self):
        """Cria painel direito (detalhes)"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Placeholder para detalhes
        self.details_placeholder = QLabel("Selecione uma placa para ver os detalhes")
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
                background-color: #3498DB;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
            QPushButton:pressed {
                background-color: #21618C;
            }
            QPushButton:disabled {
                background-color: #BDC3C7;
                color: #7F8C8D;
            }
        """
        
        self.salvar_btn.setStyleSheet(button_style)
        self.import_btn.setStyleSheet(button_style)
        self.details_btn.setStyleSheet(button_style)
        
        self.limpar_btn.setStyleSheet("""
            QPushButton {
                background-color: #95A5A6;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7F8C8D;
            }
        """)
        
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
        """)
        
        self.board_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                border: 1px solid #BDC3C7;
                border-radius: 5px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #ECF0F1;
            }
            QListWidget::item:selected {
                background-color: #3498DB;
                color: white;
                border-radius: 3px;
            }
            QListWidget::item:hover {
                background-color: #EBF5FB;
            }
        """)
        
        self.search_input.setStyleSheet("""
            QLineEdit {
                border: 2px solid #BDC3C7;
                border-radius: 5px;
                padding: 8px 12px;
                font-size: 14px;
                background-color: white;
            }
            QLineEdit:focus {
                border-color: #3498DB;
            }
        """)
        
    def set_field_style(self, field):
        """Aplica estilo consistente aos campos"""
        field.setStyleSheet("""
            QLineEdit {
                border: 2px solid #BDC3C7;
                border-radius: 5px;
                padding: 8px 12px;
                font-size: 14px;
                background-color: white;
            }
            QLineEdit:focus {
                border-color: #3498DB;
                background-color: #F8F9FA;
            }
        """)
        
    def refresh_boards(self):
        """Atualiza a lista de placas e estatísticas"""
        self.board_list.clear()
        boards = self.session.query(BoardUnit).all()
        
        for board in boards:
            status_icon = "✅" if board.is_active else "⏸️"
            item_text = f"{status_icon} {board.name} - {board.model} v{board.version} - SN:{board.serial_number}"
            
            item = QListWidgetItem(item_text)  # ✅ AGORA CORRETO
            item.setData(Qt.ItemDataRole.UserRole, board.id)
            
            # Destaca placas inativas
            if not board.is_active:
                item.setForeground(Qt.GlobalColor.gray)
                
            self.board_list.addItem(item)
            
        # Atualiza estatísticas
        total_boards = len(boards)
        active_boards = sum(1 for b in boards if b.is_active)
        self.stats_label.setText(f"Total: {total_boards} | Ativas: {active_boards}")
        
        self.show_status(f"Carregadas {total_boards} placas")
        
    def filter_boards(self):
        """Filtra a lista de placas baseado na busca"""
        search_text = self.search_input.text().lower()
        active_only = self.active_only_cb.isChecked()
        
        for i in range(self.board_list.count()):
            item = self.board_list.item(i)
            board_id = item.data(Qt.ItemDataRole.UserRole)
            board = self.session.get(BoardUnit, board_id)
            
            # Verifica filtros
            matches_search = search_text in item.text().lower()
            matches_active = not active_only or board.is_active
            
            item.setHidden(not (matches_search and matches_active))
            
    def on_board_selected(self):
        """Handle seleção de placa"""
        row = self.board_list.currentRow()
        has_selection = row >= 0
        
        self.details_btn.setEnabled(has_selection)
        self.import_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)
        
        if has_selection:
            item = self.board_list.item(row)
            board_id = item.data(Qt.ItemDataRole.UserRole)
            self.current_board = self.session.get(BoardUnit, board_id)
            self.show_board_details()
        else:
            self.current_board = None
            self.hide_board_details()
            
    def show_board_details(self):
        """Mostra detalhes da placa selecionada"""
        if not self.current_board:
            return
            
        # Limpa layout anterior
        while self.details_layout.count():
            child = self.details_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        # Cabeçalho
        title_label = QLabel(self.current_board.name)
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #2C3E50; margin-bottom: 5px;")
        
        model_label = QLabel(f"Modelo: {self.current_board.model} v{self.current_board.version}")
        model_label.setStyleSheet("color: #7F8C8D; font-size: 14px; margin-bottom: 5px;")
        
        serial_label = QLabel(f"Série: {self.current_board.serial_number}")
        serial_label.setStyleSheet("color: #7F8C8D; font-size: 14px; margin-bottom: 15px;")
        
        # Status
        status_label = QLabel("Status: " + ("✅ Ativa" if self.current_board.is_active else "⏸️ Inativa"))
        status_label.setStyleSheet("color: #27AE60;" if self.current_board.is_active else "color: #E74C3C;")
        
        # Estatísticas rápidas
        points_count = self.session.query(TestPoint).filter_by(board_id=self.current_board.id).count()
        plans_count = self.session.query(TestPlan).filter_by(board_model_id=self.current_board.board_model_id).count()
        runs_count = self.session.query(TestRun).filter_by(board_id=self.current_board.id).count()
        
        stats_text = f"• {points_count} pontos de teste\n• {plans_count} planos\n• {runs_count} execuções"
        stats_label = QLabel(stats_text)
        stats_label.setStyleSheet("color: #7F8C8D; font-size: 12px; background-color: #F8F9FA; padding: 10px; border-radius: 5px;")
        
        # Botões de ação rápida
        actions_layout = QHBoxLayout()
        
        details_btn = QPushButton("👁️ Ver Detalhes Completos")
        details_btn.clicked.connect(self.view_board_details)
        
        image_btn = QPushButton("🖼️ Adicionar Imagem")
        image_btn.clicked.connect(self.add_image)
        
        actions_layout.addWidget(details_btn)
        actions_layout.addWidget(image_btn)
        
        self.details_layout.addWidget(title_label)
        self.details_layout.addWidget(model_label)
        self.details_layout.addWidget(serial_label)
        self.details_layout.addWidget(status_label)
        self.details_layout.addWidget(stats_label)
        self.details_layout.addLayout(actions_layout)
        self.details_layout.addStretch()
        
        self.details_placeholder.setVisible(False)
        self.details_widget.setVisible(True)
        
    def hide_board_details(self):
        """Esconde detalhes da placa"""
        self.details_placeholder.setVisible(True)
        self.details_widget.setVisible(False)
        
    def limpar_formulario(self):
        """Limpa o formulário de cadastro"""
        self.nome_input.clear()
        self.modelo_input.clear()
        self.versao_input.clear()
        self.serial_input.clear()
        self.show_status("Formulário limpo")
        
    def add_board(self):
        """Cadastra nova placa"""
        nome = self.nome_input.text().strip()
        modelo = self.modelo_input.text().strip()
        versao = self.versao_input.text().strip()
        serial = self.serial_input.text().strip()

        # Validações
        if not nome or not modelo or not versao or not serial:
            self.show_status("Preencha todos os campos obrigatórios", "error")
            return
            
        # Verifica se número de série já existe
        existing = self.session.query(BoardUnit).filter_by(serial_number=serial).first()
        if existing:
            self.show_status(f"Já existe uma placa com o número de série {serial}", "error")
            return

        try:
            # Garante que existe um BoardModel
            board_model = self.session.query(BoardModel).filter_by(name=modelo, version=versao).first()
            if not board_model:
                board_model = BoardModel(name=modelo, version=versao)
                self.session.add(board_model)
                self.session.flush()

            # Cria a placa
            new_board = BoardUnit(
                name=nome,
                model=modelo,
                version=versao,
                serial_number=serial,
                board_model=board_model,
                operator=self.current_user
            )
            self.session.add(new_board)
            self.session.commit()

            self.show_status(f"Placa '{nome}' cadastrada com sucesso!", "success")
            log_user_action(self.current_user, "board_created", {
                "board_name": nome,
                "model": modelo,
                "version": versao,
                "serial": serial
            })
            
            self.limpar_formulario()
            self.refresh_boards()
            
            # Seleciona a nova placa
            for i in range(self.board_list.count()):
                item = self.board_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == new_board.id:
                    self.board_list.setCurrentItem(item)
                    break
                    
        except Exception as e:
            logger.error(f"Erro ao cadastrar placa: {e}")
            self.show_status(f"Erro ao cadastrar placa: {str(e)}", "error")
            
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
                
                img = BoardImage(
                    board=self.current_board, 
                    path=path,
                    description=description if ok and description.strip() else None
                )
                self.session.add(img)
                self.session.commit()
                
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
        plans_count = self.session.query(TestPlan).filter_by(board_model_id=self.current_board.board_model_id).count()
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
        self.status_label.setStyleSheet(f"color: {colors[type]}; font-size: 11px; padding: 5px;")
        
        # Limpa mensagem após 3 segundos para sucesso/erro
        if type in ["success", "error"]:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(3000, lambda: self.status_label.setText("Pronto"))