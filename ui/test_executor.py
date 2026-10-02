from pathlib import Path
import logging

from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QInputDialog,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from db.models import BoardUnit
from engine.pdf_report import export_test_report
from engine.runner import run_test
from ui.plan_manager import PlanManager


logger = logging.getLogger(__name__)


class FakeDMM:
    """Simulador temporário de multímetro usado enquanto não há instrumento real."""

    def measure_voltage(self, range_v=None):
        return 3.29

    def measure_current(self, range_a=None):
        return 0.012


class FakeScope:
    """Simulador temporário de osciloscópio."""

    def measure_frequency(self):
        return 1000.0

    def get_waveform_summary(self):
        return "Senoidal"


class TestExecutor(QWidget):
    """Tela responsável por selecionar placa/plano e executar o roteiro de testes."""

    def __init__(self, session, current_user):
        super().__init__()
        self.session = session
        self.user = current_user

        self.selected_board = None
        self.selected_plan = None
        self.last_run = None

        # Mantém referências de janelas auxiliares para evitar coleta de lixo do Qt.
        self.plan_manager_window = None
        self.editor = None
        self.marker = None
        self.viewer = None

        self.instruments = {
            "DMM": FakeDMM(),
            "OSC": FakeScope(),
        }

        self.setup_ui()
        self.update_button_state()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Execução de Testes")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #2C3E50;")
        layout.addWidget(title)

        # Seleção da placa e do plano
        selection_layout = QHBoxLayout()

        self.btn_select_board = QPushButton("🔌 Selecionar Placa")
        self.btn_select_board.clicked.connect(self.select_board)

        self.btn_select_plan = QPushButton("📋 Selecionar Plano")
        self.btn_select_plan.clicked.connect(self.select_plan)

        self.btn_start_test = QPushButton("▶️ INICIAR TESTE")
        self.btn_start_test.setStyleSheet(
            "background-color: #27AE60; color: white; "
            "font-weight: bold; padding: 10px;"
        )
        self.btn_start_test.clicked.connect(self.start_test)

        selection_layout.addWidget(self.btn_select_board)
        selection_layout.addWidget(self.btn_select_plan)
        selection_layout.addWidget(self.btn_start_test)
        layout.addLayout(selection_layout)

        self.lbl_board = QLabel("Placa: nenhuma selecionada")
        self.lbl_plan = QLabel("Plano: nenhum selecionado")
        layout.addWidget(self.lbl_board)
        layout.addWidget(self.lbl_plan)

        # Ferramentas de mapeamento da placa
        mapping_layout = QHBoxLayout()

        self.btn_edit_points = QPushButton("✏️ Mapear / Editar Pontos")
        self.btn_edit_points.clicked.connect(self.open_image_marker_edit)

        self.btn_view_points = QPushButton("👁️ Visualizar Mapeamento")
        self.btn_view_points.clicked.connect(self.open_image_marker_view)

        self.btn_create_plan = QPushButton("➕ Criar Plano de Teste")
        self.btn_create_plan.clicked.connect(self.open_plan_editor)

        mapping_layout.addWidget(self.btn_edit_points)
        mapping_layout.addWidget(self.btn_view_points)
        mapping_layout.addWidget(self.btn_create_plan)
        layout.addLayout(mapping_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        layout.addWidget(QLabel("Log da execução:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

    def log(self, message):
        self.log_text.append(str(message))
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def import_board_for_test(self, board):
        """Recebe uma placa da aba de cadastro e prepara a tela de testes."""
        self._set_board(board)
        self.log(f"Placa carregada: {board.name} (SN: {board.serial_number})")

    def _set_board(self, board):
        self.selected_board = board

        # Um plano pertence ao modelo da placa. Ao trocar para outro modelo,
        # invalida o plano anterior para impedir execução incompatível.
        if (
            self.selected_plan is not None
            and self.selected_plan.board_model_id != board.model_id
        ):
            self.selected_plan = None
            self.lbl_plan.setText("Plano: nenhum selecionado")

        self.lbl_board.setText(
            f"Placa: {board.name} (SN: {board.serial_number})"
        )
        self.update_button_state()

    def select_board(self):
        boards = self.session.query(BoardUnit).filter_by(is_active=True).all()

        if not boards:
            QMessageBox.warning(self, "Aviso", "Nenhuma placa ativa cadastrada.")
            return

        items = [f"{board.serial_number} - {board.name}" for board in boards]
        item, ok = QInputDialog.getItem(
            self,
            "Selecionar Placa",
            "Escolha a placa:",
            items,
            0,
            False,
        )

        if not ok or not item:
            return

        serial_number = item.split(" - ", 1)[0]
        board = (
            self.session.query(BoardUnit)
            .filter_by(serial_number=serial_number)
            .first()
        )

        if board is None:
            QMessageBox.warning(self, "Erro", "A placa selecionada não foi encontrada.")
            return

        self._set_board(board)
        self.log(f"Placa selecionada: {board.name} (SN: {board.serial_number})")

    def select_plan(self):
        if not self.selected_board:
            QMessageBox.warning(self, "Aviso", "Selecione uma placa primeiro.")
            return

        # PlanManager exige exatamente: session, callback e board_unit.
        self.plan_manager_window = PlanManager(
            self.session,
            self.set_selected_plan,
            self.selected_board,
        )
        self.plan_manager_window.show()
        self.plan_manager_window.raise_()
        self.plan_manager_window.activateWindow()

    def set_selected_plan(self, plan):
        if plan is None:
            return

        if not self.selected_board:
            QMessageBox.warning(self, "Aviso", "Selecione uma placa primeiro.")
            return

        if plan.board_model_id != self.selected_board.model_id:
            QMessageBox.warning(
                self,
                "Plano incompatível",
                "O plano selecionado pertence a outro modelo de placa.",
            )
            return

        self.selected_plan = plan
        self.lbl_plan.setText(f"Plano: {plan.name} v{plan.version}")
        self.log(f"Plano selecionado: {plan.name} v{plan.version}")
        self.update_button_state()

    def update_button_state(self):
        has_board = self.selected_board is not None
        has_plan = self.selected_plan is not None

        self.btn_select_plan.setEnabled(has_board)
        self.btn_start_test.setEnabled(has_board and has_plan)
        self.btn_edit_points.setEnabled(has_board)
        self.btn_view_points.setEnabled(has_board)
        self.btn_create_plan.setEnabled(has_board)

    # Mantém compatibilidade com versões anteriores que chamavam este nome.
    def check_can_start(self):
        self.update_button_state()

    def start_test(self):
        if not self.selected_board or not self.selected_plan:
            QMessageBox.warning(
                self,
                "Aviso",
                "Selecione uma placa e um plano de teste antes de iniciar.",
            )
            return

        if not self.selected_plan.steps:
            QMessageBox.warning(
                self,
                "Plano vazio",
                "O plano selecionado não possui etapas de teste.",
            )
            return

        self.log("=" * 60)
        self.log(f"Iniciando teste: {self.selected_plan.name}")
        self.log(
            f"Placa: {self.selected_board.name} "
            f"(SN: {self.selected_board.serial_number})"
        )
        self.log("=" * 60)

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self._set_execution_controls(False)
        QApplication.processEvents()

        try:
            # run_test retorna uma tupla (TestRun, List[Measurement]).
            run, measurements = run_test(
                session=self.session,
                plan=self.selected_plan,
                board=self.selected_board,
                operator=self.user,
                instruments=self.instruments,
                progress_callback=self.update_progress,
            )

            self.last_run = run
            self.display_test_results(run, measurements)

            reply = QMessageBox.question(
                self,
                "Relatório",
                "Teste concluído. Deseja gerar o relatório em PDF?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.generate_report()

        except Exception as exc:
            self.session.rollback()
            self.log(f"\nERRO DURANTE O TESTE: {exc}")
            logger.exception("Erro durante execução do teste")
            QMessageBox.critical(
                self,
                "Erro durante o teste",
                f"Ocorreu um erro durante o teste:\n{exc}",
            )

        finally:
            self.progress_bar.setVisible(False)
            self._set_execution_controls(True)
            self.update_button_state()

    def _set_execution_controls(self, enabled):
        self.btn_select_board.setEnabled(enabled)
        self.btn_select_plan.setEnabled(enabled and self.selected_board is not None)
        self.btn_edit_points.setEnabled(enabled and self.selected_board is not None)
        self.btn_view_points.setEnabled(enabled and self.selected_board is not None)
        self.btn_create_plan.setEnabled(enabled and self.selected_board is not None)
        self.btn_start_test.setEnabled(
            enabled
            and self.selected_board is not None
            and self.selected_plan is not None
        )

    def update_progress(self, current, total, description):
        progress = int((current / total) * 100) if total else 0
        self.progress_bar.setValue(progress)
        self.log(f"[{current}/{total}] {description}")
        QApplication.processEvents()

    def display_test_results(self, run, measurements):
        self.log("")
        self.log(f"Teste finalizado. Status: {run.status.upper()}")

        for measurement in measurements:
            step = measurement.step
            if measurement.passed is True:
                icon = "✅"
            elif measurement.passed is False:
                icon = "❌"
            else:
                icon = "⏭️"

            value = "-" if measurement.value is None else measurement.value
            unit = measurement.unit or step.unit or ""
            note = f" | {measurement.notes}" if measurement.notes else ""
            self.log(f"{icon} {step.description}: {value} {unit}{note}")

    def generate_report(self):
        if self.last_run is None:
            QMessageBox.warning(self, "Aviso", "Nenhum teste foi executado ainda.")
            return

        image_path = self._choose_board_image()
        if image_path is None:
            return

        default_name = (
            f"Relatorio_{self.selected_board.serial_number}_{self.last_run.id}.pdf"
        )
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Relatório",
            default_name,
            "PDF Files (*.pdf)",
        )

        if not file_name:
            return

        try:
            export_test_report(self.last_run, image_path, file_name)
            self.log(f"\nRelatório salvo em: {file_name}")
            QMessageBox.information(
                self,
                "Sucesso",
                "Relatório gerado com sucesso.",
            )
        except Exception as exc:
            logger.exception("Erro ao gerar relatório")
            self.log(f"\nErro ao gerar relatório: {exc}")
            QMessageBox.critical(self, "Erro", f"Falha ao gerar PDF:\n{exc}")

    def _choose_board_image(self):
        if not self.selected_board or not self.selected_board.images:
            QMessageBox.warning(
                self,
                "Imagem necessária",
                "A placa não possui imagem cadastrada para gerar o relatório.",
            )
            return None

        paths = [image.path for image in self.selected_board.images]

        if len(paths) == 1:
            selected = paths[0]
        else:
            selected, ok = QInputDialog.getItem(
                self,
                "Selecionar Imagem",
                "Escolha a imagem usada no relatório:",
                paths,
                0,
                False,
            )
            if not ok or not selected:
                return None

        if not Path(selected).exists():
            QMessageBox.warning(
                self,
                "Imagem não encontrada",
                f"O arquivo de imagem não existe no caminho cadastrado:\n{selected}",
            )
            return None

        return selected

    def open_image_marker_edit(self):
        from ui.image_marker import ImageMarker

        if not self.selected_board:
            return
        if not self.selected_board.images:
            QMessageBox.warning(
                self,
                "Erro",
                "Nenhuma imagem cadastrada para esta placa.",
            )
            return

        paths = [image.path for image in self.selected_board.images]
        choice, ok = QInputDialog.getItem(
            self,
            "Selecionar Imagem",
            "Escolha a imagem:",
            paths,
            0,
            False,
        )
        if ok and choice:
            self.marker = ImageMarker(
                self.session,
                self.selected_board,
                mode="edit",
                instruments=self.instruments,
            )
            self.marker.load_image(choice)
            self.marker.show()

    def open_image_marker_view(self):
        from ui.image_marker import ImageMarker

        if not self.selected_board:
            return
        if not self.selected_board.images:
            QMessageBox.warning(
                self,
                "Erro",
                "Nenhuma imagem cadastrada para esta placa.",
            )
            return

        paths = [image.path for image in self.selected_board.images]
        choice, ok = QInputDialog.getItem(
            self,
            "Selecionar Imagem",
            "Escolha a imagem:",
            paths,
            0,
            False,
        )
        if ok and choice:
            self.viewer = ImageMarker(
                self.session,
                self.selected_board,
                mode="view",
                instruments=self.instruments,
            )
            self.viewer.load_image(choice)
            self.viewer.show()

    def open_plan_editor(self):
        from ui.plan_editor import PlanEditor

        if not self.selected_board:
            return

        self.editor = PlanEditor(self.session, self.selected_board)
        self.editor.show()
