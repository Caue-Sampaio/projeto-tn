from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from db.models import BoardUnit, TestPlan, TestPoint, TestRun


APP_VERSION = "1.0"


class StatCard(QFrame):
    """Indicador refinado e compacto do dashboard."""

    def __init__(self, title, value, accent="#14B8A6", helper="cadastrados", parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setMinimumHeight(92)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 13, 16, 12)
        root.setSpacing(5)

        top = QHBoxLayout()
        top.setSpacing(8)

        title_label = QLabel(title.upper())
        title_label.setObjectName("statTitle")
        top.addWidget(title_label)
        top.addStretch()

        dot = QFrame()
        dot.setFixedSize(7, 7)
        dot.setStyleSheet(f"background:{accent}; border-radius:3px;")
        top.addWidget(dot, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.value_label = QLabel(str(value))
        self.value_label.setObjectName("statValue")

        helper_label = QLabel(helper)
        helper_label.setObjectName("statHelper")

        root.addLayout(top)
        root.addWidget(self.value_label)
        root.addWidget(helper_label)

        self.setStyleSheet(
            f"""
            QFrame#statCard {{
                background:#FFFFFF;
                border:1px solid #E2E8F0;
                border-top:3px solid {accent};
                border-radius:11px;
            }}
            QLabel#statTitle {{
                color:#64748B;
                font-size:9px;
                font-weight:800;
                letter-spacing:0.4px;
                background:transparent;
            }}
            QLabel#statValue {{
                color:#0F172A;
                font-size:25px;
                font-weight:800;
                background:transparent;
            }}
            QLabel#statHelper {{
                color:#94A3B8;
                font-size:10px;
                background:transparent;
            }}
            """
        )


class ActionCard(QFrame):
    """Atalho do fluxo principal; navega sem iniciar operações automaticamente."""

    clicked = pyqtSignal(str)

    def __init__(self, action_id, step, title, description, eyebrow, parent=None):
        super().__init__(parent)
        self.action_id = action_id
        self.setObjectName("actionCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(112)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._hovered = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 13)
        root.setSpacing(7)

        top = QHBoxLayout()
        top.setSpacing(10)

        number = QLabel(step)
        number.setObjectName("actionNumber")
        number.setFixedSize(34, 28)
        number.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text_box = QVBoxLayout()
        text_box.setSpacing(1)

        eyebrow_label = QLabel(eyebrow.upper())
        eyebrow_label.setObjectName("actionEyebrow")

        title_label = QLabel(title)
        title_label.setObjectName("actionTitle")
        title_label.setWordWrap(True)

        text_box.addWidget(eyebrow_label)
        text_box.addWidget(title_label)

        top.addWidget(number, alignment=Qt.AlignmentFlag.AlignTop)
        top.addLayout(text_box, 1)

        arrow = QLabel("→")
        arrow.setObjectName("actionArrow")
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(arrow, alignment=Qt.AlignmentFlag.AlignTop)

        description_label = QLabel(description)
        description_label.setObjectName("actionDescription")
        description_label.setWordWrap(True)

        root.addLayout(top)
        root.addWidget(description_label)
        root.addStretch(1)

        self._apply_style(False)

    def _apply_style(self, hovered: bool):
        bg = "#F8FFFD" if hovered else "#FFFFFF"
        border = "#5EEAD4" if hovered else "#E2E8F0"
        self.setStyleSheet(
            f"""
            QFrame#actionCard {{
                background:{bg};
                border:1px solid {border};
                border-radius:11px;
            }}
            QLabel#actionNumber {{
                background:#F0FDFA;
                color:#0F766E;
                border:1px solid #99F6E4;
                border-radius:7px;
                font-size:10px;
                font-weight:800;
            }}
            QLabel#actionEyebrow {{
                color:#0F766E;
                font-size:8px;
                font-weight:800;
                background:transparent;
            }}
            QLabel#actionTitle {{
                color:#0F172A;
                font-size:13px;
                font-weight:750;
                background:transparent;
            }}
            QLabel#actionDescription {{
                color:#64748B;
                font-size:10px;
                background:transparent;
            }}
            QLabel#actionArrow {{
                color:{'#0F766E' if hovered else '#94A3B8'};
                font-size:17px;
                font-weight:700;
                background:transparent;
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
    """Dashboard inicial refinado, sem alterar a lógica de navegação."""

    action_requested = pyqtSignal(str)

    def __init__(self, session, current_user):
        super().__init__()
        self.session = session
        self.current_user = current_user
        self.cards = []
        self.setObjectName("dashboardRoot")
        self._build_ui()
        self.refresh_stats()

    def _build_ui(self):
        self.setStyleSheet(
            """
            QWidget#dashboardRoot { background:#F4F7F9; }
            QScrollArea { border:none; background:#F4F7F9; }
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content.setStyleSheet("background:#F4F7F9;")

        self.main_layout = QVBoxLayout(content)
        self.main_layout.setContentsMargins(28, 24, 28, 22)
        self.main_layout.setSpacing(17)

        self._build_header()
        self._build_stats()
        self._build_actions()
        self.main_layout.addStretch(1)
        self._build_footer()

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _build_header(self):
        hero = QFrame()
        hero.setObjectName("hero")
        hero.setMinimumHeight(126)
        hero.setStyleSheet(
            """
            QFrame#hero {
                background:#0F172A;
                border:1px solid #172554;
                border-radius:14px;
            }
            """
        )

        layout = QHBoxLayout(hero)
        layout.setContentsMargins(24, 20, 22, 20)
        layout.setSpacing(24)

        left = QVBoxLayout()
        left.setSpacing(4)

        kicker = QLabel("TN ELETROSISTEM  /  PAINEL OPERACIONAL")
        kicker.setStyleSheet(
            "color:#5EEAD4; font-size:9px; font-weight:800; letter-spacing:0.7px; background:transparent;"
        )

        title = QLabel("TestFlow")
        title.setStyleSheet(
            "color:#FFFFFF; font-size:25px; font-weight:800; background:transparent;"
        )

        subtitle = QLabel("Mapeamento, referências e testes de placas eletrônicas em um único fluxo.")
        subtitle.setStyleSheet(
            "color:#CBD5E1; font-size:11px; background:transparent;"
        )
        subtitle.setWordWrap(True)

        left.addWidget(kicker)
        left.addWidget(title)
        left.addWidget(subtitle)
        left.addStretch()

        right_card = QFrame()
        right_card.setObjectName("operatorCard")
        right_card.setFixedWidth(220)
        right_card.setStyleSheet(
            """
            QFrame#operatorCard {
                background:#111C31;
                border:1px solid #24324A;
                border-radius:10px;
            }
            """
        )
        rv = QVBoxLayout(right_card)
        rv.setContentsMargins(14, 11, 14, 11)
        rv.setSpacing(4)

        op_caption = QLabel("SESSÃO ATUAL")
        op_caption.setStyleSheet(
            "color:#64748B; font-size:8px; font-weight:800; background:transparent;"
        )
        username = QLabel(self.current_user.username)
        username.setStyleSheet(
            "color:#F8FAFC; font-size:13px; font-weight:700; background:transparent;"
        )
        version = QLabel(f"Versão {APP_VERSION}  •  Sistema pronto")
        version.setStyleSheet(
            "color:#94A3B8; font-size:9px; background:transparent;"
        )
        status = QLabel("● ONLINE")
        status.setStyleSheet(
            "color:#5EEAD4; font-size:9px; font-weight:800; background:transparent;"
        )

        rv.addWidget(op_caption)
        rv.addWidget(username)
        rv.addWidget(version)
        rv.addStretch()
        rv.addWidget(status)

        layout.addLayout(left, 1)
        layout.addWidget(right_card)
        self.main_layout.addWidget(hero)

    def _section_header(self, title_text: str, subtitle_text: str):
        row = QHBoxLayout()
        row.setSpacing(10)

        title = QLabel(title_text)
        title.setStyleSheet(
            "color:#0F172A; font-size:14px; font-weight:800; background:transparent;"
        )
        subtitle = QLabel(subtitle_text)
        subtitle.setStyleSheet(
            "color:#94A3B8; font-size:10px; background:transparent;"
        )

        row.addWidget(title)
        row.addWidget(subtitle)
        row.addStretch()
        self.main_layout.addLayout(row)

    def _build_stats(self):
        self._section_header("Visão geral", "Indicadores atuais do sistema")

        self.stats_grid = QGridLayout()
        self.stats_grid.setHorizontalSpacing(11)
        self.stats_grid.setVerticalSpacing(11)

        self.stat_boards = StatCard("Placas", "0", "#0EA5E9", "placas cadastradas")
        self.stat_points = StatCard("Pontos", "0", "#14B8A6", "pontos mapeados")
        self.stat_plans = StatCard("Planos", "0", "#8B5CF6", "planos de teste")
        self.stat_runs = StatCard("Testes", "0", "#22C55E", "execuções registradas")

        for index, card in enumerate([
            self.stat_boards,
            self.stat_points,
            self.stat_plans,
            self.stat_runs,
        ]):
            self.stats_grid.addWidget(card, 0, index)
            self.stats_grid.setColumnStretch(index, 1)

        self.main_layout.addLayout(self.stats_grid)

    def _build_actions(self):
        self._section_header("Fluxo principal", "Atalhos de navegação — nenhuma ação é iniciada automaticamente")

        self.actions_grid = QGridLayout()
        self.actions_grid.setHorizontalSpacing(12)
        self.actions_grid.setVerticalSpacing(12)

        card_data = [
            (
                "projects", "01", "Abrir placa / projeto",
                "Acesse as placas cadastradas, máquinas e informações do equipamento.",
                "Placas",
            ),
            (
                "import_image", "02", "Capturar / Importar imagem",
                "Vá até a placa e gerencie as imagens usadas no mapeamento.",
                "Imagem",
            ),
            (
                "mapping", "03", "Mapear pontos e conexões",
                "Abra Testes e entre no mapeamento para posicionar e editar pontos.",
                "Mapeamento",
            ),
            (
                "pins", "04", "Pinos e plano de testes",
                "Acesse a área de Testes para criar ou editar o plano da placa.",
                "Plano",
            ),
            (
                "report", "05", "Exportar relatório",
                "Vá até Testes para consultar execuções e gerar o relatório final.",
                "Relatório",
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
                background:#FFFFFF;
                border:1px solid #E2E8F0;
                border-radius:10px;
            }
            """
        )

        layout = QHBoxLayout(self.footer)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        self.status_label = QLabel("● Banco de dados conectado")
        self.status_label.setStyleSheet(
            "color:#15803D; font-size:10px; font-weight:800; background:transparent;"
        )

        divider = QLabel("|")
        divider.setStyleSheet("color:#CBD5E1; background:transparent;")

        hint = QLabel("Dados atualizados ao abrir o dashboard")
        hint.setStyleSheet("color:#94A3B8; font-size:9px; background:transparent;")

        self.last_run_label = QLabel("Último teste: nenhum")
        self.last_run_label.setStyleSheet(
            "color:#64748B; font-size:10px; background:transparent;"
        )

        layout.addWidget(self.status_label)
        layout.addWidget(divider)
        layout.addWidget(hint)
        layout.addStretch()
        layout.addWidget(self.last_run_label)

        self.main_layout.addWidget(self.footer)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_cards()

    def _reflow_cards(self):
        if not hasattr(self, "actions_grid"):
            return

        width = max(self.width(), 1)
        if width >= 1080:
            columns = 3
        elif width >= 700:
            columns = 2
        else:
            columns = 1

        for card in self.cards:
            self.actions_grid.removeWidget(card)

        for index, card in enumerate(self.cards):
            row = index // columns
            col = index % columns
            self.actions_grid.addWidget(card, row, col)

        for column in range(3):
            self.actions_grid.setColumnStretch(column, 1 if column < columns else 0)

    def refresh_stats(self):
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
        board_name = latest_run.board.name if latest_run.board is not None else "placa não identificada"
        self.last_run_label.setText(
            f"Último teste: {board_name}  •  {date_text}  •  {latest_run.status}"
        )
