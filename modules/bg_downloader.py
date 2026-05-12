"""
modules/bg_downloader.py - Descarga de videos de fondo con yt-dlp.
"""

import os
import sys
import glob
import subprocess

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LARGOS_DIR = os.path.join(_BASE, "videos", "largos")
SHORTS_DIR = os.path.join(_BASE, "videos", "shorts")


def ensure_ytdlp() -> bool:
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, timeout=10)
        return True
    except FileNotFoundError:
        print("  Instalando yt-dlp...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "yt-dlp", "--quiet"],
            check=True,
        )
        print("  yt-dlp instalado.")
        return True


def download_video(url: str, output_dir: str, max_height: int = 1080) -> str:
    os.makedirs(output_dir, exist_ok=True)

    fmt = (
        f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]"
        f"/best[height<={max_height}][ext=mp4]/best"
    )
    cmd = [
        "yt-dlp",
        "-f", fmt,
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--no-overwrites",
        "-o", os.path.join(output_dir, "%(title).50s.%(ext)s"),
        url,
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=600,
    )

    if result.returncode != 0:
        err = result.stderr[-500:] if result.stderr else "(sin detalles)"
        raise RuntimeError(f"yt-dlp fallo: {err}")

    files = sorted(
        glob.glob(os.path.join(output_dir, "*.mp4")),
        key=os.path.getmtime, reverse=True,
    )
    if files:
        return files[0]
    raise RuntimeError("No se encontro el archivo descargado.")


def interactive_download():
    ensure_ytdlp()

    print("\n" + "=" * 50)
    print("  DESCARGA DE VIDEOS DE FONDO")
    print("=" * 50)
    print("\nEstos videos se usan como fondo mientras se narra.")
    print("Pega enlaces de YouTube con gameplay, naturaleza, etc.\n")

    n_largos = input("Cuantos videos LARGOS (horizontales 16:9)? [4]: ").strip()
    n_largos = int(n_largos) if n_largos.isdigit() and int(n_largos) > 0 else 4

    n_shorts = input("Cuantos videos para SHORTS (se recortan automatico)? [4]: ").strip()
    n_shorts = int(n_shorts) if n_shorts.isdigit() and int(n_shorts) > 0 else 4

    if n_largos > 0:
        print(f"\n--- Videos largos ({n_largos}) ---")
        print("(Se descargan en 1080p)")
        for i in range(1, n_largos + 1):
            url = input(f"  [{i}/{n_largos}] URL: ").strip()
            if not url:
                print("  Saltando...")
                continue
            try:
                path = download_video(url, LARGOS_DIR, max_height=1080)
                size_mb = os.path.getsize(path) / (1024 * 1024)
                print(f"  [OK] {os.path.basename(path)} ({size_mb:.0f} MB)")
            except Exception as e:
                print(f"  [ERROR] {e}")

    if n_shorts > 0:
        print(f"\n--- Videos para shorts ({n_shorts}) ---")
        print("(Se descargan en HD, el sistema los recorta a vertical)")
        for i in range(1, n_shorts + 1):
            url = input(f"  [{i}/{n_shorts}] URL: ").strip()
            if not url:
                print("  Saltando...")
                continue
            try:
                path = download_video(url, SHORTS_DIR, max_height=1080)
                size_mb = os.path.getsize(path) / (1024 * 1024)
                print(f"  [OK] {os.path.basename(path)} ({size_mb:.0f} MB)")
            except Exception as e:
                print(f"  [ERROR] {e}")

    total_l = len(glob.glob(os.path.join(LARGOS_DIR, "*.mp4")))
    total_s = len(glob.glob(os.path.join(SHORTS_DIR, "*.mp4")))
    print(f"\nTotal videos de fondo: {total_l} largos, {total_s} shorts")
    return total_l, total_s
