import sqlite3
from pathlib import Path
from db.config import DATABASE_URL, DB_CONFIG
from sqlalchemy import create_engine
from db.models import Base

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "teste.db"

def add_column_if_not_exists(cursor, table, column_name, column_type):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    if column_name not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}")
        print(f"Coluna {column_name} adicionada à tabela {table}.")

def migrate_phase2():
    print(f"Migrando banco Phase 2 em {DB_PATH}...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Expand board_models
    add_column_if_not_exists(cursor, "board_models", "manufacturer", "VARCHAR(100)")
    add_column_if_not_exists(cursor, "board_models", "equipment", "VARCHAR(100)")
    add_column_if_not_exists(cursor, "board_models", "category", "VARCHAR(50)")
    add_column_if_not_exists(cursor, "board_models", "voltage", "VARCHAR(50)")

    # Expand board_units
    add_column_if_not_exists(cursor, "board_units", "client", "VARCHAR(100)")
    add_column_if_not_exists(cursor, "board_units", "service_order", "VARCHAR(50)")
    add_column_if_not_exists(cursor, "board_units", "reported_defect", "TEXT")
    add_column_if_not_exists(cursor, "board_units", "diagnosis", "TEXT")

    # Since test_plans, test_steps, test_runs, measurements have 0 rows in the prototype,
    # we can just drop them and let SQLAlchemy recreate them with the new schema.
    # Check if they have rows first.
    tables_to_recreate = ["measurements", "test_steps", "test_plans", "test_runs"]
    for t in tables_to_recreate:
        try:
            cursor.execute(f"SELECT count(*) FROM {t}")
            count = cursor.fetchone()[0]
            if count == 0:
                cursor.execute(f"DROP TABLE {t}")
                print(f"Tabela {t} vazia foi dropada para recriação.")
        except sqlite3.OperationalError:
            pass # Table doesn't exist

    conn.commit()
    conn.close()

    # Recreate all dropped tables and create new tables (components, instruments, audit_logs)
    print("Recriando tabelas e criando novas (components, instruments, audit_logs)...")
    engine = create_engine(DATABASE_URL, **DB_CONFIG)
    Base.metadata.create_all(engine)
    print("Migração Phase 2 concluída com sucesso.")

if __name__ == "__main__":
    migrate_phase2()
