# db/config.py
import os
from pathlib import Path

# Base directory do projeto (raiz)
BASE_DIR = Path(__file__).resolve().parent.parent

# Cria diretório db se não existir
DB_DIR = BASE_DIR / "db"
DB_DIR.mkdir(exist_ok=True)

# URL do banco de dados
DATABASE_URL = f"sqlite:///{DB_DIR / 'teste.db'}"

# Configurações do banco
DB_CONFIG = {
    "echo": False,  # Define como True para ver SQL no console (apenas desenvolvimento)
    "pool_pre_ping": True,  # Verifica conexão antes de usar
    "connect_args": {
        "check_same_thread": False,  # Para SQLite
        "timeout": 30  # Timeout de 30 segundos
    }
}

# Configurações da aplicação
APP_CONFIG = {
    "app_name": "Sistema de Teste de Placas Eletrônicas",
    "version": "2.0.0",
    "company": "Laboratório Técnico",
    "backup_interval_days": 7,
    "max_backup_files": 10,
    "auto_save_reports": True
}

# Configurações de relatórios
REPORT_CONFIG = {
    "default_author": "Sistema de Teste Automático",
    "company_logo": None,  # Caminho para logo da empresa
    "default_margins": {
        "top": 2.0,
        "bottom": 2.0,
        "left": 2.0,
        "right": 2.0
    }
}

# Configurações de segurança
SECURITY_CONFIG = {
    "session_timeout_minutes": 120,
    "max_login_attempts": 3,
    "password_min_length": 4,
    "require_strong_passwords": False  # Para desenvolvimento
}

def get_database_path():
    """Retorna o caminho absoluto do arquivo do banco de dados"""
    return str(DB_DIR / "teste.db")

def ensure_directories():
    """Garante que todos os diretórios necessários existam"""
    directories = [
        "db",
        "backups", 
        "reports",
        "logs",
        "temp"
    ]
    
    for directory in directories:
        (BASE_DIR / directory).mkdir(exist_ok=True)
    
    print("Diretórios verificados/criados com sucesso")

# Inicializa diretórios ao importar
ensure_directories()