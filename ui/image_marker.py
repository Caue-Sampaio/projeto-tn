# ui/image_marker.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFormLayout, QTextEdit, QListWidget, QListWidgetItem, QMessageBox,
    QSpinBox, QInputDialog, QGraphicsView, QGraphicsScene,
    QGraphicsPixmapItem, QGraphicsEllipseItem, QGraphicsTextItem,
    QGroupBox, QComboBox, QSlider, QDialog, QDialogButtonBox,
    QProgressBar, QSplitter, QFrame, QTabWidget, QMenu
)
from PyQt6.QtGui import QPixmap, QColor, QPen, QWheelEvent, QFont, QPainter, QAction
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF
from db.models import TestPoint, BoardUnit, Measurement
from sqlalchemy.orm import Session
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class TestPointItem(QGraphicsEllipseItem):
    """Item gráfico interativo representando um ponto de teste"""
    
    def __init__(self, tp: TestPoint, marker_widget):
        # Tamanho base - será ajustado pelo zoom
        base_size = 15
        super().__init__(-base_size/2, -base_size/2, base_size, base_size)
        self.tp = tp
        self.marker_widget = marker_widget
        self.base_size = base_size
        
        # Configura aparência inicial
        self.setBrush(QColor(255, 0, 0, 180))
        pen = QPen(QColor("red"))
        pen.setWidth(2)
        self.setPen(pen)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        # Label centralizado acima do ponto
        self.label = QGraphicsTextItem(tp.refdes, self)
        self.label.setDefaultTextColor(QColor("red"))
        self.label.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        
        # Centraliza o label
        self.update_label_position()
        
        # Posiciona o item no local salvo
        self.setPos(tp.x, tp.y)
        
        # Tooltip
        self.setToolTip(f"{tp.refdes}\nX: {tp.x}, Y: {tp.y}")

    def update_label_position(self):
        """Atualiza posição do label"""
        text_rect = self.label.boundingRect()
        self.label.setPos(-text_rect.width()/2, -20)

    def update_size_based_on_zoom(self, zoom_level):
        """Atualiza tamanho baseado no nível de zoom"""
        # Tamanho inversamente proporcional ao zoom
        # Zoom 1.0 = tamanho base, Zoom 2.0 = metade do tamanho, etc.
        new_size = max(5, self.base_size / zoom_level)
        self.setRect(-new_size/2, -new_size/2, new_size, new_size)
        
        # Atualiza fonte do label
        font_size = max(6, int(8 / zoom_level))
        self.label.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
        self.update_label_position()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.marker_widget.select_point(self.tp)
        elif event.button() == Qt.MouseButton.RightButton:
            # CORREÇÃO: Para QGraphicsSceneMouseEvent, usamos screenPos()
            screen_pos = event.screenPos()
            self.marker_widget.show_point_context_menu(self.tp, screen_pos)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        # Atualiza coordenadas no banco ao soltar
        center = self.sceneBoundingRect().center()
        self.tp.x = int(center.x())
        self.tp.y = int(center.y())
        self.marker_widget.session.add(self.tp)
        self.marker_widget.session.commit()
        
        self.update_label_position()
        
        logger.debug(f"Ponto {self.tp.refdes} movido para ({self.tp.x}, {self.tp.y})")
        super().mouseReleaseEvent(event)
        
    def hoverEnterEvent(self, event):
        """Efeito hover"""
        self.setBrush(QColor(255, 100, 100, 220))
        super().hoverEnterEvent(event)
        
    def hoverLeaveEvent(self, event):
        """Remove efeito hover"""
        self.setBrush(QColor(255, 0, 0, 180))
        super().hoverLeaveEvent(event)


class ZoomableGraphicsView(QGraphicsView):
    """QGraphicsView com suporte a zoom, arrastar e adicionar pontos"""
    
    point_add_request = pyqtSignal(float, float)  # Emite coordenadas para adicionar ponto
    zoom_changed = pyqtSignal(float)  # Novo sinal para notificar mudanças no zoom
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setScene(QGraphicsScene(self))
        self.pixmap_item = None
        self.marker_widget = None
        self.zoom_level = 1.0
        self.max_zoom = 5.0
        self.min_zoom = 0.1

    def load_image(self, path):
        """Carrega imagem no view"""
        pix = QPixmap(path)
        if pix.isNull():
            logger.error(f"Falha ao carregar imagem: {path}")
            return False
            
        self.scene().clear()
        self.pixmap_item = QGraphicsPixmapItem(pix)
        self.pixmap_item.setPos(0, 0)
        self.scene().addItem(self.pixmap_item)
        self.setSceneRect(self.pixmap_item.boundingRect())
        
        # Reset zoom
        self.zoom_level = 1.0
        self.resetTransform()
        
        logger.info(f"Imagem carregada: {path} ({pix.width()}x{pix.height()})")
        return True

    def wheelEvent(self, event: QWheelEvent):
        """Handle zoom com roda do mouse"""
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        
        # Salva zoom anterior
        old_zoom = self.zoom_level
        
        # Calcula fator de zoom
        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor
            
        # Aplica limites de zoom
        new_zoom = self.zoom_level * zoom_factor
        if self.min_zoom <= new_zoom <= self.max_zoom:
            self.zoom_level = new_zoom
            self.scale(zoom_factor, zoom_factor)
            
            # Atualiza o slider se houver marker_widget
            if self.marker_widget and hasattr(self.marker_widget, 'zoom_slider'):
                slider_value = int(self.zoom_level * 100)
                # Bloqueia temporariamente o sinal para evitar loop
                self.marker_widget.zoom_slider.blockSignals(True)
                self.marker_widget.zoom_slider.setValue(slider_value)
                self.marker_widget.zoom_slider.blockSignals(False)
                self.marker_widget.zoom_label.setText(f"Zoom: {slider_value}%")
            
            # Atualiza pontos
            if self.marker_widget and hasattr(self.marker_widget, 'update_points_size'):
                self.marker_widget.update_points_size()
            
        logger.debug(f"Zoom level: {self.zoom_level:.2f}")

    def mousePressEvent(self, event):
        """Handle clique do mouse"""
        if event.button() == Qt.MouseButton.MiddleButton:
            # Clique do botão do meio para adicionar ponto
            pos = self.mapToScene(event.position().toPoint())
            self.point_add_request.emit(pos.x(), pos.y())
        elif event.button() == Qt.MouseButton.RightButton:
            # Botão direito para contexto
            if self.marker_widget:
                pos = self.mapToScene(event.position().toPoint())
                # CORREÇÃO: Para QMouseEvent (widget), usamos globalPosition()
                screen_pos = event.globalPosition().toPoint()
                self.marker_widget.show_view_context_menu(pos, screen_pos)
        else:
            super().mousePressEvent(event)


class MeasurementDialog(QDialog):
    """Dialog para realizar medições em tempo real"""
    
    def __init__(self, instruments, parent=None):
        super().__init__(parent)
        self.instruments = instruments
        self.setup_ui()
        self.apply_styles()
        
    def setup_ui(self):
        """Configura a interface"""
        self.setWindowTitle("Medição em Tempo Real")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Instrumentos disponíveis
        instruments_group = QGroupBox("Instrumentos Conectados")
        instruments_layout = QVBoxLayout()
        
        self.instruments_label = QLabel()
        instruments_text = []
        if self.instruments.get("DMM"):
            instruments_text.append("✅ Multímetro Digital (DMM)")
        if self.instruments.get("OSC"):
            instruments_text.append("✅ Osciloscópio")
        if not instruments_text:
            instruments_text.append("❌ Nenhum instrumento conectado")
            
        self.instruments_label.setText("\n".join(instruments_text))
        instruments_layout.addWidget(self.instruments_label)
        instruments_group.setLayout(instruments_layout)
        layout.addWidget(instruments_group)
        
        # Controles de medição
        measure_group = QGroupBox("Realizar Medição")
        measure_layout = QFormLayout()
        
        self.measure_type = QComboBox()
        self.measure_type.addItems(["Tensão (V)", "Corrente (A)", "Frequência (Hz)"])
        
        self.measure_button = QPushButton("🔍 Realizar Medição")
        self.measure_button.clicked.connect(self.perform_measurement)
        
        self.result_label = QLabel("Aguardando medição...")
        self.result_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px;")
        
        measure_layout.addRow("Tipo:", self.measure_type)
        measure_layout.addRow("", self.measure_button)
        measure_layout.addRow("Resultado:", self.result_label)
        measure_group.setLayout(measure_layout)
        layout.addWidget(measure_group)
        
        # Botões
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
        
    def apply_styles(self):
        """Aplica estilos"""
        self.measure_button.setStyleSheet("""
            QPushButton {
                background-color: #27AE60;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 15px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        
    def perform_measurement(self):
        """Realiza medição com instrumentos"""
        try:
            measure_type = self.measure_type.currentText()
            result = None
            
            if "Tensão" in measure_type and self.instruments.get("DMM"):
                result = self.instruments["DMM"].measure_voltage()
                unit = "V"
            elif "Corrente" in measure_type and self.instruments.get("DMM"):
                result = self.instruments["DMM"].measure_current()
                unit = "A"
            elif "Frequência" in measure_type and self.instruments.get("OSC"):
                result = self.instruments["OSC"].measure_frequency()
                unit = "Hz"
            else:
                result = None
                
            if result is not None:
                self.result_label.setText(f"📊 {result:.4f} {unit}")
                self.result_label.setStyleSheet("color: #27AE60; font-size: 16px; font-weight: bold; padding: 10px;")
                logger.info(f"Medição realizada: {result:.4f} {unit}")
            else:
                self.result_label.setText("❌ Medição não disponível")
                self.result_label.setStyleSheet("color: #E74C3C; font-size: 16px; font-weight: bold; padding: 10px;")
                
        except Exception as e:
            logger.error(f"Erro na medição: {e}")
            self.result_label.setText("❌ Erro na medição")
            
    def get_measurement_result(self):
        """Retorna o resultado da medição"""
        text = self.result_label.text()
        if "📊" in text:
            return float(text.split("📊")[1].split(" ")[1])
        return None


class ImageMarker(QWidget):
    """Widget principal para marcação de imagens de placas"""
    
    point_selected = pyqtSignal(object)  # Emite TestPoint selecionado
    point_updated = pyqtSignal(object)   # Emite TestPoint atualizado
    
    def __init__(self, session: Session, board: BoardUnit, mode: str = "edit", instruments: dict | None = None):
        super().__init__()
        self.session = session
        self.board = board
        self.mode = mode
        self.instruments = instruments or {}
        self.current_point = None
        self.image_path = None
        self.test_point_items = {}  # CORREÇÃO: deve ser dicionário, não lista
        
        self.setWindowTitle(f"Imagem da Placa - {board.name} ({'Edição' if mode=='edit' else 'Visualização'})")
        self.setMinimumSize(1000, 700)
        
        self.setup_ui()
        self.apply_styles()
        
        # Conecta sinais
        self.view.point_add_request.connect(self.add_point_by_click)
    
    def on_zoom_changed(self, value):
        """Handle mudança no slider de zoom"""
        # Converte valor do slider (10-500) para fator de zoom (0.1-5.0)
        zoom_factor = value / 100.0
        
        # Aplica o zoom na view
        self.view.resetTransform()
        self.view.scale(zoom_factor, zoom_factor)
        
        # Atualiza o nível de zoom na view
        self.view.zoom_level = zoom_factor
        
        # Atualiza o label
        self.zoom_label.setText(f"Zoom: {value}%")
        
        # Atualiza o tamanho dos pontos baseado no novo zoom
        self.update_points_size()
    
    def update_points_size(self):
        """Atualiza o tamanho de todos os pontos baseado no zoom atual"""
        if hasattr(self.view, 'zoom_level'):
            zoom_level = self.view.zoom_level
            for tp_id, tp_item in self.test_point_items.items():
                try:
                    if hasattr(tp_item, 'update_size_based_on_zoom'):
                        tp_item.update_size_based_on_zoom(zoom_level)
                    else:
                        logger.warning(f"Item {tp_id} não tem método update_size_based_on_zoom")
                except Exception as e:
                    logger.error(f"Erro ao atualizar ponto {tp_id}: {e}")

        
    def setup_ui(self):
        """Configura a interface do usuário"""
        main_layout = QHBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Splitter principal
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Painel esquerdo - Visualização da imagem
        left_panel = self.create_image_panel()
        splitter.addWidget(left_panel)
        
        # Painel direito - Controles e informações
        right_panel = self.create_control_panel()
        splitter.addWidget(right_panel)
        
        # Configura proporções
        splitter.setSizes([600, 400])
        main_layout.addWidget(splitter)
        
        self.setLayout(main_layout)
        
    def create_image_panel(self):
        """Cria painel de visualização da imagem"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Controles da imagem
        controls_layout = QHBoxLayout()
        
        self.zoom_label = QLabel("Zoom: 100%")
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 500)  # 10% to 500%
        self.zoom_slider.setValue(100)
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        
        self.fit_button = QPushButton("Ajustar à Tela")
        self.fit_button.clicked.connect(self.fit_to_view)
        
        controls_layout.addWidget(QLabel("Zoom:"))
        controls_layout.addWidget(self.zoom_slider)
        controls_layout.addWidget(self.zoom_label)
        controls_layout.addStretch()
        controls_layout.addWidget(self.fit_button)
        
        # Área de visualização
        self.view = ZoomableGraphicsView()
        self.view.marker_widget = self
        self.view.setMinimumSize(400, 400)
        
        layout.addLayout(controls_layout)
        layout.addWidget(self.view)
        
        widget.setLayout(layout)
        return widget
        
    def create_control_panel(self):
        """Cria painel de controles e informações"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Abas para organização
        self.tab_widget = QTabWidget()
        
        # Aba de pontos
        points_tab = self.create_points_tab()
        self.tab_widget.addTab(points_tab, "📍 Pontos")
        
        # Aba de propriedades
        properties_tab = self.create_properties_tab()
        self.tab_widget.addTab(properties_tab, "⚙️ Propriedades")
        
        # Aba de medições
        if self.mode == "edit":
            measurements_tab = self.create_measurements_tab()
            self.tab_widget.addTab(measurements_tab, "📊 Medições")
        
        layout.addWidget(self.tab_widget)
        
        # Barra de status
        self.status_label = QLabel("Pronto")
        self.status_label.setStyleSheet("color: #7F8C8D; font-size: 11px; padding: 5px;")
        layout.addWidget(self.status_label)
        
        widget.setLayout(layout)
        return widget
        
    def create_points_tab(self):
        """Cria aba de gerenciamento de pontos"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Controles de pontos
        points_controls = QHBoxLayout()
        
        self.add_point_btn = QPushButton("➕ Adicionar Ponto")
        self.add_point_btn.clicked.connect(self.add_point_dialog)
        self.add_point_btn.setEnabled(self.mode == "edit")
        
        self.delete_point_btn = QPushButton("🗑️ Remover")
        self.delete_point_btn.clicked.connect(self.delete_current_point)
        self.delete_point_btn.setEnabled(False)
        
        points_controls.addWidget(self.add_point_btn)
        points_controls.addWidget(self.delete_point_btn)
        points_controls.addStretch()
        
        # Lista de pontos
        self.points_list = QListWidget()
        self.points_list.itemSelectionChanged.connect(self.on_point_list_selected)
        self.points_list.setMinimumHeight(150)
        
        layout.addLayout(points_controls)
        layout.addWidget(QLabel("Pontos de Teste:"))
        layout.addWidget(self.points_list)
        
        widget.setLayout(layout)
        return widget
        
    def create_properties_tab(self):
        """Cria aba de propriedades do ponto"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Grupo de informações básicas
        basic_group = QGroupBox("Informações do Ponto")
        basic_layout = QFormLayout()
        
        self.refdes_label = QLabel("-")
        self.coords_label = QLabel("-")
        
        basic_layout.addRow("RefDes:", self.refdes_label)
        basic_layout.addRow("Coordenadas:", self.coords_label)
        
        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)
        
        # Grupo de valores esperados
        expected_group = QGroupBox("Valores Esperados")
        expected_layout = QFormLayout()
        
        self.expected_voltage = QLineEdit()
        self.expected_voltage.setPlaceholderText("Ex: 3.3, 5.0, 12.0")
        self.set_field_style(self.expected_voltage)
        
        self.expected_current = QLineEdit()
        self.expected_current.setPlaceholderText("Ex: 0.1, 0.5, 1.0")
        self.set_field_style(self.expected_current)
        
        self.expected_frequency = QLineEdit()
        self.expected_frequency.setPlaceholderText("Ex: 1000, 12000, 50000")
        self.set_field_style(self.expected_frequency)
        
        self.expected_waveform = QLineEdit()
        self.expected_waveform.setPlaceholderText("Ex: Senoidal, Quadrada, Triangular")
        self.set_field_style(self.expected_waveform)
        
        expected_layout.addRow("Tensão (V):", self.expected_voltage)
        expected_layout.addRow("Corrente (A):", self.expected_current)
        expected_layout.addRow("Frequência (Hz):", self.expected_frequency)
        expected_layout.addRow("Forma de Onda:", self.expected_waveform)
        
        expected_group.setLayout(expected_layout)
        layout.addWidget(expected_group)
        
        # Grupo de tolerâncias
        tolerance_group = QGroupBox("Tolerâncias")
        tolerance_layout = QFormLayout()
        
        self.tolerance_voltage = QLineEdit()
        self.tolerance_voltage.setPlaceholderText("Ex: 0.1, 0.05")
        self.set_field_style(self.tolerance_voltage)
        
        self.tolerance_current = QLineEdit()
        self.tolerance_current.setPlaceholderText("Ex: 0.01, 0.005")
        self.set_field_style(self.tolerance_current)
        
        self.tolerance_frequency = QLineEdit()
        self.tolerance_frequency.setPlaceholderText("Ex: 10, 50, 100")
        self.set_field_style(self.tolerance_frequency)
        
        tolerance_layout.addRow("Tensão ±(V):", self.tolerance_voltage)
        tolerance_layout.addRow("Corrente ±(A):", self.tolerance_current)
        tolerance_layout.addRow("Frequência ±(Hz):", self.tolerance_frequency)
        
        tolerance_group.setLayout(tolerance_layout)
        layout.addWidget(tolerance_group)
        
        # Observações
        notes_group = QGroupBox("Observações")
        notes_layout = QVBoxLayout()
        
        self.notes_field = QTextEdit()
        self.notes_field.setPlaceholderText("Observações sobre este ponto de teste...")
        self.notes_field.setMaximumHeight(80)
        
        notes_layout.addWidget(self.notes_field)
        notes_group.setLayout(notes_layout)
        layout.addWidget(notes_group)
        
        # Botão salvar
        self.save_btn = QPushButton("💾 Salvar Propriedades")
        self.save_btn.clicked.connect(self.save_point_properties)
        self.save_btn.setEnabled(False)
        
        layout.addWidget(self.save_btn)
        layout.addStretch()
        
        widget.setLayout(layout)
        return widget
        
    def create_measurements_tab(self):
        """Cria aba de medições em tempo real"""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Grupo de medição
        measure_group = QGroupBox("Medição em Tempo Real")
        measure_layout = QVBoxLayout()
        
        self.measure_btn = QPushButton("🔍 Abrir Painel de Medição")
        self.measure_btn.clicked.connect(self.open_measurement_dialog)
        
        measure_info = QLabel(
            "Use o painel de medição para realizar medições\n"
            "em tempo real com os instrumentos conectados."
        )
        measure_info.setStyleSheet("color: #7F8C8D; font-size: 11px;")
        
        measure_layout.addWidget(self.measure_btn)
        measure_layout.addWidget(measure_info)
        measure_group.setLayout(measure_layout)
        layout.addWidget(measure_group)
        
        # Histórico de medições
        history_group = QGroupBox("Últimas Medições")
        history_layout = QVBoxLayout()
        
        self.measurements_list = QListWidget()
        self.measurements_list.setMaximumHeight(150)
        
        history_layout.addWidget(self.measurements_list)
        history_group.setLayout(history_layout)
        layout.addWidget(history_group)
        
        layout.addStretch()
        
        widget.setLayout(layout)
        return widget
        
    def apply_styles(self):
        """Aplica estilos aos componentes"""
        button_style = """
            QPushButton {
                background-color: #3498DB;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
            QPushButton:pressed {
                background-color: #21618C;
            }
            QPushButton:disabled {
                background-color: #BDC3C7;
                color: #7F8C8D;
            }
        """
        
        # Aplica estilos apenas aos botões que existem
        self.add_point_btn.setStyleSheet(button_style)
        self.save_btn.setStyleSheet(button_style)
        self.fit_button.setStyleSheet(button_style)
        
        # Aplica estilo ao measure_btn apenas se existir (modo edit)
        if hasattr(self, 'measure_btn'):
            self.measure_btn.setStyleSheet(button_style)
        
        self.delete_point_btn.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
        """)
        
        self.points_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                border: 1px solid #BDC3C7;
                border-radius: 5px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #ECF0F1;
            }
            QListWidget::item:selected {
                background-color: #3498DB;
                color: white;
            }
    """)
        
    def set_field_style(self, field):
        """Aplica estilo consistente aos campos"""
        if isinstance(field, QLineEdit):
            field.setStyleSheet("""
                QLineEdit {
                    border: 2px solid #BDC3C7;
                    border-radius: 5px;
                    padding: 6px 10px;
                    font-size: 13px;
                    background-color: white;
                }
                QLineEdit:focus {
                    border-color: #3498DB;
                }
                QLineEdit:disabled {
                    background-color: #F8F9FA;
                    color: #7F8C8D;
                }
            """)
            
    def load_image(self, path: str):
        """Carrega imagem no viewer"""
        self.image_path = path
        success = self.view.load_image(path)
        
        if success:
            self.refresh_points()
            self.show_status(f"Imagem carregada: {os.path.basename(path)}")
        else:
            self.show_status(f"Erro ao carregar imagem: {path}", "error")
            
        return success
        
    def refresh_points(self):
        """Atualiza a lista e visualização dos pontos"""
        self.points_list.clear()
        self.test_point_items.clear()  # Limpa dicionário de itens
        
        # Remove pontos antigos da cena
        for item in self.view.scene().items():
            if isinstance(item, TestPointItem):
                self.view.scene().removeItem(item)

        # Carrega pontos do banco
        points = self.session.query(TestPoint).filter_by(board_id=self.board.id).all()
        
        for tp in points:
            # Adiciona à lista
            item_text = f"{tp.refdes} (X:{tp.x}, Y:{tp.y})"
            if tp.expected_voltage_v is not None:
                item_text += f" - {tp.expected_voltage_v}V"
                
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, tp.id)
            self.points_list.addItem(item)

            # Adiciona à cena gráfica
            tp_item = TestPointItem(tp, self)
            self.view.scene().addItem(tp_item)
            self.test_point_items[tp.id] = tp_item  # CORREÇÃO: usa dicionário corretamente

        # Aplica zoom atual aos pontos
        self.update_points_size()
            
        self.show_status(f"Carregados {len(points)} pontos de teste")
        
    def on_point_list_selected(self):
        """Handle seleção na lista de pontos"""
        row = self.points_list.currentRow()
        if row < 0:
            self.current_point = None
            self.clear_point_form()
            self.delete_point_btn.setEnabled(False)
            self.save_btn.setEnabled(False)
            return
            
        item = self.points_list.item(row)
        tp_id = item.data(Qt.ItemDataRole.UserRole)
        self.current_point = self.session.get(TestPoint, tp_id)
        self.populate_point_form(self.current_point)
        self.delete_point_btn.setEnabled(self.mode == "edit")
        self.save_btn.setEnabled(self.mode == "edit")
        
    def select_point(self, tp: TestPoint):
        """Seleciona ponto programaticamente"""
        self.current_point = tp
        self.populate_point_form(tp)
        
        # Seleciona na lista
        for i in range(self.points_list.count()):
            item = self.points_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == tp.id:
                self.points_list.setCurrentItem(item)
                break
                
    def populate_point_form(self, tp: TestPoint):
        """Preenche formulário com dados do ponto"""
        if not tp:
            return
            
        self.refdes_label.setText(tp.refdes or "-")
        self.coords_label.setText(f"X: {tp.x}, Y: {tp.y}")
        
        # Valores esperados
        self.expected_voltage.setText("" if tp.expected_voltage_v is None else str(tp.expected_voltage_v))
        self.expected_current.setText("" if tp.expected_current_a is None else str(tp.expected_current_a))
        self.expected_frequency.setText("" if tp.expected_frequency_hz is None else str(tp.expected_frequency_hz))
        self.expected_waveform.setText(tp.expected_waveform or "")
        
        # Tolerâncias
        self.tolerance_voltage.setText("" if tp.tolerance_voltage_v is None else str(tp.tolerance_voltage_v))
        self.tolerance_current.setText("" if tp.tolerance_current_a is None else str(tp.tolerance_current_a))
        self.tolerance_frequency.setText("" if tp.tolerance_frequency_hz is None else str(tp.tolerance_frequency_hz))
        
        # Observações
        self.notes_field.setPlainText(tp.notes or "")
        
    def clear_point_form(self):
        """Limpa formulário de ponto"""
        self.refdes_label.setText("-")
        self.coords_label.setText("-")
        self.expected_voltage.clear()
        self.expected_current.clear()
        self.expected_frequency.clear()
        self.expected_waveform.clear()
        self.tolerance_voltage.clear()
        self.tolerance_current.clear()
        self.tolerance_frequency.clear()
        self.notes_field.clear()
        
    def add_point_dialog(self):
        """Abre diálogo para adicionar ponto"""
        refdes, ok = QInputDialog.getText(self, "Novo Ponto", "Digite o identificador (ex: TP1, VCC, GND):")
        if not ok or not refdes.strip():
            return
            
        # Pede coordenadas
        x, ok1 = QInputDialog.getInt(self, "Coordenada X", "Posição X:", 100, 0, 10000)
        y, ok2 = QInputDialog.getInt(self, "Coordenada Y", "Posição Y:", 100, 0, 10000)
        
        if ok1 and ok2:
            self.create_point(refdes.strip(), x, y)
            
    def add_point_by_click(self, x, y):
        """Adiciona ponto por clique no viewer"""
        if self.mode != "edit":
            return
            
        refdes, ok = QInputDialog.getText(self, "Novo Ponto", "Digite o identificador:")
        if ok and refdes.strip():
            self.create_point(refdes.strip(), int(x), int(y))
            
    def create_point(self, refdes, x, y):
        """Cria novo ponto de teste"""
        # Verifica se RefDes já existe
        existing = self.session.query(TestPoint).filter_by(board_id=self.board.id, refdes=refdes).first()
        if existing:
            self.show_status(f"Já existe um ponto com o RefDes '{refdes}'", "error")
            return
            
        try:
            tp = TestPoint(
                board_id=self.board.id,
                refdes=refdes,
                x=x,
                y=y
            )
            self.session.add(tp)
            self.session.commit()
            
            # Atualiza a visualização completa
            self.refresh_points()
            self.show_status(f"Ponto {refdes} criado em ({x}, {y})", "success")
            logger.info(f"Ponto criado: {refdes} at ({x}, {y})")
            
        except Exception as e:
            logger.error(f"Erro ao criar ponto: {e}")
            self.show_status(f"Erro ao criar ponto: {str(e)}", "error")
            
    def delete_current_point(self):
        """Exclui ponto atual"""
        if not self.current_point:
            return
            
        reply = QMessageBox.question(
            self, "Confirmar Exclusão",
            f"Excluir o ponto '{self.current_point.refdes}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                refdes = self.current_point.refdes
                
                # Remove do dicionário de itens (CORREÇÃO)
                if self.current_point.id in self.test_point_items:
                    # Remove da cena primeiro
                    item_to_remove = self.test_point_items[self.current_point.id]
                    self.view.scene().removeItem(item_to_remove)
                    # Remove do dicionário
                    del self.test_point_items[self.current_point.id]
                
                # Remove do banco
                self.session.delete(self.current_point)
                self.session.commit()
                
                # Atualiza a lista
                self.refresh_points()
                self.show_status(f"Ponto {refdes} excluído", "success")
                logger.info(f"Ponto excluído: {refdes}")
                
            except Exception as e:
                logger.error(f"Erro ao excluir ponto: {e}")
                self.show_status(f"Erro ao excluir ponto: {str(e)}", "error")
                
    def save_point_properties(self):
        """Salva propriedades do ponto atual"""
        if not self.current_point:
            self.show_status("Nenhum ponto selecionado", "error")
            return
            
        try:
            # Converte valores
            def to_float(text):
                return float(text) if text.strip() else None
                
            # Atualiza propriedades
            self.current_point.expected_voltage_v = to_float(self.expected_voltage.text())
            self.current_point.expected_current_a = to_float(self.expected_current.text())
            self.current_point.expected_frequency_hz = to_float(self.expected_frequency.text())
            self.current_point.expected_waveform = self.expected_waveform.text().strip() or None
            
            self.current_point.tolerance_voltage_v = to_float(self.tolerance_voltage.text())
            self.current_point.tolerance_current_a = to_float(self.tolerance_current.text())
            self.current_point.tolerance_frequency_hz = to_float(self.tolerance_frequency.text())
            
            self.current_point.notes = self.notes_field.toPlainText().strip() or None
            
            self.session.commit()
            self.refresh_points()
            self.show_status(f"Propriedades de {self.current_point.refdes} salvas", "success")
            self.point_updated.emit(self.current_point)
            logger.info(f"Propriedades atualizadas: {self.current_point.refdes}")
            
        except ValueError as e:
            self.show_status("Erro: valores numéricos inválidos", "error")
        except Exception as e:
            logger.error(f"Erro ao salvar propriedades: {e}")
            self.show_status(f"Erro ao salvar: {str(e)}", "error")
            
    
        
    def fit_to_view(self):
        """Ajusta imagem à tela"""
        if self.view.pixmap_item:
            self.view.fitInView(self.view.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            
            # Calcula o zoom aproximado após o fit
            view_rect = self.view.viewport().rect()
            scene_rect = self.view.pixmap_item.boundingRect()
            
            zoom_x = view_rect.width() / scene_rect.width()
            zoom_y = view_rect.height() / scene_rect.height()
            zoom_level = min(zoom_x, zoom_y) * 0.9  # Pequena margem
            
            # Atualiza o slider e zoom level
            slider_value = int(zoom_level * 100)
            self.zoom_slider.setValue(slider_value)
            self.view.zoom_level = zoom_level
            
            # Atualiza pontos
            self.update_points_size()
            
    def open_measurement_dialog(self):
        """Abre diálogo de medições"""
        dialog = MeasurementDialog(self.instruments, self)
        if dialog.exec():
            result = dialog.get_measurement_result()
            if result is not None and self.current_point:
                # Aqui você pode salvar a medição no ponto atual
                self.show_status(f"Medição realizada: {result}", "success")
                
    def show_point_context_menu(self, tp: TestPoint, screen_pos):
        """Mostra menu de contexto para ponto"""
        try:
            # Implementar menu contextual se necessário
            # Por enquanto, vamos apenas logar
            logger.debug(f"Menu de contexto solicitado para ponto {tp.refdes} em {screen_pos}")
        except Exception as e:
            logger.error(f"Erro no menu de contexto do ponto: {e}")

    def show_view_context_menu(self, scene_pos, screen_pos):
        """Mostra menu de contexto para a view"""
        try:
            # Implementar menu contextual se necessário  
            # Por enquanto, vamos apenas logar
            logger.debug(f"Menu de contexto solicitado para view em {scene_pos} (tela: {screen_pos})")
        except Exception as e:
            logger.error(f"Erro no menu de contexto da view: {e}")
        
    def show_status(self, message, type="info"):
        """Exibe mensagem de status"""
        colors = {
            "info": "#3498DB",
            "success": "#27AE60",
            "warning": "#F39C12",
            "error": "#E74C3C"
        }
        
        icon = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}
        
        self.status_label.setText(f"{icon[type]} {message}")
        self.status_label.setStyleSheet(f"color: {colors[type]}; font-size: 11px; padding: 5px;")