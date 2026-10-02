# db/session_manager.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from contextlib import contextmanager
import logging
from typing import Generator, Optional
import time
from threading import Lock
from db.config import DATABASE_URL, DB_CONFIG

logger = logging.getLogger(__name__)

class SessionManager:
    """
    Gerenciador avançado de sessões do banco de dados
    
    Features:
    - Pool de conexões gerenciado
    - Retry automático em falhas
    - Controle de transações
    - Monitoramento de performance
    - Cleanup automático
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.engine = None
        self.SessionLocal = None
        self.active_sessions = 0
        self.total_queries = 0
        self._setup_engine()
        self._initialized = True
        
        logger.info("✅ SessionManager inicializado")
    
    def _setup_engine(self):
        """Configura o engine do SQLAlchemy com opções avançadas"""
        try:
            # Configurações avançadas do engine
            engine_config = {
                **DB_CONFIG,
                "pool_pre_ping": True,  # Verifica conexão antes de usar
                "pool_recycle": 3600,   # Recicla conexões a cada 1 hora
            }
            
            # Remove pool configs that are not supported by SQLite
            if DATABASE_URL.startswith("sqlite"):
                from sqlalchemy.pool import NullPool
                engine_config["poolclass"] = NullPool
            else:
                engine_config.update({
                    "pool_size": 10,        # Tamanho máximo do pool
                    "max_overflow": 20,     # Conexões extras permitidas
                    "pool_timeout": 30,     # Timeout para obter conexão
                    "echo_pool": False,     # Log de atividades do pool
                })
            
            self.engine = create_engine(DATABASE_URL, **engine_config)
            self.SessionLocal = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False
            )
            
            # Testa a conexão
            self._test_connection()
            
        except Exception as e:
            logger.error(f"❌ Erro ao configurar engine: {e}")
            raise
    
    def _test_connection(self):
        """Testa a conexão com o banco de dados"""
        from sqlalchemy import text
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("✅ Conexão com banco de dados estabelecida")
        except OperationalError as e:
            logger.error(f"❌ Falha na conexão com o banco: {e}")
            raise
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Context manager para obter sessão do banco
        
        Usage:
        with session_manager.get_session() as session:
            # usar session aqui
            user = session.query(User).first()
        """
        session = None
        start_time = time.time()
        
        try:
            session = self.SessionLocal()
            self.active_sessions += 1
            self.total_queries += 1
            
            logger.debug(f"📊 Sessão criada. Ativas: {self.active_sessions}")
            
            yield session
            
            # Commit se tudo correu bem
            session.commit()
            logger.debug("✅ Transação commitada com sucesso")
            
        except SQLAlchemyError as e:
            if session:
                session.rollback()
                logger.error(f"❌ Erro na transação - Rollback realizado: {e}")
            raise
            
        except Exception as e:
            if session:
                session.rollback()
                logger.error(f"❌ Erro inesperado - Rollback realizado: {e}")
            raise
            
        finally:
            if session:
                session.close()
                self.active_sessions -= 1
                
                duration = time.time() - start_time
                logger.debug(f"📊 Sessão fechada. Duração: {duration:.3f}s. Ativas: {self.active_sessions}")
    
    def get_session_direct(self) -> Session:
        """
        Obtém sessão diretamente (gerenciamento manual necessário)
        
        Usage:
        session = session_manager.get_session_direct()
        try:
            # operações com session
            session.commit()
        except:
            session.rollback()
            raise
        finally:
            session.close()
        """
        session = self.SessionLocal()
        self.active_sessions += 1
        logger.debug(f"📊 Sessão direta criada. Ativas: {self.active_sessions}")
        return session
    
    def close_session(self, session: Session):
        """Fecha sessão manualmente"""
        if session:
            try:
                session.close()
                self.active_sessions -= 1
                logger.debug(f"📊 Sessão fechada manualmente. Ativas: {self.active_sessions}")
            except Exception as e:
                logger.error(f"❌ Erro ao fechar sessão: {e}")
    
    @contextmanager
    def transaction(self, session: Session) -> Generator[None, None, None]:
        """
        Context manager para transações explícitas
        
        Usage:
        with session_manager.get_session() as session:
            with session_manager.transaction(session):
                # operações na transação
                session.add(some_object)
        """
        try:
            yield
            session.commit()
            logger.debug("✅ Transação explícita commitada")
            
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Erro na transação explícita - Rollback: {e}")
            raise
    
    def execute_with_retry(self, operation, max_retries: int = 3, delay: float = 1.0):
        """
        Executa operação com retry automático em falhas
        
        Args:
            operation: Função a ser executada
            max_retries: Número máximo de tentativas
            delay: Delay entre tentativas (segundos)
        """
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                return operation()
                
            except OperationalError as e:
                last_exception = e
                logger.warning(f"⚠️  Tentativa {attempt + 1}/{max_retries} falhou: {e}")
                
                if attempt < max_retries - 1:
                    time.sleep(delay * (attempt + 1))  # Backoff exponencial
                    continue
                    
            except SQLAlchemyError as e:
                logger.error(f"❌ Erro de banco não recuperável: {e}")
                raise
        
        # Se todas as tentativas falharam
        logger.error(f"❌ Todas as {max_retries} tentativas falharam")
        raise last_exception
    
    def bulk_operation(self, operations: list, batch_size: int = 1000):
        """
        Executa operações em lote para melhor performance
        
        Args:
            operations: Lista de operações (funções que recebem session)
            batch_size: Tamanho do lote
        """
        total_ops = len(operations)
        logger.info(f"🔄 Iniciando operação em lote: {total_ops} operações")
        
        with self.get_session() as session:
            for i, operation in enumerate(operations, 1):
                try:
                    operation(session)
                    
                    # Commit periódico para evitar locks longos
                    if i % batch_size == 0:
                        session.commit()
                        logger.debug(f"📦 Lote {i//batch_size} commitado ({i}/{total_ops})")
                        
                except Exception as e:
                    logger.error(f"❌ Erro na operação {i}: {e}")
                    session.rollback()
                    raise
            
            # Commit final
            session.commit()
            logger.info(f"✅ Operação em lote concluída: {total_ops} operações")
    
    def get_database_stats(self) -> dict:
        """Retorna estatísticas do banco e sessões"""
        stats = {
            "active_sessions": self.active_sessions,
            "total_queries": self.total_queries,
            "pool_status": None,
            "database_size": None
        }
        
        try:
            # Estatísticas do pool
            if hasattr(self.engine.pool, "status"):
                stats["pool_status"] = self.engine.pool.status()
            
            # Tamanho do banco (SQLite específico)
            if "sqlite" in DATABASE_URL:
                with self.engine.connect() as conn:
                    result = conn.execute("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
                    stats["database_size"] = result.scalar()
                    
        except Exception as e:
            logger.warning(f"⚠️  Não foi possível obter estatísticas completas: {e}")
        
        return stats
    
    def health_check(self) -> dict:
        """Verifica saúde do banco e conexões"""
        health = {
            "database_connected": False,
            "active_sessions": self.active_sessions,
            "pool_healthy": False,
            "response_time": None
        }
        
        try:
            start_time = time.time()
            
            with self.engine.connect() as conn:
                result = conn.execute("SELECT 1")
                health["database_connected"] = result.scalar() == 1
            
            health["response_time"] = time.time() - start_time
            health["pool_healthy"] = self.active_sessions < 50  # Limite razoável
            
            logger.debug(f"❤️  Health check: {health}")
            
        except Exception as e:
            logger.error(f"❌ Health check falhou: {e}")
            health["database_connected"] = False
        
        return health
    
    def cleanup(self):
        """Limpeza e finalização do gerenciador"""
        try:
            if self.engine:
                self.engine.dispose()
                logger.info("✅ Engine do banco finalizado")
                
            if self.active_sessions > 0:
                logger.warning(f"⚠️  {self.active_sessions} sessões ainda ativas durante cleanup")
                
        except Exception as e:
            logger.error(f"❌ Erro durante cleanup: {e}")
    
    def backup_database(self, backup_path: str = None):
        """
        Cria backup do banco de dados (SQLite específico)
        
        Args:
            backup_path: Caminho para o backup (opcional)
        """
        if "sqlite" not in DATABASE_URL:
            logger.warning("⚠️  Backup automático só disponível para SQLite")
            return None
        
        try:
            import shutil
            from datetime import datetime
            import os
            
            if not backup_path:
                backup_dir = "backups"
                os.makedirs(backup_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = os.path.join(backup_dir, f"db_backup_{timestamp}.db")
            
            # Fecha todas as conexões ativas temporariamente
            self.engine.dispose()
            
            # Copia arquivo do banco
            db_path = DATABASE_URL.replace("sqlite:///", "")
            shutil.copy2(db_path, backup_path)
            
            # Reconfigura engine
            self._setup_engine()
            
            logger.info(f"✅ Backup criado: {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"❌ Erro ao criar backup: {e}")
            # Reconfigura engine em caso de erro
            self._setup_engine()
            return None


# Instância global para uso em toda aplicação
session_manager = SessionManager()

# Funções de conveniência para uso rápido
def get_db_session() -> Generator[Session, None, None]:
    """Função de conveniência para obter sessão"""
    return session_manager.get_session()

def execute_in_session(operation):
    """
    Executa operação em uma sessão gerenciada
    
    Usage:
    result = execute_in_session(lambda session: session.query(User).all())
    """
    with session_manager.get_session() as session:
        return operation(session)

# Decorator para funções que precisam de sessão
def with_database_session(func):
    """
    Decorator que injeta sessão do banco como primeiro argumento
    
    Usage:
    @with_database_session
    def get_users(session, filters=None):
        return session.query(User).filter_by(**filters).all()
    """
    def wrapper(*args, **kwargs):
        with session_manager.get_session() as session:
            return func(session, *args, **kwargs)
    return wrapper

# Exemplo de uso das diferentes formas
class ExampleUsage:
    """Exemplos de como usar o SessionManager"""
    
    @staticmethod
    def example_context_manager():
        """Uso com context manager (recomendado)"""
        with session_manager.get_session() as session:
            # Sua lógica com o banco aqui
            # from db.models import User
            # users = session.query(User).all()
            pass
    
    @staticmethod
    def example_direct_session():
        """Uso com sessão direta (controle manual)"""
        session = session_manager.get_session_direct()
        try:
            # Sua lógica com o banco aqui
            session.commit()
        except:
            session.rollback()
            raise
        finally:
            session_manager.close_session(session)
    
    @staticmethod
    @with_database_session
    def example_decorator(session, user_id: int):
        """Uso com decorator"""
        # from db.models import User
        # return session.get(User, user_id)
        pass
    
    @staticmethod
    def example_transaction():
        """Uso com transação explícita"""
        with session_manager.get_session() as session:
            with session_manager.transaction(session):
                # Operações que devem ser atômicas
                # session.add(object1)
                # session.add(object2)
                pass
    
    @staticmethod
    def example_bulk_operations():
        """Uso com operações em lote"""
        def create_user_operation(username):
            def operation(session):
                # from db.models import User
                # session.add(User(username=username))
                pass
            return operation
        
        operations = [create_user_operation(f"user_{i}") for i in range(100)]
        session_manager.bulk_operation(operations, batch_size=50)


if __name__ == "__main__":
    # Teste básico do SessionManager
    logging.basicConfig(level=logging.DEBUG)
    
    print("🧪 Testando SessionManager...")
    
    # Teste de saúde
    health = session_manager.health_check()
    print(f"❤️  Health Check: {health}")
    
    # Teste de sessão
    with session_manager.get_session() as session:
        print("✅ Sessão criada com sucesso")
    
    # Estatísticas
    stats = session_manager.get_database_stats()
    print(f"📊 Estatísticas: {stats}")
    
    print("🎉 SessionManager testado com sucesso!")