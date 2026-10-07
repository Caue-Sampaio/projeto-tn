# main.py
import sys
import os
from tempfile import NamedTemporaryFile
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QTextEdit, QMessageBox, QTabWidget, QInputDialog, QFileDialog, QDialog,
    QProgressBar, QHBoxLayout
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPalette, QColor
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from db.models import Base, User, BoardModel, BoardUnit, TestPoint, BoardImage, TestPlan
from engine.runner import run_test
from engine.pdf_report import export_test_report, export_report_auto
from ui.image_marker import ImageMarker
from ui.plan_editor import PlanEditor
from ui.plan_manager import PlanManager
from ui.placa_tab import PlacaTab
from ui.login import LoginDialog
from db.config import DATABASE_URL
from utils.backup_manager import BackupManager
from engine.logger import setup_logging
import logging


def _prepare_gui_process():
    """Evita janela de console visível em execução normal da interface no Windows.

    O aplicativo é gráfico. Quando iniciado por associação com ``python.exe``,
    o Windows pode criar uma janela de console atrás do PyQt. Durante repaints
    mais pesados essa janela pode aparecer por alguns milissegundos.

    Se o console pertence somente a este processo, ele é ocultado. Consoles
    compartilhados (por exemplo, CMD/PowerShell usado para depuração) são
    preservados. Defina TECHNORD_KEEP_CONSOLE=1 para nunca ocultar o console.
    """
    if os.name != "nt" or os.environ.get("TECHNORD_KEEP_CONSOLE") == "1":
        return

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return

        # Não esconda o terminal do desenvolvedor quando o Python foi iniciado
        # dentro de um CMD/PowerShell já existente.
        process_ids = (ctypes.c_ulong * 16)()
        attached = kernel32.GetConsoleProcessList(process_ids, len(process_ids))
        if attached <= 1:
            user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        # A interface nunca deve deixar de iniciar por causa dessa proteção.
        pass


_prepare_gui_process()

# Configura logging
setup_logging()
logger = logging.getLogger(__name__)

# Simuladores de instrumentos
class FakeDMM:
    def measure_voltage(self, range_v=None):
        return 3.29
    def measure_current(self, range_a=None):
        return 0.012

class FakeScope:
    def measure_frequency(self):
        return 1000.0      
    def get_waveform_summary(self):
        return "Senoidal"


class TestApp(QWidget):
    def __init__(self, user, session):
        super().__init__()
        self.user = user
        self.session = session
        self.setWindowTitle(f"Teste de Placas Eletrônicas - Usuário: {self.user.username}")

        # Define tamanho inicial e centraliza
        self.resize(1000, 700)
        self.center_window()

        # Garante que o banco está inicializado
        self.setup_database()

        # Instrumentos disponíveis
        self.instruments = {"DMM": FakeDMM(), "OSC": FakeScope()}

        # Sistema de backup
        self.backup_manager = BackupManager()
        self.backup_manager.create_backup()

        # Variáveis de estado
        self.selected_board = None
        self.selected_plan = None
        self.last_run = None

        # Abas principais
        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_test_tab(), "🧪 Testes")
        self.tabs.addTab(
            PlacaTab(self.session, self.import_board_for_test, current_user=self.user),
            "🔌 Placas"
        )

        layout = QVBoxLayout()
        layout.addWidget(self.build_status_bar())
        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def center_window(self):
        """Centraliza a janela na tela"""
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        window_geometry = self.frameGeometry()
        center_point = screen_geometry.center()
        window_geometry.moveCenter(center_point)
        self.move(window_geometry.topLeft())

    def build_status_bar(self):
        """Constrói a barra de status"""
        status_widget = QWidget()
        layout = QHBoxLayout()
        
        self.status_label = QLabel(f"Usuário: {self.user.username} | Role: {self.user.role}")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        self.board_status = QLabel("Placa: Nenhuma")
        layout.addWidget(self.board_status)
        
        self.plan_status = QLabel("Plano: Nenhum")
        layout.addWidget(self.plan_status)
        
        status_widget.setLayout(layout)
        status_widget.setStyleSheet("background-color: #f0f0f0; padding: 5px; border-bottom: 1px solid #ccc;")
        return status_widget

    def setup_database(self):
        """Inicializa o banco com dados de exemplo se estiver vazio"""
        if not self.session.query(User).first():
            logger.info("Inicializando banco de dados com dados de exemplo...")
            user = User(username="tech", role="operator", password_hash="123")
            model = BoardModel(name="Placa X", version="1.0")
            board = BoardUnit(
                name="Placa de Demonstração",
                model="X",
                version="1.0",
                serial_number="SN001",
                board_model=model,
                operator=user
            )
            tp = TestPoint(board=board, refdes="TP1", x=100, y=100)
            self.session.add_all([user, model, board, tp])
            self.session.commit()
            logger.info("Dados de exemplo criados com sucesso")

    def build_test_tab(self):
        widget = QWidget()
        layout = QVBoxLayout()

        # Área de informações
        info_layout = QHBoxLayout()
        info_layout.addWidget(QLabel("Placa selecionada:"))
        self.board_info_label = QLabel("Nenhuma")
        info_layout.addWidget(self.board_info_label)
        info_layout.addStretch()
        info_layout.addWidget(QLabel("Plano selecionado:"))
        self.plan_info_label = QLabel("Nenhum")
        info_layout.addWidget(self.plan_info_label)
        layout.addLayout(info_layout)

        # Barra de progresso
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet("background-color: white; color: #1E293B; border: 1.5px solid #CBD5E1; border-radius: 6px; padding: 6px;")

        self.test_button = QPushButton("▶ Executar Teste")
        self.test_button.clicked.connect(self.execute_test)
        self.test_button.setEnabled(False)

        self.image_button = QPushButton("🖼️ Editar Imagem da Placa")
        self.image_button.clicked.connect(self.open_image_marker_edit)

        self.view_button = QPushButton("👁️ Visualizar Imagem da Placa")
        self.view_button.clicked.connect(self.open_image_marker_view)

        self.plan_button = QPushButton("📋 Criar Plano de Teste")
        self.plan_button.clicked.connect(self.open_plan_editor)

        self.manager_button = QPushButton("⚙️ Gerenciar Planos")
        self.manager_button.clicked.connect(self.open_plan_manager)

        self.report_button = QPushButton("📊 Exportar Relatório PDF")
        self.report_button.clicked.connect(self.export_report)

        self.auto_report_button = QPushButton("💾 Salvar Relatório Automaticamente")
        self.auto_report_button.clicked.connect(self.export_report_auto)

        btn_style = """
            QPushButton {
                background-color: #0284C7;
                color: white;
                border: 1px solid #0369A1;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #0369A1; }
            QPushButton:pressed { background-color: #075985; }
            QPushButton:disabled { background-color: #CBD5E1; color: #64748B; border: 1px solid #94A3B8; }
        """
        for b in [self.test_button, self.image_button, self.view_button, self.plan_button, self.manager_button, self.report_button, self.auto_report_button]:
            b.setStyleSheet(btn_style)

        layout.addWidget(QLabel("Resultado do Teste:"))
        layout.addWidget(self.output)
        layout.addWidget(self.test_button)
        layout.addWidget(self.image_button)
        layout.addWidget(self.view_button)
        layout.addWidget(self.plan_button)
        layout.addWidget(self.manager_button)
        layout.addWidget(self.report_button)
        layout.addWidget(self.auto_report_button)

        widget.setLayout(layout)
        return widget

    def import_board_for_test(self, board):
        self.selected_board = board
        self.board_info_label.setText(f"{board.name} ({board.serial_number})")
        self.board_status.setText(f"Placa: {board.name}")
        self.output.append(f"📦 Placa importada: {board.name} ({board.serial_number})")
        self.update_test_button_state()

    def set_selected_plan(self, plan):
        self.selected_plan = plan
        self.plan_info_label.setText(f"{plan.name} v{plan.version}")
        self.plan_status.setText(f"Plano: {plan.name}")
        self.output.append(f"📌 Plano selecionado: {plan.name} v{plan.version}")
        self.update_test_button_state()

    def update_test_button_state(self):
        """Ativa/desativa botão de teste baseado no estado"""
        has_board = self.selected_board is not None
        has_plan = self.selected_plan is not None
        self.test_button.setEnabled(has_board and has_plan)

    def execute_test(self):
        if not self.selected_plan or not self.selected_board:
            QMessageBox.warning(self, "Erro", "Selecione plano e placa antes de executar.")
            return

        # Prepara interface para teste
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.test_button.setEnabled(False)
        self.output.clear()

        # Executa teste em background
        QTimer.singleShot(100, self._run_test_background)

    def _run_test_background(self):
        """Executa o teste em background"""
        try:
            run, measurements = run_test(
                self.session,
                self.selected_plan,
                self.selected_board,
                self.user,
                self.instruments,
                self.highlight_test_point,
                self.update_progress
            )

            self.last_run = run
            self.display_test_results(run, measurements)
            
        except Exception as e:
            logger.error(f"Erro durante execução do teste: {e}")
            QMessageBox.critical(self, "Erro", f"Falha na execução do teste: {str(e)}")
        finally:
            self.progress_bar.setVisible(False)
            self.test_button.setEnabled(True)

    def update_progress(self, current, total, description):
        """Atualiza barra de progresso"""
        progress = int((current / total) * 100)
        self.progress_bar.setValue(progress)
        QApplication.processEvents()  # Atualiza UI

    def display_test_results(self, run, measurements):
        """Exibe resultados do teste"""
        self.output.append(f"✅ Teste finalizado: {run.status.upper()}")
        
        for m in measurements:
            step = m.step
            desired = step.desired_value if step.desired_value else "-"
            tol = step.tolerance if step.tolerance else "-"
            result_icon = "✅" if m.passed else "❌"
            
            self.output.append(
                f"{result_icon} {step.description} ({step.unit}) - "
                f"Desejado: {desired} ± {tol} | "
                f"Medido: {m.value} → {m.passed}"
            )

    def open_image_marker_edit(self):
        if not self.selected_board:
            QMessageBox.warning(self, "Erro", "Importe uma placa antes de editar a imagem.")
            return
        if not self.selected_board.images:
            QMessageBox.warning(self, "Erro", "Nenhuma imagem cadastrada para esta placa.")
            return

        paths = [img.path for img in self.selected_board.images]
        choice, ok = QInputDialog.getItem(self, "Selecionar Imagem", "Escolha a imagem da placa:", paths, 0, False)
        if ok and choice:
            self.marker = ImageMarker(self.session, self.selected_board, mode="edit", instruments=self.instruments)
            self.marker.load_image(choice)
            self.marker.show()

    def open_image_marker_view(self):
        if not self.selected_board:
            QMessageBox.warning(self, "Erro", "Importe uma placa antes de visualizar a imagem.")
            return
        if not self.selected_board.images:
            QMessageBox.warning(self, "Erro", "Nenhuma imagem cadastrada para esta placa.")
            return

        paths = [img.path for img in self.selected_board.images]
        choice, ok = QInputDialog.getItem(self, "Selecionar Imagem", "Escolha a imagem da placa:", paths, 0, False)
        if ok and choice:
            self.viewer = ImageMarker(self.session, self.selected_board, mode="view", instruments=self.instruments)
            self.viewer.load_image(choice)
            self.viewer.show()

    def open_plan_editor(self):
        if not self.selected_board:
            QMessageBox.warning(self, "Erro", "Importe uma placa antes de criar um plano de teste.")
            return
        self.editor = PlanEditor(self.session, self.selected_board)
        self.editor.show()

    def open_plan_manager(self):
        if not self.selected_board:
            QMessageBox.warning(self, "Erro", "Importe uma placa antes de gerenciar planos.")
            return
        self.manager = PlanManager(self.session, self.set_selected_plan, self.selected_board)
        self.manager.show()

    def is_image_loaded(self):
        """Verifica se uma imagem está carregada no marker"""
        return (hasattr(self, "marker") and 
                hasattr(self.marker, "image_path") and 
                self.marker.image_path and 
                os.path.exists(self.marker.image_path))

    def export_report(self):
        if not hasattr(self, "last_run"):
            QMessageBox.warning(self, "Erro", "Execute um teste antes de exportar o relatório.")
            return
        if not hasattr(self, "marker") or not self.marker.image_path:
            QMessageBox.warning(self, "Erro", "Selecione uma imagem da placa antes de gerar o relatório.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Salvar Relatório", "", "PDF (*.pdf)")
        if path:
            export_test_report(self.last_run, self.marker.image_path, path)
            QMessageBox.information(self, "Sucesso", f"Relatório salvo em:\n{path}")

    def export_report_auto(self):
        if not hasattr(self, "last_run"):
            QMessageBox.warning(self, "Erro", "Execute um teste antes de salvar automaticamente.")
            return
        if not hasattr(self, "marker") or not self.marker.image_path:
            QMessageBox.warning(self, "Erro", "Selecione uma imagem da placa antes de gerar o relatório.")
            return

        path = export_report_auto(self.last_run, self.marker.image_path)
        QMessageBox.information(self, "Relatório Salvo", f"Relatório salvo automaticamente em:\n{path}")

    def highlight_test_point(self, step):
        if hasattr(self, "marker") and step.test_point:
            self.marker.image_label.set_points([{
                "x": step.test_point.x,
                "y": step.test_point.y,
                "ref": step.test_point.refdes,
                "id": step.test_point.id
            }])
            self.marker.image_label.update()


def _install_excepthook():
    """Evita que um erro dentro de um botão/clique feche o programa inteiro.

    No PyQt6, uma exceção não tratada num slot derruba a aplicação. Aqui o erro
    é gravado em logs/crash.log e mostrado numa janela, e o programa continua.
    """
    import traceback
    from datetime import datetime

    def handler(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            os.makedirs("logs", exist_ok=True)
            with open(os.path.join("logs", "crash.log"), "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.now():%Y-%m-%d %H:%M:%S}\n{text}")
        except Exception:
            pass
        print(text, file=sys.stderr)
        try:
            box = QMessageBox()
            box.setIcon(QMessageBox.Icon.Critical)
            box.setWindowTitle("Erro inesperado")
            box.setText("Ocorreu um erro, mas o programa continua aberto.\n"
                        "Os detalhes foram salvos em logs/crash.log.")
            box.setDetailedText(text)
            box.exec()
        except Exception:
            pass

    sys.excepthook = handler


if __name__ == "__main__":
    app = QApplication(sys.argv)
    _install_excepthook()
    
    # Aplica estilo global
    app.setStyle("Fusion")

    # Define paleta limpa e com alto contraste (evita texto branco em áreas claras no Windows)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#1E293B"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#F1F5F9"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1E293B"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#1E293B"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#0284C7"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#EF4444"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#0284C7"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#0284C7"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)

    # Stylesheet global para garantir que todos os botões e campos em áreas claras tenham alta visibilidade
    app.setStyleSheet("""
        QWidget {
            font-family: "Segoe UI", Arial, sans-serif;
            color: #1E293B;
        }
        QLineEdit, QTextEdit, QPlainTextEdit {
            color: #1E293B;
            background-color: #FFFFFF;
            border: 1.5px solid #CBD5E1;
            border-radius: 6px;
            padding: 6px 10px;
            selection-background-color: #0284C7;
            selection-color: #FFFFFF;
        }
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
            border-color: #0284C7;
            background-color: #F8FAFC;
            color: #1E293B;
        }
        QLineEdit::placeholder, QTextEdit::placeholder {
            color: #94A3B8;
        }
        QPushButton {
            background-color: #0284C7;
            color: #FFFFFF;
            border: 1px solid #0369A1;
            border-radius: 6px;
            padding: 7px 16px;
            font-weight: 600;
            font-size: 13px;
        }
        QPushButton:hover {
            background-color: #0369A1;
        }
        QPushButton:pressed {
            background-color: #075985;
        }
        QPushButton:disabled {
            background-color: #CBD5E1;
            color: #64748B;
            border: 1px solid #94A3B8;
        }
        QComboBox {
            color: #1E293B;
            background-color: #FFFFFF;
            border: 1.5px solid #CBD5E1;
            border-radius: 6px;
            padding: 6px 10px;
        }
        QComboBox QAbstractItemView {
            color: #1E293B;
            background-color: #FFFFFF;
            selection-background-color: #0284C7;
            selection-color: #FFFFFF;
        }
        QCheckBox {
            color: #1E293B;
        }
        QTableWidget, QListWidget {
            color: #1E293B;
            background-color: #FFFFFF;
        }
    """)

    # Inicializa banco e sessão para login
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    from db.auto_migrate import ensure_schema
    ensure_schema(engine)  # adiciona a coluna machine_id em bancos antigos
    session = Session(engine)

    # Tela de login
    login = LoginDialog(session)
    if login.exec() == QDialog.DialogCode.Accepted:
        from ui.main_window import MainWindow
        from utils.backup_manager import BackupManager
        
        backup_manager = BackupManager()
        backup_manager.create_backup("auto")
        
        window = MainWindow(session=session, current_user=login.user, backup_manager=backup_manager)
        window.show()
        sys.exit(app.exec())
    else:
        print("Login cancelado.")
        sys.exit(0)