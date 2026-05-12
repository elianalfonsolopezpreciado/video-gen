"""
modules/resource_manager.py - Monitor continuo de RAM, CPU y almacenamiento.
Corre como daemon thread y administra recursos para mantener el sistema estable.
"""

import os
import gc
import glob
import shutil
import time
import threading

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_psutil_available = False
try:
    import psutil
    _psutil_available = True
except ImportError:
    pass


class ResourceManager:
    def __init__(self, min_disk_gb=2.0, max_ram_pct=85, max_cpu_pct=90,
                 check_interval=30):
        self.min_disk_gb = min_disk_gb
        self.max_ram_pct = max_ram_pct
        self.max_cpu_pct = max_cpu_pct
        self.check_interval = check_interval
        self._running = False
        self._thread = None
        self._status = {
            "ram_pct": 0, "ram_available_mb": 0,
            "cpu_pct": 0,
            "disk_free_gb": 999, "disk_total_gb": 0,
        }
        self._lock = threading.Lock()
        self._log = None

    def start(self):
        if self._running:
            return
        try:
            from modules.logger import get_logger
            self._log = get_logger()
        except Exception:
            pass
        self._running = True
        self._update_status()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _log_msg(self, level, msg):
        if self._log:
            getattr(self._log, level)(msg)

    def _monitor_loop(self):
        while self._running:
            self._update_status()
            status = self.get_status()

            if status["disk_free_gb"] < self.min_disk_gb * 0.5:
                self._log_msg("warning", f"Disco critico: {status['disk_free_gb']:.1f} GB")
                self.emergency_cleanup()

            if _psutil_available and status["ram_pct"] > self.max_ram_pct:
                self._log_msg("warning", f"RAM alta: {status['ram_pct']:.0f}%")
                gc.collect()
                gc.collect()

            time.sleep(self.check_interval)

    def _update_status(self):
        disk = shutil.disk_usage(_BASE)
        new_status = {
            "disk_free_gb": disk.free / (1024 ** 3),
            "disk_total_gb": disk.total / (1024 ** 3),
        }
        if _psutil_available:
            ram = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.5)
            new_status["ram_pct"] = ram.percent
            new_status["ram_available_mb"] = ram.available / (1024 ** 2)
            new_status["cpu_pct"] = cpu
        else:
            new_status["ram_pct"] = 0
            new_status["ram_available_mb"] = 0
            new_status["cpu_pct"] = 0
        with self._lock:
            self._status = new_status

    def get_status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def can_proceed(self) -> bool:
        s = self.get_status()
        if s["disk_free_gb"] < self.min_disk_gb:
            return False
        if _psutil_available and s["ram_pct"] > self.max_ram_pct:
            return False
        return True

    def wait_until_safe(self, timeout=600) -> bool:
        start = time.time()
        while not self.can_proceed():
            elapsed = time.time() - start
            if elapsed > timeout:
                self._log_msg("error",
                              f"Recursos insuficientes tras {timeout}s de espera.")
                return False
            s = self.get_status()
            self._log_msg("warning",
                          f"Esperando recursos (RAM:{s['ram_pct']:.0f}%, "
                          f"Disco:{s['disk_free_gb']:.1f}GB). Reintentando en 30s...")
            if s["disk_free_gb"] < self.min_disk_gb:
                self.emergency_cleanup()
            gc.collect()
            gc.collect()
            time.sleep(30)
        return True

    def emergency_cleanup(self):
        self._log_msg("warning", "--- Limpieza de emergencia ---")
        freed = 0.0

        temp_dir = os.path.join(_BASE, "output", "temp")
        if os.path.exists(temp_dir):
            for d in os.listdir(temp_dir):
                path = os.path.join(temp_dir, d)
                if os.path.isdir(path):
                    try:
                        size = sum(
                            os.path.getsize(os.path.join(dp, f))
                            for dp, _, fns in os.walk(path) for f in fns
                        )
                        shutil.rmtree(path, ignore_errors=True)
                        freed += size / (1024 ** 3)
                        self._log_msg("info", f"  Temp eliminado: {d}")
                    except Exception:
                        pass

        music_dir = os.path.join(_BASE, "musica")
        if os.path.exists(music_dir):
            files = sorted(glob.glob(os.path.join(music_dir, "*.mp3")),
                           key=os.path.getmtime)
            for f in files[:-2]:
                try:
                    size = os.path.getsize(f)
                    os.remove(f)
                    freed += size / (1024 ** 3)
                    self._log_msg("info", f"  Cache musica: {os.path.basename(f)}")
                except Exception:
                    pass

        logs_dir = os.path.join(_BASE, "logs")
        if os.path.exists(logs_dir):
            files = sorted(glob.glob(os.path.join(logs_dir, "*.log")),
                           key=os.path.getmtime)
            for f in files[:-3]:
                try:
                    os.remove(f)
                except Exception:
                    pass

        for d in ["output/largos", "output/shorts"]:
            out = os.path.join(_BASE, d)
            if not os.path.exists(out):
                continue
            mp4s = sorted(glob.glob(os.path.join(out, "*.mp4")),
                          key=os.path.getmtime)
            for f in mp4s[:-1]:
                try:
                    size = os.path.getsize(f)
                    os.remove(f)
                    freed += size / (1024 ** 3)
                    self._log_msg("info", f"  Video viejo: {os.path.basename(f)}")
                except Exception:
                    pass

        gc.collect()
        gc.collect()
        self._update_status()
        self._log_msg("info",
                      f"  Liberado: ~{freed:.2f} GB. "
                      f"Disco libre: {self.get_status()['disk_free_gb']:.1f} GB")

    def format_status(self) -> str:
        s = self.get_status()
        parts = [f"Disco: {s['disk_free_gb']:.1f}/{s['disk_total_gb']:.0f} GB"]
        if _psutil_available:
            parts.append(f"RAM: {s['ram_pct']:.0f}% ({s['ram_available_mb']:.0f} MB libres)")
            parts.append(f"CPU: {s['cpu_pct']:.0f}%")
        return " | ".join(parts)
