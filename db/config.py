from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import URL, create_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / "network_config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "mode": "sqlite",
    "sqlite_path": "db/teste.db",
    "postgres": {
        "host": "",
        "port": 5432,
        "database": "technord",
        "user": "technord_app",
        "password": "",
        "connect_timeout": 5,
    },
    "shared_storage": "",
}


def _merge(current: dict, defaults: dict) -> dict:
    out = dict(defaults)
    for key, value in (current or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(value, out[key])
        else:
            out[key] = value
    return out


def load_network_config() -> dict:
    current = {}
    if CONFIG_FILE.exists():
        try:
            current = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            current = {}
    return _merge(current, DEFAULT_CONFIG)


def save_network_config(config: dict) -> None:
    cfg = _merge(config, DEFAULT_CONFIG)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def is_postgres(config: dict | None = None) -> bool:
    cfg = config or load_network_config()
    return str(cfg.get("mode", "sqlite")).lower() in {"postgres", "postgresql"}


def get_database_url(config: dict | None = None):
    cfg = config or load_network_config()
    if is_postgres(cfg):
        pg = cfg.get("postgres", {})
        return URL.create(
            "postgresql+psycopg",
            username=pg.get("user") or "",
            password=pg.get("password") or "",
            host=pg.get("host") or "localhost",
            port=int(pg.get("port") or 5432),
            database=pg.get("database") or "technord",
        )

    path = Path(cfg.get("sqlite_path") or "db/teste.db").expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


def create_db_engine(config: dict | None = None):
    cfg = config or load_network_config()
    url = get_database_url(cfg)
    if is_postgres(cfg):
        timeout = int(cfg.get("postgres", {}).get("connect_timeout") or 5)
        return create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=1800,
            future=True,
            connect_args={"connect_timeout": timeout, "application_name": "TechNordTestFlow"},
        )
    return create_engine(url, future=True)


# Mantido por compatibilidade com módulos antigos que ainda importam esta constante.
DATABASE_URL = get_database_url()
