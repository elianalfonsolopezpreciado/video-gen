"""
modules/resource_manager.py - Monitor continuo de RAM, CPU y almacenamiento.

Incluye:
  - Daemon thread que monitorea cada 30s
  - Deteccion y creacion de swap en Linux
  - Umbrales inteligentes: si hay swap, tolera RAM fisica mas alta
  - Limpieza de emergencia automatica
"""

import os
import gc
import glob
import shutil
import time
import platform
import subprocess
import threading

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_psutil_available = False
try:
    import psutil
    _psutil_available = True
except ImportError:
    pass


# ── Swap management (Linux) ──

def get_swap_info() -> dict:
    """Retorna info de swap: total_mb, used_mb, free_mb, has_swap."""
    if _psutil_available:
        sw = psutil.swap_memory()
        return {
            "total_mb": sw.total / (1024 ** 2),
            "used_mb": sw.used / (1024 ** 2),
            "free_mb": (sw.total - sw.used) / (1024 ** 2),
            "has_swap": sw.total > 0,
            "percent": sw.percent,
        }

    if platform.system() == "Linux":
        try:
            with open("/proc/meminfo") as f:
                info = {}
                for line in f:
                    if line.startswith("SwapTotal:"):
                        info["total_mb"] = int(line.split()[1]) / 1024
                    elif line.startswith("SwapFree:"):
                        info["free_mb"] = int(line.split()[1]) / 1024
                if "total_mb" in info:
                    info["used_mb"] = info["total_mb"] - info.get("free_mb", 0)
                    info["has_swap"] = info["total_mb"] > 0
                    if info["total_mb"] > 0:
                        info["percent"] = (info["used_mb"] / info["total_mb"]) * 100
                    else:
                        info["percent"] = 0
                    return info
        except Exception:
            pass

    return {"total_mb": 0, "used_mb": 0, "free_mb": 0, "has_swap": False,
            "percent": 0}


def create_swap(size_gb: float = 2.0, swapfile: str = "/swapfile") -> bool:
    if platform.system() != "Linux":
        return False

    if os.path.exists(swapfile):
        try:
            result = subprocess.run(
                ["swapon", "--show=NAME", "--noheadings"],
                capture_output=True, text=True, timeout=5,
            )
            if swapfile in result.stdout:
                return True
        except Exception:
            pass

    size_mb = int(size_gb * 1024)

    commands = [
        ["sudo", "fallocate", "-l", f"{size_mb}M", swapfile],
        ["sudo", "chmod", "600", swapfile],
        ["sudo", "mkswap", swapfile],
        ["sudo", "swapon", swapfile],
    ]

    for cmd in commands:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            if "fallocate" in cmd[1]:
                dd_cmd = [
                    "sudo", "dd", "if=/dev/zero", f"of={swapfile}",
                    "bs=1M", f"count={size_mb}",
                ]
                result = subprocess.run(
                    dd_cmd, capture_output=True, text=True, timeout=300,
                )
                if result.returncode != 0:
                    return False
            else:
                return False

    try:
        with open("/etc/fstab", "r") as f:
            fstab = f.read()
        if swapfile not in fstab:
            entry = f"\n{swapfile} none swap sw 0 0\n"
            subprocess.run(
                ["sudo", "tee", "-a", "/etc/fstab"],
                input=entry, capture_output=True, text=True, timeout=10,
            )
    except Exception:
        pass

    return True


def setup_swap_interactive():
    print("\n--- MEMORIA VIRTUAL (SWAP) ---\n")

    swap = get_swap_info()

    if swap["has_swap"]:
        print(f"  [OK] Swap activo: {swap['total_mb']:.0f} MB "
              f"({swap['used_mb']:.0f} MB usados)")
        if swap["total_mb"] < 1024:
            print("  [!!] Swap muy pequeno para este sistema.")
            add = input("  Ampliar swap a 2 GB? (s/n) [s]: ").strip().lower()
            if add in ("n", "no"):
                return True
        else:
            return True

    if platform.system() != "Linux":
        print("  [!!] Sin swap. En Windows, configuralo desde Propiedades del sistema.")
        return False

    ram_gb = 1.0
    if _psutil_available:
        ram_gb = psutil.virtual_memory().total / (1024 ** 3)
    else:
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        ram_gb = int(line.split()[1]) / (1024 ** 2)
                        break
        except Exception:
            pass

    if ram_gb <= 1:
        swap_size = 2.0
    elif ram_gb <= 2:
        swap_size = 2.0
    elif ram_gb <= 4:
        swap_size = 3.0
    else:
        swap_size = 4.0

    if not swap["has_swap"]:
        print(f"  [!!] No se detecto swap.")
        print(f"  Con {ram_gb:.1f} GB de RAM, el sistema necesita swap")
        print(f"  para evitar que se cuelgue al transcribir o renderizar.")
    print()
    print(f"  Se creara un archivo swap de {swap_size:.0f} GB.")
    print("  (Requiere permisos sudo)")
    print()

    resp = input(f"  Crear swap de {swap_size:.0f} GB? (s/n) [s]: ").strip().lower()
    if resp in ("n", "no"):
        print("  Swap no creado. El sistema podria quedarse sin memoria.")
        return False

    print(f"  Creando swap de {swap_size:.0f} GB...", end=" ", flush=True)
    ok = create_swap(size_gb=swap_size)
    if ok:
        new_swap = get_swap_info()
        print(f"OK ({new_swap['total_mb']:.0f} MB)")
        print("  Swap configurado permanentemente en /etc/fstab")
        return True
    else:
        print("FALLO")
        print("  No se pudo crear swap. Intentalo manualmente:")
        print("    sudo fallocate -l 2G /swapfile")
        print("    sudo chmod 600 /swapfile")
        print("    sudo mkswap /swapfile")
        print("    sudo swapon /swapfile")
        return False


def adjust_swappiness(value: int = 60):
    if platform.system() != "Linux":
        return
    try:
        subprocess.run(
            ["sudo", "sysctl", f"vm.swappiness={value}"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass


# ── Resource Manager ──

class ResourceManager:
    def __init__(self, min_disk_gb=2.0, max_ram_pct=85, max_cpu_pct=90,
                 check_interval=30):
        self.min_disk_gb = min_disk_gb
        self._base_max_ram = max_ram_pct
        self.max_cpu_pct = max_cpu_pct
        self.check_interval = check_interval
        self._running = False
        self._thread = None
        self._status = {
            "ram_pct": 0, "ram_available_mb": 0,
            "cpu_pct": 0,
            "disk_free_gb": 999, "disk_total_gb": 0,
            "swap_total_mb": 0, "swap_used_mb": 0, "swap_pct": 0,
            "has_swap": False,
        }
        self._lock = threading.Lock()
        self._log = None
        self._last_warning = 0

        swap = get_swap_info()
        if swap["has_swap"] and swap["total_mb"] > 512:
            self.max_ram_pct = 95
        else:
            self.max_ram_pct = max_ram_pct

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

    def _should_warn(self) -> bool:
        now = time.time()
        if now - self._last_warning > 300:
            self._last_warning = now
            return True
        return False

    def _monitor_loop(self):
        while self._running:
            self._update_status()
            status = self.get_status()

            if status["disk_free_gb"] < self.min_disk_gb * 0.5:
                self._log_msg("warning",
                              f"Disco critico: {status['disk_free_gb']:.1f} GB")
                self.emergency_cleanup()

            if _psutil_available and status["ram_pct"] > self.max_ram_pct:
                if status["has_swap"] and status["swap_pct"] < 80:
                    pass
                elif self._should_warn():
                    self._log_msg("warning",
                                  f"RAM: {status['ram_pct']:.0f}% "
                                  f"| Swap: {status['swap_used_mb']:.0f}/"
                                  f"{status['swap_total_mb']:.0f} MB "
                                  f"({status['swap_pct']:.0f}%)")
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

        swap = get_swap_info()
        new_status["swap_total_mb"] = swap["total_mb"]
        new_status["swap_used_mb"] = swap["used_mb"]
        new_status["swap_pct"] = swap["percent"]
        new_status["has_swap"] = swap["has_swap"]

        with self._lock:
            self._status = new_status

    def get_status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def _memory_ok(self) -> bool:
        if not _psutil_available:
            return True
        s = self.get_status()

        if s["ram_pct"] <= self.max_ram_pct:
            return True

        if s["has_swap"] and s["swap_pct"] < 85:
            return True

        if s["ram_available_mb"] > 100:
            return True

        return False

    def can_proceed(self) -> bool:
        s = self.get_status()
        if s["disk_free_gb"] < self.min_disk_gb:
            return False
        return self._memory_ok()

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
                          f"Swap:{s['swap_pct']:.0f}%, "
                          f"Disco:{s['disk_free_gb']:.1f}GB). "
                          f"Reintentando en 30s...")
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
                    self._log_msg("info",
                                  f"  Cache musica: {os.path.basename(f)}")
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
                    self._log_msg("info",
                                  f"  Video viejo: {os.path.basename(f)}")
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
            parts.append(
                f"RAM: {s['ram_pct']:.0f}% "
                f"({s['ram_available_mb']:.0f} MB libres)"
            )
            if s["has_swap"]:
                parts.append(
                    f"Swap: {s['swap_used_mb']:.0f}/"
                    f"{s['swap_total_mb']:.0f} MB "
                    f"({s['swap_pct']:.0f}%)"
                )
            else:
                parts.append("Swap: NO")
            parts.append(f"CPU: {s['cpu_pct']:.0f}%")
        return " | ".join(parts)
