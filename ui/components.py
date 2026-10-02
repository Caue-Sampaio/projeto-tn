# ui/components.py
from PyQt6.QtWidgets import (
    QLabel, QPushButton, QLineEdit, QComboBox, QProgressBar,
    QFrame, QWidget, QHBoxLayout, QVBoxLayout, QFormLayout  # Adicionei QFormLayout aqui
)
from PyQt6.QtGui import QFont, QPalette, QColor
from PyQt6.QtCore import Qt, pyqtSignal
import logging

logger = logging.getLogger(__name__)

class TitleLabel(QLabel):
    """Label de título padronizado"""
    
    def __init__(self, text, level=1):
        super().__init__(text)
        
        font_sizes = {1: 18, 2: 16, 3: 14, 4: 12}
        font_weights = {1: QFont.Weight.Bold, 2: QFont.Weight.Bold, 3: QFont.Weight.Normal, 4: QFont.Weight.Normal}
        
        self.setFont(QFont("Arial", font_sizes.get(level, 14), font_weights.get(level, QFont.Weight.Normal)))
        self.setStyleSheet(f"color: #2C3E50; margin: 5px 0px;")
        self.setAlignment(Qt.AlignmentFlag.AlignLeft)

class SubtitleLabel(QLabel):
    """Label de subtítulo padronizado"""
    
    def __init__(self, text):
        super().__init__(text)
        self.setFont(QFont("Arial", 11))
        self.setStyleSheet("color: #7F8C8D; margin: 2px 0px;")
        self.setAlignment(Qt.AlignmentFlag.AlignLeft)

class PrimaryButton(QPushButton):
    """Botão primário padronizado"""
    
    clicked_safe = pyqtSignal()  # Sinal com tratamento de erro
    
    def __init__(self, text, icon=None):
        super().__init__(text)
        
        if icon:
            self.setText(f"{icon} {text}")
            
        self.setMinimumHeight(35)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
            QPushButton:pressed {
                background-color: #21618C;
            }
            QPushButton:disabled {
                background-color: #BDC3C7;
                color: #666666;
            }
        """)
        
        # Conecta com tratamento de erro
        super().clicked.connect(self._safe_click)
    
    def _safe_click(self):
        """Wrapper seguro para clicks"""
        try:
            self.clicked_safe.emit()
        except Exception as e:
            logger.error(f"Erro no botão {self.text()}: {e}")

class SecondaryButton(QPushButton):
    """Botão secundário padronizado"""
    
    def __init__(self, text, icon=None):
        super().__init__(text)
        
        if icon:
            self.setText(f"{icon} {text}")
            
        self.setMinimumHeight(35)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.setStyleSheet("""
            QPushButton {
                background-color: #95A5A6;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #7F8C8D;
            }
            QPushButton:disabled {
                background-color: #BDC3C7;
                color: #666666;
            }
        """)

class SuccessButton(QPushButton):
    """Botão de sucesso padronizado"""
    
    def __init__(self, text, icon=None):
        super().__init__(text)
        
        if icon:
            self.setText(f"{icon} {text}")
            
        self.setMinimumHeight(35)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.setStyleSheet("""
            QPushButton {
                background-color: #27AE60;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
            QPushButton:disabled {
                background-color: #BDC3C7;
                color: #666666;
            }
        """)

class DangerButton(QPushButton):
    """Botão de perigo/destrutivo padronizado"""
    
    def __init__(self, text, icon=None):
        super().__init__(text)
        
        if icon:
            self.setText(f"{icon} {text}")
            
        self.setMinimumHeight(35)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
            QPushButton:disabled {
                background-color: #BDC3C7;
                color: #666666;
            }
        """)

class OutlineButton(QPushButton):
    """Botão com contorno padronizado"""
    
    def __init__(self, text, color="#3498DB", icon=None):
        super().__init__(text)
        
        if icon:
            self.setText(f"{icon} {text}")
            
        self.setMinimumHeight(35)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {color};
                border: 2px solid {color};
                border-radius: 5px;
                padding: 6px 16px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {color};
                color: white;
            }}
            QPushButton:disabled {{
                background-color: transparent;
                color: #BDC3C7;
                border-color: #BDC3C7;
            }}
        """)

class ValidatedLineEdit(QLineEdit):
    """Campo de entrada com validação integrada"""
    
    validation_changed = pyqtSignal(bool)  # Emite estado da validação
    
    def __init__(self, placeholder="", validator=None):
        super().__init__()
        self.placeholder = placeholder
        self.validator = validator
        self.valid = True
        
        self.setPlaceholderText(placeholder)
        self.textChanged.connect(self._validate)
        
        self.setStyleSheet("""
            QLineEdit {
                border: 2px solid #BDC3C7;
                border-radius: 5px;
                padding: 8px 12px;
                font-size: 14px;
                background-color: white;
                selection-background-color: #3498DB;
            }
            QLineEdit:focus {
                border-color: #3498DB;
                background-color: #F8F9FA;
            }
            QLineEdit[valid="true"] {
                border-color: #27AE60;
            }
            QLineEdit[valid="false"] {
                border-color: #E74C3C;
                background-color: #FDEDEC;
            }
        """)
    
    def _validate(self):
        """Executa validação"""
        if self.validator:
            self.valid = self.validator(self.text())
        else:
            self.valid = bool(self.text().strip())
            
        self.setProperty("valid", "true" if self.valid else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        
        self.validation_changed.emit(self.valid)
    
    def set_validator(self, validator):
        """Define validador personalizado"""
        self.validator = validator
        self._validate()
    
    def is_valid(self):
        """Retorna estado da validação"""
        return self.valid

class IconComboBox(QComboBox):
    """ComboBox com suporte a ícones"""
    
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(35)
        
        self.setStyleSheet("""
            QComboBox {
                border: 2px solid #BDC3C7;
                border-radius: 5px;
                padding: 8px 12px;
                font-size: 14px;
                background-color: white;
                min-width: 120px;
            }
            QComboBox:focus {
                border-color: #3498DB;
            }
            QComboBox::drop-down {
                border: none;
                width: 25px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #7F8C8D;
                width: 0px;
                height: 0px;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #BDC3C7;
                border-radius: 5px;
                background-color: white;
                selection-background-color: #3498DB;
                selection-color: white;
            }
        """)
    
    def add_icon_item(self, text, icon, data=None):
        """Adiciona item com ícone"""
        self.addItem(f"{icon} {text}", data)
    
    def add_items_with_icons(self, items):
        """Adiciona múltiplos items com ícones"""
        for text, icon, data in items:
            self.add_icon_item(text, icon, data)

class StyledProgressBar(QProgressBar):
    """Barra de progresso estilizada"""
    
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(8)
        self.setTextVisible(False)
        
        self.setStyleSheet("""
            QProgressBar {
                border: none;
                background-color: #ECF0F1;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #3498DB;
                border-radius: 4px;
            }
        """)
    
    def set_progress_color(self, color):
        """Define cor da barra de progresso"""
        self.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background-color: #ECF0F1;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 4px;
            }}
        """)

class StatusLabel(QLabel):
    """Label para mostrar status do sistema"""
    
    def __init__(self):
        super().__init__("Pronto")
        self.setStyleSheet("""
            QLabel {
                color: #7F8C8D;
                font-size: 11px;
                padding: 5px;
                background-color: #F8F9FA;
                border-radius: 3px;
            }
        """)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
    
    def set_status(self, message, type="info"):
        """Define mensagem de status com tipo"""
        colors = {
            "info": "#3498DB",
            "success": "#27AE60",
            "warning": "#F39C12",
            "error": "#E74C3C"
        }
        
        icons = {
            "info": "ℹ️",
            "success": "✅", 
            "warning": "⚠️",
            "error": "❌"
        }
        
        self.setText(f"{icons[type]} {message}")
        self.setStyleSheet(f"""
            QLabel {{
                color: {colors[type]};
                font-size: 11px;
                padding: 5px;
                background-color: #F8F9FA;
                border-radius: 3px;
            }}
        """)

class CardWidget(QFrame):
    """Widget tipo card para agrupar conteúdo"""
    
    def __init__(self, title=None):
        super().__init__()
        
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #BDC3C7;
                border-radius: 8px;
                padding: 15px;
            }
        """)
        
        self.layout = QVBoxLayout()
        self.layout.setSpacing(10)
        self.layout.setContentsMargins(15, 15, 15, 15)
        
        if title:
            title_label = TitleLabel(title, level=3)
            self.layout.addWidget(title_label)
            
            # Separador
            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFrameShadow(QFrame.Shadow.Sunken)
            separator.setStyleSheet("background-color: #ECF0F1;")
            self.layout.addWidget(separator)
        
        self.setLayout(self.layout)
    
    def add_widget(self, widget):
        """Adiciona widget ao card"""
        self.layout.addWidget(widget)
    
    def add_layout(self, layout):
        """Adiciona layout ao card"""
        self.layout.addLayout(layout)

class Toolbar(QWidget):
    """Barra de ferramentas padronizada"""
    
    def __init__(self):
        super().__init__()
        
        self.layout = QHBoxLayout()
        self.layout.setSpacing(8)
        self.layout.setContentsMargins(10, 5, 10, 5)
        
        self.setStyleSheet("""
            QWidget {
                background-color: #2C3E50;
                border-bottom: 1px solid #34495E;
            }
        """)
        
        self.setLayout(self.layout)
        self.setFixedHeight(45)
    
    def add_button(self, button):
        """Adiciona botão à toolbar"""
        self.layout.addWidget(button)
    
    def add_stretch(self):
        """Adiciona espaço elástico"""
        self.layout.addStretch()
    
    def add_separator(self):
        """Adiciona separador vertical"""
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("background-color: #34495E;")
        separator.setFixedWidth(1)
        self.layout.addWidget(separator)

class Sidebar(QWidget):
    """Barra lateral padronizada"""
    
    def __init__(self, width=250):
        super().__init__()
        
        self.setFixedWidth(width)
        self.layout = QVBoxLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.setStyleSheet("""
            QWidget {
                background-color: #34495E;
                color: white;
            }
        """)
        
        self.setLayout(self.layout)
    
    def add_section(self, title):
        """Adiciona seção à sidebar"""
        section_label = QLabel(title)
        section_label.setStyleSheet("""
            QLabel {
                color: #BDC3C7;
                font-weight: bold;
                font-size: 11px;
                padding: 15px 15px 5px 15px;
                text-transform: uppercase;
            }
        """)
        self.layout.addWidget(section_label)
    
    def add_item(self, text, icon=None, callback=None):
        """Adiciona item à sidebar"""
        item_button = QPushButton(f"  {icon} {text}" if icon else f"  {text}")
        item_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #ECF0F1;
                border: none;
                text-align: left;
                padding: 12px 15px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2C3E50;
            }
            QPushButton:pressed {
                background-color: #1ABC9C;
            }
        """)
        
        if callback:
            item_button.clicked.connect(callback)
            
        self.layout.addWidget(item_button)
    
    def add_stretch(self):
        """Adiciona espaço elástico"""
        self.layout.addStretch()

class LoadingOverlay(QWidget):
    """Overlay de carregamento"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        if parent:
            self.setGeometry(parent.rect())
            
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(52, 73, 94, 0.8);
            }
        """)
        
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Spinner
        self.spinner = QLabel("⏳")
        self.spinner.setStyleSheet("font-size: 32px; color: white;")
        self.spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Texto
        self.text = QLabel("Carregando...")
        self.text.setStyleSheet("color: white; font-size: 14px; margin-top: 10px;")
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(self.spinner)
        layout.addWidget(self.text)
        
        self.setLayout(layout)
        self.hide()
    
    def set_text(self, text):
        """Define texto do overlay"""
        self.text.setText(text)
    
    def show_overlay(self, text="Carregando..."):
        """Mostra overlay"""
        self.set_text(text)
        self.show()
    
    def hide_overlay(self):
        """Esconde overlay"""
        self.hide()

# Validadores pré-definidos
class Validators:
    """Coleção de validadores úteis"""
    
    @staticmethod
    def numeric(text):
        """Valida se é numérico"""
        try:
            if text.strip():
                float(text)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def integer(text):
        """Valida se é inteiro"""
        try:
            if text.strip():
                int(text)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def voltage(text):
        """Valida valor de tensão"""
        try:
            if text.strip():
                value = float(text)
                return 0 <= value <= 1000  # Limite razoável para tensão
            return True
        except ValueError:
            return False
    
    @staticmethod
    def current(text):
        """Valida valor de corrente"""
        try:
            if text.strip():
                value = float(text)
                return 0 <= value <= 100  # Limite razoável para corrente
            return True
        except ValueError:
            return False
    
    @staticmethod
    def frequency(text):
        """Valida valor de frequência"""
        try:
            if text.strip():
                value = float(text)
                return 0 <= value <= 1000000  # 1MHz limite
            return True
        except ValueError:
            return False
    
    @staticmethod
    def not_empty(text):
        """Valida que não está vazio"""
        return bool(text.strip())
    
    @staticmethod
    def serial_number(text):
        """Valida número de série"""
        return bool(text.strip()) and len(text.strip()) >= 3

# Funções úteis para UI
class UIHelpers:
    """Funções auxiliares para interface"""
    
    @staticmethod
    def create_form_layout(labels_and_widgets, spacing=10):
        """Cria layout de formulário rapidamente"""
        layout = QFormLayout()  # ✅ AGORA CORRETO - QFormLayout importado
        layout.setSpacing(spacing)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        for label, widget in labels_and_widgets:
            layout.addRow(label, widget)
            
        return layout
    
    @staticmethod
    def create_button_group(buttons, orientation=Qt.Orientation.Horizontal):
        """Cria grupo de botões organizados"""
        if orientation == Qt.Orientation.Horizontal:
            layout = QHBoxLayout()
        else:
            layout = QVBoxLayout()
            
        layout.setSpacing(5)
        
        for button in buttons:
            layout.addWidget(button)
            
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    
    @staticmethod
    def create_separator(orientation=Qt.Orientation.Horizontal):
        """Cria separador padronizado"""
        separator = QFrame()
        
        if orientation == Qt.Orientation.Horizontal:
            separator.setFrameShape(QFrame.Shape.HLine)
        else:
            separator.setFrameShape(QFrame.Shape.VLine)
            
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("color: #BDC3C7;")
        
        return separator
    
    @staticmethod
    def center_window(window):
        """Centraliza janela na tela"""
        screen_geometry = window.screen().availableGeometry()
        window_geometry = window.frameGeometry()
        center_point = screen_geometry.center()
        window_geometry.moveCenter(center_point)
        window.move(window_geometry.topLeft())