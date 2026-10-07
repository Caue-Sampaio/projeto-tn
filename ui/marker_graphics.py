from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QBrush, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QSpinBox, QVBoxLayout, QWidget,
)


DEFAULT_MARKER_SHAPE = "circle"
DEFAULT_MARKER_SIZE = 16
MIN_MARKER_SIZE = 8
MAX_MARKER_SIZE = 40

MARKER_SHAPES = {
    "circle": "Círculo",
    "square": "Quadrado",
    "diamond": "Losango",
    "arrow": "Seta",
    "cross": "Cruz",
}


def normalize_marker_shape(shape: str | None) -> str:
    value = str(shape or DEFAULT_MARKER_SHAPE).strip().lower()
    return value if value in MARKER_SHAPES else DEFAULT_MARKER_SHAPE


def normalize_marker_size(size) -> int:
    try:
        value = int(size)
    except (TypeError, ValueError):
        value = DEFAULT_MARKER_SIZE
    return max(MIN_MARKER_SIZE, min(MAX_MARKER_SIZE, value))


def build_marker_path(shape: str | None, size) -> QPainterPath:
    """Cria um marcador centralizado na origem do item gráfico."""
    shape = normalize_marker_shape(shape)
    s = float(normalize_marker_size(size))
    h = s / 2.0
    path = QPainterPath()

    if shape == "circle":
        path.addEllipse(QRectF(-h, -h, s, s))
        return path

    if shape == "square":
        path.addRect(QRectF(-h, -h, s, s))
        return path

    if shape == "diamond":
        path.addPolygon(QPolygonF([
            QPointF(0, -h), QPointF(h, 0), QPointF(0, h), QPointF(-h, 0)
        ]))
        path.closeSubpath()
        return path

    if shape == "arrow":
        # Seta apontando para baixo. O centro geométrico continua próximo da
        # coordenada do ponto, mas o bico deixa claro onde está a medição.
        w = h * 0.42
        stem_top = -h
        head_y = -h * 0.05
        path.addPolygon(QPolygonF([
            QPointF(-w, stem_top), QPointF(w, stem_top),
            QPointF(w, head_y), QPointF(h, head_y),
            QPointF(0, h), QPointF(-h, head_y),
            QPointF(-w, head_y),
        ]))
        path.closeSubpath()
        return path

    # Cruz preenchida: área clicável confortável, diferente de duas linhas finas.
    arm = s * 0.26
    path.addPolygon(QPolygonF([
        QPointF(-arm, -h), QPointF(arm, -h),
        QPointF(arm, -arm), QPointF(h, -arm),
        QPointF(h, arm), QPointF(arm, arm),
        QPointF(arm, h), QPointF(-arm, h),
        QPointF(-arm, arm), QPointF(-h, arm),
        QPointF(-h, -arm), QPointF(-arm, -arm),
    ]))
    path.closeSubpath()
    return path


def draw_marker(painter: QPainter, x: float, y: float, *, shape: str, size: int,
                color: QColor, selected: bool = False) -> None:
    """Desenha o mesmo marcador em widgets que usam QPainter, como Teste Geral."""
    painter.save()
    painter.translate(float(x), float(y))
    path = build_marker_path(shape, size)
    fill = QColor(color)
    fill.setAlpha(225 if selected else 185)
    pen_color = QColor("#FDE047") if selected else QColor("#FFFFFF")
    painter.setBrush(QBrush(fill))
    painter.setPen(QPen(pen_color, 2.6 if selected else 1.4))
    painter.drawPath(path)
    painter.restore()


class MarkerPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.shape = DEFAULT_MARKER_SHAPE
        self.size = DEFAULT_MARKER_SIZE
        self.color = QColor("#E53935")
        self.setMinimumHeight(72)

    def set_values(self, shape: str, size: int, color: str | QColor = "#E53935"):
        self.shape = normalize_marker_shape(shape)
        self.size = normalize_marker_size(size)
        self.color = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0B1220"))
        draw_marker(
            painter,
            self.width() / 2,
            self.height() / 2,
            shape=self.shape,
            size=self.size,
            color=self.color,
        )


class MarkerAppearanceDialog(QDialog):
    """Editor compacto e reutilizável da aparência de um ponto."""

    def __init__(self, point, parent=None):
        super().__init__(parent)
        self.point = point
        self.setWindowTitle(f"Aparência do marcador — {getattr(point, 'refdes', 'Ponto')}")
        self.setModal(True)
        self.setMinimumWidth(360)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("Marcador do ponto")
        title.setStyleSheet("font-size:15px;font-weight:700;")
        root.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.shape_combo = QComboBox()
        for key, label in MARKER_SHAPES.items():
            self.shape_combo.addItem(label, key)
        current_shape = normalize_marker_shape(getattr(point, "marker_shape", None))
        idx = self.shape_combo.findData(current_shape)
        self.shape_combo.setCurrentIndex(max(0, idx))

        self.size_spin = QSpinBox()
        self.size_spin.setRange(MIN_MARKER_SIZE, MAX_MARKER_SIZE)
        self.size_spin.setSuffix(" px")
        self.size_spin.setValue(normalize_marker_size(getattr(point, "marker_size", None)))

        form.addRow("Formato", self.shape_combo)
        form.addRow("Tamanho", self.size_spin)
        root.addLayout(form)

        self.preview = MarkerPreview()
        root.addWidget(self.preview)

        info = QLabel("A cor continua sendo configurada pela opção ‘Alterar cor’. O tamanho é individual por ponto.")
        info.setWordWrap(True)
        info.setStyleSheet("color:#94A3B8;font-size:11px;")
        root.addWidget(info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.shape_combo.currentIndexChanged.connect(self._refresh_preview)
        self.size_spin.valueChanged.connect(self._refresh_preview)
        self._refresh_preview()

    def _refresh_preview(self):
        self.preview.set_values(
            self.shape_combo.currentData(),
            self.size_spin.value(),
            getattr(self.point, "marker_color", None) or "#E53935",
        )

    def values(self) -> tuple[str, int]:
        return normalize_marker_shape(self.shape_combo.currentData()), normalize_marker_size(self.size_spin.value())
