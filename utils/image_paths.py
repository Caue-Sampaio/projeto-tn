# utils/image_paths.py
"""Localiza as imagens das placas e guarda sempre o caminho ABSOLUTO no banco."""
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
IMAGES_DIR = BASE_DIR / "imagens"


def _to_posix(path):
    return Path(path).resolve().as_posix()


def resolve_image_path(stored_path):
    """Devolve o caminho ABSOLUTO real da imagem, ou None se não achar.

    Tenta, na ordem:
      1. o caminho salvo no banco;
      2. o caminho relativo à pasta do projeto;
      3. o mesmo NOME de arquivo em imagens/ e na raiz do projeto.
    """
    if not stored_path:
        return None

    p = Path(str(stored_path).replace("\\", "/"))
    candidates = [p, BASE_DIR / p, IMAGES_DIR / p.name, BASE_DIR / p.name]

    for c in candidates:
        try:
            if c.is_file():
                return _to_posix(c)
        except OSError:
            pass
    return None


def import_image_to_project(source_path):
    """Copia a imagem escolhida para imagens/ e devolve o caminho ABSOLUTO da cópia."""
    IMAGES_DIR.mkdir(exist_ok=True)
    src = Path(source_path)
    dest = IMAGES_DIR / src.name

    n = 1
    while dest.exists() and dest.resolve() != src.resolve():
        dest = IMAGES_DIR / f"{src.stem}_{n}{src.suffix}"
        n += 1

    if not dest.exists():
        shutil.copy2(src, dest)

    return _to_posix(dest)


def heal_board_images(session, board):
    """Regrava como ABSOLUTO o caminho de cada imagem da placa que for encontrada.

    Devolve a lista de imagens que continuam sem arquivo.
    """
    missing = []
    changed = False
    for image in board.images:
        real = resolve_image_path(image.path)
        if real is None:
            missing.append(image)
        elif image.path != real:
            image.path = real
            changed = True
    if changed:
        session.commit()
    return missing