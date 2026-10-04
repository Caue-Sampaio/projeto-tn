# diagnostico_imagens.py
# Coloque este arquivo na RAIZ do projeto (ao lado do main.py) e rode:
#     python diagnostico_imagens.py
# Ele cria o arquivo diagnostico.txt com o resultado. Mande esse texto.
import os
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
out = []


def say(msg=""):
    print(msg)
    out.append(str(msg))


say("=== DIAGNÓSTICO DE IMAGENS ===")
say(f"Python: {sys.version.split()[0]}")
say(f"Pasta do projeto: {BASE}")

# 1) Os arquivos corrigidos foram colocados no lugar certo?
say("\n[1] Arquivos corrigidos instalados?")
checks = [
    ("utils/image_paths.py", "def resolve_image_path"),
    ("ui/placa_tab.py", "class ImagePreviewLabel"),
    ("ui/test_executor.py", "heal_board_images"),
]
for rel, marker in checks:
    f = BASE / rel
    if not f.exists():
        say(f"  FALTA   {rel}  (arquivo não existe nesta pasta)")
        continue
    txt = f.read_text(encoding="utf-8", errors="ignore")
    say(f"  {'OK    ' if marker in txt else 'ANTIGO'}  {rel}"
        + ("" if marker in txt else "  <- ainda é a versão antiga, não foi substituído"))

# 2) Qt
say("\n[2] PyQt6")
try:
    from PyQt6.QtCore import PYQT_VERSION_STR
    from PyQt6.QtGui import QImage, QImageReader
    fmts = sorted(bytes(x).decode() for x in QImageReader.supportedImageFormats())
    say(f"  PyQt6 {PYQT_VERSION_STR} | formatos: {', '.join(fmts)}")
    HAS_QT = True
except Exception as e:
    say(f"  PyQt6 não pôde ser importado: {e}")
    HAS_QT = False

# 3) Imagens cadastradas no banco
say("\n[3] Imagens cadastradas no banco")
db = BASE / "db" / "teste.db"
say(f"  Banco: {db}  ({'existe' if db.exists() else 'NÃO EXISTE'})")

resolve = None
try:
    sys.path.insert(0, str(BASE))
    from utils.image_paths import resolve_image_path as resolve
except Exception as e:
    say(f"  (utils.image_paths não carregou: {e})")

if db.exists():
    con = sqlite3.connect(str(db))
    rows = con.execute(
        "SELECT bi.id, bu.name, bu.serial_number, bi.path "
        "FROM board_images bi LEFT JOIN board_units bu ON bu.id = bi.board_id"
    ).fetchall()
    if not rows:
        say("  Nenhuma imagem cadastrada em nenhuma placa.")
    for img_id, name, sn, path in rows:
        say(f"\n  Imagem #{img_id} | placa: {name} (SN {sn})")
        say(f"    salvo no banco : {path}")
        say(f"    existe nesse caminho? {os.path.isfile(path)}")
        real = resolve(path) if resolve else None
        say(f"    resolvido para : {real}")
        if real and HAS_QT:
            qi = QImage(real)
            say(f"    Qt consegue abrir? {not qi.isNull()}"
                + (f"  ({qi.width()}x{qi.height()})" if not qi.isNull() else ""))
    boards = con.execute("SELECT id, name, serial_number FROM board_units").fetchall()
    sem = [b for b in boards if not any(r[1] == b[1] for r in rows)]
    for b in sem:
        say(f"\n  Placa SEM imagem cadastrada: {b[1]} (SN {b[2]})")

# 4) Imagens soltas na pasta
say("\n[4] Imagens encontradas na pasta do projeto")
exts = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}
for folder in (BASE, BASE / "imagens"):
    if folder.exists():
        for f in sorted(folder.iterdir()):
            if f.suffix.lower() in exts:
                say(f"  {f}")

(BASE / "diagnostico.txt").write_text("\n".join(out), encoding="utf-8")
say("\nResultado salvo em: diagnostico.txt")
