# ui/user_register.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QMessageBox, QComboBox, QFormLayout, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from db.models import User
from engine.logger import log_user_action
import logging

logger = logging.getLogger(__name__)

class UserRegisterDialog(QDialog):
    """Dialog para cadastro de novos usuários"""
    
    def __init__(self, session):
        super().__init__()
        self.session = session
        self.new_username = None
        
        self.setup_ui()
        self.apply_styles()
        
    def setup_ui(self):
        """Configura a interface do usuário"""
        self.setWindowTitle("Cadastro de Novo Usuário")
        self.setFixedSize(450, 400)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | 
                           Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint)
        
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(25, 25, 25, 20)
        
        # Título
        title_label = QLabel("Cadastrar Novo Usuário")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #2C3E50; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # Formulário
        form_layout = self.create_form()
        layout.addLayout(form_layout)
        
        # Botões
        buttons_layout = self.create_buttons()
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
        
    def create_form(self):
        """Cria formulário de cadastro"""
        layout = QFormLayout()
        layout.setSpacing(15)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        # Campo usuário
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Digite o nome de usuário")
        self.username_input.setMinimumHeight(35)
        self.set_field_style(self.username_input)
        layout.addRow("Usuário:", self.username_input)
        
        # Campo senha
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Digite a senha")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMinimumHeight(35)
        self.set_field_style(self.password_input)
        layout.addRow("Senha:", self.password_input)
        
        # Confirmação de senha
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setPlaceholderText("Confirme a senha")
        self.confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password_input.setMinimumHeight(35)
        self.set_field_style(self.confirm_password_input)
        layout.addRow("Confirmar Senha:", self.confirm_password_input)
        
        # Campo função
        self.role_select = QComboBox()
        self.role_select.setMinimumHeight(35)
        self.role_select.addItems(["operator", "admin"])
        self.role_select.setStyleSheet("""
            QComboBox {
                border: 2px solid #BDC3C7;
                border-radius: 5px;
                padding: 8px 12px;
                font-size: 14px;
                background-color: white;
                min-width: 150px;
            }
            QComboBox:focus {
                border-color: #3498DB;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #7F8C8D;
                width: 0px;
                height: 0px;
            }
        """)
        layout.addRow("Função:", self.role_select)
        
        # Descrição das funções
        roles_info = QLabel(
            "• <b>Operator</b>: Pode executar testes e gerenciar placas<br>"
            "• <b>Admin</b>: Acesso completo ao sistema"
        )
        roles_info.setStyleSheet("color: #7F8C8D; font-size: 11px; background-color: #F8F9FA; padding: 10px; border-radius: 5px;")
        roles_info.setWordWrap(True)
        layout.addRow("", roles_info)
        
        # Status
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #E74C3C; font-size: 11px; min-height: 16px;")
        layout.addRow("", self.status_label)
        
        return layout
        
    def create_buttons(self):
        """Cria botões de ação"""
        layout = QHBoxLayout()
        layout.setSpacing(10)
        
        # Botão cancelar
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setMinimumHeight(40)
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #95A5A6;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #7F8C8D;
            }
        """)
        self.cancel_button.clicked.connect(self.reject)
        
        # Botão cadastrar
        self.register_button = QPushButton("Cadastrar Usuário")
        self.register_button.setMinimumHeight(40)
        self.register_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.register_button.setStyleSheet("""
            QPushButton {
                background-color: #27AE60;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
            QPushButton:disabled {
                background-color: #BDC3C7;
                color: #7F8C8D;
            }
        """)
        self.register_button.clicked.connect(self.register_user)
        
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.register_button)
        
        return layout
        
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
            QLineEdit[error="true"] {
                border-color: #E74C3C;
                background-color: #FDEDEC;
            }
        """)
        
    def apply_styles(self):
        """Aplica estilos gerais"""
        self.setStyleSheet("""
            QDialog {
                background-color: #F8F9FA;
            }
            QLabel {
                background-color: transparent;
            }
        """)
        
    def validate_form(self):
        """Valida os dados do formulário"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        confirm_password = self.confirm_password_input.text().strip()
        
        # Limpa status anterior
        self.clear_errors()
        
        # Validações
        errors = []
        
        if not username:
            errors.append("Nome de usuário é obrigatório")
            self.mark_field_error(self.username_input)
            
        elif len(username) < 3:
            errors.append("Nome de usuário deve ter pelo menos 3 caracteres")
            self.mark_field_error(self.username_input)
            
        elif self.session.query(User).filter_by(username=username).first():
            errors.append("Nome de usuário já existe")
            self.mark_field_error(self.username_input)
            
        if not password:
            errors.append("Senha é obrigatória")
            self.mark_field_error(self.password_input)
            
        elif len(password) < 4:
            errors.append("Senha deve ter pelo menos 4 caracteres")
            self.mark_field_error(self.password_input)
            
        if password != confirm_password:
            errors.append("As senhas não coincidem")
            self.mark_field_error(self.password_input)
            self.mark_field_error(self.confirm_password_input)
            
        return errors
        
    def mark_field_error(self, field):
        """Marca campo com erro"""
        field.setProperty("error", "true")
        field.style().unpolish(field)
        field.style().polish(field)
        
    def clear_errors(self):
        """Remove marcações de erro dos campos"""
        for field in [self.username_input, self.password_input, self.confirm_password_input]:
            field.setProperty("error", "false")
            field.style().unpolish(field)
            field.style().polish(field)
        self.status_label.clear()
        
    def register_user(self):
        """Processa o cadastro do usuário"""
        errors = self.validate_form()
        
        if errors:
            self.status_label.setText("❌ " + " | ".join(errors))
            self.status_label.setStyleSheet("color: #E74C3C; font-size: 11px;")
            return
            
        try:
            username = self.username_input.text().strip()
            password = self.password_input.text().strip()
            role = self.role_select.currentText()
            
            # Cria novo usuário com hash
            from utils.security import hash_password
            hashed_password = hash_password(password)

            new_user = User(
                username=username,
                password_hash=hashed_password,
                role=role
            )
            
            self.session.add(new_user)
            self.session.commit()
            
            # Log da ação
            log_user_action(new_user, "user_registration", {"role": role})
            logger.info(f"Novo usuário cadastrado: {username} ({role})")
            
            self.new_username = username
            
            QMessageBox.information(
                self, 
                "Cadastro Concluído", 
                f"Usuário '{username}' cadastrado com sucesso!\n\n"
                f"Função: {role}\n"
                f"O usuário já pode fazer login no sistema."
            )
            
            self.accept()
            
        except Exception as e:
            logger.error(f"Erro ao cadastrar usuário: {e}")
            QMessageBox.critical(
                self,
                "Erro no Cadastro",
                f"Erro ao cadastrar usuário:\n{str(e)}"
            )
            
    def get_new_username(self):
        """Retorna o username do novo usuário cadastrado"""
        return self.new_username
        
    def keyPressEvent(self, event):
        """Trata pressionamento de teclas"""
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.register_user()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)