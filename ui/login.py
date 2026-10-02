# ui/login.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox,
    QHBoxLayout, QCheckBox, QFrame, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPixmap
from db.models import User
from ui.user_register import UserRegisterDialog
from engine.logger import log_user_action
import logging

logger = logging.getLogger(__name__)

class LoginDialog(QDialog):
    """Dialog de login com interface moderna"""
    
    # Sinal para indicar login bem-sucedido
    login_successful = pyqtSignal(object)  # Emite o objeto User
    
    def __init__(self, session):
        super().__init__()
        self.session = session
        self.user = None
        self.login_attempts = 0
        self.max_attempts = 3
        
        self.setup_ui()
        self.apply_styles()
        
    def setup_ui(self):
        """Configura a interface do usuário"""
        self.setWindowTitle("Sistema de Teste de Placas - Login")
        self.setFixedSize(400, 500)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | 
                           Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 20)
        
        # Cabeçalho
        header_layout = self.create_header()
        layout.addLayout(header_layout)
        
        # Formulário de login
        form_layout = self.create_login_form()
        layout.addLayout(form_layout)
        
        # Botões
        buttons_layout = self.create_buttons()
        layout.addLayout(buttons_layout)
        
        # Rodapé
        footer_layout = self.create_footer()
        layout.addLayout(footer_layout)
        
        self.setLayout(layout)
        
    def create_header(self):
        """Cria cabeçalho do login"""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Título
        title_label = QLabel("Sistema de Teste")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #2C3E50; margin-bottom: 5px;")
        
        # Subtítulo
        subtitle_label = QLabel("Laboratório Técnico")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setFont(QFont("Arial", 12))
        subtitle_label.setStyleSheet("color: #7F8C8D; margin-bottom: 20px;")
        
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        
        return layout
        
    def create_login_form(self):
        """Cria formulário de login"""
        layout = QVBoxLayout()
        layout.setSpacing(12)
        
        # Campo usuário
        user_layout = QVBoxLayout()
        user_label = QLabel("Usuário:")
        user_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        user_label.setStyleSheet("color: #2C3E50;")
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Digite seu nome de usuário")
        self.username_input.setMinimumHeight(40)
        self.username_input.setStyleSheet("""
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
        
        user_layout.addWidget(user_label)
        user_layout.addWidget(self.username_input)
        
        # Campo senha
        password_layout = QVBoxLayout()
        password_label = QLabel("Senha:")
        password_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        password_label.setStyleSheet("color: #2C3E50;")
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Digite sua senha")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMinimumHeight(40)
        self.password_input.setStyleSheet("""
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
        
        # Checkbox para mostrar senha
        self.show_password_cb = QCheckBox("Mostrar senha")
        self.show_password_cb.setStyleSheet("color: #7F8C8D; font-size: 12px;")
        self.show_password_cb.toggled.connect(self.toggle_password_visibility)
        
        password_layout.addWidget(password_label)
        password_layout.addWidget(self.password_input)
        password_layout.addWidget(self.show_password_cb)
        
        # Status do login
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #E74C3C; font-size: 11px; min-height: 16px;")
        
        # Barra de progresso (para simulação de carregamento)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimumHeight(4)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #ECF0F1;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #3498DB;
                border-radius: 2px;
            }
        """)
        
        layout.addLayout(user_layout)
        layout.addLayout(password_layout)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        
        return layout
        
    def create_buttons(self):
        """Cria botões de ação"""
        layout = QVBoxLayout()
        layout.setSpacing(8)
        
        # Botão de login
        self.login_button = QPushButton("Entrar no Sistema")
        self.login_button.setMinimumHeight(45)
        self.login_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_button.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
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
        """)
        self.login_button.clicked.connect(self.check_login)
        
        # Botão de cadastro
        self.register_button = QPushButton("Cadastrar Novo Usuário")
        self.register_button.setMinimumHeight(35)
        self.register_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.register_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #3498DB;
                border: 2px solid #3498DB;
                border-radius: 5px;
                font-size: 12px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #3498DB;
                color: white;
            }
        """)
        self.register_button.clicked.connect(self.open_register)
        
        layout.addWidget(self.login_button)
        layout.addWidget(self.register_button)
        
        return layout
        
    def create_footer(self):
        """Cria rodapé"""
        layout = QVBoxLayout()
        
        # Linha separadora
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("color: #BDC3C7; margin: 15px 0px;")
        
        # Informações de versão
        version_label = QLabel("Versão 2.0 - Laboratório Técnico © 2024")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("color: #95A5A6; font-size: 10px;")
        
        layout.addWidget(separator)
        layout.addWidget(version_label)
        
        return layout
        
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
        
    def toggle_password_visibility(self, checked):
        """Alterna entre mostrar e ocultar senha"""
        if checked:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
            
    def check_login(self):
        """Valida usuário e senha"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        # Validações básicas
        if not username:
            self.show_error("Por favor, informe o nome de usuário.")
            self.username_input.setFocus()
            return
            
        if not password:
            self.show_error("Por favor, informe a senha.")
            self.password_input.setFocus()
            return

        # Mostra progresso
        self.show_loading(True)
        self.status_label.clear()

        # Simula processamento (remove em produção)
        QTimer.singleShot(800, lambda: self._perform_login(username, password))

    def _perform_login(self, username, password):
        """Executa a validação do login"""
        try:
            user = self.session.query(User).filter_by(username=username).first()
            
            from utils.security import check_password
            if user and check_password(password, user.password_hash):
                if not user.is_active:
                    self.show_error("Usuário desativado. Contate o administrador.")
                    self.show_loading(False)
                    return
                    
                # Login bem-sucedido
                self.user = user
                logger.info(f"Login bem-sucedido: {username}")
                log_user_action(user, "login", {"status": "success"})
                
                self.status_label.setText("✅ Login bem-sucedido!")
                self.status_label.setStyleSheet("color: #27AE60; font-size: 11px;")
                
                # Aguarda um pouco antes de fechar
                QTimer.singleShot(500, self.accept)
                
            else:
                self.login_attempts += 1
                attempts_left = self.max_attempts - self.login_attempts
                
                if attempts_left > 0:
                    self.show_error(f"Usuário ou senha inválidos. Tentativas restantes: {attempts_left}")
                    logger.warning(f"Tentativa de login falhou: {username} (tentativa {self.login_attempts})")
                else:
                    self.show_error("Número máximo de tentativas excedido. Tente novamente mais tarde.")
                    self.login_button.setEnabled(False)
                    logger.warning(f"Login bloqueado para usuário: {username}")
                    
                # Limpa campos
                self.password_input.clear()
                self.password_input.setFocus()
                
        except Exception as e:
            logger.error(f"Erro durante login: {e}")
            self.show_error("Erro interno do sistema. Tente novamente.")
            
        finally:
            self.show_loading(False)

    def show_error(self, message):
        """Exibe mensagem de erro"""
        self.status_label.setText(f"❌ {message}")
        self.status_label.setStyleSheet("color: #E74C3C; font-size: 11px;")
        
        # Efeito de shake no formulário
        self.shake_form()

    def shake_form(self):
        """Efeito de shake para indicar erro"""
        import math
        original_pos = self.pos()
        
        def animate_shake(step):
            if step >= 10:
                self.move(original_pos)
                return
                
            x = original_pos.x() + math.sin(step * 2) * 5
            self.move(int(x), original_pos.y())
            QTimer.singleShot(30, lambda: animate_shake(step + 1))
            
        animate_shake(0)

    def show_loading(self, show):
        """Mostra/oculta indicador de carregamento"""
        self.progress_bar.setVisible(show)
        self.login_button.setEnabled(not show)
        self.register_button.setEnabled(not show)
        
        if show:
            self.progress_bar.setRange(0, 0)  # Progresso indeterminado
        else:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)

    def open_register(self):
        """Abre tela de cadastro de novo usuário"""
        dialog = UserRegisterDialog(self.session)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Se um novo usuário foi cadastrado, preenche o campo de usuário
            new_username = dialog.get_new_username()
            if new_username:
                self.username_input.setText(new_username)
                self.password_input.setFocus()
                
            self.status_label.setText("✅ Usuário cadastrado com sucesso!")
            self.status_label.setStyleSheet("color: #27AE60; font-size: 11px;")

    def keyPressEvent(self, event):
        """Trata pressionamento de teclas"""
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.check_login()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    def get_user(self):
        """Retorna o usuário logado"""
        return self.user