from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from db.models import BoardUnit, Machine, MachineDocument, BoardDocument


class MetricCard(QFrame):
    def __init__(self, title, value="0", helper="", parent=None):
        super().__init__(parent)
        self.setObjectName("metricCard")
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 15, 18, 14)
        lay.setSpacing(4)
        title_lbl = QLabel(title.upper()); title_lbl.setObjectName("metricTitle")
        self.value_lbl = QLabel(str(value)); self.value_lbl.setObjectName("metricValue")
        helper_lbl = QLabel(helper); helper_lbl.setObjectName("metricHelper")
        lay.addWidget(title_lbl); lay.addWidget(self.value_lbl); lay.addWidget(helper_lbl)

    def set_value(self, value):
        self.value_lbl.setText(str(value))


class MainActionCard(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, action_id, icon, title, description, button_text, parent=None):
        super().__init__(parent)
        self.action_id = action_id
        self.setObjectName("mainActionCard")
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(9)
        top = QHBoxLayout()
        ico = QLabel(icon); ico.setObjectName("actionIcon"); ico.setAlignment(Qt.AlignmentFlag.AlignCenter); ico.setFixedSize(42, 42)
        title_lbl = QLabel(title); title_lbl.setObjectName("actionTitle")
        top.addWidget(ico); top.addWidget(title_lbl, 1); root.addLayout(top)
        desc = QLabel(description); desc.setObjectName("actionDesc"); desc.setWordWrap(True)
        root.addWidget(desc); root.addStretch()
        btn = QPushButton(button_text); btn.setObjectName("actionButton"); btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self.clicked.emit(self.action_id))
        root.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft)


class Dashboard(QWidget):
    """Dashboard deliberadamente simples: inventário e documentação técnica."""

    action_requested = pyqtSignal(str)

    def __init__(self, session, current_user):
        super().__init__()
        self.session = session
        self.current_user = current_user
        self.setObjectName("dashboardRoot")
        self._build_ui()
        self.refresh_stats()

    def _build_ui(self):
        self.setStyleSheet(self._style())
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(); content.setObjectName("dashboardContent")
        root = QVBoxLayout(content); root.setContentsMargins(30, 26, 30, 26); root.setSpacing(18)

        hero = QFrame(); hero.setObjectName("hero")
        hl = QHBoxLayout(hero); hl.setContentsMargins(24, 20, 24, 20)
        left = QVBoxLayout(); left.setSpacing(4)
        kicker = QLabel("TN ELETROSISTEM  /  PAINEL"); kicker.setObjectName("heroKicker")
        title = QLabel("Visão geral"); title.setObjectName("heroTitle")
        sub = QLabel("Acesse o inventário de equipamentos e placas ou gerencie a documentação técnica do sistema.")
        sub.setObjectName("heroSub"); sub.setWordWrap(True)
        left.addWidget(kicker); left.addWidget(title); left.addWidget(sub)
        hl.addLayout(left, 1)
        user = QLabel(f"Usuário: {getattr(self.current_user, 'username', '—')}"); user.setObjectName("userChip")
        hl.addWidget(user, 0, Qt.AlignmentFlag.AlignTop)
        root.addWidget(hero)

        metrics = QGridLayout(); metrics.setHorizontalSpacing(12); metrics.setVerticalSpacing(12)
        self.machine_metric = MetricCard("Equipamentos", helper="cadastrados")
        self.board_metric = MetricCard("Placas", helper="cadastradas")
        self.docs_metric = MetricCard("Documentos técnicos", helper="equipamentos + placas")
        metrics.addWidget(self.machine_metric, 0, 0); metrics.addWidget(self.board_metric, 0, 1); metrics.addWidget(self.docs_metric, 0, 2)
        root.addLayout(metrics)

        sec = QVBoxLayout(); sec.setSpacing(3)
        sec_title = QLabel("Acessos principais"); sec_title.setObjectName("sectionTitle")
        sec_sub = QLabel("Somente os caminhos usados no dia a dia."); sec_sub.setObjectName("sectionSub")
        sec.addWidget(sec_title); sec.addWidget(sec_sub); root.addLayout(sec)

        actions = QGridLayout(); actions.setHorizontalSpacing(14); actions.setVerticalSpacing(14)
        inventory = MainActionCard(
            "inventory", "▣", "Equipamentos",
            "Cadastre equipamentos, organize as placas vinculadas e abra os detalhes técnicos de cada placa.",
            "Abrir inventário",
        )
        documents = MainActionCard(
            "documents", "▤", "Documentos Técnicos",
            "Centralize datasheets, manuais, diagramas, procedimentos e outros arquivos de equipamentos e placas.",
            "Abrir documentos",
        )
        inventory.clicked.connect(self.action_requested); documents.clicked.connect(self.action_requested)
        actions.addWidget(inventory, 0, 0); actions.addWidget(documents, 0, 1)
        root.addLayout(actions)
        root.addStretch(1)

        foot = QLabel("O teste, o mapeamento e as referências continuam acessíveis pelo contexto de cada placa.")
        foot.setObjectName("footerNote"); foot.setWordWrap(True); root.addWidget(foot)
        scroll.setWidget(content); outer.addWidget(scroll)

    def refresh_stats(self):
        try:
            machines = self.session.query(Machine).count()
            boards = self.session.query(BoardUnit).count()
            docs = self.session.query(MachineDocument).count() + self.session.query(BoardDocument).count()
            self.machine_metric.set_value(machines)
            self.board_metric.set_value(boards)
            self.docs_metric.set_value(docs)
        except Exception:
            self.machine_metric.set_value("—"); self.board_metric.set_value("—"); self.docs_metric.set_value("—")

    @staticmethod
    def _style():
        return """
        QWidget#dashboardRoot, QWidget#dashboardContent { background:#F4F7F9; color:#0F172A; }
        QScrollArea { border:none; background:#F4F7F9; }
        QFrame#hero { background:#0F172A; border:1px solid #1E293B; border-radius:14px; }
        QLabel#heroKicker { color:#5EEAD4; font:800 9px 'Segoe UI'; letter-spacing:1px; }
        QLabel#heroTitle { color:#FFFFFF; font:800 25px 'Segoe UI'; }
        QLabel#heroSub { color:#CBD5E1; font:11px 'Segoe UI'; }
        QLabel#userChip { color:#D5F5F0; background:#123331; border:1px solid #1E5D57; border-radius:10px; padding:7px 11px; font:700 10px 'Segoe UI'; }
        QFrame#metricCard { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:11px; }
        QLabel#metricTitle { color:#64748B; font:800 9px 'Segoe UI'; letter-spacing:.5px; }
        QLabel#metricValue { color:#0F172A; font:800 27px 'Segoe UI'; }
        QLabel#metricHelper { color:#94A3B8; font:10px 'Segoe UI'; }
        QLabel#sectionTitle { color:#0F172A; font:800 16px 'Segoe UI'; }
        QLabel#sectionSub { color:#64748B; font:10px 'Segoe UI'; }
        QFrame#mainActionCard { background:#FFFFFF; border:1px solid #DCE5EC; border-radius:12px; }
        QFrame#mainActionCard:hover { border:1px solid #5FC8BC; background:#FBFFFE; }
        QLabel#actionIcon { color:#0F766E; background:#ECFDF5; border:1px solid #A7F3D0; border-radius:9px; font:800 18px 'Segoe UI'; }
        QLabel#actionTitle { color:#0F172A; font:800 16px 'Segoe UI'; }
        QLabel#actionDesc { color:#64748B; font:11px 'Segoe UI'; }
        QPushButton#actionButton { background:#0F766E; color:#FFFFFF; border:none; border-radius:8px; min-height:38px; padding:0 16px; font:700 11px 'Segoe UI'; }
        QPushButton#actionButton:hover { background:#115E59; }
        QLabel#footerNote { color:#94A3B8; background:#FFFFFF; border:1px solid #E2E8F0; border-radius:9px; padding:11px 13px; font:10px 'Segoe UI'; }
        """
