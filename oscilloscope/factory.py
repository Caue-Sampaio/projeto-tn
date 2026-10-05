from __future__ import annotations

from typing import Any

from .mock_driver import MockOscilloscope
from .rigol_mso5000 import RigolMSO5000


def list_visa_resources(visa_backend: str = "") -> list[str]:
    try:
        import pyvisa
        rm = pyvisa.ResourceManager(visa_backend) if visa_backend else pyvisa.ResourceManager()
        try:
            return list(rm.list_resources())
        finally:
            rm.close()
    except Exception:
        return []


def create_driver(config: dict[str, Any]):
    backend = str(config.get("backend") or "visa").lower().strip()
    if backend == "mock" or str(config.get("resource") or "").upper().startswith("MOCK"):
        return MockOscilloscope(config)
    if backend == "visa":
        return RigolMSO5000(config)
    raise ValueError(f"Backend de osciloscópio não suportado: {backend}")
