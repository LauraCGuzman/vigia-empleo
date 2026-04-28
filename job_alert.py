"""
🔍 Vigía de Empleo
Busca ofertas via JobSpy (LinkedIn + Indeed), filtra con Claude,
extrae skills del mercado y envía email semanal.

Configuración: edita config.yaml (no este archivo).
Dependencias:  pip install -r requirements.txt
"""

import os
import smtplib
import json
import time
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    print("⚠️  PyYAML no disponible. Instala con: pip install pyyaml")

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


# ─────────────────────────────────────────────
# CARGAR CONFIGURACIÓN
# ─────────────────────────────────────────────

def cargar_config() -> dict:
    config_path = Path("config.yaml")
    if not config_path.exists():
        print("❌ No se encontró config.yaml. Copia config.yaml.example y personalízalo.")
        raise FileNotFoundError("config.yaml no encontrado")
    if not YAML_AVAILABLE:
        raise ImportError("PyYAML no instalado: pip install pyyaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


CONFIG            = cargar_config()
MI_PERFIL         = CONFIG.get("perfil", "")
SEARCH_QUERIES    = [tuple(q) for q in CONFIG.get("busquedas", [])]
EMPRESAS_OBJETIVO = [e.lower() for e in CONFIG.get("empresas_objetivo", [])]
KEYWORDS_EXCLUDE  = [k.lower() for k in CONFIG.get("exclusiones", [])]
MY_SKILLS         = CONFIG.get("mis_skills", {})

SKILLS_TRACKER_PATH = Path("skills_tracker.json")


# ─────────────────────────────────────────────
# BÚSQUEDA EN PORTALES
# ─────────────────────────────────────────────

def buscar_ofertas() -> list[dict]:
    if not JOBSPY_AVAILABLE:
        print("❌ JobSpy no instalado.")
        return []

    print("🔍 Buscando en LinkedIn e Indeed...")
    todas = []

    for query, location in SEARCH_QUERIES:
        print(f"  → '{query}' en {location}")
        try:
            jobs = scrape_jobs(
                site_name=["linkedin", "indeed"],
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
            time.sleep(4)
        except Exception as e:
            print(f"    ⚠️  Error: {e}")

    print(f"  📦 {len(todas)} ofertas brutas encontradas")
    return todas


# ─────────────────────────────────────────────
# FILTRADO RÁPIDO
# ─────────────────────────────────────────────

def filtro_rapido(job: dict) -> bool:
    titulo = job.get("title", "").lower()
    desc   = job.get("description", "").lower()
    texto  = titulo + " " + desc
    if any(ex in texto for ex in KEYWORDS_EXCLUDE):
        return False
    if len(titulo) < 5:
        return False
    return True


def marcar_empresas_objetivo(ofertas: list[dict]) -> list[dict]:
    for job in ofertas:
        company = job.get("company", "").lower()
        job["es_objetivo"] = any(emp in company for emp in EMPRESAS_OBJETIVO)
    n_objetivo = sum(1 for j in ofertas if j["es_objetivo"])
    print(f"🏷️  Ofertas de empresas objetivo: {n_objetivo}/{len(ofertas)}")
    return ofertas


def deduplicar(ofertas: list[dict]) -> list[dict]:
    vistas, unicas = set(), []
    for job in ofertas:
        url = job.get("url", "")
        if url and url not in vistas:
            vistas.add(url)
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
        "skills": []
    }
    if not CLAUDE_AVAILABLE:
        return fallback
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("  ⚠️  ANTHROPIC_API_KEY no configurada.")
        return fallback

    prompt = f"""Eres un experto en reclutamiento técnico. Analiza si esta oferta encaja con el siguiente perfil y extrae los skills técnicos requeridos.

PERFIL:
{MI_PERFIL}

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
  "skills": ["Python", "SQL", "AWS", "scikit-learn"]
}}

Criterios de puntuación:
- 8-10: encaje excelente con el perfil y el rol objetivo
- 6-7: encaje bueno, algunos gaps menores
- 4-5: encaje parcial, vale la pena revisar
- <4: poco encaje con el perfil

Señales de alerta en "punto_clave" con ⚠️:
- "reportarás al CTO", "serás el primero en datos", "construir desde cero"
- Lista de responsabilidades muy heterogénea
- "buscamos autonomía e iniciativa", "entorno dinámico"
- Stack caótico o proyecto heredado sin documentar

Para "skills": extrae TODOS los skills técnicos mencionados en la oferta
(lenguajes, librerías, frameworks, cloud, metodologías, herramientas).
Usa nombres canónicos: "Python", "SQL", "AWS", "scikit-learn", "TensorFlow",
"Docker", "Kubernetes", "Airflow", "MLflow", "PySpark", "LLMs", "RAG",
"series temporales", "forecasting", "anomaly detection", "ETL", etc.
Máximo 20 skills por oferta."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            if "skills" not in result:
                result["skills"] = []
            return result
    except Exception as e:
        print(f"  ⚠️  Error en Claude: {e}")
    return fallback


# ─────────────────────────────────────────────
# SKILLS TRACKER
# ─────────────────────────────────────────────

def acumular_skills(ofertas: list[dict]) -> dict:
    """Extrae skills de las ofertas analizadas y los acumula en skills_tracker.json."""

    skills_semana: dict[str, int] = {}
    for job in ofertas:
        for skill in job.get("ia_analysis", {}).get("skills", []):
            skill = skill.strip()
            if skill:
                skills_semana[skill] = skills_semana.get(skill, 0) + 1

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


def top_skills_semana(skills_semana: dict, n: int = 15) -> list[tuple]:
    """Devuelve los N skills más frecuentes de la semana con estado del gap."""
    sorted_skills = sorted(skills_semana.items(), key=lambda x: x[1], reverse=True)[:n]
    result = []
    for skill, count in sorted_skills:
        estado = "no"
        for k, v in MY_SKILLS.items():
            if k.lower() == skill.lower():
                estado = v
                break
        result.append((skill, count, estado))
    return result


# ─────────────────────────────────────────────
# EMAIL HTML
# ─────────────────────────────────────────────

def generar_seccion_skills(skills_semana: dict) -> str:
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
      Actualiza mis_skills en config.yaml al avanzar en tu roadmap
    </div>
  </div>"""


def generar_email_html(ofertas: list[dict], skills_semana: dict) -> str:
    fecha = datetime.now().strftime("%d/%m/%Y")
    n = len(ofertas)
    ofertas.sort(key=lambda x: (
        x.get("es_objetivo", False),
        x.get("ia_analysis", {}).get("puntuacion", 5)
    ), reverse=True)

    roles_buscados = ", ".join(q for q, _ in SEARCH_QUERIES[:5])

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
    Fuentes: LinkedIn + Indeed &nbsp;·&nbsp;
    Filtrado: {'✅ Claude Haiku' if CLAUDE_AVAILABLE else '⚠️ Sin IA'} &nbsp;·&nbsp;
    🎯 = empresa objetivo
  </div>
"""

    if not ofertas:
        html += """  <div class="empty">
    <p style="font-size:36px">🔎</p>
    <p>Esta semana no hay ofertas que encajen con tu perfil.</p>
    <p style="font-size:13px">Sigue con tu plan. El momento llegará.</p>
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
    Buscando: {roles_buscados}
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

def main():
    print("=" * 60)
    print("🔍 VIGÍA DE EMPLEO – BÚSQUEDA SEMANAL")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    ofertas = buscar_ofertas()

    ofertas = [j for j in ofertas if filtro_rapido(j)]
    print(f"✂️  Tras filtro exclusión: {len(ofertas)}")

    ofertas = marcar_empresas_objetivo(ofertas)
    ofertas = deduplicar(ofertas)
    print(f"🔄 Únicas: {len(ofertas)}")

    print(f"\n🤖 Analizando con Claude...")
    ofertas_finales = []
    for i, job in enumerate(ofertas[:30]):
        print(f"  [{i+1}/{min(len(ofertas),30)}] {job['company']} · {job['title'][:45]}...")
        analysis = analizar_con_claude(job)
        job["ia_analysis"] = analysis
        if analysis.get("puntuacion", 5) >= 4:
            ofertas_finales.append(job)
        time.sleep(1.5)

    print(f"\n✅ Ofertas finales: {len(ofertas_finales)}")

    skills_semana = acumular_skills(ofertas_finales)
    html = generar_email_html(ofertas_finales, skills_semana)
    enviar_email(html, len(ofertas_finales))
    print("🎯 Proceso completado.")


if __name__ == "__main__":
    main()
