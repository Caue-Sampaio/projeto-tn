from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

from db.config import PROJECT_ROOT, load_network_config


def get_storage_root(config: dict | None = None) -> Path:
    cfg = config or load_network_config()
    shared = str(cfg.get("shared_storage") or "").strip()
    if shared:
        return Path(shared).expanduser()
    return PROJECT_ROOT


def ensure_storage_root(config: dict | None = None) -> Path:
    root = get_storage_root(config)
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_storage_write(directory: str | Path) -> tuple[bool, str]:
    path = Path(directory).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".technord_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True, f"Pasta acessível: {path}"
    except Exception as exc:
        return False, f"Não foi possível gravar em {path}: {exc}"


def _safe_name(name: str) -> str:
    invalid = '<>:"/\\|?*'
    value = "".join("_" if ch in invalid else ch for ch in name)
    return value.strip().replace(" ", "_") or "arquivo"


def storage_relative(path: Path, root: Path | None = None) -> str:
    base = root or get_storage_root()
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except Exception:
        return str(path)


def resolve_storage_path(stored_path: str | Path | None) -> Path | None:
    if not stored_path:
        return None
    raw = str(stored_path).strip()
    if raw.startswith("storage://"):
        raw = raw[len("storage://"):]

    candidate = Path(raw).expanduser()
    if candidate.is_absolute() and candidate.exists():
        return candidate

    # 1) armazenamento compartilhado atual
    shared_candidate = get_storage_root() / candidate
    if shared_candidate.exists():
        return shared_candidate

    # 2) compatibilidade com arquivos antigos dentro do projeto local
    project_candidate = PROJECT_ROOT / candidate
    if project_candidate.exists():
        return project_candidate

    # Retorna o caminho esperado no storage para permitir mensagens claras.
    return shared_candidate


def copy_file_to_storage(source_path: str | Path, relative_dir: str | Path) -> str:
    source = Path(source_path).expanduser()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {source}")

    root = ensure_storage_root()
    target_dir = root / Path(relative_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target = target_dir / f"{stamp}_{_safe_name(source.name)}"
    shutil.copy2(source, target)
    return target.relative_to(root).as_posix()


def open_storage_directory(relative_dir: str | Path = "") -> Path:
    path = ensure_storage_root() / Path(relative_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path
