#!/usr/bin/env python3
"""
cli.py - Sistema automatizado de videos para YouTube.
Canal: "Lo lei en algun lugar"

Primera ejecucion:
  python cli.py                    # Lanza wizard de configuracion automatico

Despues de configurar:
  python cli.py                    # Modo daemon (corre indefinidamente, X videos/dia)
  python cli.py --batch 5          # Generar 5 videos y parar
  python cli.py --wizard           # Re-ejecutar wizard de configuracion
  python cli.py --check            # Verificar dependencias y espacio
  python cli.py --status           # Ver estado del sistema
  python cli.py --backgrounds      # Descargar mas videos de fondo
  python cli.py --no-short         # Solo video largo (sin short)
  python cli.py --no-upload        # Sin subida a YouTube
  python cli.py --no-cleanup       # No borrar archivos despues de subir
  python cli.py --upload public    # Subir como publico
"""

import os
import sys
import gc
import json
import time
import shutil
import signal
import argparse
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)


# ══════════════════════════════════════════════════════════════
#  Utilidades
# ══════════════════════════════════════════════════════════════

def get_disk_free_gb(path=None) -> float:
    try:
        st = shutil.disk_usage(path or BASE_DIR)
        return st.free / (1024 ** 3)
    except Exception:
        return 999.0


def force_gc():
    gc.collect()
    gc.collect()


# ══════════════════════════════════════════════════════════════
#  Guardar metadatos TXT
# ══════════════════════════════════════════════════════════════

def save_metadata_txt(directory, filename, title, description, tags, hashtags,
                      video_path=None):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("  METADATOS PARA YOUTUBE\n")
        f.write("=" * 60 + "\n\n")
        f.write("TITULO:\n" + str(title) + "\n\n")
        f.write("DESCRIPCION:\n" + str(description) + "\n\n")
        f.write("TAGS (separados por coma):\n")
        f.write(
            (", ".join(str(t) for t in tags) if isinstance(tags, list)
             else str(tags)) + "\n\n"
        )
        f.write("HASHTAGS:\n")
        f.write(
            (" ".join(str(h) for h in hashtags) if isinstance(hashtags, list)
             else str(hashtags)) + "\n\n"
        )
        if video_path:
            f.write("ARCHIVO DE VIDEO:\n" + str(video_path) + "\n")


# ══════════════════════════════════════════════════════════════
#  Pipeline de un solo video
# ══════════════════════════════════════════════════════════════

def run_single_video(video_num, label, args, cfg, youtube_client, log,
                     resource_mgr=None):
    from modules.story_database import save_story, mark_uploaded
    from modules.story_generator import (
        generate_long_story, generate_short_script, generate_metadata,
    )
    from modules.tts_engine import generate_voice, convert_to_wav, get_audio_duration
    from modules.subtitle_engine import transcribe_to_srt, srt_to_ass
    from modules.music_manager import get_music
    from modules.video_renderer import (
        render_long_video, render_short_video, OUTPUT_LARGOS, OUTPUT_SHORTS,
    )
    from modules.youtube_uploader import upload_video

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = os.path.join(BASE_DIR, "output", "temp", ts)
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(OUTPUT_LARGOS, exist_ok=True)
    os.makedirs(OUTPUT_SHORTS, exist_ok=True)

    make_short = cfg.get("generate_short", True) and not args.no_short
    do_upload = (cfg.get("upload_to_youtube", True)
                 and not args.no_upload
                 and youtube_client is not None)
    do_cleanup = cfg.get("cleanup_after_upload", True) and not args.no_cleanup
    privacy = args.upload if args.upload else cfg.get("youtube_privacy", "public")
    min_disk = cfg.get("min_disk_gb", 2)

    log.info(f"{'=' * 50}")
    log.info(f"  VIDEO {video_num} — {label} — {ts}")
    if resource_mgr:
        log.info(f"  {resource_mgr.format_status()}")
    log.info(f"{'=' * 50}")

    free_gb = get_disk_free_gb()
    if free_gb < min_disk:
        log.error(f"Espacio insuficiente ({free_gb:.1f} GB < {min_disk} GB)")
        if resource_mgr:
            resource_mgr.emergency_cleanup()
            free_gb = get_disk_free_gb()
            if free_gb < min_disk:
                return False
        else:
            return False

    try:
        # ── 1. Historia larga ──
        log.info("[1/7] Generando historia larga...")
        long_story, named_chars = generate_long_story()
        long_meta = generate_metadata(long_story, is_short=False)
        long_title = long_meta.get("title", f"Historia {video_num}")
        long_desc = long_meta.get("description", long_story[:500])
        tags = long_meta.get("tags", [])
        hashtags = long_meta.get("hashtags", ["#LoLeiEnAlgunLugar"])

        story_id = save_story(
            long_title, long_desc,
            json.dumps(tags, ensure_ascii=False), long_story,
        )
        log.info(f"Historia: '{long_title[:50]}...' (ID: {story_id})")

        # ── 2. Guion short ──
        short_script = None
        short_meta = None
        if make_short:
            log.info("[2/7] Generando guion short...")
            try:
                short_script = generate_short_script(long_story, long_title)
                short_meta = generate_metadata(short_script, is_short=True)
            except Exception as e:
                log.warning(f"Short fallo, continuando sin el: {e}")
                make_short = False
        else:
            log.info("[2/7] Short omitido")

        force_gc()

        # ── 3. TTS ──
        log.info("[3/7] Generando voz TTS...")
        long_mp3 = os.path.join(work_dir, "voice_long.mp3")
        long_wav = os.path.join(work_dir, "voice_long.wav")
        generate_voice(long_story, long_mp3)
        convert_to_wav(long_mp3, long_wav)

        duration = get_audio_duration(long_mp3)
        log.info(f"Audio largo: {int(duration // 60)}:{int(duration % 60):02d}")

        short_mp3 = short_wav = None
        if make_short and short_script:
            short_mp3 = os.path.join(work_dir, "voice_short.mp3")
            short_wav = os.path.join(work_dir, "voice_short.wav")
            generate_voice(short_script, short_mp3)
            convert_to_wav(short_mp3, short_wav)

        del long_story, named_chars
        force_gc()

        # ── 4. Musica ──
        log.info("[4/7] Obteniendo musica...")
        music_path = None
        try:
            music_path = get_music(cfg.get("music_query", "epic"))
        except Exception as e:
            log.warning(f"Sin musica: {e}")

        # ── 5. Subtitulos ──
        log.info("[5/7] Generando subtitulos...")
        srt_long = transcribe_to_srt(
            long_wav, os.path.join(work_dir, "voice_long"),
        )
        ass_long = os.path.join(work_dir, "subs_long.ass")
        srt_to_ass(srt_long, ass_long, is_short=False, is_long=True)

        ass_short = srt_short = None
        if make_short and short_wav:
            srt_short = transcribe_to_srt(
                short_wav, os.path.join(work_dir, "voice_short"),
            )
            ass_short = os.path.join(work_dir, "subs_short.ass")
            srt_to_ass(srt_short, ass_short, is_short=True, is_long=False)

        force_gc()

        for wav in [long_wav, short_wav]:
            if wav and os.path.exists(wav):
                os.remove(wav)

        # ── 6. Render ──
        log.info("[6/7] Renderizando...")
        safe = (
            "".join(c if (c.isalnum() or c in " -_") else ""
                    for c in long_title[:40]).strip().replace(" ", "_")
            or "video"
        )
        long_out = os.path.join(OUTPUT_LARGOS, f"{ts}_{safe}.mp4")
        render_long_video(long_mp3, ass_long, music_path, long_out)

        short_out = None
        if make_short and short_mp3 and ass_short:
            short_out = os.path.join(OUTPUT_SHORTS, f"{ts}_{safe}_short.mp4")
            render_short_video(short_mp3, ass_short, music_path, short_out)

        long_size = os.path.getsize(long_out) / (1024 * 1024)
        log.info(f"Render completo: {long_size:.0f} MB")

        for f in [long_mp3, short_mp3, ass_long, ass_short, srt_long, srt_short]:
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

        # ── Metadatos TXT ──
        meta_dir = os.path.join(BASE_DIR, "output", "metadatos")
        save_metadata_txt(
            meta_dir, f"{ts}_largo.txt",
            long_title, long_desc, tags, hashtags, long_out,
        )
        if make_short and short_meta and short_out:
            s_title = (long_title + " #Shorts")[:100]
            s_desc = short_meta.get("description", "")
            s_tags = short_meta.get("tags", tags) + ["shorts"]
            s_hash = short_meta.get("hashtags", hashtags) + ["#shorts"]
            save_metadata_txt(
                meta_dir, f"{ts}_short.txt",
                s_title, s_desc, s_tags, s_hash, short_out,
            )

        # ── 7. Upload ──
        uploaded = False
        if do_upload:
            log.info("[7/7] Subiendo a YouTube...")
            try:
                full_long_desc = long_desc.rstrip() + "\n\n" + " ".join(hashtags)
                long_vid_id = upload_video(
                    youtube_client, long_out, long_title, full_long_desc,
                    tags, is_short=False, privacy=privacy,
                )
                log.info(f"Largo subido: https://youtu.be/{long_vid_id}")

                if short_out and os.path.exists(short_out):
                    short_title_yt = (long_title + " #Shorts")[:100]
                    short_tags = tags + ["shorts", "youtube shorts"]
                    short_meta_final = generate_metadata(
                        short_script or "",
                        is_short=True, long_video_id=long_vid_id,
                    )
                    short_desc_yt = short_meta_final.get(
                        "description",
                        f"{long_title}\n\nHistoria completa: "
                        f"https://youtu.be/{long_vid_id}",
                    )
                    upload_video(
                        youtube_client, short_out, short_title_yt,
                        short_desc_yt, short_tags,
                        is_short=True, privacy=privacy,
                    )
                    log.info("Short subido")

                if story_id:
                    mark_uploaded(story_id)
                uploaded = True

            except Exception as e:
                log.error(f"Error subiendo: {e}")
        else:
            log.info("[7/7] Subida omitida")

        # ── Limpieza ──
        if do_cleanup and uploaded:
            log.info("Limpiando videos renderizados...")
            for f in [long_out, short_out]:
                if f and os.path.exists(f):
                    try:
                        os.remove(f)
                        log.info(f"  Eliminado: {os.path.basename(f)}")
                    except Exception as e:
                        log.warning(f"  No se pudo eliminar {f}: {e}")

        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)

        force_gc()

        if resource_mgr:
            log.info(f"Video {video_num} completado. {resource_mgr.format_status()}")
        else:
            log.info(
                f"Video {video_num} completado. "
                f"Disco libre: {get_disk_free_gb():.1f} GB"
            )
        return True

    except Exception as e:
        log.error(f"Error en video {video_num}: {e}")
        if os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)
        force_gc()
        return False


# ══════════════════════════════════════════════════════════════
#  Modo Daemon (corre indefinidamente, X videos/dia)
# ══════════════════════════════════════════════════════════════

_shutdown = False


def _signal_handler(sig, frame):
    global _shutdown
    print("\n\n  Deteniendo tras el video actual...\n")
    _shutdown = True


def run_daemon(args):
    global _shutdown

    from modules.logger import setup_logger, get_logger
    from modules.config_manager import load_config
    from modules.story_database import init_db
    from modules.youtube_uploader import get_youtube_client
    from modules.resource_manager import ResourceManager

    setup_logger(os.path.join(BASE_DIR, "logs"))
    log = get_logger()
    cfg = load_config()

    if not cfg.get("api_key"):
        print("\n[ERROR] API key no configurada.")
        print("Ejecuta: python cli.py --wizard\n")
        return

    init_db()

    videos_per_day = cfg.get("videos_per_day", 20)
    interval_seconds = 86400 / videos_per_day
    do_upload = cfg.get("upload_to_youtube", True) and not args.no_upload

    resource_mgr = ResourceManager(
        min_disk_gb=cfg.get("min_disk_gb", 2),
        max_ram_pct=85,
        check_interval=30,
    )
    resource_mgr.start()

    log.info("=" * 55)
    log.info("  MODO DAEMON — Ejecucion continua")
    log.info("=" * 55)
    log.info(f"  Videos/dia:   {videos_per_day}")
    log.info(f"  Intervalo:    {interval_seconds / 60:.0f} min entre videos")
    log.info(f"  {resource_mgr.format_status()}")
    log.info(f"  Proveedor:    {cfg.get('provider', 'openrouter')}")
    log.info(f"  Modelo largo: {cfg.get('long_model')}")
    log.info(f"  Whisper:      {cfg.get('whisper_model', 'base')}")
    log.info(f"  FFmpeg:       preset={cfg.get('ffmpeg_preset', 'fast')}, "
             f"crf={cfg.get('ffmpeg_crf', 26)}")
    log.info("  Ctrl+C para detener de forma segura")
    log.info("=" * 55)

    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _signal_handler)

    youtube_client = None
    if do_upload:
        log.info("Autenticando YouTube...")
        try:
            youtube_client = get_youtube_client()
            log.info("YouTube listo")
        except Exception as e:
            log.error(f"Auth YouTube fallo: {e}")
            log.info("Continuando sin subida.")

    video_num = 0
    ok_count = 0
    fail_count = 0
    day_start = time.time()

    while not _shutdown:
        video_num += 1

        if not resource_mgr.wait_until_safe(timeout=600):
            log.error("Recursos insuficientes. Esperando 10 min...")
            time.sleep(600)
            continue

        start_time = time.time()
        label = f"{videos_per_day}/dia"
        success = run_single_video(
            video_num, label, args, cfg, youtube_client, log, resource_mgr,
        )

        if success:
            ok_count += 1
        else:
            fail_count += 1

        elapsed_today = time.time() - day_start
        if elapsed_today > 86400:
            log.info(
                f"--- Resumen del dia: {ok_count} exitosos, "
                f"{fail_count} fallidos ---"
            )
            day_start = time.time()
            ok_count = 0
            fail_count = 0

        if _shutdown:
            break

        elapsed = time.time() - start_time
        wait = max(30, interval_seconds - elapsed)
        next_time = datetime.fromtimestamp(time.time() + wait)
        log.info(
            f"Siguiente video en {wait / 60:.0f} min "
            f"(~{next_time.strftime('%H:%M')})"
        )

        wait_end = time.time() + wait
        while time.time() < wait_end and not _shutdown:
            time.sleep(min(10, wait_end - time.time()))

    log.info("=" * 55)
    log.info(f"  DAEMON DETENIDO")
    log.info(f"  Videos: {ok_count} OK, {fail_count} fallidos")
    log.info(f"  {resource_mgr.format_status()}")
    log.info("=" * 55)
    resource_mgr.stop()


# ══════════════════════════════════════════════════════════════
#  Modo Batch (N videos y para)
# ══════════════════════════════════════════════════════════════

def run_batch(args):
    from modules.logger import setup_logger, get_logger
    from modules.config_manager import load_config
    from modules.story_database import init_db
    from modules.youtube_uploader import get_youtube_client
    from modules.resource_manager import ResourceManager

    setup_logger(os.path.join(BASE_DIR, "logs"))
    log = get_logger()
    cfg = load_config()

    if not cfg.get("api_key"):
        print("\n[ERROR] API key no configurada.")
        print("Ejecuta: python cli.py --wizard\n")
        return

    init_db()

    total = args.batch
    do_upload = cfg.get("upload_to_youtube", True) and not args.no_upload

    resource_mgr = ResourceManager(
        min_disk_gb=cfg.get("min_disk_gb", 2),
    )
    resource_mgr.start()

    log.info(f"=== BATCH: {total} videos ===")
    log.info(f"  {resource_mgr.format_status()}")

    youtube_client = None
    if do_upload:
        log.info("Autenticando YouTube...")
        try:
            youtube_client = get_youtube_client()
            log.info("YouTube listo")
        except Exception as e:
            log.error(f"Auth YouTube fallo: {e}")

    ok_count = 0
    fail_count = 0

    for i in range(1, total + 1):
        if not resource_mgr.wait_until_safe(timeout=300):
            log.error("Espacio insuficiente. Deteniendo batch.")
            break

        success = run_single_video(
            i, f"{i}/{total}", args, cfg, youtube_client, log, resource_mgr,
        )

        if success:
            ok_count += 1
        else:
            fail_count += 1

        if i < total:
            log.info("Pausa de 30s...")
            time.sleep(30)

    log.info(
        f"=== BATCH TERMINADO: {ok_count} OK, {fail_count} fallidos "
        f"de {total} ==="
    )
    resource_mgr.stop()

    print(f"\n  Resultado: {ok_count}/{total} videos completados")
    print(f"  Fallidos: {fail_count}")
    print(f"  Disco libre: {get_disk_free_gb():.1f} GB")
    print(f"  Metadatos en: {os.path.join(BASE_DIR, 'output', 'metadatos')}\n")


# ══════════════════════════════════════════════════════════════
#  Verificar dependencias
# ══════════════════════════════════════════════════════════════

def check_deps():
    print("\n=== VERIFICACION DEL SISTEMA ===\n")
    import subprocess
    import glob as g

    checks = []

    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        checks.append(("FFmpeg", r.returncode == 0))
    except Exception:
        checks.append(("FFmpeg", False))

    try:
        r = subprocess.run(["ffprobe", "-version"], capture_output=True, timeout=5)
        checks.append(("FFprobe", r.returncode == 0))
    except Exception:
        checks.append(("FFprobe", False))

    for pkg, imp in [
        ("edge-tts", "edge_tts"),
        ("requests", "requests"),
        ("faster-whisper", "faster_whisper"),
        ("psutil", "psutil"),
        ("yt-dlp", "yt_dlp"),
        ("google-api-python-client", "googleapiclient"),
    ]:
        try:
            __import__(imp)
            checks.append((pkg, True))
        except ImportError:
            checks.append((pkg, False))

    from modules.subtitle_engine import WHISPER_CLI, WHISPER_MODEL
    checks.append(("Whisper CLI local", os.path.exists(WHISPER_CLI)))
    checks.append(("Modelo Whisper local", os.path.exists(WHISPER_MODEL)))

    bg_l = g.glob(os.path.join(BASE_DIR, "videos", "largos", "*.mp4"))
    bg_s = g.glob(os.path.join(BASE_DIR, "videos", "shorts", "*.mp4"))
    checks.append((f"Videos fondo largos ({len(bg_l)})", len(bg_l) > 0))
    checks.append((f"Videos fondo shorts ({len(bg_s)})", len(bg_s) > 0))

    from modules.secrets_manager import has_api_key
    checks.append(("API key en .secrets", has_api_key()))

    checks.append((
        "client_secrets.json",
        os.path.exists(os.path.join(BASE_DIR, "client_secrets.json")),
    ))

    for name, ok in checks:
        status = "[OK]" if ok else "[!!]"
        print(f"  {status} {name}")

    print()

    from modules.resource_manager import ResourceManager, get_swap_info
    rm = ResourceManager()
    rm._update_status()
    print(f"  {rm.format_status()}")

    swap = get_swap_info()
    if not swap["has_swap"]:
        checks.append(("Swap (memoria virtual)", False))
        print("  [!!] Sin swap — usa: python cli.py --swap")
    else:
        checks.append(("Swap (memoria virtual)", True))

    from modules.config_manager import load_config
    cfg = load_config()
    vpd = cfg.get("videos_per_day", 20)
    print(f"  Videos/dia: {vpd} (1 cada {86400 / vpd / 60:.0f} min)")

    print()
    if not all(ok for _, ok in checks[:2]):
        print("  FFmpeg es REQUERIDO:")
        print("    Linux:   sudo apt install ffmpeg")
        print("    macOS:   brew install ffmpeg")
        print("    Windows: https://ffmpeg.org/download.html\n")

    configured = os.path.exists(
        os.path.join(BASE_DIR, ".configured"),
    )
    print(f"  Estado: {'CONFIGURADO' if configured else 'SIN CONFIGURAR'}")
    if not configured:
        print("  Ejecuta: python cli.py --wizard")
    print()


def show_status():
    print("\n=== ESTADO DEL SISTEMA ===\n")

    from modules.config_manager import load_config
    from modules.secrets_manager import has_api_key
    from modules.resource_manager import ResourceManager

    cfg = load_config()

    rm = ResourceManager()
    rm._update_status()
    print(f"  {rm.format_status()}")
    print()

    print(f"  Proveedor:     {cfg.get('provider', 'openrouter')}")
    print(f"  API key:       {'configurada' if has_api_key() else 'NO configurada'}")
    print(f"  Modelo largo:  {cfg.get('long_model', '?')}")
    print(f"  Modelo short:  {cfg.get('short_model', '?')}")
    print(f"  Voz TTS:       {cfg.get('tts_voice', '?')}")
    print(f"  Whisper:       {cfg.get('whisper_model', '?')}")
    print(f"  FFmpeg:        preset={cfg.get('ffmpeg_preset')}, "
          f"crf={cfg.get('ffmpeg_crf')}")
    print(f"  Videos/dia:    {cfg.get('videos_per_day', 20)}")
    vpd = cfg.get("videos_per_day", 20)
    print(f"  Intervalo:     {86400 / vpd / 60:.0f} min")
    print(f"  YouTube:       {'activo' if cfg.get('upload_to_youtube') else 'desactivado'}")
    print(f"  Privacidad:    {cfg.get('youtube_privacy', 'public')}")
    print(f"  Limpieza:      {'auto' if cfg.get('cleanup_after_upload') else 'manual'}")

    import glob as g
    bg_l = len(g.glob(os.path.join(BASE_DIR, "videos", "largos", "*.mp4")))
    bg_s = len(g.glob(os.path.join(BASE_DIR, "videos", "shorts", "*.mp4")))
    print(f"  Videos fondo:  {bg_l} largos, {bg_s} shorts")
    print()


# ══════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Lo lei en algun lugar — Generador automatico de videos",
    )
    parser.add_argument(
        "--wizard", action="store_true",
        help="Ejecutar wizard de configuracion",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Verificar dependencias y sistema",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Ver estado actual del sistema",
    )
    parser.add_argument(
        "--backgrounds", action="store_true",
        help="Descargar mas videos de fondo",
    )
    parser.add_argument(
        "--swap", action="store_true",
        help="Crear/verificar swap (memoria virtual)",
    )
    parser.add_argument(
        "--batch", type=int, default=0,
        help="Generar N videos y parar (en vez de daemon)",
    )
    parser.add_argument(
        "--no-short", action="store_true",
        help="No generar Short",
    )
    parser.add_argument(
        "--no-upload", action="store_true",
        help="No subir a YouTube",
    )
    parser.add_argument(
        "--no-cleanup", action="store_true",
        help="No borrar archivos despues de subir",
    )
    parser.add_argument(
        "--upload", choices=["private", "unlisted", "public"],
        help="Subir con privacidad especifica",
    )

    args = parser.parse_args()

    # ── Comandos directos ──
    if args.wizard:
        from modules.setup_wizard import run_wizard
        run_wizard()
        print("\n  El sistema esta listo. Ejecuta: python cli.py\n")
        return

    if args.check:
        check_deps()
        return

    if args.status:
        show_status()
        return

    if args.backgrounds:
        from modules.bg_downloader import interactive_download
        interactive_download()
        return

    if args.swap:
        from modules.resource_manager import setup_swap_interactive, get_swap_info
        setup_swap_interactive()
        swap = get_swap_info()
        if swap["has_swap"]:
            print(f"\n  Swap activo: {swap['total_mb']:.0f} MB")
        return

    # ── Primera ejecucion → wizard automatico ──
    from modules.setup_wizard import is_first_run
    if is_first_run():
        print()
        print("=" * 50)
        print("  Primera ejecucion detectada")
        print("=" * 50)
        print()
        print("  Se iniciara el asistente de configuracion.")
        print()

        from modules.setup_wizard import run_wizard
        if not run_wizard():
            return

        print("\n  Iniciando sistema automatico...\n")
        time.sleep(3)

    # ── Banner ──
    print()
    print("=" * 55)
    print("  Lo lei en algun lugar — Sistema Automatico")
    print("=" * 55)
    print()

    # ── Batch o Daemon ──
    if args.batch > 0:
        run_batch(args)
    else:
        run_daemon(args)


if __name__ == "__main__":
    main()
