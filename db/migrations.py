import sqlite3
from pathlib import Path
from utils.security import hash_password

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "teste.db"

def migrate():
    print(f"Migrando banco em {DB_PATH}...")
    if not DB_PATH.exists():
        print("Banco de dados não encontrado. Nada a migrar.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Update passwords
    print("Atualizando senhas...")
    cursor.execute("SELECT id, password_hash FROM users")
    users = cursor.fetchall()

    for user_id, pwd in users:
        # Check if already a bcrypt hash (starts with $2b$)
        if not pwd.startswith("$2b$"):
            hashed = hash_password(pwd)
            cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hashed, user_id))
            print(f"Senha atualizada para o usuário ID {user_id}")

    # 2. Fix test_points table (recreate without measured columns)
    # Get columns
    cursor.execute("PRAGMA table_info(test_points)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if "measured_voltage_v" in columns:
        print("Removendo colunas measured_* de test_points...")
        # Create new table
        cursor.execute("""
        CREATE TABLE test_points_new (
            id INTEGER NOT NULL PRIMARY KEY,
            refdes VARCHAR(50) NOT NULL,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            expected_voltage_v FLOAT,
            expected_current_a FLOAT,
            expected_frequency_hz FLOAT,
            expected_waveform VARCHAR(100),
            tolerance_voltage_v FLOAT,
            tolerance_current_a FLOAT,
            tolerance_frequency_hz FLOAT,
            notes TEXT,
            marker_color VARCHAR(7) NOT NULL DEFAULT '#E53935',
            created_at DATETIME NOT NULL,
            board_id INTEGER NOT NULL,
            FOREIGN KEY(board_id) REFERENCES board_units (id)
        )
        """)
        
        # Copy data
        cursor.execute("""
        INSERT INTO test_points_new (id, refdes, x, y, expected_voltage_v, expected_current_a, expected_frequency_hz, expected_waveform, tolerance_voltage_v, tolerance_current_a, tolerance_frequency_hz, notes, marker_color, created_at, board_id)
        SELECT id, refdes, x, y, expected_voltage_v, expected_current_a, expected_frequency_hz, expected_waveform, tolerance_voltage_v, tolerance_current_a, tolerance_frequency_hz, notes, '#E53935', created_at, board_id
        FROM test_points
        """)
        
        cursor.execute("DROP TABLE test_points")
        cursor.execute("ALTER TABLE test_points_new RENAME TO test_points")
        print("Tabela test_points atualizada com sucesso.")
    else:
        print("A tabela test_points já está atualizada.")

    conn.commit()
    conn.close()
    print("Migração concluída.")

if __name__ == "__main__":
    migrate()
