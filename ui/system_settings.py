from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from db.config import load_network_config
from .server_settings import ServerSettingsDialog
from .backup_settings import BackupSettingsDialog


class SystemSettingsDialog(QDialog):
    def __init__(self, backup_manager, parent=None):
        super().__init__(parent)
        self.backup_manager = backup_manager
        self.setWindowTitle("Configurações")
        self.setModal(True)
        self.resize(650, 460)
        self._build()
        self._style()
        self.refresh()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(18,18,18,18); root.setSpacing(14)
        title = QLabel("Configurações do sistema"); title.setObjectName("title")
        sub = QLabel("Conexão em rede, armazenamento compartilhado e política de backup."); sub.setObjectName("sub")
        root.addWidget(title); root.addWidget(sub)

        self.network_card = QFrame(); self.network_card.setObjectName("card")
        nl = QVBoxLayout(self.network_card); nl.setContentsMargins(16,14,16,14); nl.setSpacing(8)
        nt = QLabel("Servidor e rede"); nt.setObjectName("section")
        self.network_summary = QLabel(); self.network_summary.setWordWrap(True); self.network_summary.setObjectName("summary")
        nb = QPushButton("Configurar servidor e pasta compartilhada"); nb.setObjectName("primary"); nb.clicked.connect(self.open_network)
        nl.addWidget(nt); nl.addWidget(self.network_summary); nl.addWidget(nb,0,Qt.AlignmentFlag.AlignLeft)
        root.addWidget(self.network_card)

        backup_card = QFrame(); backup_card.setObjectName("card")
        bl = QVBoxLayout(backup_card); bl.setContentsMargins(16,14,16,14); bl.setSpacing(8)
        bt = QLabel("Backup"); bt.setObjectName("section")
        bs = QLabel("Configure backup diário, backup ao fechar e o diretório de destino."); bs.setObjectName("summary")
        bb = QPushButton("Configurar backup"); bb.setObjectName("secondary"); bb.clicked.connect(self.open_backup)
        bl.addWidget(bt); bl.addWidget(bs); bl.addWidget(bb,0,Qt.AlignmentFlag.AlignLeft)
        root.addWidget(backup_card)
        root.addStretch()

        close = QPushButton("Fechar"); close.setObjectName("secondary"); close.clicked.connect(self.accept)
        row = QHBoxLayout(); row.addStretch(); row.addWidget(close); root.addLayout(row)

    def refresh(self):
        cfg = load_network_config(); pg = cfg.get("postgres", {})
        if cfg.get("mode") in {"postgres","postgresql"}:
            db = f"PostgreSQL • {pg.get('host') or 'servidor não informado'}:{pg.get('port',5432)} • banco {pg.get('database','technord')}"
        else:
            db = "SQLite local"
        storage = cfg.get("shared_storage") or "Pasta compartilhada não configurada"
        self.network_summary.setText(f"Banco: {db}\nArquivos: {storage}\n\nA troca de banco entra em vigor após reiniciar o programa.")

    def open_network(self):
        ServerSettingsDialog(self).exec(); self.refresh()

    def open_backup(self):
        BackupSettingsDialog(self.backup_manager, self).exec()

    def _style(self):
        self.setStyleSheet("""
            QDialog{background:#F4F7F9;color:#0F172A;font-family:'Segoe UI';} QLabel#title{font-size:20px;font-weight:800;} QLabel#sub{color:#64748B;font-size:11px;margin-bottom:4px;} QFrame#card{background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;} QLabel#section{font-size:12px;font-weight:800;} QLabel#summary{color:#475569;font-size:11px;} QPushButton#primary{background:#0F766E;color:white;border:none;border-radius:8px;padding:9px 15px;font-weight:700;} QPushButton#primary:hover{background:#115E59;} QPushButton#secondary{background:#FFFFFF;color:#334155;border:1px solid #CBD5E1;border-radius:8px;padding:9px 15px;font-weight:600;} QPushButton#secondary:hover{background:#F8FAFC;border-color:#0F766E;}
        """)
