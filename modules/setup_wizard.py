"""
modules/setup_wizard.py - Wizard de primera ejecucion.

Flujo:
  1. Escaneo del sistema + benchmarks
  2. Instalar dependencias segun capacidad del hardware
  3. Configurar API key (almacenada en .secrets)
  4. Configurar videos por dia
  5. Autenticar YouTube
  6. Descargar videos de fondo con yt-dlp
"""

import os
import sys
import time
import shutil
import subprocess
import platform
import tempfile

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIGURED_FLAG = os.path.join(_BASE, ".configured")


def is_first_run() -> bool:
    if not os.path.exists(CONFIGURED_FLAG):
        return True
    from modules.secrets_manager import has_api_key
    return not has_api_key()


def _print_banner():
    print()
    print("=" * 58)
    print("  ╔═══════════════════════════════════════════════════╗")
    print("  ║   Lo lei en algun lugar — Configuracion inicial  ║")
    print("  ╚═══════════════════════════════════════════════════╝")
    print("=" * 58)
    print()
    print("  Este asistente configurara todo automaticamente.")
    print("  Solo necesitas tu API key de OpenRouter y una")
    print("  cuenta de YouTube con API habilitada.")
    print()


def _scan_system() -> dict:
    print("--- ESCANEANDO SISTEMA ---\n")
    info = {
        "os": platform.system(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "cores": os.cpu_count() or 1,
        "ram_gb": 0,
        "disk_free_gb": 0,
        "disk_total_gb": 0,
        "gpu": False,
        "cpu_score": 0,
        "disk_write_mbps": 0,
    }

    disk = shutil.disk_usage(_BASE)
    info["disk_free_gb"] = disk.free / (1024 ** 3)
    info["disk_total_gb"] = disk.total / (1024 ** 3)

    try:
        import psutil
        ram = psutil.virtual_memory()
        info["ram_gb"] = ram.total / (1024 ** 3)
    except ImportError:
        if platform.system() == "Linux":
            try:
                with open("/proc/meminfo") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            kb = int(line.split()[1])
                            info["ram_gb"] = kb / (1024 ** 2)
                            break
            except Exception:
                pass
        if info["ram_gb"] == 0:
            info["ram_gb"] = 1.0

    print(f"  SO:          {info['os']} {info['arch']}")
    print(f"  Python:      {info['python']}")
    print(f"  CPU:         {info['cores']} nucleos")
    print(f"  RAM:         {info['ram_gb']:.1f} GB")
    print(f"  Disco:       {info['disk_free_gb']:.1f} GB libres / {info['disk_total_gb']:.0f} GB total")

    return info


def _run_benchmarks(info: dict) -> dict:
    print("\n--- BENCHMARKS ---\n")

    print("  CPU...", end=" ", flush=True)
    start = time.perf_counter()
    total = 0
    for n in range(2, 80000):
        is_prime = True
        for d in range(2, int(n ** 0.5) + 1):
            if n % d == 0:
                is_prime = False
                break
        if is_prime:
            total += 1
    cpu_time = time.perf_counter() - start
    info["cpu_score"] = cpu_time
    if cpu_time < 2:
        cpu_label = "RAPIDO"
    elif cpu_time < 5:
        cpu_label = "NORMAL"
    else:
        cpu_label = "LENTO"
    print(f"{cpu_time:.1f}s ({cpu_label})")

    print("  Disco...", end=" ", flush=True)
    try:
        test_file = os.path.join(_BASE, ".bench_test")
        data = os.urandom(10 * 1024 * 1024)
        start = time.perf_counter()
        with open(test_file, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        disk_time = time.perf_counter() - start
        info["disk_write_mbps"] = 10 / disk_time
        os.remove(test_file)
        print(f"{info['disk_write_mbps']:.0f} MB/s")
    except Exception:
        info["disk_write_mbps"] = 50
        print("no medible (usando default)")

    print()
    return info


def _determine_config(info: dict) -> dict:
    auto = {}

    ram = info["ram_gb"]
    if ram < 1.0:
        auto["whisper_model"] = "tiny"
    elif ram < 2.5:
        auto["whisper_model"] = "base"
    else:
        auto["whisper_model"] = "small"

    cpu = info["cpu_score"]
    if cpu < 2:
        auto["ffmpeg_preset"] = "medium"
        auto["ffmpeg_crf"] = 23
    elif cpu < 5:
        auto["ffmpeg_preset"] = "fast"
        auto["ffmpeg_crf"] = 26
    else:
        auto["ffmpeg_preset"] = "ultrafast"
        auto["ffmpeg_crf"] = 28

    if info["disk_free_gb"] < 10:
        auto["cleanup_after_upload"] = True
        auto["min_disk_gb"] = 1.5
    elif info["disk_free_gb"] < 30:
        auto["cleanup_after_upload"] = True
        auto["min_disk_gb"] = 2
    else:
        auto["cleanup_after_upload"] = True
        auto["min_disk_gb"] = 3

    print("--- CONFIGURACION AUTOMATICA ---\n")
    print(f"  Whisper:      {auto['whisper_model']}"
          f"  (RAM: {ram:.1f} GB)")
    print(f"  FFmpeg:       preset={auto['ffmpeg_preset']}, crf={auto['ffmpeg_crf']}"
          f"  (CPU: {cpu:.1f}s)")
    print(f"  Limpieza:     {'si' if auto['cleanup_after_upload'] else 'no'}"
          f"  (Disco: {info['disk_free_gb']:.0f} GB libres)")
    print(f"  Min disco:    {auto['min_disk_gb']} GB")
    print()

    return auto


def _install_dependencies(info: dict):
    print("--- INSTALANDO DEPENDENCIAS ---\n")

    packages = [
        ("psutil", "psutil"),
        ("requests", "requests"),
        ("edge-tts", "edge_tts"),
        ("yt-dlp", None),
        ("google-api-python-client", "googleapiclient"),
        ("google-auth-oauthlib", "google_auth_oauthlib"),
        ("google-auth-httplib2", None),
    ]

    if info["ram_gb"] >= 0.8:
        packages.append(("faster-whisper", "faster_whisper"))

    to_install = []
    for pip_name, import_name in packages:
        if import_name:
            try:
                __import__(import_name)
                print(f"  [OK] {pip_name}")
                continue
            except ImportError:
                pass
        else:
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "show", pip_name],
                    capture_output=True, timeout=10,
                )
                print(f"  [OK] {pip_name}")
                continue
            except Exception:
                pass
        to_install.append(pip_name)
        print(f"  [--] {pip_name} (pendiente)")

    if to_install:
        print(f"\n  Instalando {len(to_install)} paquetes...")
        cmd = [sys.executable, "-m", "pip", "install"] + to_install + ["--quiet"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("  Todas las dependencias instaladas.")
        else:
            print(f"  [WARN] Algunos paquetes fallaron: {result.stderr[-300:]}")
    else:
        print("\n  Todas las dependencias ya estaban instaladas.")

    print()

    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        print("  [OK] FFmpeg encontrado")
    except FileNotFoundError:
        print("  [!!] FFmpeg NO encontrado.")
        if info["os"] == "Linux":
            print("       Instala con: sudo apt install ffmpeg")
        elif info["os"] == "Darwin":
            print("       Instala con: brew install ffmpeg")
        else:
            print("       Descarga de: https://ffmpeg.org/download.html")
        print()
        resp = input("  Continuar sin FFmpeg? (s/n) [n]: ").strip().lower()
        if resp not in ("s", "si", "y"):
            print("\n  Instala FFmpeg y vuelve a ejecutar el wizard.")
            sys.exit(1)

    print()


def _configure_api() -> str:
    from modules.secrets_manager import save_api_key, load_api_key

    print("--- CONFIGURACION DE API ---\n")
    print("  Proveedor: OpenRouter (soporta modelos free y de pago)")
    print("  Obtener key: https://openrouter.ai/keys")
    print()

    existing = load_api_key()
    if existing:
        masked = existing[:10] + "..." + existing[-4:]
        print(f"  Key actual: {masked}")
        change = input("  Cambiar? (s/n) [n]: ").strip().lower()
        if change not in ("s", "si", "y"):
            return existing

    while True:
        key = input("  API Key de OpenRouter: ").strip()
        if key and len(key) > 10:
            save_api_key(key)
            print("  Key guardada en .secrets (no en config.json)")
            return key
        print("  Key invalida. Debe tener al menos 10 caracteres.")


def _configure_schedule() -> int:
    print("\n--- PROGRAMACION ---\n")
    print("  El sistema subira videos automaticamente a lo largo del dia.")
    print("  Ejemplos:")
    print("    5  = 1 video cada ~4.8 horas")
    print("    10 = 1 video cada ~2.4 horas")
    print("    20 = 1 video cada ~1.2 horas")
    print("    30 = 1 video cada ~48 minutos")
    print()

    while True:
        n = input("  Cuantos videos al dia? [20]: ").strip()
        if not n:
            return 20
        if n.isdigit() and 1 <= int(n) <= 100:
            count = int(n)
            interval = 86400 / count
            mins = interval / 60
            print(f"  OK: {count} videos/dia = 1 cada {mins:.0f} minutos")
            return count
        print("  Ingresa un numero entre 1 y 100.")


def _setup_youtube():
    print("\n--- AUTENTICACION DE YOUTUBE ---\n")

    secrets_path = os.path.join(_BASE, "client_secrets.json")
    if not os.path.exists(secrets_path):
        print("  [!!] No se encontro client_secrets.json")
        print()
        print("  Para obtenerlo:")
        print("  1. Ve a https://console.cloud.google.com/")
        print("  2. Crea un proyecto (o usa uno existente)")
        print("  3. Activa YouTube Data API v3")
        print("  4. Crea credenciales > OAuth 2.0 > Aplicacion de escritorio")
        print("  5. Descarga el JSON y colocalo como:")
        print(f"     {secrets_path}")
        print()
        input("  Presiona ENTER cuando hayas colocado el archivo...")

        if not os.path.exists(secrets_path):
            print("  [!!] Aun no se encuentra. Puedes agregarlo despues.")
            print("       El sistema funcionara sin subida a YouTube.")
            return False

    print("  Autenticando con YouTube...")
    print("  Te dara un enlace para copiar en tu navegador.")
    print("  Despues pegas el codigo de autorizacion aqui.")
    print()

    try:
        from modules.youtube_uploader import get_youtube_client
        client = get_youtube_client()
        print("\n  [OK] YouTube autenticado correctamente.")
        return True
    except Exception as e:
        print(f"  [ERROR] {e}")
        print("  Puedes intentar de nuevo mas tarde con: python cli.py --wizard")
        return False


def _download_backgrounds():
    print("\n--- VIDEOS DE FONDO ---\n")

    from modules.bg_downloader import LARGOS_DIR, SHORTS_DIR
    import glob as g

    existing_l = len(g.glob(os.path.join(LARGOS_DIR, "*.mp4")))
    existing_s = len(g.glob(os.path.join(SHORTS_DIR, "*.mp4")))

    if existing_l > 0 or existing_s > 0:
        print(f"  Ya tienes: {existing_l} largos, {existing_s} shorts")
        add = input("  Descargar mas? (s/n) [s]: ").strip().lower()
        if add in ("n", "no"):
            return

    print("\n  El sistema necesita videos de fondo (gameplay, naturaleza, etc.)")
    print("  que se reproducen detras de la narracion.")
    print("  Pega enlaces de YouTube uno por uno.\n")

    from modules.bg_downloader import interactive_download
    interactive_download()


def run_wizard():
    _print_banner()

    input("  Presiona ENTER para comenzar...\n")

    info = _scan_system()

    info = _run_benchmarks(info)

    # Swap automatico en VPS con poca RAM
    from modules.resource_manager import setup_swap_interactive, adjust_swappiness
    swap_ok = setup_swap_interactive()
    if swap_ok and info["os"] == "Linux":
        adjust_swappiness(60)

    auto_cfg = _determine_config(info)

    _install_dependencies(info)

    api_key = _configure_api()

    videos_per_day = _configure_schedule()

    yt_ok = _setup_youtube()

    _download_backgrounds()

    from modules.config_manager import load_config, save_config

    cfg = load_config()
    cfg.update({
        "provider": "openrouter",
        "api_base_url": "https://openrouter.ai/api/v1/chat/completions",
        "long_model": "mistralai/mistral-small-2603",
        "short_model": "openrouter/auto",
        "free_models": [
            "openrouter/free",
            "meta-llama/llama-3.2-3b-instruct:free",
            "google/gemma-4-26b-a4b-it:free",
            "qwen/qwen3-next-80b-a3b-instruct:free",
            "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
        ],
        "tts_voice": "es-MX-DaliaNeural",
        "generate_short": True,
        "upload_to_youtube": yt_ok,
        "youtube_privacy": "public",
        "music_query": "epic",
        "videos_per_day": videos_per_day,
        "whisper_model": auto_cfg["whisper_model"],
        "ffmpeg_preset": auto_cfg["ffmpeg_preset"],
        "ffmpeg_crf": auto_cfg["ffmpeg_crf"],
        "cleanup_after_upload": auto_cfg["cleanup_after_upload"],
        "min_disk_gb": auto_cfg["min_disk_gb"],
    })

    if "api_key" in cfg:
        del cfg["api_key"]

    save_config(cfg)

    with open(CONFIGURED_FLAG, "w") as f:
        f.write(f"configured={time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    print()
    print("=" * 58)
    print("  CONFIGURACION COMPLETA")
    print("=" * 58)
    print()
    print(f"  Videos/dia:    {videos_per_day}")
    print(f"  Intervalo:     {86400 / videos_per_day / 60:.0f} min entre videos")
    print(f"  Whisper:       {auto_cfg['whisper_model']}")
    print(f"  FFmpeg:        {auto_cfg['ffmpeg_preset']} / CRF {auto_cfg['ffmpeg_crf']}")
    print(f"  YouTube:       {'listo' if yt_ok else 'pendiente'}")
    print(f"  Limpieza:      automatica")
    print()

    return True
