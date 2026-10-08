# utils/backup_manager.py
from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import subprocess
import stat
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import inspect, text
from db.config import load_network_config, create_db_engine, is_postgres
from utils.storage import get_storage_root

logger = logging.getLogger(__name__)


class BackupManager:
    """Gerencia backups locais do TechNord/TestFlow.

    Recursos principais:
      • backup diário (no máximo um por dia);
      • backup ao fechar o programa;
      • diretório de destino configurável;
      • backup manual;
      • retenção automática dos backups mais recentes.
    """

    def __init__(self, db_path: str | None = None, backup_dir: str | None = None):
        self.project_root = Path(__file__).resolve().parent.parent
        self.config_file = self.project_root / "backup_config.json"
        self.network_config = load_network_config()
        sqlite_path = db_path or self.network_config.get("sqlite_path") or "db/teste.db"
        self.db_path = self._resolve_project_path(sqlite_path)

        self.scheduler_thread: Optional[threading.Thread] = None
        self.stop_scheduler = False
        self._backup_lock = threading.Lock()

        self._load_config()

        # O argumento explícito tem prioridade apenas nesta inicialização.
        if backup_dir:
            self.config["backup_directory"] = str(Path(backup_dir).expanduser().resolve())
            self._save_config()

        self._refresh_backup_dir()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Configuração
    # ------------------------------------------------------------------
    def _resolve_project_path(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        if path.is_absolute():
            return path
        return (self.project_root / path).resolve()

    def _default_backup_dir(self) -> Path:
        return (self.project_root / "backups").resolve()

    @staticmethod
    def _merge_defaults(current: dict, defaults: dict) -> dict:
        result = dict(defaults)
        for key, value in current.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = BackupManager._merge_defaults(value, result[key])
            else:
                result[key] = value
        return result

    def _load_config(self):
        default_config = {
            "backup_directory": str(self._default_backup_dir()),
            "daily_backup": True,
            "backup_on_close": True,
            "max_backups": 30,
            "compression_level": 6,
            "backup_reports": True,
            "backup_logs": True,
            "backup_images": True,
            "backup_documents": True,
            "last_backup": None,
            "last_daily_backup": None,
            "last_close_backup": None,
            "backup_stats": {
                "total_backups": 0,
                "last_successful": None,
                "total_size_mb": 0,
            },
        }

        current = {}
        if self.config_file.exists():
            try:
                current = json.loads(self.config_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Não foi possível ler backup_config.json: %s", exc)

        # Compatibilidade com versões antigas.
        if "auto_backup" in current and "daily_backup" not in current:
            current["daily_backup"] = bool(current.get("auto_backup"))

        self.config = self._merge_defaults(current, default_config)
        self._save_config()

    def _save_config(self):
        try:
            self.config_file.write_text(
                json.dumps(self.config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("Erro ao salvar configuração de backup: %s", exc)

    def _refresh_backup_dir(self):
        configured = self.config.get("backup_directory") or str(self._default_backup_dir())
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = self._resolve_project_path(path)
        self.backup_dir = path.resolve()
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.config["backup_directory"] = str(self.backup_dir)
        self._save_config()

    def get_backup_directory(self) -> str:
        return str(self.backup_dir)

    def set_backup_directory(self, directory: str):
        path = Path(directory).expanduser()
        if not path.is_absolute():
            path = path.resolve()
        path.mkdir(parents=True, exist_ok=True)

        # Teste simples de escrita para evitar descobrir o erro somente no fechamento.
        test_file = path / ".technord_backup_write_test"
        try:
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
        except Exception as exc:
            raise PermissionError(f"Sem permissão para gravar em: {path}") from exc

        self.config["backup_directory"] = str(path.resolve())
        self._refresh_backup_dir()

    def update_config(self, new_config: Dict):
        directory = new_config.pop("backup_directory", None)
        self.config.update(new_config)
        if directory:
            self.set_backup_directory(str(directory))
        else:
            self._save_config()

        # Reinicia o monitor diário para refletir a nova configuração.
        self.stop_auto_backup()
        if self.config.get("daily_backup", True):
            self.start_auto_backup()

    # ------------------------------------------------------------------
    # Criação de backup
    # ------------------------------------------------------------------
    def create_backup(self, backup_type: str = "manual") -> Dict:
        """Cria um ZIP com os dados importantes do sistema."""
        if not self._backup_lock.acquire(blocking=False):
            return {
                "status": "busy",
                "type": backup_type,
                "error": "Já existe um backup em andamento.",
            }

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{backup_type}_{timestamp}"
        work_dir = self.backup_dir / backup_name
        zip_path = self.backup_dir / f"{backup_name}.zip"

        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            work_dir.mkdir(parents=True, exist_ok=False)

            info = {
                "name": backup_name,
                "type": backup_type,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "destination": str(zip_path),
                "files": {},
                "total_size_mb": 0.0,
                "status": "in_progress",
            }

            db_ok = self._backup_database(work_dir, info)

            if self.config.get("backup_documents", True):
                self._backup_folder("documents", work_dir, info)
            if self.config.get("backup_images", True):
                self._backup_folder("board_images", work_dir, info)
                self._backup_folder("temp_images", work_dir, info)
            if self.config.get("backup_reports", True):
                self._backup_folder("reports", work_dir, info)
            if self.config.get("backup_logs", True):
                self._backup_folder("logs", work_dir, info, ignore_errors=True)

            self._backup_configurations(work_dir, info)
            self._create_backup_info_file(work_dir, info)
            zip_ok = self._compress_backup(work_dir, zip_path)

            info["status"] = "success" if db_ok and zip_ok else "partial"
            if zip_path.exists():
                info["compressed_size_mb"] = round(zip_path.stat().st_size / (1024 * 1024), 2)

            if info["status"] == "success":
                self._register_success(info)
                if backup_type == "daily":
                    self.config["last_daily_backup"] = info["timestamp"]
                elif backup_type == "close":
                    self.config["last_close_backup"] = info["timestamp"]
                self._save_config()

            self.cleanup_old_backups()
            return info

        except Exception as exc:
            logger.exception("Erro ao criar backup")
            try:
                if zip_path.exists() and zip_path.stat().st_size == 0:
                    zip_path.unlink()
            except Exception:
                pass
            return {
                "name": backup_name,
                "type": backup_type,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "status": "failed",
                "error": str(exc),
            }
        finally:
            try:
                if work_dir.exists():
                    self._safe_rmtree(work_dir)
            except Exception as exc:
                logger.warning("Não foi possível remover pasta temporária do backup: %s", exc)
            self._backup_lock.release()

    def _backup_database(self, work_dir: Path, info: Dict) -> bool:
        self.network_config = load_network_config()
        if is_postgres(self.network_config):
            return self._backup_postgres_database(work_dir, info)
        return self._backup_sqlite_database(work_dir, info)

    def _backup_sqlite_database(self, work_dir: Path, info: Dict) -> bool:
        if not self.db_path.exists():
            logger.error("Banco SQLite não encontrado em %s", self.db_path)
            return False

        target_dir = work_dir / "database"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_db = target_dir / self.db_path.name

        src = sqlite3.connect(str(self.db_path), timeout=30)
        dst = sqlite3.connect(str(target_db), timeout=30)
        try:
            src.backup(dst)
        finally:
            dst.close(); src.close()

        dump_path = target_dir / "dump.sql"
        conn = sqlite3.connect(str(target_db), timeout=30)
        try:
            with dump_path.open("w", encoding="utf-8") as fh:
                for line in conn.iterdump():
                    fh.write(line + "\n")
        finally:
            conn.close()

        size = target_db.stat().st_size + dump_path.stat().st_size
        info["files"]["database"] = {
            "engine": "sqlite",
            "size_mb": round(size / (1024 * 1024), 2),
            "files": [target_db.name, dump_path.name],
        }
        info["total_size_mb"] += size / (1024 * 1024)
        return True

    @staticmethod
    def _json_value(value):
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, (bytes, bytearray)):
            return {"__bytes_hex__": bytes(value).hex()}
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:
                pass
        return str(value)

    def _backup_postgres_database(self, work_dir: Path, info: Dict) -> bool:
        """Exporta PostgreSQL sem exigir pg_dump; usa pg_dump também quando disponível."""
        target_dir = work_dir / "database"
        target_dir.mkdir(parents=True, exist_ok=True)
        engine = create_db_engine(self.network_config)
        export_path = target_dir / "postgres_export.json"
        payload = {
            "format": "technord-postgresql-json-v1",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "tables": {},
        }
        try:
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            with engine.connect() as conn:
                for table_name in tables:
                    quoted = '"' + table_name.replace('"', '""') + '"'
                    rows = conn.execute(text(f"SELECT * FROM {quoted}")).mappings().all()
                    payload["tables"][table_name] = [
                        {key: self._json_value(value) for key, value in row.items()}
                        for row in rows
                    ]
            export_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

            files = [export_path.name]
            pg = self.network_config.get("postgres", {})
            pg_dump = shutil.which("pg_dump")
            if pg_dump:
                dump_path = target_dir / "postgres.dump"
                env = os.environ.copy(); env["PGPASSWORD"] = str(pg.get("password") or "")
                cmd = [
                    pg_dump, "-Fc", "-h", str(pg.get("host") or "localhost"),
                    "-p", str(pg.get("port") or 5432), "-U", str(pg.get("user") or "technord_app"),
                    "-d", str(pg.get("database") or "technord"), "-f", str(dump_path),
                ]
                kwargs = {"env": env, "stdout": subprocess.DEVNULL, "stderr": subprocess.PIPE, "text": True}
                if os.name == "nt":
                    kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                proc = subprocess.run(cmd, **kwargs)
                if proc.returncode == 0 and dump_path.exists():
                    files.append(dump_path.name)
                else:
                    logger.warning("pg_dump não concluiu: %s", (proc.stderr or "").strip())

            total = sum((target_dir / name).stat().st_size for name in files if (target_dir / name).exists())
            info["files"]["database"] = {
                "engine": "postgresql",
                "size_mb": round(total / (1024 * 1024), 2),
                "files": files,
            }
            info["total_size_mb"] += total / (1024 * 1024)
            return True
        except Exception as exc:
            logger.exception("Erro ao exportar PostgreSQL: %s", exc)
            return False
        finally:
            engine.dispose()

    def _backup_folder(self, relative_dir: str, work_dir: Path, info: Dict, ignore_errors: bool = False):
        if relative_dir in {"documents", "board_images", "temp_images", "reports"}:
            source = get_storage_root() / relative_dir
        else:
            source = self.project_root / relative_dir
        if not source.exists() or not source.is_dir():
            return

        destination = work_dir / relative_dir
        copied = 0
        total_size = 0

        for file_path in source.rglob("*"):
            if not file_path.is_file():
                continue
            try:
                rel = file_path.relative_to(source)
                dest = destination / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, dest)
                copied += 1
                total_size += file_path.stat().st_size
            except Exception as exc:
                if not ignore_errors:
                    logger.warning("Falha ao copiar %s: %s", file_path, exc)

        if copied:
            info["files"][relative_dir] = {
                "file_count": copied,
                "size_mb": round(total_size / (1024 * 1024), 2),
            }
            info["total_size_mb"] += total_size / (1024 * 1024)

    def _backup_configurations(self, work_dir: Path, info: Dict):
        dest = work_dir / "config"
        dest.mkdir(parents=True, exist_ok=True)
        total = 0
        count = 0
        for rel in ("db/config.py", "backup_config.json", "network_config.json"):
            source = self.project_root / rel
            if source.exists() and source.is_file():
                shutil.copy2(source, dest / source.name)
                total += source.stat().st_size
                count += 1
        if count:
            info["files"]["config"] = {
                "file_count": count,
                "size_mb": round(total / (1024 * 1024), 2),
            }
            info["total_size_mb"] += total / (1024 * 1024)

    @staticmethod
    def _create_backup_info_file(work_dir: Path, info: Dict):
        (work_dir / "backup_info.json").write_text(
            json.dumps(info, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _compress_backup(self, work_dir: Path, zip_path: Path) -> bool:
        level = max(0, min(9, int(self.config.get("compression_level", 6))))
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=level) as archive:
            for file_path in work_dir.rglob("*"):
                if file_path.is_file():
                    archive.write(file_path, file_path.relative_to(work_dir))
        return zip_path.exists() and zip_path.stat().st_size > 0

    def _register_success(self, info: Dict):
        now = info["timestamp"]
        self.config["last_backup"] = now
        stats = self.config.setdefault("backup_stats", {})
        stats["total_backups"] = int(stats.get("total_backups", 0)) + 1
        stats["last_successful"] = now
        stats["total_size_mb"] = round(
            float(stats.get("total_size_mb", 0)) + float(info.get("compressed_size_mb", 0)),
            2,
        )

    # ------------------------------------------------------------------
    # Backup diário / fechamento
    # ------------------------------------------------------------------
    @staticmethod
    def _same_calendar_day(value: str | None, now: datetime) -> bool:
        if not value:
            return False
        try:
            return datetime.fromisoformat(value).date() == now.date()
        except Exception:
            return False

    def backup_if_due(self) -> Dict:
        """Cria o backup diário se ainda não houver um backup diário hoje."""
        if not self.config.get("daily_backup", True):
            return {"status": "disabled", "type": "daily"}

        now = datetime.now()
        if self._same_calendar_day(self.config.get("last_daily_backup"), now):
            return {"status": "not_due", "type": "daily"}
        return self.create_backup("daily")

    def create_close_backup(self) -> Dict:
        if not self.config.get("backup_on_close", True):
            return {"status": "disabled", "type": "close"}
        return self.create_backup("close")

    def start_auto_backup(self):
        """Mantém um verificador leve para o caso de o programa ficar aberto vários dias."""
        if not self.config.get("daily_backup", True):
            return
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            return

        self.stop_scheduler = False
        self.scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="TechNordBackupScheduler",
            daemon=True,
        )
        self.scheduler_thread.start()

    def _scheduler_loop(self):
        # A verificação inicial já é feita no main.py. Aqui aguardamos 30 minutos
        # antes de cada nova verificação para não disputar o lock com um backup
        # manual logo após salvar as configurações.
        while not self.stop_scheduler:
            for _ in range(180):
                if self.stop_scheduler:
                    return
                time.sleep(10)
            try:
                self.backup_if_due()
            except Exception:
                logger.exception("Erro no verificador de backup diário")

    def stop_auto_backup(self):
        self.stop_scheduler = True
        thread = self.scheduler_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        self.scheduler_thread = None

    # ------------------------------------------------------------------
    # Consulta / retenção / restauração
    # ------------------------------------------------------------------
    def cleanup_old_backups(self):
        max_backups = max(1, int(self.config.get("max_backups", 30)))
        backups = self.list_backups()
        for backup in backups[max_backups:]:
            try:
                Path(backup["file_path"]).unlink(missing_ok=True)
            except Exception as exc:
                logger.warning("Falha ao remover backup antigo %s: %s", backup.get("filename"), exc)

    def list_backups(self) -> List[Dict]:
        self._refresh_backup_dir()
        rows: List[Dict] = []
        for zip_file in self.backup_dir.glob("backup_*.zip"):
            try:
                parts = zip_file.stem.split("_", 2)
                backup_type = parts[1] if len(parts) > 1 else "desconhecido"
                timestamp = datetime.fromtimestamp(zip_file.stat().st_mtime)
                rows.append({
                    "filename": zip_file.name,
                    "type": backup_type,
                    "timestamp": timestamp,
                    "size_mb": round(zip_file.stat().st_size / (1024 * 1024), 2),
                    "file_path": str(zip_file),
                })
            except Exception:
                continue
        rows.sort(key=lambda x: x["timestamp"], reverse=True)
        return rows

    def restore_backup(self, backup_filename: str, restore_path: str = ".") -> bool:
        backup_path = self.backup_dir / backup_filename
        if not backup_path.exists():
            return False
        target = Path(restore_path).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(backup_path, "r") as archive:
            archive.extractall(target)
        return True

    def verify_backup_integrity(self, backup_filename: str) -> Dict:
        path = self.backup_dir / backup_filename
        if not path.exists():
            return {"status": "error", "message": "Backup não encontrado"}
        try:
            with zipfile.ZipFile(path, "r") as archive:
                bad = archive.testzip()
                if bad:
                    return {"status": "corrupted", "message": f"Arquivo corrompido: {bad}"}
                names = set(archive.namelist())
                if not any(name.startswith("database/") for name in names):
                    return {"status": "incomplete", "message": "Banco de dados ausente"}
            return {"status": "ok", "message": "Backup íntegro"}
        except zipfile.BadZipFile:
            return {"status": "corrupted", "message": "ZIP inválido"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def get_backup_stats(self) -> Dict:
        backups = self.list_backups()
        return {
            "total_backups": len(backups),
            "total_size_mb": round(sum(x["size_mb"] for x in backups), 2),
            "daily_backup": bool(self.config.get("daily_backup", True)),
            "backup_on_close": bool(self.config.get("backup_on_close", True)),
            "last_backup": self.config.get("last_backup"),
            "last_daily_backup": self.config.get("last_daily_backup"),
            "backup_directory": str(self.backup_dir),
        }

    @staticmethod
    def _rmtree_remove_readonly(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            func(path)
        except Exception:
            raise exc_info[1]

    def _safe_rmtree(self, path: Path):
        if path.exists():
            shutil.rmtree(path, onerror=self._rmtree_remove_readonly)


def create_quick_backup() -> bool:
    manager = BackupManager()
    return manager.create_backup("manual").get("status") == "success"
