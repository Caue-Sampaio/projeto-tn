from pathlib import Path
from datetime import datetime
import shutil

from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QComboBox, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QFileDialog, QDialog, QFormLayout, QTextEdit, QSplitter,
    QAbstractItemView, QTreeWidget, QTreeWidgetItem,
)

from db.models import Machine, BoardUnit, MachineDocument, BoardDocument


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOC_ID_ROLE = Qt.ItemDataRole.UserRole


def _resolve_file(stored_path):
    if not stored_path:
        return None
    p = Path(str(stored_path))
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p if p.exists() else None


def _copy_document(source_path: str, kind: str, entity_id: int) -> str:
    source = Path(source_path)
    folder = "machines" if kind == "equipment" else "boards"
    target_dir = PROJECT_ROOT / "documents" / folder / str(entity_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_name = source.name.replace(" ", "_")
    target = target_dir / f"{stamp}_{safe_name}"
    shutil.copy2(source, target)
    return str(target.relative_to(PROJECT_ROOT))


class AddDocumentDialog(QDialog):
    def __init__(self, entity_label: str, parent=None):
        super().__init__(parent)
        self._selected_file = ""
        self.setWindowTitle("Adicionar documento técnico")
        self.setModal(True)
        self.resize(640, 360)
        self.setMinimumWidth(600)

        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        header = QFrame(); header.setObjectName("docHeader")
        hl = QVBoxLayout(header); hl.setContentsMargins(22, 18, 22, 18); hl.setSpacing(4)
        t = QLabel("Adicionar documento técnico"); t.setObjectName("docTitle")
        s = QLabel(entity_label); s.setObjectName("docSub")
        hl.addWidget(t); hl.addWidget(s); root.addWidget(header)

        body = QFrame(); body.setObjectName("docBody")
        bl = QVBoxLayout(body); bl.setContentsMargins(22, 18, 22, 18); bl.setSpacing(14)
        form = QFormLayout(); form.setHorizontalSpacing(14); form.setVerticalSpacing(12)
        self.title_input = QLineEdit(); self.title_input.setPlaceholderText("Ex.: Datasheet do inversor")
        self.file_input = QLineEdit(); self.file_input.setReadOnly(True); self.file_input.setPlaceholderText("Selecione um arquivo")
        browse = QPushButton("Selecionar arquivo"); browse.setObjectName("secondary"); browse.clicked.connect(self._browse)
        file_row = QHBoxLayout(); file_row.setSpacing(8); file_row.addWidget(self.file_input, 1); file_row.addWidget(browse)
        self.notes = QTextEdit(); self.notes.setPlaceholderText("Observações, revisão, páginas importantes..."); self.notes.setMaximumHeight(90)
        form.addRow("Título *", self.title_input); form.addRow("Arquivo *", file_row); form.addRow("Observações", self.notes)
        bl.addLayout(form)
        actions = QHBoxLayout(); actions.addStretch()
        cancel = QPushButton("Cancelar"); cancel.setObjectName("secondary"); cancel.clicked.connect(self.reject)
        save = QPushButton("Adicionar documento"); save.setObjectName("primary"); save.clicked.connect(self._validate)
        actions.addWidget(cancel); actions.addWidget(save); bl.addLayout(actions); root.addWidget(body, 1)
        self.setStyleSheet(self._style())

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar documento técnico", "",
            "Documentos (*.pdf *.doc *.docx *.xls *.xlsx *.txt *.csv *.png *.jpg *.jpeg *.zip);;Todos os arquivos (*.*)"
        )
        if path:
            self._selected_file = path; self.file_input.setText(path)
            if not self.title_input.text().strip(): self.title_input.setText(Path(path).stem.replace("_", " "))

    def _validate(self):
        if not self.title_input.text().strip():
            QMessageBox.warning(self, "Documento", "Informe um título para o documento."); return
        if not self._selected_file:
            QMessageBox.warning(self, "Documento", "Selecione um arquivo."); return
        self.accept()

    def values(self):
        return self.title_input.text().strip(), self._selected_file, self.notes.toPlainText().strip() or None

    @staticmethod
    def _style():
        return """
        QDialog { background:#F4F7F9; color:#0F172A; font-family:'Segoe UI'; }
        QFrame#docHeader { background:#0F172A; border-bottom:1px solid #1E293B; }
        QLabel#docTitle { color:#FFFFFF; font-size:19px; font-weight:800; }
        QLabel#docSub { color:#94A3B8; font-size:10px; }
        QFrame#docBody { background:#F4F7F9; }
        QLineEdit, QTextEdit { background:#FFFFFF; color:#0F172A; border:1px solid #CBD5E1; border-radius:8px; padding:8px 10px; }
        QLineEdit:focus, QTextEdit:focus { border-color:#0F766E; }
        QPushButton#primary { background:#0F766E; color:white; border:none; border-radius:8px; min-height:38px; padding:0 16px; font-weight:700; }
        QPushButton#primary:hover { background:#115E59; }
        QPushButton#secondary { background:#FFFFFF; color:#334155; border:1px solid #CBD5E1; border-radius:8px; min-height:36px; padding:0 14px; font-weight:600; }
        QPushButton#secondary:hover { border-color:#0F766E; }
        """


class TechnicalDocuments(QWidget):
    """Biblioteca técnica com visão geral e navegação Equipamento -> Placas."""

    back_requested = pyqtSignal()
    KIND_ROLE = Qt.ItemDataRole.UserRole
    ID_ROLE = Qt.ItemDataRole.UserRole + 1
    DOC_KIND_ROLE = Qt.ItemDataRole.UserRole + 2

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self._kind = "all"
        self._entity_id = None
        self._documents = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        self.setObjectName("docsRoot")
        self.setStyleSheet(self._style())
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        header = QFrame(); header.setObjectName("docsHeader")
        hl = QHBoxLayout(header); hl.setContentsMargins(20, 16, 20, 16); hl.setSpacing(12)
        back = QPushButton("← Dashboard"); back.setObjectName("headerSecondary"); back.clicked.connect(self.back_requested)
        text = QVBoxLayout(); text.setSpacing(2)
        title = QLabel("Documentos Técnicos"); title.setObjectName("docsTitle")
        sub = QLabel("Biblioteca geral de manuais, datasheets, diagramas e arquivos de Equipamentos e Placas."); sub.setObjectName("docsSub")
        text.addWidget(title); text.addWidget(sub)
        hl.addWidget(back); hl.addLayout(text, 1)
        self.add_btn = QPushButton("+ Adicionar documento"); self.add_btn.setObjectName("primary"); self.add_btn.clicked.connect(self.add_document)
        self.add_btn.setEnabled(False)
        self.add_btn.setToolTip("Selecione um Equipamento ou Placa para adicionar um documento.")
        hl.addWidget(self.add_btn)
        root.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # LEFT — navegação por equipamento e placa.
        left = QFrame(); left.setObjectName("selectorCard")
        left.setMinimumWidth(330); left.setMaximumWidth(470)
        ll = QVBoxLayout(left); ll.setContentsMargins(16, 16, 16, 16); ll.setSpacing(10)
        cap = QLabel("EQUIPAMENTOS E PLACAS"); cap.setObjectName("caption")
        hint = QLabel("Use a busca para localizar um equipamento. Expanda-o para acessar suas placas.")
        hint.setObjectName("treeHint"); hint.setWordWrap(True)
        ll.addWidget(cap); ll.addWidget(hint)

        self.asset_search = QLineEdit()
        self.asset_search.setObjectName("assetSearch")
        self.asset_search.setPlaceholderText("Pesquisar equipamento...")
        self.asset_search.setClearButtonEnabled(True)
        self.asset_search.textChanged.connect(self._apply_asset_search)
        ll.addWidget(self.asset_search)

        self.tree = QTreeWidget()
        self.tree.setObjectName("assetTree")
        self.tree.setHeaderLabels(["Item", "Docs"])
        self.tree.setRootIsDecorated(True)
        self.tree.setItemsExpandable(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(18)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.currentItemChanged.connect(self._tree_selection_changed)
        self.tree.itemClicked.connect(self._tree_clicked)
        ll.addWidget(self.tree, 1)

        info = QFrame(); info.setObjectName("infoCard")
        il = QVBoxLayout(info); il.setContentsMargins(13, 12, 13, 12); il.setSpacing(4)
        self.entity_title = QLabel("Todos os documentos"); self.entity_title.setObjectName("entityTitle"); self.entity_title.setWordWrap(True)
        self.entity_meta = QLabel("Visão geral da biblioteca técnica."); self.entity_meta.setObjectName("entityMeta"); self.entity_meta.setWordWrap(True)
        self.entity_count = QLabel("0 documentos"); self.entity_count.setObjectName("countChip")
        il.addWidget(self.entity_title); il.addWidget(self.entity_meta); il.addSpacing(4); il.addWidget(self.entity_count, 0, Qt.AlignmentFlag.AlignLeft)
        ll.addWidget(info)
        splitter.addWidget(left)

        # RIGHT — catálogo de documentos.
        right = QFrame(); right.setObjectName("tableCard")
        rl = QVBoxLayout(right); rl.setContentsMargins(16, 16, 16, 16); rl.setSpacing(10)
        top = QHBoxLayout(); top.setSpacing(10)
        self.section_label = QLabel("Todos os documentos cadastrados"); self.section_label.setObjectName("sectionTitle")
        top.addWidget(self.section_label); top.addStretch()
        self.search = QLineEdit()
        self.search.setObjectName("documentSearch")
        self.search.setPlaceholderText("Pesquisar documento, equipamento, placa, tipo ou modelo...")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(360); self.search.setMaximumWidth(520)
        self.search.textChanged.connect(self._apply_search)
        top.addWidget(self.search)
        rl.addLayout(top)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Documento", "Tipo", "Equipamento", "Placa", "Modelo / código",
            "Arquivo", "Adicionado em", "Observações"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(self.open_selected)
        rl.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.path_note = QLabel("Duplo clique abre o arquivo. A pesquisa acima atua sobre toda a identificação do documento.")
        self.path_note.setObjectName("hint")
        bottom.addWidget(self.path_note); bottom.addStretch()
        open_btn = QPushButton("Abrir arquivo"); open_btn.setObjectName("secondary"); open_btn.clicked.connect(self.open_selected)
        remove_btn = QPushButton("Remover documento"); remove_btn.setObjectName("danger"); remove_btn.clicked.connect(self.remove_selected)
        bottom.addWidget(open_btn); bottom.addWidget(remove_btn)
        rl.addLayout(bottom)
        splitter.addWidget(right)
        splitter.setSizes([380, 980]); splitter.setStretchFactor(0, 0); splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    # TREE / NAVIGATION
    # ------------------------------------------------------------------
    def refresh(self):
        selected = (self._kind, self._entity_id)
        self.tree.blockSignals(True)
        self.tree.clear()
        match = None

        # Visão geral sempre fica no topo e é o estado padrão da tela.
        all_count = self.session.query(MachineDocument).count() + self.session.query(BoardDocument).count()
        all_item = QTreeWidgetItem(["Todos os documentos", str(all_count)])
        all_item.setData(0, self.KIND_ROLE, "all")
        all_item.setData(0, self.ID_ROLE, None)
        all_item.setToolTip(0, "Exibe documentos de todos os Equipamentos e Placas")
        self.tree.addTopLevelItem(all_item)
        if selected[0] == "all" or selected[0] is None:
            match = all_item

        machines = self.session.query(Machine).order_by(Machine.name.asc()).all()
        for machine in machines:
            item = QTreeWidgetItem([machine.name or f"Equipamento {machine.id}", str(len(machine.documents or []))])
            item.setData(0, self.KIND_ROLE, "equipment")
            item.setData(0, self.ID_ROLE, machine.id)
            item.setData(0, Qt.ItemDataRole.UserRole + 10, " ".join([
                machine.name or "", machine.code or "", machine.description or ""
            ]).casefold())
            item.setToolTip(0, "Equipamento" + (f" • Código {machine.code}" if machine.code else ""))
            self.tree.addTopLevelItem(item)
            if selected == ("equipment", machine.id):
                match = item

            boards = sorted(list(machine.boards or []), key=lambda b: (b.name or "").casefold())
            for board in boards:
                label = board.name or f"Placa {board.id}"
                child = QTreeWidgetItem([label, str(len(board.documents or []))])
                child.setData(0, self.KIND_ROLE, "board")
                child.setData(0, self.ID_ROLE, board.id)
                meta = " • ".join([x for x in [board.model, f"SN {board.serial_number}" if board.serial_number else None] if x])
                child.setToolTip(0, meta or "Placa")
                item.addChild(child)
                if selected == ("board", board.id):
                    match = child
                    item.setExpanded(True)

        orphans = self.session.query(BoardUnit).filter(BoardUnit.machine_id.is_(None)).order_by(BoardUnit.name.asc()).all()
        if orphans:
            group = QTreeWidgetItem(["Placas sem equipamento", ""])
            group.setData(0, self.KIND_ROLE, "group")
            group.setData(0, self.ID_ROLE, None)
            group.setData(0, Qt.ItemDataRole.UserRole + 10, "placas sem equipamento")
            self.tree.addTopLevelItem(group)
            for board in orphans:
                child = QTreeWidgetItem([board.name or f"Placa {board.id}", str(len(board.documents or []))])
                child.setData(0, self.KIND_ROLE, "board")
                child.setData(0, self.ID_ROLE, board.id)
                child.setToolTip(0, board.model or "Placa sem equipamento")
                group.addChild(child)
                if selected == ("board", board.id):
                    match = child
                    group.setExpanded(True)

        self.tree.blockSignals(False)
        self._apply_asset_search()

        if match is None:
            match = all_item
        self.tree.setCurrentItem(match)
        self._tree_selection_changed(match, None)

    def _apply_asset_search(self):
        """Filtra somente a navegação lateral de Equipamentos."""
        term = self.asset_search.text().strip().casefold() if hasattr(self, "asset_search") else ""
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            kind = item.data(0, self.KIND_ROLE)
            if kind == "all":
                item.setHidden(False)
                continue
            if not term:
                item.setHidden(False)
                continue
            search_text = item.data(0, Qt.ItemDataRole.UserRole + 10) or item.text(0).casefold()
            item.setHidden(term not in str(search_text))

    def _tree_clicked(self, item, column):
        if not item:
            return
        kind = item.data(0, self.KIND_ROLE)
        if kind in ("equipment", "group"):
            item.setExpanded(not item.isExpanded())

    def _tree_selection_changed(self, current, previous):
        if not current:
            self._show_no_selection("Selecione um item", "Escolha Todos os documentos, um Equipamento ou uma Placa.")
            return
        kind = current.data(0, self.KIND_ROLE)
        entity_id = current.data(0, self.ID_ROLE)

        if kind == "all":
            self._kind = "all"; self._entity_id = None
            self._load_all_documents()
            return

        if kind == "group":
            self._kind = None; self._entity_id = None; self._documents = []
            self._show_no_selection("Placas sem equipamento", "Selecione uma placa deste grupo para visualizar seus documentos.")
            return

        self._kind = kind
        self._entity_id = int(entity_id) if entity_id is not None else None
        self._load_current_documents()

    # ------------------------------------------------------------------
    # DOCUMENT CATALOG
    # ------------------------------------------------------------------
    def _machine_doc_row(self, doc):
        machine = doc.machine
        machine_name = machine.name if machine else "Equipamento removido"
        machine_code = machine.code if machine else None
        # O cadastro atual de Equipamento possui código, não um campo próprio de modelo.
        model_or_code = machine_code or "—"
        return {
            "doc": doc,
            "kind": "equipment",
            "title": doc.title or "—",
            "type": "Equipamento",
            "equipment": machine_name,
            "board": "—",
            "model": model_or_code,
            "file": doc.original_name or Path(doc.file_path).name,
            "date": doc.created_at.strftime("%d/%m/%Y %H:%M") if doc.created_at else "—",
            "notes": doc.notes or "—",
            "search_extra": " ".join([
                machine_name, machine_code or "", machine.description or "" if machine else ""
            ]),
        }

    def _board_doc_row(self, doc):
        board = doc.board
        board_name = board.name if board else "Placa removida"
        machine_name = board.machine.name if board and board.machine else "Sem equipamento"
        machine_code = board.machine.code if board and board.machine else ""
        model = board.model if board else "—"
        serial = board.serial_number if board else ""
        return {
            "doc": doc,
            "kind": "board",
            "title": doc.title or "—",
            "type": "Placa",
            "equipment": machine_name,
            "board": board_name,
            "model": model or "—",
            "file": doc.original_name or Path(doc.file_path).name,
            "date": doc.created_at.strftime("%d/%m/%Y %H:%M") if doc.created_at else "—",
            "notes": doc.notes or "—",
            "search_extra": " ".join([machine_code or "", serial or ""]),
        }

    def _load_all_documents(self):
        machine_docs = self.session.query(MachineDocument).order_by(MachineDocument.created_at.desc()).all()
        board_docs = self.session.query(BoardDocument).order_by(BoardDocument.created_at.desc()).all()
        rows = [self._machine_doc_row(d) for d in machine_docs]
        rows += [self._board_doc_row(d) for d in board_docs]
        rows.sort(key=lambda r: getattr(r["doc"], "created_at", None) or datetime.min, reverse=True)
        self._documents = rows
        self.entity_title.setText("Todos os documentos")
        self.entity_meta.setText("Documentos cadastrados em Equipamentos e Placas, reunidos em uma única biblioteca.")
        self.entity_count.setText(f"{len(rows)} documento(s)")
        self.section_label.setText("Todos os documentos cadastrados")
        self.add_btn.setEnabled(False)
        self.add_btn.setToolTip("Selecione um Equipamento ou uma Placa na esquerda para adicionar um documento.")
        self._apply_search()

    def _show_no_selection(self, title, meta):
        self.entity_title.setText(title)
        self.entity_meta.setText(meta)
        self.entity_count.setText("0 documentos")
        self.section_label.setText("Arquivos vinculados")
        self.add_btn.setEnabled(False)
        self._documents = []
        self._fill_table([])

    def _current_entity(self):
        if self._entity_id is None or self._kind not in ("equipment", "board"):
            return None
        cls = Machine if self._kind == "equipment" else BoardUnit
        return self.session.get(cls, int(self._entity_id))

    def _load_current_documents(self):
        entity = self._current_entity()
        if not entity:
            self._show_no_selection("Item não encontrado", "O cadastro pode ter sido removido.")
            return

        self.add_btn.setEnabled(True)
        self.add_btn.setToolTip("")
        self.entity_title.setText(entity.name or "—")
        if self._kind == "equipment":
            board_count = len(entity.boards or [])
            meta = f"Equipamento #{entity.id}" + (f" • Código {entity.code}" if getattr(entity, "code", None) else "")
            meta += f" • {board_count} placa(s) vinculada(s)"
            self.entity_meta.setText(meta)
            self.section_label.setText("Documentos do equipamento")
            docs = self.session.query(MachineDocument).filter(MachineDocument.machine_id == entity.id).order_by(MachineDocument.created_at.desc()).all()
            self._documents = [self._machine_doc_row(d) for d in docs]
        else:
            equipment = entity.machine.name if entity.machine else "Sem equipamento"
            self.entity_meta.setText(f"Placa #{entity.id} • {entity.model or 'Sem modelo'} • {equipment}")
            self.section_label.setText("Documentos da placa")
            docs = self.session.query(BoardDocument).filter(BoardDocument.board_id == entity.id).order_by(BoardDocument.created_at.desc()).all()
            self._documents = [self._board_doc_row(d) for d in docs]

        self.entity_count.setText(f"{len(self._documents)} documento(s)")
        self._apply_search()

    def _apply_search(self):
        term = self.search.text().strip().casefold()
        rows = self._documents
        if term:
            filtered = []
            for row in rows:
                haystack = " ".join([
                    row.get("title", ""), row.get("type", ""), row.get("equipment", ""),
                    row.get("board", ""), row.get("model", ""), row.get("file", ""),
                    row.get("notes", ""), row.get("search_extra", ""),
                ]).casefold()
                if term in haystack:
                    filtered.append(row)
            rows = filtered
        self._fill_table(rows)

    def _fill_table(self, rows):
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(0)
            for row in rows:
                r = self.table.rowCount(); self.table.insertRow(r); self.table.setRowHeight(r, 44)
                values = [
                    row["title"], row["type"], row["equipment"], row["board"],
                    row["model"], row["file"], row["date"], row["notes"],
                ]
                for c, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(value)
                    if c == 0:
                        item.setData(DOC_ID_ROLE, row["doc"].id)
                        item.setData(self.DOC_KIND_ROLE, row["kind"])
                    self.table.setItem(r, c, item)
            if rows:
                self.table.selectRow(0)
        finally:
            self.table.setUpdatesEnabled(True)

    def _selected_doc(self):
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return None
        item = self.table.item(row, 0)
        doc_id = item.data(DOC_ID_ROLE)
        kind = item.data(self.DOC_KIND_ROLE)
        if doc_id is None or kind not in ("equipment", "board"):
            return None
        cls = MachineDocument if kind == "equipment" else BoardDocument
        return self.session.get(cls, int(doc_id))

    # ------------------------------------------------------------------
    # ACTIONS
    # ------------------------------------------------------------------
    def add_document(self):
        entity = self._current_entity()
        if not entity:
            QMessageBox.information(self, "Documento", "Selecione um Equipamento ou uma Placa na lista à esquerda.")
            return
        kind_label = "Equipamento" if self._kind == "equipment" else "Placa"
        dlg = AddDocumentDialog(f"{kind_label}: {entity.name}", self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        title, source, notes = dlg.values()
        try:
            stored = _copy_document(source, self._kind, entity.id)
            if self._kind == "equipment":
                doc = MachineDocument(machine_id=entity.id, title=title, file_path=stored, original_name=Path(source).name, notes=notes)
            else:
                doc = BoardDocument(board_id=entity.id, title=title, file_path=stored, original_name=Path(source).name, notes=notes)
            self.session.add(doc); self.session.commit()
            self.refresh()
        except Exception as exc:
            self.session.rollback(); QMessageBox.critical(self, "Documento", f"Não foi possível adicionar o arquivo.\n\n{exc}")

    def open_selected(self, *args):
        doc = self._selected_doc()
        if not doc:
            QMessageBox.information(self, "Documento", "Selecione um documento."); return
        path = _resolve_file(doc.file_path)
        if not path:
            QMessageBox.warning(self, "Arquivo não encontrado", "O documento está cadastrado, mas o arquivo não foi localizado no projeto."); return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def remove_selected(self):
        doc = self._selected_doc()
        if not doc:
            QMessageBox.information(self, "Documento", "Selecione um documento."); return
        ans = QMessageBox.question(self, "Remover documento", "Remover este documento do cadastro?\n\nO arquivo físico será mantido na pasta do projeto.")
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            self.session.delete(doc); self.session.commit(); self.refresh()
        except Exception as exc:
            self.session.rollback(); QMessageBox.critical(self, "Documento", f"Não foi possível remover o documento.\n\n{exc}")

    @staticmethod
    def _style():
        return """
        QWidget#docsRoot { background:#F4F7F9; color:#0F172A; font-family:'Segoe UI'; }
        QFrame#docsHeader { background:#0F172A; border:1px solid #1E293B; border-radius:12px; }
        QLabel#docsTitle { color:#FFFFFF; font-size:19px; font-weight:800; }
        QLabel#docsSub { color:#94A3B8; font-size:10px; }
        QPushButton#headerSecondary { background:#152033; color:#E2E8F0; border:1px solid #2A3B55; border-radius:7px; min-height:34px; padding:0 12px; font-weight:700; }
        QPushButton#headerSecondary:hover { border-color:#2DD4BF; }
        QFrame#selectorCard, QFrame#tableCard { background:#FFFFFF; border:1px solid #DCE5EC; border-radius:11px; }
        QFrame#infoCard { background:#F8FAFC; border:1px solid #E2E8F0; border-radius:9px; }
        QLabel#caption { color:#64748B; font-size:9px; font-weight:800; letter-spacing:.7px; }
        QLabel#treeHint, QLabel#entityMeta, QLabel#hint { color:#64748B; font-size:10px; }
        QLabel#entityTitle { color:#0F172A; font-size:14px; font-weight:800; }
        QLabel#countChip { color:#0F766E; background:#ECFDF5; border:1px solid #A7F3D0; border-radius:9px; padding:4px 8px; font-size:9px; font-weight:800; }
        QLabel#sectionTitle { color:#0F172A; font-size:14px; font-weight:800; }
        QTreeWidget#assetTree { background:#F8FAFC; color:#334155; border:1px solid #E2E8F0; border-radius:9px; outline:0; padding:4px; }
        QTreeWidget#assetTree::item { min-height:34px; padding:3px 5px; border-radius:6px; }
        QTreeWidget#assetTree::item:hover { background:#EEF6F5; }
        QTreeWidget#assetTree::item:selected { background:#DFF7F3; color:#0F172A; }
        QTreeWidget#assetTree QHeaderView::section { background:#F1F5F9; color:#64748B; border:none; border-bottom:1px solid #E2E8F0; padding:7px; font-size:9px; font-weight:800; }
        QLineEdit { background:#FFFFFF; color:#0F172A; border:1px solid #CBD5E1; border-radius:8px; min-height:38px; padding:0 10px; }
        QLineEdit:focus { border-color:#0F766E; }
        QLineEdit#assetSearch { background:#F8FAFC; }
        QTableWidget { background:#FFFFFF; alternate-background-color:#F8FAFC; color:#334155; border:1px solid #E2E8F0; border-radius:8px; gridline-color:#EEF2F7; selection-background-color:#E6FFFA; selection-color:#0F172A; }
        QTableWidget::item { padding:5px 7px; }
        QHeaderView::section { background:#F1F5F9; color:#475569; border:none; border-bottom:1px solid #DCE5EC; padding:9px 8px; font-size:9px; font-weight:800; }
        QPushButton#primary { background:#0F766E; color:white; border:none; border-radius:8px; min-height:38px; padding:0 16px; font-weight:700; }
        QPushButton#primary:hover { background:#115E59; }
        QPushButton#primary:disabled { background:#CBD5E1; color:#64748B; }
        QPushButton#secondary { background:#FFFFFF; color:#334155; border:1px solid #CBD5E1; border-radius:8px; min-height:36px; padding:0 14px; font-weight:700; }
        QPushButton#secondary:hover { border-color:#0F766E; }
        QPushButton#danger { background:#FFFFFF; color:#B91C1C; border:1px solid #FECACA; border-radius:8px; min-height:36px; padding:0 14px; font-weight:700; }
        QPushButton#danger:hover { background:#FEF2F2; }
        QSplitter::handle { background:#E7EDF2; width:4px; }
        """

