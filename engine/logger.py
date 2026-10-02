# engine/logger.py
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import json

class CustomJSONFormatter(logging.Formatter):
    """Formatador personalizado para logs em JSON"""
    
    def format(self, record):
        """Formata o registro de log como JSON"""
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'message': record.getMessage(),
            'thread': record.threadName,
            'process': record.processName
        }
        
        # Adiciona informações de exceção se houver
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # Adiciona dados extras se existirem
        if hasattr(record, 'extra_data'):
            log_entry['extra_data'] = record.extra_data
            
        return json.dumps(log_entry, ensure_ascii=False)

class ColoredFormatter(logging.Formatter):
    """Formatador com cores para console"""
    
    # Cores ANSI
    COLORS = {
        'DEBUG': '\033[36m',      # Ciano
        'INFO': '\033[32m',       # Verde
        'WARNING': '\033[33m',    # Amarelo
        'ERROR': '\033[31m',      # Vermelho
        'CRITICAL': '\033[41m',   # Vermelho com fundo
        'RESET': '\033[0m'        # Reset
    }
    
    def format(self, record):
        """Formata o registro de log com cores"""
        log_message = super().format(record)
        levelname = record.levelname
        
        if levelname in self.COLORS:
            return f"{self.COLORS[levelname]}{log_message}{self.COLORS['RESET']}"
        return log_message

class TestSystemLogger:
    """Logger principal do sistema de teste"""
    
    def __init__(self):
        self.log_dir = Path("logs")
        self.setup_logging()
    
    def setup_logging(self):
        """Configura o sistema de logging completo"""
        # Cria diretório de logs se não existir
        self.log_dir.mkdir(exist_ok=True)
        
        # Configura logging root
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[]
        )
        
        # Remove handlers padrão
        logging.getLogger().handlers.clear()
        
        # Configura logger principal
        self.logger = logging.getLogger('TestSystem')
        self.logger.setLevel(logging.INFO)
        
        # Evita propagação para root logger
        self.logger.propagate = False
        
        # Adiciona handlers
        self._add_console_handler()
        self._add_file_handler()
        self._add_error_file_handler()
        self._add_json_handler()
        
        # Configura loggers de terceiros
        self._configure_third_party_loggers()
    
    def _add_console_handler(self):
        """Adiciona handler para console com cores"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        formatter = ColoredFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
    
    def _add_file_handler(self):
        """Adiciona handler para arquivo com rotação"""
        log_file = self.log_dir / f"test_system_{datetime.now().strftime('%Y%m')}.log"
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
    
    def _add_error_file_handler(self):
        """Adiciona handler separado para erros"""
        error_file = self.log_dir / "errors.log"
        
        error_handler = RotatingFileHandler(
            error_file,
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s\n%(exc_info)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        error_handler.setFormatter(formatter)
        self.logger.addHandler(error_handler)
    
    def _add_json_handler(self):
        """Adiciona handler para logs em JSON (para análise)"""
        json_file = self.log_dir / "system_events.json"
        
        json_handler = TimedRotatingFileHandler(
            json_file,
            when='midnight',
            interval=1,
            backupCount=7,
            encoding='utf-8'
        )
        json_handler.setLevel(logging.INFO)
        
        formatter = CustomJSONFormatter()
        json_handler.setFormatter(formatter)
        self.logger.addHandler(json_handler)
    
    def _configure_third_party_loggers(self):
        """Configura loggers de bibliotecas de terceiros"""
        third_party_loggers = [
            'sqlalchemy.engine',
            'PIL',
            'reportlab'
        ]
        
        for logger_name in third_party_loggers:
            logging.getLogger(logger_name).setLevel(logging.WARNING)
    
    def log_test_start(self, user, board, plan):
        """Registra início de teste"""
        self.logger.info(
            "Início de teste - Usuário: %s, Placa: %s, Plano: %s",
            user.username, board.serial_number, plan.name,
            extra={'extra_data': {
                'event_type': 'test_start',
                'user': user.username,
                'board_serial': board.serial_number,
                'plan_name': plan.name,
                'board_model': f"{board.model} v{board.version}"
            }}
        )
    
    def log_test_completion(self, test_run, measurements):
        """Registra conclusão de teste"""
        passed_count = sum(1 for m in measurements if m.passed is True)
        total_count = len(measurements)
        
        self.logger.info(
            "Teste concluído - Placa: %s, Status: %s, Aprovação: %d/%d",
            test_run.board.serial_number, test_run.status, passed_count, total_count,
            extra={'extra_data': {
                'event_type': 'test_completion',
                'board_serial': test_run.board.serial_number,
                'status': test_run.status,
                'passed_measurements': passed_count,
                'total_measurements': total_count,
                'success_rate': (passed_count / total_count * 100) if total_count > 0 else 0,
                'duration': str(test_run.end_time - test_run.start_time) if test_run.end_time else None
            }}
        )
    
    def log_measurement(self, step, value, passed, instrument=None):
        """Registra medição individual"""
        self.logger.debug(
            "Medição - %s: %s %s → %s",
            step.description, value, step.unit, "APROVADO" if passed else "REPROVADO",
            extra={'extra_data': {
                'event_type': 'measurement',
                'step_description': step.description,
                'step_unit': step.unit,
                'desired_value': step.desired_value,
                'tolerance': step.tolerance,
                'measured_value': value,
                'passed': passed,
                'instrument': instrument,
                'test_point': step.test_point.refdes if step.test_point else None
            }}
        )
    
    def log_user_action(self, user, action, details=None):
        """Registra ação do usuário"""
        self.logger.info(
            "Ação do usuário - %s: %s",
            user.username, action,
            extra={'extra_data': {
                'event_type': 'user_action',
                'user': user.username,
                'user_role': user.role,
                'action': action,
                'details': details or {}
            }}
        )
    
    def log_system_event(self, event_type, description, details=None):
        """Registra evento do sistema"""
        self.logger.info(
            "Evento do sistema - %s: %s",
            event_type, description,
            extra={'extra_data': {
                'event_type': 'system_event',
                'system_event_type': event_type,
                'description': description,
                'details': details or {}
            }}
        )
    
    def log_error(self, error_type, description, exception=None):
        """Registra erro do sistema"""
        extra_data = {
            'event_type': 'error',
            'error_type': error_type,
            'description': description
        }
        
        if exception:
            extra_data['exception_type'] = type(exception).__name__
            extra_data['exception_message'] = str(exception)
        
        self.logger.error(
            "ERRO - %s: %s",
            error_type, description,
            exc_info=exception is not None,
            extra={'extra_data': extra_data}
        )
    
    def log_database_operation(self, operation, table, details=None):
        """Registra operação no banco de dados"""
        self.logger.debug(
            "Operação no BD - %s em %s",
            operation, table,
            extra={'extra_data': {
                'event_type': 'database_operation',
                'operation': operation,
                'table': table,
                'details': details or {}
            }}
        )
    
    def get_log_file_paths(self):
        """Retorna caminhos dos arquivos de log"""
        return {
            'main_log': str(self.log_dir / f"test_system_{datetime.now().strftime('%Y%m')}.log"),
            'error_log': str(self.log_dir / "errors.log"),
            'json_log': str(self.log_dir / "system_events.json")
        }
    
    def cleanup_old_logs(self, days_to_keep=30):
        """Remove logs antigos"""
        try:
            cutoff_time = datetime.now().timestamp() - (days_to_keep * 24 * 60 * 60)
            
            for log_file in self.log_dir.glob("*.log"):
                if log_file.stat().st_mtime < cutoff_time:
                    log_file.unlink()
                    self.logger.info("Log antigo removido: %s", log_file.name)
            
            for log_file in self.log_dir.glob("*.json"):
                if log_file.stat().st_mtime < cutoff_time:
                    log_file.unlink()
                    self.logger.info("Log JSON antigo removido: %s", log_file.name)
                    
        except Exception as e:
            self.logger.error("Erro ao limpar logs antigos: %s", e)

# Instância global do logger
_system_logger = None

def setup_logging():
    """Configura o sistema de logging (função de conveniência)"""
    global _system_logger
    _system_logger = TestSystemLogger()
    return _system_logger.logger

def get_logger(name=None):
    """Obtém logger para uso em outros módulos"""
    if name:
        return logging.getLogger(name)
    return logging.getLogger('TestSystem')

# Funções de conveniência para logging rápido
def log_info(message, *args, **kwargs):
    """Log rápido de informação"""
    logger = get_logger()
    logger.info(message, *args, **kwargs)

def log_warning(message, *args, **kwargs):
    """Log rápido de aviso"""
    logger = get_logger()
    logger.warning(message, *args, **kwargs)

def log_error(message, *args, **kwargs):
    """Log rápido de erro"""
    logger = get_logger()
    logger.error(message, *args, **kwargs)

def log_debug(message, *args, **kwargs):
    """Log rápido de debug"""
    logger = get_logger()
    logger.debug(message, *args, **kwargs)

# Context manager para timing de operações
class Timer:
    """Context manager para medir tempo de execução"""
    
    def __init__(self, operation_name):
        self.operation_name = operation_name
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        log_debug("Iniciando: %s", self.operation_name)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        if exc_type:
            log_error("Falha em %s após %.2fs: %s", 
                     self.operation_name, duration, exc_val)
        else:
            log_debug("Concluído: %s em %.2fs", 
                     self.operation_name, duration)

# Decorator para logging de funções
def log_function_call(func):
    """Decorator para logar chamadas de função"""
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        logger.debug("Chamando função: %s", func.__name__)
        
        try:
            result = func(*args, **kwargs)
            logger.debug("Função concluída: %s", func.__name__)
            return result
        except Exception as e:
            logger.error("Erro em %s: %s", func.__name__, e)
            raise
    
    return wrapper

# FUNÇÃO QUE ESTAVA FALTANDO - ADICIONADA AGORA
def log_user_action(user, action, details=None):
    """
    Registra ação do usuário no sistema
    Função de conveniência para uso em outros módulos
    """
    logger = get_logger()
    logger.info(
        "Ação do usuário - %s: %s",
        user.username if user else "Sistema", action,
        extra={'extra_data': {
            'event_type': 'user_action',
            'user': user.username if user else "Sistema",
            'user_role': user.role if user else "Sistema",
            'action': action,
            'details': details or {}
        }}
    )