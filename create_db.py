# create_db.py
from sqlalchemy import create_engine
from db.models import Base
from db.config import DATABASE_URL, DB_CONFIG
import logging
import os
from pathlib import Path

# Configura logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_database(drop_existing=False):
    """
    Cria o banco de dados e todas as tabelas
    
    Args:
        drop_existing: Se True, apaga todas as tabelas existentes primeiro
    """
    try:
        # Garante que o diretório existe
        db_dir = Path("db")
        db_dir.mkdir(exist_ok=True)
        
        # Cria engine
        engine = create_engine(DATABASE_URL, **DB_CONFIG)
        
        if drop_existing:
            logger.warning("🗑️  Apagando todas as tabelas existentes...")
            Base.metadata.drop_all(engine)
            logger.info("✅ Tabelas existentes removidas")
        
        # Cria todas as tabelas
        logger.info("🔄 Criando tabelas do banco de dados...")
        Base.metadata.create_all(engine)
        
        # Verifica tabelas criadas
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        logger.info("✅ Banco de dados criado com sucesso!")
        logger.info(f"📊 Tabelas criadas: {len(tables)}")
        
        for table in tables:
            logger.info(f"   • {table}")
            
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro ao criar banco de dados: {e}")
        return False

def verify_database():
    """Verifica se o banco de dados está acessível"""
    try:
        engine = create_engine(DATABASE_URL, **DB_CONFIG)
        
        # Testa conexão
        with engine.connect() as conn:
            pass
            
        # Verifica tabelas
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        expected_tables = {
            'users', 'board_models', 'board_units', 'board_images',
            'test_points', 'test_plans', 'test_steps', 'test_runs', 'measurements'
        }
        
        missing_tables = expected_tables - set(tables)
        
        if missing_tables:
            logger.warning(f"⚠️  Tabelas faltando: {missing_tables}")
            return False
        else:
            logger.info("✅ Banco de dados verificado com sucesso")
            return True
            
    except Exception as e:
        logger.error(f"❌ Erro ao verificar banco de dados: {e}")
        return False

def create_sample_data():
    """Cria dados de exemplo para teste"""
    try:
        from sqlalchemy.orm import Session
        from db.models import User, BoardModel, BoardUnit, TestPoint
        
        engine = create_engine(DATABASE_URL, **DB_CONFIG)
        session = Session(engine)
        
        # Verifica se já existem dados
        if session.query(User).first():
            logger.info("ℹ️  Banco de dados já contém dados, pulando criação de amostra")
            return True
        
        logger.info("🎨 Criando dados de exemplo...")
        
        from utils.security import hash_password
        # Cria usuários
        admin = User(username="admin", password_hash=hash_password("admin123"), role="admin")
        operator = User(username="operator", password_hash=hash_password("op123"), role="operator")
        session.add_all([admin, operator])
        
        # Cria modelo de placa
        model_x1 = BoardModel(name="Placa X1", version="1.0", description="Placa de demonstração principal")
        session.add(model_x1)
        
        # Cria placas
        board1 = BoardUnit(
            name="Placa de Teste Principal",
            model="X1",
            version="1.0",
            serial_number="SN001",
            board_model=model_x1,
            operator=admin
        )
        
        board2 = BoardUnit(
            name="Placa de Desenvolvimento",
            model="X1", 
            version="1.0",
            serial_number="SN002",
            board_model=model_x1,
            operator=operator
        )
        session.add_all([board1, board2])
        
        # Cria pontos de teste
        points_data = [
            ("TP1", 100, 100, 3.3, 0.1),
            ("TP2", 200, 150, 5.0, 0.2),
            ("GND", 150, 200, 0.0, 0.0),
            ("VCC", 250, 100, 12.0, 0.5),
        ]
        
        for refdes, x, y, voltage, tolerance in points_data:
            point = TestPoint(
                board=board1,
                refdes=refdes,
                x=x,
                y=y,
                expected_voltage_v=voltage,
                tolerance_voltage_v=tolerance
            )
            session.add(point)
        
        session.commit()
        logger.info("✅ Dados de exemplo criados com sucesso")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro ao criar dados de exemplo: {e}")
        session.rollback()
        return False

def main():
    """Função principal"""
    print("=" * 50)
    print("🛠️  Criador de Banco de Dados - Sistema de Teste")
    print("=" * 50)
    
    # Pergunta se deve recriar o banco
    response = input("Recriar banco de dados? (s/N): ").strip().lower()
    drop_existing = response in ['s', 'sim', 'y', 'yes']
    
    if drop_existing:
        print("⚠️  ATENÇÃO: Todos os dados existentes serão perdidos!")
        confirm = input("Confirmar? (s/N): ").strip().lower()
        if confirm not in ['s', 'sim', 'y', 'yes']:
            print("Operação cancelada.")
            return
    
    # Cria banco
    if create_database(drop_existing=drop_existing):
        # Verifica
        if verify_database():
            # Cria dados de exemplo se solicitado
            if drop_existing:
                create_sample = input("Criar dados de exemplo? (s/N): ").strip().lower()
                if create_sample in ['s', 'sim', 'y', 'yes']:
                    create_sample_data()
            
            print("\n🎉 Configuração concluída com sucesso!")
            print(f"📁 Banco de dados: {DATABASE_URL}")
        else:
            print("\n❌ Problemas encontrados na verificação do banco.")
    else:
        print("\n❌ Falha na criação do banco de dados.")

if __name__ == "__main__":
    main()