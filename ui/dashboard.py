from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from db.models import BoardUnit, TestPlan, TestRun, TestPoint, User

class StatCard(QFrame):
    def __init__(self, title, value, color="#3498DB"):
        super().__init__()
        self.setStyleSheet(f"""
            QFrame {{
                background-color: white;
                border-radius: 8px;
                border-left: 5px solid {color};
            }}
        """)
        layout = QVBoxLayout()
        
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #7F8C8D; font-size: 14px; font-weight: bold;")
        
        value_label = QLabel(str(value))
        value_label.setStyleSheet(f"color: #2C3E50; font-size: 28px; font-weight: bold;")
        
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addStretch()
        self.setLayout(layout)

class Dashboard(QWidget):
    def __init__(self, session, current_user):
        super().__init__()
        self.session = session
        self.current_user = current_user
        self.setup_ui()
        self.refresh_stats()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)

        # Title
        title = QLabel("Dashboard")
        title.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        title.setStyleSheet("color: #2C3E50;")
        self.main_layout.addWidget(title)
        
        welcome = QLabel(f"Bem-vindo, {self.current_user.username}. Aqui está o resumo do sistema.")
        welcome.setStyleSheet("color: #7F8C8D; font-size: 14px;")
        self.main_layout.addWidget(welcome)

        # Stats Grid
        self.stats_layout = QGridLayout()
        self.stats_layout.setSpacing(15)
        self.main_layout.addLayout(self.stats_layout)
        
        self.main_layout.addStretch()

    def refresh_stats(self):
        # Clear existing
        for i in reversed(range(self.stats_layout.count())): 
            self.stats_layout.itemAt(i).widget().setParent(None)

        # Fetch stats
        boards_count = self.session.query(BoardUnit).count()
        plans_count = self.session.query(TestPlan).count()
        runs_count = self.session.query(TestRun).count()
        users_count = self.session.query(User).count()
        
        failed_runs = self.session.query(TestRun).filter_by(status="failed").count()

        # Add cards
        self.stats_layout.addWidget(StatCard("Total de Placas", boards_count, "#3498DB"), 0, 0)
        self.stats_layout.addWidget(StatCard("Planos de Teste", plans_count, "#9B59B6"), 0, 1)
        self.stats_layout.addWidget(StatCard("Execuções Realizadas", runs_count, "#2ECC71"), 1, 0)
        self.stats_layout.addWidget(StatCard("Falhas de Teste", failed_runs, "#E74C3C"), 1, 1)
        
        if self.current_user.role == "admin":
            self.stats_layout.addWidget(StatCard("Usuários Ativos", users_count, "#F1C40F"), 2, 0, 1, 2)
