from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QVBoxLayout, QWidget
)
from sqlalchemy import text

from db.config import create_db_engine, load_network_config, save_network_config
from utils.storage import test_storage_write


class ServerSettingsDialog(QDialog):
    """Configura banco central PostgreSQL e pasta compartilhada da rede."""

    def __init__(self, parent=None, *, error_message: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Servidor e Rede")
        self.setModal(True)
        self.resize(720, 650)
        self.setMinimumSize(680, 600)
        self.config = load_network_config()
        self._build_ui()
        self._load_values()
        self._style()
        if error_message:
            self.status.setText(f"Falha de conexão atual: {error_message}")
            self.status.setProperty("state", "error")
            self._refresh_status_style()

    def _card(self, title, subtitle=""):
        frame = QFrame(); frame.setObjectName("card")
        lay = QVBoxLayout(frame); lay.setContentsMargins(18, 16, 18, 16); lay.setSpacing(10)
        ttl = QLabel(title); ttl.setObjectName("sectionTitle")
        lay.addWidget(ttl)
        if subtitle:
            sub = QLabel(subtitle); sub.setObjectName("sectionSub"); sub.setWordWrap(True)
            lay.addWidget(sub)
        return frame, lay

    def _field(self, placeholder=""):
        w = QLineEdit(); w.setPlaceholderText(placeholder); w.setMinimumHeight(38)
        return w

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        header = QFrame(); header.setObjectName("header")
        hl = QVBoxLayout(header); hl.setContentsMargins(22,18,22,18); hl.setSpacing(3)
        t = QLabel("Servidor e armazenamento compartilhado"); t.setObjectName("title")
        s = QLabel("Configure todos os computadores para usar o mesmo banco e os mesmos arquivos."); s.setObjectName("subtitle")
        hl.addWidget(t); hl.addWidget(s); root.addWidget(header)

        body = QWidget(); bl = QVBoxLayout(body); bl.setContentsMargins(18,16,18,16); bl.setSpacing(14)

        card, lay = self._card("Banco de dados", "PostgreSQL é recomendado para vários computadores trabalhando ao mesmo tempo.")
        form = QFormLayout(); form.setHorizontalSpacing(16); form.setVerticalSpacing(10)
        self.mode = QComboBox(); self.mode.addItem("Servidor PostgreSQL (rede)", "postgresql"); self.mode.addItem("SQLite local (manutenção)", "sqlite")
        self.host = self._field("Ex.: 192.168.1.100 ou SERVIDOR-TECHNORD")
        self.port = QSpinBox(); self.port.setRange(1,65535); self.port.setValue(5432); self.port.setMinimumHeight(38)
        self.database = self._field("technord")
        self.user = self._field("technord_app")
        self.password = self._field("Senha do usuário do banco"); self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_password = QCheckBox("Mostrar senha"); self.show_password.toggled.connect(lambda checked: self.password.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password))
        form.addRow("Modo", self.mode); form.addRow("Servidor", self.host); form.addRow("Porta", self.port); form.addRow("Banco", self.database); form.addRow("Usuário", self.user); form.addRow("Senha", self.password); form.addRow("", self.show_password)
        lay.addLayout(form)
        test_db = QPushButton("Testar conexão com o banco"); test_db.setObjectName("secondary"); test_db.clicked.connect(self.test_database)
        lay.addWidget(test_db, 0, Qt.AlignmentFlag.AlignLeft)
        bl.addWidget(card)

        card, lay = self._card("Arquivos compartilhados", "Datasheets, manuais, imagens das placas e outros arquivos serão gravados nesta pasta para todos os PCs enxergarem.")
        row = QHBoxLayout(); self.storage = self._field(r"Ex.: \\SERVIDOR-TECHNORD\TechNordData")
        choose = QPushButton("Escolher pasta..."); choose.setObjectName("secondary"); choose.clicked.connect(self.choose_storage)
        row.addWidget(self.storage,1); row.addWidget(choose); lay.addLayout(row)
        test_storage = QPushButton("Testar acesso à pasta"); test_storage.setObjectName("secondary"); test_storage.clicked.connect(self.test_storage)
        lay.addWidget(test_storage, 0, Qt.AlignmentFlag.AlignLeft)
        bl.addWidget(card)

        self.status = QLabel("Configure os dados e faça os testes antes de salvar."); self.status.setObjectName("status"); self.status.setWordWrap(True); self.status.setProperty("state", "neutral")
        bl.addWidget(self.status)
        bl.addStretch()
        root.addWidget(body,1)

        footer = QFrame(); footer.setObjectName("footer"); fl = QHBoxLayout(footer); fl.setContentsMargins(18,12,18,12)
        cancel = QPushButton("Cancelar"); cancel.setObjectName("secondary"); cancel.clicked.connect(self.reject)
        save = QPushButton("Salvar configuração"); save.setObjectName("primary"); save.clicked.connect(self.save)
        fl.addStretch(); fl.addWidget(cancel); fl.addWidget(save); root.addWidget(footer)

        self.mode.currentIndexChanged.connect(self._update_enabled)

    def _load_values(self):
        cfg = self.config
        mode = str(cfg.get("mode", "sqlite"))
        idx = self.mode.findData("postgresql" if mode in {"postgres","postgresql"} else "sqlite")
        self.mode.setCurrentIndex(max(0, idx))
        pg = cfg.get("postgres", {})
        self.host.setText(str(pg.get("host") or "")); self.port.setValue(int(pg.get("port") or 5432)); self.database.setText(str(pg.get("database") or "technord")); self.user.setText(str(pg.get("user") or "technord_app")); self.password.setText(str(pg.get("password") or "")); self.storage.setText(str(cfg.get("shared_storage") or ""))
        self._update_enabled()

    def _update_enabled(self):
        enabled = self.mode.currentData() == "postgresql"
        for w in (self.host,self.port,self.database,self.user,self.password,self.show_password): w.setEnabled(enabled)

    def _values(self):
        cfg = load_network_config()
        cfg["mode"] = self.mode.currentData()
        cfg["postgres"] = {
            **cfg.get("postgres", {}),
            "host": self.host.text().strip(),
            "port": int(self.port.value()),
            "database": self.database.text().strip() or "technord",
            "user": self.user.text().strip() or "technord_app",
            "password": self.password.text(),
            "connect_timeout": 5,
        }
        cfg["shared_storage"] = self.storage.text().strip()
        return cfg

    def choose_storage(self):
        path = QFileDialog.getExistingDirectory(self, "Selecionar pasta compartilhada", self.storage.text().strip() or "")
        if path: self.storage.setText(path)

    def test_database(self):
        cfg = self._values()
        if cfg["mode"] != "postgresql":
            self._set_status("Modo SQLite local selecionado.", "ok"); return
        if not cfg["postgres"]["host"]:
            self._set_status("Informe o IP ou nome do servidor PostgreSQL.", "error"); return
        try:
            engine = create_db_engine(cfg)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine.dispose()
            self._set_status("Conexão com PostgreSQL realizada com sucesso.", "ok")
        except Exception as exc:
            self._set_status(f"Falha ao conectar ao PostgreSQL: {exc}", "error")

    def test_storage(self):
        value = self.storage.text().strip()
        if not value:
            self._set_status("Informe a pasta compartilhada.", "error"); return
        ok, msg = test_storage_write(value)
        self._set_status(msg, "ok" if ok else "error")

    def _set_status(self, text_value, state):
        self.status.setText(text_value); self.status.setProperty("state", state); self._refresh_status_style()

    def _refresh_status_style(self):
        self.status.style().unpolish(self.status); self.status.style().polish(self.status)

    def save(self):
        cfg = self._values()
        if cfg["mode"] == "postgresql" and not cfg["postgres"]["host"]:
            QMessageBox.warning(self,"Servidor","Informe o IP ou nome do servidor."); return
        if cfg["mode"] == "postgresql" and not cfg.get("shared_storage"):
            resp = QMessageBox.question(self,"Pasta compartilhada","Você ainda não informou uma pasta compartilhada para documentos e imagens. Deseja salvar mesmo assim?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if resp != QMessageBox.StandardButton.Yes: return
        save_network_config(cfg)
        QMessageBox.information(self,"Configuração salva","A configuração foi salva. Reinicie o programa para trocar a conexão ativa deste computador.")
        self.accept()

    def _style(self):
        self.setStyleSheet("""
            QDialog{background:#F4F7F9;color:#0F172A;font-family:'Segoe UI';}
            QFrame#header{background:#0F172A;border:none;} QLabel#title{color:#F8FAFC;font-size:20px;font-weight:800;} QLabel#subtitle{color:#94A3B8;font-size:11px;}
            QFrame#card{background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;} QLabel#sectionTitle{color:#0F172A;font-size:12px;font-weight:800;} QLabel#sectionSub{color:#64748B;font-size:10px;}
            QLineEdit,QSpinBox,QComboBox{background:#F8FAFC;color:#0F172A;border:1px solid #CBD5E1;border-radius:8px;padding:7px 9px;min-height:24px;} QLineEdit:focus,QSpinBox:focus,QComboBox:focus{background:#FFFFFF;border-color:#0F766E;}
            QLabel#status{padding:10px 12px;border-radius:8px;background:#F1F5F9;color:#475569;border:1px solid #CBD5E1;} QLabel#status[state='ok']{background:#ECFDF5;color:#047857;border-color:#A7F3D0;} QLabel#status[state='error']{background:#FEF2F2;color:#B91C1C;border-color:#FECACA;}
            QFrame#footer{background:#FFFFFF;border-top:1px solid #E2E8F0;} QPushButton#primary{background:#0F766E;color:#FFFFFF;border:none;border-radius:8px;padding:9px 16px;font-weight:700;min-height:34px;} QPushButton#primary:hover{background:#115E59;} QPushButton#secondary{background:#FFFFFF;color:#334155;border:1px solid #CBD5E1;border-radius:8px;padding:9px 14px;font-weight:600;min-height:34px;} QPushButton#secondary:hover{background:#F8FAFC;border-color:#0F766E;}
        """)
