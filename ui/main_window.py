from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QLabel,
    QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from .dashboard import Dashboard
from .placa_tab import PlacaTab
from .test_executor import TestExecutor


class SidebarButton(QPushButton):
    def __init__(self, text, icon=""):
        super().__init__(f"{icon} {text}")
        self.setCheckable(True)
        self.setMinimumHeight(45)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
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
                background-color: #3498DB;
                color: white;
            }
        """)


class MainWindow(QMainWindow):
    def __init__(self, session, current_user, backup_manager):
        super().__init__()

        self.session = session
        self.current_user = current_user
        self.backup_manager = backup_manager

        self.setWindowTitle("TN Eletrosistem - TestFlow")
        self.setMinimumSize(1200, 800)

        # Central widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.setup_sidebar()
        self.setup_content_area()

        # Initial selection
        self.btn_dashboard.setChecked(True)
        self.stack.setCurrentIndex(0)

    def setup_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(250)
        self.sidebar.setStyleSheet("""
            QFrame {
                background-color: #2C3E50;
                border-right: 1px solid #1ABC9C;
            }
        """)

        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(0, 20, 0, 20)
        self.sidebar_layout.setSpacing(5)

        # Logo / Title
        title = QLabel("TN ELETROSISTEM")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #1ABC9C; padding: 0 15px;")
        self.sidebar_layout.addWidget(title)

        subtitle = QLabel("TEST SYSTEM")
        subtitle.setFont(QFont("Arial", 10))
        subtitle.setStyleSheet(
            "color: #ECF0F1; "
            "padding: 0 15px; "
            "margin-bottom: 20px;"
        )
        self.sidebar_layout.addWidget(subtitle)

        # Navigation Buttons
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
            lambda: self.switch_tab(0, self.btn_dashboard)
        )
        self.btn_placas.clicked.connect(
            lambda: self.switch_tab(1, self.btn_placas)
        )
        self.btn_testes.clicked.connect(
            lambda: self.switch_tab(2, self.btn_testes)
        )
        self.btn_logout.clicked.connect(self.close)

        self.sidebar_layout.addWidget(self.btn_dashboard)
        self.sidebar_layout.addWidget(self.btn_placas)
        self.sidebar_layout.addWidget(self.btn_testes)

        self.sidebar_layout.addStretch()

        # User Info
        user_info = QLabel(
            f"👤 {self.current_user.username}\n"
            f"🛡️ {self.current_user.role}"
        )
        user_info.setStyleSheet(
            "color: #BDC3C7; "
            "padding: 15px; "
            "font-size: 12px;"
        )
        self.sidebar_layout.addWidget(user_info)

        self.sidebar_layout.addWidget(self.btn_logout)

        self.main_layout.addWidget(self.sidebar)

    def setup_content_area(self):
        # Content Area with StackedWidget
        self.content_area = QWidget()
        self.content_area.setStyleSheet(
            "background-color: #F8F9FA;"
        )

        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()

        # Add views
        self.dashboard_view = Dashboard(
            self.session,
            self.current_user,
        )

        self.placas_view = PlacaTab(
            self.session,
            self.dummy_callback,
            current_user=self.current_user,
        )

        self.testes_view = TestExecutor(
            self.session,
            self.current_user,
        )

        # Envia a placa selecionada para a tela de testes
        def import_to_test(board):
            self.testes_view.import_board_for_test(board)
            self.switch_tab(2, self.btn_testes)

        self.placas_view.start_test_callback = import_to_test

        self.stack.addWidget(self.dashboard_view)
        self.stack.addWidget(self.placas_view)
        self.stack.addWidget(self.testes_view)

        self.content_layout.addWidget(self.stack)
        self.main_layout.addWidget(self.content_area)

    def switch_tab(self, index, button):
        # Uncheck all buttons
        for btn in self.buttons:
            btn.setChecked(False)

        # Check clicked button
        button.setChecked(True)

        # Change stack index
        self.stack.setCurrentIndex(index)

        # Refresh dashboard if needed
        if index == 0:
            self.dashboard_view.refresh_stats()

    def dummy_callback(self, board):
        pass
