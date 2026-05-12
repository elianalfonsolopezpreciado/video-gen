"""
modules/story_generator.py - Generacion de historias via API configurable.

Soporta:
  - OpenRouter (default) — con seleccion de modelo
  - OpenAI-compatible (cualquier API con formato /chat/completions)
"""

import json
import re
import time
import requests

from modules.logger import get_logger
from modules.config_manager import get_config
from modules.story_database import (
    get_story_elements,
    get_recent_story_titles,
    assign_names_to_characters,
)


# ── System prompts ──

_LONG_SYSTEM = """\
Eres el escritor principal del canal de YouTube "Lo lei en algun lugar" en espanol latinoamericano.

SOBRE EL CANAL:
Narra historias dramaticas anonimas estilo Reddit: confesiones reales (o que suenan reales),
dilemas morales, traiciones, secretos familiares y justicia poetica. Tono de telenovela corta
narrada en primera persona como si fuera un post en un foro anonimo.

ESTILO:
- Primera persona, voz de narrador real (no novelista)
- Parrafos cortos, ritmo agil — optimizado para TTS y escucha en YT
- Lenguaje coloquial latinoamericano (evita modismos muy regionales)
- Dialogos naturales ("me dijo:", "le respondi:")
- Sin asteriscos, sin listas, sin markdown — texto limpio para TTS
- 2800-3200 palabras de historia narrada
- Usa EXACTAMENTE los nombres de personajes que te den en el prompt
- Estructura:
  1. Intro gancho — 3 parrafos cortos, situacion impactante
  2. Desarrollo — conflicto central, revelaciones progresivas
  3. Climax — giro o revelacion fuerte a los 2/3 de la historia
  4. Cierre — resolucion + reflexion que invite a comentar
- Cierra con: "Si tuvieras que tomar esa decision, que harias tu? Cuentame en los comentarios."
"""

_SHORT_SYSTEM = """\
Eres el editor de shorts del canal "Lo lei en algun lugar" en espanol latinoamericano.

Tu tarea: condensar una historia larga en un gancho corto de 380-420 palabras
que haga que el espectador quiera ver el video largo completo.

REGLAS:
- Primera persona, mismo narrador que la historia larga
- Solo lo mas impactante: el gancho inicial + el giro mas dramatico, nada mas
- Corta en el momento de maxima tension — NO des el final
- Sin asteriscos, sin listas, sin markdown
- Termina SIEMPRE con: "El final de esta historia te va a dejar sin palabras. Encuentralo en el video largo — link en la descripcion."
"""

_SEO_SYSTEM = """\
Eres un experto en SEO de YouTube para canales de entretenimiento en espanol latinoamericano.

CANAL: "Lo lei en algun lugar" — historias dramaticas tipo Reddit.
AUDIENCIA: 18-45 anios, hispanohablantes, principalmente Mexico/Colombia/Argentina/Espana.

PRINCIPIOS:
- Titulos virales: numeros, preguntas, emociones fuertes, misterio
- Palabras clave: "reddit", "historia real", "no lo vas a creer", "esto me paso",
  "confesion", "traicion", "familia", "secreto", "verdad", "karma", "justicia"
- Descripcion engancha en los primeros 150 caracteres
- Tags mezclan genericos (historias, reddit, drama) + especificos del episodio
"""


# ── API call (multi-provider) ──

def _call_llm(messages: list, system: str, model: str = None,
              use_free_fallback: bool = False) -> str:
    log = get_logger()
    cfg = get_config()

    api_key  = cfg.get("api_key", "")
    base_url = cfg.get("api_base_url", "https://openrouter.ai/api/v1/chat/completions")
    provider = cfg.get("provider", "openrouter")

    if not api_key:
        raise RuntimeError("API key no configurada. Edita config.json o usa --setup")

    models_to_try = []
    if model:
        models_to_try.append(model)
    if use_free_fallback:
        free = cfg.get("free_models", ["openrouter/auto"])
        models_to_try += [m for m in free if m not in models_to_try]
    if not models_to_try:
        models_to_try = [cfg.get("long_model", "openrouter/auto")]

    all_messages = [{"role": "system", "content": system}] + messages

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://youtube.com/@loLeiEnAlgunLugar"
        headers["X-Title"] = "Lo lei en algun lugar"

    for m in models_to_try:
        for attempt in range(2):
            try:
                body = {"model": m, "messages": all_messages}
                resp = requests.post(base_url, headers=headers, json=body, timeout=180)

                if resp.status_code == 429:
                    if attempt == 0:
                        log.warning(f"Rate limit en {m}, reintentando en 8s...")
                        time.sleep(8)
                        continue
                    log.warning(f"Rate limit persistente en {m}, siguiente modelo.")
                    break

                if resp.status_code == 404:
                    log.warning(f"Modelo no disponible: {m}")
                    break

                if not resp.ok:
                    log.warning(f"Error {resp.status_code} en {m}: {resp.text[:200]}")
                    break

                content = resp.json()["choices"][0]["message"]["content"]
                log.info(f"[{m}]: {len(content)} chars")
                return content

            except Exception as e:
                log.warning(f"Fallo {m} intento {attempt + 1}: {e}")
                if attempt == 0:
                    time.sleep(5)

    raise RuntimeError("Todos los modelos fallaron. Verifica tu API key y config.json.")


def _clean_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    elif raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    return match.group() if match else raw


# ── Historia larga ──

def generate_long_story() -> tuple:
    log = get_logger()
    cfg = get_config()
    long_model = cfg.get("long_model", "mistralai/mistral-small-2603")
    log.info(f"Generando historia LARGA con {long_model}...")

    elements = get_story_elements()
    recent_titles = get_recent_story_titles(6)
    named_chars = assign_names_to_characters(elements["characters"])

    chars_str = "\n".join(
        f"- {c['assigned_name']} ({c['age']} anios, {c['role']}): {c['traits']}. {c['backstory']}"
        for c in named_chars
    )
    locs_str = "\n".join(f"- {l['name']}: {l['description']}" for l in elements["locations"])
    hooks_str = "\n".join(f"- {h['hook']}" for h in elements["hooks"])
    recent_str = "\n".join(f"- {t}" for t in recent_titles) if recent_titles else "Ninguna todavia"

    prompt = f"""Crea una historia dramatica LARGA (2800-3200 palabras) para "Lo lei en algun lugar".

PERSONAJES (usa EXACTAMENTE estos nombres en la historia):
{chars_str}

ESCENARIOS:
{locs_str}

GANCHOS DE TRAMA (elige uno o combinalos):
{hooks_str}

HISTORIAS RECIENTES (NO repitas el mismo conflicto central):
{recent_str}

Escribe la historia completa ahora. Solo el texto narrativo, sin titulos ni etiquetas."""

    story_text = _call_llm(
        [{"role": "user", "content": prompt}],
        system=_LONG_SYSTEM,
        model=long_model,
        use_free_fallback=True,
    )

    story_text = story_text.strip()
    for prefix in ["Historia:", "**Historia:**", "Narracion:", "---"]:
        if story_text.startswith(prefix):
            story_text = story_text[len(prefix):].strip()

    word_count = len(story_text.split())
    log.info(f"Historia larga: {len(story_text)} chars (~{word_count} palabras)")
    return story_text, named_chars


# ── Historia corta ──

def generate_short_script(long_story: str, long_title: str) -> str:
    log = get_logger()
    cfg = get_config()
    short_model = cfg.get("short_model", "openrouter/auto")
    log.info(f"Generando guion SHORT con {short_model}...")

    prompt = f"""Aqui esta la historia larga completa:

---
{long_story[:4000]}
---

Titulo del video largo: "{long_title}"

Condensa esta historia en un gancho de 380-420 palabras para un YouTube Short.
Recuerda: corta en el momento de maxima tension, NO des el final.
Solo el texto narrativo, sin titulos ni etiquetas."""

    script = _call_llm(
        [{"role": "user", "content": prompt}],
        system=_SHORT_SYSTEM,
        model=short_model,
        use_free_fallback=True,
    )

    script = script.strip()
    for prefix in ["Guion:", "**Guion:**", "Short:", "---"]:
        if script.startswith(prefix):
            script = script[len(prefix):].strip()

    cta = "El final de esta historia te va a dejar sin palabras. Encuentralo en el video largo — link en la descripcion."
    if cta not in script:
        script = script.rstrip(".").rstrip() + "\n\n" + cta

    log.info(f"Guion short: ~{len(script.split())} palabras")
    return script


# ── Metadatos SEO ──

def generate_metadata(story_text: str, is_short: bool = False,
                      long_video_id: str = None) -> dict:
    log = get_logger()
    log.info(f"Generando metadatos SEO ({'short' if is_short else 'largo'})...")

    link_hint = ""
    if is_short and long_video_id:
        link_hint = f'\nEl campo "description" DEBE incluir al final: "Historia completa: https://youtu.be/{long_video_id}"'

    prompt = f"""Basandote en esta historia, genera metadatos para YouTube en espanol.

HISTORIA:
{story_text[:3000]}

{"Es un SHORT de menos de 60 segundos." if is_short else "Es un video largo de 10-30 minutos."}
{link_hint}

Devuelve EXACTAMENTE este JSON (sin markdown, sin texto extra):
{{
  "title": "Titulo de maximo 80 caracteres — gancho emocional + palabras clave",
  "description": "Parrafo 1 (150 chars, gancho fuerte). Parrafo 2 (resumen breve). Parrafo 3 (llamada a comentar/suscribirse). Termina con los hashtags.",
  "tags": ["historia real", "reddit en espanol", "drama familiar", "...hasta 28 tags"],
  "hashtags": ["#LoLeiEnAlgunLugar", "#Reddit", "#HistoriasReales", "#Drama", "#Viral"],
  "thumbnail_text": "Maximo 6 palabras impactantes para miniatura"
}}"""

    raw = _call_llm(
        [{"role": "user", "content": prompt}],
        system=_SEO_SYSTEM,
        use_free_fallback=True,
    )

    cleaned = _clean_json(raw)
    try:
        metadata = json.loads(cleaned)
    except json.JSONDecodeError as e:
        log.warning(f"JSON invalido en metadatos: {e}. Usando defaults.")
        metadata = {
            "title": "Historia que te dejara sin palabras | Lo lei en algun lugar",
            "description": story_text[:300] + "\n\n#LoLeiEnAlgunLugar #Reddit #Drama",
            "tags": ["historia real", "reddit en espanol", "drama", "confesion"],
            "hashtags": ["#LoLeiEnAlgunLugar", "#Reddit", "#HistoriasReales"],
            "thumbnail_text": "No lo vas a creer",
        }

    if is_short and long_video_id:
        link_line = f"\n\nHistoria completa: https://youtu.be/{long_video_id}"
        desc = metadata.get("description", "")
        if long_video_id not in desc:
            metadata["description"] = desc + link_line

    log.info(f"Titulo: {metadata.get('title', '')[:60]}...")
    return metadata
