"""
modules/youtube_uploader.py - Subida a YouTube con OAuth2 (multiplataforma).
Soporta Linux headless: muestra URL para copiar al navegador.
"""

import os
import pickle
import time
import random

from modules.logger import get_logger

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT_SECRETS = os.path.join(_BASE, "client_secrets.json")
TOKEN_FILE = os.path.join(_BASE, "token.pickle")
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def _is_headless() -> bool:
    import platform
    if platform.system() != "Linux":
        return False
    display = os.environ.get("DISPLAY", "")
    wayland = os.environ.get("WAYLAND_DISPLAY", "")
    return not display and not wayland


def get_youtube_client():
    from googleapiclient.discovery import build
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    log = get_logger()
    creds = None

    if os.path.exists(TOKEN_FILE):
        log.info("Cargando token guardado...")
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            log.info("Renovando token expirado...")
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRETS):
                raise FileNotFoundError(
                    f"No se encontro client_secrets.json en:\n{CLIENT_SECRETS}\n"
                    "Descargalo desde Google Cloud Console > Credentials."
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS, SCOPES,
            )

            if _is_headless():
                log.info("Modo headless: autenticacion por consola")
                print()
                print("=" * 55)
                print("  AUTENTICACION DE YOUTUBE")
                print("=" * 55)
                print()
                print("  Copia esta URL en tu navegador:")
                print()

                auth_url, _ = flow.authorization_url(prompt="consent")
                print(f"  {auth_url}")
                print()
                code = input("  Pega aqui el codigo de autorizacion: ").strip()
                flow.fetch_token(code=code)
                creds = flow.credentials
            else:
                log.info("Abriendo navegador para autenticar YouTube...")
                creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
        log.info(f"Token guardado en: {TOKEN_FILE}")

    log.info("Cliente de YouTube listo.")
    return build("youtube", "v3", credentials=creds)


def upload_video(youtube, file_path, title, description, tags,
                 is_short=False, privacy="private") -> str:
    from googleapiclient.http import MediaFileUpload

    log = get_logger()

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Archivo de video no encontrado: {file_path}")

    if is_short and "#shorts" not in description.lower():
        description = description.rstrip() + "\n\n#shorts #viral #LoLeiEnAlgunLugar"

    title_clean = title[:100]
    desc_clean = description[:5000]
    tags_clean = [str(t)[:100] for t in (tags or []) if t][:30]

    body = {
        "snippet": {
            "title": title_clean,
            "description": desc_clean,
            "tags": tags_clean,
            "categoryId": "24",
            "defaultLanguage": "es",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "madeForKids": False,
        },
    }

    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    log.info(f"Subiendo: '{title_clean[:55]}...' ({size_mb:.1f} MB, privacidad: {privacy})")

    chunk_size = 25 * 1024 * 1024

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=MediaFileUpload(
            file_path, chunksize=chunk_size, resumable=True,
        ),
    )

    response = None
    last_pct = -1
    max_retries = 8

    while response is None:
        retry = 0
        while retry < max_retries:
            try:
                status, response = request.next_chunk(num_retries=3)
                if status:
                    pct = int(status.progress() * 100)
                    if pct != last_pct and pct % 5 == 0:
                        log.info(f"  Subida: {pct}%")
                        last_pct = pct
                break
            except Exception as e:
                retry += 1
                err_str = str(e).lower()
                if retry >= max_retries:
                    raise
                if any(kw in err_str for kw in
                       ("timed out", "timeout", "broken pipe",
                        "connection reset", "connection aborted")):
                    wait = min(2 ** retry + random.random(), 60)
                    log.warning(
                        f"  Error de red en chunk, reintentando en "
                        f"{wait:.0f}s ({retry}/{max_retries})..."
                    )
                    time.sleep(wait)
                else:
                    raise

    video_id = response.get("id", "desconocido")
    url = f"https://youtube.com/watch?v={video_id}"
    log.info(f"Video subido: {url}")
    return video_id


def update_video_description(youtube, video_id: str,
                             new_description: str) -> bool:
    log = get_logger()
    try:
        resp = youtube.videos().list(part="snippet", id=video_id).execute()
        items = resp.get("items", [])
        if not items:
            log.warning(f"Video {video_id} no encontrado.")
            return False

        snippet = items[0]["snippet"]
        snippet["description"] = new_description[:5000]

        youtube.videos().update(
            part="snippet",
            body={"id": video_id, "snippet": snippet},
        ).execute()

        log.info(f"Descripcion actualizada para: {video_id}")
        return True
    except Exception as e:
        log.warning(f"No se pudo actualizar descripcion de {video_id}: {e}")
        return False
