"""
modules/music_manager.py - Descarga musica desde freetouse.com API v3.
"""

import os
import random
import requests

from modules.logger import get_logger

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSIC_DIR = os.path.join(_BASE, "musica")

API_BASE = "https://api.freetouse.com/v3"
DATA_BASE = "https://data.freetouse.com"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120",
    "Referer": "https://freetouse.com/",
    "Origin": "https://freetouse.com",
    "Accept": "application/json",
}

SEARCH_QUERIES = ["epic", "cinematic", "dramatic", "emotional", "suspense", "inspirational"]


def search_tracks(query: str = "epic", limit: int = 8) -> list:
    log = get_logger()
    url = f"{API_BASE}/music/tracks/search?q={query}&limit={limit}"
    log.info(f"Buscando musica: '{query}'")
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        if not resp.ok:
            return []
        raw_tracks = resp.json().get("data", [])
        tracks = []
        for t in raw_tracks:
            tid = t.get("id")
            if not tid:
                continue
            tracks.append({
                "id": tid,
                "title": t.get("title", "track"),
                "duration": t.get("duration", 0),
                "download_url": f"{DATA_BASE}/music/tracks/{tid}/file/mp3",
            })
        log.info(f"Tracks encontrados para '{query}': {len(tracks)}")
        return tracks
    except Exception as e:
        log.warning(f"Error buscando musica '{query}': {e}")
        return []


def get_random_tracks(limit: int = 5) -> list:
    log = get_logger()
    url = f"{API_BASE}/music/tracks/all?limit={limit}&order=random"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        if not resp.ok:
            return []
        raw = resp.json().get("data", [])
        return [
            {"id": t["id"], "title": t.get("title", "track"), "duration": t.get("duration", 0),
             "download_url": f"{DATA_BASE}/music/tracks/{t['id']}/file/mp3"}
            for t in raw if t.get("id")
        ]
    except Exception as e:
        log.warning(f"Error obteniendo tracks aleatorios: {e}")
        return []


def download_track(track: dict, output_dir: str = None) -> str:
    log = get_logger()
    if output_dir is None:
        output_dir = MUSIC_DIR
    os.makedirs(output_dir, exist_ok=True)

    url = track.get("download_url")
    title = track.get("title", "track")
    if not url:
        return None

    safe = "".join(c for c in title if c.isalnum() or c in " -_").strip()[:50] or "track"
    out_path = os.path.join(output_dir, f"{safe}.mp3")

    if os.path.exists(out_path) and os.path.getsize(out_path) > 50_000:
        log.info(f"Musica ya descargada: {os.path.basename(out_path)}")
        return out_path

    log.info(f"Descargando: {title}")
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=90, stream=True)
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=16_384):
                if chunk:
                    f.write(chunk)
        size_kb = os.path.getsize(out_path) / 1024
        if size_kb < 50:
            os.remove(out_path)
            return None
        log.info(f"Descargada: {os.path.basename(out_path)} ({size_kb:.0f} KB)")
        return out_path
    except Exception as e:
        log.warning(f"Error descargando '{title}': {e}")
        if os.path.exists(out_path):
            os.remove(out_path)
        return None


def get_music(preferred_query: str = "epic") -> str:
    log = get_logger()
    os.makedirs(MUSIC_DIR, exist_ok=True)

    queries = [preferred_query] + [q for q in SEARCH_QUERIES if q != preferred_query]
    for query in queries:
        tracks = search_tracks(query, limit=6)
        if not tracks:
            continue
        random.shuffle(tracks)
        for track in tracks:
            path = download_track(track)
            if path:
                return path

    log.info("Buscando tracks aleatorios...")
    for track in get_random_tracks(limit=5):
        path = download_track(track)
        if path:
            return path

    existing = [
        os.path.join(MUSIC_DIR, f)
        for f in os.listdir(MUSIC_DIR)
        if f.lower().endswith((".mp3", ".wav", ".ogg", ".m4a"))
    ] if os.path.exists(MUSIC_DIR) else []
    if existing:
        chosen = random.choice(existing)
        log.info(f"Usando musica existente: {os.path.basename(chosen)}")
        return chosen

    log.warning("No se encontro musica disponible.")
    return None
