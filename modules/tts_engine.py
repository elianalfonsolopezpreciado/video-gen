"""
modules/tts_engine.py - Edge TTS (gratis, multiplataforma).
"""

import os
import asyncio
import subprocess
import json
import sys

from modules.logger import get_logger

VOICES = [
    "es-MX-DaliaNeural",
    "es-MX-JorgeNeural",
    "es-AR-ElenaNeural",
    "es-CO-SalomeNeural",
    "es-ES-ElviraNeural",
]


def _ensure_edge_tts():
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        log = get_logger()
        log.info("Instalando edge-tts...")
        subprocess.run([sys.executable, "-m", "pip", "install", "edge-tts", "--quiet"], check=True)
        log.info("edge-tts instalado.")


async def _tts_async(text: str, output_path: str, voice: str, rate: str = "+5%"):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate, volume="+0%")
    await communicate.save(output_path)


def generate_voice(text: str, output_path: str, voice: str = None) -> str:
    log = get_logger()
    _ensure_edge_tts()

    from modules.config_manager import get_config
    cfg = get_config()
    preferred = voice or cfg.get("tts_voice", "es-MX-DaliaNeural")
    voices_to_try = [preferred] + [v for v in VOICES if v != preferred]

    for v in voices_to_try:
        log.info(f"Generando voz TTS: {v}")
        try:
            asyncio.run(_tts_async(text, output_path, v))
            if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
                log.warning(f"Archivo vacio con voz {v}, intentando siguiente...")
                continue
            size_kb = os.path.getsize(output_path) / 1024
            log.info(f"Audio generado: {size_kb:.0f} KB con voz {v}")
            return output_path
        except Exception as e:
            log.warning(f"Error con voz {v}: {e}")
            if os.path.exists(output_path):
                os.remove(output_path)

    raise RuntimeError("No se pudo generar el audio TTS con ninguna voz disponible.")


def convert_to_wav(mp3_path: str, wav_path: str) -> str:
    log = get_logger()
    log.info(f"Convirtiendo a WAV: {os.path.basename(mp3_path)}")
    cmd = ["ffmpeg", "-y", "-i", mp3_path, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav_path]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg fallo al convertir a WAV:\n{result.stderr[-500:]}")
    log.info(f"WAV generado: {os.path.basename(wav_path)}")
    return wav_path


def get_audio_duration(audio_path: str) -> float:
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", audio_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            return float(data["format"]["duration"])
        except Exception:
            pass
    return 0.0
