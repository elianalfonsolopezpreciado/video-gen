"""
modules/subtitle_engine.py - Subtitulos estilo TikTok (CPU-first, multiplataforma).

Optimizado para VPS con poca RAM:
  - Modelo configurable (base=140MB, small=460MB)
  - Descarga modelo del modelo si no existe localmente
  - Libera memoria tras transcribir
"""

import os
import gc
import subprocess
import sys
import platform

from modules.logger import get_logger

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if platform.system() == "Windows":
    WHISPER_CLI = os.path.join(_BASE, "whisper", "whisper-cli.exe")
else:
    WHISPER_CLI = os.path.join(_BASE, "whisper", "whisper-cli")

WHISPER_MODEL = os.path.join(_BASE, "whisper", "models", "ggml-small.bin")


def _ensure_faster_whisper():
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        log = get_logger()
        log.info("Instalando faster-whisper (transcripcion CPU)...")
        subprocess.run([sys.executable, "-m", "pip", "install", "faster-whisper", "--quiet"], check=True)
        log.info("faster-whisper instalado.")


def _sec_to_srt_time(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    ms = int((s % 1) * 1000)
    return f"{h:02d}:{m:02d}:{int(s):02d},{ms:03d}"


def _transcribe_faster_whisper(wav_path: str, out_srt: str) -> str:
    log = get_logger()
    _ensure_faster_whisper()
    from faster_whisper import WhisperModel

    from modules.config_manager import get_config
    cfg = get_config()
    model_size = cfg.get("whisper_model", "base")

    log.info(f"Transcribiendo con faster-whisper (CPU, modelo: {model_size})...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    segments, info = model.transcribe(
        wav_path, language="es", word_timestamps=True, beam_size=5,
        vad_filter=True, vad_parameters={"min_silence_duration_ms": 300},
    )

    counter = 0
    with open(out_srt, "w", encoding="utf-8") as f:
        for segment in segments:
            words = getattr(segment, "words", None) or []
            for word in words:
                text = word.word.strip()
                if not text:
                    continue
                counter += 1
                f.write(f"{counter}\n{_sec_to_srt_time(word.start)} --> {_sec_to_srt_time(word.end)}\n{text}\n\n")

    # Liberar modelo de la RAM
    del model
    gc.collect()

    log.info(f"SRT generado (faster-whisper): {counter} palabras")
    return out_srt


def _transcribe_cli(wav_path: str, output_base: str) -> str:
    log = get_logger()

    if not os.path.exists(WHISPER_CLI):
        raise FileNotFoundError(f"Whisper CLI no encontrado: {WHISPER_CLI}")
    if not os.path.exists(WHISPER_MODEL):
        raise FileNotFoundError(f"Modelo Whisper no encontrado: {WHISPER_MODEL}")

    log.info(f"Intentando Whisper CLI local: {os.path.basename(wav_path)}")

    cmd = [
        WHISPER_CLI, "-m", WHISPER_MODEL, "-f", wav_path,
        "-l", "es", "-osrt", "-ml", "1", "-sow", "-of", output_base,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

    out_srt = output_base + ".srt"
    if result.returncode != 0 or not os.path.exists(out_srt):
        raise RuntimeError(f"Whisper CLI fallo (codigo {result.returncode}).")
    return out_srt


def transcribe_to_srt(wav_path: str, output_base: str = None) -> str:
    log = get_logger()

    if output_base is None:
        output_base = os.path.splitext(wav_path)[0]

    out_srt = output_base + ".srt"

    if os.path.exists(out_srt) and os.path.getsize(out_srt) > 100:
        log.info(f"SRT ya existe: {os.path.basename(out_srt)}")
        return out_srt

    try:
        srt = _transcribe_cli(wav_path, output_base)
        log.info("Transcripcion con Whisper CLI local")
        return srt
    except Exception as e:
        log.warning(f"Whisper CLI fallo: {e}")
        log.info("Cambiando a faster-whisper (CPU)...")

    try:
        return _transcribe_faster_whisper(wav_path, out_srt)
    except Exception as e:
        raise RuntimeError(f"Ambos motores de transcripcion fallaron.\nUltimo error: {e}") from e


def parse_srt(srt_path: str) -> list:
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()
    subs = []
    for block in content.strip().split("\n\n"):
        lines = [l.strip() for l in block.strip().split("\n")]
        if len(lines) >= 3 and " --> " in lines[1]:
            start, end = lines[1].split(" --> ", 1)
            text = " ".join(lines[2:]).strip()
            if text:
                subs.append({"start": start.strip(), "end": end.strip(), "text": text})
    return subs


def _srt_time_to_ass(t: str) -> str:
    t = t.replace(",", ".")
    h, m, rest = t.split(":")
    s_float = float(rest)
    s = int(s_float)
    cs = round((s_float - s) * 100)
    return f"{int(h)}:{int(m):02d}:{s:02d}.{cs:02d}"


def srt_to_ass(srt_path: str, ass_path: str, is_short: bool = False,
               is_long: bool = False) -> str:
    log = get_logger()

    if is_short:
        play_res_x, play_res_y = 1080, 1920
        font_size = 115
        margin_v = 60
    else:
        play_res_x, play_res_y = 1920, 1080
        font_size = int(95 * 1.3) if is_long else 95
        margin_v = 55

    subs = parse_srt(srt_path)

    header = (
        "[Script Info]\n"
        "Title: Lo lei en algun lugar\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {play_res_x}\n"
        f"PlayResY: {play_res_y}\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,Impact,{font_size},"
        "&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,5,2,5,0,0,{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    event_lines = []
    for sub in subs:
        start = _srt_time_to_ass(sub["start"])
        end = _srt_time_to_ass(sub["end"])
        text = (
            sub["text"].upper()
            .replace(",", "").replace(".", "")
            .replace("?", "").replace("!", "")
        )
        event_lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(event_lines))

    log.info(f"ASS generado: {os.path.basename(ass_path)} ({len(subs)} entradas)")
    return ass_path
