from __future__ import annotations

import shutil
import sys
from pathlib import Path

from sqlalchemy import MetaData, create_engine, func, select, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.config import create_db_engine, load_network_config, is_postgres  # noqa: E402
from db.models import Base  # noqa: E402
from utils.storage import get_storage_root  # noqa: E402


def _copy_directory_if_exists(source: Path, target: Path):
    if source.exists() and source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, dirs_exist_ok=True)


def _migrate_shared_files():
    storage = get_storage_root()
    if storage.resolve() == PROJECT_ROOT.resolve():
        print("Pasta compartilhada não configurada; arquivos permanecem locais.")
        return
    storage.mkdir(parents=True, exist_ok=True)
    for name in ("documents", "board_images", "reports"):
        _copy_directory_if_exists(PROJECT_ROOT / name, storage / name)
    print(f"Arquivos copiados para: {storage}")


def _target_has_data(engine) -> bool:
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            try:
                value = conn.execute(select(func.count()).select_from(table)).scalar_one()
                if value:
                    return True
            except Exception:
                continue
    return False


def _reset_postgres_sequences(engine):
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if "id" not in table.c:
                continue
            table_name = table.name.replace("'", "''")
            try:
                conn.execute(text(f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table_name}', 'id'),
                        COALESCE((SELECT MAX(id) FROM \"{table.name}\"), 1),
                        (SELECT COUNT(*) > 0 FROM \"{table.name}\")
                    )
                """))
            except Exception:
                # Algumas PKs podem não usar sequence; isso não invalida a migração.
                pass


def migrate():
    cfg = load_network_config()
    if not is_postgres(cfg):
        raise SystemExit(
            "network_config.json ainda não está em modo PostgreSQL. "
            "Configure o servidor pelo programa antes de executar a migração."
        )

    source_path = Path(cfg.get("sqlite_path") or "db/teste.db")
    if not source_path.is_absolute():
        source_path = PROJECT_ROOT / source_path
    source_path = source_path.resolve()
    if not source_path.exists():
        raise SystemExit(f"Banco SQLite não encontrado: {source_path}")

    source_engine = create_engine(f"sqlite:///{source_path.as_posix()}", future=True)
    target_engine = create_db_engine(cfg)

    try:
        Base.metadata.create_all(target_engine)
        if _target_has_data(target_engine):
            raise SystemExit(
                "O PostgreSQL de destino já possui dados. A migração foi cancelada para evitar duplicações."
            )

        src_meta = MetaData()
        src_meta.reflect(bind=source_engine)

        total_rows = 0
        with source_engine.connect() as src, target_engine.begin() as dst:
            for target_table in Base.metadata.sorted_tables:
                if target_table.name not in src_meta.tables:
                    print(f"[ignorado] {target_table.name}: não existe no SQLite antigo")
                    continue
                source_table = src_meta.tables[target_table.name]
                common = [c.name for c in target_table.columns if c.name in source_table.c]
                if not common:
                    continue
                rows = src.execute(select(*[source_table.c[name] for name in common])).mappings().all()
                if not rows:
                    print(f"[0] {target_table.name}")
                    continue
                payload = [{name: row[name] for name in common} for row in rows]
                dst.execute(target_table.insert(), payload)
                total_rows += len(payload)
                print(f"[{len(payload)}] {target_table.name}")

        _reset_postgres_sequences(target_engine)
        _migrate_shared_files()
        print("\nMigração concluída com sucesso.")
        print(f"Total de registros copiados: {total_rows}")
        print("O arquivo SQLite original não foi alterado.")
    finally:
        source_engine.dispose()
        target_engine.dispose()


if __name__ == "__main__":
    migrate()
