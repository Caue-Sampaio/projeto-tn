from __future__ import annotations

import shutil
from pathlib import Path

from utils.storage import copy_file_to_storage, get_storage_root, resolve_storage_path


def import_image_to_project(source_path: str) -> str:
    """Copia uma imagem para o storage compartilhado e retorna caminho relativo."""
    return copy_file_to_storage(source_path, "board_images")


def resolve_image_path(stored_path):
    path = resolve_storage_path(stored_path)
    return path if path and path.exists() else None


def heal_board_images(session, board):
    """Resolve caminhos antigos. Se storage compartilhado estiver ativo, migra sob demanda."""
    missing = []
    root = get_storage_root()
    for image in getattr(board, "images", []) or []:
        raw = getattr(image, "path", None)
        resolved = resolve_storage_path(raw)
        if not resolved or not resolved.exists():
            missing.append(image)
            continue

        # Se o caminho é absoluto/local e há storage separado, copia para o storage
        # para que os demais computadores também consigam acessar.
        try:
            if Path(raw).is_absolute() and root.resolve() not in resolved.resolve().parents:
                new_rel = copy_file_to_storage(str(resolved), f"board_images/{board.id}")
                image.path = new_rel
                session.add(image)
        except Exception:
            pass

    try:
        if session.dirty:
            session.commit()
    except Exception:
        session.rollback()
    return missing
