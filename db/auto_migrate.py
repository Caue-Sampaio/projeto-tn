# db/auto_migrate.py
"""Migrações aditivas e seguras para bancos SQLite existentes."""
import logging

from sqlalchemy import inspect, text

from db.models import Base

logger = logging.getLogger(__name__)


def _columns(engine, table):
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def _add_column(engine, table: str, column: str, ddl: str) -> None:
    if column in _columns(engine, table):
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
    logger.info("Coluna %s.%s adicionada.", table, column)


def ensure_schema(engine):
    """Cria tabelas/colunas novas sem apagar dados existentes."""
    Base.metadata.create_all(engine)

    _add_column(engine, "board_units", "machine_id", "INTEGER REFERENCES machines(id)")
    _add_column(engine, "machines", "image_path", "VARCHAR(500)")

    _add_column(
        engine,
        "test_points",
        "marker_color",
        "VARCHAR(7) NOT NULL DEFAULT '#E53935'",
    )

    _add_column(
        engine,
        "test_points",
        "marker_shape",
        "VARCHAR(20) NOT NULL DEFAULT 'circle'",
    )
    _add_column(
        engine,
        "test_points",
        "marker_size",
        "INTEGER NOT NULL DEFAULT 16",
    )

    # Suporte a duas imagens por placa. Pontos antigos ficam na Imagem 1.
    _add_column(
        engine,
        "test_points",
        "image_slot",
        "INTEGER NOT NULL DEFAULT 1",
    )

    # Resumo da última captura do osciloscópio no próprio ponto.
    # O histórico completo é criado em oscilloscope_captures por create_all().
    _add_column(engine, "test_points", "last_scope_channel", "INTEGER")
    _add_column(engine, "test_points", "last_scope_vpp_v", "FLOAT")
    _add_column(engine, "test_points", "last_scope_vrms_v", "FLOAT")
    _add_column(engine, "test_points", "last_scope_frequency_hz", "FLOAT")
    _add_column(engine, "test_points", "last_scope_duty_pct", "FLOAT")
    _add_column(engine, "test_points", "last_scope_at", "DATETIME")
    _add_column(engine, "test_points", "last_oscilloscope_id", "VARCHAR(250)")

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE test_points SET marker_color = '#E53935' "
                "WHERE marker_color IS NULL OR TRIM(marker_color) = ''"
            )
        )
        conn.execute(
            text(
                "UPDATE test_points SET image_slot = 1 "
                "WHERE image_slot IS NULL OR image_slot NOT IN (1, 2)"
            )
        )
        conn.execute(
            text(
                "UPDATE test_points SET marker_shape = 'circle' "
                "WHERE marker_shape IS NULL OR marker_shape NOT IN ('circle','square','diamond','arrow','cross')"
            )
        )
        conn.execute(
            text(
                "UPDATE test_points SET marker_size = 16 "
                "WHERE marker_size IS NULL OR marker_size < 8 OR marker_size > 40"
            )
        )
