# ui/login.py
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox,
    QHBoxLayout, QCheckBox, QFrame, QProgressBar
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont

from db.models import User
from ui.user_register import UserRegisterDialog
from engine.logger import log_user_action
import logging

logger = logging.getLogger(__name__)


class LoginDialog(QDialog):
    """Dialog de login com visual alinhado ao restante do sistema."""

    login_successful = pyqtSignal(object)

    def __init__(self, session):
        super().__init__()
        self.session = session
        self.user = None
        self.login_attempts = 0
        self.max_attempts = 3

        self.setup_ui()
        self.apply_styles()

    def setup_ui(self):
        """Configura a interface do usuário."""
        self.setObjectName("loginDialog")
        self.setWindowTitle("TN Eletrosistem - Login")

        # Evita compressão/overlap em escalas de tela diferentes.
        # A janela continua compacta, mas pode crescer caso o sistema use DPI alto.
        self.setMinimumSize(440, 590)
        self.resize(460, 610)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 18)
        root.setSpacing(14)

        root.addWidget(self.create_header())
        root.addWidget(self.create_login_card(), 1)
        root.addLayout(self.create_footer())

        self.username_input.setFocus()

    def create_header(self):
        """Cabeçalho compacto seguindo a paleta já usada no programa."""
        header = QFrame()
        header.setObjectName("loginHeader")

        layout = QVBoxLayout(header)
        layout.setContentsMargins(20, 17, 20, 17)
        layout.setSpacing(4)

        eyebrow = QLabel("TN ELETROSISTEM")
        eyebrow.setObjectName("loginEyebrow")

        title = QLabel("Acesso ao sistema")
        title.setObjectName("loginTitle")

        subtitle = QLabel("Instrumentação, mapeamento e testes de placas eletrônicas")
        subtitle.setObjectName("loginSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return header

    def create_login_card(self):
        """Card principal com formulário e ações."""
        card = QFrame()
        card.setObjectName("loginCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        intro = QLabel("Entre com suas credenciais")
        intro.setObjectName("formTitle")
        layout.addWidget(intro)

        description = QLabel("Use seu usuário cadastrado para continuar.")
        description.setObjectName("formSubtitle")
        layout.addWidget(description)

        layout.addSpacing(4)
        layout.addLayout(self.create_login_form())
        layout.addSpacing(2)
        layout.addLayout(self.create_buttons())
        return card

    def create_login_form(self):
        """Cria formulário de login com espaçamento robusto."""
        layout = QVBoxLayout()
        layout.setSpacing(12)

        # Usuário
        user_block = QVBoxLayout()
        user_block.setSpacing(6)

        user_label = QLabel("Usuário")
        user_label.setObjectName("fieldLabel")

        self.username_input = QLineEdit()
        self.username_input.setObjectName("loginInput")
        self.username_input.setPlaceholderText("Digite seu nome de usuário")
        self.username_input.setMinimumHeight(44)
        self.username_input.setClearButtonEnabled(True)

        user_block.addWidget(user_label)
        user_block.addWidget(self.username_input)

        # Senha
        password_block = QVBoxLayout()
        password_block.setSpacing(6)

        password_label = QLabel("Senha")
        password_label.setObjectName("fieldLabel")

        self.password_input = QLineEdit()
        self.password_input.setObjectName("loginInput")
        self.password_input.setPlaceholderText("Digite sua senha")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMinimumHeight(44)

        # Mantido deliberadamente FORA do campo de senha. Em versões anteriores,
        # o controle podia ficar visualmente sobreposto ao input em alguns DPI.
        show_row = QHBoxLayout()
        show_row.setContentsMargins(0, 0, 0, 0)
        show_row.setSpacing(0)
        show_row.addStretch(1)

        self.show_password_cb = QCheckBox("Mostrar senha")
        self.show_password_cb.setObjectName("showPassword")
        self.show_password_cb.setMinimumHeight(22)
        self.show_password_cb.toggled.connect(self.toggle_password_visibility)
        show_row.addWidget(self.show_password_cb)

        password_block.addWidget(password_label)
        password_block.addWidget(self.password_input)
        password_block.addLayout(show_row)

        # Mensagens de estado
        self.status_label = QLabel("")
        self.status_label.setObjectName("loginStatus")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(20)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("loginProgress")
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)

        layout.addLayout(user_block)
        layout.addLayout(password_block)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        return layout

    def create_buttons(self):
        """Cria botões de ação."""
        layout = QVBoxLayout()
        layout.setSpacing(9)

        self.login_button = QPushButton("Entrar no sistema")
        self.login_button.setObjectName("primaryLoginButton")
        self.login_button.setMinimumHeight(44)
        self.login_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_button.clicked.connect(self.check_login)

        self.register_button = QPushButton("Cadastrar novo usuário")
        self.register_button.setObjectName("secondaryLoginButton")
        self.register_button.setMinimumHeight(40)
        self.register_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.register_button.clicked.connect(self.open_register)

        layout.addWidget(self.login_button)
        layout.addWidget(self.register_button)
        return layout

    def create_footer(self):
        """Cria rodapé discreto."""
        layout = QVBoxLayout()
        layout.setSpacing(6)

        version_label = QLabel("TN Eletrosistem • Versão 2.0")
        version_label.setObjectName("loginFooter")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)
        return layout

    def apply_styles(self):
        """Aplica a paleta já usada nas demais telas refatoradas."""
        self.setStyleSheet(
            """
            QDialog#loginDialog {
                background-color: #F4F7F9;
                color: #0F172A;
            }

            QFrame#loginHeader {
                background-color: #0F172A;
                border: 1px solid #1E293B;
                border-radius: 12px;
            }

            QLabel#loginEyebrow {
                color: #2DD4BF;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            QLabel#loginTitle {
                color: #FFFFFF;
                font-size: 20px;
                font-weight: 700;
            }

            QLabel#loginSubtitle {
                color: #CBD5E1;
                font-size: 11px;
            }

            QFrame#loginCard {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 11px;
            }

            QLabel#formTitle {
                color: #0F172A;
                font-size: 15px;
                font-weight: 700;
            }

            QLabel#formSubtitle {
                color: #64748B;
                font-size: 11px;
            }

            QLabel#fieldLabel {
                color: #334155;
                font-size: 11px;
                font-weight: 700;
            }

            QLineEdit#loginInput {
                background-color: #FFFFFF;
                color: #0F172A;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 8px 11px;
                font-size: 13px;
                selection-background-color: #CCFBF1;
                selection-color: #0F172A;
            }

            QLineEdit#loginInput:hover {
                border-color: #94A3B8;
            }

            QLineEdit#loginInput:focus {
                border: 1px solid #0F766E;
                background-color: #FFFFFF;
            }

            QCheckBox#showPassword {
                color: #475569;
                font-size: 11px;
                spacing: 6px;
                padding: 1px 0px;
            }

            QCheckBox#showPassword::indicator {
                width: 15px;
                height: 15px;
            }

            QLabel#loginStatus {
                color: #B91C1C;
                font-size: 11px;
            }

            QProgressBar#loginProgress {
                border: none;
                background-color: #E2E8F0;
                border-radius: 2px;
            }

            QProgressBar#loginProgress::chunk {
                background-color: #14B8A6;
                border-radius: 2px;
            }

            QPushButton#primaryLoginButton {
                background-color: #0F766E;
                color: #FFFFFF;
                border: 1px solid #0F766E;
                border-radius: 8px;
                padding: 9px 14px;
                font-size: 12px;
                font-weight: 700;
            }

            QPushButton#primaryLoginButton:hover {
                background-color: #115E59;
                border-color: #115E59;
            }

            QPushButton#primaryLoginButton:pressed {
                background-color: #134E4A;
                border-color: #134E4A;
            }

            QPushButton#primaryLoginButton:disabled {
                background-color: #CBD5E1;
                color: #64748B;
                border-color: #CBD5E1;
            }

            QPushButton#secondaryLoginButton {
                background-color: #FFFFFF;
                color: #0F766E;
                border: 1px solid #99F6E4;
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 11px;
                font-weight: 700;
            }

            QPushButton#secondaryLoginButton:hover {
                background-color: #F0FDFA;
                border-color: #14B8A6;
            }

            QPushButton#secondaryLoginButton:disabled {
                color: #94A3B8;
                border-color: #E2E8F0;
                background-color: #F8FAFC;
            }

            QLabel#loginFooter {
                color: #94A3B8;
                font-size: 10px;
            }
            """
        )

    def toggle_password_visibility(self, checked):
        """Alterna entre mostrar e ocultar senha."""
        if checked:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

    def check_login(self):
        """Valida usuário e senha."""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username:
            self.show_error("Por favor, informe o nome de usuário.")
            self.username_input.setFocus()
            return

        if not password:
            self.show_error("Por favor, informe a senha.")
            self.password_input.setFocus()
            return

        self.show_loading(True)
        self.status_label.clear()

        QTimer.singleShot(800, lambda: self._perform_login(username, password))

    def _perform_login(self, username, password):
        """Executa a validação do login."""
        try:
            user = self.session.query(User).filter_by(username=username).first()

            from utils.security import check_password

            if user and check_password(password, user.password_hash):
                if not user.is_active:
                    self.show_error("Usuário desativado. Contate o administrador.")
                    self.show_loading(False)
                    return

                self.user = user
                logger.info(f"Login bem-sucedido: {username}")
                log_user_action(user, "login", {"status": "success"})

                self.status_label.setText("Login bem-sucedido!")
                self.status_label.setStyleSheet(
                    "color: #0F766E; font-size: 11px; font-weight: 600;"
                )

                QTimer.singleShot(500, self.accept)

            else:
                self.login_attempts += 1
                attempts_left = self.max_attempts - self.login_attempts

                if attempts_left > 0:
                    self.show_error(
                        f"Usuário ou senha inválidos. Tentativas restantes: {attempts_left}"
                    )
                    logger.warning(
                        f"Tentativa de login falhou: {username} "
                        f"(tentativa {self.login_attempts})"
                    )
                else:
                    self.show_error(
                        "Número máximo de tentativas excedido. Tente novamente mais tarde."
                    )
                    self.login_button.setEnabled(False)
                    logger.warning(f"Login bloqueado para usuário: {username}")

                self.password_input.clear()
                self.password_input.setFocus()

        except Exception as e:
            logger.error(f"Erro durante login: {e}")
            self.show_error("Erro interno do sistema. Tente novamente.")

        finally:
            self.show_loading(False)

    def show_error(self, message):
        """Exibe mensagem de erro."""
        self.status_label.setText(message)
        self.status_label.setStyleSheet(
            "color: #B91C1C; font-size: 11px; font-weight: 600;"
        )
        self.shake_form()

    def shake_form(self):
        """Efeito de shake para indicar erro."""
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
        """Mostra/oculta indicador de carregamento."""
        self.progress_bar.setVisible(show)
        self.login_button.setEnabled(not show)
        self.register_button.setEnabled(not show)

        if show:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)

    def open_register(self):
        """Abre tela de cadastro de novo usuário."""
        dialog = UserRegisterDialog(self.session)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_username = dialog.get_new_username()
            if new_username:
                self.username_input.setText(new_username)
                self.password_input.setFocus()

            self.status_label.setText("Usuário cadastrado com sucesso!")
            self.status_label.setStyleSheet(
                "color: #0F766E; font-size: 11px; font-weight: 600;"
            )

    def keyPressEvent(self, event):
        """Trata pressionamento de teclas."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.check_login()
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    def get_user(self):
        """Retorna o usuário logado."""
        return self.user
