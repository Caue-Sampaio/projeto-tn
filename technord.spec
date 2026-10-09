# -*- mode: python ; coding: utf-8 -*-
# technord.spec — Configuração do PyInstaller para o TechNord TestFlow
#
# Uso:  pyinstaller technord.spec
#
# O resultado ficará em dist/TechNord/ com o executável TechNord.exe

import os
from pathlib import Path

block_cipher = None
ROOT = os.path.abspath('.')

# ---------------------------------------------------------------------------
# Dados que precisam ser incluídos no pacote
# ---------------------------------------------------------------------------
datas = [
    # Imagens da interface
    (os.path.join(ROOT, 'imagens'), 'imagens'),
    # Ícones
    (os.path.join(ROOT, 'TechNord.ico'), '.'),
    (os.path.join(ROOT, 'TechNord_icone.png'), '.'),
    # Configuração do osciloscópio
    (os.path.join(ROOT, 'config'), 'config'),
    # Exemplo de configuração de rede
    (os.path.join(ROOT, 'network_config.example.json'), '.'),
    # Script SQL de referência
    (os.path.join(ROOT, 'server'), 'server'),
]

# Incluir o banco SQLite inicial se existir (será copiado como template)
db_file = os.path.join(ROOT, 'db', 'teste.db')
if os.path.exists(db_file):
    datas.append((db_file, 'db'))

# ---------------------------------------------------------------------------
# Hidden imports — módulos que o PyInstaller não detecta automaticamente
# ---------------------------------------------------------------------------
hiddenimports = [
    # SQLAlchemy backends
    'sqlalchemy.dialects.sqlite',
    'sqlalchemy.dialects.postgresql',
    'sqlalchemy.dialects.postgresql.psycopg',
    # PyQt6
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.QtPrintSupport',
    'PyQt6.sip',
    # Instrumentação
    'pyvisa',
    'pyvisa_py',
    'pyusb',
    'usb',
    'usb.core',
    'usb.backend',
    'usb.backend.libusb1',
    # Gráficos
    'pyqtgraph',
    'numpy',
    # Relatórios
    'reportlab',
    'reportlab.lib',
    'reportlab.platypus',
    'reportlab.graphics',
    # Segurança
    'bcrypt',
    # Agendamento
    'schedule',
    # Módulos internos do projeto
    'db',
    'db.config',
    'db.models',
    'db.auto_migrate',
    'db.migrate_phase2',
    'db.migrations',
    'db.session_manager',
    'engine',
    'engine.runner',
    'engine.pdf_report',
    'engine.logger',
    'engine.guided_diagnostic',
    'ui',
    'ui.main_window',
    'ui.image_marker',
    'ui.plan_editor',
    'ui.plan_manager',
    'ui.placa_tab',
    'ui.placa_detalhes',
    'ui.login',
    'ui.components',
    'ui.dashboard',
    'ui.server_settings',
    'ui.system_settings',
    'ui.backup_settings',
    'ui.user_register',
    'ui.test_executor',
    'ui.marker_graphics',
    'ui.oscilloscope_panel',
    'ui.oscilloscope_display',
    'ui.guided_scope_client',
    'ui.reference_measurements',
    'ui.technical_documents',
    'utils',
    'utils.storage',
    'utils.image_paths',
    'utils.security',
    'utils.backup_manager',
]

# ---------------------------------------------------------------------------
# Análise
# ---------------------------------------------------------------------------
a = Analysis(
    [os.path.join(ROOT, 'main.py')],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'tkinter',
        'test',
        'unittest',
        'xmlrpc',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TechNord',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,           # <<< SEM janela de console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, 'TechNord.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TechNord',
)
