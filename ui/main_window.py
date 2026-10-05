from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .dashboard import Dashboard
from .placa_tab import PlacaTab
from .test_executor import TestExecutor


class SidebarButton(QPushButton):
    def __init__(self, text, icon=""):
        super().__init__(f"{icon} {text}")

        self.setCheckable(True)
        self.setMinimumHeight(45)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setStyleSheet(
            """
            QPushButton {
                text-align: left;
                padding-left: 15px;
                background-color: transparent;
                color: #ECF0F1;
                border: none;
                font-size: 14px;
                font-weight: bold;
                border-radius: 5px;
                margin: 2px 10px;
            }

            QPushButton:hover {
                background-color: #34495E;
            }

            QPushButton:checked {
                background-color: #0F766E;
                color: white;
            }
            """
        )


class MainWindow(QMainWindow):
    def __init__(self, session, current_user, backup_manager):
        super().__init__()

        self.session = session
        self.current_user = current_user
        self.backup_manager = backup_manager

        self.setWindowTitle("TN Eletrosistem - TestFlow")
        self.setMinimumSize(1200, 800)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.setup_sidebar()
        self.setup_content_area()

        self.btn_dashboard.setChecked(True)
        self.stack.setCurrentIndex(0)

    def setup_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(250)

        self.sidebar.setStyleSheet(
            """
            QFrame {
                background-color: #0F172A;
                border-right: 1px solid #134E4A;
            }
            """
        )

        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(0, 20, 0, 20)
        self.sidebar_layout.setSpacing(5)

        title = QLabel("TN ELETROSISTEM")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setStyleSheet(
            "color: #2DD4BF; padding: 0 15px;"
        )
        self.sidebar_layout.addWidget(title)

        subtitle = QLabel("TEST SYSTEM")
        subtitle.setFont(QFont("Arial", 10))
        subtitle.setStyleSheet(
            "color: #CBD5E1; "
            "padding: 0 15px; "
            "margin-bottom: 20px;"
        )
        self.sidebar_layout.addWidget(subtitle)

        self.btn_dashboard = SidebarButton("Dashboard", "📊")
        self.btn_placas = SidebarButton("Placas", "🔌")
        self.btn_testes = SidebarButton("Testes", "🧪")
        self.btn_logout = SidebarButton("Sair", "🚪")

        self.buttons = [
            self.btn_dashboard,
            self.btn_placas,
            self.btn_testes,
        ]

        self.btn_dashboard.clicked.connect(
            lambda: self.switch_tab(
                0,
                self.btn_dashboard,
            )
        )

        self.btn_placas.clicked.connect(
            lambda: self.switch_tab(
                1,
                self.btn_placas,
            )
        )

        self.btn_testes.clicked.connect(
            lambda: self.switch_tab(
                2,
                self.btn_testes,
            )
        )

        self.btn_logout.clicked.connect(
            self.close
        )

        self.sidebar_layout.addWidget(
            self.btn_dashboard
        )
        self.sidebar_layout.addWidget(
            self.btn_placas
        )
        self.sidebar_layout.addWidget(
            self.btn_testes
        )

        self.sidebar_layout.addStretch()

        user_info = QLabel(
            f"👤 {self.current_user.username}\n"
            f"🛡️ {self.current_user.role}"
        )

        user_info.setStyleSheet(
            "color: #94A3B8; "
            "padding: 15px; "
            "font-size: 12px;"
        )

        self.sidebar_layout.addWidget(user_info)
        self.sidebar_layout.addWidget(
            self.btn_logout
        )

        self.main_layout.addWidget(
            self.sidebar
        )

    def setup_content_area(self):
        self.content_area = QWidget()
        self.content_area.setObjectName("contentArea")
        # IMPORTANTE: com seletor. Sem ele, o fundo claro era aplicado a TODOS os
        # widgets filhos (inclusive botões dos diálogos de seleção), deixando o
        # texto branco dos botões invisível.
        self.content_area.setStyleSheet(
            "QWidget#contentArea { background-color: #F4F7F9; }"
        )

        self.content_layout = QVBoxLayout(
            self.content_area
        )
        self.content_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self.stack = QStackedWidget()

        self.dashboard_view = Dashboard(
            self.session,
            self.current_user,
        )

        self.testes_view = TestExecutor(
            self.session,
            self.current_user,
        )

        def import_to_test(board):
            self.testes_view.import_board_for_test(
                board
            )

            self.switch_tab(
                2,
                self.btn_testes,
            )

        self.placas_view = PlacaTab(
            self.session,
            import_to_test,
            current_user=self.current_user,
        )

        self.dashboard_view.action_requested.connect(
            self.handle_dashboard_action
        )

        self.stack.addWidget(
            self.dashboard_view
        )
        self.stack.addWidget(
            self.placas_view
        )
        self.stack.addWidget(
            self.testes_view
        )

        self.content_layout.addWidget(
            self.stack
        )

        self.main_layout.addWidget(
            self.content_area
        )

    def switch_tab(self, index, button):
        for btn in self.buttons:
            btn.setChecked(False)

        button.setChecked(True)
        self.stack.setCurrentIndex(index)

        if index == 0:
            self.dashboard_view.refresh_stats()

        elif index == 1:
            self.placas_view.refresh_boards()

    def handle_dashboard_action(self, action_id):
        """Navega para a área correspondente sem iniciar ações automaticamente.

        Os cards do dashboard funcionam somente como atalhos de navegação.
        Seleção de placa, cadastro de pontos, importação de imagem, edição de
        plano e geração de relatório continuam sendo iniciados pelo usuário
        dentro da aba apropriada.
        """

        # Área de cadastro/consulta de placas e imagens.
        if action_id in {"projects", "import_image"}:
            self.switch_tab(
                1,
                self.btn_placas,
            )
            return

        # Área operacional de mapeamento, planos, execução e relatórios.
        if action_id in {"mapping", "pins", "report"}:
            self.switch_tab(
                2,
                self.btn_testes,
            )
            return

        # Compatibilidade com atalhos antigos que possam voltar ao dashboard.
        if action_id == "components":
            self.switch_tab(
                1,
                self.btn_placas,
            )

        elif action_id == "settings":
            self._show_settings_info()

        elif action_id == "help":
            self._show_help()

    def _dashboard_import_image(self):
        self.switch_tab(
            1,
            self.btn_placas,
        )

        if self.placas_view.current_board:
            QTimer.singleShot(
                0,
                self.placas_view.add_image,
            )
            return

        QMessageBox.information(
            self,
            "Importar imagem",
            (
                "Selecione uma placa cadastrada.\n\n"
                "Depois use a opção de adicionar imagem "
                "para importar a foto da PCB."
            ),
        )

    def _dashboard_components(self):
        self.switch_tab(
            1,
            self.btn_placas,
        )

        QMessageBox.information(
            self,
            "Análise de componentes",
            (
                "O projeto atual já possui cadastro de "
                "componentes e mapeamento visual, porém a "
                "detecção automática por visão computacional "
                "ainda não está implementada.\n\n"
                "Nesta versão, selecione uma placa para "
                "trabalhar com seu cadastro e suas imagens."
            ),
        )

    def _prepare_board_in_test_executor(self):
        board = self.placas_view.current_board

        if board is not None:
            self.testes_view.import_board_for_test(
                board
            )

        self.switch_tab(
            2,
            self.btn_testes,
        )

        return board

    def _dashboard_mapping(self):
        board = (
            self._prepare_board_in_test_executor()
        )

        if board is None:
            QMessageBox.information(
                self,
                "Mapeamento",
                (
                    "Selecione uma placa na tela de Testes "
                    "e depois clique em "
                    "'Mapear / Editar Pontos'."
                ),
            )
            return

        QTimer.singleShot(
            0,
            self.testes_view.open_image_marker_edit,
        )

    def _dashboard_pins(self):
        board = (
            self._prepare_board_in_test_executor()
        )

        if board is None:
            QMessageBox.information(
                self,
                "Pinos e plano de testes",
                (
                    "Selecione uma placa na tela de Testes. "
                    "Depois você poderá criar um plano e "
                    "associar as etapas aos pontos mapeados."
                ),
            )
            return

        QTimer.singleShot(
            0,
            self.testes_view.open_plan_editor,
        )

    def _dashboard_report(self):
        self.switch_tab(
            2,
            self.btn_testes,
        )

        if self.testes_view.last_run is None:
            QMessageBox.information(
                self,
                "Relatório",
                (
                    "Nenhum teste foi executado nesta sessão.\n\n"
                    "Execute um plano de teste primeiro. "
                    "Ao final, o relatório poderá ser "
                    "exportado em PDF."
                ),
            )
            return

        QTimer.singleShot(
            0,
            self.testes_view.generate_report,
        )

    def _show_settings_info(self):
        QMessageBox.information(
            self,
            "Configurações",
            (
                "Configurações disponíveis nesta versão:\n\n"
                "• Banco de dados configurado pelo projeto\n"
                "• Backup automático\n"
                "• Cadastro de placas e modelos\n"
                "• Planos e instrumentos de teste\n\n"
                "Uma tela dedicada de configurações pode "
                "ser adicionada em uma próxima etapa."
            ),
        )

    def _show_help(self):
        QMessageBox.information(
            self,
            "Ajuda rápida",
            (
                "FLUXO RECOMENDADO\n\n"
                "1. Cadastre ou selecione uma placa.\n"
                "2. Adicione uma imagem da PCB.\n"
                "3. Envie a placa para a área de Testes.\n"
                "4. Abra o mapeamento e marque os pontos.\n"
                "5. Crie um plano de testes.\n"
                "6. Execute as medições.\n"
                "7. Exporte o relatório em PDF.\n\n"
                "O Dashboard funciona como acesso rápido "
                "para essas etapas."
            ),
        )

    def dummy_callback(self, board):
        pass