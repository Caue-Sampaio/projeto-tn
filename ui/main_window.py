from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QVariantAnimation, QEasingCurve, QSize
from PyQt6.QtGui import QFont, QIcon
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
from .reference_measurements import ReferenceMeasurements


class SidebarButton(QPushButton):
    """Botão de navegação que suporta os modos expandido e compacto."""

    def __init__(self, text, icon=""):
        super().__init__()
        self.label_text = text
        self.icon_text = icon
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(46)
        self.set_compact(False)

    def set_compact(self, compact: bool):
        if compact:
            self.setText(self.icon_text)
            self.setToolTip(self.label_text)
            align = "center"
            padding = "0"
            margin = "3px 10px"
        else:
            self.setText(f"{self.icon_text}   {self.label_text}")
            self.setToolTip("")
            align = "left"
            padding = "0 14px"
            margin = "3px 12px"

        self.setStyleSheet(
            f"""
            QPushButton {{
                text-align: {align};
                padding: {padding};
                margin: {margin};
                background: transparent;
                color: #A9B7CA;
                border: 1px solid transparent;
                border-left: 3px solid transparent;
                border-radius: 7px;
                font-family: 'Segoe UI';
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #151F31;
                color: #F8FAFC;
                border-color: #26364D;
                border-left-color: #38526F;
            }}
            QPushButton:checked {{
                background: #113331;
                color: #F8FAFC;
                border-color: #164E4A;
                border-left-color: #2DD4BF;
                font-weight: 700;
            }}
            QPushButton:pressed {{
                background: #0D2A29;
            }}
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
        self.sidebar_expanded_width = 258
        self.sidebar_collapsed_width = 76
        self.sidebar_collapsed = False

        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(self.sidebar_expanded_width)
        self.sidebar.setStyleSheet(
            """
            QFrame#sidebar {
                background: #0B1220;
                border-right: 1px solid #1E293B;
            }
            QFrame#sidebarHeader {
                background: transparent;
                border: none;
                border-bottom: 1px solid #172033;
            }
            QFrame#userCard {
                background: #0F1929;
                border: 1px solid #1E2B40;
                border-radius: 9px;
            }
            QLabel#brandTitle {
                color: #F8FAFC;
                font: 700 14px 'Segoe UI';
            }
            QLabel#brandSubtitle {
                color: #2DD4BF;
                font: 700 9px 'Segoe UI';
                letter-spacing: 1px;
            }
            QLabel#navSection {
                color: #5F7189;
                font: 700 9px 'Segoe UI';
                letter-spacing: 1px;
                padding-left: 14px;
            }
            QLabel#avatarLabel {
                color: #5EEAD4;
                background: #123C3A;
                border: 1px solid #17645F;
                border-radius: 16px;
                font: 700 10px 'Segoe UI';
            }
            QLabel#userName {
                color: #E5EDF7;
                font: 600 11px 'Segoe UI';
            }
            QLabel#userRole {
                color: #71839A;
                font: 9px 'Segoe UI';
            }
            QPushButton#sidebarToggle {
                background: #101B2C;
                color: #94A3B8;
                border: 1px solid #233249;
                border-radius: 7px;
                font: 700 15px 'Segoe UI';
            }
            QPushButton#sidebarToggle:hover {
                color: #5EEAD4;
                border-color: #2A6F69;
                background: #13283A;
            }
            QPushButton#sidebarToggle:pressed {
                background: #0F2531;
                border-color: #2DD4BF;
            }
            """
        )

        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 12)
        self.sidebar_layout.setSpacing(4)

        # ── Cabeçalho da sidebar ───────────────────────────────────────
        self.sidebar_header = QFrame()
        self.sidebar_header.setObjectName("sidebarHeader")
        self.sidebar_header.setFixedHeight(82)
        header_layout = QHBoxLayout(self.sidebar_header)
        header_layout.setContentsMargins(16, 12, 12, 12)
        header_layout.setSpacing(8)

        self.brand_box = QWidget()
        brand_layout = QVBoxLayout(self.brand_box)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(1)

        self.brand_title = QLabel("TN ELETROSISTEM")
        self.brand_title.setObjectName("brandTitle")
        self.brand_subtitle = QLabel("TESTFLOW / LAB")
        self.brand_subtitle.setObjectName("brandSubtitle")
        brand_layout.addWidget(self.brand_title)
        brand_layout.addWidget(self.brand_subtitle)

        header_layout.addWidget(self.brand_box, 1)

        self.sidebar_toggle = QPushButton("")
        self.sidebar_toggle.setObjectName("sidebarToggle")
        self.sidebar_toggle.setFixedSize(32, 32)
        self.sidebar_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sidebar_toggle.setToolTip("Recolher menu")

        # Ícone oficial do botão retrátil da sidebar. Ele fica visível tanto
        # com a barra aberta quanto com a barra recolhida.
        project_root = Path(__file__).resolve().parent.parent
        sidebar_icon_path = project_root / "emblema_futurista_tn_em_circuito_neon.ico"
        self.sidebar_logo_icon = (
            QIcon(str(sidebar_icon_path)) if sidebar_icon_path.exists() else QIcon()
        )

        # O botão usa sempre o logo. O tamanho do ícone muda conforme o estado
        # da sidebar, mas a identidade visual permanece a mesma.
        if not self.sidebar_logo_icon.isNull():
            self.sidebar_toggle.setText("")
            self.sidebar_toggle.setIcon(self.sidebar_logo_icon)
            self.sidebar_toggle.setIconSize(QSize(25, 25))

        self.sidebar_toggle.clicked.connect(self.toggle_sidebar)
        header_layout.addWidget(self.sidebar_toggle, 0, Qt.AlignmentFlag.AlignVCenter)

        self.sidebar_layout.addWidget(self.sidebar_header)

        self.nav_section = QLabel("NAVEGAÇÃO")
        self.nav_section.setObjectName("navSection")
        self.nav_section.setFixedHeight(30)
        self.nav_section.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.sidebar_layout.addWidget(self.nav_section)

        # Ícones em caracteres simples para manter aparência estável no Windows.
        self.btn_dashboard = SidebarButton("Dashboard", "▦")
        self.btn_placas = SidebarButton("Placas", "▣")
        self.btn_testes = SidebarButton("Testes", "▶")
        self.btn_referencias = SidebarButton("Referências", "◇")
        self.btn_logout = SidebarButton("Sair", "↪")

        self.buttons = [
            self.btn_dashboard,
            self.btn_placas,
            self.btn_testes,
            self.btn_referencias,
        ]

        self.btn_dashboard.clicked.connect(lambda: self.switch_tab(0, self.btn_dashboard))
        self.btn_placas.clicked.connect(lambda: self.switch_tab(1, self.btn_placas))
        self.btn_testes.clicked.connect(lambda: self.switch_tab(2, self.btn_testes))
        self.btn_referencias.clicked.connect(lambda: self.switch_tab(3, self.btn_referencias))
        self.btn_logout.clicked.connect(self.close)

        self.sidebar_layout.addWidget(self.btn_dashboard)
        self.sidebar_layout.addWidget(self.btn_placas)
        self.sidebar_layout.addWidget(self.btn_testes)
        self.sidebar_layout.addWidget(self.btn_referencias)
        self.sidebar_layout.addStretch(1)

        # ── Usuário ────────────────────────────────────────────────────
        self.user_card = QFrame()
        self.user_card.setObjectName("userCard")
        user_layout = QHBoxLayout(self.user_card)
        user_layout.setContentsMargins(10, 9, 10, 9)
        user_layout.setSpacing(9)

        username = str(getattr(self.current_user, "username", "Usuário") or "Usuário")
        role = str(getattr(self.current_user, "role", "Operador") or "Operador")
        initials = "".join(part[:1].upper() for part in username.split()[:2]) or "U"

        self.user_avatar = QLabel(initials[:2])
        self.user_avatar.setObjectName("avatarLabel")
        self.user_avatar.setFixedSize(34, 34)
        self.user_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        user_layout.addWidget(self.user_avatar)

        self.user_text_box = QWidget()
        user_text_layout = QVBoxLayout(self.user_text_box)
        user_text_layout.setContentsMargins(0, 0, 0, 0)
        user_text_layout.setSpacing(0)
        self.user_name_label = QLabel(username)
        self.user_name_label.setObjectName("userName")
        self.user_role_label = QLabel(role)
        self.user_role_label.setObjectName("userRole")
        user_text_layout.addWidget(self.user_name_label)
        user_text_layout.addWidget(self.user_role_label)
        user_layout.addWidget(self.user_text_box, 1)

        self.sidebar_layout.addWidget(self.user_card)
        self.sidebar_layout.addWidget(self.btn_logout)

        # Animação curta apenas para largura; não interfere no conteúdo central.
        self.sidebar_animation = QVariantAnimation(self)
        self.sidebar_animation.setDuration(170)
        self.sidebar_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.sidebar_animation.valueChanged.connect(
            lambda value: self.sidebar.setFixedWidth(int(value))
        )

        self.main_layout.addWidget(self.sidebar)

    def toggle_sidebar(self):
        """Recolhe/expande a navegação mantendo a aba ativa."""
        start_width = self.sidebar.width()
        self.sidebar_collapsed = not self.sidebar_collapsed
        end_width = (
            self.sidebar_collapsed_width
            if self.sidebar_collapsed
            else self.sidebar_expanded_width
        )

        # Atualiza o conteúdo antes da animação para não haver quebra de texto.
        self._apply_sidebar_state()

        self.sidebar_animation.stop()
        self.sidebar_animation.setStartValue(start_width)
        self.sidebar_animation.setEndValue(end_width)
        self.sidebar_animation.start()

    def _apply_sidebar_state(self):
        compact = self.sidebar_collapsed

        self.brand_box.setVisible(not compact)
        self.nav_section.setVisible(not compact)
        self.user_text_box.setVisible(not compact)

        # O logo fica no botão nos dois estados. Recolhida, ele cresce um pouco
        # e passa a funcionar como o principal elemento visual para reabrir a barra.
        self.sidebar_toggle.setText("")
        if not self.sidebar_logo_icon.isNull():
            self.sidebar_toggle.setIcon(self.sidebar_logo_icon)

        if compact:
            self.sidebar_toggle.setIconSize(QSize(36, 36))
            self.sidebar_toggle.setFixedSize(48, 48)
            self.sidebar_toggle.setToolTip("Expandir menu")
        else:
            self.sidebar_toggle.setIconSize(QSize(25, 25))
            self.sidebar_toggle.setFixedSize(34, 34)
            self.sidebar_toggle.setToolTip("Recolher menu")

        # Mantém o botão sempre visível e perfeitamente centralizado quando compacto.
        header_layout = self.sidebar_header.layout()
        if compact:
            header_layout.setContentsMargins(16, 10, 16, 10)
        else:
            header_layout.setContentsMargins(16, 12, 12, 12)

        for btn in [*self.buttons, self.btn_logout]:
            btn.set_compact(compact)

        if compact:
            self.user_card.setToolTip(
                f"{getattr(self.current_user, 'username', 'Usuário')} • "
                f"{getattr(self.current_user, 'role', 'Operador')}"
            )
            self.user_card.layout().setContentsMargins(10, 9, 10, 9)
        else:
            self.user_card.setToolTip("")
            self.user_card.layout().setContentsMargins(10, 9, 10, 9)

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

        self.referencias_view = ReferenceMeasurements(
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
        self.stack.addWidget(
            self.referencias_view
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

        elif index == 3:
            self.referencias_view.refresh_boards()

    def closeEvent(self, event):
        # Encerra a thread/VISA da aba de referências antes de fechar o app.
        try:
            if hasattr(self, "referencias_view"):
                self.referencias_view.shutdown()
        except Exception:
            pass
        super().closeEvent(event)

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