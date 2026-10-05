from PyQt6.QtCore import Qt, pyqtSignal
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

# -----------------------------------------------------------------------------
# IMPORTANTE
# Esta refatoração altera APENAS a organização visual do dashboard.
# A paleta original do projeto foi mantida:
#   azul-marinho: #0F172A
#   teal principal: #0F766E / #14B8A6 / #2DD4BF
#   fundo: #F4F7F9
#   superfícies: #FFFFFF
# -----------------------------------------------------------------------------


class StatCard(QFrame):
    """Indicador compacto usado no resumo do dashboard."""

    def __init__(self, title, value, accent="#16A085", parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setMinimumHeight(82)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setStyleSheet(
            f"""
            QFrame#statCard {{
                background: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-left: 4px solid {accent};
                border-radius: 9px;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setStyleSheet(
            "color: #6B7280; font-size: 11px; font-weight: 600;"
        )

        self.value_label = QLabel(str(value))
        self.value_label.setStyleSheet(
            "color: #111827; font-size: 23px; font-weight: 700;"
        )

        layout.addWidget(title_label)
        layout.addWidget(self.value_label)


class ActionCard(QFrame):
    """Atalho funcional do fluxo principal do programa."""

    clicked = pyqtSignal(str)

    def __init__(self, action_id, step, title, description, parent=None):
        super().__init__(parent)

        self.action_id = action_id
        self.setObjectName("actionCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(118)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self._apply_style(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(7)

        top = QHBoxLayout()
        top.setSpacing(8)

        step_label = QLabel(step)
        step_label.setFixedSize(30, 24)
        step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        step_label.setStyleSheet(
            """
            QLabel {
                background: #F0FDFA;
                color: #0F766E;
                border: 1px solid #14B8A6;
                border-radius: 6px;
                font-size: 10px;
                font-weight: 700;
            }
            """
        )

        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            """
            color: #111827;
            font-size: 14px;
            font-weight: 700;
            background: transparent;
            """
        )

        top.addWidget(step_label)
        top.addWidget(title_label, 1)

        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setStyleSheet(
            """
            color: #6B7280;
            font-size: 11px;
            background: transparent;
            """
        )

        open_label = QLabel("Ir para aba  →")
        open_label.setStyleSheet(
            """
            color: #0F766E;
            font-size: 11px;
            font-weight: 700;
            background: transparent;
            """
        )

        layout.addLayout(top)
        layout.addWidget(description_label)
        layout.addStretch()
        layout.addWidget(open_label)

    def _apply_style(self, hovered):
        background = "#F0FDFA" if hovered else "#FFFFFF"
        border = "#14B8A6" if hovered else "#E5E7EB"

        self.setStyleSheet(
            f"""
            QFrame#actionCard {{
                background: {background};
                border: 1px solid {border};
                border-radius: 10px;
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
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit(self.action_id)
        super().mouseReleaseEvent(event)


class Dashboard(QWidget):
    """
    Dashboard inicial do TN Eletrosistem.

    O dashboard foi reduzido para mostrar apenas:
      1. identificação e contexto;
      2. indicadores relevantes;
      3. atalhos que realmente executam funções do sistema;
      4. estado do banco e último teste.

    Os atalhos meramente informativos / ainda não implementados foram retirados
    da tela inicial, sem apagar os métodos correspondentes da MainWindow.
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
        self.main_layout.setSpacing(16)

        self._build_header()
        self._build_stats()
        self._build_actions()
        self.main_layout.addStretch(1)
        self._build_footer()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _build_header(self):
        """Cabeçalho mais compacto, mantendo a identidade visual existente."""
        header = QFrame()
        header.setObjectName("header")
        header.setStyleSheet(
            """
            QFrame#header {
                background: #0F172A;
                border-radius: 12px;
            }
            """
        )

        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(3)

        title = QLabel("TN Eletrosistem • TestFlow")
        title.setStyleSheet(
            "color: #FFFFFF; font-size: 19px; font-weight: 700; "
            "background: transparent;"
        )

        subtitle = QLabel(
            "Mapeamento, documentação e testes de placas eletrônicas"
        )
        subtitle.setStyleSheet(
            "color: #CBD5E1; font-size: 11px; background: transparent;"
        )

        welcome = QLabel(f"Operador: {self.current_user.username}")
        welcome.setStyleSheet(
            "color: #94A3B8; font-size: 11px; background: transparent;"
        )

        left.addWidget(title)
        left.addWidget(subtitle)
        left.addWidget(welcome)

        version = QLabel(f"v{APP_VERSION}")
        version.setStyleSheet(
            """
            QLabel {
                background: #134E4A;
                color: #CCFBF1;
                border: 1px solid #2DD4BF;
                border-radius: 8px;
                padding: 4px 8px;
                font-size: 10px;
                font-weight: 700;
            }
            """
        )

        layout.addLayout(left, 1)
        layout.addWidget(version, alignment=Qt.AlignmentFlag.AlignTop)

        self.main_layout.addWidget(header)

    def _build_stats(self):
        """Resumo numérico mantido, porém com cartões mais compactos."""
        section_title = QLabel("Resumo do sistema")
        section_title.setStyleSheet(
            "color: #0F172A; font-size: 15px; font-weight: 700;"
        )
        self.main_layout.addWidget(section_title)

        self.stats_grid = QGridLayout()
        self.stats_grid.setHorizontalSpacing(10)
        self.stats_grid.setVerticalSpacing(10)

        # As mesmas cores de destaque já utilizadas no dashboard original.
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
            self.stats_grid.setColumnStretch(index, 1)

        self.main_layout.addLayout(self.stats_grid)

    def _build_actions(self):
        """
        Mantém apenas atalhos que acionam uma função real do programa.

        Retirados do dashboard:
        - Analisar componentes: atualmente só abre aviso de recurso não pronto;
        - Configurações: atualmente só abre texto informativo;
        - Ajuda / documentação: atualmente só abre texto informativo.

        Os métodos não são apagados da MainWindow, então podem ser recuperados
        futuramente sem perda de código.
        """
        section_header = QHBoxLayout()
        section_header.setSpacing(8)

        title = QLabel("Fluxo principal")
        title.setStyleSheet(
            "color: #0F172A; font-size: 15px; font-weight: 700;"
        )

        hint = QLabel("Os atalhos apenas levam você até a área correta")
        hint.setStyleSheet("color: #94A3B8; font-size: 11px;")

        section_header.addWidget(title)
        section_header.addStretch()
        section_header.addWidget(hint)
        self.main_layout.addLayout(section_header)

        self.actions_grid = QGridLayout()
        self.actions_grid.setHorizontalSpacing(12)
        self.actions_grid.setVerticalSpacing(12)

        # Ordem baseada no fluxo real de uso do sistema.
        card_data = [
            (
                "projects",
                "01",
                "Abrir placa / projeto",
                "Selecione uma placa cadastrada e consulte suas informações.",
            ),
            (
                "import_image",
                "02",
                "Capturar / Importar imagem",
                "Abra a aba de placas para selecionar a placa e gerenciar suas imagens.",
            ),
            (
                "mapping",
                "03",
                "Mapear pontos e conexões",
                "Abra a aba de testes e, após selecionar a placa, acesse o mapeamento.",
            ),
            (
                "pins",
                "04",
                "Pinos e plano de testes",
                "Abra a aba de testes para selecionar a placa e editar o plano de testes.",
            ),
            (
                "report",
                "05",
                "Exportar relatório",
                "Abra a aba de testes para executar ensaios e acessar os relatórios.",
            ),
        ]

        for data in card_data:
            card = ActionCard(*data)
            card.clicked.connect(self.action_requested.emit)
            self.cards.append(card)

        self._reflow_cards()
        self.main_layout.addLayout(self.actions_grid)

    def _build_footer(self):
        """Barra de estado enxuta."""
        self.footer = QFrame()
        self.footer.setObjectName("footer")
        self.footer.setStyleSheet(
            """
            QFrame#footer {
                background: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 9px;
            }
            """
        )

        layout = QHBoxLayout(self.footer)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(12)

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
        """Reorganiza somente os atalhos quando a área útil muda de largura."""
        if not hasattr(self, "actions_grid"):
            return

        width = max(self.width(), 1)

        if width >= 850:
            columns = 3
        elif width >= 620:
            columns = 2
        else:
            columns = 1

        for card in self.cards:
            self.actions_grid.removeWidget(card)

        for index, card in enumerate(self.cards):
            row = index // columns
            col = index % columns
            self.actions_grid.addWidget(card, row, col)

        # Garante distribuição uniforme sem criar espaços estranhos ao redimensionar.
        for column in range(3):
            self.actions_grid.setColumnStretch(
                column,
                1 if column < columns else 0,
            )

    def refresh_stats(self):
        """Atualiza os indicadores e o estado do último teste."""
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
