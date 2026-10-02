# utils/backup_manager.py
import os
import stat
import shutil
import zipfile
import json
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import logging
from typing import List, Dict, Optional
import schedule
import time
import threading

logger = logging.getLogger(__name__)

class BackupManager:
    """Gerenciador de backup automático do sistema"""
    
    def __init__(self, db_path: str = "db/teste.db", backup_dir: str = "backups"):
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir)
        self.config_file = Path("backup_config.json")
        self._load_config()
        
        # Garante que os diretórios existam
        self.backup_dir.mkdir(exist_ok=True)
        self.db_path.parent.mkdir(exist_ok=True)
        
        # Thread para backups automáticos
        self.scheduler_thread = None
        self.stop_scheduler = False
    
    def _load_config(self):
        """Carrega ou cria configuração de backup"""
        default_config = {
            "auto_backup": True,
            "backup_interval_hours": 24,
            "max_backups": 10,
            "backup_reports": True,
            "backup_logs": True,
            "backup_images": False,
            "compression_level": 6,
            "last_backup": None,
            "backup_stats": {
                "total_backups": 0,
                "last_successful": None,
                "total_size_mb": 0
            }
        }
        
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                logger.info("Configuração de backup carregada")
            except Exception as e:
                logger.error(f"Erro ao carregar configuração: {e}")
                self.config = default_config
        else:
            self.config = default_config
            self._save_config()
    
    def _save_config(self):
        """Salva configuração de backup"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erro ao salvar configuração: {e}")
    
    def create_backup(self, backup_type: str = "manual") -> Dict:
        """
        Cria backup completo do sistema
        
        Args:
            backup_type: Tipo de backup ("manual", "auto", "emergency")
            
        Returns:
            Dicionário com informações do backup
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{backup_type}_{timestamp}"
        backup_path = self.backup_dir / backup_name
        
        try:
            logger.info(f"Iniciando backup: {backup_name}")
            
            # Cria diretório do backup
            backup_path.mkdir(exist_ok=True)
            
            backup_info = {
                "name": backup_name,
                "type": backup_type,
                "timestamp": datetime.now().isoformat(),
                "files": {},
                "total_size_mb": 0,
                "status": "in_progress"
            }
            
            # 1. Backup do banco de dados
            db_backup_success = self._backup_database(backup_path, backup_info)
            
            # 2. Backup de relatórios (se habilitado)
            if self.config.get("backup_reports", True):
                self._backup_reports(backup_path, backup_info)
            
            # 3. Backup de logs (se habilitado)
            if self.config.get("backup_logs", True):
                self._backup_logs(backup_path, backup_info)
            
            # 4. Backup de imagens (se habilitado)
            if self.config.get("backup_images", False):
                self._backup_images(backup_path, backup_info)
            
            # 5. Backup de configurações
            self._backup_configurations(backup_path, backup_info)
            
            # 6. Cria arquivo de informações do backup
            self._create_backup_info_file(backup_path, backup_info)
            
            # 7. Compacta backup
            zip_success = self._compress_backup(backup_path, backup_info)
            
            # 8. Limpa backup temporário. Em Windows/OneDrive, o copytree pode
            # preservar o atributo somente leitura de diretórios (ex.: reports),
            # fazendo shutil.rmtree falhar com WinError 5.
            self._safe_rmtree(backup_path)
            
            # Atualiza estatísticas
            if db_backup_success and zip_success:
                backup_info["status"] = "success"
                self._update_backup_stats(backup_info)
                logger.info(f"Backup criado com sucesso: {backup_name}.zip")
            else:
                backup_info["status"] = "partial"
                logger.warning(f"Backup parcial criado: {backup_name}.zip")
            
            # Limpa backups antigos
            self.cleanup_old_backups()
            
            return backup_info
            
        except Exception as e:
            logger.error(f"Erro ao criar backup: {e}")
            # Tenta limpar diretório temporário em caso de erro
            if backup_path.exists():
                try:
                    self._safe_rmtree(backup_path)
                except Exception as cleanup_error:
                    logger.warning(
                        f"Não foi possível remover o diretório temporário "
                        f"{backup_path}: {cleanup_error}"
                    )
            
            return {
                "name": backup_name,
                "type": backup_type,
                "timestamp": datetime.now().isoformat(),
                "status": "failed",
                "error": str(e)
            }
    
    @staticmethod
    def _rmtree_remove_readonly(func, path, exc_info):
        """Remove atributo somente leitura e repete uma operação do rmtree."""
        try:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            func(path)
        except Exception:
            # Mantém a exceção original caso a segunda tentativa também falhe.
            raise exc_info[1]

    def _safe_rmtree(self, path: Path):
        """Remove uma árvore mesmo quando diretórios copiados estão read-only."""
        path = Path(path)
        if not path.exists():
            return
        shutil.rmtree(path, onerror=self._rmtree_remove_readonly)

    def _backup_database(self, backup_path: Path, backup_info: Dict) -> bool:
        """Faz backup do banco de dados"""
        try:
            if not self.db_path.exists():
                logger.error("Arquivo do banco de dados não encontrado")
                return False
            
            # Copia arquivo do banco
            db_backup_path = backup_path / "database"
            db_backup_path.mkdir(exist_ok=True)
            
            shutil.copy2(self.db_path, db_backup_path / "teste.db")
            
            # Tenta fazer backup SQL (dump)
            self._create_sql_dump(db_backup_path)
            
            # Calcula tamanho
            db_size = self.db_path.stat().st_size
            backup_info["files"]["database"] = {
                "size_mb": round(db_size / (1024 * 1024), 2),
                "files": ["teste.db", "dump.sql"]
            }
            backup_info["total_size_mb"] += db_size / (1024 * 1024)
            
            logger.info("Backup do banco de dados concluído")
            return True
            
        except Exception as e:
            logger.error(f"Erro no backup do banco: {e}")
            return False
    
    def _create_sql_dump(self, backup_path: Path):
        """Cria dump SQL do banco de dados"""
        try:
            dump_path = backup_path / "dump.sql"
            
            # Conecta ao banco e cria dump
            conn = sqlite3.connect(self.db_path)
            
            with open(dump_path, 'w', encoding='utf-8') as f:
                for line in conn.iterdump():
                    f.write(f"{line}\n")
            
            conn.close()
            logger.debug("Dump SQL criado com sucesso")
            
        except Exception as e:
            logger.warning(f"Erro ao criar dump SQL: {e}")
    
    def _backup_reports(self, backup_path: Path, backup_info: Dict):
        """Faz backup dos relatórios"""
        try:
            reports_dir = Path("reports")
            if not reports_dir.exists():
                return
            
            reports_backup_path = backup_path / "reports"
            if reports_dir.exists():
                shutil.copytree(reports_dir, reports_backup_path, 
                              dirs_exist_ok=True)
            
            # Calcula tamanho
            reports_size = sum(f.stat().st_size for f in reports_dir.rglob('*') if f.is_file())
            backup_info["files"]["reports"] = {
                "size_mb": round(reports_size / (1024 * 1024), 2),
                "file_count": len(list(reports_dir.rglob('*')))
            }
            backup_info["total_size_mb"] += reports_size / (1024 * 1024)
            
            logger.info("Backup de relatórios concluído")
            
        except Exception as e:
            logger.error(f"Erro no backup de relatórios: {e}")
    
    def _backup_logs(self, backup_path: Path, backup_info: Dict):
        """Faz backup dos logs"""
        try:
            logs_dir = Path("logs")
            if not logs_dir.exists():
                return
            
            logs_backup_path = backup_path / "logs"
            logs_backup_path.mkdir(exist_ok=True)
            
            # Copia arquivos individualmente para evitar erro de arquivo em uso (WinError 5)
            logs_size = 0
            file_count = 0
            
            for log_file in logs_dir.rglob('*'):
                if log_file.is_file():
                    try:
                        dest_file = logs_backup_path / log_file.relative_to(logs_dir)
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(log_file, dest_file)
                        logs_size += log_file.stat().st_size
                        file_count += 1
                    except Exception as copy_err:
                        # Log file is likely in use, skip it or try reading
                        pass
            
            if file_count > 0:
                backup_info["files"]["logs"] = {
                    "size_mb": round(logs_size / (1024 * 1024), 2),
                    "file_count": file_count
                }
                backup_info["total_size_mb"] += logs_size / (1024 * 1024)
            
            logger.info("Backup de logs concluído")
            
        except Exception as e:
            logger.error(f"Erro no backup de logs: {e}")
    
    def _backup_images(self, backup_path: Path, backup_info: Dict):
        """Faz backup das imagens das placas"""
        try:
            # Isso precisaria ser adaptado para sua estrutura de imagens
            images_dirs = ["board_images", "temp_images"]
            total_size = 0
            total_files = 0
            
            for img_dir in images_dirs:
                img_path = Path(img_dir)
                if img_path.exists():
                    img_backup_path = backup_path / img_dir
                    shutil.copytree(img_path, img_backup_path, 
                                  dirs_exist_ok=True)
                    
                    dir_size = sum(f.stat().st_size for f in img_path.rglob('*') if f.is_file())
                    dir_files = len(list(img_path.rglob('*')))
                    
                    total_size += dir_size
                    total_files += dir_files
            
            if total_files > 0:
                backup_info["files"]["images"] = {
                    "size_mb": round(total_size / (1024 * 1024), 2),
                    "file_count": total_files
                }
                backup_info["total_size_mb"] += total_size / (1024 * 1024)
            
            logger.info("Backup de imagens concluído")
            
        except Exception as e:
            logger.error(f"Erro no backup de imagens: {e}")
    
    def _backup_configurations(self, backup_path: Path, backup_info: Dict):
        """Faz backup das configurações"""
        try:
            config_files = [
                "db/config.py",
                "backup_config.json"
            ]
            
            config_backup_path = backup_path / "config"
            config_backup_path.mkdir(exist_ok=True)
            
            total_size = 0
            
            for config_file in config_files:
                config_path = Path(config_file)
                if config_path.exists():
                    shutil.copy2(config_path, config_backup_path / config_path.name)
                    total_size += config_path.stat().st_size
            
            if total_size > 0:
                backup_info["files"]["config"] = {
                    "size_mb": round(total_size / (1024 * 1024), 2),
                    "file_count": len(config_files)
                }
                backup_info["total_size_mb"] += total_size / (1024 * 1024)
            
            logger.info("Backup de configurações concluído")
            
        except Exception as e:
            logger.error(f"Erro no backup de configurações: {e}")
    
    def _create_backup_info_file(self, backup_path: Path, backup_info: Dict):
        """Cria arquivo com informações do backup"""
        try:
            info_file = backup_path / "backup_info.json"
            with open(info_file, 'w', encoding='utf-8') as f:
                json.dump(backup_info, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erro ao criar arquivo de informações: {e}")
    
    def _compress_backup(self, backup_path: Path, backup_info: Dict) -> bool:
        """Compacta o backup em arquivo ZIP"""
        try:
            zip_path = self.backup_dir / f"{backup_path.name}.zip"
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, 
                               compresslevel=self.config.get("compression_level", 6)) as zipf:
                for file_path in backup_path.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(backup_path)
                        zipf.write(file_path, arcname)
            
            # Atualiza tamanho final
            zip_size = zip_path.stat().st_size
            backup_info["compressed_size_mb"] = round(zip_size / (1024 * 1024), 2)
            backup_info["compression_ratio"] = round(
                (backup_info["total_size_mb"] - backup_info["compressed_size_mb"]) / 
                backup_info["total_size_mb"] * 100, 1
            ) if backup_info["total_size_mb"] > 0 else 0
            
            return True
            
        except Exception as e:
            logger.error(f"Erro ao compactar backup: {e}")
            return False
    
    def _update_backup_stats(self, backup_info: Dict):
        """Atualiza estatísticas de backup"""
        self.config["last_backup"] = backup_info["timestamp"]
        self.config["backup_stats"]["total_backups"] += 1
        self.config["backup_stats"]["last_successful"] = backup_info["timestamp"]
        self.config["backup_stats"]["total_size_mb"] = round(
            self.config["backup_stats"].get("total_size_mb", 0) + 
            backup_info.get("compressed_size_mb", 0), 2
        )
        self._save_config()
    
    def list_backups(self) -> List[Dict]:
        """Lista todos os backups disponíveis"""
        backups = []
        
        for zip_file in self.backup_dir.glob("*.zip"):
            try:
                # Extrai informações do nome do arquivo
                name_parts = zip_file.stem.split('_')
                if len(name_parts) >= 3:
                    backup_type = name_parts[1]
                    timestamp_str = '_'.join(name_parts[2:])
                    
                    # Tenta parsear timestamp
                    try:
                        timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    except:
                        timestamp = datetime.fromtimestamp(zip_file.stat().st_mtime)
                    
                    # Obtém informações do arquivo
                    file_size = zip_file.stat().st_size
                    
                    backup_info = {
                        "filename": zip_file.name,
                        "type": backup_type,
                        "timestamp": timestamp,
                        "size_mb": round(file_size / (1024 * 1024), 2),
                        "file_path": str(zip_file)
                    }
                    
                    # Tenta carregar informações detalhadas
                    info_file = self._extract_backup_info(zip_file)
                    if info_file:
                        backup_info.update(info_file)
                    
                    backups.append(backup_info)
                    
            except Exception as e:
                logger.warning(f"Erro ao processar backup {zip_file.name}: {e}")
        
        # Ordena por timestamp (mais recente primeiro)
        backups.sort(key=lambda x: x["timestamp"], reverse=True)
        return backups
    
    def _extract_backup_info(self, zip_path: Path) -> Optional[Dict]:
        """Extrai informações do backup do arquivo ZIP"""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                if "backup_info.json" in zipf.namelist():
                    with zipf.open("backup_info.json") as f:
                        return json.load(f)
        except:
            pass
        return None
    
    def restore_backup(self, backup_filename: str, restore_path: str = ".") -> bool:
        """Restaura backup específico"""
        try:
            backup_path = self.backup_dir / backup_filename
            if not backup_path.exists():
                logger.error(f"Backup não encontrado: {backup_filename}")
                return False
            
            restore_dir = Path(restore_path)
            restore_dir.mkdir(exist_ok=True)
            
            logger.info(f"Iniciando restauração: {backup_filename}")
            
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                zipf.extractall(restore_dir)
            
            logger.info(f"Backup restaurado com sucesso em: {restore_path}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao restaurar backup: {e}")
            return False
    
    def cleanup_old_backups(self):
        """Remove backups antigos baseado na configuração"""
        try:
            max_backups = self.config.get("max_backups", 10)
            backups = self.list_backups()
            
            if len(backups) > max_backups:
                # Mantém os backups mais recentes
                backups_to_keep = backups[:max_backups]
                backups_to_delete = backups[max_backups:]
                
                for backup in backups_to_delete:
                    try:
                        backup_path = Path(backup["file_path"])
                        backup_path.unlink()
                        logger.info(f"Backup antigo removido: {backup_path.name}")
                    except Exception as e:
                        logger.error(f"Erro ao remover backup {backup['filename']}: {e}")
                        
        except Exception as e:
            logger.error(f"Erro ao limpar backups antigos: {e}")
    
    def get_backup_stats(self) -> Dict:
        """Retorna estatísticas de backup"""
        backups = self.list_backups()
        total_size = sum(b["size_mb"] for b in backups)
        
        return {
            "total_backups": len(backups),
            "total_size_mb": round(total_size, 2),
            "auto_backup_enabled": self.config.get("auto_backup", True),
            "last_backup": self.config.get("last_backup"),
            "next_auto_backup": self._get_next_auto_backup_time()
        }
    
    def _get_next_auto_backup_time(self) -> Optional[str]:
        """Calcula próxima execução de backup automático"""
        if not self.config.get("auto_backup", True):
            return None
        
        last_backup = self.config.get("last_backup")
        if last_backup:
            try:
                last_time = datetime.fromisoformat(last_backup)
                next_time = last_time + timedelta(hours=self.config.get("backup_interval_hours", 24))
                return next_time.isoformat()
            except:
                pass
        
        return None
    
    def start_auto_backup(self):
        """Inicia agendamento de backups automáticos"""
        if not self.config.get("auto_backup", True):
            return
        
        interval_hours = self.config.get("backup_interval_hours", 24)
        
        # Agenda backup automático
        schedule.every(interval_hours).hours.do(
            lambda: self.create_backup("auto")
        )
        
        # Inicia thread do agendador
        self.stop_scheduler = False
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        logger.info(f"Backup automático iniciado (intervalo: {interval_hours}h)")
    
    def _run_scheduler(self):
        """Executa loop do agendador"""
        while not self.stop_scheduler:
            schedule.run_pending()
            time.sleep(60)  # Verifica a cada minuto
    
    def stop_auto_backup(self):
        """Para backups automáticos"""
        self.stop_scheduler = True
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        schedule.clear()
        logger.info("Backup automático parado")
    
    def update_config(self, new_config: Dict):
        """Atualiza configuração de backup"""
        self.config.update(new_config)
        self._save_config()
        
        # Reinicia auto backup se necessário
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.stop_auto_backup()
        
        if self.config.get("auto_backup", True):
            self.start_auto_backup()
    
    def verify_backup_integrity(self, backup_filename: str) -> Dict:
        """Verifica integridade do backup"""
        try:
            backup_path = self.backup_dir / backup_filename
            
            if not backup_path.exists():
                return {"status": "error", "message": "Backup não encontrado"}
            
            # Verifica se é um arquivo ZIP válido
            try:
                with zipfile.ZipFile(backup_path, 'r') as zipf:
                    # Testa integridade do ZIP
                    bad_file = zipf.testzip()
                    if bad_file:
                        return {"status": "corrupted", "message": f"Arquivo corrompido: {bad_file}"}
                    
                    # Verifica se tem arquivos essenciais
                    essential_files = ["database/teste.db", "backup_info.json"]
                    missing_files = [f for f in essential_files if f not in zipf.namelist()]
                    
                    if missing_files:
                        return {"status": "incomplete", "message": f"Arquivos faltando: {missing_files}"}
                    
                    return {"status": "ok", "message": "Backup íntegro"}
                    
            except zipfile.BadZipFile:
                return {"status": "corrupted", "message": "Arquivo ZIP corrompido"}
                
        except Exception as e:
            return {"status": "error", "message": str(e)}

# Função de conveniência
def create_quick_backup() -> bool:
    """Cria backup rápido (função de conveniência)"""
    try:
        manager = BackupManager()
        result = manager.create_backup("quick")
        return result.get("status") == "success"
    except Exception as e:
        logger.error(f"Erro no backup rápido: {e}")
        return False