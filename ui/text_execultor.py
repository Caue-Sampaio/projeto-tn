from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QTextEdit,
    QMessageBox,
    QInputDialog,
    QDialog,
    QFileDialog,
    QApplication,
)

from db.models import BoardUnit
from ui.plan_manager import PlanManager
from engine.runner import run_test
from engine.pdf_report import export_test_report

import logging


logger = logging.getLogger(__name__)


class FakeDMM:
    def measure_voltage(self, range_v=None):
        return 3.29


class FakeScope:
    def capture_waveform(self):
        return "sinewave_1k_3v"


class TestExecutor(QWidget):
    def __init__(self, session, current_user):
        super().__init__()

        self.session = session
        self.user = current_user

        self.selected_board = None
        self.selected_plan = None
        self.last_run = None

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Botões principais
        btn_layout = QHBoxLayout()

        self.btn_select_board = QPushButton("🔌 Selecionar Placa")
        self.btn_select_board.clicked.connect(self.select_board)

        self.btn_select_plan = QPushButton("📋 Selecionar Plano")
        self.btn_select_plan.clicked.connect(self.select_plan)

        self.btn_start_test = QPushButton("▶️ INICIAR TESTE")
        self.btn_start_test.setStyleSheet(
            "background-color: #27ae60; "
            "color: white; "
            "font-weight: bold; "
            "padding: 10px;"
        )
        self.btn_start_test.clicked.connect(self.start_test)
        self.btn_start_test.setEnabled(False)

        btn_layout.addWidget(self.btn_select_board)
        btn_layout.addWidget(self.btn_select_plan)
        btn_layout.addWidget(self.btn_start_test)

        layout.addLayout(btn_layout)

        # Labels de informação
        self.lbl_board = QLabel("Nenhuma placa selecionada")
        self.lbl_plan = QLabel("Nenhum plano selecionado")

        layout.addWidget(self.lbl_board)
        layout.addWidget(self.lbl_plan)

        # Log
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)

        layout.addWidget(self.log_text)

    def log(self, message):
        """Adiciona mensagem ao log na tela."""
        self.log_text.append(str(message))

        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def import_board_for_test(self, board):
        """Recebe uma placa de outra aba para teste."""

        self.selected_board = board

        self.lbl_board.setText(
            f"Placa selecionada: {board.name} "
            f"(SN: {board.serial_number})"
        )

        self.check_can_start()

        self.log(f"Placa carregada: {board.name}")

    def select_board(self):
        boards = (
            self.session.query(BoardUnit)
            .filter_by(is_active=True)
            .all()
        )

        if not boards:
            QMessageBox.warning(
                self,
                "Aviso",
                "Nenhuma placa cadastrada!",
            )
            return

        items = [
            f"{board.serial_number} - {board.name}"
            for board in boards
        ]

        item, ok = QInputDialog.getItem(
            self,
            "Selecionar Placa",
            "Escolha a placa:",
            items,
            0,
            False,
        )

        if ok and item:
            serial_number = item.split(" - ")[0]

            self.selected_board = (
                self.session.query(BoardUnit)
                .filter_by(serial_number=serial_number)
                .first()
            )

            self.lbl_board.setText(
                f"Placa selecionada: "
                f"{self.selected_board.name} "
                f"(SN: {serial_number})"
            )

            self.check_can_start()

    def select_plan(self):
        if not self.selected_board:
            QMessageBox.warning(
                self,
                "Aviso",
                "Selecione uma placa primeiro!",
            )
            return

        dialog = QDialog(self)

        dialog.setWindowTitle("Selecionar Plano de Teste")
        dialog.setMinimumSize(800, 600)

        layout = QVBoxLayout(dialog)

        plan_manager = PlanManager(
            self.session,
            self.set_selected_plan,
            self.selected_board,
        )

        layout.addWidget(plan_manager)

        btn_confirm = QPushButton("Confirmar Seleção")

        btn_confirm.clicked.connect(dialog.accept)

        layout.addWidget(btn_confirm)

        dialog.exec()

    def set_selected_plan(self, plan):
        """Define o plano selecionado."""

        if not plan:
            return

        self.selected_plan = plan

        self.lbl_plan.setText(
            f"Plano selecionado: "
            f"{plan.name} v{plan.version}"
        )

        self.log(
            f"Plano selecionado: "
            f"{plan.name} v{plan.version}"
        )

        self.check_can_start()

    def check_can_start(self):
        has_board = self.selected_board is not None
        has_plan = self.selected_plan is not None

        self.btn_start_test.setEnabled(
            has_board and has_plan
        )

    def start_test(self):
        if not self.selected_board or not self.selected_plan:
            QMessageBox.warning(
                self,
                "Aviso",
                "Selecione uma placa e um plano de teste.",
            )
            return

        self.log("=" * 50)

        self.log(
            f"Iniciando teste: "
            f"{self.selected_plan.name}"
        )

        self.log(
            f"Placa: "
            f"{self.selected_board.name} "
            f"(SN: {self.selected_board.serial_number})"
        )

        self.log("=" * 50)

        self.btn_start_test.setEnabled(False)
        self.btn_select_board.setEnabled(False)
        self.btn_select_plan.setEnabled(False)

        QApplication.processEvents()

        try:
            instruments = {
                "DMM": FakeDMM(),
                "OSC": FakeScope(),
            }

            run, measurements = run_test(
                self.session,
                self.selected_plan,
                self.selected_board,
                self.user,
                instruments,
            )

            self.last_run = run

            self.log("")
            self.log(
                f"Teste concluído! "
                f"Status: {run.status}"
            )

            for measurement in measurements:
                step = measurement.step

                result_icon = (
                    "✅"
                    if measurement.passed
                    else "❌"
                )

                self.log(
                    f"{result_icon} "
                    f"{step.description} - "
                    f"Medido: {measurement.value}"
                )

            reply = QMessageBox.question(
                self,
                "Relatório",
                (
                    "Teste concluído. "
                    "Deseja gerar o relatório em PDF?"
                ),
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.generate_report()

        except Exception as e:
            self.log(
                f"\nERRO DURANTE O TESTE: {e}"
            )

            logger.error(
                f"Erro no teste: {e}",
                exc_info=True,
            )

            QMessageBox.critical(
                self,
                "Erro Fatal",
                (
                    "Ocorreu um erro durante o teste:\n"
                    f"{e}"
                ),
            )

        finally:
            self.btn_select_board.setEnabled(True)
            self.btn_select_plan.setEnabled(True)

            self.check_can_start()

    def generate_report(self):
        if not self.last_run:
            QMessageBox.warning(
                self,
                "Aviso",
                "Nenhum teste foi executado ainda.",
            )
            return

        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Relatório",
            (
                f"Relatorio_"
                f"{self.selected_board.serial_number}_"
                f"{self.last_run.id}.pdf"
            ),
            "PDF Files (*.pdf)",
        )

        if not file_name:
            return

        try:
            export_test_report(
                self.session,
                self.last_run.id,
                file_name,
            )

            self.log(
                f"\nRelatório salvo em: {file_name}"
            )

            QMessageBox.information(
                self,
                "Sucesso",
                "Relatório gerado com sucesso!",
            )

        except Exception as e:
            self.log(
                f"\nErro ao gerar relatório: {e}"
            )

            QMessageBox.critical(
                self,
                "Erro",
                f"Falha ao gerar PDF:\n{e}",
            )