from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class BackupSettingsDialog(QDialog):
    """Configuração visual do backup automático."""

    def __init__(self, backup_manager, parent=None):
        super().__init__(parent)
        self.backup_manager = backup_manager
        self.setWindowTitle("Configurações de Backup")
        self.setModal(True)
        self.resize(760, 560)
        self.setMinimumSize(700, 520)
        self._build_ui()
        self._load_values()
        self._style()

    def _card(self, title: str, subtitle: str = ""):
        frame = QFrame()
        frame.setObjectName("backupCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        layout.addWidget(title_label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("cardSub")
            sub.setWordWrap(True)
            layout.addWidget(sub)
        return frame, layout

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("backupHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(22, 18, 22, 18)
        h.setSpacing(12)
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        title = QLabel("Backup do sistema")
        title.setObjectName("backupTitle")
        subtitle = QLabel("Proteja banco de dados, documentos técnicos, imagens e relatórios.")
        subtitle.setObjectName("backupSub")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        h.addLayout(title_box)
        h.addStretch()
        self.status_chip = QLabel("ATIVO")
        self.status_chip.setObjectName("statusChip")
        h.addWidget(self.status_chip)
        root.addWidget(header)

        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(18, 16, 18, 16)
        body_l.setSpacing(14)

        schedule_card, schedule_l = self._card(
            "Automação",
            "Você pode manter as duas opções ligadas. O backup diário é criado no máximo uma vez por dia.",
        )
        self.daily_check = QCheckBox("Criar backup automático diariamente")
        self.daily_check.setObjectName("backupCheck")
        self.close_check = QCheckBox("Criar backup sempre que o programa for fechado")
        self.close_check.setObjectName("backupCheck")
        schedule_l.addWidget(self.daily_check)
        schedule_l.addWidget(self.close_check)

        retention_row = QHBoxLayout()
        retention_row.setSpacing(10)
        retention_label = QLabel("Quantidade máxima de backups mantidos")
        retention_label.setObjectName("fieldLabel")
        self.max_backups = QSpinBox()
        self.max_backups.setRange(1, 365)
        self.max_backups.setSuffix(" arquivos")
        self.max_backups.setMinimumHeight(36)
        retention_row.addWidget(retention_label)
        retention_row.addStretch()
        retention_row.addWidget(self.max_backups)
        schedule_l.addLayout(retention_row)
        body_l.addWidget(schedule_card)

        dest_card, dest_l = self._card(
            "Diretório de destino",
            "Escolha uma pasta local, pasta de rede, HD externo ou outro local com permissão de gravação.",
        )
        row = QHBoxLayout()
        row.setSpacing(8)
        self.path_edit = QLineEdit()
        self.path_edit.setObjectName("pathEdit")
        self.path_edit.setReadOnly(True)
        self.path_edit.setMinimumHeight(38)
        choose_btn = QPushButton("Escolher pasta…")
        choose_btn.setObjectName("secondary")
        choose_btn.clicked.connect(self._choose_directory)
        row.addWidget(self.path_edit, 1)
        row.addWidget(choose_btn)
        dest_l.addLayout(row)

        open_btn = QPushButton("Abrir pasta de backups")
        open_btn.setObjectName("linkButton")
        open_btn.clicked.connect(self._open_directory)
        dest_l.addWidget(open_btn, 0, Qt.AlignmentFlag.AlignLeft)
        body_l.addWidget(dest_card)

        status_card, status_l = self._card("Status", "Informações do último backup registrado.")
        status_grid = QHBoxLayout()
        status_grid.setSpacing(12)
        self.last_backup_label = QLabel("—")
        self.last_backup_label.setObjectName("statusValue")
        self.count_label = QLabel("0")
        self.count_label.setObjectName("statusValue")

        left_box = QVBoxLayout()
        left_caption = QLabel("ÚLTIMO BACKUP")
        left_caption.setObjectName("statusCaption")
        left_box.addWidget(left_caption)
        left_box.addWidget(self.last_backup_label)

        right_box = QVBoxLayout()
        right_caption = QLabel("ARQUIVOS NO DESTINO")
        right_caption.setObjectName("statusCaption")
        right_box.addWidget(right_caption)
        right_box.addWidget(self.count_label)

        status_grid.addLayout(left_box, 1)
        status_grid.addLayout(right_box, 1)
        status_l.addLayout(status_grid)
        body_l.addWidget(status_card)
        body_l.addStretch(1)
        root.addWidget(body, 1)

        footer = QFrame()
        footer.setObjectName("backupFooter")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(18, 12, 18, 12)
        fl.setSpacing(10)
        backup_now = QPushButton("Criar backup agora")
        backup_now.setObjectName("secondary")
        backup_now.clicked.connect(self._backup_now)
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Salvar configurações")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        fl.addWidget(backup_now)
        fl.addStretch()
        fl.addWidget(cancel)
        fl.addWidget(save)
        root.addWidget(footer)

    def _load_values(self):
        cfg = self.backup_manager.config
        self.daily_check.setChecked(bool(cfg.get("daily_backup", True)))
        self.close_check.setChecked(bool(cfg.get("backup_on_close", True)))
        self.max_backups.setValue(int(cfg.get("max_backups", 30)))
        self.path_edit.setText(self.backup_manager.get_backup_directory())
        self._refresh_status()

    def _refresh_status(self):
        stats = self.backup_manager.get_backup_stats()
        last = stats.get("last_backup")
        if last:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(last)
                self.last_backup_label.setText(dt.strftime("%d/%m/%Y %H:%M:%S"))
            except Exception:
                self.last_backup_label.setText(str(last))
        else:
            self.last_backup_label.setText("Nenhum backup realizado")
        self.count_label.setText(str(stats.get("total_backups", 0)))
        enabled = self.daily_check.isChecked() or self.close_check.isChecked()
        self.status_chip.setText("ATIVO" if enabled else "MANUAL")

    def _choose_directory(self):
        start = self.path_edit.text().strip() or str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "Selecionar pasta de backup", start)
        if directory:
            self.path_edit.setText(directory)

    def _open_directory(self):
        path = self.path_edit.text().strip()
        if not path:
            return
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def _backup_now(self):
        # Usa o diretório que está no campo, mesmo antes de salvar o restante.
        try:
            path = self.path_edit.text().strip()
            if path and path != self.backup_manager.get_backup_directory():
                self.backup_manager.set_backup_directory(path)
            result = self.backup_manager.create_backup("manual")
        except Exception as exc:
            QMessageBox.critical(self, "Backup", f"Não foi possível criar o backup.\n\n{exc}")
            return

        if result.get("status") == "success":
            QMessageBox.information(
                self,
                "Backup concluído",
                f"Backup criado com sucesso em:\n{result.get('destination', self.backup_manager.get_backup_directory())}",
            )
        else:
            QMessageBox.warning(
                self,
                "Backup",
                f"O backup não foi concluído.\n\n{result.get('error', result.get('status'))}",
            )
        self._refresh_status()

    def _save(self):
        directory = self.path_edit.text().strip()
        if not directory:
            QMessageBox.warning(self, "Backup", "Escolha um diretório para os backups.")
            return
        try:
            self.backup_manager.update_config({
                "backup_directory": directory,
                "daily_backup": self.daily_check.isChecked(),
                "backup_on_close": self.close_check.isChecked(),
                "max_backups": self.max_backups.value(),
            })
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Diretório inválido",
                f"Não foi possível usar a pasta selecionada.\n\n{exc}",
            )
            return
        self.accept()

    def _style(self):
        self.setStyleSheet("""
            QDialog { background:#F5F7FA; color:#0F172A; font-family:'Segoe UI'; }
            QFrame#backupHeader { background:#0F172A; border-bottom:1px solid #1E293B; }
            QLabel#backupTitle { color:#F8FAFC; font-size:20px; font-weight:800; }
            QLabel#backupSub { color:#94A3B8; font-size:11px; }
            QLabel#statusChip { color:#5EEAD4; background:#103C38; border:1px solid #17645F; border-radius:11px; padding:6px 10px; font-size:10px; font-weight:800; }
            QFrame#backupCard { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:11px; }
            QLabel#cardTitle { color:#0F172A; font-size:12px; font-weight:800; }
            QLabel#cardSub { color:#64748B; font-size:10px; }
            QLabel#fieldLabel { color:#334155; font-size:11px; font-weight:600; }
            QCheckBox#backupCheck { color:#1E293B; spacing:9px; font-size:11px; padding:5px 0; }
            QCheckBox#backupCheck::indicator { width:18px; height:18px; }
            QLineEdit#pathEdit, QSpinBox { background:#F8FAFC; border:1px solid #CBD5E1; border-radius:7px; padding:7px 9px; color:#0F172A; }
            QLabel#statusCaption { color:#64748B; font-size:9px; font-weight:800; }
            QLabel#statusValue { color:#0F766E; font-size:13px; font-weight:800; }
            QFrame#backupFooter { background:#FFFFFF; border-top:1px solid #E2E8F0; }
            QPushButton#primary { background:#0F766E; color:white; border:none; border-radius:7px; min-height:36px; padding:0 16px; font-weight:700; }
            QPushButton#primary:hover { background:#115E59; }
            QPushButton#secondary { background:#FFFFFF; color:#334155; border:1px solid #CBD5E1; border-radius:7px; min-height:36px; padding:0 14px; font-weight:600; }
            QPushButton#secondary:hover { background:#F1F5F9; border-color:#94A3B8; }
            QPushButton#linkButton { background:transparent; color:#0F766E; border:none; text-align:left; padding:2px 0; font-weight:700; }
            QPushButton#linkButton:hover { color:#115E59; text-decoration:underline; }
        """)
