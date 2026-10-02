from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from db.models import BoardUnit, TestPlan, TestPoint, TestRun


APP_VERSION = "1.0"


class StatCard(QFrame):
    """Card pequeno para indicadores do sistema."""

    def __init__(self, title, value, accent="#16A085", parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setMinimumHeight(92)
        self.setStyleSheet(
            f"""
            QFrame#statCard {{
                background: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-left: 4px solid {accent};
                border-radius: 10px;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(3)

        title_label = QLabel(title)
        title_label.setStyleSheet(
            "color: #6B7280; font-size: 12px; font-weight: 600;"
        )

        self.value_label = QLabel(str(value))
        self.value_label.setStyleSheet(
            "color: #111827; font-size: 25px; font-weight: 700;"
        )

        layout.addWidget(title_label)
        layout.addWidget(self.value_label)


class ActionCard(QFrame):
    """Card clicável usado como acesso rápido."""

    clicked = pyqtSignal(str)

    def __init__(
        self,
        action_id,
        icon,
        title,
        description,
        badge="",
        enabled=True,
        parent=None,
    ):
        super().__init__(parent)

        self.action_id = action_id
        self._enabled = enabled

        self.setObjectName("actionCard")
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if enabled
            else Qt.CursorShape.ArrowCursor
        )
        self.setMinimumSize(220, 155)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self._apply_style(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(7)

        top = QHBoxLayout()

        icon_label = QLabel(icon)
        icon_label.setStyleSheet(
            "font-size: 30px; background: transparent;"
        )

        top.addWidget(icon_label)
        top.addStretch()

        if badge:
            badge_label = QLabel(badge)
            badge_label.setStyleSheet(
                """
                QLabel {
                    background: #FFF7ED;
                    color: #C2410C;
                    border: 1px solid #FED7AA;
                    border-radius: 8px;
                    padding: 3px 7px;
                    font-size: 10px;
                    font-weight: 700;
                }
                """
            )
            top.addWidget(badge_label)

        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            """
            color: #111827;
            font-size: 15px;
            font-weight: 700;
            background: transparent;
            """
        )

        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setStyleSheet(
            """
            color: #6B7280;
            font-size: 11px;
            background: transparent;
            """
        )

        layout.addLayout(top)
        layout.addWidget(title_label)
        layout.addWidget(description_label)
        layout.addStretch()

        access = QLabel("Abrir  →" if enabled else "Indisponível nesta versão")
        access.setStyleSheet(
            """
            color: #0F766E;
            font-size: 11px;
            font-weight: 700;
            background: transparent;
            """
            if enabled
            else """
            color: #9CA3AF;
            font-size: 11px;
            font-weight: 600;
            background: transparent;
            """
        )
        layout.addWidget(access)

    def _apply_style(self, hovered):
        if not self._enabled:
            background = "#F9FAFB"
            border = "#E5E7EB"
        elif hovered:
            background = "#F0FDFA"
            border = "#14B8A6"
        else:
            background = "#FFFFFF"
            border = "#E5E7EB"

        self.setStyleSheet(
            f"""
            QFrame#actionCard {{
                background: {background};
                border: 1px solid {border};
                border-radius: 12px;
            }}
            """
        )

    def enterEvent(self, event):
        self._apply_style(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(False)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if (
            self._enabled
            and event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit(self.action_id)
        super().mouseReleaseEvent(event)


class Dashboard(QWidget):
    """
    Dashboard inicial do TN Eletrosistem.

    Emite action_requested para que a MainWindow execute ações reais
    sem criar dependência circular entre Dashboard e outras telas.
    """

    action_requested = pyqtSignal(str)

    def __init__(self, session, current_user):
        super().__init__()

        self.session = session
        self.current_user = current_user
        self.cards = []

        self.setStyleSheet("background-color: #F4F7F9;")

        self._build_ui()
        self.refresh_stats()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        content = QWidget()
        content.setStyleSheet("background-color: #F4F7F9;")

        self.main_layout = QVBoxLayout(content)
        self.main_layout.setContentsMargins(28, 24, 28, 20)
        self.main_layout.setSpacing(18)

        self._build_header()
        self._build_stats()
        self._build_actions()
        self._build_footer()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _build_header(self):
        header = QFrame()
        header.setObjectName("header")
        header.setStyleSheet(
            """
            QFrame#header {
                background: #0F172A;
                border-radius: 14px;
            }
            """
        )

        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 20, 24, 20)

        left = QVBoxLayout()
        left.setSpacing(4)

        title = QLabel("⚡ TN Eletrosistem • TestFlow")
        title.setFont(QFont("Arial", 21, QFont.Weight.Bold))
        title.setStyleSheet("color: #FFFFFF; background: transparent;")

        subtitle = QLabel(
            "Mapeamento, documentação e testes de placas eletrônicas"
        )
        subtitle.setStyleSheet(
            "color: #CBD5E1; font-size: 12px; background: transparent;"
        )

        left.addWidget(title)
        left.addWidget(subtitle)

        version = QLabel(f"v{APP_VERSION}")
        version.setStyleSheet(
            """
            QLabel {
                background: #134E4A;
                color: #CCFBF1;
                border: 1px solid #2DD4BF;
                border-radius: 9px;
                padding: 5px 9px;
                font-size: 11px;
                font-weight: 700;
            }
            """
        )

        layout.addLayout(left)
        layout.addStretch()
        layout.addWidget(version, alignment=Qt.AlignmentFlag.AlignTop)

        self.main_layout.addWidget(header)

        welcome = QLabel(
            f"Olá, {self.current_user.username}. "
            "Escolha uma função para começar."
        )
        welcome.setStyleSheet(
            "color: #475569; font-size: 13px; font-weight: 600;"
        )
        self.main_layout.addWidget(welcome)

    def _build_stats(self):
        self.stats_grid = QGridLayout()
        self.stats_grid.setHorizontalSpacing(12)
        self.stats_grid.setVerticalSpacing(12)

        self.stat_boards = StatCard("Placas cadastradas", "0", "#0EA5E9")
        self.stat_points = StatCard("Pontos mapeados", "0", "#14B8A6")
        self.stat_plans = StatCard("Planos de teste", "0", "#8B5CF6")
        self.stat_runs = StatCard("Testes realizados", "0", "#22C55E")

        stats = [
            self.stat_boards,
            self.stat_points,
            self.stat_plans,
            self.stat_runs,
        ]

        for index, card in enumerate(stats):
            self.stats_grid.addWidget(card, 0, index)

        self.main_layout.addLayout(self.stats_grid)

    def _build_actions(self):
        section_header = QHBoxLayout()

        title = QLabel("Acesso rápido")
        title.setStyleSheet(
            "color: #0F172A; font-size: 17px; font-weight: 700;"
        )

        hint = QLabel("Clique em um card para abrir a função")
        hint.setStyleSheet("color: #94A3B8; font-size: 11px;")

        section_header.addWidget(title)
        section_header.addStretch()
        section_header.addWidget(hint)

        self.main_layout.addLayout(section_header)

        self.actions_grid = QGridLayout()
        self.actions_grid.setSpacing(14)

        card_data = [
            (
                "import_image",
                "📷",
                "Capturar / Importar imagem",
                "Adicione uma imagem da PCB a uma placa cadastrada.",
                "",
                True,
            ),
            (
                "components",
                "🔍",
                "Analisar componentes",
                "Acesso ao cadastro e análise visual de componentes.",
                "EM EVOLUÇÃO",
                True,
            ),
            (
                "mapping",
                "🗺️",
                "Mapear pontos e conexões",
                "Abra a placa e marque pontos de teste diretamente na imagem.",
                "",
                True,
            ),
            (
                "pins",
                "🧩",
                "Pinos e plano de testes",
                "Organize pontos físicos e crie etapas de medição da placa.",
                "",
                True,
            ),
            (
                "report",
                "💾",
                "Salvar / Exportar relatório",
                "Gere o PDF do último ensaio executado no sistema.",
                "",
                True,
            ),
            (
                "projects",
                "📂",
                "Abrir placa / projeto",
                "Consulte placas cadastradas, imagens e histórico de testes.",
                "",
                True,
            ),
            (
                "settings",
                "⚙️",
                "Configurações",
                "Veja as configurações disponíveis nesta versão do sistema.",
                "BÁSICO",
                True,
            ),
            (
                "help",
                "❓",
                "Ajuda / Documentação",
                "Veja um guia rápido do fluxo de trabalho do programa.",
                "",
                True,
            ),
        ]

        for data in card_data:
            card = ActionCard(*data)
            card.clicked.connect(self.action_requested.emit)
            self.cards.append(card)

        self._reflow_cards()
        self.main_layout.addLayout(self.actions_grid)

    def _build_footer(self):
        self.footer = QFrame()
        self.footer.setObjectName("footer")
        self.footer.setStyleSheet(
            """
            QFrame#footer {
                background: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 10px;
            }
            """
        )

        layout = QHBoxLayout(self.footer)
        layout.setContentsMargins(15, 10, 15, 10)

        self.status_label = QLabel("● Banco de dados conectado")
        self.status_label.setStyleSheet(
            "color: #15803D; font-size: 11px; font-weight: 700;"
        )

        self.last_run_label = QLabel("Último teste: nenhum")
        self.last_run_label.setStyleSheet(
            "color: #64748B; font-size: 11px;"
        )

        layout.addWidget(self.status_label)
        layout.addStretch()
        layout.addWidget(self.last_run_label)

        self.main_layout.addWidget(self.footer)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_cards()

    def _reflow_cards(self):
        width = max(self.width(), 1)

        if width >= 1250:
            columns = 4
        elif width >= 900:
            columns = 3
        elif width >= 620:
            columns = 2
        else:
            columns = 1

        while self.actions_grid.count():
            item = self.actions_grid.takeAt(0)
            if item.widget():
                item.widget().setParent(self)

        for index, card in enumerate(self.cards):
            row = index // columns
            col = index % columns
            self.actions_grid.addWidget(card, row, col)

        for column in range(columns):
            self.actions_grid.setColumnStretch(column, 1)

    def refresh_stats(self):
        """Atualiza indicadores e o rodapé com dados do banco."""

        boards_count = self.session.query(BoardUnit).count()
        points_count = self.session.query(TestPoint).count()
        plans_count = self.session.query(TestPlan).count()
        runs_count = self.session.query(TestRun).count()

        self.stat_boards.value_label.setText(str(boards_count))
        self.stat_points.value_label.setText(str(points_count))
        self.stat_plans.value_label.setText(str(plans_count))
        self.stat_runs.value_label.setText(str(runs_count))

        latest_run = (
            self.session.query(TestRun)
            .order_by(TestRun.start_time.desc())
            .first()
        )

        if latest_run is None:
            self.last_run_label.setText("Último teste: nenhum")
            return

        date_text = (
            latest_run.start_time.strftime("%d/%m/%Y %H:%M")
            if latest_run.start_time
            else "-"
        )

        board_name = (
            latest_run.board.name
            if latest_run.board is not None
            else "placa não identificada"
        )

        self.last_run_label.setText(
            f"Último teste: {board_name} • {date_text} • {latest_run.status}"
        )
