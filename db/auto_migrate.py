# db/auto_migrate.py
"""Ajustes automáticos de esquema para bancos SQLite já existentes.

`Base.metadata.create_all()` cria tabelas novas (como `machines`), mas NÃO
adiciona colunas novas em tabelas que já existem. Este módulo faz isso, sem
apagar nenhum dado.
"""
import logging

from sqlalchemy import inspect, text

from db.models import Base

logger = logging.getLogger(__name__)


def _columns(engine, table):
    return {col["name"] for col in inspect(engine).get_columns(table)}


def ensure_schema(engine):
    """Cria tabelas que faltam e adiciona colunas novas. Pode rodar quantas vezes quiser."""
    Base.metadata.create_all(engine)

    if "machine_id" not in _columns(engine, "board_units"):
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE board_units ADD COLUMN machine_id INTEGER REFERENCES machines(id)")
            )
        logger.info("Coluna board_units.machine_id adicionada.")

    if "image_path" not in _columns(engine, "machines"):
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE machines ADD COLUMN image_path VARCHAR(500)"))
        logger.info("Coluna machines.image_path adicionada.")