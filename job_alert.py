"""
🔍 Vigía de Empleo
Busca ofertas via JobSpy (LinkedIn + Indeed) y Climatebase, filtra con Claude,
extrae skills del mercado y envía email semanal.

Toda la configuración está en tres archivos (no necesitas tocar este código):
  config.yaml      → plataformas, búsquedas, empresas, filtros, criterios de IA
  perfil.txt       → tu perfil profesional (lo lee Claude para evaluar las ofertas)
  habilidades.yaml → tus skills y nivel actual (consolidado / aprendiendo / pendiente)

Dependencias: pip install -r requirements.txt
"""

import os
import smtplib
import json
import time
import re
import yaml
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

try:
    from jobspy import scrape_jobs
    JOBSPY_AVAILABLE = True
except ImportError:
    JOBSPY_AVAILABLE = False
    print("⚠️  JobSpy no disponible.")

try:
    import anthropic
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False
    print("⚠️  anthropic no disponible.")

try:
    from scrapers.climatebase import scrape_climatebase
    CLIMATEBASE_AVAILABLE = True
except ImportError:
    CLIMATEBASE_AVAILABLE = False
    print("⚠️  scrapers.climatebase no disponible.")


# ─────────────────────────────────────────────
# CARGA DE CONFIGURACIÓN
# ─────────────────────────────────────────────

def cargar_config() -> dict:
    """Carga config.yaml, perfil.txt y habilidades.yaml.
    Lanza un error claro si algún archivo falta.
    """
    for archivo in ["config.yaml", "perfil.txt", "habilidades.yaml"]:
        if not Path(archivo).exists():
            raise FileNotFoundError(
                f"\n❌ No se encuentra '{archivo}'.\n"
                f"   Asegúrate de que está en la misma carpeta que job_alert.py.\n"
                f"   Consulta el README para ver cómo rellenarlo."
            )

    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    with open("perfil.txt", "r", encoding="utf-8") as f:
        config["perfil"] = f.read().strip()

    with open("habilidades.yaml", "r", encoding="utf-8") as f:
        habilidades_raw = yaml.safe_load(f)

    # Convertir lista de habilidades al formato interno
    nivel_map = {"consolidado": "yes", "aprendiendo": "learning", "pendiente": "no"}
    skills = {}
    for h in habilidades_raw.get("habilidades", []):
        nombre = h["nombre"]
        nivel = nivel_map.get(h.get("nivel", "pendiente"), "no")
        aliases = [a.lower() for a in h.get("aliases", [])]
        skills[nombre] = {"aliases": aliases, "level": nivel}
    config["skills"] = skills

    # Aplanar tiers de empresas a lista plana para matching
    empresas_flat = []
    for tier_companies in config.get("empresas_objetivo", {}).values():
        if isinstance(tier_companies, list):
            empresas_flat.extend(e.lower() for e in tier_companies)
    config["_empresas_flat"] = empresas_flat

    return config


CONFIG = cargar_config()
SKILLS_TRACKER_PATH = Path("skills_tracker.json")


# ─────────────────────────────────────────────
# CLIENTE CLAUDE COMPARTIDO
# Se crea UNA sola vez (es thread-safe → reutilizable en el pool).
# timeout corta conexiones colgadas; max_retries acota el backoff ante
# 429/529 transitorios. Sin esto, una llamada muerta congela todo el run.
# ─────────────────────────────────────────────

_CLAUDE_CLIENT = None


def _get_claude_client():
    global _CLAUDE_CLIENT
    if _CLAUDE_CLIENT is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        _CLAUDE_CLIENT = anthropic.Anthropic(
            api_key=api_key,
            timeout=30.0,
            max_retries=3,
        )
    return _CLAUDE_CLIENT


# ─────────────────────────────────────────────
# BÚSQUEDA EN PORTALES
# ─────────────────────────────────────────────

def buscar_ofertas() -> list[dict]:
    """Busca ofertas en las fuentes activas según config.yaml → plataformas.

    Si una fuente está desactivada o falla, las otras siguen funcionando.
    """
    todas = []
    plataformas = CONFIG.get("plataformas", {})
    use_linkedin = plataformas.get("linkedin", True)
    use_indeed = plataformas.get("indeed", True)
    use_climatebase = plataformas.get("climatebase", True)

    # ── Fuente 1: JobSpy (LinkedIn + Indeed) ──
    site_name = []
    if use_linkedin:
        site_name.append("linkedin")
    if use_indeed:
        site_name.append("indeed")

    if not site_name:
        print("⏭️  LinkedIn e Indeed desactivados en config.yaml.")
    elif not JOBSPY_AVAILABLE:
        print("⏭️  JobSpy no disponible, saltando LinkedIn/Indeed.")
    else:
        label = " + ".join(s.capitalize() for s in site_name)
        print(f"🔍 Buscando en {label}...")
        n_jobspy = 0
        for query, location in CONFIG.get("busquedas_linkedin_indeed", []):
            print(f"  → '{query}' en {location}")
            try:
                jobs = scrape_jobs(
                    site_name=site_name,
                    search_term=query,
                    location=location,
                    results_wanted=10,
                    hours_old=168,
                    country_indeed="Spain",
                )
                for _, row in jobs.iterrows():
                    todas.append({
                        "title":       str(row.get("title", "")).strip(),
                        "company":     str(row.get("company", "")).strip(),
                        "url":         str(row.get("job_url", "")).strip(),
                        "description": str(row.get("description", ""))[:2000].strip(),
                        "location":    str(row.get("location", "España")).strip(),
                        "source":      str(row.get("site", "portal")),
                    })
                    n_jobspy += 1
                time.sleep(4)
            except Exception as e:
                print(f"    ⚠️  Error: {e}")
        print(f"  📦 {label}: {n_jobspy} ofertas")

    # ── Fuente 2: Climatebase (climate tech remota) ──
    if not use_climatebase:
        print("⏭️  Climatebase desactivado en config.yaml.")
    elif not CLIMATEBASE_AVAILABLE:
        print("⏭️  scrapers.climatebase no disponible.")
    else:
        print("\n🌱 Buscando en Climatebase (climate tech remoto EU)...")
        n_climatebase = 0
        for query in CONFIG.get("busquedas_climatebase", []):
            print(f"  → '{query}'")
            try:
                resultados = scrape_climatebase(query, max_results=30, only_remote=True)
                todas.extend(resultados)
                n_climatebase += len(resultados)
                time.sleep(1)
            except Exception as e:
                print(f"    ⚠️  Error: {e}")
        print(f"  📦 Climatebase: {n_climatebase} ofertas")

    print(f"\n  📦 TOTAL ofertas brutas (todas las fuentes): {len(todas)}")
    return todas


# ─────────────────────────────────────────────
# FILTRADO RÁPIDO
# ─────────────────────────────────────────────

def filtro_rapido(job: dict) -> bool:
    titulo = job.get("title", "").lower()
    desc   = job.get("description", "").lower()
    texto  = titulo + " " + desc
    if any(ex in texto for ex in CONFIG.get("palabras_excluir", [])):
        return False
    if len(titulo) < 5:
        return False
    return True


def marcar_empresas_objetivo(ofertas: list[dict]) -> list[dict]:
    for job in ofertas:
        company = job.get("company", "").lower()
        job["es_objetivo"] = any(emp in company for emp in CONFIG["_empresas_flat"])
    n_objetivo = sum(1 for j in ofertas if j["es_objetivo"])
    print(f"🏷️  Ofertas de empresas objetivo: {n_objetivo}/{len(ofertas)}")
    return ofertas


def _normalize_for_dedup(text: str) -> str:
    """Normaliza un string para comparación de duplicados:
    - lowercase
    - elimina espacios redundantes y signos de puntuación comunes
    - elimina paréntesis con contenido (ej. '(Madrid)', '(m/f/d)', '(Remote)')
    - quita sufijos típicos de seniority/género que varían entre listings
    """
    if not text:
        return ""
    s = text.lower().strip()
    s = re.sub(r'\([^)]*\)', '', s)
    s = re.sub(r'[,;:|\-–—/\\]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def deduplicar(ofertas: list[dict]) -> list[dict]:
    """Deduplica en dos pasadas:
    1. Por URL exacta (más rápido, captura re-scrapes).
    2. Por (título normalizado, empresa normalizada) — captura la misma oferta
       listada en LinkedIn + Indeed con URLs distintas.

    En caso de colisión cross-source, conserva la primera vista.
    """
    vistas_url, vistas_titulo_empresa, unicas = set(), set(), []
    for job in ofertas:
        url = job.get("url", "").strip()
        titulo_norm = _normalize_for_dedup(job.get("title", ""))
        empresa_norm = _normalize_for_dedup(job.get("company", ""))
        clave_tit_emp = (titulo_norm, empresa_norm)

        if url and url in vistas_url:
            continue
        if titulo_norm and empresa_norm and clave_tit_emp in vistas_titulo_empresa:
            continue

        if url:
            vistas_url.add(url)
        if titulo_norm and empresa_norm:
            vistas_titulo_empresa.add(clave_tit_emp)
        unicas.append(job)
    return unicas


# ─────────────────────────────────────────────
# ANÁLISIS CON CLAUDE (puntuación + skills)
# ─────────────────────────────────────────────

def analizar_con_claude(job: dict) -> dict:
    fallback = {
        "encaja": True, "puntuacion": 5,
        "razon": "Análisis IA no disponible. Revisión manual recomendada.",
        "punto_clave": "N/D",
        "eje": "principal",
        "skills": []
    }
    if not CLAUDE_AVAILABLE:
        return fallback
    client = _get_claude_client()
    if client is None:
        print("  ⚠️  ANTHROPIC_API_KEY no configurada.")
        return fallback

    ia_cfg = CONFIG.get("criterios_ia", {})

    ejes_text = "\n".join(
        f'- "{nombre}": {str(desc).strip()}'
        for nombre, desc in ia_cfg.get("ejes", {}).items()
    )
    penalizaciones_text = "\n".join(
        f"- {p}" for p in ia_cfg.get("penalizaciones", [])
    )
    no_penalizar_text = "\n".join(
        f"- {p}" for p in ia_cfg.get("no_penalizar", [])
    )
    criterios_descarte_text = "\n".join(
        f"- {c}" for c in ia_cfg.get("criterios_descarte", [])
    )
    senales_alerta_text = "\n".join(
        f"- {s}" for s in ia_cfg.get("senales_alerta", [])
    )
    bandas_text = str(ia_cfg.get("bandas_puntuacion", "")).strip()
    skills_canonicos = ", ".join(f'"{k}"' for k in CONFIG["skills"].keys())

    prompt = f"""Eres una experta en reclutamiento técnico para perfiles de datos (Data Science / Data Analytics / ML). Analiza si esta oferta encaja con el perfil del usuario, clasifica el eje sectorial y extrae los skills técnicos requeridos.

PERFIL DEL USUARIO:
{CONFIG["perfil"]}

OFERTA:
Título: {job.get('title', 'N/D')}
Empresa: {job.get('company', 'N/D')}
Ubicación: {job.get('location', 'N/D')}
Descripción: {job.get('description', 'Sin descripción')[:1500]}

Responde ÚNICAMENTE con JSON válido, sin texto adicional ni bloques de código:
{{
  "encaja": true,
  "puntuacion": 7,
  "razon": "explicación breve",
  "punto_clave": "factor clave o alerta",
  "eje": "principal",
  "skills": ["Python", "SQL", "AWS", "scikit-learn", "Time Series"]
}}

═══ CLASIFICACIÓN DE EJE ═══
Asigna UNO de estos valores al campo "eje":
{ejes_text}

═══ CRITERIOS DE PUNTUACIÓN (agnósticos al eje) ═══
Todos los ejes definidos compiten en igualdad, salvo "otros", que se penaliza por falta de fit narrativo (cajón de sastre sin dominio claro).

{bandas_text}

═══ PENALIZACIONES (sobre puntuación base) ═══
{penalizaciones_text}

═══ NO PENALIZAR ═══
{no_penalizar_text}

═══ CRITERIOS DE DESCARTE (encaja=false) ═══
{criterios_descarte_text}

Sé preciso: básate en el perfil del usuario tal como está descrito arriba, sin dar
por hechas experiencias que no menciona. No infles la puntuación por afinidad de
empresa si el rol no encaja con su nivel. Tampoco la desinfles por geografía o
idioma si el rol es técnicamente compatible y remoto real.

═══ SEÑALES DE ALERTA en "punto_clave" con ⚠️ ═══
{senales_alerta_text}

═══ SKILLS ═══
Extrae TODOS los skills técnicos mencionados en la oferta (lenguajes, librerías, frameworks,
cloud, metodologías, herramientas). USA NOMBRES CANÓNICOS EN INGLÉS para máxima estandarización:
{skills_canonicos}
Máximo 20 skills por oferta."""

    try:
        modelo = CONFIG.get("configuracion_general", {}).get("modelo_ia", "claude-haiku-4-5-20251001")
        response = client.messages.create(
            model=modelo,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            result.setdefault("skills", [])
            result.setdefault("eje", "otros")
            return result
    except Exception as e:
        print(f"  ⚠️  Error en Claude: {e}")
    return fallback


# ─────────────────────────────────────────────
# SKILLS TRACKER
# ─────────────────────────────────────────────

def acumular_skills(ofertas: list[dict]) -> dict:
    """Extrae skills de las ofertas analizadas y los acumula en skills_tracker.json.

    Cada skill se canonicaliza antes de contarse: aliases y variantes de
    capitalización colapsan a la clave canónica de habilidades.yaml.
    Skills no reconocidos se mantienen con su grafía original para inspección manual.
    """
    skills_semana: dict[str, int] = {}
    for job in ofertas:
        for skill in job.get("ia_analysis", {}).get("skills", []):
            if not skill or not skill.strip():
                continue
            canonical = _canonical_name(skill)
            skills_semana[canonical] = skills_semana.get(canonical, 0) + 1

    if SKILLS_TRACKER_PATH.exists():
        with open(SKILLS_TRACKER_PATH, "r", encoding="utf-8") as f:
            tracker = json.load(f)
    else:
        tracker = {"semanas": [], "acumulado": {}}

    fecha = datetime.now().strftime("%Y-%m-%d")
    tracker["semanas"].append({
        "fecha": fecha,
        "ofertas_analizadas": len(ofertas),
        "skills": skills_semana
    })

    for skill, count in skills_semana.items():
        tracker["acumulado"][skill] = tracker["acumulado"].get(skill, 0) + count

    with open(SKILLS_TRACKER_PATH, "w", encoding="utf-8") as f:
        json.dump(tracker, f, ensure_ascii=False, indent=2)

    print(f"📊 Skills tracker actualizado: {len(skills_semana)} skills distintos esta semana")
    return skills_semana


def _canonical_name(skill: str) -> str:
    """Devuelve el nombre canónico de un skill o el original si no hay match.

    Busca contra la clave canónica y todos sus aliases. Case-insensitive.
    """
    s = skill.strip()
    s_lower = s.lower()
    for canonical, info in CONFIG["skills"].items():
        if canonical.lower() == s_lower:
            return canonical
        if s_lower in info.get("aliases", []):
            return canonical
    return s


def _lookup_skill_level(skill: str) -> str:
    """Busca un skill en habilidades.yaml y devuelve su nivel.

    Match case-insensitive. Devuelve 'no' si no se encuentra.
    """
    s = skill.strip().lower()
    for canonical, info in CONFIG["skills"].items():
        if canonical.lower() == s:
            return info["level"]
        if s in info.get("aliases", []):
            return info["level"]
    return "no"


def top_skills_semana(skills_semana: dict, n: int = 15) -> list[tuple]:
    """Devuelve los N skills más frecuentes de la semana con estado del gap."""
    sorted_skills = sorted(skills_semana.items(), key=lambda x: x[1], reverse=True)[:n]
    return [(skill, count, _lookup_skill_level(skill)) for skill, count in sorted_skills]


# ─────────────────────────────────────────────
# EMAIL HTML
# ─────────────────────────────────────────────

def generar_seccion_skills(skills_semana: dict) -> str:
    """Genera la sección de skills para el email."""
    if not skills_semana:
        return ""

    top = top_skills_semana(skills_semana, n=15)

    estado_html = {
        "yes":      ('<span style="color:#2d6a4f;font-weight:700;">✅ Consolidado</span>', "#e6f4ea"),
        "learning": ('<span style="color:#e9a824;font-weight:700;">🔄 En curso</span>',    "#fff8e6"),
        "no":       ('<span style="color:#c0392b;font-weight:700;">❌ Pendiente</span>',   "#fdf0f0"),
    }

    filas = ""
    for skill, count, estado in top:
        badge_html, row_bg = estado_html.get(estado, estado_html["no"])
        barra_w = min(count * 20, 100)
        filas += f"""
        <tr style="background:{row_bg};">
          <td style="padding:7px 12px;font-size:13px;font-weight:500;">{skill}</td>
          <td style="padding:7px 12px;text-align:center;font-size:12px;color:#666;">{count}×</td>
          <td style="padding:7px 12px;">
            <div style="background:#e0e0e0;border-radius:3px;height:6px;width:100px;">
              <div style="background:#0f3460;height:6px;border-radius:3px;width:{barra_w}px;"></div>
            </div>
          </td>
          <td style="padding:7px 12px;font-size:12px;">{badge_html}</td>
        </tr>"""

    return f"""
  <div style="padding:20px 24px;border-top:2px solid #e9ecef;">
    <div style="font-size:13px;font-weight:700;color:#1a1a2e;margin-bottom:4px;">
      📊 Skills más demandados esta semana
    </div>
    <div style="font-size:11px;color:#999;margin-bottom:14px;">
      Top 15 · extraído de las ofertas analizadas
    </div>
    <table style="width:100%;border-collapse:collapse;font-family:-apple-system,sans-serif;">
      <thead>
        <tr style="background:#f8f9fa;border-bottom:1px solid #dee2e6;">
          <th style="padding:7px 12px;text-align:left;font-size:11px;color:#666;text-transform:uppercase;letter-spacing:.05em;">Skill</th>
          <th style="padding:7px 12px;text-align:center;font-size:11px;color:#666;text-transform:uppercase;letter-spacing:.05em;">Frec.</th>
          <th style="padding:7px 12px;font-size:11px;color:#666;text-transform:uppercase;letter-spacing:.05em;">Peso</th>
          <th style="padding:7px 12px;font-size:11px;color:#666;text-transform:uppercase;letter-spacing:.05em;">Tu nivel</th>
        </tr>
      </thead>
      <tbody>{filas}
      </tbody>
    </table>
    <div style="margin-top:12px;font-size:11px;color:#aaa;">
      ✅ Consolidado · 🔄 En curso · ❌ Pendiente &nbsp;|&nbsp;
      Actualiza tus niveles en habilidades.yaml al avanzar en el roadmap
    </div>
  </div>"""


def generar_email_html(ofertas: list[dict], skills_semana: dict) -> str:
    fecha = datetime.now().strftime("%d/%m/%Y")
    n = len(ofertas)
    ofertas.sort(key=lambda x: (
        x.get("es_objetivo", False),
        x.get("ia_analysis", {}).get("puntuacion", 5)
    ), reverse=True)

    # Fuentes activas para mostrar en el email
    plataformas = CONFIG.get("plataformas", {})
    fuentes_activas = []
    if plataformas.get("linkedin", True):    fuentes_activas.append("LinkedIn")
    if plataformas.get("indeed", True):      fuentes_activas.append("Indeed")
    if plataformas.get("climatebase", True): fuentes_activas.append("Climatebase")
    fuentes_label = " + ".join(fuentes_activas) if fuentes_activas else "Ninguna"

    # Términos de búsqueda para el pie del email
    terminos = list(dict.fromkeys(
        q[0] if isinstance(q, (list, tuple)) else q
        for q in CONFIG.get("busquedas_linkedin_indeed", [])
    ))[:6]
    terminos_label = " · ".join(terminos)

    html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8">
<style>
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#f5f5f5; margin:0; padding:20px; color:#333; }}
  .container {{ max-width:680px; margin:0 auto; background:white;
               border-radius:12px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,.1); }}
  .header {{ background:linear-gradient(135deg,#1a1a2e,#0f3460);
            color:white; padding:28px 30px; text-align:center; }}
  .header h1 {{ margin:0; font-size:22px; }}
  .header p  {{ margin:6px 0 0; opacity:.75; font-size:13px; }}
  .summary {{ background:#f8f9fa; padding:14px 24px; font-size:13px;
             color:#666; border-bottom:1px solid #e9ecef; }}
  .job {{ padding:20px 24px; border-bottom:1px solid #f0f0f0; }}
  .job.objetivo {{ border-left:3px solid #2d6a4f; }}
  .job:last-child {{ border-bottom:none; }}
  .job-top {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }}
  .job-title {{ font-size:16px; font-weight:600; color:#1a1a2e; margin:0 0 3px; }}
  .job-meta  {{ font-size:13px; color:#666; margin:0 0 10px; }}
  .badge {{ border-radius:20px; padding:4px 12px; font-size:12px;
            font-weight:700; white-space:nowrap; flex-shrink:0; color:white; }}
  .green  {{ background:#2d6a4f; }}
  .yellow {{ background:#e9a824; color:#333; }}
  .grey   {{ background:#888; }}
  .ia-box {{ background:#f8f9fa; border-left:3px solid #0f3460;
            padding:10px 14px; border-radius:0 6px 6px 0;
            font-size:13px; color:#555; margin:10px 0; line-height:1.5; }}
  .tag {{ display:inline-block; background:#e8f4fd; color:#1a73e8;
          border-radius:4px; padding:2px 7px; font-size:11px; margin:0 4px 8px 0; }}
  .tag-objetivo {{ background:#e6f4ea; color:#2d6a4f; }}
  .btn {{ display:inline-block; background:#0f3460; color:white;
          padding:8px 18px; border-radius:6px; text-decoration:none;
          font-size:13px; font-weight:600; margin-top:8px; }}
  .empty {{ padding:40px; text-align:center; color:#999; }}
  .footer {{ background:#f8f9fa; padding:18px 24px; text-align:center;
            font-size:11px; color:#aaa; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🔍 Vigía de Empleo</h1>
    <p>{fecha} &nbsp;·&nbsp; {n} oferta{'s' if n != 1 else ''} relevante{'s' if n != 1 else ''}</p>
  </div>
  <div class="summary">
    Fuentes: {fuentes_label} &nbsp;·&nbsp;
    Filtrado: {'✅ Claude' if CLAUDE_AVAILABLE else '⚠️ Sin IA'} &nbsp;·&nbsp;
    🎯 = empresa objetivo
  </div>
"""

    if not ofertas:
        html += """  <div class="empty">
    <p style="font-size:36px">🔎</p>
    <p>Esta semana no hay ofertas que encajen con tu perfil.</p>
    <p style="font-size:13px">Sigue con los cursos y el proyecto estrella. El momento llegará.</p>
  </div>
"""
    else:
        for job in ofertas:
            ia     = job.get("ia_analysis", {})
            score  = ia.get("puntuacion", 5)
            razon  = ia.get("razon", "")
            clave  = ia.get("punto_clave", "")
            src    = job.get("source", "portal").capitalize()
            es_obj = job.get("es_objetivo", False)

            if score >= 8:   badge_cls, emoji = "badge green",  "🟢"
            elif score >= 6: badge_cls, emoji = "badge yellow", "🟡"
            else:            badge_cls, emoji = "badge grey",   "⚪"

            ia_block     = f'<div class="ia-box"><strong>💡 {clave}</strong><br>{razon}</div>' if razon else ""
            objetivo_tag = '<span class="tag tag-objetivo">🎯 Empresa objetivo</span>' if es_obj else ""
            job_class    = "job objetivo" if es_obj else "job"

            html += f"""  <div class="{job_class}">
    <div class="job-top">
      <div>
        <div class="job-title">{job.get('title','Sin título')}</div>
        <div class="job-meta">🏢 {job.get('company','N/D')} &nbsp;·&nbsp; 📍 {job.get('location','España')}</div>
      </div>
      <span class="{badge_cls}">{emoji} {score}/10</span>
    </div>
    {objetivo_tag}<span class="tag">{src}</span>
    {ia_block}
    <br><a href="{job.get('url','#')}" class="btn" target="_blank">Ver oferta →</a>
  </div>
"""

    html += generar_seccion_skills(skills_semana)

    html += f"""  <div class="footer">
    Vigía de Empleo · generado automáticamente cada lunes<br>
    Buscando: {terminos_label}
  </div>
</div>
</body></html>"""
    return html


# ─────────────────────────────────────────────
# ENVÍO EMAIL
# ─────────────────────────────────────────────

def enviar_email(html_content: str, n_ofertas: int):
    remitente    = os.getenv("GMAIL_ADDRESS")
    password     = os.getenv("GMAIL_APP_PASSWORD")
    destinatario = os.getenv("DESTINATARIO_EMAIL", remitente)

    if not remitente or not password:
        print("⚠️  Credenciales Gmail no configuradas. Guardando email_preview.html")
        with open("email_preview.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔍 Vigía Empleo: {n_ofertas} oferta{'s' if n_ofertas != 1 else ''} relevante{'s' if n_ofertas != 1 else ''} esta semana"
    msg["From"]    = remitente
    msg["To"]      = destinatario
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(remitente, password)
            server.sendmail(remitente, destinatario, msg.as_string())
        print(f"✅ Email enviado a {destinatario} con {n_ofertas} ofertas.")
    except Exception as e:
        print(f"❌ Error enviando email: {e}")
        with open("email_preview.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        print("📄 Guardado como email_preview.html")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def muestreo_proporcional(ofertas: list[dict], cap: int = 300) -> list[dict]:
    """Selecciona hasta `cap` ofertas con muestreo proporcional al volumen de
    cada fuente. Garantiza que ninguna fuente domine completamente el batch.

    Estrategia:
    - Si len(ofertas) <= cap: devuelve todas, sin muestreo.
    - Si no: agrupa por 'source', asigna cuota proporcional, redondea preservando
      el total = cap. Cada fuente con ≥1 oferta obtiene mínimo 1 slot.
    - Dentro de cada fuente preserva el orden original (queries más relevantes
      primero, asumiendo que están al inicio de las listas en config.yaml).
    """
    if len(ofertas) <= cap:
        return ofertas

    grupos: dict[str, list[dict]] = {}
    for job in ofertas:
        src = job.get("source", "unknown")
        grupos.setdefault(src, []).append(job)

    total = len(ofertas)
    n_fuentes = len(grupos)

    cuotas: dict[str, int] = {}
    for src, items in grupos.items():
        proporcional = round(cap * len(items) / total)
        cuotas[src] = max(1, proporcional)

    diff = cap - sum(cuotas.values())
    if diff != 0:
        fuentes_por_volumen = sorted(grupos.keys(), key=lambda s: -len(grupos[s]))
        i = 0
        while diff != 0:
            src = fuentes_por_volumen[i % n_fuentes]
            if diff > 0 and cuotas[src] < len(grupos[src]):
                cuotas[src] += 1
                diff -= 1
            elif diff < 0 and cuotas[src] > 1:
                cuotas[src] -= 1
                diff += 1
            i += 1
            if i > cap * 2:
                break

    seleccion = []
    for src, n in cuotas.items():
        seleccion.extend(grupos[src][:n])

    print(f"📐 Muestreo proporcional (cap={cap}, total={total}):")
    for src, n in cuotas.items():
        print(f"   · {src}: {n} de {len(grupos[src])} disponibles")

    return seleccion



def main():
    print("=" * 60)
    print("🔍 VIGÍA DE EMPLEO – BÚSQUEDA SEMANAL")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    cfg_general = CONFIG.get("configuracion_general", {})
    puntuacion_minima = cfg_general.get("puntuacion_minima", 4)
    max_ofertas = cfg_general.get("max_ofertas", 300)

    ofertas = buscar_ofertas()

    ofertas = [j for j in ofertas if filtro_rapido(j)]
    print(f"✂️  Tras filtro exclusión: {len(ofertas)}")

    ofertas = marcar_empresas_objetivo(ofertas)
    ofertas = deduplicar(ofertas)
    print(f"🔄 Únicas: {len(ofertas)}")

    ofertas = muestreo_proporcional(ofertas, cap=max_ofertas)

    print(f"\n🤖 Analizando {len(ofertas)} ofertas con Claude (paralelo)...")
    ofertas_finales = []
    total = len(ofertas)
    completadas = 0

    def _procesar(job):
        return job, analizar_con_claude(job)

    # Pool pequeño: rápido pero sin reventar rate limits de Haiku.
    # map() preserva el orden de entrada, así el contador progresa en orden.
    with ThreadPoolExecutor(max_workers=6) as ex:
        for job, analysis in ex.map(_procesar, ofertas):
            completadas += 1
            print(f"  [{completadas}/{total}] {job['company']} · {job['title'][:45]}...")
            job["ia_analysis"] = analysis
            if analysis.get("puntuacion", 5) >= puntuacion_minima:
                ofertas_finales.append(job)

    print(f"\n✅ Ofertas finales: {len(ofertas_finales)}")

    skills_semana = acumular_skills(ofertas_finales)

    html = generar_email_html(ofertas_finales, skills_semana)
    enviar_email(html, len(ofertas_finales))
    print("🎯 Proceso completado.")


if __name__ == "__main__":
    main()
