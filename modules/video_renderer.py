"""
modules/video_renderer.py - Composicion de video final con FFmpeg (multiplataforma).

Optimizado para VPS: preset y CRF configurables para balancear calidad/velocidad/tamaño.
"""

import os
import glob
import json
import random
import subprocess

from modules.logger import get_logger

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BG_LARGOS = os.path.join(_BASE, "videos", "largos")
BG_SHORTS = os.path.join(_BASE, "videos", "shorts")
OUTPUT_LARGOS = os.path.join(_BASE, "output", "largos")
OUTPUT_SHORTS = os.path.join(_BASE, "output", "shorts")


def _get_ffmpeg_opts() -> tuple:
    from modules.config_manager import get_config
    cfg = get_config()
    preset = cfg.get("ffmpeg_preset", "fast")
    crf = str(cfg.get("ffmpeg_crf", 26))
    return preset, crf


def _pick_bg(folder: str, fallback: str = None) -> str:
    bgs = glob.glob(os.path.join(folder, "*.mp4"))
    if not bgs and fallback:
        bgs = glob.glob(os.path.join(fallback, "*.mp4"))
    if not bgs:
        raise FileNotFoundError(
            f"No se encontraron videos de fondo en: {folder}\n"
            "Coloca al menos un .mp4 en videos/largos/ y videos/shorts/"
        )
    return random.choice(bgs)


def _run_ffmpeg(cmd: list, cwd: str = None):
    log = get_logger()
    log.debug("FFmpeg cmd: " + " ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
    if result.returncode != 0:
        stderr = result.stderr[-1200:] if result.stderr else "(vacio)"
        raise RuntimeError(f"FFmpeg fallo (codigo {result.returncode}):\n{stderr}")


def render_long_video(voice_path, ass_path, music_path, output_path, bg_folder=None) -> str:
    log = get_logger()
    if os.path.exists(output_path):
        log.info(f"Video largo ya existe: {os.path.basename(output_path)}")
        return output_path

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    preset, crf = _get_ffmpeg_opts()

    bg = _pick_bg(bg_folder or BG_LARGOS)
    bg_start = random.randint(0, 30)
    work_dir = os.path.dirname(ass_path)
    ass_rel = os.path.basename(ass_path)

    log.info(f"Renderizando video largo 1920x1080 (preset={preset}, crf={crf})...")

    if music_path and os.path.exists(music_path):
        fc = (
            f"[0:v]scale=1920:1080,ass='{ass_rel}'[v];"
            "[1:a]volume=1.0[voice];"
            "[2:a]volume=0.15,aloop=loop=-1:size=2000000000[music];"
            "[voice][music]amix=inputs=2:duration=first:dropout_transition=3[a]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(bg_start), "-stream_loop", "-1", "-i", bg,
            "-i", voice_path, "-i", music_path,
            "-filter_complex", fc,
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", preset, "-crf", crf,
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", "-shortest", output_path,
        ]
    else:
        fc = f"[0:v]scale=1920:1080,ass='{ass_rel}'[v]"
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(bg_start), "-stream_loop", "-1", "-i", bg,
            "-i", voice_path,
            "-filter_complex", fc,
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-preset", preset, "-crf", crf,
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", "-shortest", output_path,
        ]

    _run_ffmpeg(cmd, cwd=work_dir)
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    log.info(f"Video largo listo: {os.path.basename(output_path)} ({size_mb:.1f} MB)")
    return output_path


def render_short_video(voice_path, ass_path, music_path, output_path, bg_folder=None) -> str:
    log = get_logger()
    if os.path.exists(output_path):
        log.info(f"Short ya existe: {os.path.basename(output_path)}")
        return output_path

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    preset, crf = _get_ffmpeg_opts()

    bg = _pick_bg(bg_folder or BG_SHORTS, fallback=BG_LARGOS)
    bg_start = random.randint(0, 30)
    work_dir = os.path.dirname(ass_path)
    ass_rel = os.path.basename(ass_path)

    log.info(f"Renderizando Short 1080x1920 (preset={preset}, crf={crf})...")

    if music_path and os.path.exists(music_path):
        fc = (
            f"[0:v]crop=ih*(9/16):ih,scale=1080:1920,ass='{ass_rel}'[v];"
            "[1:a]volume=1.0[voice];"
            "[2:a]volume=0.12,aloop=loop=-1:size=2000000000[music];"
            "[voice][music]amix=inputs=2:duration=first:dropout_transition=3[a]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(bg_start), "-stream_loop", "-1", "-i", bg,
            "-i", voice_path, "-i", music_path,
            "-filter_complex", fc,
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", preset, "-crf", crf,
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", "-shortest", output_path,
        ]
    else:
        fc = f"[0:v]crop=ih*(9/16):ih,scale=1080:1920,ass='{ass_rel}'[v]"
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(bg_start), "-stream_loop", "-1", "-i", bg,
            "-i", voice_path,
            "-filter_complex", fc,
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-preset", preset, "-crf", crf,
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", "-shortest", output_path,
        ]

    _run_ffmpeg(cmd, cwd=work_dir)
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    log.info(f"Short listo: {os.path.basename(output_path)} ({size_mb:.1f} MB)")
    return output_path
