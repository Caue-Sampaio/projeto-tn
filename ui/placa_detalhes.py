from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QUrl
from PyQt6.QtGui import QColor, QBrush, QPen, QPixmap, QFont, QPainter, QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsPathItem, QGraphicsTextItem,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QFileDialog, QInputDialog, QMenu, QColorDialog, QSlider,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from db.models import (
    BoardModel,
    BoardUnit,
    BoardImage,
    BoardDocument,
    OscilloscopeReference,
    TestPoint,
)

from utils.image_paths import import_image_to_project, resolve_image_path

from ui.marker_graphics import build_marker_path, normalize_marker_shape, normalize_marker_size, MarkerAppearanceDialog

from ui.technical_documents import AddDocumentDialog, _copy_document, _resolve_file



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fmt_date(value) -> str:
    if not value:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    return str(value)


def _fmt_voltage(value) -> str:
    if value is None:
        return "—"
    value = float(value)
    if abs(value) < 1:
        return f"{value * 1000:.2f} mV"
    return f"{value:.3g} V"


def _fmt_frequency(value) -> str:
    if value is None:
        return "—"
    value = float(value)
    if abs(value) >= 1e6:
        return f"{value / 1e6:.3g} MHz"
    if abs(value) >= 1e3:
        return f"{value / 1e3:.3g} kHz"
    return f"{value:.3g} Hz"


def _float_or_none(text: str):
    raw = (text or "").strip().replace(",", ".")
    if not raw:
        return None
    return float(raw)


class BoardEditDialog(QDialog):
    """Edição cadastral da placa com visual profissional e compacto."""

    def __init__(self, board: BoardUnit, parent=None):
        super().__init__(parent)
        self.board = board
        self.setWindowTitle("Editar Placa")
        self.setModal(True)
        self.resize(760, 560)
        self.setMinimumSize(700, 520)
        self._build_ui()
        self._apply_style()
        self.name.setFocus()

    def _field_label(self, text):
        lbl = QLabel(text); lbl.setObjectName("boardEditFieldLabel"); return lbl

    def _input(self, value="", placeholder=""):
        edit = QLineEdit(value or ""); edit.setObjectName("boardEditInput"); edit.setPlaceholderText(placeholder); edit.setMinimumHeight(42); return edit

    def _card(self, title, subtitle=""):
        frame = QFrame(); frame.setObjectName("boardEditCard")
        lay = QVBoxLayout(frame); lay.setContentsMargins(18, 16, 18, 16); lay.setSpacing(11)
        t = QLabel(title); t.setObjectName("boardEditSectionTitle"); lay.addWidget(t)
        if subtitle:
            s = QLabel(subtitle); s.setObjectName("boardEditSectionSub"); s.setWordWrap(True); lay.addWidget(s)
        return frame, lay

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        header = QFrame(); header.setObjectName("boardEditHeader")
        hl = QHBoxLayout(header); hl.setContentsMargins(24, 18, 24, 18); hl.setSpacing(14)
        title_box = QVBoxLayout(); title_box.setSpacing(3)
        title = QLabel("Editar placa"); title.setObjectName("boardEditTitle")
        subtitle = QLabel("Atualize os dados cadastrais da placa sem alterar seus pontos de teste, referências ou histórico.")
        subtitle.setObjectName("boardEditSubtitle"); subtitle.setWordWrap(True)
        title_box.addWidget(title); title_box.addWidget(subtitle); hl.addLayout(title_box, 1)
        chip = QLabel("EDIÇÃO"); chip.setObjectName("boardEditChip"); hl.addWidget(chip, 0, Qt.AlignmentFlag.AlignTop)
        root.addWidget(header)

        body = QWidget(); body.setObjectName("boardEditBody")
        bl = QVBoxLayout(body); bl.setContentsMargins(20, 18, 20, 18); bl.setSpacing(14)

        info_card, info_l = self._card("Identificação da placa", "Mantenha os dados usados para localizar a placa no sistema atualizados.")
        self.name = self._input(self.board.name, "Ex.: Placa de controle principal")
        self.model = self._input(self.board.model, "Ex.: PCB-X1")
        self.version = self._input(self.board.version, "Ex.: RevA, 1.0")
        self.serial = self._input(self.board.serial_number, "Ex.: SN001")

        info_l.addWidget(self._field_label("NOME DA PLACA *")); info_l.addWidget(self.name)
        row = QHBoxLayout(); row.setSpacing(12)
        col1 = QVBoxLayout(); col1.setSpacing(6); col1.addWidget(self._field_label("MODELO *")); col1.addWidget(self.model)
        col2 = QVBoxLayout(); col2.setSpacing(6); col2.addWidget(self._field_label("VERSÃO *")); col2.addWidget(self.version)
        row.addLayout(col1, 2); row.addLayout(col2, 1); info_l.addLayout(row)
        info_l.addWidget(self._field_label("NÚMERO DE SÉRIE *")); info_l.addWidget(self.serial)
        bl.addWidget(info_card)

        status_card, status_l = self._card("Status da placa", "Use este controle para indicar se a placa continua ativa no inventário.")
        status_row = QHBoxLayout(); status_row.setSpacing(10)
        self.active = QCheckBox("Placa ativa")
        self.active.setObjectName("boardEditCheck")
        self.active.setChecked(bool(self.board.is_active))
        status_text = QLabel("Desmarque somente quando a placa estiver fora de uso, arquivada ou desativada.")
        status_text.setObjectName("boardEditHint"); status_text.setWordWrap(True)
        status_row.addWidget(self.active); status_row.addWidget(status_text, 1)
        status_l.addLayout(status_row)
        bl.addWidget(status_card)
        bl.addStretch(1)
        root.addWidget(body, 1)

        footer = QFrame(); footer.setObjectName("boardEditFooter")
        fl = QHBoxLayout(footer); fl.setContentsMargins(20, 12, 20, 12); fl.setSpacing(10)
        hint = QLabel("* Campos obrigatórios"); hint.setObjectName("boardEditFooterHint")
        cancel = QPushButton("Cancelar"); cancel.setObjectName("boardEditSecondary"); cancel.setMinimumHeight(40); cancel.clicked.connect(self.reject)
        save = QPushButton("Salvar alterações"); save.setObjectName("boardEditPrimary"); save.setMinimumHeight(40); save.setMinimumWidth(165); save.setDefault(True); save.clicked.connect(self.accept)
        fl.addWidget(hint); fl.addStretch(1); fl.addWidget(cancel); fl.addWidget(save)
        root.addWidget(footer)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background:#F4F7FA; color:#0F172A; font-family:"Segoe UI", "Inter", Arial, sans-serif; }
            QFrame#boardEditHeader { background:#0B1220; border-bottom:1px solid #1E293B; }
            QLabel#boardEditTitle { color:#FFFFFF; font-size:20px; font-weight:800; }
            QLabel#boardEditSubtitle { color:#94A3B8; font-size:11px; }
            QLabel#boardEditChip { color:#67E8F9; background:#0B2533; border:1px solid #155E75; border-radius:11px; padding:6px 10px; font-size:9px; font-weight:800; }
            QWidget#boardEditBody { background:#F4F7FA; }
            QFrame#boardEditCard { background:#FFFFFF; border:1px solid #DCE3EA; border-radius:11px; }
            QLabel#boardEditSectionTitle { color:#0F172A; font-size:13px; font-weight:800; }
            QLabel#boardEditSectionSub { color:#64748B; font-size:10px; }
            QLabel#boardEditFieldLabel { color:#475569; font-size:9px; font-weight:800; letter-spacing:.5px; }
            QLabel#boardEditHint { color:#64748B; font-size:10px; }
            QLineEdit#boardEditInput { background:#F8FAFC; color:#0F172A; border:1px solid #CBD5E1; border-radius:8px; padding:9px 11px; font-size:12px; selection-background-color:#0F766E; selection-color:#FFFFFF; }
            QLineEdit#boardEditInput:focus { background:#FFFFFF; border:1px solid #0F766E; }
            QCheckBox#boardEditCheck { color:#0F172A; font-size:11px; font-weight:700; spacing:8px; }
            QCheckBox#boardEditCheck::indicator { width:18px; height:18px; border:1px solid #CBD5E1; border-radius:5px; background:#FFFFFF; }
            QCheckBox#boardEditCheck::indicator:checked { background:#0F766E; border-color:#0F766E; }
            QFrame#boardEditFooter { background:#FFFFFF; border-top:1px solid #E2E8F0; }
            QLabel#boardEditFooterHint { color:#94A3B8; font-size:9px; }
            QPushButton#boardEditPrimary { background:#0F766E; color:#FFFFFF; border:none; border-radius:8px; padding:9px 18px; font-size:12px; font-weight:800; }
            QPushButton#boardEditPrimary:hover { background:#0D9488; }
            QPushButton#boardEditSecondary { background:#FFFFFF; color:#334155; border:1px solid #CBD5E1; border-radius:8px; padding:8px 14px; font-size:10px; font-weight:700; }
            QPushButton#boardEditSecondary:hover { background:#F1F5F9; border-color:#94A3B8; }
        """)


class NewTestPointDialog(QDialog):
    """Cadastro rápido de ponto de teste dentro de PlacaDetalhes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Novo ponto de teste")
        self.setModal(True)
        self.setMinimumWidth(480)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)
        root.addWidget(QLabel("Cadastre o ponto sem sair dos detalhes da placa."))

        form = QFormLayout()
        form.setVerticalSpacing(9)
        self.refdes = QLineEdit()
        self.refdes.setPlaceholderText("Ex.: TP1, VCC, CLOCK")
        self.x = QSpinBox(); self.x.setRange(0, 99999)
        self.y = QSpinBox(); self.y.setRange(0, 99999)
        self.expected_v = QLineEdit(); self.expected_v.setPlaceholderText("Opcional")
        self.expected_a = QLineEdit(); self.expected_a.setPlaceholderText("Opcional")
        self.expected_hz = QLineEdit(); self.expected_hz.setPlaceholderText("Opcional")
        self.notes = QTextEdit(); self.notes.setMinimumHeight(75)

        form.addRow("Ponto / RefDes *", self.refdes)
        form.addRow("Posição X", self.x)
        form.addRow("Posição Y", self.y)
        form.addRow("Tensão esperada (V)", self.expected_v)
        form.addRow("Corrente esperada (A)", self.expected_a)
        form.addRow("Frequência esperada (Hz)", self.expected_hz)
        form.addRow("Observações", self.notes)
        root.addLayout(form)

        hint = QLabel(
            "A posição pode ser refinada depois no mapeamento visual. "
            "Todo ponto novo nasce vermelho (#E53935)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#64748B;font-size:11px;")
        root.addWidget(hint)

        actions = QHBoxLayout(); actions.addStretch()
        cancel = QPushButton("Cancelar")
        save = QPushButton("Criar ponto"); save.setObjectName("primary")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._validate)
        actions.addWidget(cancel); actions.addWidget(save)
        root.addLayout(actions)
        self._style()

    def _style(self):
        self.setStyleSheet(
            """
            QDialog { background:#FFFFFF; color:#0F172A; }
            QLineEdit, QTextEdit, QSpinBox { min-height:32px; border:1px solid #CBD5E1;
                border-radius:7px; padding:4px 8px; background:#FFFFFF; color:#0F172A; }
            QPushButton { min-height:36px; padding:0 15px; border-radius:7px;
                border:1px solid #CBD5E1; background:#FFFFFF; color:#334155; font-weight:600; }
            QPushButton#primary { background:#0F766E; color:white; border-color:#0F766E; }
            """
        )

    def _validate(self):
        if not self.refdes.text().strip():
            QMessageBox.warning(self, "Ponto", "Informe o nome/RefDes do ponto.")
            return
        try:
            _float_or_none(self.expected_v.text())
            _float_or_none(self.expected_a.text())
            _float_or_none(self.expected_hz.text())
        except ValueError:
            QMessageBox.warning(self, "Ponto", "Revise os valores numéricos informados.")
            return
        self.accept()


class PointDetailsDialog(QDialog):
    """Popup atualizado para visualizar/editar um ponto na aba Detalhes da Placa."""

    def __init__(self, point: TestPoint, reference: OscilloscopeReference | None, parent=None):
        super().__init__(parent)
        self.point = point
        self.reference = reference
        self.setWindowTitle(f"Ponto {point.refdes}")
        self.setModal(True)
        self.resize(700, 700)
        self.setMinimumSize(640, 600)
        self._build_ui()
        self._load()
        self._style()

    def _field(self, placeholder=""):
        w = QLineEdit(); w.setPlaceholderText(placeholder); w.setMinimumHeight(34); w.setObjectName("editField")
        return w

    def _read(self):
        w = QLabel("—"); w.setObjectName("readValue"); w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return w

    def _section(self, title):
        card = QFrame(); card.setObjectName("pointCard")
        lay = QVBoxLayout(card); lay.setContentsMargins(16, 14, 16, 14); lay.setSpacing(10)
        ttl = QLabel(title); ttl.setObjectName("sectionTitle"); lay.addWidget(ttl)
        return card, lay

    def _build_ui(self):
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        header = QFrame(); header.setObjectName("pointHeader")
        hl = QHBoxLayout(header); hl.setContentsMargins(20, 15, 20, 15)
        box = QVBoxLayout(); box.setSpacing(2)
        self.title = QLabel(self.point.refdes); self.title.setObjectName("pointTitle")
        sub = QLabel("Dados do ponto, referência correta e última captura"); sub.setObjectName("pointSub")
        box.addWidget(self.title); box.addWidget(sub); hl.addLayout(box); hl.addStretch()
        self.slot_chip = QLabel(); self.slot_chip.setObjectName("slotChip"); hl.addWidget(self.slot_chip)
        root.addWidget(header)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(); bl = QVBoxLayout(body); bl.setContentsMargins(16, 14, 16, 14); bl.setSpacing(12)

        card, lay = self._section("IDENTIFICAÇÃO")
        g = QGridLayout(); g.setHorizontalSpacing(18); g.setVerticalSpacing(8)
        self.refdes = self._read(); self.coords = self._read(); self.image = self._read(); self.marker = self._read()
        for r, c, label, widget in [
            (0,0,"RefDes",self.refdes),(0,2,"Coordenadas",self.coords),
            (1,0,"Imagem",self.image),(1,2,"Marcador",self.marker),
        ]:
            lab=QLabel(label); lab.setObjectName("fieldLabel"); g.addWidget(lab,r,c); g.addWidget(widget,r,c+1)
        lay.addLayout(g); bl.addWidget(card)

        card, lay = self._section("VALORES CADASTRADOS")
        form = QFormLayout(); form.setHorizontalSpacing(18); form.setVerticalSpacing(9)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.exp_v=self._field("Ex.: 3.3"); self.exp_a=self._field("Ex.: 0.250"); self.exp_hz=self._field("Ex.: 1000")
        self.exp_wave=self._field("PWM, senoidal, quadrada...")
        self.tol_v=self._field("± V"); self.tol_a=self._field("± A"); self.tol_hz=self._field("± Hz")
        form.addRow("Tensão esperada (V)", self.exp_v); form.addRow("Corrente esperada (A)", self.exp_a)
        form.addRow("Frequência esperada (Hz)", self.exp_hz); form.addRow("Forma de onda", self.exp_wave)
        form.addRow("Tolerância de tensão", self.tol_v); form.addRow("Tolerância de corrente", self.tol_a)
        form.addRow("Tolerância de frequência", self.tol_hz)
        lay.addLayout(form); bl.addWidget(card)

        card, lay = self._section("REFERÊNCIA CORRETA")
        rg = QGridLayout(); rg.setHorizontalSpacing(18); rg.setVerticalSpacing(8)
        self.ref_ch=self._read(); self.ref_vpp=self._read(); self.ref_vrms=self._read(); self.ref_freq=self._read(); self.ref_duty=self._read(); self.ref_date=self._read()
        ref_items=[("Canal",self.ref_ch),("Vpp",self.ref_vpp),("Vrms",self.ref_vrms),("Frequência",self.ref_freq),("Duty",self.ref_duty),("Atualizada",self.ref_date)]
        for i,(label,w) in enumerate(ref_items):
            r,c=divmod(i,2); lab=QLabel(label); lab.setObjectName("fieldLabel"); rg.addWidget(lab,r,c*2); rg.addWidget(w,r,c*2+1)
        lay.addLayout(rg); bl.addWidget(card)

        card, lay = self._section("ÚLTIMA MEDIÇÃO DO OSCILOSCÓPIO")
        mg = QGridLayout(); mg.setHorizontalSpacing(18); mg.setVerticalSpacing(8)
        self.m_ch=self._read(); self.m_vpp=self._read(); self.m_vrms=self._read(); self.m_freq=self._read(); self.m_duty=self._read(); self.m_date=self._read()
        meas=[("Canal",self.m_ch),("Vpp",self.m_vpp),("Vrms",self.m_vrms),("Frequência",self.m_freq),("Duty",self.m_duty),("Capturada",self.m_date)]
        for i,(label,w) in enumerate(meas):
            r,c=divmod(i,2); lab=QLabel(label); lab.setObjectName("fieldLabel"); mg.addWidget(lab,r,c*2); mg.addWidget(w,r,c*2+1)
        lay.addLayout(mg); bl.addWidget(card)

        card, lay = self._section("OBSERVAÇÕES")
        self.notes = QTextEdit(); self.notes.setObjectName("notes"); self.notes.setMinimumHeight(90)
        self.notes.setPlaceholderText("Observações técnicas deste ponto...")
        lay.addWidget(self.notes); bl.addWidget(card); bl.addStretch()

        scroll.setWidget(body); root.addWidget(scroll,1)

        footer = QFrame(); footer.setObjectName("pointFooter")
        fl = QHBoxLayout(footer); fl.setContentsMargins(16, 10, 16, 10)
        appearance = QPushButton("Aparência do marcador"); appearance.setObjectName("secondary")
        appearance.clicked.connect(self._edit_appearance)
        cancel = QPushButton("Cancelar"); cancel.setObjectName("secondary"); cancel.clicked.connect(self.reject)
        save = QPushButton("Salvar alterações"); save.setObjectName("primary"); save.clicked.connect(self._validate_and_accept)
        fl.addWidget(appearance); fl.addStretch(); fl.addWidget(cancel); fl.addWidget(save)
        root.addWidget(footer)

    def _load(self):
        p=self.point
        slot=int(getattr(p,"image_slot",1) or 1); color=getattr(p,"marker_color",None) or "#E53935"
        shape=normalize_marker_shape(getattr(p,"marker_shape","circle")); size=normalize_marker_size(getattr(p,"marker_size",16))
        self.title.setStyleSheet(f"color:{color};"); self.slot_chip.setText(f"IMAGEM {slot}")
        self.refdes.setText(p.refdes or "—"); self.coords.setText(f"({p.x}, {p.y})"); self.image.setText(f"Imagem {slot}")
        self.marker.setText(f"{shape} • {size}px • {color}")
        self.exp_v.setText("" if p.expected_voltage_v is None else str(p.expected_voltage_v))
        self.exp_a.setText("" if p.expected_current_a is None else str(p.expected_current_a))
        self.exp_hz.setText("" if p.expected_frequency_hz is None else str(p.expected_frequency_hz))
        self.exp_wave.setText(p.expected_waveform or "")
        self.tol_v.setText("" if p.tolerance_voltage_v is None else str(p.tolerance_voltage_v))
        self.tol_a.setText("" if p.tolerance_current_a is None else str(p.tolerance_current_a))
        self.tol_hz.setText("" if p.tolerance_frequency_hz is None else str(p.tolerance_frequency_hz))
        self.notes.setPlainText(p.notes or "")

        r=self.reference
        if r:
            self.ref_ch.setText(f"CH{r.channel}"); self.ref_vpp.setText(_fmt_voltage(r.vpp_v)); self.ref_vrms.setText(_fmt_voltage(r.vrms_v))
            self.ref_freq.setText(_fmt_frequency(r.frequency_hz)); self.ref_duty.setText("—" if r.duty_cycle_pct is None else f"{r.duty_cycle_pct:.3g} %")
            self.ref_date.setText(_fmt_date(r.updated_at))
        else:
            for w in (self.ref_ch,self.ref_vpp,self.ref_vrms,self.ref_freq,self.ref_duty,self.ref_date): w.setText("Sem referência")

        self.m_ch.setText(f"CH{p.last_scope_channel}" if p.last_scope_channel else "—")
        self.m_vpp.setText(_fmt_voltage(p.last_scope_vpp_v)); self.m_vrms.setText(_fmt_voltage(p.last_scope_vrms_v)); self.m_freq.setText(_fmt_frequency(p.last_scope_frequency_hz))
        self.m_duty.setText("—" if p.last_scope_duty_pct is None else f"{p.last_scope_duty_pct:.3g} %"); self.m_date.setText(_fmt_date(p.last_scope_at))

    def _edit_appearance(self):
        dlg=MarkerAppearanceDialog(self.point,self)
        if dlg.exec()!=QDialog.DialogCode.Accepted: return
        shape,size=dlg.values(); self.point.marker_shape=shape; self.point.marker_size=size
        color=getattr(self.point,"marker_color",None) or "#E53935"; self.marker.setText(f"{shape} • {size}px • {color}")

    def _validate_and_accept(self):
        try: self.values()
        except ValueError:
            QMessageBox.warning(self,"Valor inválido","Revise os campos numéricos antes de salvar."); return
        self.accept()

    def values(self):
        return {
            "expected_voltage_v":_float_or_none(self.exp_v.text()), "expected_current_a":_float_or_none(self.exp_a.text()),
            "expected_frequency_hz":_float_or_none(self.exp_hz.text()), "expected_waveform":self.exp_wave.text().strip() or None,
            "tolerance_voltage_v":_float_or_none(self.tol_v.text()), "tolerance_current_a":_float_or_none(self.tol_a.text()),
            "tolerance_frequency_hz":_float_or_none(self.tol_hz.text()), "marker_shape":normalize_marker_shape(getattr(self.point,"marker_shape","circle")),
            "marker_size":normalize_marker_size(getattr(self.point,"marker_size",16)), "notes":self.notes.toPlainText().strip() or None,
        }

    def _style(self):
        self.setStyleSheet("""
        QDialog{background:#F6F8FB;color:#0F172A;font-family:'Segoe UI';}
        QFrame#pointHeader{background:#0F172A;border:none;} QLabel#pointTitle{font-size:20px;font-weight:800;}
        QLabel#pointSub{color:#94A3B8;font-size:10px;} QLabel#slotChip{color:#67E8F9;background:#0B2533;border:1px solid #155E75;border-radius:10px;padding:5px 9px;font-weight:800;}
        QFrame#pointCard{background:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;} QLabel#sectionTitle{color:#334155;font-size:10px;font-weight:800;}
        QLabel#fieldLabel{color:#64748B;font-size:10px;font-weight:600;} QLabel#readValue{color:#0F172A;font-size:11px;font-weight:700;}
        QLineEdit#editField,QTextEdit#notes{background:#F8FAFC;color:#0F172A;border:1px solid #CBD5E1;border-radius:7px;padding:7px 9px;}
        QLineEdit#editField:focus,QTextEdit#notes:focus{background:#FFFFFF;border:1px solid #0F766E;}
        QFrame#pointFooter{background:#FFFFFF;border-top:1px solid #E2E8F0;} QPushButton#primary{background:#0F766E;color:white;border:none;border-radius:7px;min-height:34px;padding:0 16px;font-weight:700;}
        QPushButton#primary:hover{background:#115E59;} QPushButton#secondary{background:#FFFFFF;color:#334155;border:1px solid #CBD5E1;border-radius:7px;min-height:34px;padding:0 14px;font-weight:600;}
        QPushButton#secondary:hover{background:#F1F5F9;} QScrollArea{border:none;background:#F6F8FB;} QScrollArea>QWidget>QWidget{background:#F6F8FB;}
        """)


class NewReferenceDialog(QDialog):
    """Cadastro manual rápido de referência para um ponto existente."""

    def __init__(self, points: list[TestPoint], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Novo ponto de referência")
        self.setModal(True)
        self.setMinimumWidth(500)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)

        info = QLabel(
            "Associe uma referência a um ponto já mapeado. Para capturar a forma "
            "de onda real com o Rigol, use depois “Configurar Preferências de Teste”."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#475569;")
        root.addWidget(info)

        form = QFormLayout(); form.setVerticalSpacing(9)
        self.point = QComboBox()
        for p in points:
            self.point.addItem(p.refdes, p.id)
        self.channel = QComboBox(); self.channel.addItems(["CH1", "CH2", "CH3", "CH4"])
        self.vpp = QLineEdit(); self.vpp.setPlaceholderText("Opcional")
        self.vrms = QLineEdit(); self.vrms.setPlaceholderText("Opcional")
        self.frequency = QLineEdit(); self.frequency.setPlaceholderText("Opcional")
        self.tol_vpp = QLineEdit("10")
        self.tol_vrms = QLineEdit("10")
        self.tol_freq = QLineEdit("5")
        self.notes = QTextEdit(); self.notes.setMinimumHeight(70)

        form.addRow("Ponto *", self.point)
        form.addRow("Canal", self.channel)
        form.addRow("Vpp correto (V)", self.vpp)
        form.addRow("Vrms correto (V)", self.vrms)
        form.addRow("Frequência correta (Hz)", self.frequency)
        form.addRow("Tolerância Vpp (%)", self.tol_vpp)
        form.addRow("Tolerância Vrms (%)", self.tol_vrms)
        form.addRow("Tolerância frequência (%)", self.tol_freq)
        form.addRow("Observações", self.notes)
        root.addLayout(form)

        actions = QHBoxLayout(); actions.addStretch()
        cancel = QPushButton("Cancelar")
        save = QPushButton("Salvar referência"); save.setObjectName("primary")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._validate)
        actions.addWidget(cancel); actions.addWidget(save)
        root.addLayout(actions)
        self.setStyleSheet(
            """
            QDialog { background:#FFFFFF; color:#0F172A; }
            QLineEdit, QTextEdit, QComboBox { min-height:32px; border:1px solid #CBD5E1;
                border-radius:7px; padding:4px 8px; background:#FFFFFF; color:#0F172A; }
            QPushButton { min-height:36px; padding:0 15px; border-radius:7px;
                border:1px solid #CBD5E1; background:#FFFFFF; color:#334155; font-weight:600; }
            QPushButton#primary { background:#0F766E; color:white; border-color:#0F766E; }
            """
        )

    def _validate(self):
        try:
            for edit in (self.vpp, self.vrms, self.frequency, self.tol_vpp, self.tol_vrms, self.tol_freq):
                _float_or_none(edit.text())
        except ValueError:
            QMessageBox.warning(self, "Referência", "Revise os valores numéricos informados.")
            return
        self.accept()



class BoardDetailsGraphicsView(QGraphicsView):
    """Canvas da placa com pan, zoom e modo de criação de pontos."""

    point_place_requested = pyqtSignal(float, float)
    zoom_changed = pyqtSignal(int)

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._zoom_percent = 100
        self._placement_mode = False
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setMinimumHeight(420)

    def set_placement_mode(self, enabled: bool):
        self._placement_mode = bool(enabled)
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.setDragMode(QGraphicsView.DragMode.NoDrag if enabled else QGraphicsView.DragMode.ScrollHandDrag)

    def fit_scene(self):
        rect = self.scene().sceneRect()
        if rect.isNull():
            rect = self.scene().itemsBoundingRect()
        if rect.isNull():
            return
        self.resetTransform()
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom_percent = 100
        self.zoom_changed.emit(100)

    def set_zoom_percent(self, value: int):
        value = max(25, min(400, int(value)))
        if value == self._zoom_percent:
            return
        factor = value / float(self._zoom_percent)
        self.scale(factor, factor)
        self._zoom_percent = value
        self.zoom_changed.emit(value)

    def wheelEvent(self, event):
        """A roda normal rola a página; Ctrl + roda controla o zoom da PCB.

        Antes, qualquer tentativa de descer a aba com o cursor sobre a imagem
        alterava o zoom. O slider lateral continua disponível o tempo todo.
        """
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if not self.scene().items():
                event.accept()
                return
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            target = max(25, min(400, int(round(self._zoom_percent * factor))))
            self.set_zoom_percent(target)
            event.accept()
            return

        # Encaminha a rolagem para o QScrollArea externo da página.
        parent = self.parent()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                bar = parent.verticalScrollBar()
                bar.setValue(bar.value() - event.angleDelta().y())
                event.accept()
                return
            parent = parent.parent()
        event.ignore()

    def mousePressEvent(self, event):
        if self._placement_mode and event.button() == Qt.MouseButton.LeftButton:
            pos = self.mapToScene(event.position().toPoint())
            if self.scene().sceneRect().contains(pos):
                self.point_place_requested.emit(pos.x(), pos.y())
                event.accept()
                return
        super().mousePressEvent(event)


class BoardDetailsPointItem(QGraphicsPathItem):
    """Marcador interativo usado dentro de Detalhes da Placa."""

    def __init__(self, point: TestPoint, owner: "PlacaDetalhes"):
        super().__init__()
        self.point = point
        self.owner = owner
        self.setPos(point.x, point.y)
        self.setZValue(20)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.label = QGraphicsTextItem(point.refdes, self)
        self.label.setDefaultTextColor(QColor('#FFFFFF'))
        self.label.setFont(QFont('Segoe UI', 8, QFont.Weight.Bold))
        self.update_appearance()
        self.update_color(getattr(point, 'marker_color', None) or '#E53935')
        self._update_tooltip()

    def update_appearance(self):
        shape = normalize_marker_shape(getattr(self.point, 'marker_shape', None))
        size = normalize_marker_size(getattr(self.point, 'marker_size', None))
        self.setPath(build_marker_path(shape, size))
        self.label.setPos(size / 2 + 3, -size / 2 - 8)
        self._update_tooltip()

    def update_color(self, color_hex: str):
        color = QColor(color_hex)
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor('#FFFFFF'), 1.3))
        self._color_hex = color_hex

    def set_selected(self, selected: bool):
        self.setPen(QPen(QColor('#22D3EE') if selected else QColor('#FFFFFF'), 2.5 if selected else 1.3))

    def _update_tooltip(self):
        slot = int(getattr(self.point, 'image_slot', 1) or 1)
        self.setToolTip(
            f"{self.point.refdes}\nImagem {slot} • ({self.point.x}, {self.point.y})\n"
            f"Marcador: {normalize_marker_shape(getattr(self.point, 'marker_shape', None))} • "
            f"{normalize_marker_size(getattr(self.point, 'marker_size', None))} px\n"
            "Arraste para mover • botão direito para opções"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.owner.select_point(self.point)
            self.owner.show_point_menu(self.point, event.screenPos())
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.owner.select_point(self.point)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if event.button() == Qt.MouseButton.LeftButton:
            p = self.pos()
            x, y = int(round(p.x())), int(round(p.y()))
            if x != self.point.x or y != self.point.y:
                self.owner.point_moved(self.point, x, y)
            self._update_tooltip()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.owner.select_point(self.point)
            self.owner.edit_point(self.point)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class PlacaDetalhes(QWidget):
    """Página dinâmica reutilizável: equivalente a /placas/:id/detalhes.

    O mesmo widget atende qualquer placa. ``load_board(board_id)`` muda o contexto
    sem duplicar telas nem lógica.
    """

    back_requested = pyqtSignal()
    test_requested = pyqtSignal(int)
    preferences_requested = pyqtSignal(int)
    board_updated = pyqtSignal(int)

    def __init__(self, session, current_user=None, parent=None):
        super().__init__(parent)
        self.session = session
        self.current_user = current_user
        self.board_id: int | None = None
        self.board: BoardUnit | None = None
        self.active_image_slot = 1
        self.current_point: TestPoint | None = None
        self.point_items: dict[int, BoardDetailsPointItem] = {}
        self._placing_point = False
        self._build_ui()
        self._apply_style()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.setObjectName("boardDetailsRoot")
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(14)

        # breadcrumb / navegação
        breadcrumb_bar = QFrame(); breadcrumb_bar.setObjectName("breadcrumbBar")
        breadcrumb = QHBoxLayout(breadcrumb_bar); breadcrumb.setContentsMargins(4, 0, 4, 0); breadcrumb.setSpacing(8)
        back = QPushButton("← Placas")
        back.setObjectName("breadcrumbBtn")
        back.clicked.connect(self.back_requested.emit)
        self.route_label = QLabel("/placas/—/detalhes")
        self.route_label.setObjectName("routeLabel")
        breadcrumb.addWidget(back)
        breadcrumb.addWidget(self.route_label)
        breadcrumb.addStretch()
        root.addWidget(breadcrumb_bar)

        # Cabeçalho técnico da placa
        header = QFrame(); header.setObjectName("detailsHeader")
        h = QHBoxLayout(header); h.setContentsMargins(22, 18, 22, 18); h.setSpacing(14)
        title_box = QVBoxLayout(); title_box.setSpacing(3)
        eyebrow = QLabel("DOSSIÊ TÉCNICO DA PLACA"); eyebrow.setObjectName("detailsEyebrow")
        self.title_label = QLabel("Detalhes da placa"); self.title_label.setObjectName("detailsTitle")
        self.meta_label = QLabel("ID — • código —"); self.meta_label.setObjectName("detailsMeta")
        title_box.addWidget(eyebrow); title_box.addWidget(self.title_label); title_box.addWidget(self.meta_label)
        h.addLayout(title_box, 1)
        self.status_chip = QLabel("—"); self.status_chip.setObjectName("statusChip")
        self.status_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_chip.setMinimumWidth(88)
        h.addWidget(self.status_chip)
        edit = QPushButton("Editar informações"); edit.setObjectName("headerEditBtn")
        edit.clicked.connect(self.edit_board)
        h.addWidget(edit)
        root.addWidget(header)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget(); body.setObjectName("detailsBody")
        body_layout = QVBoxLayout(body); body_layout.setContentsMargins(0, 0, 0, 0); body_layout.setSpacing(12)

        # Informações
        info_card = self._card("Informações da placa", "Dados cadastrais e identificação")
        self.info_grid = QGridLayout(); self.info_grid.setHorizontalSpacing(24); self.info_grid.setVerticalSpacing(10)
        info_card.layout().addLayout(self.info_grid)
        body_layout.addWidget(info_card)

        # Documentos técnicos da própria placa
        docs_card = self._card(
            "Documentos técnicos",
            "Manuais, datasheets, diagramas, procedimentos e outros arquivos vinculados diretamente a esta placa.",
        )
        docs_top = QHBoxLayout(); docs_top.setSpacing(8)
        self.documents_count = QLabel("0 documentos")
        self.documents_count.setObjectName("documentCountChip")
        docs_top.addWidget(self.documents_count)
        docs_top.addStretch(1)
        add_doc = QPushButton("+ Adicionar documento")
        add_doc.setObjectName("primaryBtn")
        add_doc.clicked.connect(self.add_board_document)
        docs_top.addWidget(add_doc)
        docs_card.layout().addLayout(docs_top)

        self.documents_table = QTableWidget(0, 4)
        self.documents_table.setHorizontalHeaderLabels(["Documento", "Arquivo", "Adicionado em", "Observações"])
        self._setup_table(self.documents_table)
        self.documents_table.setMinimumHeight(190)
        self.documents_table.setMaximumHeight(260)
        self.documents_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.documents_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.documents_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.documents_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.documents_table.cellDoubleClicked.connect(lambda *_: self.open_board_document())
        docs_card.layout().addWidget(self.documents_table)

        docs_actions = QHBoxLayout(); docs_actions.setSpacing(8)
        docs_hint = QLabel("Duplo clique abre o arquivo selecionado.")
        docs_hint.setObjectName("cardSub")
        docs_actions.addWidget(docs_hint)
        docs_actions.addStretch(1)
        open_doc = QPushButton("Abrir arquivo")
        open_doc.setObjectName("secondaryBtn")
        open_doc.clicked.connect(self.open_board_document)
        remove_doc = QPushButton("Remover documento")
        remove_doc.setObjectName("dangerBtn")
        remove_doc.clicked.connect(self.remove_board_document)
        docs_actions.addWidget(open_doc); docs_actions.addWidget(remove_doc)
        docs_card.layout().addLayout(docs_actions)
        body_layout.addWidget(docs_card)

        # Acesso contextual às telas ocultas da sidebar
        actions_card = QFrame(); actions_card.setObjectName("workflowCard")
        ac = QHBoxLayout(actions_card); ac.setContentsMargins(16, 14, 16, 14); ac.setSpacing(10)
        action_text = QVBoxLayout(); action_text.setSpacing(2)
        at = QLabel("AÇÕES DA PLACA"); at.setObjectName("workflowLabel")
        ast = QLabel("Acesse o diagnóstico ou cadastre as referências mantendo esta placa no contexto."); ast.setObjectName("workflowSub")
        action_text.addWidget(at); action_text.addWidget(ast); ac.addLayout(action_text, 1)
        self.test_btn = QPushButton("Ir para Teste desta Placa"); self.test_btn.setObjectName("primaryBtn")
        self.pref_btn = QPushButton("Configurar Preferências de Teste"); self.pref_btn.setObjectName("secondaryBtn")
        self.test_btn.clicked.connect(self._emit_test)
        self.pref_btn.clicked.connect(self._emit_preferences)
        ac.addWidget(self.pref_btn); ac.addWidget(self.test_btn)
        body_layout.addWidget(actions_card)

        # Mapeamento visual / Pontos de teste
        map_card = self._card(
            "Mapeamento da Placa",
            "Cadastre e organize visualmente os pontos da placa. Ctrl + roda aplica zoom; roda normal desce a página.",
        )

        map_body = QHBoxLayout()
        map_body.setContentsMargins(0, 4, 0, 0)
        map_body.setSpacing(12)

        # REFERÊNCIAS À ESQUERDA: ficam sempre visíveis junto com a imagem.
        # Ao selecionar uma referência, o ponto correspondente é destacado no
        # canvas e, se necessário, a tela troca automaticamente para Imagem 1/2.
        refs_panel = QFrame()
        refs_panel.setObjectName("referenceSidePanel")
        refs_panel.setMinimumWidth(330)
        refs_panel.setMaximumWidth(420)
        refs_layout = QVBoxLayout(refs_panel)
        refs_layout.setContentsMargins(12, 12, 12, 12)
        refs_layout.setSpacing(8)

        refs_title = QLabel("PONTOS DE REFERÊNCIA")
        refs_title.setObjectName("mapControlsTitle")
        refs_layout.addWidget(refs_title)

        refs_sub = QLabel("Selecione uma linha para localizar o ponto na placa.")
        refs_sub.setObjectName("mapHint")
        refs_sub.setWordWrap(True)
        refs_layout.addWidget(refs_sub)

        self.references_table = QTableWidget(0, 5)
        self.references_table.setHorizontalHeaderLabels(["Ponto", "CH", "Vpp", "Vrms", "Freq."])
        self._setup_table(self.references_table)
        self.references_table.setMinimumHeight(330)
        self.references_table.itemSelectionChanged.connect(self._reference_table_selected)
        refs_layout.addWidget(self.references_table, 1)

        add_ref = QPushButton("+ Novo Ponto de Referência")
        add_ref.setObjectName("primaryBtn")
        add_ref.clicked.connect(self.new_reference)
        refs_layout.addWidget(add_ref)

        map_body.addWidget(refs_panel, 0)

        # Canvas ocupa o centro e permanece visível ao lado da tabela.
        self.board_scene = QGraphicsScene(self)
        self.board_view = BoardDetailsGraphicsView(self.board_scene, self)
        self.board_view.setMinimumHeight(460)
        self.board_view.setMinimumWidth(420)
        self.board_view.point_place_requested.connect(self._place_new_point)
        self.board_view.zoom_changed.connect(self._zoom_changed)
        map_body.addWidget(self.board_view, 1)

        # Coluna lateral de comandos: evita a toolbar comprida acima da imagem
        # e deixa a rolagem da página independente do mapeamento.
        controls = QFrame()
        controls.setObjectName("mapControls")
        controls.setMinimumWidth(220)
        controls.setMaximumWidth(255)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(12, 12, 12, 12)
        controls_layout.setSpacing(8)

        controls_title = QLabel("IMAGEM / PONTOS")
        controls_title.setObjectName("mapControlsTitle")
        controls_layout.addWidget(controls_title)

        slots_row = QHBoxLayout(); slots_row.setSpacing(6)
        self.slot1_btn = QPushButton("Imagem 1")
        self.slot2_btn = QPushButton("Imagem 2")
        for btn in (self.slot1_btn, self.slot2_btn):
            btn.setCheckable(True)
            btn.setObjectName("slotBtn")
            btn.setMinimumHeight(34)
        self.slot1_btn.setChecked(True)
        self.slot1_btn.clicked.connect(lambda: self.set_image_slot(1))
        self.slot2_btn.clicked.connect(lambda: self.set_image_slot(2))
        slots_row.addWidget(self.slot1_btn)
        slots_row.addWidget(self.slot2_btn)
        controls_layout.addLayout(slots_row)

        self.image_action_btn = QPushButton("Adicionar / Trocar imagem")
        self.image_action_btn.setObjectName("secondaryBtn")
        self.image_action_btn.clicked.connect(self.replace_active_image)
        controls_layout.addWidget(self.image_action_btn)

        self.remove_image_btn = QPushButton("Remover imagem")
        self.remove_image_btn.setObjectName("ghostBtn")
        self.remove_image_btn.clicked.connect(self.remove_active_image)
        controls_layout.addWidget(self.remove_image_btn)

        line = QFrame(); line.setObjectName("mapSeparator"); line.setFixedHeight(1)
        controls_layout.addWidget(line)

        self.add_visual_point_btn = QPushButton("+ Novo Ponto")
        self.add_visual_point_btn.setObjectName("primaryBtn")
        self.add_visual_point_btn.setCheckable(True)
        self.add_visual_point_btn.toggled.connect(self._toggle_point_placement)
        controls_layout.addWidget(self.add_visual_point_btn)

        self.point_options_btn = QPushButton("Opções do ponto")
        self.point_options_btn.setObjectName("secondaryBtn")
        self.point_options_btn.setEnabled(False)
        self.point_options_btn.clicked.connect(self._show_selected_point_menu)
        controls_layout.addWidget(self.point_options_btn)

        line2 = QFrame(); line2.setObjectName("mapSeparator"); line2.setFixedHeight(1)
        controls_layout.addWidget(line2)

        zoom_title = QLabel("ZOOM")
        zoom_title.setObjectName("mapControlsTitle")
        controls_layout.addWidget(zoom_title)
        zoom_row = QHBoxLayout(); zoom_row.setSpacing(6)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(25, 400)
        self.zoom_slider.setValue(100)
        self.zoom_slider.valueChanged.connect(lambda v: self.board_view.set_zoom_percent(v))
        zoom_row.addWidget(self.zoom_slider, 1)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setFixedWidth(42)
        zoom_row.addWidget(self.zoom_label)
        controls_layout.addLayout(zoom_row)

        fit_btn = QPushButton("Ajustar imagem (Fit)")
        fit_btn.setObjectName("ghostBtn")
        fit_btn.clicked.connect(self.fit_image)
        controls_layout.addWidget(fit_btn)

        zoom_hint = QLabel("Ctrl + roda: zoom\nRoda normal: rolar página")
        zoom_hint.setObjectName("mapHint")
        zoom_hint.setWordWrap(True)
        controls_layout.addWidget(zoom_hint)

        controls_layout.addStretch(1)
        self.mapping_status = QLabel("Selecione uma placa.")
        self.mapping_status.setObjectName("cardSub")
        self.mapping_status.setWordWrap(True)
        controls_layout.addWidget(self.mapping_status)

        map_body.addWidget(controls)
        map_card.layout().addLayout(map_body, 1)
        body_layout.addWidget(map_card)

        # A lista separada de "Pontos de Teste" foi removida da interface.
        # Os pontos continuam totalmente editáveis diretamente sobre a imagem
        # (criar, selecionar, mover, editar, cor, forma/tamanho e excluir).
        # Mantemos uma tabela interna invisível apenas por compatibilidade com
        # os métodos existentes de atualização/seleção, sem ocupar espaço visual.
        self.test_points_table = QTableWidget(0, 7, self)
        self.test_points_table.setHorizontalHeaderLabels(["Ponto", "Imagem", "X", "Y", "Tensão", "Frequência", "Cor"])
        self.test_points_table.hide()

        # A tabela de referências foi incorporada ao lado esquerdo do mapeamento,
        # para que seleção e destaque visual possam ser vistos simultaneamente.

        # Histórico de testes não é exibido nesta tela. A página de detalhes
        # fica focada no cadastro visual da placa e nas referências corretas.
        body_layout.addStretch()

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def _card(self, title: str, subtitle: str):
        card = QFrame(); card.setObjectName("detailsCard")
        lay = QVBoxLayout(card); lay.setContentsMargins(18, 16, 18, 18); lay.setSpacing(10)

        header = QFrame(); header.setObjectName("cardHeader")
        header_row = QHBoxLayout(header); header_row.setContentsMargins(0, 0, 0, 8); header_row.setSpacing(10)
        accent = QFrame(); accent.setObjectName("cardAccent"); accent.setFixedSize(3, 34)
        text_box = QVBoxLayout(); text_box.setSpacing(1)
        t = QLabel(title); t.setObjectName("cardTitle")
        s = QLabel(subtitle); s.setObjectName("cardSub"); s.setWordWrap(True)
        text_box.addWidget(t); text_box.addWidget(s)
        header_row.addWidget(accent); header_row.addLayout(text_box, 1)
        lay.addWidget(header)
        return card

    @staticmethod
    def _setup_table(table: QTableWidget):
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(36)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setMinimumHeight(160)
        table.horizontalHeader().setMinimumHeight(34)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    # -------------------------------------------------------------- routing
    def load_board(self, board_id: int):
        self.board_id = int(board_id)
        self.board = self.session.get(BoardUnit, self.board_id)
        if self.board is None:
            self.route_label.setText(f"/placas/{board_id}/detalhes")
            self.title_label.setText("Placa não encontrada")
            self.meta_label.setText("O registro pode ter sido removido.")
            return
        self.session.refresh(self.board)
        self.refresh()

    def refresh(self):
        if not self.board_id:
            return
        try:
            self.session.expire_all()
        except Exception:
            pass
        self.board = self.session.get(BoardUnit, self.board_id)
        if not self.board:
            return
        b = self.board
        self.route_label.setText(f"/placas/{b.id}/detalhes")
        self.title_label.setText(b.name or f"Placa {b.id}")
        self.meta_label.setText(
            f"ID #{b.id}   •   Código/SN: {b.serial_number or '—'}   •   Modelo: {b.model or '—'}"
        )
        self.status_chip.setText("ATIVA" if b.is_active else "INATIVA")
        self.status_chip.setProperty("state", "active" if b.is_active else "inactive")
        self.status_chip.style().unpolish(self.status_chip); self.status_chip.style().polish(self.status_chip)
        self._refresh_info()
        self._refresh_documents()
        self._refresh_board_canvas()
        self._refresh_test_points()
        self._refresh_references()

    def _refresh_info(self):
        while self.info_grid.count():
            item = self.info_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        b = self.board
        model = b.board_model
        machine_name = b.machine.name if b.machine else "Sem equipamento"
        # Somente as informações que já eram exibidas originalmente na tela
        # de placas. Nada de fabricante/cliente/OS/observações extras aqui.
        values = [
            ("Nome", b.name or "—"),
            ("Modelo", b.model or (model.name if model else "—")),
            ("Versão", b.version or "—"),
            ("Número de série", b.serial_number or "—"),
            ("Equipamento", machine_name),
            ("Cadastrada em", _fmt_date(b.created_at)),
        ]
        for idx, (label, value) in enumerate(values):
            row, col = divmod(idx, 2)
            box = QFrame(); box.setObjectName("infoItem")
            lay = QVBoxLayout(box); lay.setContentsMargins(10, 8, 10, 8); lay.setSpacing(2)
            l = QLabel(label.upper()); l.setObjectName("infoLabel")
            v = QLabel(str(value)); v.setObjectName("infoValue"); v.setWordWrap(True)
            lay.addWidget(l); lay.addWidget(v)
            self.info_grid.addWidget(box, row, col)

    def _refresh_documents(self):
        if not self.board:
            return
        docs = (
            self.session.query(BoardDocument)
            .filter(BoardDocument.board_id == self.board.id)
            .order_by(BoardDocument.created_at.desc())
            .all()
        )
        self.documents_count.setText(f"{len(docs)} documento(s)")
        self.documents_table.setRowCount(0)
        for doc in docs:
            row = self.documents_table.rowCount()
            self.documents_table.insertRow(row)
            self.documents_table.setRowHeight(row, 40)
            title = QTableWidgetItem(doc.title or "—")
            title.setData(Qt.ItemDataRole.UserRole, doc.id)
            filename = QTableWidgetItem(doc.original_name or (doc.file_path or "—").split("/")[-1])
            created = QTableWidgetItem(_fmt_date(doc.created_at))
            notes = QTableWidgetItem(doc.notes or "—")
            for col, item in enumerate((title, filename, created, notes)):
                self.documents_table.setItem(row, col, item)
        if docs:
            self.documents_table.selectRow(0)

    def _selected_board_document(self):
        row = self.documents_table.currentRow()
        if row < 0:
            return None
        item = self.documents_table.item(row, 0)
        if not item:
            return None
        doc_id = item.data(Qt.ItemDataRole.UserRole)
        return self.session.get(BoardDocument, int(doc_id)) if doc_id is not None else None

    def add_board_document(self):
        if not self.board:
            return
        dlg = AddDocumentDialog(f"Placa: {self.board.name}", self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        title, source, notes = dlg.values()
        try:
            stored = _copy_document(source, "board", self.board.id)
            doc = BoardDocument(
                board_id=self.board.id,
                title=title,
                file_path=stored,
                original_name=source.replace("\\", "/").split("/")[-1],
                notes=notes,
            )
            self.session.add(doc)
            self.session.commit()
            self._refresh_documents()
        except Exception as exc:
            self.session.rollback()
            QMessageBox.critical(self, "Documento", f"Não foi possível adicionar o documento:\n\n{exc}")

    def open_board_document(self):
        doc = self._selected_board_document()
        if not doc:
            QMessageBox.information(self, "Documento", "Selecione um documento da placa.")
            return
        path = _resolve_file(doc.file_path)
        if not path:
            QMessageBox.warning(self, "Arquivo não encontrado", "O documento está cadastrado, mas o arquivo não foi localizado no projeto.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def remove_board_document(self):
        doc = self._selected_board_document()
        if not doc:
            QMessageBox.information(self, "Documento", "Selecione um documento da placa.")
            return
        answer = QMessageBox.question(
            self,
            "Remover documento",
            f"Remover '{doc.title}' dos documentos desta placa?\n\nO arquivo físico será mantido na pasta do projeto.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.session.delete(doc)
            self.session.commit()
            self._refresh_documents()
        except Exception as exc:
            self.session.rollback()
            QMessageBox.critical(self, "Documento", f"Não foi possível remover o documento:\n\n{exc}")

    def _refresh_test_points(self):
        points = self.session.query(TestPoint).filter_by(board_id=self.board.id).order_by(TestPoint.refdes).all()
        self.test_points_table.setRowCount(len(points))
        for row, p in enumerate(points):
            slot = int(getattr(p, "image_slot", 1) or 1)
            vals = [
                p.refdes, f"Imagem {slot}", str(p.x), str(p.y),
                _fmt_voltage(p.expected_voltage_v),
                _fmt_frequency(p.expected_frequency_hz),
                p.marker_color or "#E53935",
            ]
            for col, value in enumerate(vals):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, p.id)
                if col == 6:
                    item.setForeground(QColor(p.marker_color or "#E53935"))
                self.test_points_table.setItem(row, col, item)

    # ------------------------------------------------------- board image map
    def _image_slots(self):
        """Retorna {1: BoardImage|None, 2: BoardImage|None} sem apagar imagens legadas."""
        slots = {1: None, 2: None}
        if not self.board:
            return slots
        images = sorted(list(self.board.images), key=lambda i: (i.created_at or datetime.min, i.id or 0))
        remaining = []
        for img in images:
            desc = (img.description or "").upper().strip()
            if desc == "SLOT_1" and slots[1] is None:
                slots[1] = img
            elif desc == "SLOT_2" and slots[2] is None:
                slots[2] = img
            else:
                remaining.append(img)
        for slot in (1, 2):
            if slots[slot] is None and remaining:
                slots[slot] = remaining.pop(0)
        return slots

    def _active_image(self):
        return self._image_slots().get(self.active_image_slot)

    def set_image_slot(self, slot: int):
        self.active_image_slot = 1 if int(slot) != 2 else 2
        self.slot1_btn.blockSignals(True); self.slot2_btn.blockSignals(True)
        self.slot1_btn.setChecked(self.active_image_slot == 1)
        self.slot2_btn.setChecked(self.active_image_slot == 2)
        self.slot1_btn.blockSignals(False); self.slot2_btn.blockSignals(False)
        self.current_point = None
        self.point_options_btn.setEnabled(False)
        self._end_point_placement()
        self._refresh_board_canvas()
        self._refresh_references()

    def _refresh_board_canvas(self):
        self.board_scene.clear(); self.point_items.clear()
        if not self.board:
            self.mapping_status.setText("Nenhuma placa selecionada.")
            return
        img = self._active_image()
        if img:
            real = resolve_image_path(img.path)
            pix = QPixmap(real) if real else QPixmap()
            if not pix.isNull():
                self.board_scene.addItem(QGraphicsPixmapItem(pix))
                self.board_scene.setSceneRect(QRectF(pix.rect()))
            else:
                self.mapping_status.setText(f"Imagem {self.active_image_slot} não encontrada.")
        else:
            self.board_scene.setSceneRect(QRectF(0, 0, 1000, 650))
            self.mapping_status.setText(f"Imagem {self.active_image_slot} vazia — use Adicionar / Trocar imagem.")

        points = self.session.query(TestPoint).filter_by(board_id=self.board.id).all()
        visible = [p for p in points if int(getattr(p, "image_slot", 1) or 1) == self.active_image_slot]
        for p in visible:
            item = BoardDetailsPointItem(p, self)
            self.board_scene.addItem(item); self.point_items[p.id] = item
        self.mapping_status.setText(
            f"Imagem {self.active_image_slot} • {len(visible)} ponto(s) • arraste os pontos para reposicionar."
        )
        if img:
            self.fit_image()

    def replace_active_image(self):
        if not self.board:
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"Selecionar Imagem {self.active_image_slot}", "",
            "Imagens (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not file_path:
            return
        try:
            stored = import_image_to_project(file_path)
            slots = self._image_slots(); img = slots.get(self.active_image_slot)
            if img is None:
                img = BoardImage(board_id=self.board.id, path=stored, description=f"SLOT_{self.active_image_slot}")
                self.session.add(img)
            else:
                img.path = stored; img.description = f"SLOT_{self.active_image_slot}"
                self.session.add(img)
            self.session.commit(); self.session.refresh(self.board)
            self._refresh_board_canvas()
            self.board_updated.emit(self.board.id)
        except Exception as exc:
            self.session.rollback(); QMessageBox.critical(self, "Imagem", f"Não foi possível salvar a imagem:\n{exc}")

    def remove_active_image(self):
        img = self._active_image()
        if not img:
            return
        reply = QMessageBox.question(
            self, "Remover imagem",
            f"Remover a Imagem {self.active_image_slot} desta placa?\n\nOs pontos não serão apagados.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.session.delete(img); self.session.commit(); self.session.refresh(self.board)
            self._refresh_board_canvas(); self.board_updated.emit(self.board.id)
        except Exception as exc:
            self.session.rollback(); QMessageBox.critical(self, "Imagem", str(exc))

    def fit_image(self):
        self.board_view.fit_scene()

    def _zoom_changed(self, value: int):
        self.zoom_slider.blockSignals(True); self.zoom_slider.setValue(int(value)); self.zoom_slider.blockSignals(False)
        self.zoom_label.setText(f"{int(value)}%")

    def _toggle_point_placement(self, enabled: bool):
        if enabled and (not self.board or self._active_image() is None):
            QMessageBox.information(self, "Novo ponto", "Adicione uma imagem neste slot antes de posicionar pontos.")
            self.add_visual_point_btn.blockSignals(True); self.add_visual_point_btn.setChecked(False); self.add_visual_point_btn.blockSignals(False)
            return
        self._placing_point = bool(enabled)
        self.board_view.set_placement_mode(enabled)
        self.add_visual_point_btn.setText("Clique na placa…" if enabled else "+ Novo Ponto")
        if enabled:
            self.mapping_status.setText("Clique na posição desejada da placa.")

    def _end_point_placement(self):
        if not hasattr(self, "board_view"):
            return
        self._placing_point = False; self.board_view.set_placement_mode(False)
        self.add_visual_point_btn.blockSignals(True); self.add_visual_point_btn.setChecked(False); self.add_visual_point_btn.blockSignals(False)
        self.add_visual_point_btn.setText("+ Novo Ponto")

    def _place_new_point(self, x: float, y: float):
        self._end_point_placement()
        if not self.board:
            return
        dialog = NewTestPointDialog(self)
        dialog.x.setValue(int(round(x))); dialog.y.setValue(int(round(y)))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._create_point_from_dialog(dialog, self.active_image_slot)

    def _create_point_from_dialog(self, dialog: NewTestPointDialog, slot: int):
        refdes = dialog.refdes.text().strip()
        exists = self.session.query(TestPoint).filter_by(board_id=self.board.id, refdes=refdes).first()
        if exists:
            QMessageBox.warning(self, "Ponto", f"Já existe o ponto {refdes} nesta placa.")
            return
        try:
            point = TestPoint(
                board_id=self.board.id, refdes=refdes,
                x=dialog.x.value(), y=dialog.y.value(), image_slot=int(slot),
                expected_voltage_v=_float_or_none(dialog.expected_v.text()),
                expected_current_a=_float_or_none(dialog.expected_a.text()),
                expected_frequency_hz=_float_or_none(dialog.expected_hz.text()),
                marker_color="#E53935", marker_shape="circle", marker_size=16, notes=dialog.notes.toPlainText().strip() or None,
            )
            self.session.add(point); self.session.commit(); self.session.refresh(point)
            self._refresh_board_canvas(); self._refresh_test_points(); self.select_point(point)
            self.board_updated.emit(self.board.id)
        except Exception as exc:
            self.session.rollback(); QMessageBox.critical(self, "Ponto", f"Não foi possível criar o ponto:\n{exc}")

    def select_point(self, point: TestPoint):
        self.current_point = point
        slot = int(getattr(point, "image_slot", 1) or 1)
        if slot != self.active_image_slot:
            self.set_image_slot(slot)
            self.current_point = point
        for pid, item in self.point_items.items():
            item.set_selected(pid == point.id)
        self.point_options_btn.setEnabled(True)
        self.mapping_status.setText(f"Selecionado: {point.refdes} • Imagem {slot} • ({point.x}, {point.y})")

    def point_moved(self, point: TestPoint, x: int, y: int):
        try:
            point.x = int(x); point.y = int(y); self.session.add(point); self.session.commit()
            self._refresh_test_points(); self.mapping_status.setText(f"{point.refdes} movido para ({x}, {y}).")
            self.board_updated.emit(self.board.id)
        except Exception as exc:
            self.session.rollback(); self.session.refresh(point)
            item = self.point_items.get(point.id)
            if item: item.setPos(point.x, point.y)
            QMessageBox.critical(self, "Ponto", str(exc))

    def edit_point(self, point: TestPoint | None = None):
        point = point or self.current_point
        if not point:
            return
        try:
            reference = None
            if self.board and self.board.model_id:
                reference = (
                    self.session.query(OscilloscopeReference)
                    .filter_by(board_model_id=self.board.model_id, refdes=point.refdes)
                    .first()
                )
            dlg = PointDetailsDialog(point, reference, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self.session.refresh(point)
                return
            for field, value in dlg.values().items():
                setattr(point, field, value)
            self.session.add(point); self.session.commit(); self.session.refresh(point)
            self._refresh_board_canvas(); self._refresh_test_points(); self._refresh_references(); self.select_point(point)
            self.board_updated.emit(self.board.id)
        except Exception as exc:
            self.session.rollback()
            QMessageBox.critical(self, "Ponto", f"Não foi possível editar:\n{exc}")

    def change_point_color(self, point: TestPoint | None = None):
        point = point or self.current_point
        if not point: return
        chosen = QColorDialog.getColor(QColor(point.marker_color or "#E53935"), self, f"Cor de {point.refdes}")
        if not chosen.isValid(): return
        point.marker_color = chosen.name().upper(); self.session.add(point); self.session.commit()
        item = self.point_items.get(point.id)
        if item: item.update_color(point.marker_color); item.set_selected(True)
        self._refresh_test_points()

    def change_point_appearance(self, point: TestPoint | None = None):
        point = point or self.current_point
        if not point:
            return
        dlg = MarkerAppearanceDialog(point, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            shape, size = dlg.values()
            point.marker_shape = shape
            point.marker_size = size
            self.session.add(point)
            self.session.commit()
            item = self.point_items.get(point.id)
            if item:
                item.update_appearance()
                item.set_selected(True)
            self._refresh_test_points()
            self.mapping_status.setText(f"Marcador de {point.refdes}: {shape} • {size}px")
            self.board_updated.emit(self.board.id)
        except Exception as exc:
            self.session.rollback()
            QMessageBox.critical(self, "Ponto", f"Não foi possível alterar o marcador:\n{exc}")

    def move_point_to_other_image(self, point: TestPoint | None = None):
        point = point or self.current_point
        if not point: return
        target = 2 if int(getattr(point, "image_slot", 1) or 1) == 1 else 1
        point.image_slot = target; self.session.add(point); self.session.commit()
        self.set_image_slot(target); self._refresh_test_points(); self.select_point(point)

    def delete_point(self, point: TestPoint | None = None):
        point = point or self.current_point
        if not point: return
        if QMessageBox.question(self, "Excluir ponto", f"Excluir '{point.refdes}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.session.delete(point); self.session.commit(); self.current_point = None
            self._refresh_board_canvas(); self._refresh_test_points(); self._refresh_references(); self.point_options_btn.setEnabled(False)
            self.board_updated.emit(self.board.id)
        except Exception as exc:
            self.session.rollback(); QMessageBox.critical(self, "Ponto", str(exc))

    def show_point_menu(self, point: TestPoint, global_pos):
        self.select_point(point)
        menu = QMenu(self)
        menu.addAction("Editar informações…", lambda: self.edit_point(point))
        menu.addAction("Alterar cor…", lambda: self.change_point_color(point))
        menu.addAction("Formato / tamanho do marcador…", lambda: self.change_point_appearance(point))
        menu.addAction("Mover para a outra imagem", lambda: self.move_point_to_other_image(point))
        menu.addSeparator()
        menu.addAction(f"Excluir {point.refdes}", lambda: self.delete_point(point))
        menu.exec(global_pos.toPoint() if hasattr(global_pos, "toPoint") else global_pos)

    def _show_selected_point_menu(self):
        if not self.current_point: return
        pos = self.point_options_btn.mapToGlobal(self.point_options_btn.rect().bottomLeft())
        self.show_point_menu(self.current_point, pos)

    def _table_point_selected(self):
        rows = self.test_points_table.selectionModel().selectedRows()
        if not rows: return
        item = self.test_points_table.item(rows[0].row(), 0)
        pid = item.data(Qt.ItemDataRole.UserRole) if item else None
        if pid:
            point = self.session.get(TestPoint, int(pid))
            if point: self.select_point(point)

    def _table_point_menu(self, pos):
        item = self.test_points_table.itemAt(pos)
        if not item: return
        row = item.row(); id_item = self.test_points_table.item(row, 0)
        pid = id_item.data(Qt.ItemDataRole.UserRole) if id_item else None
        if not pid: return
        point = self.session.get(TestPoint, int(pid))
        if point: self.show_point_menu(point, self.test_points_table.viewport().mapToGlobal(pos))

    def _refresh_references(self):
        """Mostra somente as referências dos pontos da imagem atualmente selecionada."""
        self.references_table.blockSignals(True)

        if not self.board:
            self.references_table.setRowCount(0)
            self.references_table.blockSignals(False)
            return

        visible_points = (
            self.session.query(TestPoint)
            .filter(
                TestPoint.board_id == self.board.id,
                TestPoint.image_slot == int(self.active_image_slot),
            )
            .order_by(TestPoint.refdes)
            .all()
        )
        visible_refdes = {str(p.refdes).strip() for p in visible_points if getattr(p, 'refdes', None)}

        refs = (
            self.session.query(OscilloscopeReference)
            .filter_by(board_model_id=self.board.model_id)
            .order_by(OscilloscopeReference.refdes)
            .all()
        )
        refs = [ref for ref in refs if str(ref.refdes).strip() in visible_refdes]

        self.references_table.setRowCount(len(refs))
        for row, ref in enumerate(refs):
            vals = [
                ref.refdes,
                f"CH{ref.channel}",
                _fmt_voltage(ref.vpp_v),
                _fmt_voltage(ref.vrms_v),
                _fmt_frequency(ref.frequency_hz),
            ]
            for col, value in enumerate(vals):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, ref.refdes)
                tooltip_parts = [f"Imagem {self.active_image_slot}"]
                if ref.updated_at:
                    tooltip_parts.append(f"Atualizado em {_fmt_date(ref.updated_at)}")
                item.setToolTip(" • ".join(tooltip_parts))
                self.references_table.setItem(row, col, item)

        self.references_table.clearSelection()
        self.references_table.blockSignals(False)

    def _reference_table_selected(self):
        """Destaca no canvas o ponto correspondente à referência selecionada."""
        if not self.board or not self.references_table.selectionModel():
            return
        rows = self.references_table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.references_table.item(rows[0].row(), 0)
        if item is None:
            return
        refdes = item.data(Qt.ItemDataRole.UserRole) or item.text().strip()
        if not refdes:
            return

        point = (
            self.session.query(TestPoint)
            .filter(TestPoint.board_id == self.board.id, TestPoint.refdes == str(refdes))
            .first()
        )
        if point is None:
            self.mapping_status.setText(
                f"Referência {refdes} existe, mas este ponto ainda não foi posicionado nesta placa."
            )
            return

        self.select_point(point)
        # Centraliza a imagem no ponto, mantendo o zoom atual.
        item_graphics = self.point_items.get(point.id)
        if item_graphics is not None:
            self.board_view.centerOn(item_graphics)

    def _refresh_history(self):
        """Compatibilidade: histórico não é mais exibido em Detalhes da Placa."""
        return


    # --------------------------------------------------------------- actions
    def _emit_test(self):
        if self.board_id:
            self.test_requested.emit(self.board_id)

    def _emit_preferences(self):
        if self.board_id:
            self.preferences_requested.emit(self.board_id)

    def edit_board(self):
        if not self.board:
            return
        dialog = BoardEditDialog(self.board, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = dialog.name.text().strip()
        model_name = dialog.model.text().strip()
        version = dialog.version.text().strip()
        serial = dialog.serial.text().strip()
        if not all((name, model_name, version, serial)):
            QMessageBox.warning(self, "Placa", "Nome, modelo, versão e número de série são obrigatórios.")
            return
        duplicate = (
            self.session.query(BoardUnit)
            .filter(BoardUnit.serial_number == serial, BoardUnit.id != self.board.id)
            .first()
        )
        if duplicate:
            QMessageBox.warning(self, "Placa", "Já existe outra placa com esse número de série.")
            return
        try:
            model = (
                self.session.query(BoardModel)
                .filter_by(name=model_name, version=version)
                .first()
            )
            if model is None:
                model = BoardModel(name=model_name, version=version)
                self.session.add(model)
                self.session.flush()
            b = self.board
            b.name = name
            b.model = model_name
            b.version = version
            b.serial_number = serial
            b.is_active = dialog.active.isChecked()
            b.board_model = model
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            QMessageBox.critical(self, "Placa", f"Não foi possível salvar:\n{exc}")
            return
        self.refresh()
        self.board_updated.emit(self.board.id)

    def new_test_point(self):
        """Cadastro por formulário; usa o slot de imagem atualmente selecionado."""
        if not self.board:
            return
        dialog = NewTestPointDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._create_point_from_dialog(dialog, self.active_image_slot)

    def new_reference(self):
        if not self.board:
            return
        points = self.session.query(TestPoint).filter_by(board_id=self.board.id).order_by(TestPoint.refdes).all()
        if not points:
            QMessageBox.information(self, "Referência", "Cadastre ao menos um ponto na placa primeiro.")
            return
        dialog = NewReferenceDialog(points, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        point_id = dialog.point.currentData()
        point = self.session.get(TestPoint, point_id)
        if not point:
            return
        try:
            ref = (
                self.session.query(OscilloscopeReference)
                .filter_by(board_model_id=self.board.model_id, refdes=point.refdes)
                .first()
            )
            if ref is None:
                ref = OscilloscopeReference(
                    board_model_id=self.board.model_id,
                    refdes=point.refdes,
                )
                self.session.add(ref)
            ref.source_board_id = self.board.id
            ref.source_serial = self.board.serial_number
            ref.channel = dialog.channel.currentIndex() + 1
            ref.vpp_v = _float_or_none(dialog.vpp.text())
            ref.vrms_v = _float_or_none(dialog.vrms.text())
            ref.frequency_hz = _float_or_none(dialog.frequency.text())
            ref.tolerance_vpp_pct = _float_or_none(dialog.tol_vpp.text()) or 10.0
            ref.tolerance_vrms_pct = _float_or_none(dialog.tol_vrms.text()) or 10.0
            ref.tolerance_frequency_pct = _float_or_none(dialog.tol_freq.text()) or 5.0
            ref.notes = dialog.notes.toPlainText().strip() or None
            ref.updated_at = datetime.utcnow()
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            QMessageBox.critical(self, "Referência", f"Não foi possível salvar a referência:\n{exc}")
            return
        self._refresh_references()

    # --------------------------------------------------------------- style
    def _apply_style(self):
        self.setStyleSheet(
            """
            QWidget#boardDetailsRoot { background:#F3F6F9; color:#0F172A; font-family:'Segoe UI'; }
            QWidget#detailsBody { background:transparent; }
            QScrollArea { background:transparent; border:none; }
            QScrollArea > QWidget > QWidget { background:transparent; }

            QFrame#breadcrumbBar { background:transparent; border:none; }
            QPushButton#breadcrumbBtn { background:transparent; color:#475569; border:none; padding:4px 4px;
                font-size:11px; font-weight:700; text-align:left; }
            QPushButton#breadcrumbBtn:hover { color:#0F766E; }
            QLabel#routeLabel { color:#94A3B8; font-size:10px; }

            QFrame#detailsHeader { background:#0B1220; border:1px solid #1E293B; border-radius:13px; }
            QLabel#detailsEyebrow { color:#2DD4BF; font-size:9px; font-weight:800; letter-spacing:1px; }
            QLabel#detailsTitle { color:#FFFFFF; font:750 22px 'Segoe UI'; }
            QLabel#detailsMeta { color:#94A3B8; font:10px 'Segoe UI'; }
            QLabel#statusChip { padding:6px 12px; border-radius:12px; font:800 9px 'Segoe UI'; }
            QLabel#statusChip[state='active'] { color:#A7F3D0; background:#064E3B; border:1px solid #0F766E; }
            QLabel#statusChip[state='inactive'] { color:#FECACA; background:#7F1D1D; border:1px solid #B91C1C; }
            QPushButton#headerEditBtn { background:#172033; color:#E2E8F0; border:1px solid #334155;
                border-radius:8px; min-height:38px; padding:0 15px; font-weight:700; }
            QPushButton#headerEditBtn:hover { border-color:#2DD4BF; color:#FFFFFF; }

            QFrame#detailsCard { background:#FFFFFF; border:1px solid #DFE7EF; border-radius:11px; }
            QFrame#cardHeader { background:transparent; border:none; border-bottom:1px solid #EEF2F7; }
            QFrame#cardAccent { background:#0F766E; border:none; border-radius:1px; }
            QLabel#cardTitle { color:#0F172A; font:750 14px 'Segoe UI'; }
            QLabel#cardSub { color:#64748B; font:10px 'Segoe UI'; }

            QFrame#workflowCard { background:#0F172A; border:1px solid #1E293B; border-radius:10px; }
            QLabel#workflowLabel { color:#2DD4BF; font-size:9px; font-weight:800; letter-spacing:.8px; }
            QLabel#workflowSub { color:#CBD5E1; font-size:10px; }

            QFrame#infoItem { background:#F8FAFC; border:1px solid #E8EEF5; border-radius:9px; }
            QLabel#infoLabel { color:#64748B; font:800 9px 'Segoe UI'; letter-spacing:.4px; }
            QLabel#infoValue { color:#172033; font:650 12px 'Segoe UI'; }

            QPushButton#primaryBtn { background:#0F766E; color:#FFFFFF; border:1px solid #0F766E;
                border-radius:8px; min-height:37px; padding:0 15px; font-weight:750; }
            QPushButton#primaryBtn:hover { background:#0D9488; border-color:#0D9488; }
            QPushButton#secondaryBtn, QPushButton#ghostBtn { background:#FFFFFF; color:#334155;
                border:1px solid #CBD5E1; border-radius:8px; min-height:35px; padding:0 13px; font-weight:650; }
            QFrame#workflowCard QPushButton#primaryBtn { background:#0F766E; color:white; }
            QFrame#workflowCard QPushButton#secondaryBtn { background:#172033; color:#E2E8F0; border-color:#334155; }
            QPushButton#secondaryBtn:hover, QPushButton#ghostBtn:hover { background:#F8FAFC; border-color:#94A3B8; }

            QTableWidget { background:#FFFFFF; alternate-background-color:#F8FAFC; color:#1E293B;
                border:1px solid #E2E8F0; border-radius:8px; gridline-color:transparent; selection-background-color:#DFF7F3;
                selection-color:#0F172A; outline:0; }
            QTableWidget::item { padding:6px 8px; border-bottom:1px solid #F1F5F9; }
            QHeaderView::section { background:#F8FAFC; color:#64748B; border:none; border-bottom:1px solid #E2E8F0;
                padding:7px 8px; font:800 9px 'Segoe UI'; }
            QLabel#documentCountChip { color:#0F766E; background:#ECFDF5; border:1px solid #A7F3D0;
                border-radius:9px; padding:4px 8px; font:800 9px 'Segoe UI'; }
            QPushButton#dangerBtn { background:#FFFFFF; color:#B91C1C; border:1px solid #FECACA;
                border-radius:8px; min-height:35px; padding:0 13px; font-weight:700; }
            QPushButton#dangerBtn:hover { background:#FEF2F2; border-color:#FCA5A5; }

            QGraphicsView { background:#070C12; border:1px solid #243244; border-radius:9px; }
            QFrame#mapControls { background:#F8FAFC; border:1px solid #E2E8F0; border-radius:10px; }
            QFrame#referenceSidePanel { background:#F8FAFC; border:1px solid #E2E8F0; border-radius:10px; }
            QLabel#mapControlsTitle { color:#475569; font:800 9px 'Segoe UI'; letter-spacing:.6px; }
            QLabel#mapHint { color:#64748B; font:10px 'Segoe UI'; }
            QFrame#mapSeparator { background:#E2E8F0; border:none; }
            QPushButton#slotBtn { background:#FFFFFF; color:#475569; border:1px solid #CBD5E1; border-radius:7px;
                padding:0 10px; min-height:34px; font-weight:750; }
            QPushButton#slotBtn:checked { background:#0F172A; color:#FFFFFF; border-color:#0F172A; }
            QSlider::groove:horizontal { height:4px; background:#CBD5E1; border-radius:2px; }
            QSlider::handle:horizontal { width:14px; margin:-5px 0; border-radius:7px; background:#0F766E; }
            """
        )
